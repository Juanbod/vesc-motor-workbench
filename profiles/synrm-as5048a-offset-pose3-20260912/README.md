# Third locked-pose physical measurement

2026-09-12. The user confirmed a further repositioning and secure fixture.
Three physical `measure_ind 0.100` acquisitions were completed with the same
protective limits, DFT plot mode 1 and zero-speed PLL convention. No rotation
commands were sent. No candidate offset has been applied.

| Acquisition | Raw encoder, mechanical deg | Minimum-L axis, electrical deg | Offset branch, electrical deg |
| --- | ---: | ---: | ---: |
| pose3-01 | 263.429220 | 165.402169 | 1.456271 |
| pose3-02 | 263.411864 | 166.526477 | 0.297252 |
| pose3-03 | 263.399562 | 166.655080 | 0.144044 |

Axial mean offset: 0.632495 deg, equivalent axis branch 180.632495 deg.
Across-run range: 1.312227 deg. Largest chronological block error: 2.037267 deg.
215 evaluated DFT frames. Per-run concentrations: 0.989325, 0.986072, 0.991566.
These pass the existing per-run and independent-repeat checks; this does not
establish absolute calibration accuracy. No acceptance threshold was changed.

## Comparison Across Positions

All values below assume ratio=2, inverted=0 and minimum-inductance d axis.
Offsets are unwrapped onto a continuous branch for comparison only.

| Pose | Raw encoder, mechanical deg (approx.) | Mean offset, electrical deg | Repeat range, electrical deg |
| --- | ---: | ---: | ---: |
| 1 | 307.603 | 350.265256 | 0.787058 |
| 2 | 286.589 | 357.958102 | 0.173525 |
| 3 | 263.414 | 360.632495 | 1.312227 |

Pose 3 differs from pose 2 by 2.674393 electrical degrees and from pose 1 by
10.367238 electrical degrees. A constant offset is not independently validated.
Do not average all positions into a motor configuration or infer a fractional
pole-pair count from this small sweep. Possible causes include encoder/magnet
geometry or mounting, angle-dependent saliency, measurement bias and an
incorrect ratio/convention. These measurements do not identify the cause.

## Recovery and Final Readback

All three acquisitions reported completion, no faults, zero current and exact
baseline restoration. HFI plotting was disabled after each acquisition.
Final independent read: phase/input/Id/Iq currents zero, duty zero, ERPM zero,
bus 25.0 V, MOS temperature 27.1 C, fault 0, encoder 263.430176 deg.
Active offset remains 267.52764892578125 deg.
Application remains disabled in RAM with 300 ms watchdog and zero timeout brake;
a power cycle can re-enable the saved external control application.
The motor configuration matched the previous pose's baseline exactly on entry.
The fixture remains locked in software.

Raw measurements: `logs/locked-hfi-pose3-20260912-01` through `-03`.
Preflight backup: `logs/locked-pose3-preflight-20260912-01`.
The adjacent `offset-result.json` contains absolute source-report paths.

## Next Control Measurement

Return near the first pose with power OFF: approximately 44 mechanical degrees
counterclockwise viewed from the front, then securely relock. Target raw encoder
position is approximately 307.60 deg; verify the actual position by telemetry.
Keep the board and magnet mountings unchanged relative to stator and rotor.
Repeat the bounded acquisition to test return-to-pose reproducibility before
choosing between further angular mapping and investigation of drift/mounting.
No excitation until the user confirms readiness again.
