"""Bounded same-current startup series; abort rather than retry a failed trial."""
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter, sleep

from .fixture import require_free, verify_encoder_quiet
from .locked_probe import preflight_config
from .synrm_pilot_runner import repeatability_reference, run_pilot


def read_quiet_baseline(client, baseline, *, clock=perf_counter, pause=sleep):
    """Independent read-only check: no stop, configuration or excitation writes."""
    firmware = asdict(client.fw_version())
    motor, app = client.get_raw_config('motor'), client.get_raw_config('app')
    values, _ = preflight_config(firmware, motor, app)
    if motor != baseline:
        raise ValueError('Independent readback baseline mismatch')
    rows = []
    for _ in range(25):
        before = clock()
        row = dict(asdict(client.get_values()), position_deg=client.pid_position, t=clock())
        if (clock()-before > .1 or not all(math.isfinite(v) for v in row.values())
                or not 18 <= row['v_in'] <= 30 or row['temp_mos_c'] > 50):
            raise ValueError('Independent readback telemetry guard')
        rows.append(row)
        pause(.02)
    verify_encoder_quiet(rows)
    if client.get_raw_config('motor') != motor or client.get_raw_config('app') != app:
        raise ValueError('Configuration changed during independent readback')
    return dict(read_only=True, excitation_sent=False, baseline_restored=True,
                baseline_sha256=hashlib.sha256(baseline).hexdigest(),
                zero_current_verified=True, app_isolated=True,
                active_offset_deg=values['foc_encoder_offset'], samples=rows)


def trial_metrics(folder, report):
    folder = Path(folder)
    rows = [json.loads(line) for line in (folder/'observations.jsonl').read_text(encoding='utf-8').splitlines()]
    samples = [json.loads(line) for line in (folder/'samples.jsonl').read_text(encoding='utf-8').splitlines()]
    start = next(r['position_deg'] for r in samples if r['stage'] == 'before_current')
    tail = [r for r in rows if r['elapsed_s'] >= rows[-1]['elapsed_s']-1]
    moving = next((r for r in rows if r['travel_deg'] >= 3), None)
    return dict(path=str(folder.resolve()), start_deg=start, ok=report['ok'],
                status=report['status'], powered_s=report['powered_s'],
                travel_deg=report['travel_deg'], turns=report['travel_deg']/360,
                time_to_3deg_s=moving['elapsed_s'] if moving else None,
                peak_encoder_rpm=max(r['encoder_rpm'] for r in rows),
                tail_min_rpm=min(r['encoder_rpm'] for r in tail),
                tail_max_rpm=max(r['encoder_rpm'] for r in tail),
                tail_mean_rpm=sum(r['encoder_rpm'] for r in tail)/len(tail),
                peak_command_a=max(r['command_a'] for r in rows),
                final_command_a=rows[-1]['command_a'],
                peak_id_iq_norm_a=max(math.hypot(r['id_a'], r['iq_a']) for r in rows),
                i2t_a2s=report['i2t_a2s'], input_energy_j=report['input_energy_j'])


def run_repeatability(client_factory, baseline, pose, output, prior_run, *,
                      clock=perf_counter, pause=sleep, progress=lambda value: None):
    require_free()
    seed = repeatability_reference(prior_run, baseline)
    if seed['repeatability_index'] != 1:
        raise ValueError('Start this three-trial series from the initial rotation, not midway')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    summary = dict(schema='synrm-repeatability-v1', status='preparing', ok=False,
                   maximum_trials=3, current_ceiling_a=3, maximum_powered_s=12,
                   maximum_i2t_a2s=108, maximum_input_energy_j=36,
                   minimum_quiet_cooldown_s=8, trials=[], errors=[])

    def save():
        (output/'series.json').write_text(json.dumps(summary, indent=2, allow_nan=False), encoding='utf-8')

    save()
    prior = Path(prior_run)
    try:
        for index in range(1, 4):
            require_free()
            if (output/'STOP').exists():
                raise ValueError('Series STOP requested')
            reference = repeatability_reference(prior, baseline)
            if reference['repeatability_index'] != index:
                raise ValueError('Repeat index does not match series')
            folder = output/f'trial-{index:02d}'
            summary['status'] = f'trial_{index}_running'
            summary['active_trial'] = str(folder.resolve())
            save()
            with client_factory() as client:
                entry_readback = read_quiet_baseline(client, baseline, clock=clock, pause=pause)
            with (output/f'trial-{index:02d}-entry-readback.json').open('x', encoding='utf-8') as f:
                json.dump(entry_readback, f, indent=2, allow_nan=False)
            progress(dict(event='starting', trial=index,
                          start_deg=entry_readback['samples'][-1]['position_deg'],
                          previous_quiet_deg=reference['starting_pose_deg']))
            with client_factory() as client:
                report = run_pilot(client, baseline, pose, folder,
                                   clock=clock, pause=pause, stage='repeatability_3a',
                                   prior_run=prior, stop_file=output/'STOP', entry_readback=entry_readback)
            entry = dict(path=str(folder.resolve()), ok=report['ok'], status=report['status'],
                         excitation_sent=report['excitation_sent'])
            summary['trials'].append(entry)
            save()
            if report.get('zero_current_verified') and report.get('baseline_restored') and report.get('app_isolated'):
                with client_factory() as client:
                    final = read_quiet_baseline(client, (folder/'mcconf-before.bin').read_bytes(),
                                                clock=clock, pause=pause)
                with (folder/'final-readback.json').open('x', encoding='utf-8') as f:
                    json.dump(final, f, indent=2, allow_nan=False)
                entry['independent_zero_verified'] = True
                entry['final_deg'] = final['samples'][-1]['position_deg']
            else:
                raise ValueError('Trial cleanup unverified; no next trial')
            if report.get('last_powered_observation') is not None:
                entry.update(trial_metrics(folder, report))
            save()
            progress(dict(event='completed', trial=index, **entry))
            if not report['ok']:
                raise ValueError(f'Trial {index} did not qualify: {report["status"]}; {report["errors"]}')
            prior = folder
        summary.update(status='three_starts_observed', ok=True)
    except (Exception, KeyboardInterrupt) as exc:
        summary.update(status='stopped', ok=False)
        summary['errors'].append(str(exc) or type(exc).__name__)
    finally:
        summary['total_powered_s'] = sum(r.get('powered_s', 0) for r in summary['trials'])
        summary['total_i2t_a2s'] = sum(r.get('i2t_a2s', 0) for r in summary['trials'])
        summary['total_input_energy_j'] = sum(r.get('input_energy_j', 0) for r in summary['trials'])
        save()
    return summary
