# SciPy for the vertical profile's banded solve (#516)

**Date:** 2026-11-13. **Issue:** #516, PR #532. **Code:** `tools/track_profile.py` (`_D.system`).

**Status:** accepted by the user (2026-11-13, PR #532):
- for the trial: "Let's install scipy and compare options a and b against what you get now";
- for the decision, on the measurements below: "Yes let's go with scipy and we can merge all PRs".

## The change

`vertical_profile` and `banded_profile` solve their ADMM steps' system, diag(w) + Dᵀ diag(λ) D, with LAPACK's banded Cholesky factor through SciPy:
- the system is pentadiagonal and the same for every step of a solve;
- `scipy.linalg.lapack.dpbtrf` factors it once;
- `dpbtrs` solves with the factor each step, in O(n).

SciPy (BSD-3-Clause) is a build dependency, in the user site packages beside numpy, and CI installs it.

## Why

numpy has no banded or triangular solver.
- The pure-Python banded factorisation (`_factor`, `_back`) was 52 % of `line_heights.py` (#205).
- So since #205 each step multiplied by the system's dense inverse, which costs O(n²) a step and O(n³) to build. On the heights' 16.5 km run (n 3303) a step took 1.66 ms and the inverse 0.87 s.
- The rounds of meeting half way solve that run six times, one after another, and set the heights' pace: 72 of 210 s (#516).

On that run the banded solve:
- takes 50 µs a step and 0.3 ms for the factor;
- differs from the inverse's answers by at most 2.6e-12 m, with a smaller residual (2.3e-10 against 4.7e-10).

## Measured

`rebuild.py --parallel --from line_heights`, five lines, 24 cores, through the heavy-job queue. The four were run back to back, then again in reverse order.

| | dense inverse | (a) warm start | (b) banded factor | (a)+(b) |
|---|---|---|---|---|
| `line_heights` | 213, 211 s | 186, 186 s | 131, 130 s | 128, 128 s |
| its solves | 98, 99 s | 76, 75 s | 20, 20 s | 16, 16 s |
| the steps' CPU | 1014, 1022 s | 878, 888 s | 384, 380 s | 379, 376 s |
| outputs against the dense inverse's | | 253 heights on line 17, up to 16 mm | byte-identical | as (a) |

With #517 merged, `line_heights` took 125–126 s in four runs: the staging 54–55 s, the solves 18–19 s. 4 BLAS threads × 6 workers and 1 × 12 took the same, since the solves now wait on the chains they are pinned to, not on the workers. The data was byte-identical to main's in each run, its line steps rebuilt in the first.

## Not chosen

- **(a) a warm start:** each re-solve started where the same solve of the run ended last time.
  - It stops elsewhere within the tolerance. The rounds of meeting half way feed one chain's heights into another's pins, so they ended after 4 rounds instead of 6, with other gaps.
  - It moved the heights at one junction on line 17 (s 16 343, a place for review) by up to 16 mm.
  - It saved 25 s alone, and 4 s on top of (b).
- **Staying with the dense inverse:** 210 s against the issue's 160.
- **A compiled solver of our own, or numba:** a heavier dependency. numba is ~50 MB with llvmlite and follows new Python releases late ([the ground's record](2026-11-05-ground-built-offline.md)).

## Consequences

- Every machine that builds needs `python -m pip install --user scipy` (DATA.md).
- What kept the inverse fast is gone:
  - the products Dᵀ diag(λ) D and the inverses kept between calls;
  - the worker with 12 BLAS threads for the long run.
- The [vertical profile's record](2026-11-02-vertical-profile.md) said "no SciPy"; it points here now.
