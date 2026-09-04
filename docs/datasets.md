# Datasets

Per Section 26 of the project spec: these five datasets serve **different**
purposes and are deliberately not pooled into one training set (Section 31).
None has been downloaded or evaluated inside this build — see
[Build environment constraints](#build-environment-constraints) below for
why, and `evaluation/` for the (currently empty, honestly labeled) results
this framework will produce once that changes.

All links below were verified against live search results while writing
this documentation, not reconstructed from memory.

## Dataset A — RiceChem (primary rubric/long-answer benchmark)

The core benchmark for criterion-level grading, NLI, rubric alignment, and
evidence evaluation. 1,264 long-form chemistry answers, 27 rubric items,
8,392 rubric-response data points, formulated as a rubric-entailment
problem — the same framing this project's NLI layer uses.

- Paper (arXiv): https://arxiv.org/abs/2404.14316
- Paper (AIED 2024 proceedings, Springer): https://doi.org/10.1007/978-3-031-64302-6_12
- Code + dataset request: https://github.com/luffycodes/Automated-Long-Answer-Grading

**Access note:** the dataset itself is gated behind a Google Form request
from the authors (linked from the GitHub repo), not a direct download —
plan for that lead time before Phase 7 work starts.

## Dataset B — Pecuchova et al. (external higher-education validation)

110 university students, 1,885 responses to 24 open-ended software-engineering
questions (Scrum concepts), reference answers, and two independent human
grader scores per response — exactly the shape needed to measure
human-AI score agreement (Section 43).

- Paper: Pecuchova, J., Benko, Ľ., & Drlik, M. (2025). Automated Grading of
  Open-Ended Questions in Higher Education Using GenAI Models.
  *International Journal of Artificial Intelligence in Education*, 35,
  3813–3846. https://doi.org/10.1007/s40593-025-00517-2
- Dataset (GitHub, openly available): https://github.com/J-Pecuchova/genai-automated-grading

## Dataset C — Handwritten ASAP-SAS (OCR/HTR evaluation)

Gold, C. & Zesch, T. *Handwritten ASAP Short Answer Scoring*. Zenodo, 2020.
DOI: [10.5281/zenodo.8088866](https://doi.org/10.5281/zenodo.8088866). Student
volunteers re-wrote a subset of ASAP-SAS answers by hand so the full
pipeline (handwritten image → recognition → automated scoring) can be
evaluated end to end, which is exactly what `services/ocr.py`'s
`recognize()` interface is built to consume.

**Access note:** Zenodo is not reachable from this build sandbox's network
allowlist (`huggingface.co` and `zenodo.org` both returned
`host_not_allowed` when tested — see the root README). Download this in an
environment with normal internet access and place it under
`datasets/handwritten/`.

## Dataset D — ASAP-AES (holistic essay-scoring baseline)

The Hewlett Foundation's Automated Student Assessment Prize essay-scoring
dataset (Kaggle: `kaggle.com/c/asap-aes`). Used only for baseline/holistic
scoring comparison and generalization testing — **not** treated as this
project's primary criterion-level dataset (Section 29 is explicit about
this).

## Dataset E — ASAP-SAS (short-answer secondary benchmark)

The companion short-answer-scoring track of the same prize (Kaggle:
`kaggle.com/c/asap-sas`) — 10 prompts across science/biology/English,
answers double-scored by two human raters. Secondary benchmark for
generalization testing (Section 30).

## Build environment constraints

This backend was built in a sandboxed container whose network egress
allowlist includes `github.com`, `pypi.org`, and the Ubuntu package
mirrors, but **not** `huggingface.co` or `zenodo.org`. Practically, that
means from *this* environment:

| Source | Reachable here? |
|---|---|
| RiceChem GitHub repo/code | Yes |
| Pecuchova GitHub dataset | Yes |
| Handwritten ASAP-SAS (Zenodo) | **No** — download elsewhere, then copy in |
| Kaggle (ASAP-AES/SAS) | Untested here; typically requires Kaggle auth regardless |
| Sentence-transformers / transformers model weights (Hugging Face Hub) | **No** — see root README |

None of this blocks building or running the actual application — it only
blocks the *research-evaluation* phase (Phase 7/8), which needs the real
data downloaded in an environment that can reach it.

## Folder layout

```
datasets/
├── ricechem/      — download script + README (request-gated, see above)
├── pecuchova/      — download script + README (openly cloneable)
├── asap/           — README with Kaggle instructions (AES + SAS)
└── handwritten/     — README with the Zenodo DOI and manual-download steps
```

Each subfolder's README documents exactly how to populate it; none contain
fabricated or placeholder data files.
