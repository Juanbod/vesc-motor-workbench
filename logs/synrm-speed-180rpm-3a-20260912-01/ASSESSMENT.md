# Two bounded speed increases, 2026-09-12

The user requested faster progression toward high/maximum speed and authorized
up to 60 A. Two physical speed-increase trials were executed at the already
qualified 3 A ceiling. No command above 3 A, fast-current-limit increase,
firmware replacement, active braking or disabled protection was used.

## Physical results

| Quantity | First speed step | Second speed step |
| --- | --- | --- |
| Folder | ../synrm-speed-90rpm-3a-20260912-01 | this folder |
| Current taper starts / zero cutoff | 75 / 90 RPM | 165 / 180 RPM |
| Host mechanical speed guard | 120 RPM | 240 RPM |
| Powered observation budget | 6 s | 8 s |
| Actual powered duration | 5.802619 s | 7.802892 s |
| Net powered travel | 5.651062 turns | 14.379334 turns |
| Peak encoder-derived speed | 85.416961 RPM | 172.592227 RPM |
| Last-second speed range | 79.600464..82.216650 RPM | 168.133875..170.186319 RPM |
| Last-second arithmetic mean | 80.693414 RPM | 169.175283 RPM |
| Maximum current command | 3 A | 3 A |
| Final current command | 1.840654 A | 2.164686 A |
| Peak sampled sqrt(Id^2+Iq^2) | 3.075988 A | 3.104851 A |
| Peak absolute reported duty | 0.025 | 0.025 |
| Configured maximum duty | 0.1 | 0.1 |
| Input energy from sampled telemetry | 3.398927 J | 5.957398 J |
| Sampled Id/Iq squared-current integral | 27.968730 A2s | 51.657169 A2s |
| Largest powered sample latency | 1.4493 ms | 1.3670 ms |
| Net coast displacement | 848.474128 deg | 2841.394048 deg |
| Controller faults / experiment errors | none | none |
| Result | bounded_speed_increase_observed | bounded_speed_increase_observed |

Both tests stopped normally at the host time boundary and passed their specified
minimum speed/travel/current-tracking criteria. The 90/180 RPM values are
positive-current cutoff thresholds, not speed setpoints tracked by a tuned PI
speed loop. The respective final-speed qualification thresholds were 60/120 RPM.

No voltage ceiling is apparent within these samples: measured currents tracked
their targets and absolute reported duty stayed below the configured 0.1 limit.
This is a telemetry-based inference, not direct Vd/Vq measurement or a prediction
of available voltage at much higher speed. Reported current-vector norm is not
DC input current or an independently captured phase-current peak.

## Changes and protection

The controller candidates retain the same provisional offset, zero-PM-flux MTPA,
current gains, inductance model, 3 A motor-current cap, 5 A fast current threshold,
2 A input limit, 0.1 duty cap and encoder-source policy as the earlier rotation.
Only the controller electrical-speed limits changed: +/-240 ERPM for the first
step and +/-480 ERPM for the second, using the reviewed two-pole-pair ratio.

The host adds a one-second rise to the 3 A ceiling, speed-dependent positive
current taper, and zero-current cutoff. The first step preserves the 100 ms
telemetry-gap limit. The second tightens it to 50 ms; at 240 mechanical RPM,
the maximum permitted interval spans 72 mechanical degrees, below the 180-degree
ambiguity boundary of successive absolute-angle unwrapping. This calculation
assumes the actual speed remains within the reviewed bounds.

Maximum powered durations are 6/8 s, I2t budgets 54/72 A2s and sampled input
energy budgets 18/24 J. The maximum zero-current recovery observation is 8/16 s,
respectively, to account for longer coast. Fresh read-only entry samples,
standstill verification, exact candidate readback, isolated external application,
300 ms zero-brake watchdog, fault, bus and MOS checks remain mandatory.

Zero current does not guarantee a short stopping distance. The second trial
coasted about 7.9 further mechanical turns before final recovery verification.
The host speed guard and firmware current taper are not certified hardware
overspeed protection.

## Final state

Both runs verified zero current and encoder standstill before exact motor
baseline restoration. Each also reopened the serial connection for an independent
25-sample read-only verification.

After the second run: raw encoder angle 85.583496 degrees; motor/input currents,
Id, Iq, duty and reported ERPM all zero; fault code 0; DC bus 24.7 V; MOS 26.4 C.
Winding-temperature telemetry remains invalid. External application remains
isolated in RAM. Active encoder offset is restored to 267.527648926 degrees.

Baseline SHA256:
`41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`

First candidate SHA256:
`0bb40772d83d809e3cb66c1811af6f3696ec6f09f41aa2362f617894078b5ceb`

Second candidate SHA256:
`6853eb118ce176993e9bd407ca32a7dae1a3fa1068527cf89f9b5a8d7f3164d9`

## Limits of the conclusion

These runs do not find maximum motor speed, validate a 60 A command, demonstrate
loaded torque, calibrate the global offset, or qualify high-speed mechanical
integrity. The old KV rating does not establish the allowable speed of the
modified four-segment rotor and its attachments. A mechanically justified RPM
ceiling is needed before an actual maximum-speed search.

The candidate offset 1.020427465 degrees remains a test hypothesis. Encoder source
selection is inferred from exact configuration and reviewed reference firmware,
not directly measured through a live source flag or firmware-binary attestation.

Software verification: 191 tests ran, 188 passed and 3 NumPy-dependent tests were
skipped. Added coverage verifies both speed steps, their exact current-cap
preservation, strict predecessor evidence, speed/latency/time/energy limits,
zero-current cutoff, simulated coast recovery and rejection of an unreviewed
third speed step. No further physical run was started after these two trials.
