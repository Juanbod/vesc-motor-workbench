# First physical zero-flux current pilot, 2026-09-12

One real pilot was executed after the user confirmed physical fixture removal.
No automatic repeat, speed command, firmware update or current escalation followed.
The original machine report and raw logs are preserved unchanged.

## Observed response

| Quantity | Measured result |
| --- | --- |
| Powered duration | 0.837145 s |
| Last/maximum current command | 1.630364 A |
| Maximum measured sqrt(Id^2+Iq^2) | 1.612203 A |
| Final powered Id / Iq | -1.14 / +1.14 A |
| Maximum Id tracking error after 0.55 s | 0.031914 A |
| Maximum Iq tracking error after 0.55 s | 0.028292 A |
| Raw angle just before current | 207.663568 mechanical deg |
| Raw angle at powered stop criterion | 211.047360 mechanical deg |
| Powered encoder displacement | +3.383792 mechanical deg |
| Peak encoder-derived speed during powered interval | 2.707092 mechanical RPM |
| Sampled input energy during powered interval | 0.070616 J |
| Sampled Id/Iq I2t | 0.714245 A2s |
| Raw angle at runner final readback | 219.375008 mechanical deg |

The current command ramp stopped on the local movement criterion before reaching
2 A. The independently logged raw encoder is the motion evidence; a visual check
was requested from the user but has not yet been received at report creation.
The quoted 2.71 RPM is NOT a motor speed limit, achieved sustained-speed result,
or maximum-speed measurement. Input energy is a sampled estimate near the input
current telemetry resolution, not a calorimetric or high-bandwidth measurement.

## Important travel-limit limitation

After the powered stop criterion, the encoder moved another +8.327648 deg by the
runner's final sample: total displacement +11.711440 deg. A later independent
read-only check showed 220.605472 deg, or +12.941904 deg from the starting sample.
The later change is not independently attributable to coasting rather than an
external disturbance or position measurement behavior.

Thus the nominal 10-degree envelope was NOT demonstrated over the whole event.
The runner checks travel while powered, but commands zero current rather than
active position braking. Zero current does not guarantee a mechanical stopping
position. Its quiet window can verify small recent movement, not a permanently
fixed angle. The original `ok: true` denotes its local motion/current and recovery
criteria only; it must not be treated as full-event travel-envelope qualification.

No new run should reuse the local 207.203425-degree HFI pose without checking the
new starting position. The current position is outside the allowed +/-0.5-degree
starting-pose window. Do not simply widen that window or increase current.

## Recovery and state

No controller faults were reported. The runner verified zero current and restored
the exact pre-test motor baseline. Independent verification in
`final-readback.json` collected 25 quiet samples and rechecked motor/app bytes.
Its final values: motor/input current, Id, Iq, duty and reported ERPM zero,
fault code 0, bus 24.8 V, MOS temperature 26.3 C. Winding temperature is invalid.

Active encoder offset remains 267.527648926 deg, not the candidate 1.020427465 deg.
Baseline SHA256:
`41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`.
External control remains isolated in RAM; a power cycle requires fresh checks.
Fixture state remains user-confirmed FREE. No HFI locked-rotor command is allowed
unless the user confirms physically locking the rotor again.

## Interpretation

The zero-flux MTPA configuration produced the expected nonzero Id/Iq relationship
and an encoder-reported local forward displacement at low current. This is useful
physical evidence, but does not establish a correct global offset, guaranteed
startup, sustained rotation, useful load torque or high-speed stability.

Before further motion tests, review the full-event travel/stop envelope and choose
a new explicitly bounded experiment appropriate to the actual starting pose.
