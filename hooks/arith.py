#!/usr/bin/env python3
"""
arith — timed mental arithmetic sprints (Zetamac-style) in a tmux popup.

The sprint runs on its own, outside the model: questions are generated here, every keypress is checked here, and a
correct answer advances at once. Each question has a kind (`× 7`, `− borrow`, `/16`, …) and its time is recorded,
so `weak` mode can draw from the kinds the learner is slowest at. History: `<vault>/practice/.arith.json`.

    arith.py run [mode] [--seconds 120]     open the popup (tmux), wait for it to close, print the summary
    arith.py play [mode] [--seconds 120]    the sprint itself, in the current terminal (the popup runs this)
    arith.py last                           the summary of the newest sprint
    arith.py history [mode]                 the last 10 complete sprints per mode, best and average
    arith.py kinds [mode]                   every ranked kind's median time, slowest first

Modes: core (default), fractions, powers, estimate, mixed, weak.
"""
import random
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from fractions import Fraction

MODES = ("core", "fractions", "powers", "estimate", "mixed", "weak")
CONCRETE = ("core", "fractions", "powers", "estimate")
DENOMINATORS = list(range(2, 13)) + [16, 20, 25, 40]
PERCENTS = (5, 10, 12.5, 15, 20, 25, 30, 40, 75)
TOLERANCE = 0.02
WEAK_SHARE = 0.7


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


GENERATORS = {"core": core, "fractions": fractions, "powers": powers, "estimate": estimate}


def mode_of(kind):
    if kind.startswith("≈"):
        return "estimate"
    if kind[:1] in "+−×÷":
        return "core"
    if kind.startswith("/") or kind.endswith("% of"):
        return "fractions"
    return "powers"


def of_kind(kind, rng):
    """A question of this kind: drawn from its mode until the kind matches."""
    gen = GENERATORS[mode_of(kind)]
    for _ in range(2000):
        q = gen(rng)
        if q["kind"] == kind:
            return q
    return gen(rng)


def generate(mode, rng, weak_kinds=None):
    if mode == "weak":
        if weak_kinds and rng.random() < WEAK_SHARE:
            return of_kind(rng.choice(weak_kinds), rng)
        mode = "mixed"
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


def accepts(typed, q, enter=False):
    """Whether the typed text answers the question: exact answers on any keypress (at full precision), estimates
    on Enter within 2%."""
    v = _number(typed)
    if v is None or not typed.strip():
        return False
    if q.get("estimate"):
        true = Decimal(q["answer"])
        return enter and abs(v - true) <= Decimal(str(TOLERANCE)) * abs(true)
    return v == Decimal(q["answer"]) and _places(typed.strip()) >= _places(q["answer"])
