"""Small return-current experiment, not a battery charging controller."""
import json
import math
from pathlib import Path

BATTERY_PATH = Path(__file__).resolve().parents[1]/'config'/'bench-battery.json'


def require_battery_source():
    source = json.loads(BATTERY_PATH.read_text(encoding='utf-8'))
    if (source.get('schema') != 'bench-battery-v1' or source.get('source') != 'battery'
            or source.get('confirmed_by_user') is not True
            or source.get('series_cells') != 6 or source.get('parallel_cells') != 1
            or source.get('capacity_ah') != 4.5):
        raise ValueError('Reviewed user-confirmed 6S1P battery source required')
    return source


class BatteryReturnMonitor:
    def __init__(self):
        self.energy_j = 0.0
        self.previous = None
        self.exceeded = False

    def observe(self, row):
        for key in ('v_in', 'current_in_a', 't'):
            if not isinstance(row.get(key), (float, int)) or not math.isfinite(row[key]):
                self.exceeded = True
                raise ValueError('Missing or nonfinite battery telemetry')
        voltage, current, now = row['v_in'], row['current_in_a'], row['t']
        power = max(0.0, -voltage*current)
        if self.previous is not None:
            previous_t, previous_power = self.previous
            if now <= previous_t:
                self.exceeded = True
                raise ValueError('Invalid battery telemetry ordering')
            # Conservative endpoint rectangle; still a sampled VESC estimate.
            self.energy_j += max(power, previous_power)*(now-previous_t)
        self.previous = now, power
        if (not 21 <= voltage < 24.9 or current < -.1
                or (self.energy_j >= .25 and power > 0)):
            self.exceeded = True
            raise ValueError('Battery voltage, reverse current or returned-energy limit')
        return self.energy_j


def audit_battery_return(samples):
    monitor = BatteryReturnMonitor()
    for row in samples:
        energy = monitor.observe(row)
        if ('returned_energy_j' not in row or not math.isfinite(row['returned_energy_j'])
                or abs(row['returned_energy_j']-energy) > .00001):
            raise ValueError('Returned-energy replay disagrees with recorded samples')
    if monitor.exceeded:
        raise ValueError('Battery-return guard was exceeded')
    return monitor.energy_j
