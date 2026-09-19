# Second locked-pose physical measurement

2026-09-12. Three real stock `measure_ind 0.100` acquisitions using DFT plot
mode 1, the existing protective limits and zero-speed PLL convention.
The user confirmed repositioning and relocking. No rotation commands were sent.

## Results

| Acquisition | Raw encoder, mechanical deg | Minimum-L axis, electrical deg | Offset branch, electrical deg |
| --- | ---: | ---: | ---: |
| pose2-01 | 286.586885 | 35.315070 | 357.858701 |
| pose2-02 | 286.591307 | 35.199236 | 357.983378 |
| pose2-03 | 286.587379 | 35.142532 | 358.032226 |

Mean axial offset: **357.958102 deg**, equivalent axis branch 177.958102 deg.
Across-run range: 0.173525 deg. Evaluated DFT frames: 213.
Assumptions remain ratio=2, inverted=0 and the firmware's minimum-L d axis.

The first pose produced 350.265256 deg at raw encoder approximately 307.603 deg.
The second pose differs by **7.692846 electrical degrees**. This exceeds the
observed within-pose repeatability and does NOT validate a constant offset.
Neither result is an independently established global encoder calibration.
Do not apply their average or change the ratio based on these two positions.
Possible causes still to distinguish include angle-dependent magnetic/encoder
error, non-sinusoidal saliency, measurement bias and incorrect ratio/convention.

## Controller State After Testing

- All three commands completed, with no controller faults.
- HFI reporting disabled; zero current verified after each acquisition.
- Exact fresh motor baseline restored after every acquisition.
- Independent final read: motor/Id/Iq/input current, duty and ERPM all zero;
  bus 25.0 V, MOS temperature 27.0 C, fault 0.
- Active offset remains 267.52764892578125 deg. No candidate was applied.
- External application control remains disabled in RAM; watchdog 300 ms,
  timeout brake current zero. A power cycle restores the saved application.
- Rotor fixture remains LOCKED in the software interlock.

Fresh baseline and original application are in
`logs/locked-pose2-preflight-20260912-01`. Only current/voltage ADC calibration
fields differed from the previous baseline after power cycling; these fresh
values were preserved. Application isolation used command 149 (no flash store)
with a one-use exact-payload permit and encoder standstill verification.

Raw reports and telemetry: `logs/locked-hfi-pose2-20260912-01` through `-03`.
Machine-readable aggregate and absolute source paths: `offset-result.json`.
Software verification: 120 unittest tests passed.

## Next Step

With power OFF, reposition approximately another 25 mechanical degrees clockwise
viewed from the front, and securely relock. Keep the encoder board and its magnet
mounting unchanged relative to their intended stator/rotor attachments. Read the
actual encoder displacement rather than treating the requested angle as exact.
Acquire a third pose before selecting any final offset, ratio or inversion.
