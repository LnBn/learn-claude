---
name: arith
description: Timed mental arithmetic sprints (Zetamac-style) in a tmux popup — core + − × ÷, fractions and percentages, powers, estimates, mixed, or a weak mode drawn from the learner's slowest kinds of question; also distribution sprints (means, variances, order statistics, conditional normals, standard results, small matrices) for quant online assessments. Use with `/arith [mode] [seconds]`, `/arith last`, `/arith history [mode]`, or when the learner asks for mental arithmetic, speed maths, a Zetamac sprint or distribution speed drills.
argument-hint: [core | fractions | powers | estimate | mixed | weak | dist | dist-weak] [seconds, 10–480] | last | history [mode]
allowed-tools: Bash(python3 .claude/hooks/arith.py *), Bash(python3 .claude/hooks/md_log.py *)
---

Arguments: `$ARGUMENTS`

A sprint runs on its own in a popup: `arith.py` generates the questions, checks every keypress and keeps time. You start it and report on it. Nothing of the sprint goes through you while it runs.

`dist` asks distribution facts with a small calculation (`X ~ Expo(λ=3). Var(X)`), answered as an integer, a decimal or a fraction. `dist-weak` draws mostly from the learner's slowest distribution kinds; `weak` draws only from arithmetic kinds.

| Arguments | What to do |
|---|---|
| none, a mode, a mode and seconds | **A sprint** |
| `last` | `python3 .claude/hooks/arith.py last`; show the output |
| `history [mode]` | `python3 .claude/hooks/arith.py history [mode]`; show the output |

## A sprint

1. **Run it**, with a Bash timeout of 600000 ms (a 120-second sprint and its end screen outlast the default two minutes):
   ```
   python3 .claude/hooks/arith.py run <mode, default core> [--seconds <n>]
   ```
   Do not write anything before the call: the popup covers the terminal while it runs.
2. On `NO TMUX: …`, relay that line and stop. On `POPUP FAILED: …`, say in one line that the popup could not open and give tmux's reason. On `NO SPRINT RECORDED` (the popup closed before a sprint was saved), say so in one line and stop. If the call times out, the sprint is still saved: run `python3 .claude/hooks/arith.py last` and continue from step 3.
3. **Link today's practice note:**
   ```
   python3 .claude/hooks/md_log.py link "practice/<today, YYYY-MM-DD>.md" --session ${CLAUDE_SESSION_ID} --from-now
   ```
4. **The reply:** the heading `### Arithmetic — <mode>` (`### Distributions — <mode>` for `dist` and `dist-weak`), then two or three sentences from the summary the command printed: the score, how it compares with the best and the last-5 average (or that it is the first sprint in this mode), and the slowest kinds. When one kind is clearly slower than the rest, one concrete tip for it, e.g. `× 7`: 7 × n = 5n + 2n; `× 9`: 10n − n; `− borrow`: subtract a round number, then add back; `/16`: halve the eighths (1/8 = 0.125, so 1/16 = 0.0625). For a distribution kind, the tip is the fact in one line of LaTeX, e.g. `Beta`: $\operatorname{Var}(X) = \frac{ab}{(a+b)^2(a+b+1)}$; `cond normal`: $E[X \mid X+Y=s] = \mu_X + \frac{\sigma_X^2}{\sigma_X^2+\sigma_Y^2}(s - \mu_X - \mu_Y)$; `order stat`: the $k$-th smallest of $n$ iid $\mathrm{Unif}[a,b]$ has mean $a + (b-a)\frac{k}{n+1}$. For a stopped sprint, just the score and when it stopped. Nothing else: no encouragement, no plan.
