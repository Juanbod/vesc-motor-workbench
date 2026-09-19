"""Legacy current telemetry plus a short controller-timed counter/angle snapshot."""
from dataclasses import replace
import math
import secrets
from time import perf_counter

from .counter_angle import signed_delta
from .locked_probe import ProbeClient
from .native_counter_snapshot import (DistanceCounterDecoder, read_counter_snapshot,
                                     prepared_expression, checked_repl_ack, SNAPSHOT_METHOD, DQ_SNAPSHOT_METHOD)
from .wire_config import decode_config


class NativePacketProjector:
    def __init__(self, configuration, calibration, maximum_rpm):
        self.low, self.high = calibration['tick_hz_lower'], calibration['tick_hz_upper']
        if (not all(math.isfinite(v) for v in (self.low, self.high, maximum_rpm))
                or not 9000 <= self.low <= self.high <= 11000
                or (self.high-self.low)/self.low > .001 or maximum_rpm <= 0):
            raise ValueError('Invalid native clock calibration or RPM envelope')
        self.configuration = configuration
        self.reference_scale = calibration.get('distance_scale')
        self.maximum_rpm = maximum_rpm
        self.decoder = None
        self.anchor = None
        self.previous_end = None
        self.elapsed = 0

    def project(self, legacy, snapshot, legacy_requested_s, confirmation=None):
        if self.decoder is None:
            if confirmation is None:
                raise ValueError('Fresh quiet counter confirmation required')
            for values in (legacy, confirmation):
                if (values.fault_code or abs(values.current_motor_a) > .1
                        or math.hypot(values.id_a, values.iq_a) > .2 or abs(values.duty) > .001):
                    raise ValueError('Native counter calibration requires zero current')
            if (legacy.tachometer, legacy.tachometer_abs) != (confirmation.tachometer, confirmation.tachometer_abs):
                raise ValueError('Native calibration sectors moved')
            self.decoder = DistanceCounterDecoder(self.configuration, snapshot, legacy.tachometer, legacy.tachometer_abs)
            if len(self.decoder.scales) != 1:
                raise ValueError('Native scale must be uniquely calibrated before use')
            if self.reference_scale is not None and self.decoder.scales[0] != self.reference_scale:
                raise ValueError('Native distance scale differs from the qualified reference')
        signed = self.decoder.recover(snapshot['distance'])
        absolute = self.decoder.recover(snapshot['distance_abs'])
        duration = snapshot['host_received_s']-legacy_requested_s
        if not 0 < duration <= .1:
            raise ValueError('Legacy/native correspondence is too old')
        ds, da = signed_delta(signed, legacy.tachometer), signed_delta(absolute, legacy.tachometer_abs)
        if 30*abs(ds) > 6*self.maximum_rpm*duration+30.2 or da < 0 or da+2 < abs(ds):
            raise ValueError('Native snapshot disagrees with bracketing legacy counters')
        end = snapshot['end_tick']
        if self.previous_end is not None:
            delta = (end-self.previous_end) & 0xffffffff
            if not 0 < delta < 2**31:
                raise ValueError('Native clock reset or stopped')
            self.elapsed += delta
        if self.anchor is None:
            self.anchor = snapshot
        if snapshot['host_request_s']-self.anchor['host_received_s'] > 1:
            ticks = (end-self.anchor['end_tick']) & 0xffffffff
            native_low, native_high = (ticks-1)/self.high, (ticks+1)/self.low
            host_low = snapshot['host_request_s']-self.anchor['host_received_s']
            host_high = snapshot['host_received_s']-self.anchor['host_request_s']
            if native_high < host_low or native_low > host_high:
                raise ValueError('Native timer drift exceeds the calibrated clock interval')
        self.previous_end = end
        extra = dict(native_start_tick=snapshot['start_tick'], native_end_tick=end,
                     native_elapsed_ticks=self.elapsed, native_tick_hz_lower=self.low,
                     native_tick_hz_upper=self.high, native_distance_scale=self.decoder.scales[0],
                     native_distance=snapshot['distance'], native_distance_abs=snapshot['distance_abs'],
                     native_encoder_error_rate=snapshot['encoder_error_rate'], native_nonce=snapshot['nonce'],
                     native_host_request_s=snapshot['host_request_s'], native_host_received_s=snapshot['host_received_s'],
                     native_legacy_tachometer=legacy.tachometer, native_legacy_tachometer_abs=legacy.tachometer_abs)
        extra.update({f'native_{key}': value for key, value in snapshot.items() if key.startswith('dq_')})
        return replace(legacy, tachometer=signed, tachometer_abs=absolute), extra


class NativeProbeClient(ProbeClient):
    def __init__(self, *args, baseline, clock_calibration, maximum_rpm, dq=False, **kwargs):
        self.dq = dq
        self.native_clock_reference = clock_calibration
        self.projector = NativePacketProjector(decode_config(baseline, 'motor'), clock_calibration, maximum_rpm)
        self.native_counter_record = None
        self.nonce = secrets.randbelow(0xffffff)+1
        self.snapshot_name = 'wbcs'+secrets.token_hex(6)
        self.snapshot_setup_attempted = False
        self.native_snapshot_runtime = dict(method=DQ_SNAPSHOT_METHOD if dq else SNAPSHOT_METHOD, installed=False,
                                            removed=False, flash_writes=False,
                                            function_name=self.snapshot_name)
        super().__init__(*args, **kwargs)

    def __enter__(self):
        try:
            self.send_payload(bytes((130,))+bytes(8))
            if self.read_response(130) != bytes((130,))+bytes(8):
                raise ValueError('Prepared snapshot requires empty Lisp storage')
            legacy = super().get_values()
            if (legacy.fault_code or abs(legacy.current_motor_a) > .1
                    or math.hypot(legacy.id_a, legacy.iq_a) > .2 or abs(legacy.duty) > .001):
                raise ValueError('Snapshot setup requires zero current')
            self.snapshot_setup_attempted = True
            checked_repl_ack(self, prepared_expression(self.snapshot_name, dq=self.dq), 6818)
            self.native_snapshot_runtime['installed'] = True
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        try:
            if self.snapshot_setup_attempted:
                checked_repl_ack(self, prepared_expression(self.snapshot_name, remove=True), 6819)
                self.native_snapshot_runtime['removed'] = True
                self.snapshot_setup_attempted = False
        finally:
            super().close()

    def get_values(self):
        if not self.native_snapshot_runtime['installed']:
            raise ValueError('Native snapshot function has not been prepared')
        self.native_counter_record = None
        requested = perf_counter()
        legacy = super().get_values()
        legacy_position = self.pid_position
        snapshot = read_counter_snapshot(self, self.nonce, prepared_name=self.snapshot_name, dq=self.dq)
        self.nonce = self.nonce % 0xffffff+1
        confirmation = super().get_values() if self.projector.decoder is None else None
        values, extra = self.projector.project(legacy, snapshot, requested, confirmation)
        extra['native_legacy_position_deg'] = legacy_position
        self.pid_position = snapshot['position_deg']
        self.native_counter_record = extra
        return values
