# Speed-search continuation, 2026-09-13

CURRENT STATUS: user resumed after the successful 8823 RPM trial. Controller restart required fresh ADC-baseline and acquisition preparation. Latest high-speed repeat failed qualification; motor recovered to zero current. User confirmed ordinary rotor rotation only, with no mounting changes. Keep the provisional offset. Three subsequent no-excitation clock checks (sources 14-16) failed the telemetry-gap gate; no new powered trial ran. Resolve acquisition before repeating the existing regime or increasing speed. See `docs/synrm-restart-20260913.md`.

Continues `docs/synrm-battery-return-20260913.md`. The user's objective remains maximum stable speed. No mechanical maximum or nameplate rating has been established.

## Physical results

| Run under `logs/` | Result |
| --- | --- |
| `synrm-speed-3700rpm-7a-return-coast-20260913-01` | Complete PASS and offline audit. 39.80 s powered; final 5 s time-weighted mean 3374.85 RPM, range 3366.10-3381.22 RPM. DC 24.4-24.5 V, estimated VESC input 2.89 W. |
| `synrm-speed-4200rpm-7a-return-coast-20260913-01` | Complete PASS and offline audit. 39.80 s powered; final 5 s time-weighted mean 3854.20 RPM, range 3849.36-3859.24 RPM. DC 24.4 V, estimated VESC input 3.17 W. |
| `synrm-speed-4700rpm-7a-return-coast-20260913-01` | FAILED full protocol. Powered portion had a stable final mean about 4336.56 RPM, range 4330.02-4342.97 RPM. A single capture became temporally ambiguous on zero-current coast. Baseline and standstill recovered; no VESC faults. This run remains excluded from qualified passport points. |

All three used at most 7 A command, 10 A native fast trip, 2 A input-current limit, 40 s powered duration, 1960 A2s and 196 J limits. The small battery-return allowance and 21-24.9 V guards were unchanged. Sampled returned energy was zero. The established plateaus were host-taper-limited, not a motor maximum. MOS temperature is not winding temperature; the winding channel remains invalid.

The old 3700-stage zero-current failures did not recur in fresh strict probes. No ambiguity thresholds were relaxed: `synrm-queued-timing-3700-powered-20260913-03` and `synrm-queued-timing-3700-coast-20260913-01` passed. Matching 4200 and 4700 powered/coast probes also passed before their respective physical trials. A successful passive probe is not a guarantee against later host delays.

## Isolated late capture on coast

In the failed 4700-envelope run, the rejected sample at t=26429.7905672 had latency 5.5891 ms, Id=Iq=current_motor=duty=0, fault=0. The prior accepted sample had latency 0.3967 ms; the following sample had latency 0.6089 ms. Time from prior accepted to following capture was 11.6994 ms. The prior rolling speed estimate was about 748 RPM. The ambiguity check correctly used the complete 5170 RPM envelope rather than assuming that local speed estimate was a hard bound.

Old behavior reset the acquisition tracker on any error, preserving a failed result but losing continuity of the travel estimate. The failed source files have not been modified.

Prepared `speed_4700rpm_7a_coast_reacquire` retains byte-identical motor settings and all electrical, duration, speed and accepted-gap limits. Only zero-current coast acquisition changes:

- At most ONE temporally ambiguous capture in a full run can be deferred.
- The caller must already have sent zero current. The packet must also report effectively zero motor/dq current and duty, no fault, and consistent bounded sector-counter increments.
- Malformed counters, excessive accepted-sample gaps, current/fault/voltage violations and a second ambiguous packet still fail the run. Powered captures never use deferral.
- The last valid anchor, history, signed sector count and cumulative encoder travel are retained. The next valid capture must pass the original counter/angle, direction, speed and <=100 ms coast-gap checks against that retained anchor.
- A deferred packet cannot contribute to standstill confirmation. It must be resolved by a subsequent accepted packet; offline replay rejects unresolved or unmarked deferrals.
- The raw packet and a deferred marker remain in the log; no samples are secretly deleted. Exact travel is recomputed across the gap from the next accepted counter/angle pair.
- Timing probes remain strict and never defer a capture. Their workload and bounds match the original 4700 stage, so `timing_stage()` explicitly uses that probe identity.

