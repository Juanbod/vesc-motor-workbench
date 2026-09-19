"""Offline design of a zero-flux current pilot; never opens a controller."""
import hashlib
import math

from .bench import validate_motor_math
from .wire_config import decode_config, patch_config


SOURCE_COMMIT = 'f7c2b34e1cff2234cae98be3abf0cd50e249558f'
SPEED_STAGES = ('speed_90rpm_3a', 'speed_180rpm_3a', 'speed_360rpm_3a', 'speed_540rpm_3a',
                'speed_540rpm_5a', 'speed_540rpm_5a_smooth', 'speed_600rpm_5a_smooth',
                'speed_660rpm_5a_smooth', 'speed_700rpm_5a_smooth', 'speed_700rpm_5a_upper',
                'speed_1200rpm_5a_smooth', 'speed_1700rpm_5a_smooth', 'speed_2200rpm_5a_smooth',
                'speed_2200rpm_5a_hold', 'speed_2700rpm_5a_hold',
                'speed_2200rpm_5a_counter', 'speed_2700rpm_5a_counter', 'speed_2700rpm_6a_counter',
                'speed_90rpm_2a_return_probe', 'speed_90rpm_2a_return_margin',
                'speed_2700rpm_6a_counter_return', 'speed_2700rpm_6a_counter_return_coast',
                'speed_3200rpm_7a_counter_return_coast', 'speed_3700rpm_7a_counter_return_coast',
                'speed_4200rpm_7a_counter_return_coast', 'speed_4700rpm_7a_counter_return_coast',
                'speed_4700rpm_7a_coast_reacquire', 'speed_5200rpm_7a_coast_reacquire',
                'speed_5200rpm_7a_hold60', 'speed_5700rpm_8a_hold60', 'speed_6200rpm_8a_hold60',
                'speed_6700rpm_8a_hold60', 'speed_6200rpm_8a_native60', 'speed_6700rpm_8a_native60',
                'speed_7200rpm_8a_native60', 'speed_7200rpm_9a_native60', 'speed_7700rpm_9a_native60',
                'speed_8200rpm_9a_native60', 'speed_8200rpm_10a_native60',
                'speed_8700rpm_10a_native60', 'speed_9200rpm_10a_native60',
                'speed_8700rpm_10a_rpm95', 'speed_8200rpm_10a_dq', 'speed_8700rpm_10a_dq',
                'speed_8700rpm_10a_dq_return075', 'speed_9200rpm_10a_dq_return075',
                'speed_9200rpm_10p5a_dq_return075', 'speed_540rpm_5a_restart',
                'speed_540rpm_5a_restart_return075')
ROTATION_STAGES = ('rotation_3a', 'repeatability_3a') + SPEED_STAGES


