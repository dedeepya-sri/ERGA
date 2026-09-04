# Dataset C — Handwritten ASAP-SAS

For evaluating the OCR/HTR pipeline end to end: handwritten image →
recognition → automated scoring, against `services/ocr.py`'s
`OCREngine.recognize()` interface.

- Gold, C. & Zesch, T. (2020). *Handwritten ASAP Short Answer Scoring*.
  Version 1.0. Zenodo. DOI:
  [10.5281/zenodo.8088866](https://doi.org/10.5281/zenodo.8088866)
- Direct record: https://zenodo.org/records/8088866

## Access note (specific to this build environment)

This project was built inside a sandboxed container whose network
allowlist does not include `zenodo.org` — a direct `curl`/`wget` to it
from that sandbox returned `host_not_allowed`. **This is a constraint of
the build environment, not of the dataset**: it's openly downloadable
from Zenodo with a normal internet connection. Download it yourself and
place the extracted contents in this folder.

## What it contains

Based on the ASAP-SAS short-answer dataset; since the original scans no
longer exist, student volunteers re-wrote a subset of the SAS answers by
hand (from both the original train and test splits), giving genuine
handwritten images paired with known ground-truth text and scores.

## Use for

- Handwriting recognition evaluation
- OCR/HTR Character Error Rate / Word Error Rate (Section 43)
- Establishing a real (not assumed) recognition-confidence baseline for
  handwritten input, which this build's `ocr.handwriting_force_review`
  policy currently substitutes for with an unconditional review flag —
  see `docs/methodology.md`
