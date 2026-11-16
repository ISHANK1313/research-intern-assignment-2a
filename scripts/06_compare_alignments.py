#!/usr/bin/env python
"""Phase 5 (extra credit): compare two alignment runs boundary by boundary.

Both runs are given the same corpus and the same word sequence, so the word
tiers can be compared position by position.  When the two runs disagree about
the phone sequence -- which is exactly what happens where the base dictionary
had an OOV word and produced a single ``spn`` span, while the custom dictionary
produced real phones -- the phone tiers are compared only for the files where
the phone counts differ, and the disagreement is described rather than diffed.

Usage
-----
    python scripts/06_compare_alignments.py \
        --reference-dir outputs \
        --test-dir outputs_custom_dict \
        --out-json Report/alignment_comparison.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

try:  # praatio >= 6
    from praatio import textgrid as praatio_textgrid
except ImportError:  # pragma: no cover
    from praatio import tgio as praatio_textgrid  # type: ignore


def open_textgrid(path: Path):
    return praatio_textgrid.openTextgrid(str(path), includeEmptyIntervals=True)


def entries(tg, tier_name: str) -> list[tuple[float, float, str]]:
    names = {n.lower(): n for n in tg.tierNames}
    if tier_name.lower() not in names:
        return []
    return [
        (float(s), float(e), (label or "").strip())
        for s, e, label in tg.getTier(names[tier_name.lower()]).entries
    ]


def compare_words(ref: list, test: list) -> dict:
    """Compare word boundaries; the label sequence is identical by construction."""
    ref_words = [w for w in ref if w[2]]
    test_words = [w for w in test if w[2]]
    result: dict = {
        "word_count_ref": len(ref_words),
        "word_count_test": len(test_words),
        "labels_identical": [w[2] for w in ref_words] == [w[2] for w in test_words],
    }
    if not result["labels_identical"] or not ref_words:
        return result

    start_deltas, end_deltas = [], []
    worst = {"shift": 0.0, "label": "", "ref_start": 0.0, "test_start": 0.0}
    for (rs, re_, rl), (ts, te, _) in zip(ref_words, test_words):
        ds, de = ts - rs, te - re_
        start_deltas.append(ds)
        end_deltas.append(de)
        if abs(ds) > abs(worst["shift"]):
            worst = {
                "shift": round(ds, 4),
                "label": rl,
                "ref_start": round(rs, 3),
                "test_start": round(ts, 3),
            }

    result.update(
        {
            "start_shift_mean_abs": round(statistics.fmean(abs(d) for d in start_deltas), 4),
            "start_shift_median_abs": round(statistics.median(abs(d) for d in start_deltas), 4),
            "start_shift_max_abs": round(max(abs(d) for d in start_deltas), 4),
            "end_shift_max_abs": round(max(abs(d) for d in end_deltas), 4),
            "words_shifted_gt_10ms": sum(1 for d in start_deltas if abs(d) > 0.010),
            "words_shifted_gt_100ms": sum(1 for d in start_deltas if abs(d) > 0.100),
            "largest_start_shift": worst,
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--test-dir", type=Path, default=Path("outputs_custom_dict"))
    parser.add_argument(
        "--out-json", type=Path, default=Path("Report/alignment_comparison.json")
    )
    args = parser.parse_args()

    grids = sorted(
        p
        for p in args.reference_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".textgrid"
    )
    if not grids:
        print(f"ERROR: no TextGrids in {args.reference_dir}", file=sys.stderr)
        return 2

    report = {
        "reference_dir": str(args.reference_dir).replace("\\", "/"),
        "test_dir": str(args.test_dir).replace("\\", "/"),
        "files": [],
    }

    print(f"{'stem':<38}{'words':>6}{'phoneΔ':>8}{'mean|Δ|':>10}{'max|Δ|':>9}{'>10ms':>7}")
    print("-" * 78)

    for ref_path in grids:
        test_path = args.test_dir / ref_path.name
        if not test_path.is_file():
            print(f"{ref_path.stem:<38}  MISSING in test dir")
            continue

        ref_tg, test_tg = open_textgrid(ref_path), open_textgrid(test_path)
        ref_words, test_words = entries(ref_tg, "words"), entries(test_tg, "words")
        ref_phones, test_phones = entries(ref_tg, "phones"), entries(test_tg, "phones")

        word_cmp = compare_words(ref_words, test_words)
        ref_spn = [p for p in ref_phones if p[2] == "spn"]
        test_spn = [p for p in test_phones if p[2] == "spn"]

        entry = {
            "stem": ref_path.stem,
            "words": word_cmp,
            "phones_ref": len([p for p in ref_phones if p[2]]),
            "phones_test": len([p for p in test_phones if p[2]]),
            "spn_ref": len(ref_spn),
            "spn_test": len(test_spn),
            "spn_regions_ref": [
                {
                    "start": round(s, 3),
                    "end": round(e, 3),
                    "words": [
                        w[2] for w in ref_words if w[2] and w[0] < e and w[1] > s
                    ],
                    "phones_in_test_run": [
                        {"start": round(ps, 3), "end": round(pe, 3), "label": pl}
                        for ps, pe, pl in test_phones
                        if ps < e and pe > s
                    ],
                }
                for s, e, _ in ref_spn
            ],
        }
        report["files"].append(entry)

        delta = entry["phones_test"] - entry["phones_ref"]
        print(
            f"{ref_path.stem:<38}"
            f"{word_cmp.get('word_count_ref', 0):>6}"
            f"{delta:>+8}"
            f"{word_cmp.get('start_shift_mean_abs', float('nan')):>10}"
            f"{word_cmp.get('start_shift_max_abs', float('nan')):>9}"
            f"{word_cmp.get('words_shifted_gt_10ms', 0):>7}"
        )

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {args.out_json}")

    print("\nspn regions in the reference run and the phones the custom run used:")
    for entry in report["files"]:
        for region in entry["spn_regions_ref"]:
            words = ", ".join(region["words"])
            phones = " ".join(p["label"] for p in region["phones_in_test_run"])
            print(
                f"  {entry['stem']}  {region['start']}-{region['end']}s  "
                f"[{words}] -> {phones}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
