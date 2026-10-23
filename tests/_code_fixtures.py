"""A code task (running maximum) and solutions to it, shared by the code-task tests."""

TESTS = '''
FUNCTION = "running_max"


def reference(xs):
    out, m = [], None
    for x in xs:
        m = x if m is None or x > m else m
        out.append(m)
    return out


def slow(xs):
    out = []
    for i in range(len(xs)):
        m = xs[0]
        for x in xs[:i + 1]:
            m = x if x > m else m
        out.append(m)
    return out


CASES = [
    {"name": "example", "args": [[3, 1, 4, 1, 5]], "expected": [3, 3, 4, 4, 5]},
    {"name": "empty", "args": [[]], "expected": []},
    {"name": "all equal", "args": [[2, 2, 2]], "expected": [2, 2, 2]},
]


def large():
    import random
    r = random.Random(1)
    yield {"name": "n = 10000", "args": [[r.random() for _ in range(10000)]]}
'''

NOTE = """# Running maximum
*quant · task 01 · level 1 · lists*

Return a list whose i-th entry is the largest of the first i+1 numbers.

running_max([3, 1, 4, 1, 5]) → [3, 3, 4, 4, 5]

**Your file:** `{starter}`. Run it with `python3 {name}`, then type **submit**.

## Submissions
"""

STARTER = '''def running_max(xs: list[float]) -> list[float]:
    ...


if __name__ == "__main__":
    print(running_max([3, 1, 4, 1, 5]))  # expect [3, 3, 4, 4, 5]
'''

GOOD = '''def running_max(xs):
    out, m = [], None
    for x in xs:
        m = x if m is None or x > m else m
        out.append(m)
    return out
'''

WRONG = '''def running_max(xs):
    return xs
'''

RAISES = '''def running_max(xs):
    m = xs[0]
    out = []
    for x in xs:
        m = max(m, x)
        out.append(m)
    return out
'''

LOOPS = '''def running_max(xs):
    while True:
        pass
'''

PRINTS = GOOD + '''

_good = running_max


def running_max(xs):
    for i in range(30):
        print("line", i)
    return _good(xs)
'''

MUTATES = GOOD + '''

_good = running_max


def running_max(xs):
    out = _good(list(xs))
    xs.append(0)
    return out
'''

QUADRATIC = '''def running_max(xs):
    out = []
    for i in range(len(xs)):
        m = xs[0]
        for x in xs[:i + 1]:
            m = x if x > m else m
        out.append(m)
    return out
'''

UNPRINTABLE = '''class Weird:
    def __repr__(self):
        raise RuntimeError("no repr")


def running_max(xs):
    return Weird()
'''

SYNTAX_ERROR = '''def running_max(xs)
    return xs
'''

WRONG_NAME = '''def other_name(xs):
    return xs
'''