def stage_limits(stage='pilot'):
    if stage == 'speed_540rpm_5a_restart_return075':
        limits = stage_limits('speed_540rpm_5a_restart')
        limits.update(return_current_a=.075, minimum_voltage=21, maximum_voltage=24.9)
        return limits
    if stage == 'speed_540rpm_5a_restart':
        return stage_limits('speed_540rpm_5a_smooth')
    if stage == 'speed_9200rpm_10p5a_dq_return075':
        limits = stage_limits('speed_9200rpm_10a_dq_return075')
        limits.update(current=10.5, observed_current=12.6, trip=14, i2t=6615, energy=661.5)
        return limits
    if stage == 'speed_9200rpm_10a_dq_return075':
        limits = stage_limits('speed_9200rpm_10a_native60')
        limits.update(native_dq=True, return_current_a=.075)
        return limits
    if stage == 'speed_8700rpm_10a_dq_return075':
        limits = stage_limits('speed_8700rpm_10a_dq')
        limits['return_current_a'] = .075
        return limits
    if stage in ('speed_8200rpm_10a_dq', 'speed_8700rpm_10a_dq'):
        limits = stage_limits(stage.replace('_dq', '_native60'))
        limits['native_dq'] = True
        return limits
    if stage == 'speed_8700rpm_10a_rpm95':
        limits = stage_limits('speed_8700rpm_10a_native60')
        limits['erpm_start'] = .95
        return limits
    if stage == 'speed_9200rpm_10a_native60':
        limits = stage_limits('speed_8700rpm_10a_native60')
        limits.update(taper_start_rpm=8800, cutoff_rpm=9200, maximum_rpm=10120,
                      minimum_finish_rpm=8750, travel=3643200, full_travel=9472320)
        return limits
    if stage == 'speed_8700rpm_10a_native60':
        limits = stage_limits('speed_8200rpm_10a_native60')
        limits.update(taper_start_rpm=8300, cutoff_rpm=8700, maximum_rpm=9570,
                      minimum_finish_rpm=8250, travel=3445200, full_travel=8957520)
        return limits
    if stage == 'speed_8200rpm_10a_native60':
        limits = stage_limits('speed_8200rpm_9a_native60')
        limits.update(current=10, observed_current=12, trip=13, i2t=6000, energy=600)
        return limits
    if stage == 'speed_8200rpm_9a_native60':
        limits = stage_limits('speed_7700rpm_9a_native60')
        limits.update(taper_start_rpm=7800, cutoff_rpm=8200, maximum_rpm=9020,
                      minimum_finish_rpm=7750, travel=3247200, full_travel=8442720)
        return limits
    if stage == 'speed_7700rpm_9a_native60':
        limits = stage_limits('speed_7200rpm_9a_native60')
        limits.update(taper_start_rpm=7300, cutoff_rpm=7700, maximum_rpm=8470,
                      minimum_finish_rpm=7250, travel=3049200, full_travel=7927920)
        return limits
    if stage == 'speed_7200rpm_9a_native60':
        limits = stage_limits('speed_7200rpm_8a_native60')
        limits.update(current=9, observed_current=10.8, trip=12, i2t=4860, energy=486)
        return limits
    if stage == 'speed_7200rpm_8a_native60':
        limits = stage_limits('speed_6700rpm_8a_native60')
        limits.update(taper_start_rpm=6800, cutoff_rpm=7200, maximum_rpm=7920,
                      minimum_finish_rpm=6750, travel=2851200, full_travel=7413120)
        return limits
    if stage == 'speed_6700rpm_8a_native60':
        limits = stage_limits('speed_6200rpm_8a_native60')
        limits.update(taper_start_rpm=6300, cutoff_rpm=6700, maximum_rpm=7370,
                      minimum_finish_rpm=6250, travel=2653200, full_travel=6898320)
        return limits
    if stage == 'speed_6200rpm_8a_native60':
        limits = stage_limits('speed_6200rpm_8a_hold60')
        limits.update(native_counter=True, queued_logging=False, memory_logging=True,
                      defer_coast_capture=False, sample_interval_s=0, coast_sample_interval_s=0)
        return limits
    if stage == 'speed_6700rpm_8a_hold60':
        limits = stage_limits('speed_6200rpm_8a_hold60')
        limits.update(taper_start_rpm=6300, cutoff_rpm=6700, maximum_rpm=7370,
                      minimum_finish_rpm=6250, travel=2653200, full_travel=6898320,
                      queued_logging=False, memory_logging=True)
        return limits
    if stage == 'speed_6200rpm_8a_hold60':
        limits = stage_limits('speed_5700rpm_8a_hold60')
        limits.update(taper_start_rpm=5800, cutoff_rpm=6200, maximum_rpm=6820,
                      minimum_finish_rpm=5750, travel=2455200, full_travel=6383520)
        return limits
    if stage == 'speed_5700rpm_8a_hold60':
        limits = stage_limits('speed_5200rpm_7a_hold60')
        limits.update(current=8, observed_current=9.6, trip=11, i2t=3840, energy=384,
                      taper_start_rpm=5300, cutoff_rpm=5700, maximum_rpm=6270,
                      minimum_finish_rpm=5250, travel=2257200, full_travel=5868720)
        return limits
    if stage == 'speed_5200rpm_7a_hold60':
        limits = stage_limits('speed_5200rpm_7a_coast_reacquire')
        limits.update(powered_s=60, minimum_observation_s=59.5, i2t=2940, energy=294,
                      travel=2059200, full_travel=5353920)
        return limits
    if stage == 'speed_5200rpm_7a_coast_reacquire':
        limits = stage_limits('speed_4700rpm_7a_coast_reacquire')
        limits.update(taper_start_rpm=4800, cutoff_rpm=5200, maximum_rpm=5720,
                      minimum_finish_rpm=4750, travel=1372800, full_travel=4667520)
        return limits
    if stage == 'speed_4700rpm_7a_coast_reacquire':
        limits = stage_limits('speed_4700rpm_7a_counter_return_coast')
        limits['defer_coast_capture'] = True
        return limits
    if stage == 'speed_4700rpm_7a_counter_return_coast':
        limits = stage_limits('speed_4200rpm_7a_counter_return_coast')
        limits.update(taper_start_rpm=4300, cutoff_rpm=4700, maximum_rpm=5170,
                      minimum_finish_rpm=4250, travel=1240800, full_travel=4218720)
        return limits
    if stage == 'speed_4200rpm_7a_counter_return_coast':
        limits = stage_limits('speed_3700rpm_7a_counter_return_coast')
        limits.update(taper_start_rpm=3800, cutoff_rpm=4200, maximum_rpm=4620,
                      minimum_finish_rpm=3750, travel=1108800, full_travel=3769920)
        return limits
    if stage == 'speed_3700rpm_7a_counter_return_coast':
        limits = stage_limits('speed_3200rpm_7a_counter_return_coast')
        limits.update(taper_start_rpm=3300, cutoff_rpm=3700, maximum_rpm=4070,
                      minimum_finish_rpm=3250, travel=976800, full_travel=3321120)
        return limits
    if stage == 'speed_3200rpm_7a_counter_return_coast':
        limits = stage_limits('speed_2700rpm_6a_counter_return_coast')
        limits.update(current=7, observed_current=8.4, trip=10, i2t=1960, energy=196,
                      taper_start_rpm=2800, cutoff_rpm=3200, maximum_rpm=3520,
                      minimum_finish_rpm=2750, travel=844800, full_travel=2872320)
        return limits
    if stage == 'speed_2700rpm_6a_counter_return_coast':
        limits = stage_limits('speed_2700rpm_6a_counter_return')
        limits.update(coast_telemetry_gap_s=.1, coast_counter_window_s=.5, queued_logging=True)
        return limits
    if stage == 'speed_2700rpm_6a_counter_return':
        limits = stage_limits('speed_2700rpm_6a_counter')
        limits.update(return_current_a=.05, minimum_voltage=21, maximum_voltage=24.9)
        return limits
    if stage == 'speed_90rpm_2a_return_margin':
        limits = stage_limits('speed_90rpm_2a_return_probe')
        limits['trip'] = 4
        return limits
    if stage == 'speed_90rpm_2a_return_probe':
        return dict(current=2, observed_current=2.5, input_current=1,
                    observed_input=1.2, trip=3, travel=2880, full_travel=8640,
                    i2t=16, energy=8, finish_travel=10, minimum_observation_s=3.5,
                    powered_s=4, maximum_rpm=120, taper_start_rpm=75, cutoff_rpm=90,
                    minimum_finish_rpm=5, telemetry_gap_s=.05, recovery_s=16,
                    sample_interval_s=.01, coast_sample_interval_s=.01,
                    return_current_a=.05, minimum_voltage=21, maximum_voltage=24.9)
    if stage == 'speed_2700rpm_6a_counter':
        limits = stage_limits('speed_2700rpm_5a_counter')
        limits.update(current=6, observed_current=7.2, i2t=1440, energy=144,
                      minimum_finish_rpm=2250)
        return limits
    if stage in ('speed_2200rpm_5a_counter', 'speed_2700rpm_5a_counter'):
        limits = stage_limits(stage.replace('_counter', '_hold'))
        limits.update(counter_assisted=True, telemetry_gap_s=.025,
                      sample_interval_s=.002, coast_sample_interval_s=.002)
        return limits
    if stage == 'pilot':
        return dict(current=2, observed_current=2.5, input_current=1,
                    observed_input=1.2, trip=3, travel=10, i2t=16, energy=8,
                    finish_travel=3, minimum_observation_s=0)
    if stage == 'extension_3a':
        return dict(current=3, observed_current=3.6, input_current=2,
                    observed_input=2.2, trip=5, travel=90, i2t=36, energy=12,
                    finish_travel=60, minimum_observation_s=2)
    if stage == 'speed_90rpm_3a':
        return dict(current=3, observed_current=3.6, input_current=2,
                    observed_input=2.2, trip=5, travel=4320, full_travel=10080,
                    i2t=54, energy=18, finish_travel=720, minimum_observation_s=5.5,
                    powered_s=6, maximum_rpm=120, taper_start_rpm=75, cutoff_rpm=90,
                    minimum_finish_rpm=60)
    if stage == 'speed_180rpm_3a':
        return dict(current=3, observed_current=3.6, input_current=2,
                    observed_input=2.2, trip=5, travel=11520, full_travel=34560,
                    i2t=72, energy=24, finish_travel=1440, minimum_observation_s=7.5,
                    powered_s=8, maximum_rpm=240, taper_start_rpm=165, cutoff_rpm=180,
                    minimum_finish_rpm=120, telemetry_gap_s=.05, recovery_s=16)
    if stage == 'speed_360rpm_3a':
        return dict(current=3, observed_current=3.6, input_current=2,
                    observed_input=2.2, trip=5, travel=34560, full_travel=103680,
                    i2t=108, energy=36, finish_travel=3600, minimum_observation_s=11.5,
                    powered_s=12, maximum_rpm=480, taper_start_rpm=345, cutoff_rpm=360,
                    minimum_finish_rpm=240, telemetry_gap_s=.04, recovery_s=24)
    if stage == 'speed_540rpm_3a':
        return dict(current=3, observed_current=3.6, input_current=2,
                    observed_input=2.2, trip=5, travel=103680, full_travel=241920,
                    i2t=216, energy=72, finish_travel=7200, minimum_observation_s=23.5,
                    powered_s=24, maximum_rpm=720, taper_start_rpm=525, cutoff_rpm=540,
                    minimum_finish_rpm=420, telemetry_gap_s=.02, recovery_s=32,
                    sample_interval_s=.005)
    if stage == 'speed_540rpm_5a':
        limits = stage_limits('speed_540rpm_3a')
        limits.update(current=5, observed_current=6, trip=8, i2t=600)
        return limits
    if stage == 'speed_540rpm_5a_smooth':
        limits = stage_limits('speed_540rpm_5a')
        limits.update(taper_start_rpm=400, latch_speed_cutoff=True,
                      stability_window_s=5, stability_span_rpm=20, stability_slope_rpm_s=2)
        return limits
    if stage == 'speed_600rpm_5a_smooth':
        limits = stage_limits('speed_540rpm_5a_smooth')
        limits.update(taper_start_rpm=450, cutoff_rpm=600, minimum_finish_rpm=480)
        return limits
    if stage == 'speed_660rpm_5a_smooth':
        limits = stage_limits('speed_600rpm_5a_smooth')
        limits.update(taper_start_rpm=500, cutoff_rpm=660, minimum_finish_rpm=530)
        return limits
    if stage == 'speed_700rpm_5a_smooth':
        limits = stage_limits('speed_660rpm_5a_smooth')
        limits.update(taper_start_rpm=520, cutoff_rpm=700, minimum_finish_rpm=560)
        return limits
    if stage == 'speed_700rpm_5a_upper':
        limits = stage_limits('speed_700rpm_5a_smooth')
        limits.update(taper_start_rpm=600, minimum_finish_rpm=600)
        return limits
    if stage == 'speed_1200rpm_5a_smooth':
        limits = stage_limits('speed_700rpm_5a_upper')
        # Including RPC timestamp uncertainty: 1320*6*(.01+.01) < 180 deg.
        limits.update(taper_start_rpm=1000, cutoff_rpm=1200, maximum_rpm=1320,
                      minimum_finish_rpm=1000, telemetry_gap_s=.01,
                      sample_interval_s=.002, recovery_s=48,
                      travel=190080, full_travel=570240)
        return limits
    if stage == 'speed_1700rpm_5a_smooth':
        limits = stage_limits('speed_1200rpm_5a_smooth')
        limits.update(taper_start_rpm=1400, cutoff_rpm=1700, maximum_rpm=1870,
                      minimum_finish_rpm=1400, telemetry_gap_s=.007,
                      sample_interval_s=.001, recovery_s=64,
                      travel=269280, full_travel=987360)
        return limits
    if stage == 'speed_2200rpm_5a_smooth':
        limits = stage_limits('speed_1700rpm_5a_smooth')
        limits.update(taper_start_rpm=1800, cutoff_rpm=2200, maximum_rpm=2420,
                      minimum_finish_rpm=1750, telemetry_gap_s=.006,
                      sample_interval_s=0, recovery_s=80,
                      travel=348480, full_travel=1510080)
        return limits
    if stage == 'speed_2200rpm_5a_hold':
        limits = stage_limits('speed_2200rpm_5a_smooth')
        limits.update(powered_s=40, minimum_observation_s=39.5, i2t=1000, energy=96,
                      coast_sample_interval_s=.002, travel=580800, full_travel=1742400)
        return limits
    if stage == 'speed_2700rpm_5a_hold':
        limits = stage_limits('speed_2200rpm_5a_hold')
        limits.update(taper_start_rpm=2300, cutoff_rpm=2700, maximum_rpm=2970,
                      minimum_finish_rpm=1900, telemetry_gap_s=.005,
                      coast_sample_interval_s=.001, recovery_s=96,
                      travel=712800, full_travel=2423520)
        return limits
    if stage in ROTATION_STAGES:
        return dict(current=3, observed_current=3.6, input_current=2,
                    observed_input=2.2, trip=5, travel=1440, full_travel=4320,
                    i2t=36, energy=12, finish_travel=360, minimum_observation_s=3.5)
    raise ValueError('Unreviewed current stage; automatic escalation is prohibited')


