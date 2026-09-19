# Locked-Rotor Calibration Preparation

## Measured Offset Update

The stock HFI capture path was subsequently implemented and exercised physically.
Three independent qualified DFT acquisitions now give 350.2653 / 170.2653 electrical
degrees at the current locked pose, assuming ratio 2 and non-inverted encoder.
This supersedes the preparation-stage statements below about the missing
acquisition adapter. Raw captures and limitations are in the
[measured-offset report](../profiles/synrm-as5048a-offset-measured-20260912/README.md).
The result has not been applied; multi-pose and free-rotor validation remain.

## Subsequent Physical Probe

After the offline preparation below, one real 0.5 A / 40 ms fixed-phase command
was issued. Winding-current telemetry became nonzero, but recording was aborted
by an observer-ERPM guard. No inductance sampling or offset calibration occurred.
The original configuration was subsequently verified restored and current zero.
See [physical probe report](../logs/locked-physical-probe-20260912-03/REPORT.md).
This uses a separate exact-command permission, not a free-rotor unlock; the
general acquisition adapter described below remains unimplemented.

## State

On 2026-09-12 the user reported that the rotor was mechanically fixed.
No motor commands, serial connections, configuration writes or firmware uploads
were performed while preparing this software.

Implemented:

- Offline measurement schedule, repeat validation, harmonic fit and reports.
- Joint encoder direction/pole-pair search, without using the PM observer.
- Two offset candidates, 180 electrical degrees apart; no automatic selection.
- Synthetic datasets, deterministic replay, evidence hashes, exclusive output
  directories, and rejection tests. No new dependency is required.
- A local fixture interlock in the maintained UART client's `send_payload` path.

NOT implemented/validated:

- A real on-controller bounded pulse acquisition adapter.
- Conversion of stock HFI plots to verified stator-frame measurement records.
- Actual inductance axes, encoder ratio/direction or offset calibration.
- Automatic application of the result or free-rotor verification.

The preparation is not a claim that a powered calibration is ready. Keep the
rotor locked, power disconnected when handling the fixture, and do not run a
normal startup/speed experiment with the fixture installed.

## Offline Commands

Run from `C:\Users\jando\Desktop\Codex\2026-08-11\e-d\outputs`:

```powershell
.\.venv\Scripts\python.exe -B scripts/calibrate-locked-rotor.py prepare --plan config/locked-rotor.json --output logs/locked-prepare-new
.\.venv\Scripts\python.exe -B scripts/calibrate-locked-rotor.py simulate --plan config/locked-rotor.json --output logs/locked-simulation-new
.\.venv\Scripts\python.exe -B scripts/calibrate-locked-rotor.py analyze --input logs/locked-simulation-new/dataset.json --output logs/locked-replay-new
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
```

All three calibration commands are offline and have no `--armed`, serial-port,
terminal-command or firmware-upload option. `--baseline PATH` optionally hashes
a local binary backup; it neither loads that backup into VESC nor proves that
the live configuration matches it. Existing output directories are rejected.
An analysis exit code of 2 means rejected/ambiguous data, not a controller fault.

## Acquisition Contract

Default schedule: 12 stator excitation directions from 0 to 165 degrees, three
complete repeats per locked pose. Four distinct mechanical poses are required
to discriminate direction and pole-pair count. Suggested manual relative poses
are 0, 17, 43, 79 mechanical degrees, to avoid common symmetric sampling aliases.
These are planning targets, not motor positioning commands. Each physical
reposition must occur with power disconnected and needs a fresh fixture check.
The actual encoder position is recorded; it need not equal the planning target.

The dataset schema is `vesc-locked-rotor-v1`. See generated `dataset.json` for a
complete example. It contains an embedded plan, explicit `simulated` flag,
`frame=stator_alpha_beta`, `quantity=directional_inverse_inductance_h-1` and poses.
Each pose has a unique ID and one sample per repeat/direction. Required fields:

| Field | Meaning |
| --- | --- |
| repeat | Zero-based repeat index |
| phase_deg | Applied vector angle in the fixed stator alpha/beta frame |
| response_inv_h | Directional incremental inverse inductance, 1/H |
| encoder_deg | Raw mechanical AS5048A angle, [0, 360) |
| encoder_age_s | Age at acquisition, not at file import |
| peak_current_a | Maximum absolute phase-current measurement during the burst |
| burst_s | Actual excitation burst duration, seconds |
| energy_j | Nonnegative consumed energy integrated during that burst |
| i2t_a2s | Integral of squared phase-current magnitude during that burst |
| fault | Controller fault code; only integer zero is accepted |

Required future acquisition envelope: at most 3 A peak phase current, 50 ms per
burst, 2 J and 5 A^2 s per pose, at least 8 s cooldown. These are proposed ceilings,
NOT a tested pulse amplitude recipe and NOT guarantees implemented in firmware.
Start amplitude and pulse timing must be established from hardware acquisition
and protection behavior, rather than derived from a host USB sampling interval.

