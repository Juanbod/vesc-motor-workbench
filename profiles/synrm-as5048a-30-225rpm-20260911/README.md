# AS5048A: bounded 30 and 225 RPM candidate

Hardware MKSESC_84_100_HP, firmware 6.02, direct AS5048A SPI, configured ratio 2.
No-load evidence only. These tests do not establish continuous duty, maximum
speed, torque under load, or guaranteed starting from every rotor position.

## Final candidate

- Encoder offset: 357.52764892578125 degrees; ratio 2; inverted 0.
- MTPA 1, zero PM flux model, saturation compensation 0, observer type 0.
- Corrected speed source 0, Kp 0.064, Ki 0.04.
- Phase current limit 15 A; battery current limit 5 A; absolute trip 18 A.
- Speed limit +/-600 eRPM, duty limit 0.35; other values retained from baseline.

The XML and binary contain the tested absolute calibration. They are not
portable to a different motor or sensor mounting. The saved motor profile does
not include application input isolation or the host-side test protections.

## Actual hardware results

Each speed trial lasted approximately five seconds. Means below cover the
last approximately 2.5 seconds, after acceleration. Values are mechanical RPM,
derived from encoder angle with the configured ratio 2 for electrical conversion.

| Target RPM | Repetition means, RPM | Highest measured phase current |
| --- | --- | --- |
| 30 | 29.63, 29.16, 28.87 | 2.98 A |
| 225 | 227.04, 227.14, 227.16 | 5.94 A |

All six completed and passed the short-window speed criteria, with no reported
VESC faults. The 225-RPM tests contained instantaneous estimates up to about
243 RPM: good average tracking does not mean zero ripple.

Evidence directories under logs/:

- live-speed-60erpm-20260911-02/01_diagnostic
- live-speed-60erpm-20260911-confirm/01_diagnostic
- live-speed-60erpm-20260911-confirm/02_diagnostic
- live-speed-450erpm-20260911-02/01_diagnostic
- live-speed-450erpm-20260911-confirm/01_diagnostic
- live-speed-450erpm-20260911-confirm/02_diagnostic

Earlier current-mode starts in live-start-12a-20260911-01 succeeded from angles
164.82, 64.51 and 201.62 degrees in 0.828, 0.844 and 0.844 seconds. Peak current
was 9.90 A, below the ramp target 12 A because the success threshold ended the
pulse early. Those starts used Kp 0.08 (irrelevant to current mode), not the
final speed Kp. They are not a complete 12-sector startup qualification.

## Measurement correction

Before live-speed-300erpm-20260911-02, the host estimated speed using timestamps
of every queued encoder packet. A burst could put several angles at nearly
the same receive time. Windows monotonic() also had 15.625-ms resolution.
This inflated rolling speed estimates and caused false overspeed assessments.

The fix uses perf_counter(), unwraps every angle to retain travel, but uses
only the last point in each USB batch for the speed history. A regression test
reproduces batched arrival at a known 150 mechanical RPM and verifies 300 eRPM.

For live-speed-300erpm-20260911-01, long-window angular travel gives 292.36 eRPM,
matching VESC around 292 eRPM, while the old rolling calculation reported about
330 eRPM. Treat old instantaneous encoder_erpm values and speed scores as
superseded; raw angle, travel, measured currents and controller faults remain
available. Historical logs were not rewritten.

## Reproduction and limits

From the project root, with the physical bench ready and attended:

```powershell
.\.venv\Scripts\python.exe scripts/diagnose-start.py --plan config/synrm-speed-60erpm-5s.json --output logs/low-speed-next --baseline logs/synrm-speed-offset90-gains-03/baseline/mcconf.bin --offset-absolute 357.52764892578125 --mtpa 1 --speed --kp 0.064 --ki 0.04 --repeats 3 --armed
```

For 225 RPM, use config/synrm-speed-450erpm-5s.json and a new output directory.
Temperature is unavailable; only the existing five-second diagnostic envelope
was used under the user's manual monitoring. No 70-A or minute-long run was
performed and no thermal protections for extended operation were removed.
Trips for current, voltage, speed, stale data, energy, I2t and loss of control
remain active. A software stop is not a substitute for a guarded rotor and a
physical power cutoff. Do not touch the rotor between automatic attempts.

After each actual run, the motor stopped and its original configuration was
restored and read back. ADC/PPM remains disabled in RAM until power cycling;
set the throttle to zero before restoring power.
