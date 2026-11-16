#!/usr/bin/env bash
# Full pipeline, end to end: inspect -> prepare corpus -> validate -> align -> verify.
#
# This is the single entry point; run it from the repository root inside the
# MFA conda environment:
#
#   conda activate aligner
#   ./scripts/run_pipeline.sh
#
# Every MFA command it issues is appended to logs/commands.log.
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

PYTHON="${PYTHON:-python}"
CORPUS_DIR="$REPO_ROOT/data/corpus"
OUT_DIR="$REPO_ROOT/outputs"
DICTIONARY="${DICTIONARY:-english_us_arpa}"
ACOUSTIC_MODEL="${ACOUSTIC_MODEL:-english_us_arpa}"

log_command "# full pipeline run"

echo "############################################################"
echo "# 1/5  inspect the raw dataset"
echo "############################################################"
run_logged "$REPO_ROOT/logs/01_inspect.log" \
    "$PYTHON" "$REPO_ROOT/scripts/00_inspect_dataset.py"

echo
echo "############################################################"
echo "# 2/5  build the MFA corpus"
echo "############################################################"
run_logged "$REPO_ROOT/logs/01_prepare.log" \
    "$PYTHON" "$REPO_ROOT/scripts/01_prepare_corpus.py"

echo
echo "############################################################"
echo "# 3/5  validate"
echo "############################################################"
run_logged "$REPO_ROOT/logs/validate.log" \
    mfa validate "$CORPUS_DIR" "$DICTIONARY" --output_directory "$REPO_ROOT/logs/mfa_validate"

echo
echo "############################################################"
echo "# 4/5  align"
echo "############################################################"
run_logged "$REPO_ROOT/logs/align.log" \
    mfa align "$CORPUS_DIR" "$DICTIONARY" "$ACOUSTIC_MODEL" "$OUT_DIR" --clean

echo
echo "############################################################"
echo "# 5/5  verify TextGrid count == wav count"
echo "############################################################"
wav_count=$(find "$CORPUS_DIR" -name '*.wav' | wc -l | tr -d ' ')
grid_count=$(find "$OUT_DIR" -name '*.TextGrid' | wc -l | tr -d ' ')
echo "wav files      : $wav_count"
echo "TextGrid files : $grid_count"
if [ "$wav_count" -ne "$grid_count" ]; then
    echo "FAILED: counts differ"
    exit 1
fi
echo "OK: every wav has a TextGrid"
echo
echo "inspect and plot with:"
echo "  $PYTHON scripts/04_inspect_textgrids.py"
