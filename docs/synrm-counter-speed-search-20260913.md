# Counter-assisted speed trials, 13 September 2026

## Physical results

All four trials ended with zero current, exact baseline rollback and independent
standstill readback. None changed the stored baseline permanently. No autonomous
trial, background process or scheduled retry remains after this session.

| Trial folder under logs/ | Outcome |
| --- | --- |
| synrm-counter-validation-2200-20260913-01 | 39.80 s powered at up to 5 A; old receive-time estimator mean 1819.60 RPM, span 35.33 RPM. Failed old stability/coast timing criteria. Preserved as a failed speed trial. |
| synrm-speed-2200rpm-5a-counter-20260913-01 | Qualified complete counter-assisted trial: 39.80 s, final five-second mean 1820.54 RPM, range 1814.49-1827.72 RPM, slope 0.41 RPM/s. Powered travel 874.43 turns. No powered or coast guard violations. |
| synrm-speed-2700rpm-5a-counter-20260913-01 | Complete 39.80 s acquisition, peak 1914.57 RPM; final-five-second mean 1886.73 RPM, span 60.42 RPM, slope 11.17 RPM/s. Still accelerating with 5 A commanded. Not a stable speed point; no telemetry/coast/fault violations. |
| synrm-speed-2700rpm-6a-counter-20260913-01 | Aborted after 0.508 s at command 1.504 A, before reaching 6 A. Id=-1.02 A, Iq=-0.01 A, travel 0.110 degrees. Current-target tracking guard stopped excitation. This is NOT a six-amp rotation test. |

No motor maximum, rated speed, shaft power, torque, efficiency or continuous-duty
rating has been established. Offset remains provisional and startup at arbitrary
rotor angles is not guaranteed. Winding-temperature telemetry is invalid; MOS
temperature monitoring, finite current/energy/time budgets and watchdog remain.

## Measurement change

The old parser discarded GET_VALUES signed tachometer and absolute tachometer
fields. They are now retained as signed int32 values in every sample. Truncated
base packets are rejected before field access.

Reference firmware commit `f7c2b34e1cff2234cae98be3abf0cd50e249558f`:

- `comm/commands.c` transmits tachometer and absolute tachometer in GET_VALUES.
- `motor/mcpwm_foc.c`, tachometer update near line 3258, counts six sectors per
  electrical revolution from corrected FOC phase, including when undriven.
- `motor/mc_interface.c` applies DIR_MULT to the signed count.

This is not an independent physical tachometer, and the installed board binary
has not been attested against the reference source. Encoder-only configuration
assumptions and the reviewed ratio=2/non-inverted convention remain necessary.

The first trial recorded 41,491 before-current/powered/coast samples. Counter-
assisted angle travel agreed with short-gap encoder unwrapping through
415,473.002944 degrees, including 100,425.761728 degrees of coast. Sparse replay
of the real packets reconstructed the same travel without losing full turns.
This qualifies measurement agreement only, not the failed trial's speed status.

`counter_angle.py` combines 30-mechanical-degree count increments with precise
AS5048A angle. It rejects missing, nonfinite, inconsistent and ambiguous data;
checks signed int32 wrap; brackets each capture by its complete request latency;
checks cumulative counter/angle agreement to detect a frozen counter even when
individual small angle steps appear plausible;
and estimates speed over a 0.25 s rolling window. Uncertainty bounds, not only
the point estimate, are checked for reverse motion and overspeed. Absolute-count
boundary chatter at rest is not interpreted as mechanical travel.

New stages use 25 ms maximum command/sample gap, a 2 ms requested pause for
powered and coast acquisition, and fresh matching 60-second zero-current timing
proofs for both cadences. Old stages retain their original guards. New counter
stages also require offline reference agreement before opening COM10. Successful
new speed runs are replayed from raw samples, including coast, before promotion.
Fault recovery can reinitialize measurement only to prove standstill; the failed
run remains disqualified and no positive command is resumed.

Four passive probes passed without excitation or configuration writes:

- `synrm-counter-timing-2200-powered-20260913-01`: maximum command gap 17.323 ms.
- `synrm-counter-timing-2200-coast-20260913-01`: maximum command gap 5.730 ms.
- `synrm-counter-timing-2700-powered-20260913-01`: maximum command gap 6.428 ms.
- `synrm-counter-timing-2700-coast-20260913-01`: maximum command gap 5.517 ms.

The 6 A stage shares only the explicitly reviewed zero-current timing workload
with the 5 A / 2700 stage: same speed envelope, cadence and measurement logic.
It still requires a qualified 2200 counter trial, reference agreement, fresh
proofs and live guards. It retains the 8 A fast trip, 2 A DC input cap, zero
allowed regeneration, 0.1 duty cap and 40-second deadline. Its separately reviewed
I2t/input-energy budgets are 1440 A2s / 144 J. That allowance was not consumed:
the startup guard stopped the physical trial at approximately 1.5 A.

## Current startup hypothesis, not a diagnosis

The last failed start began at encoder 174.946288 degrees. Unlike the successful
starts at other poses, Iq stayed near zero while Id followed its target.

Reference `motor/mcpwm_foc.c` applies MTPA first and then input-current limits.
For `mod_q < -0.001`, the upper Iq limit becomes
`lo_in_current_min / mod_q`. With input regeneration limited to zero, that upper
limit is zero, while the MTPA Id target remains. This can produce the observed
Id-without-Iq pattern. The trial did not record mod_q or iq_target directly, so
this causal explanation is NOT yet confirmed. Sensor/calibration and other
control causes remain possible.

Do not remove the current-tracking guard or blindly allow regenerative current.
Ask whether the present 24.5 V source is a battery or a bench supply, and obtain
the supply model/capability before any reverse-power allowance. A short bounded
diagnostic of internal targets/modulation would help distinguish clipping from
tracking error. No such extra powered diagnostic was performed this session.

## Last controller state

Source: `logs/synrm-speed-2700rpm-6a-counter-20260913-01/final-readback.json`.
Baseline SHA256:
`41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`.
Independent readback confirms zero current, standstill, isolated application and
restored baseline. The next action depends on the source-capability answer, not
permission to escalate current blindly.

The passport manifest retains all four new trials, admitting only the qualified
counter-assisted 2200 trial as a stable point. Earlier drafts are unchanged.

Final verification: 248 tests, 245 passed and 3 dependency skips. The reference
acquisition and successful live counter run also passed offline replay with the
final cumulative-agreement check. Passport output is
`docs/motor-passport-20260913-v02/motor-passport-draft.md`, with ten accepted and
eight excluded historical runs. The latest accepted point has time-weighted
1820.569 RPM, 24.5 V and 2.046 W estimated VESC DC input power, not shaft power.
Final independent readback: 24.5 V, MOS 26.8 C, encoder 174.99024 degrees,
all motor/input currents, Id, Iq, duty and ERPM zero, fault 0.