Diagnostic replay of the old raw packet stream resolved precisely one deferred capture and produced 1104542.2705 degrees total travel; maximum accepted gap was 11.6994 ms. This checks algorithm feasibility only and does NOT reclassify the failed physical protocol. The new mode requires a new physical run and full independent readback before it can qualify.

## Subsequent complete trials

| Run under `logs/` | Result |
| --- | --- |
| `synrm-speed-4700rpm-7a-reacquire-20260913-01` | PASS and offline audit; 39.80 s powered, final mean 4339.57 RPM, range 4330.51-4350.07. No deferred capture was needed. Candidate bytes identical to the preceding failed run. |
| `synrm-speed-5200rpm-7a-reacquire-20260913-01` | FAIL stability criterion, not a controller fault or capture failure. At 39.80 s it was still accelerating: last speed 4755.80 RPM, final-window slope 33.59 RPM/s. Restored baseline and quiet state. Excluded from qualified points. |
| `synrm-speed-5200rpm-7a-hold60-20260913-01` | PASS and offline audit; same candidate bytes, duration extended to 60 s. Final mean 4821.80 RPM, range 4815.81-4828.35. Actual 59.80 s, 2750.46 A2s, 221.62 J input. |
| `synrm-speed-5700rpm-8a-hold60-20260913-01` | PASS and offline audit; 8 A cap, 11 A fast trip, 2 A input cap, 60 s. Final mean 5351.66 RPM, range 5344.59-5358.67. Actual 3210.25 A2s, 255.62 J input. |
| `synrm-speed-6200rpm-8a-hold60-20260913-01` | PASS and offline audit; same 8 A / 11 A / 2 A electrical limits. Final mean 5829.58 RPM, range 5821.72-5837.42, slope -0.549 RPM/s. Actual 59.80 s, 3472.41 A2s, 274.86 J input. Independent final standstill angle 43.769532 degrees. |

Successful plateaus remain host-current-taper-limited. They are measured no-load test points, not a discovered maximum or a rated continuous speed. Input energy/power is derived from VESC DC telemetry, not shaft output. Bus voltage was about 24.4 V; sampled returned energy was zero in these runs. No winding temperature measurement is available.

For 6200-stage preparation, the immediately preceding 5700-stage zero-current timing evidence was requalified offline against the NEW 6820 RPM hard envelope. Explicit adjacent-stage mapping is permitted only for identical zero-current acquisition workloads; every raw counter capture is replayed with the target bounds and original strict ambiguity checks. Matching scheduling/GC/buffer/logging settings and <=600 s freshness remain required. Unit coverage verifies a packet valid at the old envelope is rejected at the tighter new envelope. No failed or stale proof is made valid by this mapping.

Prepared next stage `speed_6700rpm_8a_hold60`: taper starts 6300 RPM, current cut at 6700 RPM, hard envelope 7370 RPM. The 8 A command, 11 A fast trip, 2 A battery input, 60 s / 3840 A2s / 384 J bounds and zero-current coast checks remain unchanged. Requires the qualified 6200-stage predecessor and fresh matching powered/coast timing proofs. Not yet a physical result.

## 6700 preparation: acquisition limitation, not a motor limit

The first powered-cadence zero-current probe passed, but coast-cadence probes failed with 5.000 and 3.000 ms captures. These are not powered runs. An independent readback in `logs/synrm-6700-timing-recovery-20260913-01` verified zero current and exact baseline. Fault history still contained only the earlier ABS_OVER_CURRENT at tacho 106865, not a new high-speed fault.

Three acquisition changes were implemented and tested without relaxing ambiguity bounds:

- Process-local Python thread switch interval 1 ms while above-normal scheduling is enabled; restored on exit. Fresh proof metadata must match. This alone did NOT remove delayed reads (`synrm-queued-timing-6700-coast-switch1ms-20260913-01`).
- `capture_values` timestamps completion of GET_VALUES before `asdict`/log formatting, records formatting separately, and leaves real read latency and sample age visible. Probes must match this timestamp method. The next failed packet took 2.7502 ms to obtain but only 16.8 us to format, so formatting was not the main cause (`synrm-queued-timing-6700-coast-capture-v1-20260913-01`).
- 6700 stage now uses a bounded in-memory log, no disk writer thread during acquisition, maximum 64 MiB ASCII text / 131072 records per stream. Drain only after zero-current recovery; overflow/drain errors fail qualification. This also did NOT solve the host delay (`synrm-memory-timing-6700-coast-20260913-01`, 3.0732 ms). Independent recovery readback: `synrm-6700-memory-recovery-20260913-01`.

