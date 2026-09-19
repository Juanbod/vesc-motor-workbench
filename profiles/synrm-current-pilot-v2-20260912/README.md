# Single current pilot v2

Software implementation and fault-injection tests are complete. No physical
pilot has been run, no COM port opened during this preparation, and no controller
configuration or fixture state changed. The fixture is still marked LOCKED.

This replaces the execution plan in `profiles/synrm-current-pilot-20260912`.
The old evidence and draft were not overwritten. Neither binary is a production
profile or permission for unattended use. Do not upload the binary manually.

## Encoder source enforcement

The currently used stock telemetry does not expose `m_using_encoder`. The new
runner therefore uses a configuration-based argument, NOT a fabricated live flag:

- Pinned reference: `f7c2b34e1cff2234cae98be3abf0cd50e249558f`.
- `motor/mcpwm_foc.c:2754`: dt is at least 1/f_zv for a positive integer loop divider.
- `motor/mcpwm_foc.c:3243`: phase differences entering the fast estimator are clamped
  to +/-pi/3; its 0.01 low-pass update is convex, starting from zero initialization.
- At 30 kHz this bounds the fast estimate by 300,000 electrical RPM (a conservative
  bound covering both sampling modes), not the actual rotor speed.
- `motor/foc_math.c:512`: encoder re-entry threshold is 0.95*Sensorless ERPM.
- Set Sensorless ERPM to 500,000 for this isolated low-speed test. Re-entry at
  475,000 exceeds the estimator bound; the reference selection logic chooses the
  encoder when available. No observer transition is being tested.

This does NOT raise the permitted motor speed. The configuration speed limits
remain +/-120 electrical RPM, or 60 mechanical RPM at ratio 2. Current and duty
limits are also unchanged from the 2 A pilot proposal.

The proof is conditional on the board using the reviewed source logic, a positive
loop divider, a functioning configured encoder and no competing configuration
writer. Firmware name/version are not binary attestation. The report explicitly
labels this as configuration inference, not direct source telemetry or an
unconditional hardware guarantee. Exact readback must accept all requested fields;
if the board clamps/rejects them, no torque command follows.

## Dedicated runner

Entry point: `scripts/run-synrm-pilot.py`. No speed commands, terminal rotation
commands, repeats, parameter search or automatic escalation are implemented.

1. Refuse before opening COM10 unless the user-confirmed fixture state is free.
2. Revalidate the HFI source reports, firmware/hardware and baseline configuration.
3. After power cycling, permit only fresh current/voltage ADC calibration changes;
   reject other field or unexplained byte changes. Preserve and restore the freshly
   read baseline rather than overwriting it with stale ADC calibration.
4. Back up configuration, isolate external control in RAM with a verified 300 ms
   zero-brake watchdog, check SPI diagnostics and verify an 8-second quiet interval.
5. Require starting raw position within 0.5 mechanical degree of 207.203425277 deg.
6. Write the low-current candidate, verify exact bytes and source-policy fields,
   then check another quiet interval and unchanged configuration.
7. Ramp current toward 2 A over 1 second. Compare measured Id/Iq to the zero-flux
   targets, independently derive physical travel/speed from raw encoder position,
   and enforce the timing, current, energy, temperature and direction limits.
8. Stop early when at least 3 mechanical degrees of forward motion and 150 ms of
   current tracking after ramp settling are observed. This is a LOCAL movement
   result, not a successful full start, torque rating, global offset or speed test.
9. Always send zero current and wait for fresh, quiet telemetry before rollback.
   If quiet data cannot be obtained, retain the low-current configuration and
   report `recovery_required`; never restore the high-current baseline blindly.
   External control is not re-enabled.

The host stops sending torque by 3.8 s, leaving margin for the nominal 4 s budget.
These are software/sample-based bounds, not hard real-time guarantees; the 300 ms
controller watchdog is a separate fallback for communication loss. A `STOP` file
in the run folder is checked before excitation and throughout the current loop.

## Limits and data

Command <=2 A, phase limits +/-2 A, fast absolute fault threshold 3 A, input 1 A,
duty <=0.1, travel <10 mechanical degrees, speed <60 mechanical RPM, input energy
<8 J, I2t <16 A2s, telemetry gaps <=100 ms, bus 18..30 V, MOS temperature <=50 C.
Winding temperature is unavailable; these are short diagnostic bounds only.

MTPA requests Id=-abs(I)/sqrt(2) and Iq=I/sqrt(2) in the reviewed zero-flux model.
The tentative 1.020427465-degree offset remains a local HFI hypothesis. R/L,
current-loop gains and ADC calibration are not tuned by this experiment.

Each execution writes backups, the candidate bytes, raw `samples.jsonl`, derived
`observations.jsonl` including commands/Id/Iq/energy/travel, and `result.json`.
An ADC-only power-cycle migration keeps its differences and the original evidence
baseline hash in the report; it does not relabel the old HFI measurement as new.

## Verification

Full suite: 165 tests, 162 passed, 3 NumPy-dependent tests skipped. New checks cover
the configuration bound, unchanged speed limits, positive/negative current math,
power-cycle ADC preservation, local motion, stall, reverse motion, missing Id,
transient/permanent telemetry loss, configuration readback mismatch, STOP file,
and locked-fixture refusal before serial construction. Tests use fake hardware;
they are not physical motor results.

## Next physical step

With power off, remove the mechanical fixture without deliberately turning the
shaft. Secure the motor body and clear the rotor's movement area. Only after the
user confirms that the rotor is free may the fixture marker change. On power-up,
run fresh checks; any position/configuration mismatch stops the pilot for review.

Prepared files: `plan.json`, `candidate.NOT_ARMED.bin`.
Baseline SHA256: `41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`.
Candidate SHA256: `3b00126e2760a9e178b29088aee4e49db74c34e62daa0894391eb1c1a4273a2e`.
