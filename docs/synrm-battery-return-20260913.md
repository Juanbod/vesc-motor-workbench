# Battery return and counter-assisted speed trials, 2026-09-13

## Scope and state

- Project: `C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs`.
- COM10, VESC 6.02, MKSESC_84_100_HP, direct SPI AS5048A, rotor free.
- User confirmed battery 6S1P, 4.5 Ah. Chemistry, C ratings, BMS and individual cell voltages remain unverified. Capacity is not a current rating.
- Canonical baseline: `logs/locked-check-preflight-20260912-01/mcconf-before.bin`, SHA256 `41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`.
- Candidate model remains zero permanent-magnet flux, requested-current MTPA, ratio 2 and provisional offset 1.020427465 degrees. Global offset/startup qualification is NOT complete.
- Every physical run is bounded, followed by zero-current coast, exact baseline restoration and separate quiet readback. External app is RAM-isolated, watchdog 300 ms with zero brake. A power cycle may restore the external ADC application.

## Startup finding

The prior 6 A/no-return trial stopped at about 1.5 A command: Id was present but Iq was nearly zero. Reference firmware at commit `f7c2b34e1cff2234cae98be3abf0cd50e249558f`, `motor/mcpwm_foc.c` around lines 3053-3091, can clamp Iq to zero when filtered q modulation is negative and allowed return current is zero.

This is a supported hypothesis, not direct observation of internal mod_q/iq_target. The first small-return probe started near the same raw angle and produced both Iq and physical encoder travel.

New battery-return stages allow only -0.05 A configured input current. Guards retain 21 <= V < 24.9 V, sampled input current >= -0.1 A and at most 0.25 J sampled returned energy. Native maximum bus voltage is also 24.9 V. Returned energy is accumulated separately from consumed energy, including coast. No active brake commands are used. These sampled guards cannot establish unobserved transient or per-cell bounds.

| Log under `logs/` | Result |
| --- | --- |
| `synrm-startup-2a-return-20260913-01` | FAILED. Started near 174.99 degrees, traveled 65.57 degrees, then native fault 4 (ABS_OVER_CURRENT). Fault history recorded about -3 A at the selected 3 A fast-trip threshold. |
| `synrm-startup-return-faults-20260913-01` | Read-only fault history and quiet baseline verification. No excitation or configuration writes. |
| `synrm-startup-2a-return-margin-20260913-01` | PASSED bounded startup diagnostic. Same 2 A command limit, reviewed 4 A fast-trip limit. 3.80 s powered, 513.94 degrees travel, final 49.77 RPM. This is not a steady-speed passport point. |
| `synrm-speed-2700rpm-6a-return-20260913-01` | FAILED full protocol. Powered portion reached a stable approximately 2355 RPM, but a 46.47 ms host gap on zero-current coast exceeded the then-shared 25 ms limit. Original failed record is preserved. |
| `synrm-speed-2700rpm-6a-return-coast-20260913-01` | PASSED complete acquisition and offline replay. 39.80 s powered, 2353.31 RPM time-weighted final mean, range 2350.11-2356.16 RPM, 24.5 V, estimated VESC input 2.45 W. |
| `synrm-speed-3200rpm-7a-return-coast-20260913-01` | PASSED complete acquisition and offline replay. 39.80 s powered, 2895.81 RPM time-weighted final mean, range 2889.05-2903.02 RPM, 24.5 V, estimated VESC input 2.53 W. |

Both qualified high-speed points satisfied a final 5 s stability window, span <=20 RPM and endpoint slope <=2 RPM/s. They were host-taper-limited, not evidence of a motor maximum. Both had zero sampled returned energy and no VESC fault. Electrical power is quantized, not externally calibrated and not shaft power. The winding temperature channel remains invalid; MOS temperature is not winding temperature.

## Acquisition changes

- Added a distinct reviewed coast envelope: up to 100 ms response gap and 0.5 s counter speed window, only after a zero-current command. Powered command/response gaps remain limited to 25 ms with a 0.25 s speed window.
- Transition retains cumulative encoder travel and signed sector counts. Capture-latency ambiguity, counter consistency, direction and overspeed checks still apply. Offline replay uses the same timing transition and rejects resumed powered acquisition after coast.
- Errors latch a failed result; recovery cannot convert failed samples into a passed run. Counter errors now retain stage, time and reason.
- Two subsequent zero-current probes failed from approximately 23 ms disk-log stalls. Logs: `synrm-return-timing-2700-powered-20260913-02` and `-03`. Neither sent torque or changed motor configuration.
- New stages use bounded queued disk writers. Enqueue does not wait for disk; overflow and writer errors abort torque. Recovery can still verify standstill when logging fails. Both queues must drain after zero-current recovery before a result can qualify.
- With queued logs, matching 60 s zero-current probes passed, with command intervals below 6 ms. Probe and runner logging modes must match. Timing evidence still expires after 600 s.
- Large prior-run replay initially made the 1 s entry readback stale. No torque was sent. The runner now obtains the fresh entry through a callback AFTER offline predecessor validation; the 1 s gate remains unchanged.

## Current progression

The complete 2353 RPM run supports `speed_3200rpm_7a_counter_return_coast`. The complete 2896 RPM run supports the prepared `speed_3700rpm_7a_counter_return_coast`: same 7 A current limit, 10 A fast trip, 2 A input limit, 40 s duration, 1960 A2s and 196 J budgets; only the speed/travel envelope advances. Each actual run still requires fresh zero-current timing evidence, preflight and the dedicated runner.

Successful candidate binaries and all readbacks are in their log directories. Do not load a binary alone and call it the full controller: the external bounded current supervisor is part of the tested setup.

The passport manifest is `config/motor-passport.json`; draft generation is offline via `scripts/build-motor-passport.py`. Keep failed speed trials excluded rather than rewriting their outcomes.

## Final checkpoint

- The 3700 RPM-envelope stage was NOT physically started. Both zero-current timing probes, `logs/synrm-queued-timing-3700-powered-20260913-01` and `-02`, aborted on `Counter/angle wrap is temporally ambiguous` under the 4070 RPM hard envelope. This is an acquisition limit, not a demonstrated motor speed limit. Neither trial sent torque or changed motor configuration.
- Those failed probes did not retain the rejected packet. The probe now preserves the failed packet and previous packet in future error reports, so the exact response-bracket ambiguity can be diagnosed rather than inferred. Do not claim an exact latency for either past rejected packet.
- Independent final readback: `logs/synrm-battery-return-final-20260913-01/final-readback.json`. Read-only fault history still contains only the original 3 A startup trip at tacho 106865; no new fault records appeared.
- Next work: diagnose the rejected request bracket at zero current before authorizing the prepared higher-speed stage. Do not relax angle ambiguity or powered gap limits to make a speed trial pass.
- Last full software suite: 268 tests passed, 3 skipped. Separate tests cover queued-write overflow/error, zero-current recovery after logging failure, long-gap coast replay and stale-entry ordering.
