"""Evidence-based qualification, separate from merely completing a trial."""
import math
import statistics


def speed_steps(samples: list[dict]) -> list[dict]:
    groups = []
    for sample in samples:
        if not groups or groups[-1][-1]['target_erpm'] != sample['target_erpm']:
            groups.append([])
        groups[-1].append(sample)
    result = []
    for group in groups:
        target = group[0]['target_erpm']
        span = group[-1]['t'] - group[0]['t']
        tail = [s for s in group if s['t'] >= group[0]['t'] + span / 2]
        errors = [s['encoder_erpm'] - target for s in tail]
        speeds = [s['encoder_erpm'] for s in tail]
        duration = tail[-1]['t'] - tail[0]['t']
        tolerance = max(10, abs(target) * .10)
        mean_t = statistics.mean(s['t'] for s in tail)
        denominator = sum((s['t'] - mean_t)**2 for s in tail)
        mean_speed = statistics.mean(speeds)
        drift = (sum((s['t'] - mean_t) * (s['encoder_erpm'] - mean_speed)
                     for s in tail) / denominator) if denominator else 0
        inside = sum(abs(e) <= tolerance for e in errors) / len(errors)
        peak = max(abs(e) for e in errors)
        passed = (duration >= 2 and inside >= .9 and peak <= 2 * tolerance
                  and abs(drift) <= max(5, abs(target) * .02))
        result.append(dict(target_erpm=target, observed_s=span, evaluation_s=duration,
                           mean_erpm=mean_speed, min_erpm=min(speeds), max_erpm=max(speeds),
                           bias_erpm=statistics.mean(errors),
                           rmse_erpm=math.sqrt(statistics.mean(e*e for e in errors)),
                           peak_error_erpm=peak, drift_erpm_s=drift,
                           fraction_in_tolerance=inside, tolerance_erpm=tolerance,
                           qualified=passed))
    return result


def startup_coverage(results: list[dict], bins: int = 12, repeats: int = 3) -> dict:
    if type(bins) is not int or bins < 1 or type(repeats) is not int or repeats < 1:
        raise ValueError('Positive integer bin and repeat counts required')
    starts = [r for r in results if r.get('stage') == 'startup']
    counts = [0] * bins
    failures = 0
    same_candidate = all(r.get('changes') == starts[0].get('changes') for r in starts)
    for row in starts:
        angle = row.get('start_angle')
        if (not row.get('ok') or row.get('startup_s') is None
                or not isinstance(angle, (int, float)) or not math.isfinite(angle)):
            failures += 1
            continue
        counts[int((angle % 360) * bins / 360)] += 1
    return dict(bins=bins, required_per_bin=repeats, successful_starts=counts,
                failures=failures, same_candidate=same_candidate,
                qualified=bool(starts) and same_candidate and not failures
                and all(n >= repeats for n in counts),
                scope='Observed no-load starts only; not a guarantee under all loads or temperatures')
