"""Generate synthetic Indian rental agreements with clause-level labels.

Every agreement is assembled from the clause library in data/clause_library/,
so the ground truth for each clause (category, fair/risky, severity, risk type)
is known by construction. No real data is needed to start evaluating.

Each agreement is assigned to the dev or test split. Every library clause has a
separate dev and test wording, and an agreement uses only its split's wording,
so test agreements contain no scored clause text that appears in dev.

Usage:
    python evals/generate_agreements.py --n 100 --seed 42
    python evals/generate_agreements.py --n 20 --risk-rate 0.6 --out data/generated_small

Outputs (in --out, default data/generated):
    agreements/AGR-0001.txt   one plain-text agreement per file
    labels.jsonl              one row per clause, with exact character offsets
    agreements.jsonl          one row per agreement (city, split, risky clauses)
    manifest.json             settings and label counts

The same --seed always produces the same files.
"""

from __future__ import annotations

import argparse
import calendar
import json
import random
import string
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIBRARY = ROOT / "data" / "clause_library"
DEFAULT_OUT = ROOT / "data" / "generated"

# Order of numbered clauses. Names in RISK_CATEGORIES come from category files;
# the rest are neutral sections from general.yaml.
RISK_CATEGORIES = ["security_deposit", "repairs_painting", "landlord_entry"]
CLAUSE_ORDER = [
    "premises",
    "term",
    "rent",
    "security_deposit",
    "utilities",
    "use",
    "repairs_painting",
    "landlord_entry",
    "termination",
    "registration",
    "jurisdiction",
]
# Pairs of neighbouring clauses that may swap places, so positions vary a little.
SWAPPABLE = [("utilities", "use"), ("repairs_painting", "landlord_entry")]

VALID_SEVERITY = {"fair": {"none"}, "risky": {"low", "medium", "high"}}
SPLITS = ("dev", "test")


def placeholders(template: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(template) if f}

# Fictional profile data. Addresses and pincodes are random and not real places.
CITIES = [
    ("Bengaluru", "Karnataka", "560", ["Koramangala", "HSR Layout", "Indiranagar", "Whitefield", "Jayanagar"]),
    ("Hyderabad", "Telangana", "500", ["Madhapur", "Kondapur", "Gachibowli", "Kukatpally", "Begumpet"]),
    ("Pune", "Maharashtra", "411", ["Kothrud", "Baner", "Hinjewadi", "Viman Nagar", "Aundh"]),
    ("Chennai", "Tamil Nadu", "600", ["Adyar", "Velachery", "T. Nagar", "Anna Nagar", "Thoraipakkam"]),
    ("Mumbai", "Maharashtra", "400", ["Andheri West", "Powai", "Goregaon East", "Chembur", "Malad West"]),
    ("New Delhi", "Delhi", "110", ["Lajpat Nagar", "Dwarka", "Saket", "Rohini", "Mayur Vihar"]),
    ("Kolkata", "West Bengal", "700", ["Salt Lake", "New Town", "Ballygunge", "Behala", "Garia"]),
    ("Ahmedabad", "Gujarat", "380", ["Navrangpura", "Satellite", "Bopal", "Maninagar", "Vastrapur"]),
    ("Kochi", "Kerala", "682", ["Kakkanad", "Edappally", "Vyttila", "Kaloor", "Palarivattom"]),
    ("Noida", "Uttar Pradesh", "201", ["Sector 62", "Sector 50", "Sector 137", "Sector 18", "Sector 76"]),
]
FIRST_NAMES = [
    "Arjun", "Priya", "Rahul", "Sneha", "Karthik", "Ananya", "Vikram", "Divya", "Suresh", "Lakshmi",
    "Aditya", "Meera", "Rohan", "Kavya", "Imran", "Fatima", "Harpreet", "Joseph", "Ayesha", "Venkat",
    "Neha", "Sanjay", "Pooja", "Ravi", "Deepa", "Anil", "Swati", "Manoj", "Nikhil", "Shreya",
]
LAST_NAMES = [
    "Sharma", "Reddy", "Iyer", "Nair", "Patel", "Kulkarni", "Banerjee", "Singh", "Khan", "Das",
    "Menon", "Rao", "Gupta", "Joshi", "Mehta", "Pillai", "Chatterjee", "Fernandes", "Verma", "Shetty",
]
BUILDINGS = [
    "Sunrise Apartments", "Green Valley Residency", "Lakeview Towers", "Shanti Enclave",
    "Maple Heights", "Orchid Court", "Silver Oak Apartments", "Ganga Residency",
]
STREETS = ["MG Road", "Station Road", "Temple Street", "Main Road", "Church Street", "Park Avenue"]
NUMBER_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
    7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve",
}


