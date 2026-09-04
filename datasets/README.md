# Datasets

See [`docs/datasets.md`](../docs/datasets.md) for full detail, verified
links, and licensing/access notes. Quick summary:

| Folder | Dataset | Access |
|---|---|---|
| `ricechem/` | RiceChem (1,264 long chemistry answers, 27 rubric items) | Code is open; data requires a Google Form request to the authors |
| `pecuchova/` | 1,885 open-ended software-engineering responses, 2 human graders | Openly cloneable from GitHub — `./pecuchova/download.sh` works as-is |
| `asap/` | ASAP-AES + ASAP-SAS (Kaggle) | Requires a Kaggle account/API token |
| `handwritten/` | Handwritten ASAP-SAS (Zenodo) | Openly downloadable, but **not reachable from this build's sandbox** — see note below |

No dataset has been downloaded into this repository. These are download
scripts and instructions only, not bundled data — per the project's own
Rule 1, nothing here should be mistaken for results already obtained.

**A note on the Zenodo dataset specifically:** this project was built in a
sandboxed environment whose network allowlist doesn't include
`zenodo.org` (confirmed by testing, not assumed — see the root README).
That has no bearing on whether *you* can reach it; `handwritten/README.md`
has the direct DOI link and works from any normal internet connection.
