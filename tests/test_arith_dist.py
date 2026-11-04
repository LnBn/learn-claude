"""The `dist` mode of arith.py: every kind's answers checked against an independent computation (exact enumeration,
numerical integration, an absorbing Markov chain or brute force) parsed from the question text alone."""
import ast
import itertools
import json
import math
import os
import random
import re
import shutil
import tempfile
import unittest
from fractions import Fraction as F
from pathlib import Path

from tests._vault import make_vault, run
import arith  # noqa: E402


def num(text):
    return F(text.replace("−", "-"))


def simpson(f, lo, hi, n=2000):
    h = (hi - lo) / n
    s = f(lo) + f(hi) + sum((4 if i % 2 else 2) * f(lo + i * h) for i in range(1, n))
    return s * h / 3


def stat_of(label, m1, m2):
    """E[X], Var(X) or E[X²] from the first two raw moments."""
    return {"E[X]": m1, "Var(X)": m2 - m1 * m1, "E[X²]": m2}[label]


def pmf_moments(pmf):
    return sum(p * x for x, p in pmf.items()), sum(p * x * x for x, p in pmf.items())


def pdf_moments(pdf, lo, hi, n=4000):
    mass = simpson(pdf, lo, hi, n)
    return simpson(lambda x: x * pdf(x), lo, hi, n) / mass, simpson(lambda x: x * x * pdf(x), lo, hi, n) / mass


def normal_pdf(mu, var):
    return lambda x: math.exp(-(x - mu) ** 2 / (2 * var)) / math.sqrt(2 * math.pi * var)


def matrix(text):
    return [[F(x) for x in row] for row in ast.literal_eval(text.replace("−", "-"))]


def det(m):
    if len(m) == 1:
        return m[0][0]
    return sum((-1) ** j * m[0][j] * det([r[:j] + r[j + 1:] for r in m[1:]]) for j in range(len(m)))


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def inverse(m):
    n = len(m)
    aug = [list(r) + [F(int(i == j)) for j in range(n)] for i, r in enumerate(m)]
    for c in range(n):
        piv = next(r for r in range(c, n) if aug[r][c] != 0)
        aug[c], aug[piv] = aug[piv], aug[c]
        aug[c] = [x / aug[c][c] for x in aug[c]]
        for r in range(n):
            if r != c:
                aug[r] = [x - aug[r][c] * y for x, y in zip(aug[r], aug[c])]
    return [r[n:] for r in aug]


def charpoly(m, x):
    return det([[m[i][j] - (x if i == j else 0) for j in range(len(m))] for i in range(len(m))])


def eigenvalues(m):
    """The real roots of det(A − xI), found on a grid of quarters in [−10, 20] (exact zeros; any sign change between
    grid points, a root off the grid, fails)."""
    grid = [F(k, 4) for k in range(-40, 81)]
    vals = [charpoly(m, x) for x in grid]
    assert all(v == 0 or w == 0 or (v > 0) == (w > 0) for v, w in zip(vals, vals[1:]))
    return [x for x, v in zip(grid, vals) if v == 0]


def expected_steps(start, step):
    """Expected number of steps to absorption from `start`, where step(state) is [(prob, next state or None)]: an
    exact linear solve over the reachable transient states."""
    states, todo = [start], [start]
    while todo:
        for _, t in step(todo.pop()):
            if t is not None and t not in states:
                states.append(t)
                todo.append(t)
    idx, n = {s: i for i, s in enumerate(states)}, len(states)
    rows = []  # E_s − Σ P(s→t) E_t = 1
    for s in states:
        row = [F(0)] * n + [F(1)]
        row[idx[s]] += 1
        for p, t in step(s):
            if t is not None:
                row[idx[t]] -= p
        rows.append(row)
    return solve(rows)[idx[start]]


def solve(rows):
    n = len(rows)
    a = [list(r) for r in rows]
    for c in range(n):
        piv = next(r for r in range(c, n) if a[r][c] != 0)
        a[c], a[piv] = a[piv], a[c]
        a[c] = [x / a[c][c] for x in a[c]]
        for r in range(n):
            if r != c and a[r][c] != 0:
                a[r] = [x - a[r][c] * y for x, y in zip(a[r], a[c])]
    return [a[i][n] for i in range(n)]


