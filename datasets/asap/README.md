# Datasets D & E — ASAP-AES and ASAP-SAS

Established Hewlett Foundation "Automated Student Assessment Prize"
benchmarks, hosted on Kaggle. Used only as **secondary** baselines —
neither is this project's primary criterion-level dataset (Sections 29–30
are explicit about this; don't present results here as the headline
evaluation).

## ASAP-AES (Dataset D — holistic essay-scoring baseline)

https://www.kaggle.com/c/asap-aes

Use for: baseline comparison against holistic (non-rubric) scoring, and
generalization testing outside the rubric-entailment framing.

## ASAP-SAS (Dataset E — short-answer secondary benchmark)

https://www.kaggle.com/c/asap-sas

10 prompts spanning science, biology, and English/ELA, each answer scored
by two human raters. Use for: additional short-answer benchmarking and
generalization testing.

## Access

Both require a (free) Kaggle account and, for programmatic access, a
Kaggle API token (`~/.kaggle/kaggle.json`) — not fetched automatically as
part of this project. Once you have credentials:

```bash
pip install kaggle
kaggle competitions download -c asap-aes
kaggle competitions download -c asap-sas
```