# ---------------------------------------------------------------- formatting

def inr(amount: int) -> str:
    """Format an amount in the Indian numbering system, e.g. 120000 -> Rs. 1,20,000."""
    digits = str(int(amount))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"Rs. {digits}"


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def long_date(d: date) -> str:
    return f"{d.day} {calendar.month_name[d.month]} {d.year}"


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def months_text(n: int) -> str:
    """'one month's' / 'two months'' — the possessive form used before 'rent'."""
    word = NUMBER_WORDS.get(n, str(n))
    return f"{word} month's" if n == 1 else f"{word} months'"


# ---------------------------------------------------------------- library

def load_library(library_dir: Path) -> tuple[dict, dict]:
    """Return (categories, general_sections) and validate the library."""
    categories: dict[str, dict] = {}
    general: dict[str, list[str]] = {}
    seen_ids: set[str] = set()
    # Every wording in the library must be unique, so no dev template can
    # appear in a test agreement under another variant's name.
    seen_wordings: dict[str, str] = {}

    for path in sorted(library_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if "sections" in data:
            general = data["sections"]
            continue
        name = data["category"]
        for v in data["variants"]:
            vid = v["id"]
            if vid in seen_ids:
                raise ValueError(f"{path.name}: duplicate variant id {vid}")
            seen_ids.add(vid)
            if v["label"] not in VALID_SEVERITY:
                raise ValueError(f"{vid}: label must be fair or risky")
            if v["severity"] not in VALID_SEVERITY[v["label"]]:
                raise ValueError(f"{vid}: severity {v['severity']} does not fit label {v['label']}")
            for key, values in (v.get("params") or {}).items():
                if not values:
                    raise ValueError(f"{vid}: param {key} has no values")
            wordings = v.get("wordings") or {}
            if set(wordings) != set(SPLITS):
                raise ValueError(f"{vid}: needs exactly one 'dev' and one 'test' wording")
            if " ".join(wordings["dev"].split()) == " ".join(wordings["test"].split()):
                raise ValueError(f"{vid}: dev and test wordings must differ")
            if placeholders(wordings["dev"]) != placeholders(wordings["test"]):
                raise ValueError(f"{vid}: dev and test wordings use different placeholders")
            for split in SPLITS:
                key = " ".join(wordings[split].split())
                if key in seen_wordings:
                    raise ValueError(f"{vid}.{split}: same wording as {seen_wordings[key]}")
                seen_wordings[key] = f"{vid}.{split}"
        labels = {v["label"] for v in data["variants"]}
        if labels != {"fair", "risky"}:
            raise ValueError(f"{path.name}: needs at least one fair and one risky variant")
        categories[name] = data

    missing = [c for c in RISK_CATEGORIES if c not in categories]
    if missing:
        raise ValueError(f"missing category files for: {missing}")
    missing_sections = [s for s in CLAUSE_ORDER + ["preamble", "signature"]
                        if s not in RISK_CATEGORIES and s not in general]
    if missing_sections:
        raise ValueError(f"general.yaml is missing sections: {missing_sections}")
    return categories, general


# ---------------------------------------------------------------- generation

def person(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def make_profile(rng: random.Random) -> dict:
    """Random but self-consistent facts for one agreement."""
    city, state, pin_prefix, localities = rng.choice(CITIES)
    landlord, tenant = person(rng), person(rng)
    while tenant == landlord:
        tenant = person(rng)
    other_city = rng.choice([c for c in CITIES if c[0] != city])

    start = date(2026, rng.randint(1, 12), 1)
    term_months = rng.choice([11, 11, 11, 12])
    end = add_months(start, term_months) - timedelta(days=1)
    rent = rng.randrange(8000, 60001, 500)

    return {
        "city": city,
        "state": state,
        "locality": rng.choice(localities),
        "pincode": f"{pin_prefix}{rng.randint(1, 99):03d}",
        "building": rng.choice(BUILDINGS),
        "flat_no": rng.choice([f"{rng.choice('ABCD')}-{rng.randint(1, 14)}0{rng.randint(1, 4)}",
                               str(rng.randint(101, 1504))]),
        "bhk": rng.choice([1, 2, 2, 3]),
        "landlord": landlord,
        "tenant": tenant,
        "landlord_address": f"{rng.randint(1, 250)}, {rng.choice(STREETS)}, "
                            f"{rng.choice(localities)}, {city}",
        "tenant_address": f"{rng.randint(1, 250)}, {rng.choice(STREETS)}, "
                          f"{rng.choice(other_city[3])}, {other_city[0]}",
        "agreement_date": long_date(start - timedelta(days=rng.randint(3, 15))),
        "start_date": long_date(start),
        "end_date": long_date(end),
        "term_months_text": f"{NUMBER_WORDS[term_months]} months",
        "rent_value": rent,
        "rent": inr(rent),
        "due_day": ordinal(rng.choice([5, 7, 10])),
    }


def variant_values(variant: dict, profile: dict, rng: random.Random) -> dict:
    """Sample a variant's params and derive the placeholders that depend on them."""
    values: dict = {}
    for key, choices in (variant.get("params") or {}).items():
        values[key] = rng.choice(choices)
    if "deposit_months" in values:
        values["deposit_amount"] = inr(profile["rent_value"] * values["deposit_months"])
        values["deposit_months_text"] = months_text(values["deposit_months"])
    if "painting_charge" in values:
        values["painting_charge"] = inr(values["painting_charge"])
    return values


def fill(template: str, values: dict, where: str) -> str:
    try:
        text = template.format_map(values)
    except KeyError as missing:
        raise KeyError(f"{where}: no value for placeholder {missing}") from None
    leftover = placeholders(text)
    if leftover:
        raise ValueError(f"{where}: unfilled placeholders {leftover}")
    return text.strip()


def build_agreement(index: int, categories: dict, general: dict, rng: random.Random,
                    risk_rate: float, dev_fraction: float) -> tuple[str, list[dict], dict]:
    agreement_id = f"AGR-{index:04d}"
    split = "dev" if rng.random() < dev_fraction else "test"
    profile = make_profile(rng)

    order = list(CLAUSE_ORDER)
    for a, b in SWAPPABLE:
        if rng.random() < 0.5:
            i, j = order.index(a), order.index(b)
            order[i], order[j] = order[j], order[i]

    # Each piece: (section, clause_number or None, text, label fields)
    pieces: list[tuple[str, int | None, str, dict]] = []

    def neutral(section: str, number: int | None) -> None:
        options = general[section]
        k = rng.randrange(len(options))
        text = fill(options[k], profile, f"general.{section}[{k}]")
        pieces.append((section, number, text, {
            "category": "general", "variant_id": f"gen_{section}_{k + 1:02d}",
            "label": "neutral", "severity": "none", "risk_type": "none", "why": "",
            "params": {},
        }))

    neutral("preamble", None)
    for number, section in enumerate(order, start=1):
        if section not in RISK_CATEGORIES:
            neutral(section, number)
            continue
        label = "risky" if rng.random() < risk_rate else "fair"
        pool = [v for v in categories[section]["variants"] if v["label"] == label]
        variant = rng.choice(pool)
        params = variant_values(variant, profile, rng)
        # Dev agreements use the dev wording, test agreements the test wording,
        # so no test clause text is ever seen while tuning prompts on dev.
        text = fill(variant["wordings"][split], {**profile, **params}, f"{variant['id']}.{split}")
        pieces.append((section, number, text, {
            "category": section, "variant_id": variant["id"], "label": variant["label"],
            "severity": variant["severity"], "risk_type": variant["risk_type"],
            "why": variant["why"],
            "params": {k: v for k, v in params.items() if k in (variant.get("params") or {})},
        }))
    neutral("signature", None)

    # Render the document and record exact offsets of every clause's text.
    parts: list[str] = []
    cursor = 0
    rows: list[dict] = []

    def emit(chunk: str) -> int:
        nonlocal cursor
        start = cursor
        parts.append(chunk)
        cursor += len(chunk)
        return start

    emit("RENTAL AGREEMENT\n\n")
    for section, number, text, fields in pieces:
        if section == "signature":
            emit("\n")
        if number is not None:
            emit(f"{number}. ")
        start = emit(text)
        emit("\n\n")
        if section == "preamble":
            emit("NOW THIS AGREEMENT WITNESSES AS FOLLOWS:\n\n")
        rows.append({
            "agreement_id": agreement_id, "split": split, "clause_number": number,
            "section": section, **fields, "text": text,
            "start": start, "end": start + len(text),
        })
    document = "".join(parts).rstrip() + "\n"

    summary = {
        "agreement_id": agreement_id, "split": split,
        "city": profile["city"], "state": profile["state"],
        "file": f"agreements/{agreement_id}.txt",
        "n_clauses": sum(1 for r in rows if r["clause_number"] is not None),
        "risky_clauses": [
            {"clause_number": r["clause_number"], "variant_id": r["variant_id"],
             "severity": r["severity"], "risk_type": r["risk_type"]}
            for r in rows if r["label"] == "risky"
        ],
    }
    return document, rows, summary


def verify(document: str, rows: list[dict]) -> None:
    """Every label must point at text that appears in the document word for word."""
    for r in rows:
        if document[r["start"]:r["end"]] != r["text"]:
            raise AssertionError(f"{r['agreement_id']} clause {r['clause_number']}: offsets do not match text")


def check_no_leakage(rows: list[dict]) -> int:
    """Count scored test clauses whose filled-in text also appears in dev; should be 0.

    This is a cheap sanity check on the output. The real guarantee comes from
    load_library(), which requires every wording in the library to be unique.
    """
    dev = {" ".join(r["text"].split()) for r in rows if r["split"] == "dev" and r["label"] != "neutral"}
    return sum(1 for r in rows
               if r["split"] == "test" and r["label"] != "neutral" and " ".join(r["text"].split()) in dev)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=100, help="number of agreements (default 100)")
    parser.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    parser.add_argument("--risk-rate", type=float, default=0.4,
                        help="chance that each risk category gets a risky clause (default 0.4)")
    parser.add_argument("--dev-fraction", type=float, default=0.5,
                        help="share of agreements in the dev split; the rest are test (default 0.5)")
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    categories, general = load_library(args.library)
    rng = random.Random(args.seed)

    out_dir: Path = args.out
    (out_dir / "agreements").mkdir(parents=True, exist_ok=True)
    for old in (out_dir / "agreements").glob("AGR-*.txt"):
        old.unlink()

    all_rows: list[dict] = []
    summaries: list[dict] = []
    for i in range(1, args.n + 1):
        document, rows, summary = build_agreement(i, categories, general, rng,
                                                  args.risk_rate, args.dev_fraction)
        verify(document, rows)
        (out_dir / summary["file"]).write_text(document, encoding="utf-8")
        all_rows.extend(rows)
        summaries.append(summary)

    with open(out_dir / "labels.jsonl", "w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(out_dir / "agreements.jsonl", "w", encoding="utf-8") as f:
        for s in summaries:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    scored = [r for r in all_rows if r["label"] != "neutral"]
    leaked = check_no_leakage(all_rows)
    if leaked:
        raise AssertionError(f"{leaked} test clauses reuse dev wording")
    manifest = {
        "settings": {"n": args.n, "seed": args.seed, "risk_rate": args.risk_rate,
                     "dev_fraction": args.dev_fraction},
        "agreements_by_split": dict(Counter(s["split"] for s in summaries)),
        "agreements_with_no_risky_clause": sum(1 for s in summaries if not s["risky_clauses"]),
        "scored_clauses": len(scored),
        "by_category_and_label": {
            c: dict(Counter(r["label"] for r in scored if r["category"] == c)) for c in RISK_CATEGORIES
        },
        "risky_by_severity": dict(Counter(r["severity"] for r in scored if r["label"] == "risky")),
        "hard_negatives": sum(1 for r in scored if r["variant_id"].endswith("_hardneg")),
        "test_clauses_reusing_dev_wording": leaked,
        "by_variant": dict(sorted(Counter(r["variant_id"] for r in scored).items())),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Wrote {args.n} agreements to {out_dir}")
    print(f"  splits: {manifest['agreements_by_split']}")
    print(f"  scored clauses: {len(scored)} "
          f"(risky {sum(1 for r in scored if r['label'] == 'risky')}, "
          f"fair {sum(1 for r in scored if r['label'] == 'fair')}, "
          f"hard negatives {manifest['hard_negatives']})")
    print(f"  agreements with no risky clause: {manifest['agreements_with_no_risky_clause']}")
    print("  all clause offsets verified against the agreement text")
    print("  no test clause reuses dev wording")


if __name__ == "__main__":
    main()
