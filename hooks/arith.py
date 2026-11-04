#!/usr/bin/env python3
"""
arith — timed mental arithmetic sprints (Zetamac-style) in a tmux popup.

The sprint runs on its own, outside the model: questions are generated here, every keypress is checked here, and a
correct answer advances at once. Each question has a kind (`× 7`, `− borrow`, `/16`, …) and its time is recorded,
so `weak` mode can draw from the kinds the learner is slowest at (`dist-weak` for distribution kinds). History: `<vault>/practice/.arith.json`.

    arith.py run [mode] [--seconds 120]     open the popup (tmux), wait for it to close, print the summary
    arith.py play [mode] [--seconds 120]    the sprint itself, in the current terminal (the popup runs this)
    arith.py last                           the summary of the newest sprint
    arith.py history [mode]                 the last 10 complete sprints per mode, best and average
    arith.py kinds [mode]                   every ranked kind's median time, slowest first

Modes: core (default), fractions, powers, estimate, mixed, weak; dist (distribution facts) and dist-weak.
"""
import argparse
import json
import math
import os
import random
import shlex
import statistics
import subprocess
import sys
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from fractions import Fraction

import book

CLAUDE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT = os.path.dirname(CLAUDE_DIR)
HISTORY = os.path.join(VAULT, "practice", ".arith.json")

MODES = ("core", "fractions", "powers", "estimate", "mixed", "weak", "dist", "dist-weak")
CONCRETE = ("core", "fractions", "powers", "estimate")
WEAK = {"weak": ("mixed", CONCRETE), "dist-weak": ("dist", ("dist",))}  # weak mode: (its 30% mode, its modes' kinds)
DENOMINATORS = list(range(2, 13)) + [16, 20, 25, 40]
PERCENTS = (5, 10, 12.5, 15, 20, 25, 30, 40, 75)
TOLERANCE = 0.02
WEAK_SHARE = 0.7
SPEED_WINDOW = 50  # a kind's speed: the median over its last 50 correct answers
RANK_FLOOR = 10  # ranked only with at least this many
WEAK_KINDS = 5


# ---------------------------------------------------------------- questions

def _q(text, answer, kind, mode, estimate=False):
    return {"text": text, "answer": answer, "kind": kind, "mode": mode, "estimate": estimate}


