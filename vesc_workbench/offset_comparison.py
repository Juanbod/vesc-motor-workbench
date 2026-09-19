"""Offline comparison only: no transport, configuration writer or auto-apply."""
import json
import math
from pathlib import Path
import statistics

from .locked_rotor import _axial_mean, axial_delta, angular_delta


def mean_angle(values):
    if not values or any(not math.isfinite(v) for v in values):
        raise ValueError('Invalid angle values')
    x = statistics.mean(math.cos(math.radians(v)) for v in values)
    y = statistics.mean(math.sin(math.radians(v)) for v in values)
    if math.hypot(x, y) < .99:
        raise ValueError('Not a single pose')
    return math.degrees(math.atan2(y, x)) % 360


def hfi_pose(summary_path):
    # Revalidate original acquisitions rather than trusting a hand-edited mean.
    from .hfi_capture import summarize_dft_runs
    path = Path(summary_path).resolve()
    summary = json.loads(path.read_text(encoding='utf-8'))
    sources = [Path(p) for p in summary['source_reports']]
    runs = [json.loads(p.read_text(encoding='utf-8')) for p in sources]
    checked = summarize_dft_runs(runs, 0)
    if (checked['encoder_ratio'] != 2 or checked['encoder_inverted']
            or checked['d_axis'] != 'minimum_inductance' or checked['duty'] != .1):
        raise ValueError('Unexpected HFI convention/settings')
    return dict(method='HFI', source=str(path),
                encoder_deg=mean_angle(checked['raw_encoder_positions_deg']),
                offset_deg=axial_delta(checked['preferred_branch_deg'], 0),
                repeat_range_deg=checked['repeat_range_deg'],
                baseline_sha256=checked['baseline_sha256'],
                source_reports=[str(p) for p in sources])


def alignment_rows(report_path):
    path = Path(report_path).resolve()
    r = json.loads(path.read_text(encoding='utf-8'))
    if not (r.get('simulated') is False and r.get('baseline_restored')
            and r.get('zero_current_verified') and r.get('app_isolated') and r.get('no_faults')):
        raise ValueError('Alignment run has not verified recovery/no-fault state')
    p = r['plan']
    if (p['current_a'] != 2 or p['dwell_s'] != 4
            or p['source_commit'] != 'f7c2b34e1cff2234cae98be3abf0cd50e249558f'):
        raise ValueError('Unexpected alignment excitation')
    accepted, excluded = [], []
    for s in r['steps']:
        if not (s.get('settled') and s.get('completed') and abs(s.get('travel_deg', 0)) >= 1):
            excluded.append(dict(source=str(path), index=s['index'], reason='No independently observed move-and-settle'))
            continue
        # A failed overall sweep can still supply an explicitly labelled local
        # equilibrium observation; it never becomes a qualified sweep here.
        accepted.append(dict(method='stator_field', source=str(path), index=s['index'],
                             encoder_deg=s['encoder_deg'], field_deg=s['phase_deg'],
                             offset_deg=axial_delta(2*s['encoder_deg']-(s['phase_deg']+90), 0),
                             net_travel_deg=s['travel_deg'], run_ok=r['ok'],
                             run_errors=r['errors'], baseline_sha256=r['baseline_sha256']))
    return accepted, excluded


def match_pose(row, references, tolerance=.5):
    if not references:
        raise ValueError('No reference poses')
    nearest = min(references, key=lambda r: abs(angular_delta(row['encoder_deg'], r['encoder_deg'])))
    distance = abs(angular_delta(row['encoder_deg'], nearest['encoder_deg']))
    return dict(nearest_hfi_source=nearest['source'], mechanical_distance_deg=distance,
                same_pose=distance <= tolerance,
                measured_method_difference_deg=axial_delta(row['offset_deg'], nearest['offset_deg'])
                if distance <= tolerance else None)


def fit_hypothesis(rows):
    """A 90-mechanical-degree periodic model, NOT an encoder correction table."""
    import numpy as np  # Optional analysis runtime, not required by motor tools.
    if len(rows) < 4:
        raise ValueError('At least four independent positions are required')
    angles = [r['encoder_deg'] for r in rows]
    if any(abs(angular_delta(a, b)) <= .5 for i, a in enumerate(angles) for b in angles[:i]):
        raise ValueError('Repeated same-pose acquisitions cannot count as independent positions')
    center, _ = _axial_mean([r['offset_deg'] for r in rows])
    center = axial_delta(center, 0)
    y = np.array([center + axial_delta(r['offset_deg'], center) for r in rows])
    X = np.array([[1, math.cos(math.radians(4*a)), math.sin(math.radians(4*a))] for a in angles])
    if not np.isfinite(X).all() or not np.isfinite(y).all():
        raise ValueError('Nonfinite fit data')
    coefficients, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
    if rank != 3 or np.linalg.cond(X) > 100:
        raise ValueError('Insufficient independent angular coverage')
    errors = y-X@coefficients
    loo = []
    for i in range(len(rows)):
        xx, yy = np.delete(X, i, axis=0), np.delete(y, i)
        b, _, rank, _ = np.linalg.lstsq(xx, yy, rcond=None)
        if rank != 3 or np.linalg.cond(xx) > 100:
            loo.append(None)
        else:
            loo.append(float(y[i]-X[i]@b))
    return dict(model='offset = c + a*cos(4*mechanical_angle) + b*sin(4*mechanical_angle)',
                hypothesized_period_mechanical_deg=90, coefficients_deg=coefficients.tolist(),
                constant_only_rms_deg=float(np.sqrt(np.mean((y-y.mean())**2))),
                training_rms_deg=float(np.sqrt(np.mean(errors**2))),
                training_residuals_deg=errors.tolist(), leave_one_pose_out_errors_deg=loo,
                leave_one_pose_out_max_abs_deg=max((abs(e) for e in loo if e is not None), default=None),
                all_leave_one_out_fits_supported=all(e is not None for e in loo),
                geometric_periodicity_verified=False, correction_validated=False, auto_apply_allowed=False)


def predict(model, angle):
    c, a, b = model['coefficients_deg']
    return c+a*math.cos(math.radians(4*angle))+b*math.sin(math.radians(4*angle))


def compare(training, check, alignment):
    model = fit_hypothesis(training)
    rows = []
    for r in alignment:
        prediction = predict(model, r['encoder_deg'])
        rows.append(dict(r, **match_pose(r, training+check),
                         model_prediction_deg=prediction,
                         model_difference_deg=axial_delta(r['offset_deg'], prediction)))
    return dict(status='diagnostic_only_no_matched_pose_validation', delta_connection='user_confirmed',
                encoder_ratio_assumed=2, encoder_inverted_assumed=False,
                training=training, check=[dict(r, model_difference_deg=axial_delta(
                    r['offset_deg'], predict(model, r['encoder_deg']))) for r in check],
                model=model, alignment=rows, current_limits_changed=False, motor_commands_sent=False,
                offset_applied=False, calibration_validated=False,
                next_measurement='HFI at a mechanically locked pose matching a recorded field-alignment equilibrium',
                caveat='Model differences across methods are not measured same-pose errors; no automatic correction')
