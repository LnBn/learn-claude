"""A small filled-in paper on chapter 2 of the test course, its marking scheme, and the sections it may cite."""
import copy

PAPER = """---
exam: pml1-ch02
covers: "[[pml1-ch02]]"
attempt: 1
length: short
status: open
marks: 16
set: 2026-10-11
---
# Exam — Chapter 2: Probability: univariate models

*Closed book. About 20 minutes, 16 marks. Tick one box per multiple-choice
question unless it says "select all". When you are done, type `/exam submit`.*

## Part A — Multiple choice (4 marks)

### Q1 (2 marks)
Which of these is Bayes' rule?

- [x] a) $p(h \\mid D) = p(D \\mid h)\\,p(h) / p(D)$
- [ ] b) $p(h \\mid D) = p(D \\mid h)$
- [ ] c) $p(h \\mid D) = p(h)$
- [ ] d) $p(h \\mid D) = p(D)$

### Q2 (2 marks)
Which term of Bayes' rule is the evidence?

- [ ] a) $p(h)$
- [ ] b) $p(D \\mid h)$
*  [X]  c) $p(D)$
- [ ] d) $p(h \\mid D)$

## Part B — Short answer (4 marks)

### Q3 (4 marks)
A test has sensitivity 0.9; the prior is 0.1 and $p(+) = 0.3$. What is $p(h \\mid +)$?

**Answer:** 0.3

## Part C — Problems (8 marks)

### Q4 (8 marks)
Derive Bayes' rule from the product rule.

**Answer:**
### Step 1
Write the joint both ways.
## Working
$$
p(h, D) = p(D \\mid h)\\,p(h) = p(h \\mid D)\\,p(D)
$$
Divide by $p(D)$.
"""

SECTIONS = {"pml1-ch02#2.1 Intro", "pml1-ch02#2.2 Rules", "pml1-ch02#2.3 Bayes' rule"}

_SCHEME = {
    "paper": "courses/pml1/exams/pml1-ch02-exam-1.md",
    "covers": "courses/pml1/pml1-ch02.md",
    "course": "pml1",
    "chapter": "2",
    "attempt": 1,
    "length": "short",
    "marks": 16,
    "questions": [
        {"id": "q1", "part": "A", "type": "mc", "marks": 2, "correct": ["a"],
         "explanation": "The posterior is likelihood times prior over evidence.",
         "why_wrong": {"b": "leaves out the prior and the evidence", "c": "is the prior alone",
                       "d": "is the evidence alone"},
         "section": "pml1-ch02#2.3 Bayes' rule", "unit": "2.3"},
        {"id": "q2", "part": "A", "type": "mc", "marks": 2, "correct": ["c"],
         "explanation": "The evidence is the marginal likelihood p(D).",
         "why_wrong": {"a": "is the prior", "b": "is the likelihood", "d": "is the posterior"},
         "section": "pml1-ch02#2.3 Bayes' rule", "unit": "2.3"},
        {"id": "q3", "part": "B", "type": "short", "marks": 4,
         "model_answer": "$p(h \\mid +) = 0.9 \\cdot 0.1 / 0.3 = 0.3$",
         "points": [{"text": "applies Bayes' rule", "marks": 2}, {"text": "gets 0.3", "marks": 2}],
         "section": "pml1-ch02#2.3 Bayes' rule", "unit": "2.3"},
        {"id": "q4", "part": "C", "type": "long", "marks": 8,
         "model_answer": "Write p(h, D) both ways with the product rule and divide by p(D).",
         "points": [{"text": "product rule both ways", "marks": 4}, {"text": "divides by p(D)", "marks": 4}],
         "section": "pml1-ch02#2.2 Rules", "unit": "2.2"},
    ],
}


def scheme():
    return copy.deepcopy(_SCHEME)


def without_q3_heading(paper=PAPER):
    return paper.replace("### Q3 (4 marks)\n", "")


def with_tags(paper=PAPER):
    return paper.replace("set: 2026-10-11\n", "set: 2026-10-11\ntags: [x]\n")


def blank_q3(paper=PAPER):
    return paper.replace("**Answer:** 0.3", "**Answer:**")
