# HFI processing and control-path audit, 2026-09-12

## Scope and outcome

Replayed seven saved mode-1 acquisitions, added an offline audit tool and four
tests, and performed ONE additional physical mode-2 acquisition at duty 0.050.
No rotation command, higher-current test, encoder-offset change, firmware update,
or current-protection relaxation was performed. Rotor remains locked.

The audited processing choices do not explain the earlier 7.69 electrical-degree
held-out model error. This is not proof that all software or hardware is correct.
The periodic correction and local +1 deg offset remain unqualified for global use.

## Source review

Reference source is local `bldc-mt6816-inspect`, pinned commit
`f7c2b34e1cff2234cae98be3abf0cd50e249558f`, NOT the working checkout HEAD.
Reported firmware 6.02 and hardware name are not proof of binary identity with
this source; board-specific changes remain a limitation.

- `motor/mcpwm_foc.c:4200`: raw current response is projected onto
  `(sin(phi), -cos(phi))`. L is updated as voltage/(switching_frequency*delta_i)
  only when delta_i > 0.01 A; otherwise an earlier buffer value may remain.
- `motor/mcpwm_foc.c:3698`: saliency angle is minus half the second-bin phase.
  Speed correction and 180-degree branch handling follow it.
- `motor/mcpwm_foc.c:3745`: graph 0 is the saliency angle; graph 1 is actually
  the first-bin angle despite its label. The host correctly uses graph 0.
- `motor/mcpwm_foc.c:3778`: mode 2 exports one sample index per plotting interval,
  NOT an atomic 32-point snapshot. A plotted curve spans many HFI buffer updates.
- `util/utils_math.c:203`: polynomial atan2 approximation.

## Offline checks

`scripts/audit-hfi.py` replays production analysis before evaluating diagnostic
variants. Variants discard 50, 100 or 150 ms and use weighted or unweighted axial
means. Rejected captures never become qualified just because another window looks
better. This code has no serial-port operations or configuration writer.

For four qualified duty-0.100 captures, the largest change from production is
0.572566 electrical deg. Low-duty captures remain rejected; their alternative
means are highly unstable and are not offset estimates.

For an ideal incremental-inductance tensor and 32-point sampling, 1,800 synthetic
axes confirm the min-L mapping to numerical precision (maximum 7.2e-10 deg).
Transcribing the pinned atan2 polynomial gives a maximum axis error of
0.290751 electrical deg on that grid. This is a double-precision model, not a
bit-exact STM32 execution or hardware calibration.

Machine-readable evidence: `audit.json` in this directory.
Verification: 147 unit tests ran, 144 passed, 3 NumPy-runtime tests skipped.

## Physical raw-data check

Source: `logs/locked-hfi-raw-audit-20260912-01/result.json` and its packet,
plot-point and telemetry logs. Pulse command: `measure_ind 0.050`, plot mode 2.
Firmware completion reported 38.24 uH, Lq-Ld 20.81 uH and measurement current
0.73 A. Raw encoder mean 207.175646 mechanical deg; run span 0.263664 deg.

During excitation, 83 exported raw-current samples ranged from 0.091265 to
1.654156 A. NONE was at or below the 0.01 A buffer-update threshold. Thus stale
values from that condition were NOT demonstrated by this capture. Sparse plot
exports cannot exclude unobserved events in the internal buffer.

83 paired exported L/current values had L*delta_i between 23.968873 and
23.968878 uH*A, consistent with the source calculation. This checks the pair
relationship, not the absolute ADC gain or applied phase voltage.
Exported L ranged from 14.490092 to 262.630066 uH: do not substitute these
instantaneous diagnostic values for configured motor inductance.

Two full plotted curves were available. The first failed the sinusoidal-response
fit criterion; the second included a raw-current sample above the existing
1.5 A analysis bound. Neither supplies a calibration candidate. The bound was
not increased and no rejection was discarded. The firmware-reported 0.73 A,
the largest raw delta-current sample, and sampled motor current are different
quantities; none is a captured instantaneous phase-current peak.

Capture cleanup verified zero current, plotting disabled, exact baseline
restoration, app unchanged and no controller fault. The unsuccessful process exit
means rejected measurement quality, not failed recovery.

## Separate startup constraint

Readback still has MTPA=0, field-weakening current=0, encoder offset
267.527648926 deg, flux linkage -4.240488124e-5 Wb and Lq-Ld 1.433364469e-5 H.
Pinned `motor/mcpwm_foc.c:2952` sets Id target to zero in normal encoder control,
except phase-override/open-loop-phase modes. MTPA is applied later at line 3051.
Therefore calibrating the encoder alone does not establish a suitable nonzero
Id/Iq target for a magnet-free reluctance drive.

Do NOT simply enable MTPA on this baseline. Its negative flux linkage can make
the square root for Iq invalid at low command current in the pinned formula.
`vesc_workbench/bench.py:419` already rejects this combination; retain that guard.
Likewise, zero flux cannot be substituted blindly into observer/saturation modes
that divide by flux. No live changes to these parameters were made.

## Final verification and next work

Independent read-only verification: `logs/locked-hfi-raw-audit-20260912-final-readback.json`.
25 quiet samples; motor/input current, Id/Iq, duty and reported ERPM zero,
fault 0, bus 24.9 V, MOS 26.2 C. The winding-temperature reading is invalid.
Motor SHA256 remains
`41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`.
External app remains isolated in RAM; a power cycle requires a new check.

The next drive experiment needs an explicitly reviewed magnet-free current-target
configuration and independent motion/torque evidence, not another blind offset
fit. Prepare and validate it offline first. Do not send rotation commands while
the fixture is locked; require physical fixture-removal confirmation before any
free-rotor test. Absolute offset, startup and full-speed stability remain open.
