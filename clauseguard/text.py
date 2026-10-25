"""Text helpers shared by the splitter evaluation and, later, the quote checker."""

from __future__ import annotations

import re

# A hyphen at the end of a line, as in "day-\nto-day" from a PDF.
_LINE_END_HYPHEN = re.compile(r"-[ \t]*\n[ \t]*")


def normalize(text: str) -> str:
    """Make two copies of the same clause comparable despite layout differences.

    Joins words broken across lines at a hyphen (keeping the hyphen, since
    "day-to-day" is more common in agreements than a split word like "repa-ir")
    and collapses all runs of whitespace to single spaces.
    """
    return " ".join(_LINE_END_HYPHEN.sub("-", text).split())