The 6700 powered stage has NOT been run. Do not report 6300 or 6700 RPM achieved. All failed probes remain preserved. Latest complete powered qualification is approximately 5830 RPM.

## Native Lisp acquisition feasibility

Read-only queries found zero stored Lisp bytes; statistics initially timed out, which alone did not prove lack of support (`synrm-lisp-capability-20260913-01`). A literal RAM-only `(+ 1 2)` expression returned `> 3`, proving interpreter availability (`synrm-lisp-arithmetic-20260913-01`). No flash/config writes or motor commands were sent. This expression can initialize the empty Lisp runtime; the top-level runtime_started=false in that old file describes its initial read-only subquery, NOT the subsequent arithmetic operation. The runtime is now available and idle with no stored script.

`synrm-lisp-snapshot-20260913-01` returned encoder 41.286621 degrees, local timer ticks, near-zero RPM/Id/Iq and about 24.385 V from a fixed read-only expression. Reference firmware system tick is 10000 Hz; installed-build timing scale still needs empirical verification.

An initial fixed 16-sample native burst failed decode and its raw response was not retained; its entry/final quiet readbacks remain in `synrm-lisp-burst-20260913-01`. The decoder was corrected to preserve raw evidence on rejection. The new physical read-only burst `synrm-lisp-burst-20260913-02` passed: 21.4 ms native span, maximum adjacent upper gap 1.9 ms, maximum acquisition bracket 0.4 ms, host round trip 38.60 ms. This proves local sampling feasibility at standstill ONLY; it is explicitly not qualified for powered control. No motor test has occurred since the successful 6200-stage run.

User's new comparison target is documented in `docs/dualsky-comparison-target-20260913.md`; reaching unloaded speed does not establish original loaded power/efficiency.

## Native counter snapshots and clock correction

`native_counter_snapshot.py` prepares a fixed, read-only RAM expression: system tick, signed distance, absolute distance, raw encoder angle, system tick, plus encoder error rate. Only these fields share the short native acquisition bracket; host request age remains a separate measurement. No motor setters, flash writes, spawned task or persistent user script are included.

The reference distance getters multiply sector counters by a float32 SI scale. The actual baseline still has SI poles=14, wheel diameter=0.08299999684 m and gear=1; these metadata are used ONLY to invert the distance getter, never to infer physical rotor poles. At verified standstill the decoder retains every nearby float32 scale reproducing both independently queried integer counters, then accepts subsequent inversion only when it yields exactly one possible integer. Wrong scales, nonfinite data and insufficient float precision fail. The observed unique scale is 0.006208385806530714 m/count. This remains conditional on matching getter behavior; moving-data comparison is still required.

- `synrm-native-counter-probe-20260913-01`: 5-second read-only probe passed with 277 snapshots. Native counters matched the bracketing legacy GET_VALUES counters; largest native angle/counter bracket 0.3 ms, largest snapshot host round trip 20.868 ms.
- `synrm-native-counter-probe60-20260913-01`: all 3319 snapshot/counter comparisons and 25 ms acquisition checks passed, but the final assumed-10000-Hz clock check FAILED. Source log is preserved as failed, not reclassified.
- Offline `synrm-native-clock-calibration-20260913-01.json` used the preserved host request/response brackets, native tick quantization and 133 staggered long windows. Compatible tick rate is 10036.96208-10042.38110 Hz, midpoint 10039.67159 Hz, not 10000 Hz. Relative interval width 0.054%. This explains a roughly 0.4% bias if nominal ticks were used for RPM. It is a stationary interval calibration, not a temperature-wide oscillator qualification or a powered-controller acceptance.

Last independent readback: `synrm-native-counter-probe60-20260913-01/final-readback.json`; zero current, exact baseline and isolated app. Bus 24.3 V, MOS 27.2 C, winding channel invalid. The empty Lisp runtime remains available/idle. Next work: carry the calibrated native clock interval through speed uncertainty and offline replay, qualify the complete native acquisition path, then repeat a known powered point before increasing speed. Do not start the old 6700 profile using these read-only prototype files as a timing permit.

