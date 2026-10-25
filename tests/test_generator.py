import random

import pytest

from evals.generate_agreements import (
    DEFAULT_LIBRARY,
    build_agreement,
    check_no_leakage,
    inr,
    load_library,
    verify,
)


@pytest.fixture(scope="module")
def library():
    return load_library(DEFAULT_LIBRARY)


@pytest.fixture(scope="module")
def generated(library):
    categories, general = library
    rng = random.Random(7)
    return [build_agreement(i, categories, general, rng, risk_rate=0.5, dev_fraction=0.5)
            for i in range(1, 41)]


def test_indian_number_format():
    assert inr(500) == "Rs. 500"
    assert inr(18500) == "Rs. 18,500"
    assert inr(185000) == "Rs. 1,85,000"
    assert inr(12345678) == "Rs. 1,23,45,678"


def test_labels_point_at_exact_text(generated):
    for document, rows, _ in generated:
        verify(document, rows)  # raises if any offset is wrong


def test_agreements_use_only_their_split_wording(library, generated):
    categories, _ = library
    wordings = {v["id"]: v["wordings"] for c in categories.values() for v in c["variants"]}
    for document, rows, summary in generated:
        for r in rows:
            if r["label"] == "neutral":
                continue
            other = "test" if r["split"] == "dev" else "dev"
            # The first words of the other split's wording never appear in this clause.
            other_opening = " ".join(wordings[r["variant_id"]][other].split()[:6])
            assert other_opening not in " ".join(r["text"].split())


def test_no_scored_text_shared_between_splits(generated):
    rows = [r for _, agreement_rows, _ in generated for r in agreement_rows]
    assert check_no_leakage(rows) == 0


def test_library_rejects_identical_wordings(tmp_path):
    (tmp_path / "general.yaml").write_text((DEFAULT_LIBRARY / "general.yaml").read_text())
    for name in ["security_deposit", "repairs_painting", "landlord_entry"]:
        (tmp_path / f"{name}.yaml").write_text((DEFAULT_LIBRARY / f"{name}.yaml").read_text())
    bad = (tmp_path / "landlord_entry.yaml").read_text().replace(
        "For inspection, repairs or replacements, the Landlord shall enter the Premises only after\n"
        "        giving the Tenant written notice at least 24 hours in advance, and only between 8 a.m. and\n"
        "        8 p.m.",
        "The Landlord may enter the Premises for inspection, repairs or replacement after giving\n"
        "        the Tenant at least 24 hours' prior written notice, and only between 8 a.m. and 8 p.m.",
    )
    (tmp_path / "landlord_entry.yaml").write_text(bad)
    with pytest.raises(ValueError, match="must differ"):
        load_library(tmp_path)
