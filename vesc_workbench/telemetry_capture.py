"""Bracket a complete GET_VALUES transaction before formatting its log record."""
from dataclasses import asdict
from time import perf_counter

CAPTURE_TIMING = 'get_values_return_before_formatting_v1'


def capture_values(client, clock=perf_counter):
    before = clock()
    values = client.get_values()
    received = clock()
    position = client.pid_position
    row = dict(asdict(values), position_deg=position, t=received,
               latency_s=received-before)
    native = getattr(client, 'native_counter_record', None)
    if native is not None:
        if any(not key.startswith('native_') for key in native):
            raise ValueError('Native metadata must not override host capture fields')
        row.update(native)
    row['formatting_s'] = clock()-received
    return row
