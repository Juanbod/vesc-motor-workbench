"""Controller-timed counter reconstruction with explicit clock-rate uncertainty."""
import math

from .counter_angle import CounterAngle
from .native_counter_snapshot import f32


class NativeCounterAngle(CounterAngle):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calibration = None

    def update_coast(self, row, *, allow_defer=False):
        if allow_defer:
            raise ValueError('Native acquisition has no deferred-capture mode')
        return self.update(row)

    def update(self, row):
        names = ('native_tick_hz_lower', 'native_tick_hz_upper', 'native_distance_scale',
                 'native_distance', 'native_distance_abs')
        if any(not isinstance(row.get(k), (int, float)) or not math.isfinite(row[k]) for k in names):
            raise ValueError('Missing native calibration/distance data')
        low, high, scale = (row[k] for k in names[:3])
        if not 9000 <= low <= high <= 11000 or (high-low)/low > .001 or scale <= 0:
            raise ValueError('Native calibration outside its reviewed interval')
        calibration = (low, high, scale)
        if self.calibration is not None and calibration != self.calibration:
            raise ValueError('Native calibration changed during acquisition')
        for key in ('native_start_tick', 'native_end_tick', 'native_elapsed_ticks'):
            if type(row.get(key)) is not int or not 0 <= row[key] < 2**32:
                raise ValueError('Invalid native clock field')
        end, start = row['native_end_tick'], row['native_start_tick']
        width = (end-start) & 0xffffffff
        if width > 100:
            raise ValueError('Native capture bracket exceeds 10 ms')
        if self.previous is not None:
            gap = (end-self.previous['native_end_tick']) & 0xffffffff
            if gap != row['native_elapsed_ticks']-self.previous['native_elapsed_ticks']:
                raise ValueError('Native elapsed ticks disagree with raw timestamp increments')
        for distance_key, counter_key in (('native_distance', 'tachometer'), ('native_distance_abs', 'tachometer_abs')):
            value = row[distance_key]
            estimate = value/scale
            if abs(estimate) >= 2**23:
                raise ValueError('Native counter float32 precision exceeded')
            centre = math.floor(estimate)
            possibilities = {n for n in range(centre-2, centre+4) if f32(n*scale) == value}
            if possibilities != {row[counter_key]}:
                raise ValueError('Native raw distance does not uniquely reproduce the sector counter')
        # Low clock rate makes all time/bracket bounds conservative for unwrapping.
        projected = dict(row, t=(row['native_elapsed_ticks']+1)/low, latency_s=(width+1)/low)
        evidence = super().update(projected)
        factor = high/low
        bounds = [evidence[k]*f for k in ('counter_rpm_lower', 'counter_rpm_upper') for f in (1, factor)]
        evidence['counter_rpm'] *= (1+factor)/2
        evidence['counter_rpm_lower'], evidence['counter_rpm_upper'] = min(bounds), max(bounds)
        self.calibration = calibration
        return evidence
