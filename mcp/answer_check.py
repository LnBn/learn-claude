#!/usr/bin/env python3
"""
answer_check — read, show and compare typed quiz answers (numbers and formulas).

    read("2(2^n-1)", {"n": "int 1..12"})          -> ast.Expression, or AnswerError
    display("2^(n+1)-2", {"n": "int 1..12"})      -> "2ⁿ⁺¹ − 2"
    check("2*2^n-2", "2^(n+1)-2", {"n": "int 1..12"}) -> "correct"

The text is tokenised and rewritten into Python syntax (implicit *, ^ -> **, n! -> fact(n)),
parsed with ast, and only a whitelist of nodes is accepted; a small tree walker evaluates it in
floats. Two formulas are compared at six points drawn from the variables' ranges, seeded from the
expected answer, so the popup and the server always draw the same points.
"""
import ast
import hashlib
import json
import math
import random
import re

from latex_text import SUP

FUNCS = {"sqrt": 1, "ln": 1, "log": 1, "log2": 1, "log10": 1, "exp": 1, "abs": 1, "binom": 2, "C": 2}
CONSTS = ("inf", "pi", "e")
RESERVED = set(FUNCS) | set(CONSTS) | {"fact"}
N_POINTS = 6
UNICODE = {"π": " pi ", "∞": " inf ", "×": "*", "·": "*", "−": "-", "√": " √ "}
RANGE_RE = re.compile(r"^\s*(int\s+)?(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)\s*$")
NUM_RE = re.compile(r"\d+\.?\d*|\.\d+")


class AnswerError(ValueError):
    """An answer that cannot be read, or a question that cannot be set; the message is shown as is."""


# ----------------------------------------------------------------- ranges and points

def parse_ranges(variables):
    out = {}
    for name, spec in (variables or {}).items():
        if name in RESERVED or not re.fullmatch(r"[A-Za-z]+", name):
            raise AnswerError(f"{name}: reserved name, choose another")
        m = RANGE_RE.match(str(spec))
        if not m:
            raise AnswerError(f'{name}: bad range "{spec}" — write "int a..b" or "a..b" with a < b')
        kind = "int" if m.group(1) else "real"
        conv = int if kind == "int" else float
        try:
            a, b = conv(m.group(2)), conv(m.group(3))
        except ValueError:
            raise AnswerError(f'{name}: bad range "{spec}" — write "int a..b" or "a..b" with a < b') from None
        if a >= b:
            raise AnswerError(f'{name}: bad range "{spec}" — write "int a..b" or "a..b" with a < b')
        out[name] = (kind, a, b)
    return out


def points(expected, variables):
    ranges = parse_ranges(variables)
    if not ranges:
        return [{}]
    seed = hashlib.sha256((expected + json.dumps(sorted((variables or {}).items()))).encode()).hexdigest()
    rng = random.Random(int(seed, 16))
    out = []
    for _ in range(N_POINTS):
        p = {}
        for name, (kind, a, b) in sorted(ranges.items()):
            p[name] = float(rng.randint(a, b)) if kind == "int" else a + (b - a) * (0.02 + 0.96 * rng.random())
        out.append(p)
    return out


# ----------------------------------------------------------------- reading

def _unknown(name, names):
    tail = f" — this question's variables are {', '.join(sorted(names))}" if names else ""
    return AnswerError(f"unknown name: {name}{tail}")


def _split_letters(run, names, before_paren):
    """A run of letters as function, constant and variable tokens, read greedily."""
    out, i = [], 0
    by_length = sorted(names, key=len, reverse=True)
    while i < len(run):
        rest = run[i:]
        if before_paren and rest in FUNCS:
            out.append(("func", "binom" if rest == "C" else rest))
            break
        const = next((c for c in CONSTS if rest.startswith(c)), None)
        var = next((v for v in by_length if rest.startswith(v)), None)
        if const:
            out.append(("name", const))
            i += len(const)
        elif var:
            out.append(("name", var))
            i += len(var)
        else:
            raise _unknown(rest, names)
    return out


def _tokens(text, names):
    s = text
    for k, v in UNICODE.items():
        s = s.replace(k, v)
    s = s.replace("**", "^")
    toks, i = [], 0
    while i < len(s):
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        m = NUM_RE.match(s, i)
        if m:
            toks.append(("num", m.group()))
            i = m.end()
            continue
        if ch.isascii() and ch.isalpha():
            m = re.compile(r"[A-Za-z]+").match(s, i)
            run, j = m.group(), m.end()
            if run.endswith("log"):
                d = re.compile(r"(2|10)(?=\s*\()").match(s, j)
                if d:
                    run, j = run + d.group(), d.end()
            before_paren = bool(re.compile(r"\s*\(").match(s, j))
            toks += _split_letters(run, names, before_paren)
            i = j
            continue
        if ch in "+-*/^":
            toks.append(("op", ch))
        elif ch == "(":
            toks.append(("lp", ch))
        elif ch == ")":
            toks.append(("rp", ch))
        elif ch == ",":
            toks.append(("comma", ch))
        elif ch == "!":
            toks.append(("bang", ch))
        elif ch == "√":
            toks.append(("sqrt", ch))
        else:
            raise AnswerError(f"can't read: unexpected character {ch!r}")
        i += 1
    return toks


