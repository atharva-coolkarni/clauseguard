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
    assert set(update) == {"clauses", "preamble", "split_method"}
    assert len(update["clauses"]) == 3
