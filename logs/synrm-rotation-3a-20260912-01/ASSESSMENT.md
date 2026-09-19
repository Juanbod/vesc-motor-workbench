# Bounded rotation at 3 A, 2026-09-12

One real free-rotor test was executed after the user requested continuation.
No automatic repeat, current escalation above 3 A, firmware replacement or
active braking was performed. The candidate motor bytes were identical to the
previous 3 A extension. Only the host experiment and positive-current taper changed.

## Method

- Maximum command 3 A, rise/fall slew 3 A/s.
- Above 20 mechanical RPM, the requested-current ceiling tapers toward zero
  at 35 RPM. The zero-current cutoff at 35 RPM overrides the slew limiter.
- Encoder-derived hard speed guard 60 RPM; host powered loop under 3.8 s
  plus the final bounded sample, with a 4 s total powered budget.
- Existing current, duty, bus, MOS, telemetry freshness, 36 A2s and 12 J
  guards remain. External application isolated, watchdog 300 ms with zero brake.
- Powered travel envelope 1440 degrees; full event 4320 degrees including
  at most 8 s of recovery observation. These are monitored limits, not a
  mechanical guarantee of stopping distance. Zero current allows coast.
- Completion requires at least one net mechanical turn, current tracking for
  at least 3 s, and final encoder speed at least 5 RPM, without guard failures.

The prior run was accepted only after reviewing its raw 90-degree trigger and
independent successful recovery. Its original failed travel qualification was
not changed. The new start was checked against its final quiet encoder reading.

## Physical results

| Quantity | Result |
| --- | --- |
| Powered observations | 171 |
| Powered time | 3.802533 s |
| Powered net travel | 472.829592 degrees, 1.313416 turns |
| Peak encoder-derived speed | 33.719156 RPM |
| Last-second speed range | 26.105409 to 28.084741 RPM |
| Last-second arithmetic mean speed | 26.861208 RPM |
| Maximum commanded current | 3.000 A |
| Final commanded current | 1.418820 A |
| Peak measured sqrt(Id^2 + Iq^2) | 3.034485 A |
| Final measured Id / Iq | -1.01 / +0.97 A |
| Sampled input energy | 1.555749 J |
| Sampled I2t | 12.311188 A2s |
| Largest powered sample latency | 0.002502 s |
| Subsequent net travel during runner recovery | 144.184565 degrees |
| Full-event net travel | 617.014157 degrees |
| Full-event peak absolute travel | 619.211422 degrees |
| Controller fault code | 0 |
| Result | bounded_rotation_observed, ok=true |

The torque command was positive; direction here means increasing unwrapped
encoder angle, not an independently observed clockwise/counterclockwise direction.
Reported signed current_motor and duty are preserved in raw logs; they are not
used as a substitute for encoder direction or measured Id/Iq magnitude.

The speed ceiling is a positive-current supervisor, not a tuned speed PID. The
last-second range is evidence for this short interval only, not a long-duration
speed-accuracy qualification. One start at this angle does not prove guaranteed
starting from arbitrary positions or loaded torque.

## Recovery and independent verification

Zero-current stop, encoder standstill and exact motor-baseline restoration passed.
An independent read-only acquisition collected 25 quiet samples and checked
unchanged motor and app configurations. Final motor/input currents, Id/Iq, duty
and reported ERPM were zero; fault code 0, bus 24.8 V, MOS 26.4 C, encoder
13.315430 degrees. External application remains isolated in RAM.

Active baseline offset: 267.527648926 degrees. The candidate's temporary
1.020427465-degree offset was NOT left active and is NOT globally calibrated.
Winding-temperature telemetry remains invalid.

Baseline SHA256:
`41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`

Candidate SHA256:
`ae009dae1cd17e4088342e3911103b33d5dcf0774a90181dd72d55284ddac9d1`

Encoder source selection remains an inference from the reviewed reference
firmware and exact read-back configuration, not a directly observed source flag
or attestation of the board's firmware binary. No observer-transition or
maximum-speed experiment was performed.

## Software verification and next experiment

176 software tests ran: 173 passed, 3 NumPy-dependent tests skipped. Tests include
rotation across encoder wrap, current taper, priority zero-current cutoff,
overspeed, disconnect, stall, guard retention, and refusal of unrelated prior
failures. These simulated tests are separate from the physical acquisition above.

The next useful experiment is startup repeatability from distinct recorded rotor
angles at the same 3 A ceiling, with a reviewed start-pose reference and the same
speed/time/energy guards. Do not infer that more current is needed from this run.
The current runner intentionally does not accept a rotation run as the reference
for an automatic repeat; a new explicit repeatability stage must be reviewed.