def _check_shape(toks):
    if not toks:
        raise AnswerError("can't read: the answer is empty")
    depth = 0
    for k, (kind, val) in enumerate(toks):
        depth += (kind == "lp") - (kind == "rp")
        if depth < 0:
            raise AnswerError("can't read: a closing bracket has no opening one")
        nxt = toks[k + 1][0] if k + 1 < len(toks) else None
        if kind == "lp" and nxt == "rp":
            raise AnswerError("can't read: empty brackets")
        if kind in ("op", "sqrt") and nxt in (None, "rp", "comma"):
            raise AnswerError(f"can't read: nothing after {val}")
    if depth > 0:
        raise AnswerError("can't read: unclosed bracket")


def _group_start(out):
    """Index in out where the factor ending at out[-1] starts (a token, a bracket, or a call)."""
    if out[-1][0] != "rp":
        return len(out) - 1
    depth, k = 0, len(out) - 1
    while k >= 0:
        depth += (out[k][0] == "rp") - (out[k][0] == "lp")
        if depth == 0:
            break
        k -= 1
    return k - 1 if k > 0 and out[k - 1][0] == "func" else k


def _python(toks):
    out = []
    wrap_next = False  # √ applies to the next number or name, or to the next bracket
    for kind, val in toks:
        if kind == "bang":
            if not out or out[-1][0] not in ("num", "name", "rp"):
                raise AnswerError("can't read: nothing before !")
            k = _group_start(out)
            out[k:] = [("func", "fact"), ("lp", "(")] + out[k:] + [("rp", ")")]
            continue
        if wrap_next:
            wrap_next = False
            if kind in ("num", "name"):
                out += [("lp", "("), (kind, val), ("rp", ")")]
                continue
            if kind != "lp":
                raise AnswerError("can't read: put what √ applies to in brackets")
            out.append((kind, val))
            continue
        if out and out[-1][0] in ("num", "name", "rp") and kind in ("num", "name", "func", "lp", "sqrt"):
            out.append(("op", "*"))
        if kind == "sqrt":
            out.append(("func", "sqrt"))
            wrap_next = True
            continue
        out.append((kind, val))
    return "".join("**" if v == "^" else v for _, v in out)


def read(text, variables):
    names = set(variables or {})
    toks = _tokens(str(text), names)
    _check_shape(toks)
    src = _python(toks)
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError:
        raise AnswerError("can't read: check the operators") from None
    _whitelist(tree.body, names)
    return tree


def _whitelist(node, names):
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
        _whitelist(node.left, names)
        _whitelist(node.right, names)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        _whitelist(node.operand, names)
    elif isinstance(node, ast.Constant) and type(node.value) in (int, float):
        pass
    elif isinstance(node, ast.Name) and (node.id in names or node.id in CONSTS):
        pass
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        arity = 1 if node.func.id == "fact" else FUNCS.get(node.func.id)
        if arity is None:
            raise AnswerError(f"can't read: unknown function {node.func.id}")
        if len(node.args) != arity:
            raise AnswerError(f"can't read: {node.func.id} takes {arity} argument{'s' if arity > 1 else ''}")
        for a in node.args:
            _whitelist(a, names)
    elif isinstance(node, ast.Tuple):
        raise AnswerError("can't read: a comma outside a function")
    else:
        raise AnswerError("can't read: check the operators")


def is_decimal(text):
    return "." in str(text)


# ----------------------------------------------------------------- evaluating

def _integral(x):
    return float(x).is_integer()


def _fact(x):
    if _integral(x):
        if x < 0:
            raise ValueError
        if x > 170:
            raise OverflowError
        return float(math.factorial(int(x)))
    return math.gamma(x + 1)


def _binom(n, k):
    if _integral(n) and _integral(k):
        if k < 0 or (n >= 0 and k > n):
            return 0.0
        if 0 <= n <= 1000:
            return float(math.comb(int(n), int(k)))
    return math.gamma(n + 1) / (math.gamma(k + 1) * math.gamma(n - k + 1))


CALLS = {"sqrt": math.sqrt, "ln": math.log, "log": math.log, "log2": math.log2, "log10": math.log10,
         "exp": math.exp, "abs": abs, "binom": _binom, "fact": _fact}
NAMES = {"pi": math.pi, "e": math.e, "inf": math.inf}