Passport `docs/motor-passport-20260913-v04` was regenerated: 18 accepted powered points, 11 excluded runs, highest qualified mean 5829.6 RPM at approximately 24.4 V and estimated VESC DC input 4.59 W. The original 2017 manufacturer PDF is retained as a link in the comparison document, not merged into prototype measurements.

## Integrated native path and first powered repeat

Clock source `synrm-native-clock-source-20260913-02` passed a new stationary 60-second capture. Calibration `synrm-native-clock-calibration-20260913-02.json` gives 10036.96218683839-10042.344989060268 Hz, midpoint 10039.653587949328 Hz, consistent with the independent first capture. Clock reference validation checks raw packet/source hashes, stationary legacy counter agreement, freshness <=600 s and the exact float32 distance scale.

`NativeProbeClient` combines ordinary GET_VALUES current/voltage with a controller-timed counter/angle snapshot. `NativeCounterAngle` propagates the calibrated clock interval through speed bounds and replay. Native captures have no deferred-coast exception. Host command/sample limits remain 25 ms powered and 100 ms coast. Native 6200 stage retains exactly the legacy 6200 candidate bytes; native 6700 requires a qualified native 6200 predecessor.

Both full integrated zero-current proofs passed (`synrm-native-timing-6200-powered-20260913-01`, `synrm-native-timing-6200-coast-20260913-01`): maximum command gaps 18.5111 and 18.3322 ms. Full suite then passed 316 tests, 3 skipped.

Real powered repeat `synrm-speed-6200rpm-8a-native60-20260913-01` FAILED the 25 ms counter gap bound after 14.865 s. Last accepted speed was 3938.99 RPM, command 8 A, measured Id=-5.65 A/Iq=5.66 A, bus 24.2 V. Input 59.97 J, I2t 833.46 A2s. Physical displacement was observed but the full qualification failed; do not use it as a predecessor. No controller faults, zero current, baseline rollback and independent final standstill were verified. Latest qualified stable point remains the original 5829.58 RPM run.

Next acquisition revision prepares one uniquely named read-only Lisp lambda in RAM before the session and uses short calls instead of reparsing the complete expression every sample. It has no motor setters, background task or flash write. The private binding is removed on client close; lifecycle evidence in `native-runtime.json` is required by timing and powered audit gates. Old inline-expression timing proofs are not accepted for this revision. Current, voltage, speed, time and sampling limits are unchanged. New matching zero-current proofs are required before retrying the known point.

## Prepared-function physical results

- Calibration 03: source `synrm-native-clock-source-20260913-03`, interval 10036.949916505184-10042.4574053396 Hz. Both prepared-function 6200 timing proofs passed, max command gaps 9.554/8.820 ms.
- `synrm-speed-6200rpm-8a-native60-20260913-02`: powered acquisition and recovery succeeded, mean 5827.55 RPM, span 11.47 RPM, 59.806 s. CLI finalization FAILED because a delayed `> t` print from send-data was mistaken for the cleanup acknowledgement. No native-runtime/final-readback artifacts were produced in that run; it is not qualified for escalation despite result.json describing the earlier physical phase as ok. Separate `synrm-native-repeat-recovery-20260913-01` verified baseline, zero current and standstill. Original logs were not reclassified.
- ACK handling now accepts only the expected marker, skipping bounded delayed `> t` returns, and still rejects other results/missing ACK. Private function identity is saved before powered acquisition. Four focused prepared-function tests pass, including delayed and missing ACK and serial closure on cleanup failure.
- `synrm-speed-6200rpm-8a-native60-20260913-03`: PASS with complete native lifecycle, independent readback and offline audit. Mean 5831.73685 RPM, range 5825.25367-5837.41219, span 12.15852, slope 0.60665 RPM/s, 59.80948 s, I2t 3449.1481 A2s, input 272.7911 J. Baseline restored; final angle 104.7876 degrees.
- Calibration 04: source `synrm-native-clock-source-20260913-04`, interval 10036.927537005646-10042.420623340953 Hz. Prepared 6700 timing proofs passed, max gaps 9.226/8.379 ms.
- `synrm-speed-6700rpm-8a-native60-20260913-01`: PASS with complete native lifecycle, independent readback and offline audit. Mean 6309.13875 RPM, range 6303.24964-6315.13759, span 11.88795, slope 0.69950 RPM/s, 59.80637 s, I2t 3680.7580 A2s, input 286.3944 J, bus 24.2 V. Command cap 8 A, final command 7.8237 A. Baseline restored; final angle 138.076176 degrees.