def pattern_wait(pattern, alphabet):
    """Expected draws (uniform over the alphabet) until the pattern appears: states are the matched prefix length."""
    def step(k):
        out = []
        for c in alphabet:
            s = pattern[:k] + c
            j = next(j for j in range(len(s), -1, -1) if pattern.startswith(s[len(s) - j:]))
            out.append((F(1, len(alphabet)), None if j == len(pattern) else j))
        return out
    return expected_steps(0, step)


# ---------------------------------------------------------------- one independent check per kind

def check_named(kind, setup, label):
    if kind == "Bern":
        p = num(re.fullmatch(r"X ~ Bern\((.+)\)", setup)[1])
        return stat_of(label, *pmf_moments({0: 1 - p, 1: p}))
    if kind == "Bin":
        n, p = re.fullmatch(r"X ~ Bin\((\d+), (.+)\)", setup).groups()
        n, p = int(n), num(p)
        return stat_of(label, *pmf_moments({k: math.comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(n + 1)}))
    if kind == "Geom":
        p, first = re.fullmatch(r"X ~ Geom\((.+)\) on \{(\d),(\d),…\}", setup).groups()[:2]
        p, first = float(num(p)), int(first)
        return stat_of(label, *pmf_moments({k: (1 - p) ** (k - first) * p for k in range(first, 3000)}))
    if kind == "Pois":
        lam = float(num(re.fullmatch(r"X ~ Pois\((.+)\)", setup)[1]))
        pmf, p = {}, math.exp(-lam)
        for k in range(150):
            pmf[k], p = p, p * lam / (k + 1)
        return stat_of(label, *pmf_moments(pmf))
    if kind == "DUnif":
        a, b = map(int, re.fullmatch(r"X ~ DUnif\{(\d+),…,(\d+)\}", setup).groups())
        return stat_of(label, *pmf_moments({k: F(1, b - a + 1) for k in range(a, b + 1)}))
    if kind == "Unif":
        a, b = (float(num(x)) for x in re.fullmatch(r"X ~ Unif\[(.+), (.+)\]", setup).groups())
        return stat_of(label, *pdf_moments(lambda x: 1 / (b - a), a, b))
    if kind == "Expo":
        lam = float(num(re.fullmatch(r"X ~ Expo\(λ=(.+)\)", setup)[1]))
        return stat_of(label, *pdf_moments(lambda x: lam * math.exp(-lam * x), 0, 60 / lam))
    if kind == "Gamma":
        a, lam = re.fullmatch(r"X ~ Gamma\((\d+), λ=(.+)\)", setup).groups()
        a, lam = int(a), float(num(lam))
        pdf = lambda x: lam ** a * x ** (a - 1) * math.exp(-lam * x) / math.gamma(a)  # noqa: E731
        return stat_of(label, *pdf_moments(pdf, 0, 80 / lam))
    if kind == "Beta":
        a, b = map(int, re.fullmatch(r"X ~ Beta\((\d+), (\d+)\)", setup).groups())
        return stat_of(label, *pdf_moments(lambda x: x ** (a - 1) * (1 - x) ** (b - 1), 0, 1))
    if kind == "Normal":
        mu, var = (float(num(x)) for x in re.fullmatch(r"X ~ N\((.+), (\d+)\)", setup).groups())
        pdf, sd = normal_pdf(mu, var), math.sqrt(var)
        m = {k: simpson(lambda x: x ** k * pdf(x), mu - 14 * sd, mu + 14 * sd, 4000) for k in (2, 4)}
        return {"E[X²]": m[2], "E[X⁴]": m[4], "Var(X²)": m[4] - m[2] ** 2}[label]


def check_linear(setup, label):
    v = int(re.fullmatch(r"Var\(X\) = (\d+)", setup)[1])
    a, sign, b = re.fullmatch(r"Var\((.+)X ([+−]) (\d+)\)", label).groups()
    a, b = num(a), int(b) * (1 if sign == "+" else -1)
    pmf = {-3: F(v, 18), 0: 1 - F(v, 9), 3: F(v, 18)}  # a variable with variance v
    m1, m2 = pmf_moments({a * x + b: p for x, p in pmf.items()})
    return m2 - m1 * m1


