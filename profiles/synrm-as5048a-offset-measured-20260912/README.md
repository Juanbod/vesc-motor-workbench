# Measured Encoder Offset: Single Locked Pose

Preferred candidate: **350.2653 electrical degrees**.
Equivalent saliency-axis alternative: **170.2653 electrical degrees**.

This is a measured result, NOT a simulation, but it is NOT yet a globally
validated encoder calibration. It assumes the current direct-drive encoder
ratio of 2 and non-inverted direction, and uses the minimum-inductance d-axis
convention appropriate to the positive configured VESC Lq-Ld difference.

Three independent physical HFI acquisitions produced:

| Run | Preferred offset, electrical deg | Maximum within-run block error |
| --- | ---: | ---: |
| locked-hfi-offset-20260912-05 | 350.7302 | 0.6496 |
| locked-hfi-offset-20260912-06 | 350.1225 | 0.8062 |
| locked-hfi-offset-20260912-07 | 349.9431 | 1.3012 |

216 evaluated on-controller DFT frames were used. The independent-run range is
0.7871 electrical degrees; maximum deviation from their circular mean is
0.4649 degrees. These quantify repeatability at this pose, not absolute accuracy.
The raw encoder position was approximately 307.60 mechanical degrees.

The preferred branch is 7.2624 electrical degrees below the earlier working
experimental offset of 357.52765 degrees. The 180-degree alternative cannot be
distinguished by an unpolarized inductance-axis measurement alone.

## Not Applied

No new offset or complete motor profile was uploaded. Each acquisition used
temporary-in-purpose but flash-written protective motor settings followed by
exact restoration. The final independent read confirmed the original motor
configuration byte-for-byte, active offset 267.52765 degrees, application output
disabled in RAM, zero motor/input current, zero duty/ERPM and no controller fault.
The rotor remains reported mechanically locked.

`offset-result.json` contains machine-readable results and absolute paths to the
three original reports. Those directories preserve raw packet payloads, decoded
plots, telemetry, original/protective binary configurations and terminal output.

## Method

The successful runs used the stock `measure_ind 0.100` command, approximately
0.41 seconds each, and HFI DFT plot mode 1. At about 25.1 V bus this commands
approximately 1.45 V HFI excitation. Protective current settings remained
+/-2 A phase, 3 A fast absolute-current trip, 1 A input and 0.1 maximum duty.
The terminal's approximately 2.01 A result is the mean sampled pulse current
difference in this firmware, NOT steady DC battery current or a measured peak.

The plotted graph 0 is used, not the graph misleadingly labelled `Phase bin2`.
For the reviewed 6.02 implementation, the graph-0 DFT angle identifies the
minimum-inductance stator axis modulo 180 degrees. The PLL gains were set to zero
only during acquisition, after verifying zero speed, and every acquisition
sample checked that reported speed remained zero. This removes the firmware's
speed-dependent HFI angle correction. Actual standstill was checked independently
using the encoder. Both PLL gains were restored afterward.

Low-duty attempts 01-04 were not accepted as calibration data. Their weak/raw
responses did not pass quality tests. Attempt 04 also exposed signed-radian
angle handling, which was corrected and tested before runs 05-07; the original
attempt-04 report is preserved and is not part of this result.

## Required Independent Check

With power disconnected, move the rotor to a different mechanical position and
refit the fixture. Then repeat the same bounded measurement using the actual
new encoder angle. Multiple distinct poses are required to verify encoder ratio,
inversion and the consistency of this offset around the rotor. Suggested
relative pose changes for a fuller check are about 17, 43 and 79 mechanical
degrees; exact placement is not required because the encoder records the angle.

Only after the independent pose check should a candidate be staged for a
separate low-current free-rotor startup test. Removing the fixture and enabling
ordinary rotation require a fresh explicit user confirmation.
