#!/usr/bin/env python
"""Phase 5 (extra credit): build a custom dictionary from a G2P model.

The pretrained ``english_us_arpa`` dictionary is missing a handful of words that
appear in this dataset (proper nouns and one derived form).  This script merges

* every entry of the base dictionary, unchanged, and
* the ``mfa g2p`` pronunciations generated for the words the base dictionary
  does not contain,

into a single dictionary that can be handed to ``mfa align``.

The generated entries are written in the same tab-separated
``word<TAB>pronunciation`` form MFA's G2P command emits.  Any generated
pronunciation that uses a phone absent from the base dictionary's inventory is
dropped and reported, because MFA cannot align phones its acoustic model was
never trained on.

Usage
-----
    python scripts/05_build_custom_dictionary.py \
        --base-dictionary $MFA_ROOT/pretrained_models/dictionary/english_us_arpa.dict \
        --g2p-dictionary dictionaries/g2p_oov_only.dict \
        --out-dictionary dictionaries/english_us_arpa_plus_g2p.dict
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_dictionary(path: Path) -> tuple[dict[str, list[str]], list[str]]:
    """Parse an MFA dictionary.

    Two line shapes are accepted:

    * ``word<TAB>phone phone ...``                      (plain)
    * ``word<TAB>p1<TAB>p2<TAB>p3<TAB>p4<TAB>phones``   (with probabilities)

    Returns (word -> [pronunciation, ...], all_phones).
    """
    entries: dict[str, list[str]] = {}
    phones: set[str] = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < 2:
            print(f"  ! {path.name}:{line_no}: skipping malformed line", file=sys.stderr)
            continue
        word = fields[0].strip()
        pronunciation = fields[-1].strip()
        if not word or not pronunciation:
            continue
        entries.setdefault(word, []).append(pronunciation)
        phones.update(pronunciation.split())
    return entries, sorted(phones)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dictionary", type=Path, required=True)
    parser.add_argument(
        "--g2p-dictionary",
        type=Path,
        default=Path("dictionaries/g2p_oov_only.dict"),
    )
    parser.add_argument(
        "--out-dictionary",
        type=Path,
        default=Path("dictionaries/english_us_arpa_plus_g2p.dict"),
    )
    parser.add_argument("--report-json", type=Path, default=Path("dictionaries/custom_dictionary_report.json"))
    args = parser.parse_args()

    base, base_phones = load_dictionary(args.base_dictionary)
    base_phone_set = set(base_phones)
    print(f"base dictionary : {args.base_dictionary}")
    print(f"  word types    : {len(base)}")
    print(f"  phone types   : {len(base_phone_set)}")

    added: dict[str, list[str]] = {}
    rejected: list[str] = []
    if args.g2p_dictionary.is_file():
        g2p, _ = load_dictionary(args.g2p_dictionary)
        print(f"g2p dictionary  : {args.g2p_dictionary}")
        print(f"  word types    : {len(g2p)}")
        for word, pronunciations in sorted(g2p.items()):
            if word in base:
                # Never override a curated human dictionary entry.
                continue
            keep = []
            for pronunciation in pronunciations:
                unknown = [p for p in pronunciation.split() if p not in base_phone_set]
                if unknown:
                    rejected.append(f"{word}: {pronunciation} (phones not in model: {unknown})")
                else:
                    keep.append(pronunciation)
            if keep:
                added[word] = keep
    else:
        print(f"g2p dictionary  : {args.g2p_dictionary} (not found, base dictionary only)")

    print(f"\nwords added from G2P : {len(added)}")
    for word, pronunciations in sorted(added.items()):
        print(f"  {word:<14} {len(pronunciations)} pronunciation(s): {pronunciations[0]}")
    if rejected:
        print(f"rejected pronunciations: {len(rejected)}")
        for item in rejected:
            print(f"  - {item}")

    # Write the merged dictionary: base entries verbatim, then the new ones.
    out_lines: list[str] = []
    for word, pronunciations in sorted(base.items()):
        for pronunciation in pronunciations:
            out_lines.append(f"{word}\t{pronunciation}")
    added_lines = 0
    for word, pronunciations in sorted(added.items()):
        for pronunciation in pronunciations:
            out_lines.append(f"{word}\t{pronunciation}")
            added_lines += 1

    args.out_dictionary.parent.mkdir(parents=True, exist_ok=True)
    args.out_dictionary.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    print(f"\nwrote {args.out_dictionary}")
    print(f"  total lines      : {len(out_lines)} ({added_lines} from G2P)")

    report = {
        "base_dictionary": str(args.base_dictionary).replace("\\", "/"),
        "g2p_dictionary": str(args.g2p_dictionary).replace("\\", "/"),
        "out_dictionary": str(args.out_dictionary).replace("\\", "/"),
        "base_word_types": len(base),
        "base_phone_types": len(base_phone_set),
        "words_added": added,
        "pronunciations_added": added_lines,
        "total_lines": len(out_lines),
        "rejected": rejected,
    }
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"  report           : {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
