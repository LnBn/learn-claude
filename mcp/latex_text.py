#!/usr/bin/env python3
"""
latex_text — render LaTeX math as plain Unicode for the terminal popup.

Not a typesetter: it turns $x^2 + \\frac{1}{2}\\alpha_i$ into  x² + 1/2 αᵢ  so a
quiz is readable in a terminal that cannot render LaTeX. The markdown log keeps
the real LaTeX for Obsidian. If `pylatexenc` is installed it is used for the
math segments instead (pip install pylatexenc), otherwise the built-in converter.
"""
import re

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν",
    "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
SYMBOLS = {
    "times": "×", "cdot": "·", "pm": "±", "mp": "∓", "div": "÷", "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥",
    "neq": "≠", "ne": "≠", "approx": "≈", "equiv": "≡", "sim": "∼", "simeq": "≃", "propto": "∝", "infty": "∞",
    "sum": "∑", "prod": "∏", "int": "∫", "oint": "∮", "partial": "∂", "nabla": "∇", "rightarrow": "→", "to": "→",
    "leftarrow": "←", "Rightarrow": "⇒", "Leftarrow": "⇐", "leftrightarrow": "↔", "Leftrightarrow": "⇔",
    "iff": "⇔", "implies": "⇒", "mapsto": "↦", "in": "∈", "notin": "∉", "ni": "∋", "subset": "⊂", "subseteq": "⊆",
    "supset": "⊃", "supseteq": "⊇", "cup": "∪", "cap": "∩", "setminus": "∖", "emptyset": "∅", "varnothing": "∅",
    "forall": "∀", "exists": "∃", "nexists": "∄", "neg": "¬", "lnot": "¬", "land": "∧", "wedge": "∧", "lor": "∨",
    "vee": "∨", "oplus": "⊕", "otimes": "⊗", "cdots": "⋯", "ldots": "…", "dots": "…", "vdots": "⋮", "ddots": "⋱",
    "circ": "∘", "degree": "°", "perp": "⊥", "parallel": "∥", "angle": "∠", "triangle": "△", "square": "□",
    "hbar": "ℏ", "ell": "ℓ", "Re": "ℜ", "Im": "ℑ", "aleph": "ℵ", "mid": "|", "vert": "|", "Vert": "‖", "|": "‖",
    "langle": "⟨", "rangle": "⟩", "lfloor": "⌊", "rfloor": "⌋", "lceil": "⌈", "rceil": "⌉", "prime": "′",
    "quad": "  ", "qquad": "    ", ",": " ", ";": " ", ":": " ", "!": "", " ": " ", "\\": "\n",
    "{": "{", "}": "}", "%": "%", "&": "&", "#": "#", "_": "_", "$": "$", "star": "⋆", "ast": "∗",
    "therefore": "∴", "because": "∵", "top": "⊤", "bot": "⊥", "models": "⊨", "vdash": "⊢", "ll": "≪", "gg": "≫",
    "mathbb{R}": "ℝ", "mathbb{N}": "ℕ", "mathbb{Z}": "ℤ", "mathbb{Q}": "ℚ", "mathbb{C}": "ℂ", "mathbb{E}": "𝔼",
    "mathbb{P}": "ℙ",
}
SUP = dict(zip("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ"))
SUP.update({c: s for c, s in zip("abcdefghjklmoprstuvwxyzT", "ᵃᵇᶜᵈᵉᶠᵍʰʲᵏˡᵐᵒᵖʳˢᵗᵘᵛʷˣʸᶻᵀ")})
SUB = dict(zip("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎"))
SUB.update({c: s for c, s in zip("aehijklmnoprstuvx", "ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ")})
ACCENTS = {"hat": "̂", "vec": "⃗", "bar": "̄", "overline": "̄", "dot": "̇",
           "ddot": "̈", "tilde": "̃", "check": "̌", "breve": "̆", "acute": "́"}
TEXT_CMDS = {"text", "mathrm", "mathbf", "mathit", "mathsf", "mathtt", "textbf", "textit", "operatorname",
             "mathcal", "boldsymbol", "bm", "mathfrak", "textrm", "mbox", "displaystyle", "textstyle"}
