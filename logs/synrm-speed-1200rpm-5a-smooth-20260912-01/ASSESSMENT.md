# First +500 RPM setting increment: telemetry-aborted trial

The user requested increments of 500 RPM per test. One physical trial increased
the host cutoff from 700 to 1200 mechanical RPM, with taper onset at 1000 RPM.
This supervisor commands current, not a speed PID: the setting increment is not
a promise of a 500 RPM increase in achieved shaft speed.

## Reviewed envelope and preflight

Command current remained 5 A, sampled current guard 6 A, fast trip 8 A, input
cap 2 A, duty cap 0.1, powered budget 24 s, energy budget 72 J and I2t 600 A2s.
The hard software speed guard changed from 720 to 1320 mechanical RPM
(controller ERPM limits +/-2640 with the existing ratio-2 interpretation).
This is an experimental software envelope, not a certified rotor rating.
No current increase, active brake or observer transition was requested.

Acquisition/command gap allowance tightened from 20 to 10 ms, with 2 ms pauses.
Including one prior RPC latency, 1320*6*(0.01+0.01) = 158.4 degrees, below the
180-degree absolute-angle unwrapping ambiguity boundary under those bounds.
Recovery allowance increased to 48 s; zero current is not an instantaneous stop.

The preceding zero-current probe in ../synrm-zero-current-timing-1200-20260912-01
passed: 4038 samples in 15 s, maximum command interval 6.2147 ms, maximum
GET_VALUES latency 1.5604 ms, no intervals over 10 ms. It wrote no configuration
and verified zero current and unchanged baseline. This did not guarantee
worst-case timing during the powered run.

## Observed before the interruption

5182 accepted powered observations cover about 22.4744 s. Before the bad gap:

| Quantity | Value |
| --- | --- |
| Last valid five-second mean RPM, time weighted | 1048.569550 |
| Same window range | 1043.363226 to 1053.593968 RPM |
| Window span / endpoint slope | 10.230742 RPM / 0.576668 RPM/s |
| Peak among accepted powered observations | 1055.913177 RPM |
| Last accepted speed | 1051.867844 RPM |
| Bus voltage | 24.6 V |
| Final-window VESC input-current estimate | 0.06 A |
| Final-window VESC input-power estimate | 1.476 W |
| Last accepted current command | 3.784893 A |
| Peak sampled Id/Iq vector magnitude | 5.344530 A |
| Recorded pre-gap input energy / I2t | 38.071428 J / 406.273992 A2s |

The contiguous pre-gap five-second window satisfies the local stability
criterion. The whole trial does NOT qualify: it aborted before the required
duration and failed timing/coast guards. The tapered current also makes this
an artificial operating plateau, not evidence of a motor maximum.
Input power is an uncalibrated VESC estimate, not shaft power or independently
measured complete supply consumption. Winding-temperature telemetry is invalid.

## Failure evidence and recovery

The next powered response had GET_VALUES latency 28.1741 ms and arrived
37.1124 ms after the previous response. The runner rejected it before updating
the accepted speed history and commanded zero. Cause within Windows, USB,
serial handling or firmware has not been isolated; it is not proven to be
loss of motor synchronism. Fault codes remained zero in recorded telemetry.

The first stopping response arrived only 1.9251 ms after the delayed response.
Naively differencing these receive timestamps gives 5520 RPM. The diagnostic
acquisition-uncertainty interval is approximately 353 to 8342 RPM and spans the
1320 RPM guard; this cannot establish or exclude a real overspeed. Moreover,
the preceding 37 ms gap breaks the reviewed unwrapping timing envelope.
Do not report the 5520 RPM artifact as measured maximum shaft speed, and do
not dismiss the guard violation as harmless. The zero-current stop remained
latched and no higher-speed or automatic retry trial was launched.

Measured Id and Iq were zero in the second stopping response, approximately
5.0164 ms after the rejected powered response. After coast-down the exact
baseline was restored. Independent reopened-COM10 readback confirms standstill,
zero motor/input current, zero Id/Iq, duty and ERPM, fault 0, bus 24.6 V and
MOS temperature about 26.7 C. External application remains isolated in RAM.

Baseline SHA256:
41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562

Candidate SHA256:
ae05c2fd1fa86f5b0c5e8414ac5aa69ae836d876c5e4875087fbaa494e98b43d

## Disposition

Include this attempt in the passport evidence manifest, but exclude it from
qualified operating points. The highest fully qualified run remains about
638 RPM; the approximately 1049 RPM pre-interruption window is provisional.
The motor's maximum stable speed has not been found. Do not progress to a
1700 RPM setting or widen timing guards using this failed trial as predecessor.
Next work is timing-path diagnosis and validation, then a repeat of this same
bounded setting before any further +500 RPM increment.

Software verification before excitation: 209 tests, 206 passed, 3 dependency
skips. Coverage includes the new strict predecessor link, only ERPM fields
changing in controller bytes, retained current/energy caps, tightened timing,
simulated completion/rollback, and rejection of invalid speed/timing inputs.
