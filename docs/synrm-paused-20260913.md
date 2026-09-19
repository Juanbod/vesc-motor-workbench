# Bench paused, 2026-09-13

HISTORICAL PAUSE: the user subsequently explicitly resumed. Current state and restart results are recorded in `docs/synrm-restart-20260913.md`. Do not treat the stopped-state values below as a fresh hardware readback.

The user requested one final test and a pause. That test is complete. Do not start another motor test until the user explicitly resumes.

Regenerated passport: `docs/motor-passport-20260913-v06/motor-passport-draft.md` and matching JSON, 26 accepted / 20 excluded runs. At the last qualified plateau, time-weighted VESC DC input estimate is 7.45 W; this is unloaded electrical input, not shaft power.

## Last qualified result

- Run: `logs/synrm-speed-9200rpm-10p5a-dq-return075-20260913-01`.
- Stage: `speed_9200rpm_10p5a_dq_return075`.
- Mean mechanical speed 8823.2556 RPM; final five-second range 8815.2503-8831.0688 RPM.
- Powered duration 59.8074 s; command cap 10.5 A; battery bus about 24.0 V.
- Input energy 440.0825 J from VESC telemetry, not shaft output energy.
- Current trip 14 A; DC input cap 2 A; configured return allowance 0.075 A.
- No reported controller faults or sampled returned energy. Full offline audit passed.
- This is an unloaded controlled plateau, not mechanical maximum, continuous rating or original Dualsky power equivalence.

## Verified stopped state

Final independent readback is in the run directory. Rotor stopped, 0 ERPM, zero motor/input/Id/Iq currents, zero duty. App RAM is isolated, private diagnostic RAM function removed, baseline restored exactly:

`logs/locked-check-preflight-20260912-01/mcconf-before.bin`

SHA256 `41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`.

The successful trial configuration is preserved as `mcconf-candidate.bin` in the run directory; it is NOT left active on the controller. Power is not physically disconnected by software. A power cycle can restore the stored external app configuration.

## Resume notes

The previous repeatable Id/Iq tracking stop around 8.15k RPM was removed in the tested range by changing only the small return-current allowance from 0.05 to 0.075 A. Changing the soft ERPM knee alone did not help. Native Vd/Vq diagnostics and the pinned firmware's q-only input-current clamp support this hypothesis, but internal current targets are not measured directly.

After the user resumes, recheck fixture, battery, standstill, exact configuration and communication. Old clock/timing permits expire and cannot authorize a new powered run. The proposed next increment is approximately 9300 RPM, but no new stage or automatic sweep has been prepared. Winding temperature remains unavailable; no load/torque equipment is present. Detailed history: `docs/synrm-speed-continuation-20260913.md`.
