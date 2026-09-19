# Speed progression to 431 RPM at 3 A, 2026-09-12

The user reports that the modified rotor and its attachments tolerate at least
the original motor's speed, with additional margin. This is recorded as the
user's mechanical assessment, not an independently verified RPM rating. Three
physical acquisitions and one zero-current timing probe were performed in this
turn. No current above 3 A, firmware update, active brake or disabled protection
was used.

## Physical acquisitions

| Acquisition | Powered time | Peak/final speed | Outcome |
| --- | --- | --- | --- |
| ../synrm-speed-360rpm-3a-20260912-01 | 11.818914 s | 314.774606 RPM | Qualified bounded increase |
| ../synrm-speed-540rpm-3a-20260912-01 | Last powered summary 10.718803 s | About 299 RPM | Host supervisor input guard; recovered |
| This folder | 23.804197 s | Peak 431.133047 / final 430.983449 RPM | Qualified bounded increase |

The successful final run contains 3589 powered observations. Net powered travel
was 40655.939942 mechanical degrees, or 112.933167 turns. Maximum commanded
current was 3 A and the command remained at 3 A at the end. The peak sampled
sqrt(Id^2+Iq^2) was 3.255180 A, below the 3.6 A observation guard. This current
norm is not DC input current or an independently measured phase-current peak.

The last-second speed range was 423.942058..431.133047 RPM, mean 427.626730 RPM.
Across the final 3.998026 s, speed rose from 404.964418 to 430.983449 RPM, an
endpoint slope of about 6.51 RPM/s. The rotor was still accelerating when the
time budget ended; neither steady-state maximum speed nor the 540 RPM cutoff
was reached. The stage qualifies a bounded increase above 420 RPM, not attainment
of a 540 RPM speed setpoint.

Absolute reported duty peaked at 0.025 versus the configured 0.1 limit. Measured
Id/Iq tracked the requested targets within the specified guard. These observations
do not show voltage saturation in this interval, but are not direct Vd/Vq
measurements or proof of voltage headroom at arbitrary higher speed.

Sampled input energy was 23.040311 J; sampled squared-current integral was
208.349920 A2s, below the respective 72 J / 216 A2s budgets. Maximum GET_VALUES
latency in the successful run was 2.6896 ms. MOS temperature reached 26.5 C;
winding-temperature telemetry remains invalid.

## Timing stop and software change

The first 540-stage attempt stopped with `Invalid rotation supervisor input`,
without controller faults. Its last encoder sample was 298.932509 RPM. The next
stopping sample arrived 19.4318 ms after that last powered sample. Source review
and the valid current/speed/elapsed inputs identify the command-interval guard
as the consistent explanation, but the exact rejected interval was not recorded
by that version and must not be invented.

The runner formerly reopened observations.jsonl on every powered sample. It now
keeps the observation stream open and flushes each record, as already done with
the raw sample stream. It also records the latest supervisor inputs and emits
an explicit command-interval error with the measured duration. No timing guard,
current bound or speed bound was relaxed. Historical failed records were not
rewritten or marked successful.

The dedicated zero-current timing probe in
`../synrm-zero-current-timing-20260912-01` ran for 15 s, recording 2342 samples.
It sent only zero-current commands and made no configuration writes. Maximum
command interval was 10.5884 ms, with no intervals over 20 ms; maximum value-read
latency was 4.1863 ms. It verified zero current and unchanged baseline afterward.

Only after the software tests and this timing probe was the physical 540-stage
test repeated. The repeat completed without timing violations. This is evidence
that the revised acquisition worked during the measured interval, not a guarantee
of real-time Windows scheduling or proof of a single causal source of all jitter.

## Guards and recovery

The 360 stage retains 3 A current / 5 A fast trip, 0.1 duty and 2 A input caps,
with a 480 mechanical RPM guard, 12 s powered budget, 40 ms maximum gap, and
24 s recovery observation. The 540 stage retains those current and duty caps,
uses a 720 mechanical RPM guard, a 24 s powered budget, 20 ms maximum gap and
32 s recovery observation. Current taper starts at 525 RPM and cuts to zero at
540 RPM, but it was not reached in these actual 540-stage attempts.

The requested sampling pause is 5 ms in the faster stage; actual cycle time also
includes serial I/O and logging. At the 720 RPM guard, 20 ms spans 86.4 mechanical
degrees, below the 180-degree absolute-angle unwrap ambiguity. This statement
assumes speed stays within the reviewed operating bounds; it is not a certified
hardware overspeed guarantee.

All three physical acquisitions recovered to zero current and encoder standstill,
restored the exact motor baseline and passed a separate read-only final check.
In the successful final run, net coast displacement was 12558.186024 degrees
(about 34.9 turns). Zero current is not an immediate mechanical stop.

Final independent readback: raw angle 320.844736 degrees; motor/input currents,
Id/Iq, duty and reported ERPM all zero; fault 0; DC bus 24.7 V; MOS 26.4 C.
External application remains isolated in RAM. Active encoder offset is restored
to 267.527648926 degrees, not the temporary candidate offset.

Baseline SHA256:
`41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`

360-stage candidate SHA256:
`33898af53b7673d146916f8057fa60ce966c6f4fd65eed4097487cfed5bdcf0f`

540-stage candidate SHA256, identical for both attempts:
`39c87e0ec2288416257196ce78063e6fbe94cfe8173e5136cbf4b56a4d7616b7`

## Limits and next decision

The 1.020427465-degree candidate offset remains a hypothesis, not a global
calibration. Encoder-source selection remains an inference from the reviewed
reference firmware and exact configuration, not a directly sampled source flag
or binary attestation. No torque sensor or valid winding-temperature sensor is
available. These runs do not establish all-angle loaded startup or maximum speed.

The next useful comparison is a separately bounded modest current increase with
the same speed ceiling, measuring acceleration rather than raising current and
speed limits together. No such higher-current trial has been run yet, and the
user's earlier 60 A authorization has not been used as an operating target.

Software verification after the logging change: 193 tests ran, 190 passed,
3 NumPy-dependent tests skipped. The zero-current timing probe and physical
acquisitions above are additional real-hardware checks, not simulated tests.