def check_pair(setup, label):
    m = re.fullmatch(r"Var\(X\) = (\d+), Var\(Y\) = (\d+), Cov = (.+)", setup)
    if m:
        sx, sy = math.isqrt(int(m[1])), math.isqrt(int(m[2]))
        assert sx * sx == int(m[1]) and sy * sy == int(m[2])
        rho = num(m[3]) / (sx * sy)
    else:
        sx, sy, rho = re.fullmatch(r"SD\(X\) = (\d+), SD\(Y\) = (\d+), ρ = (.+)", setup).groups()
        sx, sy, rho = int(sx), int(sy), num(rho)
    assert abs(rho) <= 1
    sign = 1 if re.fullmatch(r"Var\(X ([+−]) Y\)", label)[1] == "+" else -1
    joint = {(u * sx, w * sy): (1 + rho * u * w) / 4 for u in (-1, 1) for w in (-1, 1)}  # Corr(X, Y) = ρ
    m1 = m2 = 0
    for (x, y), p in joint.items():
        m1, m2 = m1 + p * (x + sign * y), m2 + p * (x + sign * y) ** 2
    return m2 - m1 * m1


def check_iid(setup, label):
    n, mu, v = re.fullmatch(r"(\d+) iid draws, mean (.+), var (\d+)", setup).groups()
    n, mu, v = int(n), num(mu), int(v)
    one = {mu - 3: F(v, 18), mu: 1 - F(v, 9), mu + 3: F(v, 18)}
    total = {F(0): F(1)}
    for _ in range(n):
        nxt = {}
        for s, p in total.items():
            for x, q in one.items():
                nxt[s + x] = nxt.get(s + x, 0) + p * q
        total = nxt
    if label == "Var(sample mean)":
        m1, m2 = pmf_moments({s / n: p for s, p in total.items()})
        return m2 - m1 * m1
    m1, m2 = pmf_moments(total)
    return {"E[sum]": m1, "Var(sum)": m2 - m1 * m1, "E[sum²]": m2}[label]


