# Higher-speed trials, 2026-09-12

Status: stages through 750 RPM physically tested after the user confirmed the rotor
was secured and guarded. The motor is stopped; normalized baseline restored.
This is short no-load evidence, not continuous-duty or all-position startup
qualification. Keep the physical power cutoff accessible.

## Results

| Mechanical target | Mean after acceleration | Peak phase current | Duration | Log |
| --- | --- | --- | --- | --- |
| 300 RPM | 304.75 RPM | 5.89 A | 5.015 s | run-300rpm-02 |
| 450 RPM | 460.03 RPM | 6.01 A | 5.015 s | run-450rpm-01 |
| 600 RPM, ramp 600 eRPM/s | 610.60 RPM | 7.01 A | 5.002 s | run-600rpm-02 |
| 750 RPM, ramp 600 eRPM/s | 765.72 RPM | 7.16 A | 5.022 s | run-750rpm-01 |

Means cover the last approximately 2.48 seconds, not the acceleration portion.
The stages in the table passed the configured short-window speed criteria, with no VESC
fault reported. The 450-RPM instantaneous estimate ranged about 445..493 RPM
in that evaluation window. At the 750-RPM target the range was about 724..821 RPM.
Speed ripple remains; a single short trial is not a guarantee of long-term
stability. Latest tested candidate: profile-750rpm-tested/.

run-600rpm-01 used the old 400-eRPM/s acceleration ramp and failed the steady
speed drift criterion, despite reaching the target without a controller fault.
About three of the five seconds were needed for the requested acceleration.
The second trial changed only the commanded speed ramp to 600 eRPM/s and passed.
No current, temperature, energy or I2t guard was relaxed. The highest tested
setpoint is 750 mechanical RPM; the transient estimate near 821 RPM is NOT a
validated operating point or the motor's maximum speed.

The initial run-300rpm-01 was aborted BEFORE any nonzero drive command because
strict motor readback and rollback comparisons failed. Inspection showed only
foc_offsets_voltage[0] changed from 0.0007 to 0.0006. Firmware float16 encoding
uses scale 10000 with integer truncation. Float32 round-trip reproduces
0.0007 * 10000 = 6.999999523..., which truncates to 6; 0.0006 is stable.
No comparator tolerance was introduced. baseline-normalized/ contains the
verified current configuration after this quantization; subsequent writes
passed strict comparison. baseline/ preserves the original preflight.

After the 450-RPM drive completed, automatic rollback timed out waiting for
standstill (10-second limit). No subsequent acceleration was attempted.
recover_stopped.py applied only zero-current commands, verified standstill
over the configured pause, and restored baseline-normalized/ with exact
readback. See recovery-450rpm/result.json. Original run status is preserved
as recovery_required rather than rewritten to conceal the timeout.

The runner now has a bounded rollback_timeout_s (default 30 s, maximum 60 s).
It still supplies only zero-current commands while waiting, requires standstill,
and leaves drive disabled if the wait expires. Regression tests cover coasting
for 12 seconds before stopping and continuing to coast past the 30-second timeout.
All three subsequent 600/750-RPM trials restored their baseline automatically.
The speed ramp is explicitly configurable in 100..600 eRPM/s. All 48 tests pass.
Do not skip standstill verification or rewrite profiles on a moving rotor.

## Encoder versus sensorless

ERPM is electrical RPM, not a control mode. With the configured encoder ratio
2 and direct drive, 1200 eRPM corresponds to 600 mechanical RPM.
The relevant mode change is encoder angle versus the sensorless observer angle.

The live foc_sl_erpm setting is 4000. Official firmware 6.02 uses a 5% hysteresis
in foc_correct_encoder: when already using the encoder it selects the observer
above 4200 eRPM, and returns below 3800 eRPM. At ratio 2 these are approximately
2100 and 1900 mechanical RPM, respectively. These are CODE/CONFIGURATION
thresholds, not observed switching events. The threshold uses the controller's
fast speed estimate, so a host RPM sample alone does not establish the event.

Source: https://github.com/vedderb/bldc/blob/f7c2b34e1cff2234cae98be3abf0cd50e249558f/motor/foc_math.c

No transition was intentionally crossed. The tested candidate uses zero PM flux
and an unqualified observer for this magnet-free rotor. The standard observer
contains the configured PM flux in its state equations; there is no evidence
here that its angle is usable on this motor. Do not lower the transition speed
simply to force a switch, or describe the calculated threshold as measured.

Before a transition experiment, record observer/encoder electrical angle error
and the actually selected phase source while the encoder still controls the
motor. The current experiment CSV does not expose the selected-source flag or
both angles, so this requires additional verified telemetry support. Establish
acceptable angle tracking first. Maximum-speed testing also needs a defined
mechanical speed rating/ceiling and a validated thermal/loaded test envelope;
do not use the first loss of synchronism or damage as the target condition.

## Setup

The maintained program is under:
C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs

This directory holds the new plans and read-only controller snapshot because
the maintained project currently has read-only filesystem access.
Use the maintained project's Python with -B and absolute plan/output paths;
the older program copy in the parent workspace is not the tested implementation.

First stage: 300 mechanical RPM (600 eRPM at ratio 2), 800-eRPM trip ceiling.
Second stage: 450 mechanical RPM (900 eRPM), 1200-eRPM trip ceiling, only after
successful first-stage evaluation and a stop. These are separate five-second
trials, not a command to immediately execute both stages.

Retain phase limit 15 A, input limit 5 A, absolute current trip 18 A,
Kp 0.064, Ki 0.04, absolute encoder offset 357.52764892578125 degrees,
MTPA enabled and the existing magnet-free model corrections.
No field weakening or sensorless transition is intended at these speeds.

Use baseline-normalized/mcconf.bin for exact pre-write comparison and rollback.
The old baseline differs in six current/voltage measurement offset fields;
do not overwrite today's measurement calibration with yesterday's values.
The 1.9-C motor temperature seen in preflight is not confirmation of a working
winding temperature sensor. The existing short missing-temperature envelope
remains in effect; no 70-A or minute-long testing is enabled.

Preflight recorded: 25.2 V, zero current, zero eRPM, no fault. Follow-up runs
must retain input isolation, watchdog, telemetry
checks, energy/I2t guards, stop verification and baseline restoration.
ADC/PPM remains disabled in RAM until power cycling; set the throttle to zero
before restoring power. The standalone saved motor profile does not include
host-side guards or application input isolation.
