#!/usr/bin/env bash
# Downloads Dataset B (Pecuchova et al.) — openly available, no auth needed.
# Verified working (git clone tested) while building this project.
set -euo pipefail
cd "$(dirname "$0")"

if [ -d "genai-automated-grading" ]; then
  echo "Already present at ./genai-automated-grading — pulling latest."
  git -C genai-automated-grading pull
else
  git clone --depth 1 https://github.com/J-Pecuchova/genai-automated-grading.git
fi

echo "Done. Data file: ./genai-automated-grading/open_questions_grading.csv"
