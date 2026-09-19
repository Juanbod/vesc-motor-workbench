"""Read controller-computed electrical angle error without selecting sensorless."""
from dataclasses import asdict
from time import perf_counter as monotonic, sleep
import math
import statistics

from .bench import BenchStop, EncoderMotion, HardwareBench


class ObserverBench(HardwareBench):
    def __init__(self, port):
        self.observer_enabled = False
        self.last_position_at = None
        super().__init__(port)

    def prepare(self, plan):
        self.max_position_gap = 30 * self.values['foc_encoder_ratio'] / plan.max_erpm
        if abs(self.values['p_pid_ang_div'] - 1) > 1e-6:
            raise BenchStop('Observer diagnostic requires unscaled PID position (divider 1)')
        super().prepare(plan)
        # Match the separate GET_VALUES position channel to raw encoder data
        # while torque is off, before changing the untagged position stream.
        deadline = monotonic() + .15
        while monotonic() < deadline:
            self.stop()
            self.client.get_values()
            sleep(.02)
        pos, raw = self.client.pid_position, self.client.rotor_angle
        if pos is None or raw is None or abs((pos - raw + 180) % 360 - 180) > 3:
            raise BenchStop('GET_VALUES position does not match the raw encoder at rest')
        self.client.set_position_stream(6)
        # Mode packets have no type tag. Drain old frames only while stopped.
        deadline = monotonic() + .15
        while monotonic() < deadline:
            self.stop()
            self.client.get_values()
            sleep(.02)
        self.motion = EncoderMotion(self.values['foc_encoder_ratio'],
                                    -1 if self.values['foc_encoder_inverted'] else 1)
        self.observer_enabled = True

    def sample(self):
        if not self.observer_enabled:
            return super().sample()
        values = asdict(self.client.get_values())
        now = monotonic()
        pos = self.client.pid_position
        if pos is None or not 0 <= pos < 360:
            raise BenchStop('Independent encoder position unavailable')
        if (self.last_position_at is not None and abs(values['erpm']) > 20
                and self.client.pid_received_at - self.last_position_at >= self.max_position_gap):
            raise BenchStop('Position sampling gap could alias rotor motion')
        self.last_position_at = self.client.pid_received_at
        self.motion.update([(self.client.pid_received_at, pos)], batched=True)
        values.update(encoder_angle=pos, encoder_age=now-self.client.pid_received_at,
                      encoder_erpm=self.motion.speed, turns=self.motion.turns,
                      observer_error_deg=self.client.observer_error
                      if self.client.observer_error is not None else math.nan,
                      observer_error_age=now-self.client.observer_received_at)
        return values

    def close(self):
        if self.observer_enabled:
            try:
                self.stop()
                self.client.stream_encoder(True)
                deadline = monotonic() + .15
                while monotonic() < deadline:
                    self.stop()
                    self.client.get_values()
                    sleep(.02)
                self.client.rotor_samples.clear()
                self.motion = EncoderMotion(self.values['foc_encoder_ratio'],
                                            -1 if self.values['foc_encoder_inverted'] else 1)
                self.observer_enabled = False
            except Exception as exc:
                # No write is allowed if switching back to raw position fails.
                self.client.close()
                return dict(motor_restored=not self.modified,
                            app_output='disabled until power cycle' if self.isolated else 'unverified',
                            error=f'Raw encoder recovery stream unavailable: {exc}')
        return super().close()


def summarize_observer_error(samples):
    if not samples:
        return {'valid': False, 'reason': 'No samples'}
    cutoff = (samples[0]['t'] + samples[-1]['t']) / 2
    tail = [s for s in samples if s['t'] >= cutoff]
    errors = [s['observer_error_deg'] for s in tail]
    if any(not math.isfinite(e) or abs(e) > 180 for e in errors):
        return {'valid': False, 'reason': 'Invalid electrical angle difference'}
    sine = statistics.mean(math.sin(math.radians(e)) for e in errors)
    cosine = statistics.mean(math.cos(math.radians(e)) for e in errors)
    bias = math.degrees(math.atan2(sine, cosine))
    resultant = math.hypot(sine, cosine)
    residuals = [abs((e-bias+180) % 360-180) for e in errors]
    rank = max(0, math.ceil(len(errors)*.95)-1)
    absolute_p95 = sorted(abs(e) for e in errors)[rank]
    residual_p95 = sorted(residuals)[rank]
    seconds = tail[-1]['t'] - tail[0]['t']
    return dict(valid=True, samples=len(errors), evaluation_s=seconds,
                mean_error_deg=bias if resultant >= .8 else None,
                mean_error_reliable=resultant >= .8, resultant=resultant,
                p95_absolute_error_deg=absolute_p95,
                p95_residual_deg=residual_p95,
                min_error_deg=min(errors), max_error_deg=max(errors),
                mean_encoder_erpm=statistics.mean(s['encoder_erpm'] for s in tail),
                passes_angle_screen=seconds >= 2 and len(errors) >= 50
                and abs(bias) <= 15 and absolute_p95 <= 25 and resultant >= .95,
                sensorless_validated=False)