def _walk(node, point):
    if isinstance(node, ast.Expression):
        return _walk(node.body, point)
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        return NAMES[node.id] if node.id in NAMES else float(point[node.id])
    if isinstance(node, ast.UnaryOp):
        v = _walk(node.operand, point)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.Call):
        return CALLS[node.func.id](*[_walk(a, point) for a in node.args])
    a, b = _walk(node.left, point), _walk(node.right, point)
    op = type(node.op)
    if op is ast.Add:
        return a + b
    if op is ast.Sub:
        return a - b
    if op is ast.Mult:
        return a * b
    if op is ast.Div:
        return a / b
    return a ** b


def evaluate(tree, point):
    """The value of a read answer at a point, or None where it is undefined."""
    try:
        v = _walk(tree, point)
    except (ZeroDivisionError, OverflowError, ValueError, KeyError):
        return None
    if isinstance(v, complex) or v != v:
        return None
    return float(v)


def defined_points(expected, variables):
    tree = read(expected, variables)
    return sum(evaluate(tree, p) is not None for p in points(expected, variables))


# ----------------------------------------------------------------- comparing

def _close(g, x, decimal):
    if math.isinf(x) or math.isinf(g):
        return g == x
    if decimal:
        tol = 5e-4 if x == 0 else 0.5 * 10 ** (math.floor(math.log10(abs(x))) - 2)
        return abs(g - x) <= tol * (1 + 1e-9)
    return math.isclose(g, x, rel_tol=1e-9, abs_tol=1e-12)


def check(given, expected, variables, exact=False):
    gt = read(given, variables)
    decimal = is_decimal(given)
    if exact and decimal:
        raise AnswerError("give the exact form, not a decimal")
    et = read(expected, variables)
    compared = 0
    for p in points(expected, variables):
        x = evaluate(et, p)
        if x is None:
            continue
        g = evaluate(gt, p)
        if g is None or not _close(g, x, decimal):
            return "wrong"
        compared += 1
    return "correct" if compared else "wrong"


def matches_wrong(given, wrong_answers, variables, exact=False):
    for i, w in enumerate(wrong_answers or []):
        try:
            if check(given, str(w.get("answer", "")), variables, exact) == "correct":
                return i
        except AnswerError:
            continue
    return None


# ----------------------------------------------------------------- showing

PREC = {ast.Add: 1, ast.Sub: 1, ast.Mult: 2, ast.Div: 2, ast.Pow: 4}


def _prec(node):
    if isinstance(node, ast.BinOp):
        return PREC[type(node.op)]
    if isinstance(node, ast.UnaryOp):
        return 3
    return 5


def _num(v):
    return str(int(v)) if isinstance(v, int) or (isinstance(v, float) and v.is_integer() and abs(v) < 1e15) else repr(v)


def _show(node):
    if isinstance(node, ast.Constant):
        return _num(node.value)
    if isinstance(node, ast.Name):
        return {"pi": "π", "inf": "∞"}.get(node.id, node.id)
    if isinstance(node, ast.UnaryOp):
        inner = _show(node.operand)
        if _prec(node.operand) < 3:
            inner = f"({inner})"
        return ("−" if isinstance(node.op, ast.USub) else "+") + inner
    if isinstance(node, ast.Call):
        args = [_show(a) for a in node.args]
        name = node.func.id
        if name == "sqrt":
            return "√" + (args[0] if _prec(node.args[0]) == 5 and not isinstance(node.args[0], ast.Call) else f"({args[0]})")
        if name == "fact":
            return (args[0] if _prec(node.args[0]) == 5 else f"({args[0]})") + "!"
        if name == "binom":
            return f"C({args[0]}, {args[1]})"
        return f"{name}({', '.join(args)})"
    op = type(node.op)
    p = PREC[op]
    left, right = _show(node.left), _show(node.right)
    fact_base = op is ast.Pow and isinstance(node.left, ast.Call) and node.left.func.id == "fact"
    if _prec(node.left) < p or (op is ast.Pow and _prec(node.left) <= p) or fact_base:
        left = f"({left})"
    if op is ast.Pow:
        compact = right.replace(" ", "").replace("−", "-")
        if all(c in SUP for c in compact):
            return left + "".join(SUP[c] for c in compact)
        return left + "^" + (right if _prec(node.right) == 5 else f"({right})")
    if _prec(node.right) < p or (_prec(node.right) == p and op in (ast.Sub, ast.Div)):
        right = f"({right})"
    if op is ast.Add:
        return f"{left} + {right}"
    if op is ast.Sub:
        return f"{left} − {right}"
    if op is ast.Div:
        return f"{left}/{right}"
    if isinstance(node.left, ast.Constant) and (right[:1].isalpha() or right[:1] in "√(π"):
        return left + right
    if right.startswith("("):
        return left + right
    return f"{left} · {right}"


def display(text, variables):
    return _show(read(text, variables).body)