Next prepared stage `speed_7200rpm_8a_native60` raises the taper/cut by 500 RPM (6800/7200), hard envelope 7920 RPM, with all electrical, time, stability and capture limits retained. It requires the qualified native 6700 predecessor. Its identical zero-current workload may use the fresh 6700 proofs only after replay against the new 7920 RPM envelope and matching clock/method/cadence checks. This stage is not a physical result until executed.

`synrm-speed-7200rpm-8a-native60-20260913-01` subsequently ran for 59.8073 s and failed the requested speed/stability criterion, with no faults or capture errors. Last speed 6401.49 RPM, final five-second mean 6381.24, range 6358.18-6403.66, slope +8.6794 RPM/s. Command stayed at 8 A. I2t 3706.0422 A2s, input 287.1256 J, bus 24.2 V; zero current, exact baseline, private-function removal and independent final standstill verified. This is continuing acceleration, not a proved maximum, and is not a qualifying predecessor.

Prepared `speed_7200rpm_9a_native60` retains the same 6800/7200/7920 RPM envelope and all capture, voltage, 2 A DC input, 60 s and coast limits. Only commanded current (9 A), observation threshold (10.8 A), fast trip (12 A), I2t (4860 A2s) and input energy budget (486 J) change. Its predecessor remains the successfully qualified native 6700/8 A trial, never the failed 7200 trial. New clock source and timing evidence will be needed after the current full software test suite.

Full software suite passed 322 tests (3 skipped). Passport v05 contains 20 accepted / 14 excluded runs through the 7200/8 A attempt, highest qualified 6309.1 RPM.

Calibration 05 (`synrm-native-clock-calibration-20260913-05.json`): interval 10036.94717075095-10042.411222975432 Hz, source hash 6c0198d875ec39b559f1b50ff31066a035f9473795d50c70733431558599851f. Fresh 7200/9 A zero-current powered and coast proofs passed with maximum command gaps 8.5354 and 9.6561 ms.

`synrm-speed-7200rpm-9a-native60-20260913-01` PASSED full physical acquisition, private-function cleanup, independent standstill and offline audit. Mean 6836.6510 RPM, range 6829.5627-6843.3936, span 13.8309, slope +0.34654 RPM/s. Powered 59.80892 s, I2t 4273.6586 A2s, input 327.16565 J, bus 24.1 V, final command 8.1308 A under the 9 A cap. No faults; exact baseline restored, final angle 160.620112 degrees. This is still a controlled no-load plateau, not motor maximum or shaft-power qualification.

Prepared next `speed_7700rpm_9a_native60`: same 9 A / 12 A trip / 2 A DC / 60 s bounds, taper 7300, cutoff 7700, hard 8470 RPM, min completion 7250 RPM. Requires qualified 7200/9 A predecessor; identical zero-current workload can reuse fresh 7200/9 A proofs only with raw replay against 8470 RPM and matching clock/method/cadence. No physical result for this stage yet.

`synrm-speed-7700rpm-9a-native60-20260913-01` subsequently PASSED with independent final readback and offline audit. Mean 7319.8495 RPM, range 7310.8855-7327.4318, span 16.5463, slope +1.58446 RPM/s, 59.80272 s. I2t 4524.1184 A2s, input 343.3035 J, bus 24.1 V, final command 8.48336 A. Exact baseline and zero current verified, final angle 78.859864 degrees.

The next clock source 06 failed a zero-current acquisition gap; it remains failed. Repeat source 07 passed, calibration interval 10036.919372219243-10042.437468032971 Hz, source hash 25cd0b52c115da705bf158b7d92316ef44cdce106fc7fcffd458a30b0cd65139. Both 8200/9 A timing probes passed (max gaps 10.5447/11.8701 ms).

`synrm-speed-8200rpm-9a-native60-20260913-01` completed 59.80903 s without faults or acquisition errors but FAILED the requested speed/stability criterion. Last speed 7674.808 RPM, final mean 7652.526, range 7626.930-7680.350, span 53.420, slope +9.3823 RPM/s; command 9 A throughout the final window. I2t 4673.4349 A2s, input 352.3834 J, bus 24.1 V. Baseline, zero current, private-function cleanup and independent final standstill verified. It is continued acceleration, not a stable maximum and not a qualifying predecessor.