def timing_stage(stage, *, coast=False):
    if stage == 'speed_9200rpm_10p5a_dq_return075':
        return 'speed_9200rpm_10a_dq_return075'
    if stage == 'speed_9200rpm_10a_dq_return075':
        return 'speed_8700rpm_10a_dq_return075'
    if stage == 'speed_8700rpm_10a_dq_return075':
        return 'speed_8200rpm_10a_dq'
    if stage == 'speed_8700rpm_10a_dq':
        return 'speed_8200rpm_10a_dq'
    if stage == 'speed_8700rpm_10a_rpm95':
        return 'speed_8700rpm_10a_native60'
    if stage == 'speed_9200rpm_10a_native60':
        return 'speed_8700rpm_10a_native60'
    if stage == 'speed_8700rpm_10a_native60':
        return 'speed_8200rpm_10a_native60'
    if stage == 'speed_8200rpm_10a_native60':
        return 'speed_8200rpm_9a_native60'
    if stage == 'speed_8200rpm_9a_native60':
        return 'speed_7700rpm_9a_native60'
    if stage == 'speed_7700rpm_9a_native60':
        return 'speed_7200rpm_9a_native60'
    if stage in ('speed_7200rpm_8a_native60', 'speed_7200rpm_9a_native60'):
        # Identical read-only workload; replay still uses the new speed envelope.
        return 'speed_6700rpm_8a_native60'
    # Zero-current workload, cadence, angle envelope and receive options match.
    if stage == 'speed_4700rpm_7a_coast_reacquire':
        # The timing probe remains strict: it never defers any capture.
        return 'speed_4700rpm_7a_counter_return_coast'
    if stage == 'speed_5200rpm_7a_hold60':
        return 'speed_5200rpm_7a_coast_reacquire'
    if stage == 'speed_6200rpm_8a_hold60':
        # Same zero-current workload. Raw captures must pass the NEW RPM envelope.
        return 'speed_5700rpm_8a_hold60'
    return 'speed_2700rpm_5a_counter' if stage == 'speed_2700rpm_6a_counter' else stage


