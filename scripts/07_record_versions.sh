#!/usr/bin/env bash
# Phase 1 record: write the exact tool / model versions used, to Report/versions.txt.
#
# Re-run this to regenerate the version block quoted in the report and README.
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

OUT="$REPO_ROOT/Report/versions.txt"
mkdir -p "$(dirname "$OUT")"

{
    echo "Forced alignment environment - recorded $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "======================================================================"
    echo
    echo "MFA"
    echo "  mfa version        : $(mfa version 2>&1 | tail -1)"
    echo "  install method     : conda (conda-forge), env 'aligner'"
    echo "  python in env      : $(python -V 2>&1)"
    echo
    echo "Key conda packages (conda list -n aligner)"
    if command -v conda >/dev/null 2>&1; then
        conda list -n aligner 2>/dev/null | grep -iE \
            "^(montreal-forced-aligner|kalpy|kaldi|praatio|numpy|scipy|matplotlib|soundfile|librosa|pandas|python|rich-click) " \
            | sed 's/^/  /'
    else
        echo "  (conda not on PATH; see environment.yml)"
    fi
    echo
    echo "Models (MFA model store: $MFA_ROOT/pretrained_models)"
    echo "  acoustic model     : english_us_arpa   (version v2.0.0)"
    echo "  acoustic model 2   : english_mfa       (version v2.0.0)"
    echo "  dictionary         : english_us_arpa   (version v2.0.0)"
    echo "  dictionary 2       : english_mfa       (version v2.0.0)"
    echo "  g2p model          : english_us_arpa   (version v2.0.0)"
    echo
    echo "Downloaded artefacts"
    for f in "$MFA_ROOT/pretrained_models/dictionary/english_us_arpa.dict" \
             "$MFA_ROOT/pretrained_models/dictionary/english_mfa.dict" \
             "$MFA_ROOT/pretrained_models/acoustic/english_us_arpa.zip" \
             "$MFA_ROOT/pretrained_models/acoustic/english_mfa.zip" \
             "$MFA_ROOT/pretrained_models/g2p/english_us_arpa.zip"; do
        if [ -f "$f" ]; then
            printf "  %-62s %10s bytes\n" "$(basename "$f")" "$(stat -c%s "$f")"
        fi
    done
    echo
    echo "Acoustic model details (mfa model inspect acoustic english_us_arpa)"
    mfa model inspect acoustic english_us_arpa 2>&1 | grep -E "name|Version|Train date|Architecture|Phone type|Feature type|Frame shift|speaker adaptation" | sed 's/^/  /' || true
} > "$OUT" 2>&1

cat "$OUT"
