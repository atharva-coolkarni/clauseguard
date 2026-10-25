# ClauseGuard

An agentic AI reviewer for Indian rental agreements. It flags risky clauses, quotes the exact text as evidence, explains each risk in plain language, and suggests what to ask the landlord before signing.

Built with LangGraph and LangChain. Work in progress.

## Why I built this

I lost part of my security deposit at move-out because of a clause in my rental agreement that I had missed when I signed. ClauseGuard is the tool I wish I had used before signing.

## Status

- [x] Synthetic labelled dataset: clause library + generator ([data/README.md](data/README.md))
- [x] Clause splitter (first graph node)
- [ ] Parallel clause review with LangGraph
- [ ] Rules knowledge base and verifier
- [ ] Human review step and Gradio app
- [ ] Evaluation results
- [ ] Live demo on Hugging Face Spaces

## Quick start

```bash
pip install -r requirements.txt
python evals/generate_agreements.py --n 100 --seed 42
```

This writes 100 synthetic agreements with clause-level labels to `data/generated/`.

```bash
pip install -r requirements-dev.txt
python -m pytest              # unit tests
python evals/eval_splitter.py # splitter accuracy
```

## Results so far

**Clause splitter** on 100 synthetic agreements, including copies reformatted to look like real documents. "Risky recall" is the share of risky clauses that come out of the splitter intact, since those are the clauses that must reach the reviewer.

| Format | Precision | Recall | Risky recall |
| --- | --- | --- | --- |
| As generated | 100% | 100% | 100% |
| Wrapped lines, as copied from a PDF | 100% | 100% | 100% |
| Numbered "1)" or "Clause 1:" | 100% | 100% | 100% |
| No space after the number ("1.Rent") | 100% | 100% | 100% |
| Clause 4 missing from the numbering | 100% | 100% | 100% |
| Wrapped + "1)" + no blank lines | 100% | 100% | 100% |
| No clause numbers | 91.7% | 100% | 100% |

**What changed after the first version.** The first splitter accepted clause numbers strictly in order, one at a time. On the same data it scored 0% on "1.Rent"-style numbering, and a single missing clause number dropped recall to 18% and risky recall to 0%: everything after the gap merged into one clause. The splitter now picks the longest plausible sequence of clause numbers, allowing small gaps, and reports each gap as a warning for the final report.

**Limits.** The splitter and the generator share formatting conventions, so these numbers show the splitter handles layout changes, not that it handles every real agreement. Without clause numbers, the opening paragraph is counted as a clause. A numbered list in the preamble (for example, a list of tenants) is still taken as clause 1; this is recorded as an expected-failure test. Lettered and Roman numbering are not supported yet. An LLM fallback for messy documents is planned.

## Disclaimer

ClauseGuard gives general guidance, not legal advice. All agreements in this repo are synthetic, and the names and addresses in them are fictional.
