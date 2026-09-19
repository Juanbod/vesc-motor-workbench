# HFI amplitude check, locked rotor, 2026-09-12

## Result

Reducing measurement duty from 0.100 to 0.050 made the stock HFI angle
unusable in all three acquisitions at this pose. Returning to 0.100 produced
a qualified single-pose estimate consistent with the preceding 0.100 series.
This demonstrates amplitude-dependent measurement quality, NOT a calibrated
angle-versus-voltage correction, saturation curve, or absolute offset accuracy.
No new offset, inductance or correction was applied.

## Sequence and evidence

All measurements used plot mode 1, PLL gains zero during acquisition, the same
protective limits, ratio 2, non-inverted encoder, and minimum-L d-axis convention.
The rotor remained mechanically locked. No rotation commands were sent.
Cooldown between acquisitions was at least 8 seconds.

| Run | Duty | Raw mechanical deg | Concentration | Block error, electrical deg | Result |
| --- | --- | --- | --- | --- | --- |
| Lower voltage 01 | 0.050 | 207.199633 | 0.161592 | 61.855913 | Rejected |
| Lower voltage 02 | 0.050 | 207.188331 | 0.149643 | 73.162061 | Rejected |
| Lower voltage 03 | 0.050 | 207.196656 | 0.159560 | 72.189795 | Rejected |
| Return control 01 | 0.100 | 207.190265 | 0.980210 | 1.601511 | Single-pose candidate |

Acceptance thresholds were unchanged: concentration >= 0.9 and block error <= 3
electrical degrees. Rejected runs have `candidate: null`; their apparent mean
angles must not be treated as offsets or averaged into a calibration.

At 0.050 the firmware reported inductances of 40.86, 38.79 and 39.31 uH,
Lq-Ld of 28.12, 20.48 and 23.80 uH, and measurement currents of 0.73, 0.73,
and 0.74 A. These are unvalidated diagnostics, not replacement motor parameters.
At 0.100 the control reported 23.30 uH, Lq-Ld 8.79 uH and 1.93 A.
Reported measurement current is not battery current or an independently sampled
instantaneous phase-current peak.

The return-control offset is 0.903828448 electrical degrees modulo 180, compared
with 1.020427459 in the previous three-run series: difference -0.116599011 deg.
The return check is ONE acquisition, not another independently qualified
three-run mean. Alternative 180-degree branches remain unresolved.

Maximum encoder span within a run was 0.219712 mechanical degrees. Each of the
four new acquisitions verified no controller fault, zero current after the
measurement, plotting disabled, app unchanged and exact baseline restoration.
The three unsuccessful exit statuses denote rejected measurement quality, not
failed recovery or controller faults. No rejected records were overwritten.

## Source files

- Previous 0.100 series: `profiles/synrm-as5048a-offset-check-20260912/offset-result.json`
- `logs/locked-hfi-amplitude-005-20260912-01/result.json`
- `logs/locked-hfi-amplitude-005-20260912-02/result.json`
- `logs/locked-hfi-amplitude-005-20260912-03/result.json`
- `logs/locked-hfi-amplitude-010-control-20260912-01/result.json`
- Independent final readback: `logs/locked-hfi-amplitude-20260912-final-readback.json`

Baseline SHA256: `41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`.
Final active offset remains 267.527648926 deg. Read-only verification collected
25 quiet samples; final motor/input current, Id, Iq, duty and reported ERPM were
zero, fault code 0, bus 24.9 V, MOS temperature 26.3 C. Motor-temperature reading
was invalid. External control remains isolated in RAM; recheck after power cycling.

## Implications

Do not reduce excitation further to seek a more precise offset with this method.
Do not increase excitation beyond the reviewed limits based on these results.
The approximately +1 deg estimate is repeatable locally at duty 0.100 but is not
a global calibration. The earlier frozen periodic model failed its independent
check and remains ineligible for application.

Before more offset fitting, investigate the measurement path and its assumptions:
current sampling and offsets, inverter nonlinearity at low excitation, and the
mapping from HFI saliency axis to the torque-producing axis. These are hypotheses,
not diagnosed causes. Retain the locked fixture state; any later rotation test
requires the user to confirm physical removal of the fixture.
