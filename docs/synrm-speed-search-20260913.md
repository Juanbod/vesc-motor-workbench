# Incremental speed search: 12-13 September 2026

## Outcome

The highest fully qualified point is approximately **1816 mechanical RPM**.
The next host setting, 2700 RPM, is prepared but has NOT been physically run:
the required coast-cadence timing qualification failed. No maximum motor rating
has been established. No running command, retry process or scheduled test remains.

The request was to add 500 RPM after a stable test. This runner uses a current
taper, not a speed PID. Thus 1200, 1700, 2200 and 2700 are host cutoff settings,
not claims that the measured shaft speed rises by exactly 500 RPM each time.

## New qualified points

All three passed their complete powered/coast protocol, exact baseline rollback,
and independent reopened-port standstill readback. Figures use the final five
seconds; voltage and input-power estimates are time weighted.

| Host cutoff | Powered duration | Mean mechanical RPM | Final-window range | DC voltage | VESC input-power estimate |
| --- | --- | --- | --- | --- | --- |
| 1200 | 23.804 s | 1048.21 | 1042.73-1053.43 | 24.501 V | 1.470 W |
| 1700 | 23.801 s | 1437.61 | 1426.83-1445.63 | 24.500 V | 1.788 W |
| 2200 | 39.800 s | 1816.00 | 1807.70-1824.37 | 24.500 V | 2.096 W |

Qualified source folders under `logs/`:

- `synrm-speed-1200rpm-5a-smooth-20260912-02`
- `synrm-speed-1700rpm-5a-smooth-20260912-01`
- `synrm-speed-2200rpm-5a-hold-20260912-01`

The last point had a 16.67 RPM span and 1.66 RPM/s endpoint slope. Its transient
peak was 1837.44 RPM, not the stable speed. Command current remained at most 5 A;
final mean Id/Iq vector magnitude was 4.810 A. Recorded input energy was 84.029 J
and I2t was 961.279 A2s. The 40-second stage used separately reviewed 96 J and
1000 A2s budgets; sampled-current/fast-trip guards remained 6/8 A, DC input cap
2 A, duty cap 0.1, and the software speed guard was 2420 RPM.

These are unloaded bench observations, not continuous-duty or all-angle startup
guarantees. The offset remains provisional. Input power is an uncalibrated VESC
estimate, not shaft power or independently measured complete supply consumption.
Motor winding-temperature telemetry is invalid. MOS temperature is monitored.

## Failed attempts retained

- The first 1200 trial reached about 1049 RPM before a 28 ms telemetry delay.
- The first 2200 attempt stopped at startup: 0.044 degrees of encoder variation
  divided by a sub-millisecond interval produced a false reverse-speed estimate.
- The second 2200 attempt stopped around 1309 RPM on a 6.65 ms command interval.
- The third 2200 attempt completed 24 seconds of excitation and reached 1631 RPM,
  but was still accelerating at about 32 RPM/s. A receive-timestamp ambiguity
  also tripped the coast guard. Neither event was reclassified as a successful run.
- The subsequent 40-second 2200 trial passed, including paced coast acquisition.

The passport manifest retains failures separately. The current draft at
`motor-passport-20260913-v01/motor-passport-draft.md` accepts nine historical
qualified runs and excludes five failed runs. Earlier immutable drafts remain.

## Software changes and validation

- Rolling speed windows use deques instead of copying the whole window each sample.
- A fresh quiet 100-120 ms encoder window is required before excitation; small
  idle-angle noise no longer becomes a spurious first-sample speed. Real reverse
  motion is still rejected in regression tests.
- Detected powered acquisition delays issue zero current before diagnostic logging.
- Zero-current probes measure interlock, transmission, waiting, reception, logging
  and cyclic-GC pauses, with selectable 15/60-second duration and coast cadence.
- Optional `--above-normal` changes only the trial process and restores its prior
  scheduling class. It is not a real-time guarantee. See
  [Microsoft scheduling documentation](https://learn.microsoft.com/en-us/windows/win32/procthread/scheduling-priorities).
- Optional `--defer-cyclic-gc` defers cyclic collection only across the bounded
  trial and restores its prior state on exit. Reference-count reclamation is
  unchanged. See [Python GC documentation](https://docs.python.org/3/library/gc.html).
- Optional `--buffered-rx` reuses bytes already present in the serial receive
  buffer; packet lengths, CRC checks and response-command matching remain intact.
  Tests cover short/long packets, adjacent packets, truncation and corrupt CRC.
- An experimental active short wait did not pass coast timing qualification and
  was removed rather than adopted as a workaround. Its diagnostic logs remain.

Final software verification: **235 tests, 232 passed, 3 dependency skips**.

## Why 2700 is blocked

The proposed 2700 stage retains 5 A and the 40-second/96 J/1000 A2s budgets,
with a 2970 RPM software guard and a 5 ms telemetry budget. The latter is tied
to absolute-angle unwrapping, including receive-time uncertainty, not a certified
mechanical rating.

Buffered unpaced polling passed for 60 seconds with a 2.7063 ms maximum command
interval (`synrm-zero-current-timing-2700-buffered-20260913-01`). However, paced
coast polling failed at 5.6344 ms. Experimental active waiting also failed at
6.0033 ms. Neither failed probe applied torque or wrote configuration.

For stages above the 2420 RPM software envelope, the CLI now requires both
`--timing-probe` and `--coast-timing-probe` before opening COM10. The gate checks
matching stage/cadence/runtime options, 60 seconds of raw zero-current timing
evidence, unchanged baseline, verified final standstill and freshness within
10 minutes. A failed summary, raw gap, nonzero command, stale proof or mismatched
runtime is rejected. Missing-proof rejection was exercised with the real CLI;
the requested test output directory was not created.

The next engineering path is to validate an acquisition/control method that does
not depend on tightly spaced Windows receive timestamps, for example verified
controller-side timing and unwrapped revolution information. Such a method has
not been implemented or qualified here. Do not simply widen timing limits,
discard coast violations, or treat an isolated inferred speed spike as RPM evidence.

## Last independent state

The last zero-current readback has motor/input current, Id, Iq, duty and ERPM
all zero; fault 0; DC bus 24.5 V; MOS 26.5 C; encoder 276.130368 degrees.
Application input remains isolated in RAM. Baseline SHA256:

`41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`

Source: `logs/synrm-zero-current-timing-2700-coast-20260913-02/final-readback.json`.