def counter_timing(limits, *, coast=False):
    if coast:
        return (limits.get('coast_telemetry_gap_s', limits.get('telemetry_gap_s', .1)),
                limits.get('coast_counter_window_s', .25))
    return limits.get('telemetry_gap_s', .1), .25


def rotation_current(previous_a, encoder_rpm, dt_s, elapsed_s, stage='rotation_3a'):
    """Positive-current taper, not a speed PID or an active brake."""
    if stage not in ROTATION_STAGES:
        raise ValueError('Unreviewed rotation supervisor stage')
    limits = stage_limits(stage)
    maximum = limits['current']
    slew = 3
    cutoff = limits.get('cutoff_rpm', 35)
    taper_start = limits.get('taper_start_rpm', 20)
    if math.isfinite(dt_s) and dt_s > limits.get('telemetry_gap_s', .1):
        raise ValueError(f'Command interval {dt_s:.6f} s exceeds {limits.get("telemetry_gap_s", .1):.6f} s')
    if (not all(math.isfinite(v) for v in (previous_a, encoder_rpm, dt_s, elapsed_s))
            or not 0 <= previous_a <= maximum or not 0 <= dt_s <= limits.get('telemetry_gap_s', .1)
            or not 0 <= elapsed_s < limits.get('powered_s', 4)
            or not -5 <= encoder_rpm < limits.get('maximum_rpm', 60)):
        raise ValueError('Invalid rotation supervisor input')
    if encoder_rpm >= cutoff:
        return 0.0
    target = min(maximum, max(0, maximum*(cutoff-encoder_rpm)/(cutoff-taper_start)))
    # Up/down slew is 3 A/s; the stage's zero-current cutoff has priority.
    return min(maximum, slew*elapsed_s, max(previous_a-slew*dt_s, min(target, previous_a+slew*dt_s)))


