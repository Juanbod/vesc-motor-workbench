# Independent Stator-Field Alignment

## Status

Latest result: 2 A / 4 s gave stable powered alignment at 120 degrees and a
successful reverse approach. A subsequent sweep stopped after its second step
because field tracking error was 7.086 electrical degrees (limit 5). No global
offset was applied. All trials restored the exact baseline and verified zero
current. See `logs/stator-alignment-sweep-20260912-01/REPORT.md`.

Current implementation updates superseding the preparation-only schedule below:
`--dwell` accepts 0.8, 2 or 4 seconds; matching pilot duration is required for a
sweep. Longer holds use a final approximately 0.8-second settling window.
Zero-only cleanup allows up to 6 extra seconds for coast-down without relaxing
the quiet criteria. Tracking errors abort before another step is sent.
The complete suite currently has 138 passing tests. Earlier status follows.

Latest update: physical motion was achieved at 2 A / 0.8 s, field phase 120 deg,
with 28.498544 mechanical degrees of movement during excitation. The rotor did
not settle, so no sweep was run. Initial cleanup retained low motor limits during
coast-down; separate zero-only recovery verified standstill and restored the exact
baseline. See `logs/stator-alignment-pilot-20260912-04/REPORT.md` and its
`recovery-01/result.json`. Motion reporting no longer depends on settling.
The full software test suite now has 135 passing tests. Earlier status follows.

Update: the first physical 0.5 A / 0.8 s pilot has now run after explicit
fixture-removal confirmation. Current reached 0.50 A but no movement was
verified, so no sweep was started. Zero current and exact restoration were
confirmed. See `logs/stator-alignment-pilot-20260912-01/REPORT.md`. The following
preparation-time status describes the earlier state, not the current fixture.

Prepared and software-tested on 2026-09-12. NO physical alignment run yet.
The rotor is still considered mechanically locked. No serial connection was
opened while preparing this feature. No fixture state or live configuration was
changed. Do not remove the software interlock without explicit confirmation
that the user has physically removed the fixture and cleared the test area.

Entry point: `scripts/align-stator-field.py`.
Implementation: `vesc_workbench/field_alignment.py`.
Tests: `tests/test_field_alignment.py`; complete suite: 134 passing tests.

## Why a Separate Measurement

HFI at four distinct positions produced offset estimates spanning 10.367238
electrical degrees. Returning near the first pose reproduced its result.
Ratio=2/noninverted ranked best, but did not pass the common-offset criteria.
The new procedure observes physical equilibrium in a known stationary stator
field instead of deriving an axis from the HFI current waveform.

The supplied rotor drawing specifies four equally spaced helical through-slots,
90-degree spacing, width 5 +/- 0.1 mm, length 21 +/- 0.1 mm and 26 mechanical
degrees of right-hand angular advance over its length. Inner/outer diameters
are 36 and 40.3 mm. There are no permanent torque-producing magnets. The separate
AS5048A sensor magnet must remain fixed relative to the shaft. This geometry is
context, not a computed encoder calibration or proof of the pole-pair count.

## Audited Firmware Convention

Source commit: `f7c2b34e1cff2234cae98be3abf0cd50e249558f`.

- `terminal.c`: `rotor_lock_openloop current time angle` repeats a fixed-phase
  command every approximately 2 ms, checks faults, then sets current to zero
  and prints `Done`. A zero-duration command is unbounded and is NOT used.
- `motor/mcpwm_foc.c`: `mcpwm_foc_set_openloop_phase` sets Id=current, Iq=0 and
  overrides the control phase with the supplied stator angle. MTPA is disabled.
  Current decoupling and field weakening are also disabled for the test.
- In the ideal reluctance model, stable alignment follows maximum inductance.
  This is not the minimum-L d-axis used by the previous HFI analysis. Conversion:
  `minimum_L_axis = stator_field_angle + 90 electrical degrees (mod 180)`.
- Candidate offset: `sign * ratio * raw_encoder - minimum_L_axis (mod 180)`.
  The two branches separated by 180 electrical degrees are retained. No
  automatic branch choice, application or startup validation is performed.

