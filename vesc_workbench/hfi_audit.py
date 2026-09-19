"""Offline sensitivity checks. No transport or calibration writer."""
import math
import statistics

from .hfi_capture import analyze_dft
from .locked_rotor import axial_delta


def firmware_atan2(y, x):
    """Double-precision transcription of pinned 6.02 utils_fast_atan2."""
    ay = abs(y) + 1e-20
    if x >= 0:
        r, base = (x-ay)/(x+ay), math.pi/4
    else:
        r, base = (x+ay)/(ay-x), 3*math.pi/4
    angle = (.1963*r*r-.9817)*r+base
    return -angle if y < 0 else angle


def synthetic_axis(axis, approximate=False):
    # HFI vector is (sin(phi), -cos(phi)); incremental inverse L is a tensor.
    values = [1/(50000+17000*math.cos(2*(2*math.pi*k/32-math.pi/2-
                                       math.radians(axis)))) for k in range(32)]
    real = sum(v*math.cos(4*math.pi*k/32) for k, v in enumerate(values))/32
    imag = -sum(v*math.sin(4*math.pi*k/32) for k, v in enumerate(values))/32
    atan = firmware_atan2 if approximate else math.atan2
    return math.degrees(-atan(imag, real)/2) % 180


def audit_run(report, points):
    if report.get('plot_mode') != 1 or not report.get('excitation_sent'):
        raise ValueError('Expected a physical mode-1 capture')
    if not all(report.get(k) for k in ('baseline_restored', 'zero_current_verified',
                                      'app_unchanged', 'no_faults')) or report.get('errors'):
        raise ValueError('Capture/recovery failed; not a quality-only rejection')
    start, end = report['dispatch_t'], report['measurement_response']['t']
    if not math.isfinite(start) or not math.isfinite(end) or end <= start:
        raise ValueError('Invalid acquisition window')
    selected = [p for p in points if start <= p['t'] <= end]
    assumptions = report['analysis']['assumptions']
    result = analyze_dft(selected, assumptions['raw_encoder_deg'],
                         assumptions['encoder_ratio'], assumptions['encoder_inverted'], 0)
    if result['status'] != report['analysis']['status']:
        raise ValueError('Replayed analysis status differs from saved result')
    frames = result['frames']
    variants = []
    if frames:
        for discard in (.05, .10, .15):
            window = [f for f in frames if f['t'] >= frames[0]['t']+discard]
            if len(window) < 30:
                continue
            for weighted in (True, False):
                weights = [f['amplitude_uh'] if weighted else 1 for f in window]
                x = sum(w*math.cos(2*math.radians(f['angle_deg'])) for w, f in zip(weights, window))
                y = sum(w*math.sin(2*math.radians(f['angle_deg'])) for w, f in zip(weights, window))
                axis = math.degrees(math.atan2(y, x))/2 % 180
                variants.append(dict(discard_s=discard, weighted=weighted, frames=len(window),
                                     axis_deg=axis, concentration=math.hypot(x, y)/sum(weights),
                                     difference_from_production_deg=axial_delta(
                                         axis, result['minimum_inductance_axis_deg'])))
    candidate = result.get('candidate')
    return dict(duty=report['duty'], raw_encoder_deg=assumptions['raw_encoder_deg'],
                production_status=result['status'], qualified=bool(candidate),
                production_axis_deg=result.get('minimum_inductance_axis_deg'),
                production_concentration=result.get('concentration'),
                diagnostic_variants=variants,
                max_sensitivity_deg=max((abs(v['difference_from_production_deg']) for v in variants), default=None),
                mean_plot_inductance_uh=statistics.mean(f['average_uh'] for f in frames) if frames else None,
                calibration_validated=False, offset_applied=False,
                warning='Alternative windows are diagnostics, not permission to accept a rejected capture')