def adjacent_speed_evidence(delta_deg, gap_s, previous_latency_s, latency_s):
    """Diagnostic interval bounds, assuming acquisition occurs during each RPC.

    These do not replace the existing guard or prove instantaneous shaft speed.
    """
    if (not all(math.isfinite(v) for v in (delta_deg, gap_s, previous_latency_s, latency_s))
            or gap_s <= 0 or min(previous_latency_s, latency_s) < 0):
        raise ValueError('Invalid speed timing evidence')
    shortest = gap_s-latency_s
    longest = gap_s+previous_latency_s
    return dict(apparent_rpm=delta_deg/gap_s/6, response_gap_s=gap_s,
                previous_latency_s=previous_latency_s, latency_s=latency_s,
                minimum_abs_average_rpm=abs(delta_deg)/longest/6,
                maximum_abs_average_rpm=abs(delta_deg)/shortest/6 if shortest > 0 else None)


def speed_stability(tail, stage):
    limits = stage_limits(stage)
    if not tail or 'stability_window_s' not in limits:
        raise ValueError('Missing stability evidence or unreviewed stage')
    if any(not math.isfinite(t) or not math.isfinite(r) for t, r in tail):
        raise ValueError('Nonfinite stability evidence')
    if any(b[0] <= a[0] for a, b in zip(tail, tail[1:])):
        raise ValueError('Nonmonotonic stability evidence')
    duration = tail[-1][0]-tail[0][0]
    values = [r for _, r in tail]
    span = max(values)-min(values)
    slope = (values[-1]-values[0])/duration if duration > 0 else None
    gaps_ok = all(b[0]-a[0] <= limits['telemetry_gap_s'] for a, b in zip(tail, tail[1:]))
    return dict(duration_s=duration, minimum_rpm=min(values), maximum_rpm=max(values),
                mean_rpm=sum(values)/len(values), span_rpm=span, endpoint_slope_rpm_s=slope,
                verified=bool(duration >= limits['stability_window_s']-limits['telemetry_gap_s']
                              and gaps_ok and min(values) >= limits['minimum_finish_rpm']
                              and span <= limits['stability_span_rpm']
                              and slope is not None and abs(slope) <= limits['stability_slope_rpm_s']))


