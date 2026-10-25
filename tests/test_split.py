import pytest

from clauseguard.graph.nodes.split import split_clauses, split_node


def numbers(result):
    return [c["number"] for c in result["clauses"]]


def assert_offsets(text, result):
    for c in result["clauses"]:
        assert text[c["start"]:c["end"]] == c["text"]


STANDARD = """RENTAL AGREEMENT

This agreement is made between A (Landlord) and B (Tenant).

1. The rent is Rs. 20,000 per month.

2. The deposit is two months' rent.

3. The Landlord shall give 24 hours' notice before entry.

IN WITNESS WHEREOF the parties have signed.

LANDLORD: A     TENANT: B
"""


def test_standard_numbering():
    r = split_clauses(STANDARD)
    assert r["method"] == "numbered"
    assert numbers(r) == [1, 2, 3]
    assert r["clauses"][0]["text"] == "The rent is Rs. 20,000 per month."
    assert r["preamble"].endswith("B (Tenant).")
    assert_offsets(STANDARD, r)


def test_signature_block_is_not_part_of_last_clause():
    r = split_clauses(STANDARD)
    assert "WITNESS" not in r["clauses"][-1]["text"]
    assert "LANDLORD" not in r["clauses"][-1]["text"]


def test_parenthesis_and_clause_prefix_styles():
    for marker in ["{n})", "({n})", "Clause {n}:", "clause {n}."]:
        text = "\n".join(f"{marker.format(n=n)} Term number {n}." for n in range(1, 5))
        r = split_clauses(text)
        assert numbers(r) == [1, 2, 3, 4], marker
        assert r["clauses"][1]["text"] == "Term number 2."
        assert_offsets(text, r)


def test_wrapped_lines_stay_in_one_clause():
    text = (
        "1. The Tenant shall pay a security deposit of Rs. 1,20,000, equal to\n"
        "six months' rent, before taking possession.\n"
        "2. The Landlord may enter after 24 hours'\n"
        "notice.\n"
        "3. Either party may end this agreement on one month's notice.\n"
    )
    r = split_clauses(text)
    assert numbers(r) == [1, 2, 3]
    assert "six months' rent" in r["clauses"][0]["text"]
    assert_offsets(text, r)


def test_sub_clauses_stay_inside_parent():
    text = (
        "1. Rent.\n"
        "2. Repairs:\n"
        "2.1 The Landlord handles structural repairs.\n"
        "2.2 The Tenant handles minor repairs.\n"
        "3. Entry.\n"
    )
    r = split_clauses(text)
    assert numbers(r) == [1, 2, 3]
    assert "2.2 The Tenant" in r["clauses"][1]["text"]


def test_out_of_sequence_number_is_ignored():
    # The "1." line inside clause 3 is a list item, not a new clause.
    text = (
        "1. Rent.\n"
        "2. Deposit.\n"
        "3. The Tenant shall not:\n"
        "1. keep pets,\n"
        "4. Entry.\n"
    )
    r = split_clauses(text)
    assert numbers(r) == [1, 2, 3, 4]
    assert "keep pets" in r["clauses"][2]["text"]


def test_unnumbered_text_falls_back_to_paragraphs():
    text = (
        "RENTAL AGREEMENT\n\n"
        "The rent is Rs. 20,000 per month.\n\n"
        "The deposit is two months' rent.\n\n"
        "IN WITNESS WHEREOF the parties have signed.\n"
    )
    r = split_clauses(text)
    assert r["method"] == "paragraphs"
    assert [c["text"] for c in r["clauses"]] == [
        "The rent is Rs. 20,000 per month.",
        "The deposit is two months' rent.",
    ]
    assert_offsets(text, r)


def test_node_returns_state_update():
    update = split_node({"document_text": STANDARD})
    assert set(update) == {"clauses", "preamble", "split_method", "split_warnings"}
    assert len(update["clauses"]) == 3
    assert update["split_warnings"] == []


# ---- added after the first evaluation exposed these failures ----

def test_skipped_number_keeps_later_clauses_separate():
    text = "1. Rent.\n2. Deposit.\n3. Repairs.\n5. Entry.\n6. Notice.\n"
    r = split_clauses(text)
    assert numbers(r) == [1, 2, 3, 5, 6]
    assert r["clauses"][2]["text"] == "Repairs."
    assert len(r["warnings"]) == 1 and "clause 4 was not found" in r["warnings"][0]
    assert_offsets(text, r)


def test_gap_larger_than_limit_is_not_bridged():
    # 3 -> 9 is too large a jump to be a missing clause, so "9." stays inside clause 3.
    text = "1. Rent.\n2. Deposit.\n3. Repairs, see item\n9. of the schedule.\n"
    r = split_clauses(text)
    assert numbers(r) == [1, 2, 3]
    assert "9. of the schedule" in r["clauses"][2]["text"]


def test_no_space_after_marker():
    text = "1.Rent.\n2.Deposit.\n3)Repairs.\n4.Entry.\n"
    r = split_clauses(text)
    assert numbers(r) == [1, 2, 3, 4]
    assert r["clauses"][0]["text"] == "Rent."
    assert_offsets(text, r)


def test_marker_on_its_own_line():
    text = "1.\nRent is due monthly.\n2.\nDeposit.\n3.\nRepairs.\n"
    r = split_clauses(text)
    assert numbers(r) == [1, 2, 3]
    assert r["clauses"][0]["text"] == "Rent is due monthly."


def test_decimal_and_time_at_line_start_are_not_markers():
    text = "1. Rent is\n10.30 a.m. on the 5th.\n2. Deposit of\n1.5 lakh.\n3. Repairs.\n"
    r = split_clauses(text)
    assert numbers(r) == [1, 2, 3]
    assert "10.30 a.m." in r["clauses"][0]["text"]
    assert "1.5 lakh" in r["clauses"][1]["text"]


def test_stray_higher_number_inside_clause_does_not_hijack_sequence():
    # With a greedy scan that allows gaps, "5. stray" would be taken as clause 5
    # and the real clauses 4 and 5 would be lost. The longest chain avoids that.
    text = "1. A.\n2. B.\n3. C includes:\n5. stray item\n4. D.\n5. E.\n6. F.\n"
    r = split_clauses(text)
    assert numbers(r) == [1, 2, 3, 4, 5, 6]
    assert "5. stray item" in r["clauses"][2]["text"]
    assert r["warnings"] == []


def test_paragraph_fallback_reports_a_warning():
    r = split_clauses("The rent is due.\n\nThe deposit is two months' rent.\n")
    assert r["method"] == "paragraphs"
    assert r["warnings"] and "No clause numbering" in r["warnings"][0]


@pytest.mark.xfail(strict=True, reason="Known limitation: a numbered list in the preamble "
                   "is taken as clause 1. Ties are broken towards the earlier marker, which is "
                   "right for lists nested inside clauses but wrong here.")
def test_numbered_list_in_preamble():
    text = "Parties:\n1. Mr A\n\n1. Rent.\n2. Deposit.\n3. Repairs.\n"
    r = split_clauses(text)
    assert r["clauses"][0]["text"] == "Rent."
