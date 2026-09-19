# Locked HFI independent check: 2026-09-12

Diagnostic result only. No encoder offset or correction has been applied.
Rotor remains mechanically locked according to the user's confirmation.

## Physical acquisitions

Three real `measure_ind 0.100` acquisitions, plot mode 1, on COM10.
Sources: `logs/locked-hfi-check-20260912-01/result.json` through `-03/result.json`.
Protective settings and acquisition procedure were unchanged from previous HFI tests.
Each acquisition returned without a fault, verified zero current, disabled plotting,
and restored the exact motor baseline. No rotation command was sent.

| Quantity | Result |
| --- | --- |
| Mean raw encoder position | 207.203425277 mechanical deg |
| Individual offset estimates | 0.379603581, 1.697643020, 0.984045396 electrical deg |
| Axial mean offset | 1.020427459 electrical deg, modulo 180 |
| Alternative branch | 181.020427459 electrical deg |
| Repeat range | 1.318039439 electrical deg |
| Evaluated DFT frames | 206 |
| Maximum encoder span within one run | 0.175776 mechanical deg |
| Firmware-reported inductance | 23.19, 23.29, 23.03 uH |
| Firmware-reported Lq-Ld | 8.48, 9.03, 8.42 uH |
| Firmware-reported measurement current | 1.94, 1.93, 1.95 A |

Firmware measurement current is not battery current or an independently captured
instantaneous phase-current peak. Encoder repeatability does not establish absolute
angle accuracy. The ratio of 2, non-inverted encoder, and minimum-L d-axis convention
remain the analysis assumptions.

## Frozen-model check

The model from `profiles/offset-method-comparison-20260912/comparison.json` was
evaluated without refitting or including this new measurement in training:

`offset = -4.791234316 + 6.178099413*cos(4*theta) + 0.122968034*sin(4*theta)`

Here theta is the raw mechanical angle in degrees; the result is electrical degrees.
Prediction at the new pose: -6.667224190 deg.
Measured minus predicted axial difference: +7.687651649 deg.
This independent point does not support using the proposed periodic correction.
It does not identify the physical cause of the discrepancy.

## Field-alignment comparison

The nearest earlier moved-and-settled field observation was raw 207.836806724 deg,
field 150 deg, inferred minimum-L offset -4.326386552 electrical deg. It belongs
to a sweep that stopped on a tracking error; it is only a local observation.

Actual mechanical separation is 0.633381447 deg, exceeding the existing 0.5 deg
same-pose criterion. Therefore this is NOT a qualified same-pose comparison.
The nearby estimates differ by 5.346814010 electrical deg, but that must not be
reported as an independently measured same-pose method bias. The user's estimated
10 deg repositioning is not the measured displacement from this reference.

## Final state

Independent read-only verification is recorded in
`logs/locked-hfi-check-20260912-final-readback.json` (25 samples).
Baseline SHA256: `41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`.
Active offset remains 267.527648926 deg. Motor and input current, Id, Iq, duty and
reported ERPM were zero; fault code 0, bus 24.9 V, MOS temperature 26.4 C.
Motor temperature -50.2 C is not a credible winding-temperature measurement.
External control remains isolated in RAM; this does not establish isolation after
a power cycle. Recheck before any subsequent excitation.

Next investigation: distinguish HFI measurement/convention bias from actual
position-dependent magnetic response, including excitation dependence at a fixed
locked pose. Do not apply this local offset globally or increase torque based on
this result. Rotation remains prohibited until the fixture is physically removed
and the user confirms that change.
