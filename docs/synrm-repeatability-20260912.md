# Bounded startup repeatability runner

The implementation is `vesc_workbench/synrm_repeatability.py`, using the existing
single-trial runner with stage `repeatability_3a`. It performs at most three
powered trials and never automatically retries a failed trial or raises current.

## Entry conditions

- User-confirmed free rotor in `config/bench-fixture.json`.
- A successful `rotation_3a` seed run with raw observations, exact baseline and
  candidate backups, and independent `final-readback.json`.
- Matching reviewed MKSESC hardware and firmware identifiers, direct AS504x
  encoder, ratio 2, noninverted encoder and isolated external app.
- Fresh read-only baseline/standstill acquisition before every repeat. The entry
  reading must be at most 1 s old when the runner accepts it. The initial angle
  must remain within 0.5 deg through preflight and candidate configuration.
- Raw starting angle at least 10 deg from earlier tested starts. This is not
  phase-aware saliency coverage and must not be described as all-angle testing.

## Bounds and controls

Current ceiling 3 A, current ramp/slew 3 A/s, positive-current taper starting at
20 RPM and zero-current cutoff at 35 RPM. No speed PID or active brake is used.
Encoder-derived hard speed guard 60 RPM; each host loop is limited to 3.8 s plus
one bounded final sample, remaining below the 4 s observation budget. A 300 ms
zero-brake controller watchdog is verified, not a hard-real-time guarantee.

Other per-trial bounds remain: observed Id/Iq norm 3.6 A, fast current threshold
5 A, input limit 2 A, duty 0.1, bus 18..30 V, MOS <=50 C, 36 A2s and 12 J.
Winding temperature is unavailable, so the series is short and current-limited.
At least 8 s of quiet preflight precedes each trial. Zero-current recovery must
verify standstill within its 8 s observation window before baseline restoration.

The controller candidate bytes are unchanged from `rotation_3a`. The larger
rotation travel envelope already reviewed for that stage is retained, including
coast monitoring. No position-stop or stopping-distance guarantee is implied.

## Launch and records

Run from the `outputs` project directory with its `.venv` interpreter:

```powershell
.\.venv\Scripts\python.exe -B scripts/run-synrm-repeatability.py `
  --armed-free-rotor `
  --baseline logs/locked-check-preflight-20260912-01/mcconf-before.bin `
  --hfi-summary profiles/synrm-as5048a-offset-check-20260912/offset-result.json `
  --prior-run logs/synrm-rotation-3a-20260912-01 `
  --output logs/<new-reviewed-series-directory>
```

This command opens COM10 and can physically move the motor. It is not an offline
generator. A new output directory is required; historical reports are never
overwritten. The script does not run on a schedule or after it exits.

`series.json` records incremental status and totals. Each `trial-NN` directory
contains raw samples, derived observations, controller backups and the single-run
result. `trial-NN-entry-readback.json` records the fresh starting reference.
`trial-NN/final-readback.json` is acquired independently after cleanup.

A `STOP` file in the series root or active trial directory prevents subsequent
excitation and requests zero-current stopping during a trial. This is software
control, not a physical emergency stop. A failed trial ends the series; there is
no automatic restart from an aborted run.

## Verification

Tests cover three simulated starts and refusal of a fourth in the reference
chain, identical current configuration, wraparound, same-pose refusal, stale
entry rejection, refusal of movement during preparation, STOP during excitation,
stall, independent readback failure, read-only behavior and locked-fixture CLI
interlock. Run all tests with:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
```