The real adapter must establish the phase origin/sign, simultaneous ADC timing,
current offsets, applied voltage, resistance/dead-time correction, and firmware
identity. GET_VALUES at USB rates cannot measure microsecond current slopes.
The adapter must enforce bounds on the controller even if USB disconnects.
Host-side rejection after a measurement is not a substitute for those guards.

## Axis Calculation

For a linear incremental inductance tensor, the directional inverse inductance
has a second spatial harmonic:

```text
response(theta) = a + b*cos(2*theta) + c*sin(2*theta)
amplitude = hypot(b, c)
minimum_L_axis = 0.5*atan2(c, b) modulo 180 degrees
L_min = 1 / (a + amplitude)
L_max = 1 / (a - amplitude)
offset = (direction*pole_pairs*raw_encoder_angle - d_axis_angle) modulo 180
```

The balanced acquisition grid permits a small standard-library Fourier fit.
Every repeat must pass independently. Weak saliency, nonlinear/higher-harmonic
response, nonpositive eigenvalues, inconsistent repeats, encoder movement,
stale data, missing/duplicate grid samples, faults and exceeded recorded budgets
are rejected. Saturation or a non-sinusoidal custom rotor may legitimately fail
the model; do not hide that by relaxing thresholds until an offset appears.

The default `minimum_inductance` d-axis follows the configured positive
`foc_motor_ld_lq_diff` convention in the reviewed VESC source:

```text
Lq = L_average + configured_difference/2
Ld = L_average - configured_difference/2
```

If choosing a different axis convention, the sign of the motor model must agree.
The parameter name alone does not establish the sign. The analyzer supports an
explicit maximum-inductance d-axis but does not change the controller model.

All integer pole-pair hypotheses 1..8 and both encoder directions are compared
over the poses. A candidate requires a unique fit within 3 electrical degrees
and separation from the next hypothesis. Repeated/symmetric poses can leave the
result ambiguous. The pair-count assumption is direct drive; encoder gearing
would require a different hypothesis model.

Even a perfect saliency fit leaves 180 electrical degrees of axis ambiguity.
The result always has `hardware_validated=false` and `auto_apply_allowed=false`.
A result is not a guarantee of loaded starting torque, speed stability or
thermal capability. Do not use synthetic results as measured motor parameters.

## Firmware Audit

Reviewed the locally available official source at commit
`f7c2b34e1cff2234cae98be3abf0cd50e249558f`, the project's 6.02 reference. This is
a source reference, not an assertion that the live controller binary is identical.
The source checkout HEAD is newer; the audit explicitly used `git show` at the
pinned commit, not the current working-tree implementation.

- `terminal.c`: `measure_ind` invokes `mcpwm_foc_measure_inductance` with 400
  samples and prints scalar inductance, difference and current. It does not
  return the saliency axis angle.
- `motor/mcpwm_foc.c`: this routine changes the HFI configuration in RAM, locks
  the motor interface, performs a loop of 10 ms waits and resets the watchdog
  internally. The host's usual 300 ms watchdog must not be assumed to abort
  this routine on USB loss. Its duty input is not a calibrated peak-current cap.
- At the pinned version, the HFI plot graph labelled `Phase bin2` is fed
  `angle_bin_1`. The label alone is not a reliable calibration reference.
- `rotor_lock_openloop` is a current-holding command, not an inductance sampler;
  its timed loop also resets the watchdog. It is not used by this preparation.

Sources:
[terminal.c](https://github.com/vedderb/bldc/blob/f7c2b34e1cff2234cae98be3abf0cd50e249558f/terminal.c),
[mcpwm_foc.c](https://github.com/vedderb/bldc/blob/f7c2b34e1cff2234cae98be3abf0cd50e249558f/motor/mcpwm_foc.c),
[foc_math.c](https://github.com/vedderb/bldc/blob/f7c2b34e1cff2234cae98be3abf0cd50e249558f/motor/foc_math.c).

Next engineering step: implement/review a firmware-matched, self-terminating
acquisition path with on-controller current/time limits and verified angular
data. It may use an audited existing sample path or a separate firmware change;
no firmware changes or uploads are authorized by this preparation. Do not
enable a host script that assumes those missing protections already exist.

## Fixture Interlock Scope

`config/bench-fixture.json` records the user's locked-rotor report. The maintained
`VescUartClient.send_payload` checks it before serial writes. While locked, or
if the file is missing/corrupt, only exact read-only requests and zero-current
stop are allowed. RPM zero, duty zero, ALIVE, terminal excitation, display-mode
changes and configuration writes are blocked. The file is re-read for each
potentially powered command. There is no automatic unlock or `--force` option.

Clearing the state requires the user's explicit confirmation that the fixture
was physically removed. A future bounded acquisition must have its own narrowly
scoped authorization, not pretend that the rotor is free.

This interlock covers this package's UART client only. VESC Tool, previous
standalone scripts, other applications and already-running programs are not
interlocked. It cannot replace a mechanical guard or physical power isolation.
