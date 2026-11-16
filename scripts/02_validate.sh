#!/usr/bin/env bash
# Phase 2c: validate the prepared corpus with MFA before aligning.
#
# Catches the problems MFA cares about: OOV words (words with no entry in the
# pronunciation dictionary), audio it cannot read, and empty transcripts.
#
#   ./scripts/02_validate.sh [corpus_dir] [dictionary]
#
# Defaults: corpus_dir=data/corpus, dictionary=english_us_arpa
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

CORPUS_DIR="${1:-$REPO_ROOT/data/corpus}"
DICTIONARY="${2:-${DICTIONARY:-english_us_arpa}}"

OUT_DIR="$REPO_ROOT/logs"

echo "=== MFA validate ==="
echo "corpus     : $CORPUS_DIR"
echo "dictionary : $DICTIONARY"
echo

# --output_directory keeps MFA's validation report next to our logs instead of
# inside the corpus directory, which we want to stay clean.
run_logged "$OUT_DIR/validate.log" \
    mfa validate "$CORPUS_DIR" "$DICTIONARY" --output_directory "$OUT_DIR/mfa_validate"

echo
echo "validation log : $OUT_DIR/validate.log"
