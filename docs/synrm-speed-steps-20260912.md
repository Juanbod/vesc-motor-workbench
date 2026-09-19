# Bounded speed and current steps

The dedicated pilot CLI supports these explicit speed stages:

| Stage | Required predecessor | Taper / zero-current RPM | Speed guard | Powered budget | Recovery observation |
| --- | --- | --- | --- | --- | --- |
| speed_90rpm_3a | trial 3 of a successful repeatability series | 75 / 90 | 120 RPM | 6 s | 8 s |
| speed_180rpm_3a | qualified speed_90rpm_3a run | 165 / 180 | 240 RPM | 8 s | 16 s |
| speed_360rpm_3a | qualified speed_180rpm_3a run | 345 / 360 | 480 RPM | 12 s | 24 s |
| speed_540rpm_3a | qualified speed_360rpm_3a run | 525 / 540 | 720 RPM | 24 s | 32 s |
| speed_540rpm_5a | qualified speed_540rpm_3a run | 525 / 540 | 720 RPM | 24 s | 32 s |
| speed_540rpm_5a_smooth | qualified speed_540rpm_3a run | 400 / 540 | 720 RPM | 24 s | 32 s |
| speed_600rpm_5a_smooth | qualified and raw-stability-audited speed_540rpm_5a_smooth run | 450 / 600 | 720 RPM | 24 s | 32 s |
| speed_660rpm_5a_smooth | qualified and raw-stability-audited speed_600rpm_5a_smooth run | 500 / 660 | 720 RPM | 24 s | 32 s |
| speed_700rpm_5a_smooth | qualified speed_660rpm_5a_smooth run | 520 / 700 | 720 RPM | 24 s | 32 s |
| speed_700rpm_5a_upper | qualified speed_700rpm_5a_smooth run | 600 / 700 | 720 RPM | 24 s | 32 s |

The 3 A stages retain the 3 A current ceiling and 5 A fast current threshold.
The separate 5 A comparison changes only the motor current caps to +/-5 A and
fast trip to 8 A, with a 6 A sampled-current guard and 600 A2s integral budget.
Its speed, duration, 72 J input-energy budget and acquisition bounds are unchanged
from the 540 RPM / 3 A stage. All stages retain 3 A/s rise/fall slew,
2 A DC input limit and 0.1 duty cap. The 5 A ramp takes at least 1.67 s.
The zero-current speed cutoff has
priority over the slew limiter. There is no negative torque or active brake.
Electrical speed limits are twice mechanical RPM for the reviewed ratio of 2.

The 180, 360 and 540 stages tighten the control/telemetry gap to 50, 40 and
20 ms, respectively. The 540 stage requests a 5 ms sampling pause during powered
acquisition and zero-current recovery. Sampling absolute
angle without turn ambiguity is a separate requirement from merely having a
working encoder. Do not extend RPM limits without rechecking that bound, host
latency, controller-side limits and recovery behavior.

The entry angle is acquired fresh through read-only telemetry and must stay
within 0.5 degrees through preparation. The candidate is read back exactly before
excitation. On completion, the runner commands zero current, verifies encoder
standstill, restores the exact baseline, then the CLI reopens COM10 for an
independent final quiet check. If quiet recovery fails, the runner leaves the
protective candidate in place and reports recovery_required rather than restoring
the high-current baseline while moving.

Example invocation from the outputs project directory:

```powershell
.\.venv\Scripts\python.exe -B scripts/run-synrm-pilot.py `
  --armed-free-rotor `
  --baseline logs/locked-check-preflight-20260912-01/mcconf-before.bin `
  --hfi-summary profiles/synrm-as5048a-offset-check-20260912/offset-result.json `
  --stage speed_180rpm_3a `
  --prior-run logs/synrm-speed-90rpm-3a-20260912-01 `
  --output logs/<new-reviewed-run-directory>
```

This command physically moves the motor. It performs one trial, not a scheduled
or indefinite search, and requires a confirmed free rotor. A STOP file in the
active run directory requests stopping. It is not a physical emergency stop.

Records include entry-readback.json, exact controller backups, samples.jsonl,
observations.jsonl, result.json and independent final-readback.json. The current
runtime only accepts the explicit predecessor pairs in the table. It does not
automatically progress beyond the listed stages. No 60 A stage or true maximum-speed
stage has been implemented.

The current software verifies trial-specific operating bounds, not mechanical
integrity of the custom rotor. Establish an allowable mechanical RPM ceiling
before searching for the actual maximum. Phase voltage is not measured directly
by this acquisition; DC bus, duty and current-tracking observations are retained
without relabelling them as direct Vd/Vq measurements.

The positive-current taper is not a tuned speed controller. A high-gain simulated
plant oscillates under the 5 A cutoff; this case is retained as a regression test
alongside a lower-gain passing case and stalled-rotor recovery. A physical trial
must be assessed from its complete speed history, not just a passing final-RPM
criterion. This comparison does not qualify stable speed or all-angle startup.

## Timing Diagnostics

The separately reviewed smooth 5 A comparison keeps the exact 5 A controller
candidate and all operating bounds. Only host taper onset changes to 400 RPM.
Its cutoff ends the trial with zero-current recovery, rather than resuming after
a cutoff or evaluating transient current against a powered steady-state target.
No current-tracking tolerance is loosened. Completion additionally requires a
continuous final five-second window above 420 RPM, span <=20 RPM and absolute
endpoint slope <=2 RPM/s. This is a bounded unloaded stability criterion, not
proof of maximum speed or arbitrary-load regulation.

It uses the qualified 3 A predecessor. The failed first 5 A comparison remains
diagnostic evidence only and is not reclassified as successful. Tests include
an illustrative quadratic-current plant that settles, an aggressive plant that
hits the latched cutoff, and unchanged coast-guard failure/recovery.

Coast guard events now include adjacent response gaps and both RPC latencies.
Possible interval-average speeds assume each angle was acquired within its RPC;
they are not direct acquisition timestamps or instantaneous-speed bounds.
Ambiguous spikes still fail qualification: no coast guard is suppressed.

The runner keeps both JSONL streams open, flushes every sample, and records the
last supervisor inputs, including command interval and encoder sample age. An
interval violation is reported with its measured duration rather than only a
generic input error.

`scripts/probe-synrm-timing.py --baseline <baseline.bin> --output <new-directory>`
performs a 15-second zero-current-only timing/logging test at the faster requested
sampling rate. It makes no configuration writes and verifies the unchanged
baseline and encoder standstill. A successful probe is not a hard-real-time
guarantee and does not authorize bypassing a later timing guard.
