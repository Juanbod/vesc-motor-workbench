# Restart continuation, 2026-09-13

The user explicitly resumed. The previous 8823.2556 RPM qualification remains a historical result, not a newly reproduced point. No 9300 RPM stage has been prepared or run.

## Controller restart state

First read-only attempt `logs/synrm-resume-quiet-20260913-01` failed because app=5, timeout=1000 ms. Direct inspection found unchanged motor parameters except six automatic ADC offsets; counters reset to approximately zero. No excitation was sent during these queries.

`logs/synrm-resume-session-20260913-01` preserves the fresh baseline and app configuration, verifies standstill, and isolates app RAM to app=0, timeout=300 ms, brake=0. No motor configuration or flash write was performed in this preparation.

Current baseline: `logs/synrm-resume-session-20260913-01/mcconf-before.bin`.
SHA256: `06c3d49a73fff1da4b79ce149fb49ba7ccdc72e7c8171d3635341cb293f8a695`.
Original reference SHA256: `41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`.

New ADC currents: 2047.364990, 2047.818970, 2047.887939. New voltage offsets: 0.0003, 0, -0.0003. No encoder offset/ratio, phase or motor-model configuration change was observed. Hardware mounting cannot be verified through these parameters.

Added `baseline_transition.py`: accepts only exact byte-explained ADC changes, current offset delta <=2 counts with new value 2000-2100, voltage delta <=0.01 and absolute <=0.05. Original speed/counter evidence is still audited against its own original baseline; transferred metadata records both hashes and all changes. This is not a fresh HFI offset calibration. `--reference-baseline` transfers the audited HFI pose convention to an otherwise unchanged motor configuration without editing historical source files.

Five baseline-transition tests and 17 existing pilot-runner tests passed. Full suite has not been rerun for this restart revision. New scripts: `prepare-free-session.py`, `initialize-readonly-runtime.py`.

## Physical and acquisition results

- `synrm-speed-540rpm-5a-restart-20260913-01`: ABORT at 0.50948 s, command 1.5055 A, Id=-1.03 A/Iq=0, no encoder displacement. This old low-speed variant had zero return allowance. Zero current, baseline and independent final readback verified. Remains failed.
- `synrm-speed-540rpm-5a-restart-return075-20260913-01`: PASS and offline audit after restoring the previously tested 0.075 A return allowance and 21-24.9 V guards. Mean 480.3264 RPM, range 478.1219-482.2962, span 4.1742, slope -0.04178 RPM/s. Powered 23.80246 s, I2t 159.4755 A2s, input 17.4419 J. This both checked startup from the new stop angle and accumulated enough counts for native float32 inversion. Independent final angle 124.870608 degrees.
- Native clock source 12: failed without excitation because the Lisp runtime was inactive. No stored program existed. `synrm-native-runtime-resume-20260913-01` initialized it using only `(+ 1 2)` and verified standstill before/after.
- Native clock source 13: PASS, 3305 samples, 133 timing windows. Calibration interval 10036.668774-10042.140271 Hz; source SHA256 5f8b6111ad932b4a56f4ffc1751a9aeebd928c11ae48298e1abb63478d698de6. Calibration file `logs/synrm-native-clock-calibration-20260913-13.json`.
- Fresh v2 timing proofs `synrm-native-timing-9200-dq-resume-powered-20260913-01` and coast equivalent passed, maximum command gaps 12.9361/9.2443 ms.
- `synrm-speed-9200rpm-10p5a-dq-resume-20260913-01`: FAILED target stability after 59.80737 s. Last 8619.0143 RPM; final mean 8552.9133, range 8501.9022-8620.9515, span 119.0493, slope +23.0939 RPM/s. Command 10.5 A; final legacy Id=-7.26/Iq=7.60 A, native sequential Id=-8.1162/Iq=5.2685 A, Vd=-0.7881/Vq=-0.2910 V. Input 449.6285 J, I2t 6288.7093 A2s, 23.9 V, no reported fault or sampled returned energy. Private native function removed and baseline restored. CLI independent final verification also failed because encoder motion exceeded the standstill band. No final-readback file was produced in this trial, and it must not be qualified retroactively.

Separate `logs/synrm-resume-recovery-20260913-01/final-readback.json` subsequently verified exact fresh baseline, app isolated, zero currents/duty/ERPM and standstill. Last angle 228.977056 degrees, t=68485.1737717, bus 23.9 V, MOS 27.2 C. No motor test followed this recovery.

## Rotor clarification resolved

The user clarified that they only rotated the rotor and did not change its mounting. Keep the existing provisional offset; normal rotation is not a reason to recalibrate the absolute encoder. Repeat the previously tested approximately 8800 RPM regime without raising current or speed, after renewing acquisition permits. `logs/synrm-resume-quiet-20260913-02/final-readback.json` independently verified the exact current baseline, isolated app, zero current and standstill at 23.9 V, MOS 27.3 C. Winding temperature remains invalid, not a measured cold winding.

Comparison at the same 10.5 A shows broadly similar low-speed dq readings but slower high-speed acceleration after restart. Near the end, q-current variability increased. This is not enough to attribute the change to the encoder, ADC calibration, friction or the return clamp. Zero-current coast from 8000 to 7000 RPM took approximately 2.716 s previously and 2.557 s after restart; this alone is not a mechanical diagnosis.

Passport v06 remains the last consolidated export. It does not include this fresh-baseline session; keep the new results and failures separate until mixed-baseline reporting is explicitly implemented with hash checks. Historical 8823 RPM is not a newly established maximum or Dualsky performance equivalence.

## Acquisition gate after rotor clarification

No powered trial followed the clarification. Native clock source attempts `synrm-native-clock-source-20260913-14`, `-15`, and `-16` all failed `Counter telemetry gap exceeds bound`, after 1127, 308 and 1474 samples respectively. Preserve these failures; no calibration or timing permit was issued from them.

Added optional `--above-normal` and `--defer-cyclic-gc` to `scripts/probe-native-counters.py`, using existing bounded process-local context managers and recording their metadata. No timing bound, motor parameter, actuator command, or calibration formula was changed. Attempt 16 used both options but still failed, with the final nominal controller-time gap 0.0254 s against the 0.025 s gate. This is not evidence that scheduling resolved the issue, nor a motor/offset diagnosis. Six host-scheduling and three native-clock unit tests passed; the full suite was not rerun for this small change.

Attempt 16's independent `final-readback.json` verified the current baseline, isolated app, zero currents/duty/ERPM, no fault and standstill at t=69097.3660699; bus 23.9 V, MOS 27.3 C, encoder 238.227536 degrees. Motor temperature -49.3 C is invalid. No motor excitation was sent in any of these three attempts. Do not retry the powered run or increase speed until acquisition qualifies again; investigate the calibration snapshot path and latency without relaxing the gate.
