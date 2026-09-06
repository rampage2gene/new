"""Post-processing for OCR output on electrical documentation.

Two responsibilities:

1. Normalise common OCR renderings of technical notation without changing the
   meaning (``4 / 0 AWG`` -> ``4/0 AWG``, ``mm2`` -> ``mm²``, ``3O0`` -> ``300``).
2. Detect places where OCR could have produced a *different valid number*
   (3<->8, 1<->7, 0<->6/9, 5<->6, ``4 AWG`` vs ``4/0 AWG``, ``48 V`` vs ``480 V``)
   and report them as ambiguity candidates so the QC layer can flag them.

Every normalisation is recorded so the original text is never lost.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

DIGIT_CONFUSIONS = {
    "3": ["8"],
    "8": ["3", "6"],
    "1": ["7"],
    "7": ["1"],
    "0": ["6", "9", "8"],
    "6": ["0", "5", "8"],
    "9": ["0"],
    "5": ["6"],
}

LETTER_TO_DIGIT = {"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "B": "8", "Z": "2"}

UNIT_TOKEN = r"(?:k?V(?:DC|AC|dc|ac)?|k?W|k?VA|m?A|Ah|Hz|N[·.]?m|mm2|mm²|AWG|°[CF]|Ω|ohms?)"


@dataclass
class Normalisation:
    original: str
    normalised: str
    rule: str


@dataclass
class PostprocessResult:
    text: str
    normalisations: list[Normalisation] = field(default_factory=list)


_RULES: list[tuple[str, str, str]] = [
    # "4 / 0 AWG", "4 /0 AWG", "4-0 AWG", "4\\0 AWG" -> "4/0 AWG"
    (r"\b([1-4])\s*[/\\\-]\s*0\s*(AWG|awg)\b", r"\1/0 \2", "awg_slash"),
    # "0000 AWG" style
    (r"\b0000\s*AWG\b", "4/0 AWG", "awg_zeros"),
    (r"\b000\s*AWG\b", "3/0 AWG", "awg_zeros"),
    (r"\b00\s*AWG\b", "2/0 AWG", "awg_zeros"),
    # "#4/0" -> "4/0 AWG" handled by extractor; keep "#" but tidy spaces
    (r"#\s+(\d/0|\d{1,2})\b", r"#\1", "awg_hash"),
    # mm2 -> mm²
    (r"\bmm\s*(?:2|\^2)\b", "mm²", "mm2"),
    # "V DC"/"V AC" -> "VDC"/"VAC"
    (r"(\d)\s*V\s*(DC|AC)\b", r"\1 V\2", "v_dc_space"),
    (r"\bVdc\b", "VDC", "vdc_case"),
    (r"\bVac\b", "VAC", "vac_case"),
    # thin-space / comma thousands spacing: "12, 000" -> "12,000"
    (r"\b(\d{1,3}),\s+(\d{3})\b", r"\1,\2", "thousands"),
    # Degree symbol variants "° C" -> "°C", "deg C" -> "°C"
    (r"°\s+([CF])\b", r"°\1", "degree_space"),
    (r"\bdeg\.?\s*([CF])\b", r"°\1", "deg_word"),
    # Ohm variants
    (r"(\d)\s*(?:ohm|Ohm|OHM)s?\b", r"\1 Ω", "ohm_word"),
    # Torque: "N m" / "N-m" -> "N·m"
    (r"(\d)\s*N\s*[- ]\s*m\b", r"\1 N·m", "newton_metre"),
    (r"\bNm\b", "N·m", "nm"),
]


def _fix_letter_digits(token: str) -> str:
    """Replace letters that are obviously digits inside numeric tokens (3O0 -> 300)."""
    if not re.search(r"\d", token):
        return token
    letters = sum(ch.isalpha() for ch in token)
    digits = sum(ch.isdigit() for ch in token)
    if letters == 0 or letters > digits:
        return token
    if not re.fullmatch(r"[0-9OolISBZ.,/]+", token):
        return token
    return "".join(LETTER_TO_DIGIT.get(ch, ch) for ch in token)


def normalise_technical_text(text: str) -> PostprocessResult:
    result = PostprocessResult(text=text)
    out = text
    # Letter/digit confusion inside numeric tokens that precede a unit.
    def _repl(m: re.Match) -> str:
        fixed = _fix_letter_digits(m.group(1))
        if fixed != m.group(1):
            result.normalisations.append(Normalisation(m.group(1), fixed, "letter_digit"))
        return fixed + m.group(2)

    out = re.sub(r"\b([0-9OolISBZ][0-9OolISBZ.,/]*)(\s*" + UNIT_TOKEN + r"\b)", _repl, out)
    for pattern, repl, rule in _RULES:
        def _r(m: re.Match, repl=repl, rule=rule) -> str:
            new = m.expand(repl) if "\\" in repl else repl
            if new != m.group(0):
                result.normalisations.append(Normalisation(m.group(0), new, rule))
            return new

        out = re.sub(pattern, _r, out)
    result.text = out
    return result


def digit_alternatives(number_text: str, max_alternatives: int = 4) -> list[str]:
    """Plausible alternative readings of a number given common OCR confusions."""
    alts: list[str] = []
    for i, ch in enumerate(number_text):
        for alt in DIGIT_CONFUSIONS.get(ch, []):
            cand = number_text[:i] + alt + number_text[i + 1 :]
            if cand != number_text and cand not in alts:
                alts.append(cand)
            if len(alts) >= max_alternatives:
                return alts
    return alts


def awg_ambiguity(raw: str) -> str | None:
    """Return a note if an AWG token could be read as either N or N/0."""
    # "4 0 AWG" (space instead of slash) or "4O AWG" (letter O) are the ambiguous forms;
    # "10 AWG" / "40 AWG" written normally are not.
    m = re.search(r"\b([1-4])(?:\s+[0Oo]|[Oo])\s*AWG\b", raw)
    if not m:
        return None
    return f"'{m.group(0).strip()}' could be {m.group(1)}0 AWG or {m.group(1)}/0 AWG - verify against the page"
