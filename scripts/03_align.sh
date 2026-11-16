#!/usr/bin/env bash
# Phase 3: run forced alignment with the downloaded acoustic model + dictionary.
#
#   ./scripts/03_align.sh [corpus_dir] [dictionary] [acoustic_model] [output_dir]
#
# Defaults: data/corpus, english_us_arpa, english_us_arpa, outputs
# After the run it checks that the number of TextGrids equals the number of
# wav files and reports any file that failed to align.
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

CORPUS_DIR="${1:-$REPO_ROOT/data/corpus}"
DICTIONARY="${2:-${DICTIONARY:-english_us_arpa}}"
ACOUSTIC_MODEL="${3:-${ACOUSTIC_MODEL:-english_us_arpa}}"
OUT_DIR="${4:-${OUT_DIR:-$REPO_ROOT/outputs}}"

echo "=== MFA align ==="
echo "corpus         : $CORPUS_DIR"
echo "dictionary     : $DICTIONARY"
echo "acoustic model : $ACOUSTIC_MODEL"
echo "output         : $OUT_DIR"
echo

run_logged "$REPO_ROOT/logs/align.log" \
    mfa align "$CORPUS_DIR" "$DICTIONARY" "$ACOUSTIC_MODEL" "$OUT_DIR" --clean

echo
echo "=== verifying output ==="
wav_count=$(find "$CORPUS_DIR" -name '*.wav' | wc -l | tr -d ' ')
grid_count=$(find "$OUT_DIR" -name '*.TextGrid' | wc -l | tr -d ' ')
echo "wav files       : $wav_count"
echo "TextGrid files  : $grid_count"

if [ "$wav_count" -eq "$grid_count" ]; then
    echo "RESULT: OK — TextGrid count matches wav count"
else
    echo "RESULT: MISMATCH — the following wav files have no TextGrid:"
    for wav in $(find "$CORPUS_DIR" -name '*.wav'); do
        stem="$(basename "$wav" .wav)"
        if ! find "$OUT_DIR" -name "$stem.TextGrid" | grep -q .; then
            echo "  - $stem"
        fi
    done
    exit 1
fi