SKIP_CMDS = {"left", "right", "big", "Big", "bigg", "Bigg", "limits", "nolimits", "displaystyle", "textstyle",
             "scriptstyle", "mathstrut", "phantom", "vphantom", "hphantom", "nonumber", "notag"}


def _script(body, table, mark):
    if body != "" and all(ch in table for ch in body):
        return "".join(table[ch] for ch in body)
    return f"{mark}({body})" if len(body) > 1 else f"{mark}{body}"


def _simple(s):
    return bool(re.fullmatch(r"[\w²³¹⁰-⁹₀-₉αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΥΦΨΩ]+", s))


class _Parser:
    def __init__(self, s):
        self.s, self.i = s, 0

    def parse(self, stop=None):
        out = []
        while self.i < len(self.s):
            ch = self.s[self.i]
            if stop and ch == stop:
                self.i += 1
                return "".join(out)
            if ch == "{":
                self.i += 1
                out.append(self.parse("}"))
            elif ch == "\\":
                out.append(self.command())
            elif ch in "^_":
                self.i += 1
                body = self.arg()
                out.append(_script(body, SUP if ch == "^" else SUB, ch))
            elif ch == "~":
                self.i += 1
                out.append(" ")
            else:
                self.i += 1
                out.append(ch)
        return "".join(out)

    def arg(self):
        """One argument: a {group}, a \\command, or a single character."""
        if self.i >= len(self.s):
            return ""
        ch = self.s[self.i]
        if ch == "{":
            self.i += 1
            return self.parse("}")
        if ch == "\\":
            return self.command()
        self.i += 1
        return ch

    def command(self):
        self.i += 1  # backslash
        m = re.match(r"[A-Za-z]+", self.s[self.i:])
        if m:
            name = m.group(0)
            self.i += len(name)
        elif self.i < len(self.s):
            name = self.s[self.i]
            self.i += 1
        else:
            return "\\"
        # peek for \mathbb{R}-style lookups
        if name == "mathbb":
            save = self.i
            body = self.arg()
            key = f"mathbb{{{body}}}"
            if key in SYMBOLS:
                return SYMBOLS[key]
            self.i = save
            return self.arg()
        if name == "frac" or name == "dfrac" or name == "tfrac":
            a, b = self.arg(), self.arg()
            if _simple(a) and _simple(b):
                return f"{a}/{b}"
            return f"({a})/({b})"
        if name == "binom":
            a, b = self.arg(), self.arg()
            return f"C({a},{b})"
        if name == "sqrt":
            if self.s[self.i:self.i + 1] == "[":
                end = self.s.index("]", self.i)
                n = self.s[self.i + 1:end]
                self.i = end + 1
                return f"{_script(n, SUP, '^')}√({self.arg()})"
            body = self.arg()
            return f"√{body}" if _simple(body) and len(body) == 1 else f"√({body})"
        if name in ACCENTS:
            body = self.arg()
            return (body[0] + ACCENTS[name] + body[1:]) if body else ""
        if name in TEXT_CMDS:
            return self.arg()
        if name in SKIP_CMDS:
            return ""
        if name in GREEK:
            return GREEK[name]
        if name in SYMBOLS:
            return SYMBOLS[name]
        return name  # \sin, \log, \max, … → sin, log, max


def math_to_text(latex):
    try:
        from pylatexenc.latex2text import LatexNodes2Text  # optional, better coverage
        return LatexNodes2Text(math_mode="text").latex_to_text(latex).strip()
    except Exception:
        pass
    try:
        out = _Parser(latex).parse()
    except Exception:
        return latex
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


MATH_RE = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\$(.+?)\$|\\\((.+?)\\\)", re.S)


def render(text):
    """Convert every math segment in `text`; leave prose alone (light markdown cleanup)."""
    if not text:
        return text

    def sub(m):
        body = next(g for g in m.groups() if g is not None)
        return math_to_text(body)

    out = MATH_RE.sub(sub, text)
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", out)  # bold markers add noise in a TUI
    out = re.sub(r"`([^`]+)`", r"\1", out)
    return out


if __name__ == "__main__":
    import sys
    print(render(" ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()))
