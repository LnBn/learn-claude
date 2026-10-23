#!/usr/bin/env python3
"""
coding_runner — run one case of a code task and print the result as one JSON line.

coding.py starts this script once per case, so a crash, a runaway loop or a runaway allocation ends here and
not in the caller. Memory is capped at 2 GiB; --timeout limits the call itself (an interval timer, so starting
Python, building the inputs and copying them do not count); --cpu caps the whole process's CPU seconds.

    coding_runner.py <tests.py> --count
                        {"function", "cases": [names], "large": [names], "slow": bool} of a hidden-tests module
    coding_runner.py <tests.py> case:<i>|large:<i> (--solution <file.py> | --impl reference|slow)
                     [--timeout <s>] [--cpu <s>]
                        {"name", "call", "passed", "got", "expected", "seconds", "timeout", "stdout", "error"}

The tests module: FUNCTION, reference(*args), CASES [{"name", "args", "expected"}], and optionally slow(*args),
large() yielding {"name", "args"} (expected = reference(*args)), and check(got, expected, args).
"""
import argparse
import contextlib
import copy
import importlib.util
import io
import itertools
import json
import math
import os
import resource
import signal
import sys
import time
import traceback

MEMORY = 2 * 1024 ** 3
MAX_REPR = 300
MAX_STDOUT = 20  # lines
MAX_STDOUT_CHARS = 2000
MAX_FRAMES = 10
MAX_MESSAGE = 500


class CallTimeout(BaseException):
    """Raised by the interval timer; a BaseException, so `except Exception` in the solution does not swallow it."""


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compare(got, expected):
    """==, with floats (also inside lists, tuples and dict values) and numpy arrays compared with a tolerance;
    NaN equals NaN, and a numpy array equals a list of the same values."""
    np = sys.modules.get("numpy")  # only when the solution or the tests imported it
    if np is not None and (isinstance(got, np.ndarray) or isinstance(expected, np.ndarray)):
        try:
            a, b = np.asarray(got), np.asarray(expected)
            return a.shape == b.shape and bool(np.allclose(a, b))
        except Exception:
            return False
    numbers = (int, float)
    if isinstance(got, numbers) and isinstance(expected, numbers) and float in (type(got), type(expected)):
        if math.isnan(got) or math.isnan(expected):
            return math.isnan(got) and math.isnan(expected)
        return math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-12)
    if isinstance(expected, (list, tuple)):
        return type(got) is type(expected) and len(got) == len(expected) and \
            all(compare(g, e) for g, e in zip(got, expected))
    if isinstance(expected, dict):
        return isinstance(got, dict) and got.keys() == expected.keys() and \
            all(compare(got[k], expected[k]) for k in expected)
    try:
        return bool(got == expected)
    except Exception:
        return False


def short(value):
    try:
        text = repr(value)
    except Exception:
        return "<unprintable>"
    return text if len(text) <= MAX_REPR else text[:MAX_REPR] + "…"


def error_text(exc, path):
    """The exception, with its traceback cut to the frames in `path` (the learner's file, or the tests')."""
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if os.path.abspath(f.filename) == path]
    message = str(exc)
    message = message if len(message) <= MAX_MESSAGE else message[:MAX_MESSAGE] + "…"
    text = f"{type(exc).__name__}: {message}"
    if len(frames) > MAX_FRAMES:
        text += f"\n  … {len(frames) - MAX_FRAMES} earlier frames"
        frames = frames[-MAX_FRAMES:]
    return text + ("\n" + "".join(traceback.format_list(frames)).rstrip() if frames else "")


def count(tests_path):
    tests = load(tests_path, "hidden_tests")
    large = list(tests.large()) if hasattr(tests, "large") else []
    return {"function": tests.FUNCTION, "cases": [c.get("name", f"case {i + 1}") for i, c in enumerate(tests.CASES)],
            "large": [c.get("name", f"large {i + 1}") for i, c in enumerate(large)], "slow": hasattr(tests, "slow")}


def captured(text):
    lines = [ln if len(ln) <= 200 else ln[:200] + "…" for ln in text.splitlines()[:MAX_STDOUT]]
    text = "\n".join(lines)
    return text if len(text) <= MAX_STDOUT_CHARS else text[:MAX_STDOUT_CHARS] + "…"


def _alarm(signum, frame):
    raise CallTimeout()


def run(tests_path, case, solution=None, impl=None, timeout=None):
    tests = load(tests_path, "hidden_tests")
    kind, i = case.split(":")
    if kind == "case":
        c = tests.CASES[int(i)]
        args, expected = c["args"], c["expected"]
    else:
        c = next(itertools.islice(tests.large(), int(i), None))  # only the cases up to this one are built
        args = c["args"]
        expected = tests.reference(*copy.deepcopy(args))
    name = c.get("name", f"{'case' if kind == 'case' else 'large'} {int(i) + 1}")
    call = f"{tests.FUNCTION}({', '.join(short(x) for x in args)})"
    result = {"name": name, "call": call if len(call) <= MAX_REPR else call[:MAX_REPR] + "…", "passed": False, "got": None, "expected": short(expected),
              "seconds": None, "timeout": False, "stdout": "", "error": None}
    path = os.path.abspath(solution or tests_path)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            if solution:
                module = load(solution, "solution")
                if not hasattr(module, tests.FUNCTION):
                    raise NameError(f"the file does not define {tests.FUNCTION}()")
                fn = getattr(module, tests.FUNCTION)
            else:
                fn = getattr(tests, impl)
            call = copy.deepcopy(args)
            if timeout:
                signal.signal(signal.SIGALRM, _alarm)
                signal.setitimer(signal.ITIMER_REAL, timeout)
            start = time.perf_counter()
            try:
                got = fn(*call)
            finally:
                result["seconds"] = time.perf_counter() - start
                if timeout:
                    signal.setitimer(signal.ITIMER_REAL, 0)
        result["got"] = short(got)
        check = getattr(tests, "check", None)
        result["passed"] = bool(check(got, expected, copy.deepcopy(args)) if check else compare(got, expected))
    except CallTimeout:
        result["timeout"] = True
    except Exception as exc:
        result["error"] = error_text(exc, path)
    result["stdout"] = captured(out.getvalue())
    return result


def main(argv):
    p = argparse.ArgumentParser(prog="coding_runner.py")
    p.add_argument("tests")
    p.add_argument("case", nargs="?")
    p.add_argument("--count", action="store_true")
    p.add_argument("--solution")
    p.add_argument("--impl", choices=["reference", "slow"])
    p.add_argument("--timeout", type=float)
    p.add_argument("--cpu", type=int)
    a = p.parse_args(argv[1:])
    if a.count:
        print(json.dumps(count(a.tests)))
        return 0
    if not a.case or bool(a.solution) == bool(a.impl):
        p.error("give a case and exactly one of --solution or --impl")
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))  # a CPU-limit kill leaves no core dump (nor a crash report)
    if a.cpu:
        resource.setrlimit(resource.RLIMIT_CPU, (a.cpu, a.cpu + 1))
    print(json.dumps(run(a.tests, a.case, a.solution, a.impl, a.timeout)), file=sys.__stdout__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
