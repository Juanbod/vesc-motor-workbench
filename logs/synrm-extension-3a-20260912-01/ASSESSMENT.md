# Physical 3 A extension, 2026-09-12

The user authorized continued testing and currents up to 15 A. Only the first
reviewed increase to 3 A was executed, once. No test at 5..15 A, automatic repeat,
speed command, firmware update or disabled temperature protection occurred.

## Experiment

This is a motion experiment at a new starting pose, NOT another same-pose HFI
calibration. It retains the provisional 1.020427465-degree encoder offset and
zero-flux MTPA hypothesis. The initial angle was checked against the independent
quiet readback from the previous physical pilot, not relabelled as a calibrated
HFI pose. Reference source and source-selection inference limitations remain.

Reviewed limits: command/phase current 3 A, observed Id/Iq magnitude 3.6 A,
fast absolute fault threshold 5 A, input limit 2 A, duty 0.1, physical speed
60 RPM, powered host budget under 4 s, 90-degree travel envelope, 36 A2s and
12 J budgets, bus 18..30 V, MOS <=50 C. At least 8 s quiet cooldown preceded it.
Zero-current stop was used, not active braking; full-event travel was recorded.

## Results from raw observations

| Quantity | Value |
| --- | --- |
| Starting raw angle | 221.044928 mechanical deg |
| Final powered raw angle | 312.231456 mechanical deg |
| Powered displacement at triggering sample | +91.186528 mechanical deg |
| Time at triggering sample | 1.499840 s |
| Maximum current command | 3.000 A |
| Maximum measured sqrt(Id^2+Iq^2) | 3.047638 A |
| Final powered Id / Iq | -2.07 / +2.19 A |
| Final expected Id / Iq | -2.121320 / +2.121320 A |
| Peak encoder-derived speed during power | 34.000816 mechanical RPM |
| Largest powered sample latency | 0.0009593 s |
| Peak sampled input current | 0.04 A |
| Peak duty | 0.024 |
| Sampled powered input energy | 0.865018 J |
| Sampled powered I2t | 7.329345 A2s |
| Maximum observed MOS temperature | 26.4 C |
| Controller fault code | 0 |

The triggering sample exceeds the 90-degree powered travel threshold. It does not
exceed the speed, telemetry, current, duty, voltage, temperature, energy or duration
checks. Zero current was then commanded. This was a host experiment-bound stop,
NOT an ESC fault, diagnosed desynchronization or evidence of insufficient current.
It also does not establish sustained rotation or the motor's maximum speed.

## Coast and report interpretation

At the runner's final sample, unwrapped total displacement was +256.398920 deg
(peak +256.618648 deg). Subtracting the actual triggering powered displacement
gives approximately +165.212392 deg of subsequent net movement. Hence the total
90-degree envelope was not met; no automatic retry is justified by this result.

The original `result.json` remains unchanged. At acquisition time, its summarized
powered fields were updated only after the guard passed. They therefore contain
the previous valid sample (86.440416 deg, 1.478340 s), and its `coast_travel_deg`
overstates coast by one powered sample. The complete triggering observation was
already preserved in `observations.jsonl`; the table above uses that record.
The runner has now been fixed to record the triggering sample before validation.

`motion_observed: false` in the old result means the stage's planned completion
criterion was not reached before the guard stopped it; it does NOT mean the raw
encoder showed no movement. Future reports separately record encoder displacement
and stage qualification. The status `travel_envelope_exceeded` and `ok: false`
correctly prevent this from being classified as a fully qualified experiment.

## Recovery

Zero current and exact motor-baseline restoration succeeded. Independent read-only
verification in `final-readback.json` collected 25 quiet samples and confirmed
unchanged motor/app bytes. Final raw angle was 117.048336 deg; motor/input current,
Id, Iq, duty and reported ERPM were zero, fault code 0, bus 24.8 V, MOS 26.4 C.
Winding-temperature telemetry is invalid; the user's observation of no stator
heating is not a calibrated winding-temperature measurement.

Active offset is again 267.527648926 deg, not the provisional candidate offset.
External app remains isolated in RAM. Baseline SHA256:
`41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`.
Candidate SHA256:
`ae009dae1cd17e4088342e3911103b33d5dcf0774a90181dd72d55284ddac9d1`.

## Next decision

There is useful low-current acceleration evidence. Before raising current again,
define a bounded continuous-rotation experiment at the same 3 A with suitable
speed/time/energy and coast-down checks, rather than merely raising the old
position envelope after its stop. Recheck the actual starting angle and retain
the uncalibrated-offset caveat. Do not classify the present result as guaranteed
startup, steady-speed control or load-torque validation.

Software verification after the extension and report fix: 169 tests ran,
166 passed, 3 NumPy-dependent tests skipped. These tests use simulated hardware
and are distinct from the one physical acquisition documented here.
