"""Explicit ADC-only evidence transfer after a controller restart."""
import hashlib
import math

from .synrm_pilot import fresh_adc_changes


def adc_transition(reference, actual):
    changes = fresh_adc_changes(reference, actual)
    for key, (before, after) in changes.items():
        if not all(math.isfinite(v) for v in (before, after)):
            raise ValueError('Nonfinite ADC calibration')
        if 'current' in key:
            if not 2000 <= after <= 2100 or abs(after-before) > 2:
                raise ValueError('Current ADC change exceeds restart review envelope')
        elif abs(after) > .05 or abs(after-before) > .01:
            raise ValueError('Voltage ADC change exceeds restart review envelope')
    return dict(method='bounded_adc_only_restart_v1',
                reference_sha256=hashlib.sha256(reference).hexdigest(),
                actual_sha256=hashlib.sha256(actual).hexdigest(), changes=changes,
                limitation='Transfers unchanged motor/encoder settings, not a new offset calibration')


def transfer_pose(pose, reference, actual):
    transition = adc_transition(reference, actual)
    if pose['baseline_sha256'] != transition['reference_sha256']:
        raise ValueError('HFI source does not match the reference baseline')
    return dict(pose, baseline_sha256=transition['actual_sha256'], baseline_transition=transition)


def transfer_counter_evidence(folder, actual):
    from pathlib import Path
    from .counter_angle import audit_counter_reference
    reference = (Path(folder)/'mcconf-before.bin').read_bytes()
    transition = adc_transition(reference, actual)
    evidence = audit_counter_reference(folder, reference)
    return dict(evidence, baseline_sha256=transition['actual_sha256'], baseline_transition=transition)
