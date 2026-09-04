"""
Break a normalized answer into candidate evidence units (Section 8).

Implementation note: this is a deterministic, rule-based sentence/line
splitter rather than a statistical sentence tokenizer (e.g. nltk's `punkt`
or spaCy's parser). Both of those need a downloaded model/data package;
this one doesn't, so it works identically online or offline. It handles
common abbreviations and decimal numbers so it doesn't fracture sentences
like "e.g. Fig. 2.5 shows..." into nonsense fragments. Swap in spaCy/nltk
here if you need better handling of unusual punctuation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ABBREVIATIONS = {
    "e.g.", "i.e.", "etc.", "dr.", "mr.", "mrs.", "ms.", "vs.", "fig.",
    "eq.", "no.", "approx.", "et al.", "cf.", "viz.",
}

# Matches sentence-ending punctuation followed by whitespace and a capital
# letter/digit/quote — but we post-filter out false positives from the
# abbreviation list and decimal numbers (e.g. "3.5").
_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"\u2018\u2019\u201c\u201d(])')
_DECIMAL_RE = re.compile(r"\d\.\d")
_BULLET_RE = re.compile(r"^\s*(?:[-*\u2022\u25CF]|\(?\d+[.)]|\(?[a-zA-Z][.)])\s+")


@dataclass
class Segment:
    index: int
    text: str
    line: int  # 0-indexed source line, for coarse traceability


def _ends_with_abbreviation(fragment: str) -> bool:
    lowered = fragment.lower().rstrip()
    return any(lowered.endswith(abbr) for abbr in _ABBREVIATIONS)


def _split_sentences(paragraph: str) -> list[str]:
    # Protect decimals from being treated as sentence boundaries.
    protected = _DECIMAL_RE.sub(lambda m: m.group(0).replace(".", "\u0000"), paragraph)
    raw_parts = _SPLIT_RE.split(protected)

    sentences: list[str] = []
    buffer = ""
    for part in raw_parts:
        part = part.replace("\u0000", ".")
        buffer = f"{buffer} {part}".strip() if buffer else part
        if _ends_with_abbreviation(buffer):
            continue  # keep accumulating — that "." wasn't a sentence end
        sentences.append(buffer)
        buffer = ""
    if buffer:
        sentences.append(buffer)
    return [s.strip() for s in sentences if s.strip()]


def segment_into_sentences(text: str, min_chars: int = 3) -> list[Segment]:
    """
    Split `text` into evidence segments: first by line (so bullet points and
    manual line breaks are respected as authored), then each line by
    sentence-ending punctuation.
    """
    segments: list[Segment] = []
    idx = 0
    for line_no, raw_line in enumerate(text.splitlines()):
        line = _BULLET_RE.sub("", raw_line).strip()
        if not line:
            continue
        for sentence in _split_sentences(line):
            cleaned = sentence.strip()
            if len(cleaned) < min_chars:
                continue
            segments.append(Segment(index=idx, text=cleaned, line=line_no))
            idx += 1

    # Fallback: if the whole answer was one unbroken blob with no punctuation
    # that our splitter recognized, treat it as a single segment rather than
    # returning nothing.
    if not segments and text.strip():
        segments.append(Segment(index=0, text=text.strip(), line=0))

    return segments
