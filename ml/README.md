# ml/

Scaffolding for Phase 7 (research evaluation) model-level work, as
distinct from `evaluation/`, which is for *system*-level evaluation
against the datasets in `docs/datasets.md`. Everything in this folder is
currently empty on purpose (Section 52 Rule 1 — no fabricated results,
metrics, or checkpoints).

- **`configs/`** — model-specific training configs, if you fine-tune a
  custom NLI or embedding model. The *serving-time* config that actually
  controls the running application is `backend/config/model_config.yaml`,
  not this folder — this is only for configs used to *produce* a model
  checkpoint in the first place.
- **`training/`** — training scripts, once there's a model worth training
  (e.g. fine-tuning a small NLI classifier on RiceChem/Pecuchova). Nothing
  here yet: the active NLI/embedding engines
  (`LexicalNLIAssessor`/`TfidfEmbedder`) are rule-based and need no
  training.
- **`evaluation/`** — held-out metrics for a specific trained model
  (accuracy curves, loss curves, confusion matrices). Different from
  top-level `evaluation/`, which measures the *whole system* end to end.
- **`checkpoints/`** — trained model weights. Empty; nothing has been
  trained. If you do fine-tune something, keep large weight files out of
  git (see `.gitignore`) and document the training run that produced them
  here instead.
