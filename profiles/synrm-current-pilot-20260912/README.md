# Zero-flux current pilot: offline draft

NOT ARMED. No motor command or configuration write was sent while preparing this
draft. `candidate.NOT_ARMED.bin` is not a released operating profile and must not
be imported manually to bypass the pending checks. `plan.json` is the full draft.

## Purpose

Separate the current-target problem from the encoder-offset problem. Use a single
short current-command trial, not a speed loop, automatic offset sweep, high-speed
test or observer transition experiment. A zero-PM-flux model is a test hypothesis,
not proof that the installed firmware implements a fully validated SynRM drive.

The candidate uses requested-current MTPA, zero flux linkage, saturation
compensation off, the original Ortega observer selection, decoupling off and field
weakening off. Speed source is corrected phase, not observer-only phase. R/L,
current-loop gains, encoder ratio/direction and ADC calibrations are preserved.

For positive Lq-Ld and zero flux the pinned MTPA formula reduces to
`Id = -abs(I)/sqrt(2)`, `Iq = I/sqrt(2)` before later limiting. A 2 A command
therefore requests approximately -1.414 A Id and +1.414 A Iq, not 2 A on each axis.
The software checks both channels; this is not a direct measurement of torque.

The tentative offset is 1.020427465 electrical deg, derived from the repeatable
HFI point at raw 207.203425277 mechanical deg. It is NOT globally calibrated.
Starting position must be rechecked against that local measurement. No numerical
correction from the rejected periodic model is used.

## Proposed bounds

- One command ramp to at most 2 A over 1 second.
- Stop by 4 powered seconds, 10 mechanical degrees, or 60 mechanical RPM.
- Phase limits +/-2 A, fast absolute fault threshold 3 A, input limit 1 A.
- Duty <=0.1, no commanded regeneration, 8 J input-energy and 16 A2s budgets.
- At least 8 seconds cooldown; fresh encoder/current telemetry within 100 ms.
- Bus 18..30 V and MOS temperature <=50 C; winding-temperature sensor unavailable.
- Stop and verify standstill before exact rollback. No automatic follow-on trial.

These are proposed runtime constraints. The current generic startup runner does
NOT implement all of them, so do not launch this draft with `diagnose-start.py`.

## Implemented preparation checks

`scripts/prepare-synrm-pilot.py` revalidates the original HFI reports and rejects a
different baseline hash. `vesc_workbench/synrm_pilot.py` checks encoder setup,
positive-definite inductance model, reviewed current-loop gains, finite MTPA math
and preservation of all unrequested configuration fields. It generates files only.

`validate_observation` checks source status freshness, current, voltage, duty,
MOS temperature, actual encoder speed/travel, timing, energy and I2t. After current
settling it checks Id/Iq against the model with tolerance max(0.2 A, 25% of command).
That function is unit-tested but is NOT yet wired to a physical pilot runner.

Seven new unit tests cover current targets in both directions, finite-input and
configuration rejection, preservation of unrelated fields, source telemetry and
pilot bounds. Full suite: 154 tests, 151 passed, 3 NumPy-dependent tests skipped.
Synthetic tests are software verification, not physical motor results.

## Blocking items before physical execution

1. Rotor is still physically reported locked. A free-rotor trial requires the user
   to remove the fixture with power off and confirm that state change.
2. Source selection needs explicit telemetry or another reviewed enforcement
   mechanism. Do not infer it from ordinary GET_VALUES ERPM.
3. Complete and test the single-trial executor with the above checks, exact
   readback, stop/rollback, fresh baseline and power-cycle handling.

Pinned source `f7c2b34e1cff2234cae98be3abf0cd50e249558f`:
`motor/foc_math.c:512` selects encoder/observer using `m_speed_est_fast`, with
5% hysteresis. At threshold 4000 eRPM it selects encoder below 3800 and switches
away above 4200. `motor/mcpwm_foc.c:3227` distinguishes the fast estimate from the
PLL estimate. A low physical speed or low exported PLL ERPM alone is insufficient
to assert the selected source. Changing to corrected-phase speed is not an
unconditional encoder-only switch.

The pinned source is a reviewed reference, not a binary identity attestation for
the connected board. No firmware update has been made.

## Files and hashes

- Plan: `plan.json`.
- Non-armed binary draft: `candidate.NOT_ARMED.bin`.
- Baseline SHA256: `41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`.
- Candidate SHA256: `a8016f6864802fc8a5efb620ecda34f29a5da866e0ff2aab07414592e7435e83`.

No claim is made that the motor starts, runs at speed, produces a particular
torque or has a correct global offset with this draft.
