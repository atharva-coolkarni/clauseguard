"""Clause splitter: the first node of the ClauseGuard graph.

Turns the agreement text into a list of clauses with exact character offsets.

Strategy:
1. Find every possible clause marker at the start of a line: "1.", "1)", "1:",
   "(1)" or "Clause 1:", with or without a space before the text ("1.Rent").
   Sub-clauses like "4.1" are not markers, so they stay inside clause 4.
2. Choose the longest chain of markers whose numbers increase by at most
   MAX_GAP at each step. This keeps a numbered list inside a clause from
   breaking the real sequence, and tolerates a missing number (1, 2, 3, 5)
   instead of merging everything after the gap into one clause.
3. Stop the last clause at the signature block ("IN WITNESS WHEREOF", ...).
4. With fewer than MIN_NUMBERED markers, fall back to splitting on blank lines.

Anything unusual (a gap, numbering not starting at 1, the fallback) is
reported in `warnings`, so the final report can tell the user that part of
the document may not have been reviewed clause by clause.

An LLM-based splitter for messy documents is planned as a later fallback; this
module makes no model calls so it is fast, free and testable.
"""

from __future__ import annotations

import re
from typing import TypedDict

from clauseguard.graph.state import Clause, ClauseGuardState

MIN_NUMBERED = 3
# Largest allowed step between consecutive clause numbers: 3 accepts "3 -> 6"
# (two clauses missing) but not "3 -> 7".
MAX_GAP = 3

# "1." "1)" "1:" "(1)" optionally preceded by "Clause", at the start of a line,
# then whitespace (which may be a line break) or directly a non-digit character.
# (?!\d) stops "4.1", "1.5 lakh" or "10.30" from counting as a clause number.
MARKER = re.compile(
    r"^[ \t]*(?:clause[ \t]+)?(?:\((\d{1,2})\)|(\d{1,2})[.):])(?!\d)(?:\s+|(?=[^\s\d]))",
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
    warnings: list[str]


def _number(m: re.Match) -> int:
    return int(m.group(1) or m.group(2))


def _trimmed(text: str, start: int, end: int) -> tuple[int, int]:
    """Move start/end inwards past surrounding whitespace."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _best_chain(markers: list[re.Match]) -> list[re.Match]:
    """Longest chain of markers, in document order, with numbers rising by 1..MAX_GAP.

    Dynamic programming over the markers (there are only a few dozen, so the
    O(n^2) loop is instant). On a tie, the earlier predecessor wins, which
    prefers the main sequence over a numbered list nested inside a clause.
    """
    n = len(markers)
    length = [0] * n
    prev = [-1] * n
    for j in range(n):
        num_j = _number(markers[j])
        if num_j <= MAX_GAP:          # a chain may start here
            length[j] = 1
        for i in range(j):
            step = num_j - _number(markers[i])
            if length[i] and 0 < step <= MAX_GAP and length[i] + 1 > length[j]:
                length[j] = length[i] + 1
                prev[j] = i
    if not n or max(length) == 0:
        return []
    # Longest chain; among equally long chains, the one that ends latest covers more text.
    end = max(range(n), key=lambda j: (length[j], j))
    chain = []
    while end != -1:
        chain.append(markers[end])
        end = prev[end]
    return chain[::-1]


def _gap_warnings(chain: list[re.Match]) -> list[str]:
    warnings = []
    first = _number(chain[0])
    if first != 1:
        warnings.append(f"Clause numbering starts at {first}; earlier clauses may be in the preamble.")
    for a, b in zip(chain, chain[1:]):
        na, nb = _number(a), _number(b)
        if nb - na > 1:
            missing = ", ".join(str(k) for k in range(na + 1, nb))
            warnings.append(
                f"Numbering jumps from {na} to {nb}; clause {missing} was not found, "
                f"so its text may be included in clause {na}."
            )
    return warnings


def _split_numbered(text: str, chain: list[re.Match]) -> SplitResult:
    end_match = END_OF_CLAUSES.search(text, chain[-1].end())
    body_end = end_match.start() if end_match else len(text)

    clauses: list[Clause] = []
    for i, m in enumerate(chain):
        stop = chain[i + 1].start() if i + 1 < len(chain) else body_end
        start, end = _trimmed(text, m.end(), stop)
        clauses.append({"number": _number(m), "text": text[start:end], "start": start, "end": end})

    p_start, p_end = _trimmed(text, 0, chain[0].start())
    return {"clauses": clauses, "preamble": text[p_start:p_end], "method": "numbered",
            "warnings": _gap_warnings(chain)}


def _split_paragraphs(text: str) -> SplitResult:
    end_match = END_OF_CLAUSES.search(text)
    body_end = end_match.start() if end_match else len(text)

    clauses: list[Clause] = []
    for block in re.finditer(r"\S(?:.*?)(?=\n[ \t]*\n|\Z)", text[:body_end], re.DOTALL):
        start, end = _trimmed(text, block.start(), block.end())
        para = text[start:end]
        if HEADING.match(para):
            continue
        clauses.append({"number": len(clauses) + 1, "text": para, "start": start, "end": end})
    warning = ("No clause numbering found; the document was split on blank lines, "
               "so the opening paragraph may be treated as a clause.")
    return {"clauses": clauses, "preamble": "", "method": "paragraphs", "warnings": [warning]}


def split_clauses(text: str) -> SplitResult:
    """Split an agreement into clauses. Offsets always index into `text`."""
    chain = _best_chain(list(MARKER.finditer(text)))
    if len(chain) >= MIN_NUMBERED:
        return _split_numbered(text, chain)
    return _split_paragraphs(text)


def split_node(state: ClauseGuardState) -> dict:
    """LangGraph node: reads `document_text`; writes clauses, preamble, method and warnings."""
    result = split_clauses(state["document_text"])
    return {
        "clauses": result["clauses"],
        "preamble": result["preamble"],
        "split_method": result["method"],
        "split_warnings": result["warnings"],
    }