Prepared 10 A branch keeps 60 s, 2 A DC input, capture and voltage limits. Current guard 12 A observed / 13 A fast trip, I2t 6000 A2s, energy 600 J. First `speed_8200rpm_10a_native60` repeats the same speed envelope and requires qualified 7700/9 A; later 8700/10 A and 9200/10 A stages add 500 RPM each and require their immediately preceding qualified 10 A stage. None is an automatic unbounded sweep. Freshness, raw timing replay and exact lifecycle checks apply to every invocation.

## 7842 RPM qualification and reproducible tracking stop

`synrm-speed-8200rpm-10a-native60-20260913-01` PASSED with complete lifecycle, independent readback and offline audit. Mean 7842.1150 RPM, range 7832.5317-7851.5754, span 19.0437, slope -0.62995 RPM/s. Powered 59.80734 s, I2t 5119.9499 A2s, input 384.8464 J, bus 24.1 V, final command 8.9840 A. Candidate SHA256 26269f9d00296ecdfde7ece9037615a2220b2c2946e19e29344924f6efc78959. This remains a controlled unloaded plateau, not a maximum or shaft-power measurement.

Clock source 08 and matching native 8700/10 A powered/coast proofs passed. The next two physical runs both ABORTED on measured Id/Iq not following zero-flux MTPA targets, never a qualified predecessor:

| Run suffix under `logs/synrm-speed-8700rpm-10a-` | Time s | Last RPM | Id / Iq A | Input J |
| --- | ---: | ---: | --- | ---: |
| `native60-20260913-01` | 31.6701 | 8176.689 | -7.87 / 4.49 | 210.5686 |
| `native60-20260913-02` | 30.8157 | 8159.615 | -7.54 / 3.87 | 204.2895 |
| `rpm95-20260913-01` | 31.2314 | 8152.352 | -7.78 / 4.37 | 206.5125 |

All had 10 A command and expected Id=-7.071 A / Iq=7.071 A. No controller fault or encoder error was reported. All recovered zero current, exact baseline, private-function removal and independent standstill. Failed logs remain excluded.

The RPM95 diagnostic changes only `l_erpm_start` from 0.8 to 0.95, retaining hard +/-19140 ERPM, 8700 RPM host cut, 10 A / 13 A trip and 60 s. Reference `motor/mc_interface.c` uses fast ERPM for its soft knee; ordinary telemetry uses PLL speed. The repeated stop with the new knee does NOT support this explanation. Fresh clock 09 passed (10036.843314-10042.524541 Hz, source SHA256 56c2023825756fb6794a88336feee3582da25292bf5bdf19ec328539e02378bf); RPM95 powered/coast timing gaps were 9.7764/8.7309 ms.

Next diagnostic is measurement, not another current increase: record native Vd/Vq and Id/Iq to separate voltage saturation, cross-coupling and the q-only input-current clamp. In pinned reference `motor/mcpwm_foc.c`, input limiting explicitly omits the d-axis input-current contribution; negative mod_q can clamp positive Iq even when total DC input is positive. This is a hypothesis until measured. Cross decoupling remains disabled. Winding temperature remains unavailable. No higher-speed or full Dualsky performance claim is made.

## Dq diagnostics and first correction

Added optional `prepared_readonly_dq_lambda_v2`: 497-byte setup expression, packet magic 6820 and 53-byte response, Vd/Vq plus filtered Id/Iq and a separate diagnostic end tick. The counter/angle bracket and old v1 format stay unchanged. Dq values are sequential, not simultaneous or the internal current targets/mod_q_filter. Nonfinite/missing data, malformed packets, excessive diagnostic bracket and mismatched lifecycle versions fail. Old timing permits cannot qualify v2. Full suite passed 331 tests with 3 skips; subsequent return-stage focused tests also passed.

Clock 10: 10036.944446-10042.460167 Hz, source SHA256 35051eb7381fc708066d8bfd8a8aaeed558c21f8a4e206e7d2d2aeb37560972c. New 8200 dq powered/coast proofs passed with 13.3110/9.4551 ms maximum gaps.

