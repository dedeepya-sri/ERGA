#!/usr/bin/env bash
# Downloads the RiceChem *code* repo (public). The dataset itself requires
# a separate request via the Google Form linked from that repo's README —
# see ./README.md. Verified working (git clone tested) while building
# this project.
set -euo pipefail
cd "$(dirname "$0")"

if [ -d "Automated-Long-Answer-Grading" ]; then
  echo "Already present — pulling latest."
  git -C Automated-Long-Answer-Grading pull
else
  git clone --depth 1 https://github.com/luffycodes/Automated-Long-Answer-Grading.git
fi

echo
echo "Code fetched. The dataset itself is NOT bundled in this repo — see"
echo "./README.md for the data-request form link."
