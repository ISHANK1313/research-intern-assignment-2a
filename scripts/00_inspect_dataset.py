#!/usr/bin/env python
"""Phase 2a: inspect the provided dataset before touching it.

Reports, without modifying anything:

* how many ``.wav`` files and how many transcripts exist
* whether the names pair up one-to-one
* the container format of each audio file (RIFF/WAVE vs NIST SPHERE)
* sample rate / channel count / duration
* transcripts that are missing, empty or suspiciously short

Usage
-----
    python scripts/00_inspect_dataset.py \
        --wav-dir data/raw/wav \
        --transcript-dir data/raw/transcripts \
        --out-json data/dataset_summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfa_utils import describe_audio, transcript_to_words  # noqa: E402

TRANSCRIPT_SUFFIXES = (".txt", ".lab", ".text")


def find_transcripts(directory: Path) -> dict[str, Path]:
    """Map lower-cased stem -> transcript path (case-insensitive match)."""
    found: dict[str, Path] = {}
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in TRANSCRIPT_SUFFIXES:
            found[path.stem.lower()] = path
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav-dir", type=Path, default=Path("data/raw/wav"))
    parser.add_argument("--transcript-dir", type=Path, default=Path("data/raw/transcripts"))
    parser.add_argument("--out-json", type=Path, default=Path("data/dataset_summary.json"))
    args = parser.parse_args()

    if not args.wav_dir.is_dir():
        print(f"ERROR: wav directory not found: {args.wav_dir}", file=sys.stderr)
        return 2
    if not args.transcript_dir.is_dir():
        print(f"ERROR: transcript directory not found: {args.transcript_dir}", file=sys.stderr)
        return 2

    wavs = sorted(p for p in args.wav_dir.iterdir() if p.is_file() and p.suffix.lower() == ".wav")
    transcripts = find_transcripts(args.transcript_dir)

    print("=" * 78)
    print("DATASET INSPECTION")
    print("=" * 78)
    print(f"wav directory        : {args.wav_dir}")
    print(f"transcript directory : {args.transcript_dir}")
    print(f"wav files            : {len(wavs)}")
    print(f"transcript files     : {len(transcripts)}")
    print()

    print("-" * 78)
    print("AUDIO FILES")
    print("-" * 78)
    header = f"{'file':<38}{'container':<14}{'rate':>7}{'ch':>4}{'sec':>8}{'words':>7}"
    print(header)
    print("-" * 78)

    entries = []
    for wav in wavs:
        info = describe_audio(wav)
        transcript = transcripts.get(wav.stem.lower())
        text = transcript.read_text(encoding="utf-8", errors="replace") if transcript else ""
        words = transcript_to_words(text)
        entries.append(
            {
                "wav": wav.name,
                "stem": wav.stem,
                "transcript": transcript.name if transcript else None,
                "transcript_present": transcript is not None,
                **info,
                "raw_chars": len(text.strip()),
                "word_count": len(words),
                "words": words,
            }
        )
        print(
            f"{wav.name:<38}{info['source_format']:<14}"
            f"{str(info['sample_rate']):>7}{str(info['channels']):>4}"
            f"{str(info['duration_sec']):>8}{len(words):>7}"
        )

    print()
    print("-" * 78)
    print("PAIRING / PROBLEM CHECKS")
    print("-" * 78)

    problems: list[str] = []
    wav_stems = {e["stem"].lower() for e in entries}
    transcript_stems = set(transcripts)

    missing = sorted(wav_stems - transcript_stems)
    orphan = sorted(transcript_stems - wav_stems)
    if missing:
        problems.append(f"wav without transcript: {missing}")
    if orphan:
        problems.append(f"transcript without wav: {orphan}")
    print(f"1:1 name match            : {'yes' if not missing and not orphan else 'NO'}")
    if missing:
        print(f"  wav without transcript  : {missing}")
    if orphan:
        print(f"  transcript without wav  : {orphan}")

    formats = sorted({e["source_format"] for e in entries})
    print(f"container formats         : {formats}")

    rates = sorted({e["sample_rate"] for e in entries})
    print(f"sample rates (Hz)         : {rates}")
    channels = sorted({e["channels"] for e in entries})
    print(f"channel counts            : {channels}")
    widths = sorted({e["sample_bytes"] for e in entries})
    print(f"bytes per sample          : {widths}")

    empty = [e["wav"] for e in entries if not e["words"]]
    if empty:
        problems.append(f"empty transcript: {empty}")
    print(f"empty transcripts         : {len(empty)} {empty if empty else ''}")

    tiny = [e["wav"] for e in entries if e["words"] and e["word_count"] < 3]
    print(f"transcripts < 3 words     : {len(tiny)} {tiny if tiny else ''}")

    bad_audio = [e["wav"] for e in entries if e["source_format"] == "UNKNOWN"]
    if bad_audio:
        problems.append(f"unreadable audio: {bad_audio}")
    print(f"unreadable audio          : {len(bad_audio)} {bad_audio if bad_audio else ''}")

    # Case differences between wav and transcript extensions are worth flagging:
    # MFA matches on the stem, and on a case-sensitive filesystem ".TXT" is not
    # picked up as a ".txt" transcript.
    odd_case = [
        f"{e['wav']} -> {e['transcript']}"
        for e in entries
        if e["transcript"] and Path(e["transcript"]).suffix != ".txt"
    ]
    print(f"non-lowercase transcript  : {len(odd_case)} {odd_case if odd_case else ''}")

    total_words = sum(e["word_count"] for e in entries)
    total_dur = sum(e["duration_sec"] or 0 for e in entries)
    print()
    print(f"total audio duration      : {round(total_dur, 2)} s")
    print(f"total words (normalised)  : {total_words}")
    print(f"problems found            : {len(problems)}")
    for problem in problems:
        print(f"  - {problem}")

    summary = {
        "wav_count": len(wavs),
        "transcript_count": len(transcripts),
        "one_to_one_match": not missing and not orphan,
        "container_formats": formats,
        "sample_rates": rates,
        "channel_counts": channels,
        "bytes_per_sample": widths,
        "empty_transcripts": empty,
        "short_transcripts": tiny,
        "unreadable_audio": bad_audio,
        "non_lowercase_transcripts": odd_case,
        "total_words": total_words,
        "total_duration_sec": round(total_dur, 2),
        "problems": problems,
        "files": entries,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print()
    print(f"summary written to {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
