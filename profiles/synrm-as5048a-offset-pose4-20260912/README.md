# Fourth distinct locked-pose measurement and ratio comparison

2026-09-12. User confirmed the new locked position. Three physical stock
`measure_ind 0.100` acquisitions used the existing low-current limits, DFT plot
mode 1 and zero-speed PLL convention. No rotation commands were sent.

| Run | Raw encoder, mechanical deg | Minimum-L axis, electrical deg | Offset branch, electrical deg |
| --- | ---: | ---: | ---: |
| pose4-01 | 212.801054 | 74.278366 | 351.323743 |
| pose4-02 | 212.789746 | 75.039830 | 350.539663 |
| pose4-03 | 212.774224 | 75.111221 | 350.437226 |

Mean axial offset: 350.766869 deg; equivalent branch 170.766869 deg.
Repeat range: 0.886517 electrical deg; 205 evaluated DFT frames.
Actual displacement from the near-return pose was about -96.32 mechanical deg,
not the requested -80 deg. Analysis uses actual encoder readings throughout.

## Across-Pose Diagnostic

| Distinct pose | Raw encoder (approx.) | Mean offset, continuous branch |
| --- | ---: | ---: |
| 1 | 307.603 | 350.265256 |
| 2 | 286.589 | 357.958102 |
| 3 | 263.414 | 360.632495 |
| 4 | 212.788 | 350.766869 |

The near-return control at 309.104 deg gave 351.093041 deg. It is deliberately
excluded from the equal-pose fit to avoid overweighting the first region.

Enumerated integer ratios 1..8 and both encoder directions. For each pose,
reconstructed the measured minimum-L axis modulo 180 from its original
ratio=2/inverted=0 aggregate and mean raw encoder angle. Each hypothesis uses
`offset = (sign * ratio * raw - measured_axis) mod 180`, an axial circular mean
over the four distinct positions, and RMS/max axial residuals. Equal weight per
position; not per frame. This is a diagnostic ranking, NOT a write-ready result.

| Ranked hypothesis | Inverted | RMS residual, electrical deg | Max residual, electrical deg |
| --- | --- | ---: | ---: |
| ratio 2 | false | 4.493801 | 5.729140 |
| ratio 6 | true | 17.222970 | 30.574449 |
| ratio 5 | true | 20.591421 | 30.972179 |
| ratio 4 | false | 30.743066 | 53.155361 |
| ratio 8 | true | 32.910256 | 49.139370 |

Ratio 2, noninverted is clearly the best of the tested hypotheses, but fails the
existing 3-degree maximum-error and 0.99 axial-resultant criteria (resultant
0.987727). Its fitted offset 354.903354 deg is a diagnostic compromise only;
DO NOT apply it or claim a validated constant offset. Across-pose range is
10.367238 electrical deg. Tests have not identified whether this originates
from encoder geometry, saliency harmonics, HFI bias or another systematic error.
The finite hypothesis search and limited angular coverage are not a proof of
ratio/direction under arbitrary errors.

## Readback and Safety State

All three measurements completed without faults; zero current and exact baseline
restoration were verified after each run. HFI plotting was disabled. Fresh ADC
current/voltage calibration values after restart were preserved; no other motor
fields changed on entry. App control was temporarily isolated in RAM.

Independent final read: phase/input/Id/Iq currents, duty and ERPM all zero;
25.0 V bus, MOS 27.1 C, fault 0, raw encoder 212.761232 deg. Motor bytes match
`logs/locked-pose4-preflight-20260912-01/mcconf-before.bin` exactly.
Active offset remains 267.52764892578125 deg. No candidate applied.
App=0 in RAM, watchdog 300 ms, timeout brake current 0. A power cycle can restore
the saved external application. The software fixture state remains locked.

The read-only `encoder` terminal query returned:
`SPI encoder value: 58835, errors: 0, error rate: 0.000 %`.
The host then timed out waiting for additional replies after the complete
diagnostic had arrived. This was a read-only extra-response timeout, not a fault
or a failure of the prior verified restoration. The diagnostic reports SPI
transport integrity, not magnet strength or angular accuracy.

## Sources and Next Step

Individual telemetry, plot data, commands and recovery flags are in
`logs/locked-hfi-pose4-20260912-01` through `-03`. The adjacent `offset-result.json`
contains aggregate statistics and absolute source paths. Earlier aggregates are
in the sibling offset-measured, offset-pose2, offset-pose3 and offset-return
profile directories for 20260912.

Pause manual repositioning. Keep the rotor fixed until the next test is agreed.
Before applying a global offset, distinguish angle-dependent encoder error from
HFI/saliency bias. Candidate checks include independent magnet/alignment
diagnostics and a reviewed acquisition method that evaluates waveform harmonics
or excitation dependence without increasing the existing protection limits.
No new acquisition mode, larger current or free-rotor command is authorized by
this report. A startup test still requires explicit fixture-removal confirmation.
