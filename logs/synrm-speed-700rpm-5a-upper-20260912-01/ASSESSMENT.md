# Highest verified operating point, not a motor maximum

The user requested the maximum stable motor speed. Two physical trials were
performed inside the existing 720 mechanical RPM guard. That software guard
has not been relabelled as a mechanical rating. A numerical allowable rotor
speed was requested from the user; no answer was available during these tests.

| Trial | Host taper / cutoff | Powered time | Final five-second speed |
| --- | --- | --- | --- |
| ../synrm-speed-700rpm-5a-smooth-20260912-01 | 520 / 700 RPM | 23.802492 s | Mean 590.868519; range 583.945638..599.531742 RPM |
| This directory | 600 / 700 RPM | 23.802706 s | Mean 637.922778; range 634.082993..641.068852 RPM |

Both passed their bounded final-window stability criterion. In the second run,
the final-window span was 6.985860 RPM and endpoint slope 0.079940 RPM/s.
The overall peak was 648.385300 RPM; it is not the sustained operating speed.
Powered travel was 218.409424 mechanical turns. First 3 degrees of motion were
observed about 0.573425 s into the ramp from a fresh entry angle of 240.073248 deg.

The final-window time-weighted measured Id/Iq norm was 3.100407 A. Maximum
command was 5 A, peak sampled Id/Iq norm 5.289282 A. The host taper was active
throughout the final window: the command stayed below 95% of the available 5 A
while speed exceeded its taper onset. This directly identifies an artificial
host-governed plateau, not evidence of a motor maximum. The program now records
maximum_speed_established=false and classification=host_taper_limited.

Time-weighted final-window bus voltage was 24.6 V, reported input current
0.041629909 A, estimated input power 1.024096 W. Per-sample power ranged from
0.984 to 1.230 W. These are quantized, uncalibrated VESC input estimates, not
shaft power or complete independently measured DC supply consumption. The
recorded powered input-energy estimate was 28.952018 J and Id/Iq I2t was
291.508611 A2s. Winding-temperature telemetry remains invalid.

## Protection and recovery

No hard limit was raised: current command 5 A, observed-current guard 6 A,
fast trip 8 A, input cap 2 A, duty 0.1, speed guard 720 RPM, timing gap 20 ms,
powered budget 24 s, recovery observation 32 s, energy 72 J and I2t 600 A2s.
Both stages end excitation at 700 RPM, rather than resuming after a cutoff.
No active brake or observer-mode transition was requested.

The candidate bytes are identical to earlier 5 A trials:
92e5c10d635744bfe7170225c386024ed7905fef57c7c2fcb9ee4a011aa0a368.
Both runs completed without fault or guard errors, verified standstill, restored
the exact baseline and passed an independent reopened COM10 quiet readback.

Final independent state after the second trial: motor/input currents, Id/Iq,
duty and ERPM all zero; fault 0; bus 24.6 V; MOS 26.7 C; raw encoder
73.125 degrees. Application remains isolated in RAM. Baseline SHA256:
41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562.
There is no running motor command or scheduled retry.

## Next decision

638 RPM is the highest currently verified stable bench point. Neither it nor
the short peak at 648 RPM is a rated or physical maximum. Raising host thresholds
alone can produce another artificial plateau and must not be presented as finding
the limit. A maximum-speed search requires an explicitly bounded allowable
mechanical speed, a specified supply/current envelope, and classification of
the actual limiting mechanism. Current/telemetry/cutoff protections remain active.

Before any larger hard-speed envelope, review encoder sampling ambiguity,
controller-side speed limits, host timing and coast recovery at the proposed
range. The original KV510 is not an allowable RPM rating for the modified rotor.
No stage above the present 720 RPM hard guard has been implemented or run.

Software verification: 208 tests, 205 passed and 3 NumPy-dependent skips.
Tests include both new predecessor links, unchanged controller bytes/guards,
simulated completed trials/recovery, and rejection of the claim that a governed
plateau or full-current plateau by itself establishes the motor maximum.
