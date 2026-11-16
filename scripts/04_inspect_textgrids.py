#!/usr/bin/env python
"""Phase 4: inspect aligned TextGrids and plot the boundaries.

For each requested file this script

1. reads the TextGrid MFA produced (``words`` and ``phones`` tiers),
2. plots the waveform with every word boundary and every phone boundary
   marked (full file plus a zoom on the busiest region),
3. writes machine-readable per-file statistics that the report quotes:
   tier sizes, zero-length intervals, silence handling, the longest phone,
   ``spn`` (MFA's "unknown/OOV phone") occurrences and the largest timing
   gap between two consecutive words.

Nothing here is hard-coded: every number printed comes from the TextGrids
actually on disk.

Usage
-----
    python scripts/04_inspect_textgrids.py \
        --textgrid-dir outputs \
        --corpus-dir data/corpus \
        --out-dir Report/figures \
        --stats-json Report/alignment_stats.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

try:  # praatio >= 6
    from praatio import textgrid as praatio_textgrid
except ImportError:  # pragma: no cover - older praatio
    from praatio import tgio as praatio_textgrid  # type: ignore


def open_textgrid(path: Path):
    """Open a TextGrid with whichever praatio API is available."""
    try:
        return praatio_textgrid.openTextgrid(str(path), includeEmptyIntervals=True)
    except AttributeError:  # praatio < 6
        return praatio_textgrid.openTextgrid(str(path), includeEmptyIntervals=True)


def tier_entries(tg, name: str) -> list[tuple[float, float, str]]:
    """Return the (start, end, label) entries of a tier, or [] if absent."""
    names = {n.lower(): n for n in tg.tierNames}
    if name.lower() not in names:
        return []
    tier = tg.getTier(names[name.lower()])
    return [(float(s), float(e), (label or "").strip()) for s, e, label in tier.entries]


def summarize(stem: str, words: list, phones: list, audio_dur: float) -> dict:
    """Derive the quantitative observations quoted in the report."""
    non_empty_words = [w for w in words if w[2]]
    non_empty_phones = [p for p in phones if p[2]]
    zero_len_phones = [
        p for p in non_empty_phones if round(p[1] - p[0], 6) == 0
    ]
    spn = [p for p in non_empty_phones if p[2] in {"spn", "sp", "<unk>"}]

    # Non-speech handling.  MFA does not emit "sil" phones here: silence shows
    # up as *unlabelled* intervals, in both tiers.  So count both the explicit
    # silence labels and the empty ones, over the whole tier.
    explicit_sil = [p for p in phones if p[2] in {"sil", "sp", "silence"}]
    unlabelled = [p for p in phones if not p[2]]
    nonspeech = sorted(explicit_sil + unlabelled)
    # Leading/trailing non-speech is what a downstream consumer cares about most.
    leading = 0.0
    for start, end, label in phones:
        if label:
            break
        leading = end
    trailing = 0.0
    for start, end, label in reversed(phones):
        if label:
            # measured from the END of the last labelled phone, not its start
            trailing = audio_dur - end
            break

    # Longest phone, and the largest gap between two consecutive words (this is
    # where a pause or an alignment failure shows up).
    longest = max(
        non_empty_phones, key=lambda p: p[1] - p[0], default=(0.0, 0.0, "")
    )
    gaps = []
    for prev, cur in zip(non_empty_words, non_empty_words[1:]):
        gaps.append((round(cur[0] - prev[1], 4), prev[2], cur[2], round(prev[1], 3)))
    largest_gap = max(gaps, default=(0.0, "", "", 0.0))

    return {
        "stem": stem,
        "audio_duration_sec": round(audio_dur, 3),
        "word_intervals": len(words),
        "word_intervals_non_empty": len(non_empty_words),
        "phone_intervals": len(phones),
        "phone_intervals_non_empty": len(non_empty_phones),
        "zero_length_phones": [f"{p[2]}@{round(p[0], 3)}" for p in zero_len_phones],
        "zero_length_phone_count": len(zero_len_phones),
        "spn_count": len(spn),
        "spn_phones": [f"{round(p[0], 3)}-{round(p[1], 3)}" for p in spn],
        "spn_words": sorted(
            {
                w[2]
                for p in spn
                for w in non_empty_words
                if w[0] < p[1] and w[1] > p[0]
            }
        ),
        "explicit_sil_labels": len(explicit_sil),
        "unlabelled_intervals": len(unlabelled),
        "nonspeech_intervals": [
            f"{round(p[0], 3)}-{round(p[1], 3)}" for p in nonspeech
        ],
        "nonspeech_total_sec": round(sum(p[1] - p[0] for p in nonspeech), 3),
        "leading_nonspeech_sec": round(leading, 3),
        "trailing_nonspeech_sec": round(trailing, 3),
        "longest_phone": {
            "label": longest[2],
            "start": round(longest[0], 3),
            "end": round(longest[1], 3),
            "duration": round(longest[1] - longest[0], 3),
        },
        "largest_word_gap": {
            "gap_sec": largest_gap[0],
            "after_word": largest_gap[1],
            "before_word": largest_gap[2],
            "at_time": largest_gap[3],
        },
        "first_word": non_empty_words[0][2] if non_empty_words else None,
        "first_word_start": round(non_empty_words[0][0], 3) if non_empty_words else None,
        "last_word": non_empty_words[-1][2] if non_empty_words else None,
        "last_word_end": round(non_empty_words[-1][1], 3) if non_empty_words else None,
        "words": [{"start": round(s, 3), "end": round(e, 3), "label": lb} for s, e, lb in words],
        "phones": [{"start": round(s, 3), "end": round(e, 3), "label": lb} for s, e, lb in phones],
    }


def pick_zoom(
    words: list, phones: list, audio_dur: float, span: float
) -> tuple[float, float]:
    """Choose the zoom window.

    For a short clip the whole file is already roughly *span* long, so zooming
    on a sub-region would show the same thing twice; in that case zoom on the
    actual speech (first to last word) instead.  For a long clip, centre the
    window on the densest run of phones -- that is where the boundaries are
    hardest to see at full scale.
    """
    non_empty_words = [w for w in words if w[2]]
    if audio_dur <= span * 1.5 and non_empty_words:
        start = max(0.0, non_empty_words[0][0] - 0.1)
        end = min(audio_dur, non_empty_words[-1][1] + 0.1)
        return start, end

    non_empty = [p for p in phones if p[2]]
    if not non_empty:
        return 0.0, min(span, audio_dur)
    best_start, best_count = non_empty[0][0], -1
    for start, _, _ in non_empty:
        count = sum(1 for s, _, _ in non_empty if start <= s < start + span)
        if count > best_count:
            best_count, best_start = count, start
    zoom_start = max(0.0, best_start - span * 0.1)
    zoom_end = min(audio_dur, zoom_start + span)
    return zoom_start, zoom_end


def plot_file(
    stem: str,
    wav_path: Path,
    words: list,
    phones: list,
    out_path: Path,
    zoom_span: float = 4.0,
    zoom_override: tuple[float, float] | None = None,
) -> None:
    """Plot waveform + word tier + phone tier (full file and a zoom)."""
    samples, rate = sf.read(str(wav_path), dtype="float32", always_2d=False)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    times = np.arange(len(samples)) / rate
    audio_dur = len(samples) / rate

    zoom_start, zoom_end = (
        zoom_override
        if zoom_override is not None
        else pick_zoom(words, phones, audio_dur, zoom_span)
    )

    fig, axes = plt.subplots(
        4, 1, figsize=(16, 11), constrained_layout=True
    )

    # --- panel 1: full waveform with word boundaries -----------------------
    ax = axes[0]
    ax.plot(times, samples, linewidth=0.4, color="#333333")
    for start, _, label in words:
        if label:
            ax.axvline(start, color="#1f77b4", linewidth=0.7, alpha=0.8)
    ax.set_title(
        f"{stem} — full file ({audio_dur:.2f} s): green = word boundaries "
        f"({len([w for w in words if w[2]])} words)",
        fontsize=11,
    )
    ax.set_xlim(0, audio_dur)
    ax.set_ylabel("amp")

    # --- panel 2: full waveform with phone boundaries ----------------------
    ax = axes[1]
    ax.plot(times, samples, linewidth=0.4, color="#333333")
    for start, _, label in phones:
        if label:
            ax.axvline(start, color="#d62728", linewidth=0.4, alpha=0.55)
    ax.set_title(
        f"phone boundaries ({len([p for p in phones if p[2]])} phones, red)",
        fontsize=11,
    )
    ax.set_xlim(0, audio_dur)
    ax.set_ylabel("amp")

    # --- panel 3: zoomed waveform with word labels -------------------------
    ax = axes[2]
    mask = (times >= zoom_start) & (times <= zoom_end)
    ax.plot(times[mask], samples[mask], linewidth=0.7, color="#333333")
    visible_words = [
        (s, e, lb) for s, e, lb in words if lb and e > zoom_start and s < zoom_end
    ]
    for start, end, label in visible_words:
        ax.axvline(start, color="#1f77b4", linewidth=1.0)
        ax.hlines(
            np.max(samples[mask]) * 0.92 if mask.any() else 0.9,
            max(start, zoom_start),
            min(end, zoom_end),
            color="#1f77b4",
            linewidth=3,
            alpha=0.35,
        )
        ax.text(
            max(start, zoom_start) + (zoom_end - zoom_start) * 0.004,
            0.95,
            label,
            rotation=0,
            fontsize=9,
            ha="left",
            va="top",
            color="#1f77b4",
            transform=ax.get_xaxis_transform(),
        )
    ax.set_title(f"zoom {zoom_start:.2f}–{zoom_end:.2f} s — word tier", fontsize=11)
    ax.set_xlim(zoom_start, zoom_end)
    ax.set_ylim(-1.05, 1.05)
    ax.set_ylabel("amp")

    # --- panel 4: zoomed waveform with phone labels ------------------------
    ax = axes[3]
    ax.plot(times[mask], samples[mask], linewidth=0.7, color="#333333")
    for start, end, label in phones:
        if not label or end <= zoom_start or start >= zoom_end:
            continue
        ax.axvline(start, color="#d62728", linewidth=1.0)
        ax.text(
            (max(start, zoom_start) + min(end, zoom_end)) / 2,
            1.0,
            label,
            fontsize=8,
            ha="center",
            va="top",
            color="#d62728",
            transform=ax.get_xaxis_transform(),
        )
    ax.set_title(f"zoom {zoom_start:.2f}–{zoom_end:.2f} s — phone tier", fontsize=11)
    ax.set_xlim(zoom_start, zoom_end)
    ax.set_ylim(-1.05, 1.05)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("amp")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    print(f"  wrote {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--textgrid-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--corpus-dir", type=Path, default=Path("data/corpus"))
    parser.add_argument("--out-dir", type=Path, default=Path("Report/figures"))
    parser.add_argument("--stats-json", type=Path, default=Path("Report/alignment_stats.json"))
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="stems to inspect; default = every TextGrid found",
    )
    parser.add_argument("--zoom-span", type=float, default=4.0)
    parser.add_argument(
        "--zoom-start",
        type=float,
        default=None,
        help="force the zoom window start (seconds); use with --zoom-end",
    )
    parser.add_argument("--zoom-end", type=float, default=None)
    parser.add_argument(
        "--suffix",
        default="_alignment",
        help="filename suffix for the figures, e.g. _alignment or _oov_zoom",
    )
    args = parser.parse_args()

    zoom_override = None
    if args.zoom_start is not None and args.zoom_end is not None:
        zoom_override = (args.zoom_start, args.zoom_end)

    # Case-insensitive scan: on Windows glob('*.TextGrid') and glob('*.textgrid')
    # both match every file, which would list each TextGrid twice.
    grids = sorted(
        p
        for p in args.textgrid_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".textgrid"}
    )
    if not grids:
        print(f"ERROR: no TextGrids in {args.textgrid_dir}", file=sys.stderr)
        return 2

    if args.files:
        wanted = {f.lower() for f in args.files}
        grids = [g for g in grids if g.stem.lower() in wanted]

    stats = []
    for grid in grids:
        stem = grid.stem
        wav = args.corpus_dir / f"{stem}.wav"
        if not wav.is_file():
            print(f"  ! {stem}: no matching wav in {args.corpus_dir}, skipping")
            continue

        tg = open_textgrid(grid)
        words = tier_entries(tg, "words")
        phones = tier_entries(tg, "phones")
        audio_dur = sf.info(str(wav)).duration

        info = summarize(stem, words, phones, audio_dur)
        stats.append(info)

        print(f"{stem}")
        print(
            f"  duration {info['audio_duration_sec']} s | "
            f"words {info['word_intervals_non_empty']} | "
            f"phones {info['phone_intervals_non_empty']} | "
            f"spn {info['spn_count']} | "
            f"zero-length phones {info['zero_length_phone_count']} | "
            f"non-speech {info['nonspeech_total_sec']} s "
            f"(lead {info['leading_nonspeech_sec']} / trail {info['trailing_nonspeech_sec']})"
        )
        if info["spn_words"]:
            print(f"  spn covers OOV word(s): {info['spn_words']}")
        print(
            f"  first word '{info['first_word']}' @ {info['first_word_start']} s, "
            f"last word '{info['last_word']}' ends @ {info['last_word_end']} s"
        )
        print(
            f"  longest phone {info['longest_phone']['label']} "
            f"{info['longest_phone']['duration']} s @ {info['longest_phone']['start']} s"
        )
        print(
            f"  largest word gap {info['largest_word_gap']['gap_sec']} s at "
            f"{info['largest_word_gap']['at_time']} s "
            f"('{info['largest_word_gap']['after_word']}' -> "
            f"'{info['largest_word_gap']['before_word']}')"
        )
        if info["spn_phones"]:
            print(f"  spn at {info['spn_phones']}")

        plot_file(
            stem,
            wav,
            words,
            phones,
            args.out_dir / f"{stem}{args.suffix}.png",
            zoom_span=args.zoom_span,
            zoom_override=zoom_override,
        )

    if args.stats_json:
        args.stats_json.parent.mkdir(parents=True, exist_ok=True)
        args.stats_json.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.stats_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
