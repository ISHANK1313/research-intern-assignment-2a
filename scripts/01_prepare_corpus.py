#!/usr/bin/env python
"""Phase 2b: build the MFA corpus from the raw provided dataset.

MFA expects a *corpus directory* in which every ``<name>.wav`` is accompanied
by a ``<name>.lab`` transcript containing the words spoken in that file.  The
provided dataset is not in that shape:

* the audio is a mix of RIFF/WAVE and NIST SPHERE containers;
* the transcripts live in a separate directory and some use an upper-case
  ``.TXT`` extension;
* the transcript text carries sentence punctuation, which is not part of a
  pronunciation.

This script performs the conversion deterministically and is safe to re-run:
it wipes and rebuilds ``data/corpus`` every time, so the corpus always mirrors
``data/raw``.

Usage
-----
    python scripts/01_prepare_corpus.py \
        --wav-dir data/raw/wav \
        --transcript-dir data/raw/transcripts \
        --corpus-dir data/corpus
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfa_utils import (  # noqa: E402
    NistSphereError,
    copy_riff_wave,
    is_nist_sphere,
    is_riff_wave,
    nist_sphere_to_wav,
    normalize_text,
    transcript_to_words,
)

TRANSCRIPT_SUFFIXES = (".txt", ".lab", ".text")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav-dir", type=Path, default=Path("data/raw/wav"))
    parser.add_argument("--transcript-dir", type=Path, default=Path("data/raw/transcripts"))
    parser.add_argument("--corpus-dir", type=Path, default=Path("data/corpus"))
    parser.add_argument("--out-json", type=Path, default=Path("data/corpus_summary.json"))
    args = parser.parse_args()

    if not args.wav_dir.is_dir():
        print(f"ERROR: wav directory not found: {args.wav_dir}", file=sys.stderr)
        return 2
    if not args.transcript_dir.is_dir():
        print(f"ERROR: transcript directory not found: {args.transcript_dir}", file=sys.stderr)
        return 2

    if args.corpus_dir.exists():
        shutil.rmtree(args.corpus_dir)
    args.corpus_dir.mkdir(parents=True, exist_ok=True)

    transcripts = {
        path.stem.lower(): path
        for path in sorted(args.transcript_dir.iterdir())
        if path.is_file() and path.suffix.lower() in TRANSCRIPT_SUFFIXES
    }
    wavs = sorted(p for p in args.wav_dir.iterdir() if p.is_file() and p.suffix.lower() == ".wav")

    print("=" * 78)
    print("CORPUS PREPARATION")
    print("=" * 78)
    print(f"{'stem':<38}{'conversion':<16}{'words':>6}")
    print("-" * 78)

    records = []
    failures: list[str] = []
    for wav in wavs:
        stem = wav.stem
        dst_wav = args.corpus_dir / f"{stem}.wav"
        dst_lab = args.corpus_dir / f"{stem}.lab"

        try:
            if is_nist_sphere(wav):
                info = nist_sphere_to_wav(wav, dst_wav)
                conversion = "NIST->WAV"
            elif is_riff_wave(wav):
                info = copy_riff_wave(wav, dst_wav)
                conversion = "WAV copy"
            else:
                raise NistSphereError(f"{wav.name}: unrecognised audio container")
        except (NistSphereError, OSError) as exc:
            print(f"{stem:<38}{'FAILED':<16}  {exc}")
            failures.append(f"{wav.name}: {exc}")
            continue

        transcript = transcripts.get(stem.lower())
        raw_text = (
            transcript.read_text(encoding="utf-8", errors="replace") if transcript else ""
        )
        words = transcript_to_words(raw_text)
        dst_lab.write_text(normalize_text(raw_text) + "\n", encoding="utf-8")

        record = {
            "stem": stem,
            "source_wav": str(wav.relative_to(args.wav_dir.parent))
            if args.wav_dir.parent in wav.parents
            else wav.name,
            "source_transcript": transcript.name if transcript else None,
            "corpus_wav": dst_wav.name,
            "corpus_lab": dst_lab.name,
            "conversion": conversion,
            **info,
            "word_count": len(words),
            "words": words,
        }
        records.append(record)
        print(f"{stem:<38}{conversion:<16}{len(words):>6}")

    print()
    print("-" * 78)
    print(f"corpus wav files : {len(list(args.corpus_dir.glob('*.wav')))}")
    print(f"corpus .lab files: {len(list(args.corpus_dir.glob('*.lab')))}")
    print(f"failures         : {len(failures)}")
    for failure in failures:
        print(f"  - {failure}")

    # MFA matches transcript to audio by stem, so a stem that appears twice with
    # different cases would silently shadow one file.
    stems = [record["stem"] for record in records]
    duplicates = sorted({stem for stem in stems if stems.count(stem) > 1})
    if duplicates:
        print(f"duplicate stems  : {duplicates}")
        failures.append(f"duplicate stems: {duplicates}")

    summary = {
        "corpus_dir": str(args.corpus_dir).replace("\\", "/"),
        "wav_count": len(list(args.corpus_dir.glob("*.wav"))),
        "lab_count": len(list(args.corpus_dir.glob("*.lab"))),
        "conversions": {record["conversion"] for record in records},
        "total_words": sum(record["word_count"] for record in records),
        "failures": failures,
        "files": records,
    }
    # sets are not JSON serialisable
    summary["conversions"] = sorted(summary["conversions"])
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print()
    print(f"summary written to {args.out_json}")

    # Vocabulary used later by the OOV check / G2P extra credit.
    vocab = sorted({word for record in records for word in record["words"]})
    vocab_path = args.out_json.parent / "corpus_vocabulary.txt"
    vocab_path.write_text("\n".join(vocab) + "\n", encoding="utf-8")
    print(f"vocabulary ({len(vocab)} types) written to {vocab_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
