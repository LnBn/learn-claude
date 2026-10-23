#!/usr/bin/env python3
"""
coding_runner — run one case of a code task and print the result as one JSON line.

coding.py starts this script once per case, so a crash, a runaway loop or a runaway allocation ends here and
not in the caller. Memory is capped at 2 GiB; --cpu caps CPU seconds (the kernel kills the process past it).

    coding_runner.py <tests.py> --count
                        {"function", "cases", "large"} of a hidden-tests module
    coding_runner.py <tests.py> case:<i>|large:<i> (--solution <file.py> | --impl reference|slow) [--cpu <s>]
                        {"name", "passed", "got", "expected", "seconds", "stdout", "error"}

The tests module: FUNCTION, reference(*args), CASES [{"name", "args", "expected"}], and optionally slow(*args),
large() yielding {"name", "args"} (expected = reference(*args)), and check(got, expected, args).
"""
import argparse
import contextlib
import copy
import importlib.util
import io
import json
import math
import os
import resource
import sys
import time
import traceback

MEMORY = 2 * 1024 ** 3
MAX_REPR = 300
MAX_STDOUT = 20


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compare(got, expected):
    """==, with floats (also inside lists, tuples and dict values) and numpy arrays compared with a tolerance."""
    numbers = (int, float)
    if isinstance(got, numbers) and isinstance(expected, numbers) and float in (type(got), type(expected)):
        return math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-12)
    if isinstance(expected, (list, tuple)):
        return type(got) is type(expected) and len(got) == len(expected) and \
            all(compare(g, e) for g, e in zip(got, expected))
    if isinstance(expected, dict):
        return isinstance(got, dict) and got.keys() == expected.keys() and \
            all(compare(got[k], expected[k]) for k in expected)
    np = sys.modules.get("numpy")  # only when the solution or the tests imported it
    if np is not None and (isinstance(got, np.ndarray) or isinstance(expected, np.ndarray)):
        try:
            a, b = np.asarray(got), np.asarray(expected)
            return a.shape == b.shape and bool(np.allclose(a, b))
        except Exception:
            return False
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
    return f"{type(exc).__name__}: {exc}" + ("\n" + "".join(traceback.format_list(frames)).rstrip() if frames else "")


def count(tests_path):
    tests = load(tests_path, "hidden_tests")
    large = list(tests.large()) if hasattr(tests, "large") else []
    return {"function": tests.FUNCTION, "cases": len(tests.CASES), "large": len(large)}


def run(tests_path, case, solution=None, impl=None):
    tests = load(tests_path, "hidden_tests")
    kind, i = case.split(":")
    if kind == "case":
        c = tests.CASES[int(i)]
        args, expected = c["args"], c["expected"]
    else:
        c = list(tests.large())[int(i)]
        args = c["args"]
        expected = tests.reference(*copy.deepcopy(args))
    result = {"name": c.get("name", case), "passed": False, "got": None, "expected": short(expected),
              "seconds": None, "stdout": "", "error": None}
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
            start = time.perf_counter()
            got = fn(*call)
            result["seconds"] = time.perf_counter() - start
        result["got"] = short(got)
        check = getattr(tests, "check", None)
        result["passed"] = bool(check(got, expected, copy.deepcopy(args)) if check else compare(got, expected))
    except Exception as exc:
        result["error"] = error_text(exc, path)
    result["stdout"] = "\n".join(out.getvalue().splitlines()[:MAX_STDOUT])
    return result


def main(argv):
    p = argparse.ArgumentParser(prog="coding_runner.py")
    p.add_argument("tests")
    p.add_argument("case", nargs="?")
    p.add_argument("--count", action="store_true")
    p.add_argument("--solution")
    p.add_argument("--impl", choices=["reference", "slow"])
    p.add_argument("--cpu", type=int)
    a = p.parse_args(argv[1:])
    if a.count:
        print(json.dumps(count(a.tests)))
        return 0
    if not a.case or bool(a.solution) == bool(a.impl):
        p.error("give a case and exactly one of --solution or --impl")
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
    if a.cpu:
        resource.setrlimit(resource.RLIMIT_CPU, (a.cpu, a.cpu + 1))
    print(json.dumps(run(a.tests, a.case, a.solution, a.impl)), file=sys.__stdout__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