def fresh_adc_changes(previous, actual):
    old, new = decode_config(previous, 'motor'), decode_config(actual, 'motor')
    changes = {k: [old[k], v] for k, v in new.items() if old[k] != v}
    allowed = {f'foc_offsets_{kind}[{i}]' for kind in ('current', 'voltage') for i in range(3)}
    if set(changes)-allowed:
        raise ValueError('Non-ADC baseline change requires review')
    # Verify byte-level preservation too, including bytes outside decoded fields.
    if patch_config(previous, 'motor', {k: pair[1] for k, pair in changes.items()}) != actual:
        raise ValueError('Baseline has unexplained byte changes')
    return changes


def encoder_policy(config, stage='pilot'):
    """Configuration proof for the reference firmware, NOT a live source flag."""
    v = decode_config(config, 'motor')
    max_erpm = 2*stage_limits(stage).get('maximum_rpm', 60)
    expected = dict(motor_type=2, foc_sensor_mode=1, m_sensor_port_mode=2,
                    foc_encoder_ratio=2, foc_encoder_inverted=0, p_pid_ang_div=1,
                    foc_f_zv=30000, foc_sample_v0_v7=0, foc_speed_soure=0,
                    foc_sl_erpm=500000, l_max_erpm=max_erpm, l_min_erpm=-max_erpm)
    if any(v[k] != value for k, value in expected.items()):
        raise ValueError('Encoder enforcement configuration differs from reviewed settings')
    # abs(delta_phase) <= pi/3, dt >= 1/f_zv (positive integer loop divider).
    # LP_FAST(..., 0.01) is a convex update, starting from zero at initialization.
    bound = 10*v['foc_f_zv']
    if .95*v['foc_sl_erpm'] <= bound:
        raise ValueError('Encoder re-entry threshold must exceed the fast-estimator bound')
    return dict(source='encoder', age_s=0, method='reference_firmware_configuration_bound',
                direct_source_flag_available=False, source_commit=SOURCE_COMMIT,
                fast_estimator_bound_erpm=bound, enter_encoder_below_erpm=475000,
                leave_encoder_above_erpm=525000,
                config_sha256=hashlib.sha256(config).hexdigest(),
                limitation='Requires matching reference logic, positive loop divider, functioning encoder and no concurrent configuration writer')


def mtpa_targets(command_a, flux_wb, lq_minus_ld_h):
    """Pinned 6.02 requested-current MTPA math, before limiting/field weakening."""
    if any(not math.isfinite(v) for v in (command_a, flux_wb, lq_minus_ld_h)):
        raise ValueError('Nonfinite MTPA input')
    if lq_minus_ld_h <= 0 or flux_wb < 0:
        raise ValueError('Pilot requires positive Lq-Ld and nonnegative flux')
    if command_a == 0:
        return dict(id_a=0.0, iq_a=0.0)
    # Rationalized form avoids cancellation at small positive command/flux.
    d, current = lq_minus_ld_h, abs(command_a)
    root = math.sqrt(flux_wb*flux_wb+8*(d*current)**2)
    id_a = -2*d*current*current/(root+flux_wb)
    radicand = current*current-id_a*id_a
    if radicand < 0:
        raise ValueError('Undefined MTPA current target')
    return dict(id_a=id_a, iq_a=math.copysign(math.sqrt(radicand), command_a))


def validate_observation(sample, command_a, source_status, settled_current=False, stage='pilot'):
    """Require a source flag or reviewed configuration proof, never PLL ERPM."""
    if not isinstance(source_status, dict) or source_status.get('source') != 'encoder':
        raise ValueError('Explicit encoder-source telemetry required; do not infer it from ERPM')
    age = source_status.get('age_s')
    if not isinstance(age, (float, int)) or not math.isfinite(age) or not 0 <= age <= .1:
        raise ValueError('Stale or invalid source telemetry')
    required = ('id_a', 'iq_a', 'current_motor_a', 'current_in_a', 'v_in', 'duty',
                'encoder_rpm', 'encoder_age_s', 'travel_deg', 'temp_mos_c',
                'fault_code', 'elapsed_s', 'i2t_a2s', 'input_energy_j', 'latency_s')
    if any(k not in sample or not isinstance(sample[k], (int, float))
           or not math.isfinite(sample[k]) for k in required):
        raise ValueError('Missing/nonfinite pilot telemetry')
    limits = stage_limits(stage)
    if limits.get('native_dq'):
        from .native_counter_snapshot import validate_dq_record
        validate_dq_record(sample)
    if not math.isfinite(command_a) or not 0 <= command_a <= limits['current']:
        raise ValueError('Pilot command outside reviewed range')
    if (sample['fault_code'] != 0 or not limits.get('minimum_voltage', 18) <= sample['v_in'] <= limits.get('maximum_voltage', 30)
            or sample['temp_mos_c'] > 50):
        raise ValueError('Controller fault, voltage or MOS temperature limit')
    if (abs(sample['current_motor_a']) > limits['observed_current']
            or math.hypot(sample['id_a'], sample['iq_a']) > limits['observed_current']
            or not -.1 <= sample['current_in_a'] <= limits['observed_input'] or abs(sample['duty']) > .1):
        raise ValueError('Current or duty outside pilot bounds')
    gap = limits.get('telemetry_gap_s', .1)
    if (not 0 <= sample['encoder_age_s'] <= gap or not 0 <= sample['latency_s'] <= gap
            or not -1 <= sample['travel_deg'] < limits['travel']
            or not -5 <= sample['encoder_rpm'] < limits.get('maximum_rpm', 60)):
        raise ValueError('Stale encoder, unexpected direction, travel or speed limit')
    if (not 0 <= sample['elapsed_s'] < limits.get('powered_s', 4) or not 0 <= sample['i2t_a2s'] < limits['i2t']
            or not 0 <= sample['input_energy_j'] < limits['energy']):
        raise ValueError('Powered duration or energy budget exhausted')
    if settled_current:
        target = mtpa_targets(command_a, 0, 1)
        tolerance = max(.2, command_a*.25)
        if any(abs(sample[k]-target[k]) > tolerance for k in ('id_a', 'iq_a')):
            raise ValueError('Measured Id/Iq do not track the zero-flux targets')


