# Dataset B — Pecuchova et al.

External higher-education validation set. **Openly available** and
verified cloneable (tested while building this project — see
`download.sh`).

- Paper: Pecuchova, J., Benko, Ľ., & Drlik, M. (2025). Automated Grading of
  Open-Ended Questions in Higher Education Using GenAI Models. *IJAIED*,
  35, 3813–3846. https://doi.org/10.1007/s40593-025-00517-2
- Data: https://github.com/J-Pecuchova/genai-automated-grading

## Structure (verified against the actual file)

Single semicolon-delimited CSV, `open_questions_grading.csv`, columns:

| Column | Meaning |
|---|---|
| `Id` | Unique response identifier |
| `QNumber` | Which of the 24 questions (1–24) |
| `Question` | The open-ended question text |
| `Answer` | The student's free-text answer |
| `Reference` | A reference/model answer from course materials |
| `Grade1` | First human grader's letter grade |
| `Grade2` | Second human grader's letter grade |

1,885 rows across 24 questions, 110 students, software-engineering/Scrum
domain.

## Use for

- CS/general university external validation
- Human-score agreement (two independent graders per response — ideal for
  Cohen's Kappa / Krippendorff's Alpha per `docs/methodology.md`)
- Comparison against SBERT/LLM holistic approaches

## Fetching it

```bash
./download.sh
```

This is a plain `git clone` of the public repository — no auth, no
request form. Not run automatically as part of building this project;
run it yourself when you're ready to work with real data.