Friction, saturation, field harmonics and sensor errors can bias equilibrium.
Agreement between methods is evidence, not a guarantee of absolute accuracy.

## Staged Sequence

1. Read and back up fresh motor/application configurations. Exact reviewed
   baseline match, correct firmware/hardware and quiet encoder are required.
2. Isolate external application control in RAM, watchdog 300 ms, brake zero.
3. Write protective motor configuration, verify exact bytes. Limits: phase
   +/-2 A, absolute 3 A with fast trip, input +1/0 A and duty 0.1.
4. Pilot: stator phase 150 degrees, 0.5 A for 0.8 s, then zero current. This phase
   is a chosen test field direction, not a presumed correct encoder offset.
5. Require powered current-vector tracking, settled position and at least one
   mechanical degree of verified movement. No movement is inconclusive; no
   automatic increase of current or duration follows. Being motionless alone
   does NOT pass the calibration test.
6. Only a successful pilot report on the same baseline/current/starting phase
   permits a sweep. Recheck fresh state before starting it.
7. Sweep: 30-electrical-degree increments over one electrical revolution,
   followed by the same positions in reverse. 26 finite 0.8 s commands,
   at least 2 s zero-current intervals. Total commanded on-time 20.8 s.
8. Verify tracking between steps, compare matching forward/reverse positions,
   and calculate axial residuals. A candidate requires <=3 electrical degrees
   of hysteresis and maximum residual, and axial concentration >=0.99.
9. Verify zero current and restore exact original motor bytes. Leave external
   application disabled in RAM; do not silently reconnect the throttle.

Current options are restricted to 0.5, 1 or 2 A; each sweep requires a pilot at
the SAME setting. Selecting another level requires an explicit reviewed run.
Whether 0.5 A can overcome this rotor's friction is unknown until the pilot.

## Abort and Cleanup

Limits include encoder speed 60 mechanical RPM, travel 60 mechanical degrees
per step, telemetry gaps/latency 100 ms, sampled current 2.5 A, input 1.2 A,
duty 0.1, bus 18..30 V, MOS temperature 50 C and any controller fault.
Observer ERPM is logged but is NOT used as physical speed evidence.
Invalid motor-temperature telemetry is not taken as a real winding temperature;
this remains a short, low-current supervised test, not an unattended thermal run.

The stock terminal loop resets its own watchdog: host zero current may NOT
cancel it immediately. Every command has a positive, fixed 0.8 s duration.
Cleanup repeatedly sends zero beyond the nominal command tail and requires a
fresh quiet interval. Faults, missing `Done`, lack of settling, `STOP` file or
interruption terminate the sequence. No automatic retry follows failure.
If standstill or application isolation cannot be verified, original high motor
limits are not restored. Physical power disconnection remains the emergency stop.

Logs contain each attempted command (persisted before dispatch), telemetry,
terminal messages, per-step results, backups, cleanup status and analysis.
A missing completion is not treated as success. A sweep may complete acquisition
but yield no calibration candidate; inspect `analysis.status`, not only `ok`.

## Offline Commands

From the maintained project root:

```powershell
.\.venv\Scripts\python.exe -B scripts/align-stator-field.py --mode pilot --output profiles/NEW-pilot-plan
.\.venv\Scripts\python.exe -B scripts/align-stator-field.py --mode sweep --output profiles/NEW-sweep-plan
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
```

Existing generated plans: `profiles/stator-alignment-pilot-20260912/plan.json`
and `profiles/stator-alignment-sweep-20260912/plan.json`.
Without `--armed-free-rotor-alignment`, the CLI never opens a serial port.
Live use additionally needs `--baseline`; sweep also needs `--pilot-result`.
Every output directory must be new. Never edit `bench-fixture.json` merely to
make a command pass: the physical fixture must actually have been removed.

## Verification Coverage

Tests include bounded schedule generation, locked/unknown fixture refusal before
I/O, angle wrap, encoder-based guards, current-vector validation, ideal full
sweep and 90-degree axis conversion, reversal hysteresis rejection, successful
pilot-to-sweep gating, missing pilot, mismatched configuration, stuck rotor,
lost telemetry and missing completion. Synthetic tests use a fake transport;
they do not establish physical settling, safe torque or achieved calibration.