def _shortest(d):
    """A Decimal as its shortest string: 0.3750 -> 0.375, 36.0 -> 36."""
    s = format(d.normalize(), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def core(rng):
    op = rng.choice("+−×÷")
    if op in "+−":
        a, b = rng.randint(2, 100), rng.randint(2, 100)
        if op == "+":
            return _q(f"{a} + {b}", str(a + b), "+ carry" if a % 10 + b % 10 >= 10 else "+ no carry", "core")
        s = a + b  # subtraction is addition reversed
        return _q(f"{s} − {a}", str(b), "− borrow" if s % 10 < a % 10 else "− no borrow", "core")
    a, b = rng.randint(2, 12), rng.randint(2, 100)
    if op == "×":
        return _q(f"{a} × {b}", str(a * b), f"× {a}", "core")
    return _q(f"{a * b} ÷ {a}", str(b), f"÷ {a}", "core")  # division is multiplication reversed


def fractions(rng):
    if rng.random() < 0.5:
        d = rng.choice(DENOMINATORS)
        n = rng.randint(1, d - 1)
        value = (Decimal(n) / Decimal(d)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        return _q(f"{n}/{d}", _shortest(value), f"/{d}", "fractions")
    p = rng.choice(PERCENTS)
    while True:
        y = rng.randrange(20, 801, 4)
        value = Fraction(str(p)) * y / 100
        if (value * 10).denominator == 1:  # at most one decimal place
            break
    p_text = f"{p:g}"
    return _q(f"{p_text}% of {y}", _shortest(Decimal(value.numerator) / Decimal(value.denominator)), f"{p_text}% of",
              "fractions")


def powers(rng):
    kind = rng.choice(("square", "2^k", "cube"))
    if kind == "square":
        n = rng.randint(11, 30)
        return _q(f"{n}²", str(n * n), "square 1x" if n < 20 else "square 2x", "powers")
    if kind == "2^k":
        k = rng.randint(5, 20)
        return _q(f"2^{k}", str(2 ** k), "2^k", "powers")
    n = rng.randint(2, 12)
    return _q(f"{n}³", str(n ** 3), "cube", "powers")


def estimate(rng):
    if rng.random() < 0.5:
        while True:
            a, b = rng.randint(12, 999), rng.randint(12, 999)
            if max(a, b) >= 100:
                break
        return _q(f"{a} × {b}", str(a * b), "≈ ×", "estimate", estimate=True)
    a, b = rng.randint(100, 9999), rng.randint(3, 99)
    return _q(f"{a} ÷ {b}", repr(round(a / b, 6)), "≈ ÷", "estimate", estimate=True)


# ---------------------------------------------------------------- distributions
# A distribution fact plus a small calculation. Answers are exact Fractions, typed as an integer, a decimal or a
# fraction. Rates for Expo and Gamma, a variance in N(μ, σ²); conventions that matter are stated in the question.

F = Fraction
RATES = tuple(map(F, ("1", "2", "3", "4", "5", "1/2", "1/3", "1/4")))
PROBS = tuple(map(F, ("1/2", "1/3", "1/4", "1/5", "1/6", "1/10", "2/3", "3/4")))
RHOS = tuple(map(F, ("1/2", "1/3", "1/4", "1/5", "2/3", "3/4", "3/5", "4/5", "-1/2", "-1/3", "-1/4")))
TRIALS, FAILURES = "on {1,2,…}", "on {0,1,…}"  # Geom: trials up to and including the first success, or failures
COIN_WAITS = {"H": 2, "HH": 6, "HT": 4, "HHH": 14, "HHT": 8, "HTH": 10, "HTT": 8}
DIE_WAITS = {"a 6": 6, "a 5 or 6": 3, "an even number": 2, "two 6s in a row": 42}


def _n(x):
    """A number for question text: 3, 1/4, −2."""
    return str(F(x)).replace("-", "−")


def _d(text, answer, kind):
    return _q(text, str(F(answer)), kind, "dist")


def _ask(rng, setup, stats, kind):
    """One of {label: answer} about the setup."""
    label = rng.choice(list(stats))
    return _d(f"{setup}. {label}", stats[label], kind)


def _moments(mean, var):
    return {"E[X]": mean, "Var(X)": var, "E[X²]": var + mean * mean}


def d_bern(rng):
    p = rng.choice(PROBS)
    return _ask(rng, f"X ~ Bern({_n(p)})", _moments(p, p * (1 - p)), "Bern")


def d_bin(rng):
    p = rng.choice(PROBS)
    n = p.denominator * rng.randint(1, 12 // p.denominator)
    return _ask(rng, f"X ~ Bin({n}, {_n(p)})", _moments(n * p, n * p * (1 - p)), "Bin")


def d_geom(rng):
    p = rng.choice(PROBS)
    trials = rng.random() < 0.5
    mean = 1 / p if trials else (1 - p) / p
    return _ask(rng, f"X ~ Geom({_n(p)}) {TRIALS if trials else FAILURES}", _moments(mean, (1 - p) / p ** 2), "Geom")


def d_pois(rng):
    lam = F(1, 2) if rng.random() < 0.1 else F(rng.randint(1, 10))
    return _ask(rng, f"X ~ Pois({_n(lam)})", _moments(lam, lam), "Pois")


def d_dunif(rng):
    a = rng.randint(0, 1)
    b = a + rng.randint(1, 11)
    m = b - a + 1
    return _ask(rng, f"X ~ DUnif{{{a},…,{b}}}", _moments(F(a + b, 2), F(m * m - 1, 12)), "DUnif")


def d_unif(rng):
    a = rng.randint(-2, 4)
    b = a + rng.randint(1, 6)
    return _ask(rng, f"X ~ Unif[{_n(a)}, {_n(b)}]", _moments(F(a + b, 2), F((b - a) ** 2, 12)), "Unif")


def d_expo(rng):
    lam = rng.choice(RATES)
    return _ask(rng, f"X ~ Expo(λ={_n(lam)})", _moments(1 / lam, 1 / lam ** 2), "Expo")


def d_gamma(rng):
    a, lam = rng.randint(2, 5), rng.choice(RATES[:4] + RATES[5:6])
    return _ask(rng, f"X ~ Gamma({a}, λ={_n(lam)})", _moments(a / lam, a / lam ** 2), "Gamma")


def d_beta(rng):
    a, b = rng.randint(1, 4), rng.randint(1, 4)
    s = a + b
    return _ask(rng, f"X ~ Beta({a}, {b})", _moments(F(a, s), F(a * b, s * s * (s + 1))), "Beta")


def d_normal(rng):
    if rng.random() < 0.6:
        mu, var = rng.choice([m for m in range(-3, 6) if m]), rng.randint(1, 9)
        return _d(f"X ~ N({_n(mu)}, {var}). E[X²]", mu * mu + var, "Normal")
    var = rng.randint(1, 5)
    return _ask(rng, f"X ~ N(0, {var})", {"E[X⁴]": 3 * var * var, "Var(X²)": 2 * var * var}, "Normal")


def d_linear(rng):
    v, a = rng.randint(1, 9), rng.choice([-5, -4, -3, -2, 2, 3, 4, 5])
    b = rng.choice([x for x in range(-9, 10) if x])
    return _d(f"Var(X) = {v}. Var({_n(a)}X {'+' if b > 0 else '−'} {abs(b)})", a * a * v, "Var(aX+b)")


def d_pair(rng):
    sx, sy, plus = rng.randint(1, 5), rng.randint(1, 5), rng.random() < 0.5
    if rng.random() < 0.5:
        c = F(rng.randint(1 - sx * sy, sx * sy - 1))
        setup = f"Var(X) = {sx * sx}, Var(Y) = {sy * sy}, Cov = {_n(c)}"
    else:
        while True:
            rho = rng.choice(RHOS)
            c = rho * sx * sy
            if (2 * c).denominator == 1:
                break
            sx, sy = rng.randint(1, 5), rng.randint(1, 5)
        setup = f"SD(X) = {sx}, SD(Y) = {sy}, ρ = {_n(rho)}"
    var = sx * sx + sy * sy + (2 if plus else -2) * c
    return _d(f"{setup}. Var(X {'+' if plus else '−'} Y)", var, "Var(X±Y)")


def d_iid(rng):
    n, mu, v = rng.choice((2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 100)), rng.randint(-2, 6), rng.randint(1, 9)
    stats = {"E[sum]": n * mu, "Var(sum)": n * v, "Var(sample mean)": F(v, n)}
    if n <= 10:
        stats["E[sum²]"] = n * v + (n * mu) ** 2
    return _ask(rng, f"{n} iid draws, mean {_n(mu)}, var {v}", stats, "iid sum")


def d_order(rng):
    a, w, n = rng.choice((0, 0, 0, 1, -1, 2)), rng.randint(1, 6), rng.randint(2, 6)
    kth = lambda k: a + F(w * k, n + 1)  # noqa: E731  the k-th smallest of n: k/(n+1) of the way along
    stats = {"E[min]": kth(1), "E[max]": kth(n), "E[max − min]": F(w * (n - 1), n + 1)}
    if n % 2:
        stats["E[median]"] = kth((n + 1) // 2)
    if n >= 3:
        stats["E[2nd smallest]"] = kth(2)
    return _ask(rng, f"{n} iid Unif[{_n(a)}, {_n(a + w)}] draws", stats, "order stat")


def d_cond(rng):
    vx, vy = rng.randint(1, 9), rng.randint(1, 9)
    mx, my = (rng.randint(-3, 3), rng.randint(-3, 3)) if rng.random() < 0.4 else (0, 0)
    t = vx + vy
    g = t // math.gcd(vx, t)  # s − E[X+Y] a multiple of g: E[X | X+Y = s] is an integer
    d = g * rng.choice([m for m in range(-3, 4) if m and abs(g * m) <= 20])
    s = mx + my + d
    setup = f"X ~ N({_n(mx)}, {vx}), Y ~ N({_n(my)}, {vy}) indep"
    return _ask(rng, setup, {f"E[X | X+Y={_n(s)}]": mx + F(vx * d, t), f"Var(X | X+Y={_n(s)})": F(vx * vy, t)},
                "cond normal")


def d_regress(rng):
    rho = rng.choice(RHOS)
    if rng.random() < 0.5:
        x = rng.choice([v for v in range(-4, 5) if v])
        return _ask(rng, f"Std bivariate normal, ρ = {_n(rho)}", {f"E[Y | X={_n(x)}]": rho * x,
                                                                    f"Var(Y | X={_n(x)})": 1 - rho * rho}, "regression")
    sx, sy = rng.randint(1, 4), rng.randint(1, 4)
    x = sx * rng.choice([v for v in range(-3, 4) if v])
    setup = f"X ~ N(0, {sx * sx}), Y ~ N(0, {sy * sy}) jointly, ρ = {_n(rho)}"
    return _ask(rng, setup, {f"E[Y | X={_n(x)}]": rho * sy * F(x, sx), f"Var(Y | X={_n(x)})": sy * sy * (1 - rho * rho)},
                "regression")


def d_coins(rng):
    if rng.random() < 0.6:
        n = rng.randint(2, 100)
        return _d(f"A: {n + 1} fair coins, B: {n}. P(A has more heads)", F(1, 2), "coins")
    n = rng.randint(1, 3)
    tie = F(math.comb(2 * n, n), 4 ** n)
    return _ask(rng, f"A: {n} fair coins, B: {n}", {"P(A has more heads)": (1 - tie) / 2, "P(same # of heads)": tie},
                "coins")


def d_linearity(rng):
    form = rng.randrange(4)
    if form == 0:
        return _d(f"Random permutation of {rng.randint(3, 8)}. E[# fixed points]", 1, "linearity")
    if form == 3:
        h, t = rng.randint(1, 6), rng.randint(1, 6)
        return _d(f"{h} H and {t} T in random order. E[# runs]", 1 + F(2 * h * t, h + t), "linearity")
    n = rng.randint(3, 12)
    if form == 1:
        return _d(f"{n} fair coin flips. E[# runs]", F(n + 1, 2), "linearity")
    return _d(f"{n} fair coin flips. E[# overlapping HH]", F(n - 1, 4), "linearity")


def d_memoryless(rng):
    s = rng.randint(1, 10)
    if rng.random() < 0.5:
        lam = rng.choice(RATES[:4] + RATES[5:6])
        return _ask(rng, f"X ~ Expo(λ={_n(lam)})", {f"E[X | X > {s}]": s + 1 / lam, f"Var(X | X > {s})": 1 / lam ** 2},
                    "memoryless")
    p = rng.choice(PROBS[:6])
    if rng.random() < 0.5:
        return _d(f"X ~ Geom({_n(p)}) {TRIALS}. E[X | X > {s}]", s + 1 / p, "memoryless")
    p, t = rng.choice(PROBS[:3] + PROBS[6:]), rng.randint(1, 3)
    return _d(f"X ~ Geom({_n(p)}) {TRIALS}. P(X > {s + t} | X > {s})", (1 - p) ** t, "memoryless")


def d_wait(rng):
    form = rng.randrange(3)
    if form == 0:
        pattern = rng.choice(list(COIN_WAITS))
        flipped = pattern.translate(str.maketrans("HT", "TH")) if rng.random() < 0.5 else pattern
        return _d(f"Fair coin. E[flips until {flipped}]", COIN_WAITS[pattern], "waiting time")
    if form == 1:
        target = rng.choice(list(DIE_WAITS))
        return _d(f"Fair die. E[rolls until {target}]", DIE_WAITS[target], "waiting time")
    n = rng.randint(2, 6)
    return _d(f"{n} equally likely types. E[draws to see all]", n * sum(F(1, i) for i in range(1, n + 1)),
              "waiting time")


def _matrix(rows):
    return "[" + ", ".join("[" + ", ".join(_n(x) for x in r) + "]" for r in rows) + "]"


def d_matrix2(rng):
    while True:
        l1 = rng.randint(-2, 6)
        l2 = l1 + rng.randint(1, 5)
        a = rng.randint(-3, 7)
        bc = -(a - l1) * (a - l2)  # tr = l1 + l2 and det = l1·l2
        if bc == 0:
            continue
        b = rng.choice([x for x in range(-9, 10) if x and bc % x == 0])
        c, d = bc // b, l1 + l2 - a
        if abs(c) <= 9 and abs(d) <= 9:
            break
    stats = {"det(A)": l1 * l2, "larger eigenvalue": l2, "smaller eigenvalue": l1, "tr(A²)": l1 * l1 + l2 * l2}
    if l1 * l2:
        stats["tr(A⁻¹)"] = F(l1 + l2, l1 * l2)
    return _ask(rng, f"A = {_matrix([[a, b], [c, d]])}", stats, "2×2 matrix")


def d_triangular(rng):
    form = rng.randrange(3)
    if form == 0:
        logs = rng.sample((0, 2, 3, 5), rng.randint(2, 3))
        entries = ", ".join(f"ln {v}" if v else "0" for v in logs)
        values = [v or 1 for v in logs]  # e^(ln v) = v, e^0 = 1
        return _ask(rng, f"A = diag({entries})", {"tr(e^A)": sum(values), "det(e^A)": math.prod(values)},
                    "triangular matrix")
    diag = [rng.randint(1, 4) for _ in range(rng.randint(2, 3))]
    stats = {"tr(A²)": sum(x * x for x in diag), "det(A⁻¹)": F(1, math.prod(diag))}
    if form == 1:
        stats.update({"tr(A⁻¹)": sum(F(1, x) for x in diag), "det(A³)": math.prod(diag) ** 3})
        return _ask(rng, f"A = diag({', '.join(map(str, diag))})", stats, "triangular matrix")
    n = len(diag)
    rows = [[diag[i] if i == j else rng.randint(-5, 9) if j > i else 0 for j in range(n)] for i in range(n)]
    stats.update({"det(A)": math.prod(diag), "largest eigenvalue": max(diag)})
    return _ask(rng, f"A = {_matrix(rows)}", stats, "triangular matrix")


DIST_KINDS = {"Bern": d_bern, "Bin": d_bin, "Geom": d_geom, "Pois": d_pois, "DUnif": d_dunif, "Unif": d_unif,
              "Expo": d_expo, "Gamma": d_gamma, "Beta": d_beta, "Normal": d_normal, "Var(aX+b)": d_linear,
              "Var(X±Y)": d_pair, "iid sum": d_iid, "order stat": d_order, "cond normal": d_cond,
              "regression": d_regress, "coins": d_coins, "linearity": d_linearity, "memoryless": d_memoryless,
              "waiting time": d_wait, "2×2 matrix": d_matrix2, "triangular matrix": d_triangular}


def dist(rng):
    return DIST_KINDS[rng.choice(list(DIST_KINDS))](rng)


GENERATORS = {"core": core, "fractions": fractions, "powers": powers, "estimate": estimate, "dist": dist}


def mode_of(kind):
    if kind in DIST_KINDS:
        return "dist"
    if kind.startswith("≈"):
        return "estimate"
    if kind[:1] in "+−×÷":
        return "core"
    if kind.startswith("/") or kind.endswith("% of"):
        return "fractions"
    return "powers"


def of_kind(kind, rng):
    """A question of this kind: drawn from its mode until the kind matches."""
    if kind in DIST_KINDS:
        return DIST_KINDS[kind](rng)
    gen = GENERATORS[mode_of(kind)]
    for _ in range(2000):
        q = gen(rng)
        if q["kind"] == kind:
            return q
    return gen(rng)


def generate(mode, rng, weak_kinds=None):
    if mode in WEAK:
        if weak_kinds and rng.random() < WEAK_SHARE:
            slot = rng.randrange(WEAK_KINDS)  # a slot no ranked kind fills is drawn uniformly below
            if slot < len(weak_kinds):
                return of_kind(weak_kinds[slot], rng)
        mode = WEAK[mode][0]
    if mode == "mixed":
        mode = rng.choice(CONCRETE)
    return GENERATORS[mode](rng)


# ---------------------------------------------------------------- answers

def _number(text):
    try:
        return Decimal(text.strip())
    except (InvalidOperation, ValueError):
        return None


def _places(text):
    return len(text.split(".", 1)[1]) if "." in text else 0


def _fraction(text):
    try:
        return F(text.strip())
    except (ValueError, ZeroDivisionError):
        return None


def accepts_fraction(typed, answer):
    """A distribution answer: any integer, decimal or fraction equal to it, or a decimal of at least 4 places equal
    to it rounded half up to those places (1/3: 0.3333)."""
    v = _fraction(typed)
    if v is None:
        return False
    true = F(answer)
    if v == true:
        return True
    places = _places(typed.strip())
    if "/" in typed or places < 4:
        return False
    rounded = (Decimal(true.numerator) / Decimal(true.denominator)).quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP)
    return v == F(rounded)


def accepts(typed, q, enter=False):
    """Whether the typed text answers the question: exact answers on any keypress (at full precision), estimates
    on Enter within 2%."""
    if q.get("mode") == "dist":
        return accepts_fraction(typed, q["answer"])
    v = _number(typed)
    if v is None or not typed.strip():
        return False
    if q.get("estimate"):
        true = Decimal(q["answer"])
        return enter and abs(v - true) <= Decimal(str(TOLERANCE)) * abs(true)
    return v == Decimal(q["answer"]) and _places(typed.strip()) >= _places(q["answer"])


# ---------------------------------------------------------------- history

def load_history():
    if not os.path.exists(HISTORY):
        return {"sprints": []}
    try:
        with open(HISTORY, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("sprints"), list):
            raise ValueError
        return data
    except (OSError, ValueError):
        book.die(f"{book.rel(HISTORY)} cannot be read; fix it or move it away", 1)


def save_sprint(sprint):
    data = load_history()
    data["sprints"].append(sprint)
    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    tmp = HISTORY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, HISTORY)


def kind_speeds(history):
    """{kind: median ms over its last 50 correct answers}, for kinds with at least 10."""
    times = {}
    for sp in history["sprints"]:
        for q in sp.get("questions", []):
            times.setdefault(q["kind"], []).append(q["ms"])
    return {k: statistics.median(v[-SPEED_WINDOW:]) for k, v in times.items() if len(v) >= RANK_FLOOR}


def weak_kinds(history, mode="weak"):
    """The five kinds slowest relative to the other kinds of their own mode, among the weak mode's modes (arithmetic
    for `weak`, distributions for `dist-weak`)."""
    speeds = {k: ms for k, ms in kind_speeds(history).items() if mode_of(k) in WEAK[mode][1]}
    by_mode = {}
    for k, ms in speeds.items():
        by_mode.setdefault(mode_of(k), []).append(ms)
    ratio = {k: ms / statistics.median(by_mode[mode_of(k)]) for k, ms in speeds.items()}
    return sorted(ratio, key=lambda k: (-ratio[k], k))[:WEAK_KINDS]


def _mmss(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def summary(sprint, history):
    sprints = history["sprints"]
    at = next((i for i, x in enumerate(sprints) if x is sprint), None)
    if at is not None:  # compare with the sprints before this one
        sprints = sprints[:at]
    mode = sprint["mode"]
    times = {}
    for q in sprint.get("questions", []):
        times.setdefault(q["kind"], []).append(q["ms"])
    slow = sorted(((statistics.median(v), k) for k, v in times.items()), reverse=True)[:3]
    slowest = "SLOWEST: " + (" · ".join(f"{k} {ms / 1000:.1f} s" for ms, k in slow) if slow else "—")
    if not sprint.get("complete"):
        return f"ARITHMETIC: {mode} · stopped at {_mmss(sprint.get('stopped', 0))} · score {sprint['score']}\n{slowest}"
    prior = [sp["score"] for sp in sprints  # only sprints of the same mode and length compare
             if sp["mode"] == mode and sp.get("seconds") == sprint["seconds"] and sp.get("complete")]
    best = str(max(prior)) if prior else "—"
    avg = f"{statistics.mean(prior[-5:]):.1f}" if prior else "—"
    return (f"ARITHMETIC: {mode} · {sprint['seconds']} s · score {sprint['score']} ({sprint.get('skipped', 0)} skipped)\n"
            f"BEST: {best} · LAST 5 AVERAGE: {avg}\n{slowest}")


# ---------------------------------------------------------------- the sprint

def deadline_left(start, seconds, now):
    """Seconds left by wall clock; a laptop that slept past the end has none."""
    return max(0.0, start + seconds - now)


def play(stdscr, mode, seconds):
    import curses
    curses.curs_set(1)
    curses.use_default_colors()
    try:
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
    except Exception:
        pass
    history = load_history()
    weak = weak_kinds(history, mode) if mode in WEAK else None
    rng = random.Random()
    stdscr.timeout(200)  # redraw the clock while waiting for keys
    q = generate(mode, rng, weak)
    start = shown = time.time()
    typed, flash, score, skipped, done = "", "", 0, 0, []
    stopped = None

    def draw(left):
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        head = f"ARITHMETIC · {mode}"
        right = f"score {score} · {_mmss(left)}"
        try:
            stdscr.addstr(0, 2, head, curses.A_BOLD | curses.color_pair(1))
            stdscr.addstr(0, max(2, w - len(right) - 2), right, curses.A_BOLD)
            line = f"{q['text']} {'≈' if q['estimate'] else '='} {typed}"
            stdscr.addstr(h // 2 - 1, max(2, (w - len(line)) // 2), line, curses.A_BOLD)
            if flash:
                stdscr.addstr(h // 2 + 1, max(2, (w - len(flash)) // 2), flash, curses.color_pair(3))
            keys = "type the answer" + (" · Enter submit" if q["estimate"] else "") + " · Tab skip · Esc stop"
            stdscr.addstr(h - 1, 2, keys[:w - 3], curses.A_DIM)
            stdscr.move(h // 2 - 1, min(w - 2, max(2, (w - len(line)) // 2) + len(line)))
        except curses.error:
            pass
        stdscr.refresh()

    def advance(correct):
        nonlocal q, typed, flash, shown, score, skipped
        if correct:
            done.append({"kind": q["kind"], "ms": int((time.time() - shown) * 1000)})
            score += 1
        else:
            skipped += 1
        was = f"{q['text']} = {q['answer']}" if not correct and q["mode"] == "dist" else ""  # learn it from a skip
        q, typed, flash, shown = generate(mode, rng, weak), "", was, time.time()

    while True:
        left = deadline_left(start, seconds, time.time())
        if left <= 0:
            break
        draw(left)
        try:
            ch = stdscr.get_wch()
        except curses.error:
            continue
        if deadline_left(start, seconds, time.time()) <= 0:
            break  # a key pressed after 0:00 does not count
        if ch == "\x1b":
            stopped = int(time.time() - start)
            break
        if ch in ("\t",):
            advance(False)
        elif ch in ("\n", "\r") or ch == curses.KEY_ENTER:
            if q["estimate"]:
                if accepts(typed, q, enter=True):
                    advance(True)
                elif typed:
                    flash = "not within 2%"
        elif ch in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            typed, flash = typed[:-1], ""
        elif isinstance(ch, str) and ch in "0123456789.-" + "/" * (q["mode"] == "dist") and len(typed) < 12:
            typed, flash = typed + ch, ""
            if not q["estimate"] and accepts(typed, q):
                advance(True)

    sprint = {"date": time.strftime("%Y-%m-%d"), "time": time.strftime("%H:%M"), "mode": mode, "seconds": seconds,
              "complete": stopped is None, "score": score, "skipped": skipped, "questions": done}
    if stopped is not None:
        sprint["stopped"] = stopped
    save_sprint(sprint)  # before the end screen, so a closed popup loses nothing
    curses.curs_set(0)
    stdscr.erase()
    lines = summary(sprint, history).split("\n") + ["", "press any key"]
    for i, ln in enumerate(lines):
        try:
            stdscr.addstr(1 + i, 2, ln, curses.A_BOLD if i == 0 else 0)
        except curses.error:
            pass
    stdscr.refresh()
    curses.flushinp()
    curses.napms(1000)  # the learner is usually mid-answer at 0:00: keys typed now must not close this screen
    curses.flushinp()
    stdscr.timeout(-1)
    stdscr.get_wch()


def popup_command(mode, seconds, height, width="70"):
    inner = " ".join(shlex.quote(x) for x in (sys.executable, os.path.abspath(__file__), "play", mode,
                                                  "--seconds", str(seconds)))
    return ["tmux", "display-popup", "-E", "-w", width, "-h", height, "-T", " arith ", inner]


# ---------------------------------------------------------------- commands

def cmd_play(a):
    import curses
    load_history()  # a corrupt file is refused here, where the message can still be read
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(play, a.mode, a.seconds)


def cmd_run(a):
    if not os.environ.get("TMUX"):
        print(f'NO TMUX: run "python3 .claude/hooks/arith.py play {a.mode}" in another terminal, then /arith last')
        return
    before = len(load_history()["sprints"])
    width = "80" if a.mode in ("dist", "dist-weak") else "70"  # a distribution question is up to 60 characters
    proc = subprocess.run(popup_command(a.mode, a.seconds, "14", width), capture_output=True, text=True)
    if proc.returncode != 0 and "too large" in (proc.stderr or ""):  # a short or narrow pane
        proc = subprocess.run(popup_command(a.mode, a.seconds, "90%", "90%"), capture_output=True, text=True)
    if proc.returncode != 0 and (proc.stderr or "").strip():
        print(f"POPUP FAILED: {proc.stderr.strip()}")
        return
    h = load_history()
    if len(h["sprints"]) <= before:
        print("NO SPRINT RECORDED")
        return
    print(summary(h["sprints"][-1], h))


def cmd_last(a):
    h = load_history()
    if not h["sprints"]:
        print("NO SPRINT RECORDED")
        return
    print(summary(h["sprints"][-1], h))


def cmd_history(a):
    h = load_history()
    for mode in ([a.mode] if a.mode else MODES):
        lengths = sorted({sp.get("seconds") for sp in h["sprints"] if sp["mode"] == mode and sp.get("complete")})
        for secs in lengths:
            scores = [sp["score"] for sp in h["sprints"]
                      if sp["mode"] == mode and sp.get("seconds") == secs and sp.get("complete")][-10:]
            print(f"{mode} {secs} s: {' '.join(map(str, scores))} · best {max(scores)} · "
                  f"average {statistics.mean(scores):.1f}")


def cmd_kinds(a):
    speeds = kind_speeds(load_history())
    for k in sorted(speeds, key=lambda k: -speeds[k]):
        if not a.mode or mode_of(k) == a.mode:
            print(f"{k} {speeds[k] / 1000:.1f} s")


def seconds_arg(text):
    n = int(text)
    if not 10 <= n <= 480:
        raise argparse.ArgumentTypeError("a sprint is 10 to 480 seconds")
    return n


def main(argv=None):
    p = argparse.ArgumentParser(prog="arith.py", description="Timed mental arithmetic sprints.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "play"):
        s = sub.add_parser(name)
        s.add_argument("mode", nargs="?", default="core", choices=MODES)
        s.add_argument("--seconds", type=seconds_arg, default=120)
    sub.add_parser("last")
    s = sub.add_parser("history")
    s.add_argument("mode", nargs="?", choices=MODES)
    s = sub.add_parser("kinds")
    s.add_argument("mode", nargs="?", choices=CONCRETE + ("dist",))
    a = p.parse_args(argv)
    {"run": cmd_run, "play": cmd_play, "last": cmd_last, "history": cmd_history, "kinds": cmd_kinds}[a.cmd](a)


if __name__ == "__main__":
    main()
