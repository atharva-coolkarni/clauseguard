"""Shared state passed between the nodes of the ClauseGuard graph.

Only the fields used so far are filled in; later nodes add theirs.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class Clause(TypedDict):
    """One clause found by the splitter.

    `start` and `end` are character offsets into `document_text`, so
    `document_text[start:end] == text` always holds. Later nodes use them to
    prove that a quoted clause really exists in the document.
    """

    number: int | None  # clause number as printed, or a running count for unnumbered text
    text: str
    start: int
    end: int


class ClauseGuardState(TypedDict, total=False):
    document_text: str
    region: str | None          # selects the rules pack, e.g. "india"
    preamble: str               # text before the first clause (parties, date)
    clauses: list[Clause]       # written by the splitter
    split_method: str           # "numbered" or "paragraphs"
    # Parallel reviewers append to this list; operator.add merges their results
    # instead of letting one branch overwrite another.
    flags: Annotated[list[dict], operator.add]
