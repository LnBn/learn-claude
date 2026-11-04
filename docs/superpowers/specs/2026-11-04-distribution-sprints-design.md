# Distribution sprints — design

Date: 2026-11-04. Status: agreed in conversation ("fast PRs": spec, then implementation, no plan document).

## Purpose

Quant research online assessments (SIG, Marshall Wace) ask many short closed-form questions: Var of U[1,2], E of the median of three U[0,3] draws, E[X | X+Y] for normals, P(51 coins show more heads than 50), tr(e^A) for a diagonal A. Each needs one distribution fact and a small calculation. Speed comes from knowing the fact cold, which is what a timed sprint trains. `/arith` already runs timed sprints with exact answers, per-kind speeds and a `weak` mode, so this is a new mode of it, not a new tool.

## Modes

| Mode | Questions |
|---|---|
| `dist` | uniform over the 22 kinds below |
| `dist-weak` | 70% from the learner's five slowest distribution kinds, 30% uniform from `dist` |

`/arith dist [seconds]` and `/arith dist-weak [seconds]`, 120 seconds by default, as for every mode.

**Separate weak modes.** `weak` ranks only arithmetic kinds and falls back to `mixed`; `dist-weak` ranks only distribution kinds and falls back to `dist`. `mixed` stays arithmetic. One table (`WEAK`: mode → its fallback mode and the modes whose kinds it ranks) drives both. A single `weak` over both families was rejected: distribution questions take several times longer than arithmetic ones, so they would fill every weak slot. A family argument (`/arith weak dist`) was rejected as a second positional word for one choice. History, `kinds` and `history` cover the new modes with no other change; a kind's mode (`mode_of`) is `dist` for every distribution kind.

## Kinds

A question is `setup. quantity`, then ` = ` and the typed answer, at most 60 characters, plain Unicode. Rates for Expo and Gamma (`λ=` in the text), variances in N(μ, σ²), Var/Cov/E. A convention that matters is in the question (`Geom(1/4) on {1,2,…}` counts trials, `on {0,1,…}` failures).

| Kind | Example | Asks |
|---|---|---|
| `Bern`, `Bin`, `Geom`, `Pois`, `DUnif`, `Unif`, `Expo`, `Gamma`, `Beta` | `X ~ Gamma(3, λ=2). Var(X)` | E[X], Var(X) or E[X²] |
| `Normal` | `X ~ N(0, 4). E[X⁴]` | E[X²]; E[X⁴], Var(X²) for μ = 0 |
| `Var(aX+b)` | `Var(X) = 4. Var(−3X + 5)` | |
| `Var(X±Y)` | `SD(X) = 2, SD(Y) = 3, ρ = 1/2. Var(X − Y)` | with Cov or ρ |
| `iid sum` | `10 iid draws, mean 3, var 2. Var(sample mean)` | E, Var of the sum; Var of the mean; E[sum²] |
| `order stat` | `3 iid Unif[0, 3] draws. E[median]` | min, max, median, 2nd smallest, max − min |
| `cond normal` | `X ~ N(0, 4), Y ~ N(0, 1) indep. E[X \| X+Y=5]` | E and Var given the sum |
| `regression` | `Std bivariate normal, ρ = 1/2. E[Y \| X=3]` | E and Var of Y given X; standard or with variances |
| `coins` | `A: 51 fair coins, B: 50. P(A has more heads)` | n + 1 vs n; n vs n (more heads, a tie) |
| `linearity` | `Random permutation of 8. E[# fixed points]` | fixed points; runs; overlapping HH |
| `memoryless` | `X ~ Expo(λ=2). E[X \| X > 3]` | Expo E, Var given X > s; Geom E and P given X > s |
| `waiting time` | `Fair coin. E[flips until HTH]` | coin patterns, die targets, coupon collector |
| `2×2 matrix` | `A = [[4, 1], [2, 3]]. larger eigenvalue` | det, eigenvalues, tr(A²), tr(A⁻¹); integer eigenvalues |
| `triangular matrix` | `A = diag(ln 2, ln 3). tr(e^A)` | diagonal or upper triangular: det, tr of powers and inverses, e^A |

Parameters keep answers small: integer eigenvalues by construction, E[X | X+Y = s] an integer, 2ρσσ an integer.

## Answers

Answers are exact Fractions, stored canonically (`3`, `1/12`, `-5/2`). A typed answer is accepted on the keypress that makes it equal the answer, as an integer, decimal or fraction (`5/4`, `10/8`, `1.25`), or as a decimal of at least four places equal to the answer rounded half up (`1/12`: `0.0833`). The `/` key works only on a distribution question, so arithmetic questions (`3/8 =`) cannot be answered with themselves. A skipped distribution question shows its answer under the next question until the next key, so a skip still teaches the fact.

The popup is 80 columns wide for the distribution modes (70 for the others).

## Testing

`tests/test_arith_dist.py` checks every kind against an independent computation parsed from the question text alone: exact enumeration of pmfs (Bern, Bin, DUnif, coins), explicit small distributions with the given variance or correlation (Var(aX+b), Var(X±Y), iid sums), Simpson integration of densities (continuous moments, order statistics via the binomial tail, conditional normals along the line X + Y = s, bivariate normal regression), long sums (Geom, Pois), brute force over permutations and sequences (linearity), absorbing Markov chains solved exactly (waiting times), and direct matrix arithmetic with a grid search for eigenvalues. A mutation of each formula was confirmed to fail it. Also: text length, canonical answers, acceptance and its prefixes, the two weak modes kept apart, `kinds dist`, the popup width.

## Out of scope

Review cards from misses; a timer per question; symbolic answers (π, e, √2); new distributions beyond the list.
