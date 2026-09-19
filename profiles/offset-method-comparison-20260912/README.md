# Offline Comparison of Offset Methods

2026-09-12. Delta connection is accepted as confirmed by the user. No rewiring,
current-limit change, motor excitation or encoder-offset write was performed in
this analysis. The adjacent `comparison.json` contains inputs, source paths,
statistics, excluded observations and all non-qualification flags.

## Evidence Used

- Four distinct HFI poses, each revalidated from three physical raw reports.
- The near-return HFI series is held out, not counted as a new training pose.
- Two successful move-and-settle field pilots (06 and 07), plus the settled
  moving step at field 150 degrees in the incomplete sweep.
- Sweep step 0 is excluded from independent equilibrium comparison: it was
  quiet under current but did not exhibit a fresh move-and-settle response.
- The whole sweep remains failed. Using its locally settled step as diagnostic
  data does not turn it into a qualified calibration run.

## HFI Hypothesis, Not a Correction

A candidate 90-mechanical-degree periodic shape was selected because the rotor
has four repeated segments. This symmetry is a hypothesis for the apparent
offset error; it is NOT assumed to prove encoder-error periodicity.

Using electrical degrees for offset and mechanical degrees for theta:

`apparent_offset(theta) = -4.791234 + 6.178099*cos(4*theta) + 0.122968*sin(4*theta)`

The zero-centered axial branch is used: -9.73 degrees is equivalent to 350.27
degrees on the earlier reported branch. The geometry-to-encoder offset has NOT
been redefined as a varying controller setting.

| Diagnostic | Electrical degrees |
| --- | ---: |
| Constant-only training RMS | 4.493801 |
| Periodic-model training RMS | 0.309802 |
| Worst leave-one-pose-out prediction error | 6.608694 |
| Held-out near-return HFI residual | 1.497098 |

Three fitted coefficients and only four independent positions leave little
redundancy. Good training residuals do not establish predictive validity. The
leave-one-pose-out result explicitly prevents treating this as a qualified
correction. No correction lookup table or write-ready profile was generated.

## Cross-Method Comparison

| Moving field observation | Raw encoder, mechanical deg | Field-derived offset, electrical deg | HFI-model prediction | Difference from MODEL |
| --- | ---: | ---: | ---: | ---: |
| Pilot 06, field 120 | 195.627335 | +1.254670 | -1.830316 | +3.084986 |
| Sweep step 1, field 150 | 207.836807 | -4.326387 | -6.925649 | +2.599262 |
| Pilot 07, field 120 | 195.765695 | +1.531390 | -1.882843 | +3.414232 |

These are differences from a fitted model, NOT directly measured errors between
methods at a common pose. The nearest existing HFI position differs by 4.95 to
17.16 mechanical degrees. Folding positions modulo 90 would assume away the very
error periodicity being investigated, so it is NOT accepted as a same-pose match.
The matching code requires actual encoder positions within 0.5 mechanical deg,
with circular wrap handling, and outputs null measured differences otherwise.

## Current Read-Only Snapshot

Following the offline calculation, a read-only controller query returned raw
encoder 207.399904 deg, offset 267.52764892578125 deg, ratio=2, inverted=0.
Currents motor/input/Id/Iq, duty and ERPM were zero, fault 0, bus 24.9 V,
MOS temperature 26.6 C. No command to turn the motor was sent.
This pose is about 0.437 mechanical deg from the moving field observation at
207.836807 deg, potentially suitable for a near-matched independent HFI check.

## Next Physical Prerequisite

With power OFF, mechanically lock the rotor without intentionally turning it,
then confirm readiness. The workbench HFI procedure requires a locked rotor.
After power is restored, verify actual encoder position, fresh calibration and
application isolation before excitation. Keep software fixture state FREE until
the user confirms actual fixation; do not infer fixation from this proposal.
If the encoder pose no longer meets matching tolerance, do not call the result
a direct same-pose validation. Record the actual mismatch and reassess.

## Reproduce

`scripts/compare-offset-methods.py` requires NumPy only for offline fitting.
The motor-control virtual environment was not modified. Use the bundled analysis
Python, from the maintained project root:

```powershell
& 'C:\Users\jando\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m scripts.compare-offset-methods --output profiles/NEW-comparison
```

Verification: project unittest suite ran 143 tests, 140 passed and 3 NumPy-only
tests skipped in that environment. All 5 comparison tests (including those 3)
passed separately in the bundled NumPy runtime. Test cases prevent counting
symmetry-folded positions as same-pose observations, accepting aliased pose
coverage, or promoting a low training error to an approved correction.