- `synrm-speed-8200rpm-10a-dq-20260913-01`: PASS plus offline audit. Byte-identical motor settings to qualified 8200/10 A v1. Mean 7840.2739 RPM, range 7832.7822-7848.1425, span 15.3603, slope +0.51286. 59.80017 s, I2t 5133.4784 A2s, input 385.6398 J, bus 24.0 V. Complete rollback and independent final standstill, angle 127.858888 degrees.
- `synrm-speed-8700rpm-10a-dq-20260913-01`: tracking ABORT at 8133.5242 RPM after 30.57698 s. Legacy Id=-7.74/Iq=4.20 A; sequential native Vd=-0.7291/Vq=-0.1453 V, Id=-5.9639/Iq=6.2075 A, indicating rapid change. Preceding Vq reached -0.2427 V. No fault/capture error; complete rollback and standstill verified. This is not a qualified speed point.
- `synrm-speed-8700rpm-10a-dq-return075-20260913-01`: PASS plus offline audit after changing ONLY input return allowance from 0.05 to 0.075 A. All other motor candidate fields and physical/sampling limits match the preceding dq attempt. Mean 8323.5496 RPM, range 8315.9960-8331.4200, span 15.4240, slope +1.30658. 59.80633 s, I2t 5464.3368 A2s, input 406.9065 J, bus 24.0 V, final command 9.3784 A. Candidate SHA256 e4068bc65b09b3685b89b05f5bbd9c6312ff08f7247cbf79df498b1979d3a39b. No sampled returned energy, no faults; complete rollback and independent final angle 27.312012 degrees.

This controlled change supports the input-clamp hypothesis but does not directly observe the internal target or attest the installed source. The unchanged external battery guards remain 0.1 A sampled reverse current, 0.25 J sampled returned energy, 21-24.9 V; no active braking. The next prepared stage `speed_9200rpm_10a_dq_return075` moves taper/cut to 8800/9200 RPM, hard 10120 RPM, retaining 10 A command / 13 A trip / 60 s. It requires the qualified 8700 dq-return075 predecessor and fresh v2 timing evidence. No result for this stage yet.

## Final two trials and user pause

Clock 11: 10036.930636-10042.535606 Hz, source SHA256 e9fe93a276014bbbb8b32a7dc15b8bc5e70fcfc56c132918377c8a49a418353a. Fresh 9200 dq-return075 powered/coast timing proofs passed, max gaps 12.5092/12.8011 ms.

- `synrm-speed-9200rpm-10a-dq-return075-20260913-01`: full acquisition and recovery completed without faults, but target stability FAILED. Last 8774.8058 RPM, final mean 8765.7857, range 8744.3411-8786.5706, span 42.2295, slope +4.89858 RPM/s. Still accelerating at the 60 s limit. Powered 59.80870 s, I2t 5747.9687 A2s, input 425.6834 J. Not a qualified predecessor.
- `synrm-speed-9200rpm-10p5a-dq-return075-20260913-01`: PASS including independent readback and offline audit. Same speed and battery limits, current cap 10.5 A, observed guard 12.6 A, fast trip 14 A, I2t budget 6615 A2s / input budget 661.5 J. Mean 8823.2556 RPM, range 8815.2503-8831.0688, span 15.8185, slope -0.63920 RPM/s. Powered 59.80739 s, I2t 5985.6623 A2s, input 440.0825 J, bus 24.0 V. Final command 9.8716 A; measured Id=-6.97/Iq=6.97 A. Candidate SHA256 21144ea949c4d911faa6df213dc1a9754575abbd8e824bc05a1fbc601826365c. No faults or sampled returned energy.

User requested this be the last test and then a pause while it was already running. It completed and NO subsequent motor test was launched. Independent final readback verifies 0 ERPM, motor/input/Id/Iq currents zero, duty zero, app isolated, exact baseline restored; final angle 192.041008 degrees. Private RAM snapshot function was removed. Latest qualified point is 8823 RPM, not a discovered maximum, continuous rating or demonstrated equivalence to the original Dualsky. After an explicit resume, the next proposed target is approximately 9300 RPM (+500); no such stage is prepared or authorized to run automatically. Fresh stationary clock and timing proofs will be required.

Software verification: full suite 331 tests / 3 skips before the last three stage additions; after those additions, focused native-dq suite 8 tests and timing-gate suite 13 tests passed. No full-suite claim is made for the subsequent additions.