def check_order(setup, label):
    n, a, b = re.fullmatch(r"(\d+) iid Unif\[(.+), (.+)\] draws", setup).groups()
    n, a, b = int(n), float(num(a)), float(num(b))

    def kth(k):  # E[X_(k)] = a + (b − a) ∫ P(fewer than k of the n draws fall below u) du
        below = lambda u: sum(math.comb(n, j) * u ** j * (1 - u) ** (n - j) for j in range(k))  # noqa: E731
        return a + (b - a) * simpson(below, 0, 1, 400)
    if label == "E[median]":
        assert n % 2
        return kth((n + 1) // 2)
    return {"E[min]": lambda: kth(1), "E[max]": lambda: kth(n), "E[2nd smallest]": lambda: kth(2),
            "E[max − min]": lambda: kth(n) - kth(1)}[label]()


def check_cond(setup, label):
    mx, vx, my, vy = (float(num(x)) for x in
                      re.fullmatch(r"X ~ N\((.+), (\d+)\), Y ~ N\((.+), (\d+)\) indep", setup).groups())
    what, s = re.fullmatch(r"(E\[|Var\()X \| X\+Y=(.+)[\])]", label).groups()
    s = float(num(s))
    fx, fy = normal_pdf(mx, vx), normal_pdf(my, vy)
    w = lambda x: fx(x) * fy(s - x)  # noqa: E731  the density of X given X + Y = s, unnormalised
    m0 = simpson(w, -80, 80, 8000)
    m1 = simpson(lambda x: x * w(x), -80, 80, 8000) / m0
    m2 = simpson(lambda x: x * x * w(x), -80, 80, 8000) / m0
    return m1 if what == "E[" else m2 - m1 * m1


def check_regress(setup, label):
    m = re.fullmatch(r"Std bivariate normal, ρ = (.+)", setup)
    if m:
        vx = vy = 1.0
        rho = float(num(m[1]))
    else:
        vx, vy, rho = re.fullmatch(r"X ~ N\(0, (\d+)\), Y ~ N\(0, (\d+)\) jointly, ρ = (.+)", setup).groups()
        vx, vy, rho = float(vx), float(vy), float(num(rho))
    what, x = re.fullmatch(r"(E\[|Var\()Y \| X=(.+)[\])]", label).groups()
    x, sx, sy = float(num(x)), math.sqrt(vx), math.sqrt(vy)
    f = lambda y: math.exp(-(x * x / vx - 2 * rho * x * y / (sx * sy) + y * y / vy) / (2 * (1 - rho * rho)))  # noqa
    m0 = simpson(f, -80, 80, 8000)
    m1 = simpson(lambda y: y * f(y), -80, 80, 8000) / m0
    m2 = simpson(lambda y: y * y * f(y), -80, 80, 8000) / m0
    return m1 if what == "E[" else m2 - m1 * m1


def check_coins(setup, label):
    a, b = map(int, re.fullmatch(r"A: (\d+) fair coins, B: (\d+)", setup).groups())
    pairs = [(i, j) for i in range(a + 1) for j in range(b + 1)]
    ways = lambda cond: sum(math.comb(a, i) * math.comb(b, j) for i, j in pairs if cond(i, j))  # noqa: E731
    cond = {"P(A has more heads)": lambda i, j: i > j, "P(same # of heads)": lambda i, j: i == j}[label]
    return F(ways(cond), 2 ** (a + b))


def runs(seq):
    return 1 + sum(x != y for x, y in zip(seq, seq[1:]))


def check_linearity(text):
    m = re.fullmatch(r"Random permutation of (\d+)\. E\[# fixed points\]", text)
    if m:
        perms = list(itertools.permutations(range(int(m[1]))))
        return F(sum(sum(p[i] == i for i in range(len(p))) for p in perms), len(perms))
    m = re.fullmatch(r"(\d+) fair coin flips\. E\[# (runs|overlapping HH)\]", text)
    if m:
        seqs = list(itertools.product("HT", repeat=int(m[1])))
        count = runs if m[2] == "runs" else (lambda s: sum(x == y == "H" for x, y in zip(s, s[1:])))
        return F(sum(map(count, seqs)), len(seqs))
    h, t = map(int, re.fullmatch(r"(\d+) H and (\d+) T in random order\. E\[# runs\]", text).groups())
    seqs = [["H" if i in pos else "T" for i in range(h + t)] for pos in itertools.combinations(range(h + t), h)]
    return F(sum(map(runs, seqs)), len(seqs))


def check_memoryless(setup, label):
    m = re.fullmatch(r"X ~ Expo\(λ=(.+)\)", setup)
    if m:
        lam = float(num(m[1]))
        what, s = re.fullmatch(r"(E\[|Var\()X \| X > (\d+)[\])]", label).groups()
        s = int(s)
        pdf = lambda x: lam * math.exp(-lam * x)  # noqa: E731
        m1, m2 = pdf_moments(pdf, s, s + 60 / lam)
        return m1 if what == "E[" else m2 - m1 * m1
    p = float(num(re.fullmatch(r"X ~ Geom\((.+)\) on \{1,2,…\}", setup)[1]))
    pmf = {k: (1 - p) ** (k - 1) * p for k in range(1, 3000)}
    m = re.fullmatch(r"E\[X \| X > (\d+)\]", label)
    if m:
        tail = {k: q for k, q in pmf.items() if k > int(m[1])}
        return sum(k * q for k, q in tail.items()) / sum(tail.values())
    big, small = map(int, re.fullmatch(r"P\(X > (\d+) \| X > (\d+)\)", label).groups())
    return sum(q for k, q in pmf.items() if k > big) / sum(q for k, q in pmf.items() if k > small)


def check_wait(text):
    m = re.fullmatch(r"Fair coin\. E\[flips until ([HT]+)\]", text)
    if m:
        return pattern_wait(m[1], "HT")
    m = re.fullmatch(r"Fair die\. E\[rolls until (.+)\]", text)
    if m:
        hit = {"a 6": {6}, "a 5 or 6": {5, 6}, "an even number": {2, 4, 6}}.get(m[1])
        if hit is None:
            assert m[1] == "two 6s in a row"
            return pattern_wait("66", "123456")
        return expected_steps("roll", lambda s: [(F(1, 6), None if f in hit else "roll") for f in range(1, 7)])
    n = int(re.fullmatch(r"(\d+) equally likely types\. E\[draws to see all\]", text)[1])
    step = lambda seen: [(F(1, n), None if len(seen | {i}) == n else seen | {i}) for i in range(n)]  # noqa: E731
    return expected_steps(frozenset(), step)


def check_matrix2(setup, label):
    a = matrix(re.fullmatch(r"A = (.+)", setup)[1])
    d = det(a)
    if label in ("larger eigenvalue", "smaller eigenvalue"):
        roots = eigenvalues(a)
        assert len(roots) == 2, setup
        return max(roots) if label.startswith("larger") else min(roots)
    return {"det(A)": lambda: d, "tr(A²)": lambda: sum(matmul(a, a)[i][i] for i in range(2)),
            "tr(A⁻¹)": lambda: sum(inverse(a)[i][i] for i in range(2))}[label]()


def check_triangular(setup, label):
    m = re.fullmatch(r"A = diag\((.+)\)", setup)
    if m and "ln" in m[1]:
        logs = [math.log(int(x[3:])) if x.startswith("ln ") else float(x) for x in m[1].split(", ")]
        n = len(logs)
        a = [[logs[i] if i == j else 0.0 for j in range(n)] for i in range(n)]
        e, term = [[float(i == j) for j in range(n)] for i in range(n)], [[float(i == j) for j in range(n)] for i in range(n)]
        for k in range(1, 60):  # e^A as its power series
            term = [[x / k for x in row] for row in matmul(term, a)]
            e = [[x + y for x, y in zip(r, s)] for r, s in zip(e, term)]
        return sum(e[i][i] for i in range(n)) if label == "tr(e^A)" else det(e)
    a = [[F(x) if i == j else F(0) for j, _ in enumerate(m[1].split(", "))] for i, x in
         enumerate(m[1].split(", "))] if m else matrix(setup[4:])
    n = len(a)
    if label == "largest eigenvalue":
        return max(eigenvalues(a))
    power = lambda k: a if k == 1 else matmul(a, power(k - 1))  # noqa: E731
    return {"det(A)": lambda: det(a), "tr(A²)": lambda: sum(power(2)[i][i] for i in range(n)),
            "det(A³)": lambda: det(power(3)), "tr(A⁻¹)": lambda: sum(inverse(a)[i][i] for i in range(n)),
            "det(A⁻¹)": lambda: det(inverse(a))}[label]()


NAMED = ("Bern", "Bin", "Geom", "Pois", "DUnif", "Unif", "Expo", "Gamma", "Beta", "Normal")
SPLIT = {"Var(aX+b)": check_linear, "Var(X±Y)": check_pair, "iid sum": check_iid, "order stat": check_order,
         "cond normal": check_cond, "regression": check_regress, "coins": check_coins,
         "memoryless": check_memoryless, "2×2 matrix": check_matrix2, "triangular matrix": check_triangular}
WHOLE = {"linearity": check_linearity, "waiting time": check_wait}


def independent(q):
    kind, text = q["kind"], q["text"]
    if kind in WHOLE:
        return WHOLE[kind](text)
    setup, label = text.rsplit(". ", 1)
    if kind in NAMED:
        return check_named(kind, setup, label)
    return SPLIT[kind](setup, label)


class Questions(unittest.TestCase):
    def test_every_kind_against_an_independent_check(self):
        self.assertEqual(set(arith.DIST_KINDS), set(NAMED) | set(SPLIT) | set(WHOLE))
        for kind, gen in arith.DIST_KINDS.items():
            rng = random.Random(7)
            seen = {}
            for _ in range(400):
                q = gen(rng)
                seen.setdefault(q["text"], q)
            for q in list(seen.values())[:60]:
                with self.subTest(kind=kind, text=q["text"]):
                    self.assertEqual(q["kind"], kind)
                    want, got = independent(q), F(q["answer"])
                    if isinstance(want, F):
                        self.assertEqual(got, want)
                    else:
                        self.assertTrue(math.isclose(float(got), want, rel_tol=1e-6, abs_tol=1e-8), (got, want))

    def test_short_exact_and_varied(self):
        rng = random.Random(2)
        qs = [arith.generate("dist", rng) for _ in range(5000)]
        self.assertEqual({q["kind"] for q in qs}, set(arith.DIST_KINDS))
        for q in qs:
            self.assertLessEqual(len(q["text"]), 60, q["text"])
            self.assertEqual((q["mode"], q["estimate"]), ("dist", False))
            self.assertEqual(q["answer"], str(F(q["answer"])))  # canonical: 3, 1/12, -5/2
            self.assertEqual(arith.mode_of(q["kind"]), "dist")
            self.assertNotIn("-", q["text"])  # minus signs in the text are U+2212, as in core
        for kind in arith.DIST_KINDS:
            labels = {q["text"].rsplit(". ", 1)[-1] for q in qs if q["kind"] == kind}
            self.assertGreater(len(labels), 1, kind)

    def test_of_kind(self):
        rng = random.Random(4)
        for kind in arith.DIST_KINDS:
            self.assertEqual(arith.of_kind(kind, rng)["kind"], kind)


class Answers(unittest.TestCase):
    def q(self, answer):
        return {"answer": answer, "mode": "dist", "estimate": False}

    def test_fraction_decimal_or_rounded(self):
        q = self.q("1/12")
        for ok in ("1/12", "2/24", "0.0833", "0.08333", ".0833"):
            self.assertTrue(arith.accepts(ok, q), ok)
        for bad in ("1/1", "1/", "0.083", "0.0834", "0.0832", "-", "/", "1/0", ""):
            self.assertFalse(arith.accepts(bad, q), bad)
        self.assertTrue(arith.accepts("1.25", self.q("5/4")))
        self.assertTrue(arith.accepts("10/8", self.q("5/4")))
        self.assertTrue(arith.accepts("0.6667", self.q("2/3")))
        self.assertFalse(arith.accepts("0.6666", self.q("2/3")))
        self.assertTrue(arith.accepts("-3/2", self.q("-3/2")))
        self.assertTrue(arith.accepts("-1.5", self.q("-3/2")))
        self.assertTrue(arith.accepts("42", self.q("42")))

    def test_arithmetic_questions_take_no_fractions(self):
        self.assertFalse(arith.accepts("3/8", {"answer": "0.375", "estimate": False, "mode": "fractions"}))

    def test_no_answer_needs_typing_past_an_accepted_prefix(self):
        rng = random.Random(9)
        for _ in range(3000):
            q = arith.generate("dist", rng)
            ans = q["answer"]
            self.assertTrue(arith.accepts(ans, q), q)
            self.assertFalse(any(arith.accepts(ans[:k], q) for k in range(1, len(ans))), q)


def sprint(mode, questions):
    return {"date": "2026-11-04", "time": "12:00", "mode": mode, "seconds": 120, "complete": True,
            "score": len(questions), "skipped": 0, "questions": [{"kind": k, "ms": ms} for k, ms in questions]}


class Weak(unittest.TestCase):
    def setUp(self):
        self.h = {"sprints": [sprint("mixed", [("× 7", 3000)] * 12 + [("× 3", 1000)] * 12),
                              sprint("dist", [("Beta", 9000)] * 12 + [("Pois", 2000)] * 12 + [("Unif", 3000)] * 12)]}

    def test_weak_kinds_per_family(self):
        self.assertEqual(arith.weak_kinds(self.h), ["× 7", "× 3"])
        self.assertEqual(arith.weak_kinds(self.h, "dist-weak"), ["Beta", "Unif", "Pois"])

    def test_weak_draws_no_distribution_questions(self):
        rng = random.Random(1)
        w = arith.weak_kinds(self.h)
        self.assertNotIn("dist", {arith.generate("weak", rng, w)["mode"] for _ in range(3000)})

    def test_dist_weak_draws_only_distribution_questions(self):
        rng = random.Random(1)
        w = arith.weak_kinds(self.h, "dist-weak")
        qs = [arith.generate("dist-weak", rng, w) for _ in range(4000)]
        self.assertEqual({q["mode"] for q in qs}, {"dist"})
        share = sum(q["kind"] == "Beta" for q in qs) / len(qs)
        self.assertTrue(0.12 < share < 0.2, share)  # 0.7 / 5 from its slot, plus a 0.3 / 22 uniform share

    def test_kinds_command_filters_dist(self):
        vault = make_vault(self)
        (vault / "practice").mkdir()
        (vault / "practice" / ".arith.json").write_text(json.dumps(self.h))
        out = run(vault, "arith.py", "kinds", "dist").stdout
        self.assertEqual(out.split("\n")[0], "Beta 9.0 s")
        self.assertNotIn("×", out)
        self.assertIn("dist 120 s: 36", run(vault, "arith.py", "history", "dist").stdout)

    def test_dist_popup_is_wider(self):
        vault = make_vault(self)
        bin_dir = Path(tempfile.mkdtemp(prefix="fake-tmux-"))
        self.addCleanup(shutil.rmtree, bin_dir, True)
        (bin_dir / "tmux").write_text(f'#!/bin/sh\necho "$@" >> "{bin_dir}/calls.log"\n')
        (bin_dir / "tmux").chmod(0o755)
        run(vault, "arith.py", "run", "dist-weak", env={"PATH": f"{bin_dir}:{os.environ['PATH']}", "TMUX": "x"})
        self.assertIn("display-popup -E -w 80 -h 14 ", (bin_dir / "calls.log").read_text())


if __name__ == "__main__":
    unittest.main()
