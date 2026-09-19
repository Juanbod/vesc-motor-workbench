# Two completed smooth-current trials, 2026-09-12

Two real hardware trials used stage speed_540rpm_5a_smooth. Both completed the
reviewed powered duration and final-window stability criterion, with no fault,
current-tracking, timing, coast or travel guard failure. Each was followed by
verified standstill, exact baseline restoration and an independent COM10 quiet
readback. There are no running motor commands or scheduled repeats.

## Physical results

Trial 1: ../synrm-speed-540rpm-5a-smooth-20260912-01
Trial 2: this directory.

| Metric | Trial 1 | Trial 2 |
| --- | --- | --- |
| Actual starting raw angle | 288.566880 deg | 86.264648 deg |
| First 3 degrees of travel | 0.677537 s | 0.676528 s |
| First 400 RPM | 3.849551 s | 3.832513 s |
| Powered duration | 23.806696 s | 23.802655 s |
| Powered mechanical turns | 163.190064 | 163.141602 |
| Peak windowed encoder speed | 466.823453 RPM | 466.574630 RPM |
| Final ~5 s mean speed | 462.543280 RPM | 462.099955 RPM |
| Final ~5 s speed range | 460.413513..464.182434 RPM | 458.269480..465.435240 RPM |
| Final-window peak-to-peak speed | 3.768921 RPM | 7.165760 RPM |
| Final-window endpoint slope | -0.118292 RPM/s | +0.211530 RPM/s |
| Final-window mean command current | 2.767088 A | 2.782468 A |
| Final-window mean measured Id/Iq norm | 2.763402 A | 2.779365 A |
| Peak sampled Id/Iq norm | 5.289282 A | 5.287882 A |
| Sampled input energy | 25.439987 J | 25.557505 J |
| Sampled Id/Iq squared-current integral | 228.287344 A2s | 229.675052 A2s |
| Powered observations | 3267 | 3427 |
| Maximum powered RPC latency | 7.264600 ms | 1.893100 ms |
| Maximum observed MOS temperature | 26.5 C | 26.6 C |

The current command rose no faster than 3 A/s to a maximum of 5 A. Current
then tapered automatically with measured speed, settling near 2.8 A. The
sampled Id/Iq norm is neither DC input current nor an independently measured
phase-current peak. Winding-temperature telemetry is invalid and was not
treated as a winding-temperature measurement.

These are two starts from distinct raw shaft angles, not proof of guaranteed
startup at all electrical angles or under load. No torque sensor is available.
The approximately 462 RPM plateau is a result of the host's current taper and
motor behavior under these bench conditions, not the motor's maximum speed or
tracking of a commanded 462 RPM setpoint. The 540 RPM cutoff was not reached.

## Software changes and verification

The smooth stage starts reducing current at 400 RPM rather than 525 RPM.
The zero-current cutoff remains 540 RPM; reaching it now ends this stage with
zero-current recovery instead of resuming torque. All steady current-tracking
tolerances and other operating protections are unchanged. No transient grace
period or blind interval was introduced.

Completion additionally requires a final five-second speed window with no
sample gaps over 20 ms, minimum speed >=420 RPM, span <=20 RPM and absolute
endpoint slope <=2 RPM/s. The window may be one sample interval shorter than
five seconds. Both actual acquisitions passed this defined criterion.

Coast guard records now include adjacent response intervals and both RPC
latencies. The old failed trial's 961.07 RPM apparent spike corresponds to a
possible interval-average speed range of approximately 506.09..1059.58 RPM,
assuming each angle was acquired during its RPC. Thus that record cannot prove
or exclude a 720 RPM excursion. Its failed guard was not suppressed; none of
the old logs was rewritten. Both new trials passed the unchanged coast guard.

Offline replay of the old speed trace showed the revised taper requesting
about 1.52 A instead of 4.59 A immediately before the old cutoff. This replay
is a controller-response comparison only, not a predicted motor trajectory.

The software suite ran 201 tests: 198 passed, 3 NumPy-dependent tests skipped.
Tests cover identical candidate bytes and operating caps, earlier current taper,
stability duration/gaps/range/slope, latency uncertainty, qualified-predecessor
validation, cutoff latching, coast-guard preservation and recovery. An
illustrative quadratic-current plant settles; an aggressive simulated plant
still reaches cutoff and is correctly rejected. Neither model is calibrated
as a physical motor simulation.

Both new trials use the independently qualified speed_540rpm_3a predecessor
in ../synrm-speed-540rpm-3a-20260912-02. The failed narrow-taper 5 A run is
diagnostic evidence only, not a successful predecessor.

## Configuration and final state

The controller candidate is byte-for-byte identical to the earlier 5 A trial.
This improvement is in the external host supervisor, not a new standalone
controller profile. Loading only the candidate without this supervisor does
not reproduce the tested speed behavior.

Candidate SHA256:
`92e5c10d635744bfe7170225c386024ed7905fef57c7c2fcb9ee4a011aa0a368`

Baseline SHA256:
`41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`

Current caps: +/-5 A, sampled-current guard 6 A, fast trip 8 A, DC input
2 A, duty 0.1, energy 72 J, integral 600 A2s, powered duration 24 s,
recovery observation 32 s, mechanical speed guard 720 RPM, timing gap 20 ms.
Current slew is 3 A/s; no active brake, field weakening or observer transition
was requested. The 1.020427465-degree candidate offset remains provisional.

Final independent readback after trial 2: motor/input currents, Id/Iq, duty
and reported ERPM all zero; fault 0; bus 24.7 V; MOS 26.6 C; encoder
78.464352 degrees. Exact baseline restored, external application isolated in
RAM. The active offset is the restored baseline value, not the temporary test
offset. A power cycle can restore a different application configuration, so
fresh preflight remains mandatory.

Net coast travel was 14130.747056 degrees for trial 1 and 13621.376952 degrees
for trial 2. Zero current does not mean immediate mechanical standstill.

Encoder-source selection remains an inference from the reviewed firmware source
and configuration, not a directly sampled source flag or firmware-binary
attestation. No mechanical maximum-speed qualification was made. A later
speed increase requires a separately reviewed stage; do not remove the timing,
current or coast guards to make a result pass.