def build_pilot(baseline, offset_deg, raw_pose_deg, stage='pilot'):
    limits = stage_limits(stage)
    values = decode_config(baseline, 'motor')
    if (values['motor_type'] != 2 or values['foc_sensor_mode'] != 1
            or values['m_sensor_port_mode'] != 2 or values['p_pid_ang_div'] != 1
            or values['foc_encoder_ratio'] != 2 or values['foc_encoder_inverted'] != 0):
        raise ValueError('Expected reviewed FOC/AS504x ratio-2 non-inverted baseline')
    if not all(math.isfinite(v) and 0 <= v < 360 for v in (offset_deg, raw_pose_deg)):
        raise ValueError('Invalid candidate offset or raw pose')
    l, diff = values['foc_motor_l'], values['foc_motor_ld_lq_diff']
    if not 0 < diff < 2*l or values['foc_motor_r'] <= 0:
        raise ValueError('Invalid positive-definite motor inductance model')
    if not .015 <= values['foc_current_kp'] <= .03 or not 10 <= values['foc_current_ki'] <= 16:
        raise ValueError('Current gains outside reviewed baseline')
    if not 0 < values['cc_min_current'] < .5:
        raise ValueError('Minimum current would interfere with pilot ramp')
    if values['foc_sl_erpm'] != 4000:
        raise ValueError('Unexpected transition threshold; review separately')
    changes = dict(foc_motor_flux_linkage=0, foc_mtpa_mode=1,
                   foc_sat_comp_mode=0, foc_observer_type=0, foc_cc_decoupling=0,
                   foc_speed_soure=0, foc_fw_current_max=0,
                   foc_encoder_offset=offset_deg,
                   l_current_max=limits['current'], l_current_min=-limits['current'],
                   l_current_max_scale=1, l_current_min_scale=1,
                   l_in_current_max=limits['input_current'], l_in_current_min=-limits.get('return_current_a', 0),
                   l_abs_current_max=limits['trip'], l_slow_abs_current=0,
                   l_min_erpm=-2*limits.get('maximum_rpm', 60),
                   l_max_erpm=2*limits.get('maximum_rpm', 60), l_max_duty=.1,
                   foc_f_zv=30000, foc_sample_v0_v7=0, foc_sl_erpm=500000)
    if 'erpm_start' in limits:
        changes['l_erpm_start'] = limits['erpm_start']
    if limits.get('return_current_a'):
        if values['l_max_vin'] <= limits['minimum_voltage']:
            raise ValueError('Baseline overvoltage protection is incompatible with the battery experiment')
        changes['l_max_vin'] = min(values['l_max_vin'], limits['maximum_voltage'])
    candidate = patch_config(baseline, 'motor', changes)
    actual = decode_config(candidate, 'motor')
    validate_motor_math(actual)
    if any(actual[k] != v for k, v in values.items() if k not in changes):
        raise ValueError('Unrequested baseline field changed')
    targets = [dict(command_a=i, **mtpa_targets(i, 0, diff))
               for i in (0, limits['current']/4, limits['current']/2, limits['current']*.75, limits['current'])]
    policy = encoder_policy(candidate, stage)
    plan = dict(schema='synrm-current-pilot-v2', status='requires_free_fixture_and_preflight',
                firmware=dict(major=6, minor=2, hardware='MKSESC_84_100_HP'),
                source_commit='f7c2b34e1cff2234cae98be3abf0cd50e249558f',
                baseline_sha256=hashlib.sha256(baseline).hexdigest(),
                candidate_sha256=hashlib.sha256(candidate).hexdigest(),
                changes={k: actual[k] for k in changes}, expected_targets=targets,
                source_pose_deg=raw_pose_deg, offset_calibrated=False,
                target_convention='minimum-L d-axis; requested-current MTPA',
                stage=stage,
                bounds=dict(command_a=limits['current'], ramp_s=limits['current']/3 if stage in ROTATION_STAGES else 1,
                            maximum_powered_s=limits.get('powered_s', 4),
                            maximum_mechanical_travel_deg=limits['travel'], maximum_mechanical_rpm=limits.get('maximum_rpm', 60),
                            maximum_i2t_a2s=limits['i2t'], maximum_input_energy_j=limits['energy'],
                            maximum_telemetry_gap_s=limits.get('telemetry_gap_s', .1), cooldown_s=8,
                            maximum_mos_temperature_c=50, bus_voltage_v=[limits.get('minimum_voltage', 18), limits.get('maximum_voltage', 30)]),
                required_checks=[
                    'User confirms power-off removal of the mechanical fixture',
                    'Fresh baseline, encoder diagnostics, zero current and standstill',
                    'Isolated external app with verified 300 ms zero-brake watchdog',
                    'Verified current-protective configuration readback before torque',
                    'Starting raw pose within 0.5 mechanical deg of the local measurement',
                    'Verify encoder-enforcement configuration and retain its reference-firmware assumptions',
                    'Measure both Id and Iq, physical encoder travel, voltage, current and MOS temperature',
                    'Stop on unexpected direction, stale data, fault, current mismatch or any bound',
                    'Verify zero current and standstill before exact baseline rollback'],
                observer_transition=dict(threshold_erpm=500000, source='m_speed_est_fast',
                                         encoder_only_guaranteed=False, evidence=policy),
                motor_temperature_available=False,
                limitations=['Zero-flux model is a test hypothesis, not measured motor characterization',
                             'No torque sensor; Id/Iq telemetry alone does not prove useful torque',
                             'Use only the dedicated single-trial runner, not the generic campaign',
                             'No source-selection flag in the currently used GET_VALUES telemetry'],
                live_runner_ready=True, auto_apply_allowed=False,
                hardware_commands_sent=False, full_speed_test_allowed=False)
    if limits.get('coast_telemetry_gap_s'):
        plan['bounds'].update(maximum_zero_current_coast_gap_s=limits['coast_telemetry_gap_s'],
                             zero_current_coast_counter_window_s=limits['coast_counter_window_s'])
    if limits.get('defer_coast_capture'):
        plan['bounds']['maximum_deferred_zero_current_coast_captures'] = 1
    if limits.get('return_current_a'):
        plan['bounds'].update(maximum_configured_return_current_a=limits['return_current_a'],
                              maximum_sampled_return_current_a=.1, maximum_sampled_return_energy_j=.25)
        plan['limitations'].append('Small battery-return experiment only; cell voltages, chemistry, BMS and current ratings not verified')
    if stage != 'pilot':
        plan['required_checks'][4] = 'Start within 0.5 deg of the prior independent quiet readback; offset is an uncalibrated hypothesis at this new pose'
        plan['limitations'].append('Travel envelope is monitored through coast-down, but zero current cannot guarantee a mechanical stop position')
    if stage in ROTATION_STAGES:
        plan['bounds']['maximum_full_event_travel_deg'] = limits['full_travel']
        plan['rotation_supervisor'] = dict(taper_starts_rpm=limits.get('taper_start_rpm', 20), zero_current_rpm=limits.get('cutoff_rpm', 35),
                                          slew_a_per_s=3, active_braking=False,
                                          minimum_completion_travel_deg=limits['finish_travel'])
        plan['limitations'].append('Positive-current taper does not guarantee steady speed or prevent externally driven overspeed')
    if stage in ('repeatability_3a',) + SPEED_STAGES:
        plan['required_checks'][4] = 'Fresh independent entry readback within 1 s; remain within 0.5 deg during preparation'
    if stage == 'repeatability_3a':
        plan['repeatability'] = dict(maximum_repeats=3, minimum_start_separation_deg=10,
                                     requires_successful_prior_run=True,
                                     requires_independent_quiet_readback=True)
        plan['required_checks'][4] = 'Fresh independent entry readback within 1 s; remain within 0.5 deg during preparation; at least 10 deg from earlier tested starts'
    if stage in SPEED_STAGES:
        plan['bounds']['maximum_recovery_s'] = limits.get('recovery_s', 8)
        plan['bounds']['requested_sample_pause_s'] = limits.get('sample_interval_s', .02)
        plan['bounds']['requested_coast_sample_pause_s'] = limits.get('coast_sample_interval_s', limits.get('sample_interval_s', .02))
        plan['limitations'].append('One reviewed bounded stage after a qualified predecessor; not a mechanical maximum-speed qualification')
    if limits.get('latch_speed_cutoff'):
        plan['rotation_supervisor']['cutoff_ends_trial'] = True
        plan['stability_criteria'] = dict(window_s=limits['stability_window_s'],
                                          maximum_span_rpm=limits['stability_span_rpm'],
                                          maximum_abs_endpoint_slope_rpm_s=limits['stability_slope_rpm_s'])
    return plan, candidate
