# Dataset A — RiceChem

Primary rubric/long-answer benchmark. 1,264 long chemistry answers, 27
rubric items, 8,392 rubric-response data points, framed as a
rubric-entailment problem — the same framing `services/nli.py` uses.

- Paper (arXiv): https://arxiv.org/abs/2404.14316
- Paper (AIED 2024, Springer): https://doi.org/10.1007/978-3-031-64302-6_12
- Code + data request form: https://github.com/luffycodes/Automated-Long-Answer-Grading

## Access (verified, not assumed)

The **code** repository is publicly cloneable — confirmed while building
this project (`./download_code.sh` below is a tested `git clone`). The
**data itself is gated**: the repo's README links to a Google Form the
authors use to vet requests, so there is a real lead time here — plan for
it before Phase 7 work starts. Do not expect `download_code.sh` to
produce the actual CSV/JSON data files; it only gets you the
preprocessing and modeling code.

## Use for

- Criterion-level grading, NLI, rubric alignment, evidence evaluation
  (Section 26) — this is the dataset closest in spirit to what
  `services/grading_pipeline.py` actually does.

## Fetching the code

```bash
./download_code.sh
```
