# ClauseGuard synthetic data

All agreements here are **synthetic**. They are assembled from a hand-written clause library, so every clause's label is known exactly. Names, addresses and pincodes are random and fictional.

## Generate

```bash
pip install pyyaml
python evals/generate_agreements.py --n 100 --seed 42
```

The same seed always gives the same files. Useful options: `--risk-rate 0.6` for more risky clauses, `--out data/generated_small` for another folder.

## What you get (in `data/generated/`)

| File | Contents |
| --- | --- |
| `agreements/AGR-0001.txt` | One plain-text rental agreement per file |
| `labels.jsonl` | One row per clause: category, `fair` / `risky` / `neutral`, severity, risk type, the reason, and exact character offsets into the agreement |
| `agreements.jsonl` | One row per agreement: city, split (`dev` or `test`), and its risky clauses |
| `manifest.json` | Settings and label counts |

Tune prompts on the `dev` split only, and report final numbers on `test`.

## Dev and test never share clause wording

Every variant in the library is written twice: a `dev` wording and a `test` wording with the same meaning and the same placeholders. A dev agreement uses only dev wordings and a test agreement only test wordings. So when you tune prompts on dev, the test score measures how the reviewer handles wording it has never seen, not how well it remembers dev sentences.

The generator enforces this: it refuses a library where two wordings are identical, and it checks the output for any test clause that also appears in dev. Each risk type still appears in both splits, so every kind of risk can be tuned on dev and measured on test. Neutral clauses (rent, term, utilities) are shared between splits, since they carry no risk label.

## The clause library (`data/clause_library/`)

| File | Fair | Risky | Notes |
| --- | --- | --- | --- |
| `security_deposit.yaml` | 4 (1 hard negative) | 5 | Baseline: deposit at most two months' rent |
| `repairs_painting.yaml` | 6 (2 hard negatives) | 6 | Includes the deep-cleaning-and-painting clause |
| `landlord_entry.yaml` | 4 (1 hard negative) | 4 | Baseline: 24 hours' notice |
| `general.yaml` | — | — | Neutral clauses (rent, term, utilities…) that make agreements read naturally |

A **hard negative** is a fair clause that sounds strict, such as "the tenant pays for damage they cause". These test whether the model over-flags.

## Adding a category

Copy one of the category files, give every variant a new unique `id` and two different wordings (`dev` and `test`), include at least one fair and one risky variant, then add the category name to `RISK_CATEGORIES` and `CLAUSE_ORDER` in `evals/generate_agreements.py`. The script validates the library on every run.
