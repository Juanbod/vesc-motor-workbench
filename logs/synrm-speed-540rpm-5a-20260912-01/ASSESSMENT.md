# First 5 A comparison, 2026-09-12

One physical acquisition was performed. The motor reached a peak of
542.210038 mechanical RPM from the encoder's 120 ms speed window. The run
ended after 5.077384 s rather than its 24 s budget. It is NOT qualified:
result.json retains ok=false, a current-tracking error and a coast guard flag.
No retry, larger current, higher speed limit or disabled protection followed.

## Acceleration

| Encoder speed first reached | Time from command-ramp start |
| --- | --- |
| 100 RPM | 1.873806 s |
| 200 RPM | 2.489607 s |
| 300 RPM | 3.165561 s |
| 400 RPM | 3.909776 s |
| 431 RPM | 4.154667 s |
| 500 RPM | 4.716933 s |
| 540 RPM | 5.070928 s |

The preceding 3 A run reached about 431 RPM at the end of its 23.8 s budget.
The 5 A run therefore shows materially faster acceleration, but it is a single
comparison from a different starting angle, not a controlled torque measurement
or a repeatable maximum-speed result.

There are 742 powered observations. Command current reached 5 A; sampled
sqrt(Id^2+Iq^2) peaked at 5.298302 A, below its 6 A observation guard. This norm
is neither DC input current nor an independent phase-current peak measurement.
Powered travel was 6903.522940 degrees (19.176453 turns), input energy
8.596546 J and current integral 98.660043 A2s. Peak duty was 0.028 with a
configured 0.1 cap. No ESC fault was reported. Maximum MOS temperature was
26.4 C; winding-temperature data remain invalid.

## Why the test stopped

The 525 RPM taper threshold was reached at 4.934882 s. Only about 0.136 s
elapsed before the 540 RPM cutoff. At the unchanged 3 A/s downward slew,
command current was still 4.591343 A when the next supervisor decision set
it directly to zero. The 15 RPM taper window is too narrow for this observed
acceleration to bring current smoothly to zero.

The first observation after that zero command reported Id=-0.71 A and
Iq=+0.71 A, outside the steady-target zero-current tolerance. The next
stopping observation, 0.729 ms later in host timestamps, reported both zero.
This is consistent with a switching/telemetry-averaging transient rather than
sustained failure to remove current, but the exact mechanism is not established.
The existing guard was honored; its error was not suppressed or rewritten.

During zero-current coast, one adjacent-sample speed estimate was
961.070886 RPM, above the 720 RPM guard. Raw angles changed from 2.702636
to 37.617188 degrees over 6.0548 ms of response timestamps. However, the
preceding GET_VALUES response took 5.4433 ms, versus 0.5629 ms for the next
response. The telemetry contains host receive times, not encoder acquisition
timestamps. This variable latency is consistent with a distorted adjacent-sample
speed estimate. Controller-reported ERPM stayed near 1077, and the surrounding
angle stream was consistent with approximately 540 RPM. These observations
do not prove either a true 961 RPM event or its absence. The guard flag remains.

## Recovery and configuration

Zero current and encoder standstill were verified before exact baseline
restoration. An independent reopened COM10 readback then confirmed:

- Motor current, input current, Id, Iq, duty and reported ERPM all zero.
- Fault code 0; bus 24.7 V; MOS 26.3 C; raw encoder angle 285.183104 degrees.
- Baseline restored exactly; external application isolated in RAM.

Net coast travel was 17540.112292 degrees (48.722534 turns). Zero current
is not an immediate mechanical stop. No active braking was commanded.

Baseline SHA256:
`41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`

Candidate SHA256:
`92e5c10d635744bfe7170225c386024ed7905fef57c7c2fcb9ee4a011aa0a368`

Only l_current_max, l_current_min and l_abs_current_max differ from the prior
540 RPM / 3 A candidate: +5 A, -5 A and 8 A respectively. The sampled-current
guard is 6 A and integral budget 600 A2s. Input limit remains 2 A, energy budget
72 J, powered budget 24 s, recovery observation 32 s, taper/cutoff 525/540 RPM,
speed guard 720 RPM, maximum command/sample gap 20 ms and requested pause 5 ms.
The ramp remains 3 A/s, taking at least 1.67 s to reach 5 A.

Offset 1.020427465 degrees remains provisional, not globally calibrated.
The encoder-selection evidence remains reference-firmware/configuration inference,
not a directly measured source flag or firmware-binary attestation.

## Software and next work

Added the explicit speed_540rpm_5a stage requiring a qualified speed_540rpm_3a
predecessor. The current supervisor now uses the reviewed stage current ceiling
instead of hardcoding 3 A; old stages retain their previous behavior. Ramp
metadata reflects the longer 5 A rise. No arbitrary-current stage was added.

Verification: 197 software tests, 194 passed and 3 NumPy-dependent skips.
Coverage includes unchanged speed/input/duty/latency protections, 5 A targets,
the qualified predecessor chain, safe recovery for a stalled simulated rotor,
a lower-gain passing plant and a high-gain plant that oscillates and fails the
completion criterion. Simulation is not a physical stability qualification.

Before repeating: review earlier/wider current taper or a bounded speed
controller, explicitly distinguish cutoff settling from sustained current
mismatch, and handle encoder acquisition-time uncertainty without simply
disabling the coast guard. Validate these changes offline first. Keep the
present speed envelope for the next comparison; this failed run must not be
used as a successful predecessor for escalation.
