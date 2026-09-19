# Verified low-speed diagnostic candidate

Controller: MKSESC_84_100_HP, firmware 6.02, direct AS5048A SPI.
This is a bounded bench candidate, not a production or high-speed profile.
Do not transfer its encoder calibration to a different installation.

## Evidence

Three five-second speed trials, with targets 150 then 300 electrical RPM:

| Log directory under logs/ | Mechanical turns | Peak measured phase current | Input energy |
| --- | ---: | ---: | ---: |
| synrm-speed-offset90-gains-01 | 8.4008 | 5.7565 A | 3.7977 J |
| synrm-speed-offset90-gains-02 | 8.4084 | 5.7780 A | 3.7439 J |
| synrm-speed-offset90-gains-03 | 8.3836 | 5.7376 A | 3.7360 J |

All three completed without a controller fault and reported successful original
motor configuration restoration. Initial encoder angles differed. These tests do
not establish reliable startup from every rotor position or under load.
The user visually confirmed counterclockwise movement during the preceding
startup test, logs/synrm-10a-offset90-01.

With the configured ratio of 2, the final target is 150 mechanical RPM.
CORRECTION: the previously reported approximately 170 RPM was based on a biased
host-side rolling speed estimator. Recomputing angular travel over the last
half-second gives approximately 147, 147 and 155 RPM for these three runs.
The old instantaneous encoder_erpm and speed scores are not reliable evidence
of overshoot. See ../synrm-as5048a-30-225rpm-20260911/README.md for the measurement
fix and new hardware trials. This is not an efficiency or torque test.

## Settings and limits

See manifest.json for all changed parameters. Key settings:

- Electrical encoder offset 357.52764892578125 degrees, ratio 2, not inverted.
- MTPA enabled, zero PM flux model, saturation compensation disabled,
  observer type 0, corrected speed source 0.
- Speed Kp 0.08 and Ki 0.04; other PID fields retained from baseline.
- Phase current limit 12 A, input current limit 5 A, absolute trip 18 A.
- Speed limit 600 electrical RPM, duty limit 0.35, no field weakening.

The source baseline contained negative flux linkage with positive Ld-Lq.
This combination makes the firmware's MTPA square-root expression invalid at
small current. The zero-flux correction is specific to the assumed magnet-free
rotor, not a general setting for permanent-magnet motors.

Motor temperature is invalid (approximately -52 C). Trials remain limited to
five seconds with energy/I2t protection and cooldown; long or high-power runs
require valid winding temperature monitoring and a guarded physical setup.

## Repeating the recorded experiment

From the project directory, with VESC Tool disconnected, an unloaded secured
rotor, a clear rotation area, and physical power cutoff available:

```powershell
.\.venv\Scripts\python.exe scripts/diagnose-start.py --plan config/synrm-10a-5s.json --output logs/synrm-speed-confirmation-next --offset-delta 90 --mtpa 1 --speed --kp 0.08 --ki 0.04 --armed
```

IMPORTANT: this command adds 90 degrees to the LIVE baseline. Use it only when
the live encoder offset is the original 267.52764892578125 degrees, ratio 2,
inverted 0, and the original motor is unchanged. Do not run it after loading
this candidate: that would add the offset a second time. Use a new output
directory for each run. The saved XML/bin already contain the absolute offset.

The diagnostic stops the motor and restores its original motor configuration.
The ADC/PPM application remains disabled in RAM until power cycling; its saved
configuration is not changed. Set the throttle to zero before restoring power.
The saved motor profile alone does not provide this input isolation or the
host-side test guards, so manual loading is not equivalent to a guarded run.
