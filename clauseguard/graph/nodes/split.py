"""Clause splitter: the first node of the ClauseGuard graph.

Turns the agreement text into a list of clauses with exact character offsets.

Strategy:
1. Look for numbered clause markers at the start of a line ("1.", "1)", "(1)",
   "Clause 1:"). Accept a marker only if it continues the sequence 1, 2, 3...,
   which ignores stray numbers such as a list inside a clause or a wrapped line
   that happens to start with a number. Sub-clauses like "4.1" stay inside 4.
2. Stop the last clause at the signature block ("IN WITNESS WHEREOF", ...).
3. If fewer than MIN_NUMBERED clauses are found, fall back to splitting on blank
   lines. An LLM-based splitter for messy documents is planned as a later
   fallback; this module stays free of model calls so it is fast and testable.
"""

from __future__ import annotations

import re
from typing import TypedDict

from clauseguard.graph.state import Clause, ClauseGuardState

MIN_NUMBERED = 3

# "1." "1)" "1:" "(1)" optionally preceded by "Clause", at the start of a line.
# (?!\d) stops "4.1" or "1.5" from counting as a new top-level clause.
MARKER = re.compile(
    r"^[ \t]*(?:clause[ \t]+)?(?:\((\d{1,2})\)|(\d{1,2})[.):])(?!\d)[ \t]+",
    re.IGNORECASE | re.MULTILINE,
)

# Lines that start the signature block; nothing after them is a clause.
END_OF_CLAUSES = re.compile(
    r"^[ \t]*(?:IN WITNESS WHEREOF|SIGNED AND DELIVERED|LANDLORD[ \t]*:|WITNESSES?\b)",
    re.IGNORECASE | re.MULTILINE,
)

# Short all-caps lines such as "RENTAL AGREEMENT" or "SCHEDULE".
HEADING = re.compile(r"^[^a-z]{1,60}$")


class SplitResult(TypedDict):
    clauses: list[Clause]
    preamble: str
    method: str


def _trimmed(text: str, start: int, end: int) -> tuple[int, int]:
    """Move start/end inwards past surrounding whitespace."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _marker_number(marker: re.Match[str]) -> int:
    return int(marker.group(1) or marker.group(2))


def _body_end(text: str, start: int = 0) -> int:
    """Return the offset where clause content ends, before any signature block."""
    end_match = END_OF_CLAUSES.search(text, start)
    return end_match.start() if end_match else len(text)


def _split_numbered(text: str, markers: list[re.Match]) -> SplitResult:
    first = markers[0]
    body_end = _body_end(text, markers[-1].end())

    clauses: list[Clause] = []
    for i, m in enumerate(markers):
        number = _marker_number(m)
        stop = markers[i + 1].start() if i + 1 < len(markers) else body_end
        start, end = _trimmed(text, m.end(), stop)
        clauses.append({"number": number, "text": text[start:end], "start": start, "end": end})

    p_start, p_end = _trimmed(text, 0, first.start())
    return {"clauses": clauses, "preamble": text[p_start:p_end], "method": "numbered"}

def _split_paragraphs(text: str) -> SplitResult:
    body_end = _body_end(text)

    clauses: list[Clause] = []
    for block in re.finditer(r"\S(?:.*?)(?=\n[ \t]*\n|\Z)", text[:body_end], re.DOTALL):
        start, end = _trimmed(text, block.start(), block.end())
        para = text[start:end]
        if HEADING.match(para):
            continue
        clauses.append({"number": len(clauses) + 1, "text": para, "start": start, "end": end})
    return {"clauses": clauses, "preamble": "", "method": "paragraphs"}


def split_clauses(text: str) -> SplitResult:
    """Split an agreement into clauses. Offsets always index into `text`."""
    accepted: list[re.Match] = []
    expected = 1
    for m in MARKER.finditer(text):
        if _marker_number(m) == expected:
            accepted.append(m)
            expected += 1

    if len(accepted) >= MIN_NUMBERED:
        return _split_numbered(text, accepted)
    return _split_paragraphs(text)


def split_node(state: ClauseGuardState) -> dict:
    """LangGraph node: reads `document_text`, writes `clauses`, `preamble`, `split_method`."""
    result = split_clauses(state["document_text"])
    return {
        "clauses": result["clauses"],
        "preamble": result["preamble"],
        "split_method": result["method"],
    }
