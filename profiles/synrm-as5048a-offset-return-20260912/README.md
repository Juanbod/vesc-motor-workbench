# Near-return locked-rotor control measurement

2026-09-12. The user confirmed repositioning and relocking. Three real stock
`measure_ind 0.100` acquisitions used unchanged protective limits, DFT mode 1
and the zero-speed PLL convention. No rotation commands were issued.

| Run | Raw encoder, mechanical deg | Minimum-L axis, electrical deg | Offset branch, electrical deg |
| --- | ---: | ---: | ---: |
| return-01 | 309.119874 | 86.977514 | 351.262235 |
| return-02 | 309.100456 | 87.447086 | 350.753827 |
| return-03 | 309.090836 | 86.918617 | 351.263056 |

Mean axial offset: 351.093041 deg, equivalent axis branch 171.093041 deg.
Across-run range: 0.509229 deg. Evaluated DFT frames: 215.
The first series gave 350.265256 deg at approximately 307.603 mechanical deg.
The return was approximate: raw encoder approximately 309.104 deg, about 1.50
mechanical degrees away. Offset difference from the first series: +0.827785
electrical deg. This supports near-pose reproducibility but is not an exact
same-pose drift test and cannot rule out mounting or measurement errors.

## Combined Interpretation

| Pose | Raw encoder (approx.) | Mean offset, continuous branch |
| --- | ---: | ---: |
| First | 307.603 | 350.265256 |
| Second | 286.589 | 357.958102 |
| Third | 263.414 | 360.632495 |
| Near return | 309.104 | 351.093041 |

All offsets assume ratio=2, inverted=0 and minimum-L d axis. They are NOT a
validated angle correction table. The near-return result is much closer to the
first pose than to the third, supporting a position-related component rather
than simple cumulative drift. The physical cause remains unresolved. Encoder
geometry, saliency harmonics, measurement bias and ratio/convention still need
to be distinguished. No candidate or cross-pose average was applied.

## Final State

- Three completed physical acquisitions, all fault-free.
- Zero current and exact baseline restoration verified after each acquisition.
- HFI plotting disabled after every run.
- Independent final read: motor/input/Id/Iq currents, duty and ERPM all zero;
  bus 25.0 V, MOS temperature 27.1 C, fault 0, raw encoder 309.111328 deg.
- Active offset remains 267.52764892578125 deg.
- Application disabled in RAM; watchdog 300 ms, timeout brake current zero.
  Saved external control can return after a power cycle.
- Software fixture state remains locked.

Raw logs: `logs/locked-hfi-return-20260912-01` through `-03`.
Preflight backup: `logs/locked-return-preflight-20260912-01`.
Absolute source paths and statistics are in the adjacent `offset-result.json`.

## Next Distinct Pose

Extend the angular span before evaluating ratio and direction: with power OFF,
rotate approximately 80 mechanical degrees clockwise viewed from the front from
this near-return position, then securely relock. Expected raw encoder is around
229 deg, approximately 79 deg from the original position. Do not move the magnet
or board relative to their intended rotor/stator attachments. Use the measured
angle, not the requested rotation, in subsequent analysis. Await user readiness
before any further excitation. No change in current limits is needed.
