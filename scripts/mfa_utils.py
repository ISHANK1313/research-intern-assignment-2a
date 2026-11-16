"""Shared helpers for the MFA forced-alignment pipeline.

Two concerns live here:

1.  Audio containers.  The provided dataset is not homogeneous: some files are
    plain RIFF/WAVE, others are NIST SPHERE (the "NIST_1A" container used by
    the BU Radio Corpus).  MFA only reads real RIFF/WAVE, so everything is
    normalised to 16 kHz mono 16-bit PCM RIFF/WAVE.

2.  Transcript text.  MFA aligns words that exist in the pronunciation
    dictionary, so punctuation has to go and whitespace has to be collapsed
    before the text can be treated as a word sequence.

Both are implemented with the standard library only, so the pipeline does not
depend on sox / ffmpeg being installed.
"""

from __future__ import annotations

import re
import struct
import wave
from pathlib import Path

NIST_MAGIC = b"NIST_1A"

# Characters kept in a transcript after normalisation: letters, digits, the
# intra-word apostrophe and the intra-word hyphen.  Everything else (sentence
# punctuation, commas, quotes, ...) is dropped by replacing it with a space.
_PUNCTUATION_RE = re.compile(r"[^a-z0-9'\-\s]")
_WHITESPACE_RE = re.compile(r"\s+")

# Clitics that the english_us_arpa dictionary carries as their own entries
# ("'s" has three pronunciations: Z, AH0 Z and S).  Keeping the leading
# apostrophe matters: "S.J.C.'s" spoken as "S J C's" must tokenise to
# "s j c 's", not "s j c s" -- both "s" and "'s" exist in the dictionary but
# they are pronounced differently.
_CLITICS = {"s", "ll", "re", "ve", "d", "m", "t"}


class NistSphereError(RuntimeError):
    """Raised when a file claims to be NIST SPHERE but cannot be parsed."""


def is_nist_sphere(path: Path) -> bool:
    """Return True if *path* starts with the NIST SPHERE magic string."""
    with open(path, "rb") as handle:
        return handle.read(len(NIST_MAGIC)) == NIST_MAGIC


def is_riff_wave(path: Path) -> bool:
    """Return True if *path* starts with a RIFF/WAVE header."""
    with open(path, "rb") as handle:
        head = handle.read(12)
    return head[:4] == b"RIFF" and head[8:12] == b"WAVE"


def read_nist_sphere_header(path: Path) -> dict:
    """Parse the ASCII header of a NIST SPHERE file.

    The container starts with ``NIST_1A\\n<header_size>\\n`` followed by
    newline-separated ``key -type value`` lines and terminated by ``end_head``.
    Values are returned as strings; the numeric ones are converted by
    :func:`nist_sphere_to_wav`.
    """
    with open(path, "rb") as handle:
        magic = handle.readline()
        if magic.strip() != NIST_MAGIC:
            raise NistSphereError(f"{path.name}: not a NIST SPHERE file")
        size_line = handle.readline()
        try:
            header_size = int(size_line.strip())
        except ValueError as exc:
            raise NistSphereError(f"{path.name}: bad header size {size_line!r}") from exc
        raw = handle.read(header_size - len(magic) - len(size_line))

    header: dict[str, str] = {}
    for line in raw.decode("latin-1").splitlines():
        line = line.strip()
        if not line or line.startswith("end_head"):
            break
        parts = line.split(" ", 2)
        if len(parts) < 2:
            continue
        key, spec = parts[0], parts[1]
        value = parts[2] if len(parts) > 2 else ""
        # The spec looks like "-i" (integer) or "-s3" (3-char string); the
        # value itself is everything after it.
        if spec.startswith("-s"):
            width = int(spec[2:]) if len(spec) > 2 else 0
            value = value[:width] if width else value
        header[key] = value.strip()
    return header


def nist_sphere_to_wav(src: Path, dst: Path) -> dict:
    """Convert a NIST SPHERE file to 16-bit PCM RIFF/WAVE.

    Returns a dict with the parsed header fields that matter for reporting
    (sample rate, channel count, byte order, sample count).
    """
    header = read_nist_sphere_header(src)
    try:
        sample_rate = int(header["sample_rate"])
        channels = int(header.get("channel_count", 1))
        sample_bytes = int(header.get("sample_n_bytes", 2))
    except (KeyError, ValueError) as exc:
        raise NistSphereError(f"{src.name}: missing/invalid header field: {exc}") from exc

    if header.get("sample_coding", "pcm") != "pcm":
        raise NistSphereError(
            f"{src.name}: unsupported sample_coding {header.get('sample_coding')!r}"
        )
    if sample_bytes != 2:
        raise NistSphereError(f"{src.name}: unsupported sample_n_bytes={sample_bytes}")

    # NIST byte format: "01" = little-endian, "10" = big-endian.
    byte_format = header.get("sample_byte_format", "01")
    endian = "<" if byte_format == "01" else ">"

    # The audio payload begins exactly header_size bytes into the file.
    with open(src, "rb") as handle:
        handle.readline()  # NIST_1A
        header_size = int(handle.readline().strip())
        handle.seek(header_size)
        payload = handle.read()

    expected = int(header.get("sample_count", 0)) * channels * sample_bytes
    if expected and len(payload) < expected:
        raise NistSphereError(
            f"{src.name}: truncated audio ({len(payload)} < {expected} bytes)"
        )
    payload = payload[:expected] if expected else payload

    samples = struct.unpack(f"{endian}{len(payload) // 2}h", payload[: len(payload) // 2 * 2])

    dst.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dst), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(sample_bytes)
        out.setframerate(sample_rate)
        out.writeframes(struct.pack(f"<{len(samples)}h", *samples))

    return {
        "source_format": "NIST_SPHERE",
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_bytes": sample_bytes,
        "sample_byte_format": byte_format,
        "sample_count": len(samples) // channels if samples else 0,
        "corpus_id": header.get("corpus_id", ""),
        "speaker_id": header.get("speaker_id", ""),
    }


def copy_riff_wave(src: Path, dst: Path) -> dict:
    """Copy a RIFF/WAVE file, reporting its parameters."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(src), "rb") as inp:
        params = inp.getparams()
        frames = inp.readframes(params.nframes)
    with wave.open(str(dst), "wb") as out:
        out.setnchannels(params.nchannels)
        out.setsampwidth(params.sampwidth)
        out.setframerate(params.framerate)
        out.writeframes(frames)
    return {
        "source_format": "RIFF_WAVE",
        "sample_rate": params.framerate,
        "channels": params.nchannels,
        "sample_bytes": params.sampwidth,
        "sample_byte_format": "01",
        "sample_count": params.nframes,
        "corpus_id": "",
        "speaker_id": "",
    }


def describe_audio(path: Path) -> dict:
    """Return container/parameter info for a wav-like file without converting it."""
    if is_nist_sphere(path):
        header = read_nist_sphere_header(path)
        sample_rate = int(header.get("sample_rate", 0) or 0)
        channels = int(header.get("channel_count", 1) or 1)
        count = int(header.get("sample_count", 0) or 0)
        return {
            "source_format": "NIST_SPHERE",
            "sample_rate": sample_rate,
            "channels": channels,
            "sample_bytes": int(header.get("sample_n_bytes", 2) or 2),
            "sample_count": count,
            "duration_sec": round(count / sample_rate, 3) if sample_rate else None,
            "corpus_id": header.get("corpus_id", ""),
            "speaker_id": header.get("speaker_id", ""),
        }
    if is_riff_wave(path):
        with wave.open(str(path), "rb") as handle:
            params = handle.getparams()
        return {
            "source_format": "RIFF_WAVE",
            "sample_rate": params.framerate,
            "channels": params.nchannels,
            "sample_bytes": params.sampwidth,
            "sample_count": params.nframes,
            "duration_sec": round(params.nframes / params.framerate, 3) if params.framerate else None,
            "corpus_id": "",
            "speaker_id": "",
        }
    return {
        "source_format": "UNKNOWN",
        "sample_rate": None,
        "channels": None,
        "sample_bytes": None,
        "sample_count": None,
        "duration_sec": None,
        "corpus_id": "",
        "speaker_id": "",
    }


def normalize_text(text: str) -> str:
    """Normalise transcript text into a whitespace-separated word sequence.

    * lower-cased (MFA's ``english_us_arpa`` dictionary is lower-case)
    * sentence punctuation removed
    * apostrophes and hyphens kept, since the dictionary contains both
      (``'s`` clitics, compounds such as ``seventy-six``)
    * whitespace collapsed

    Hyphens followed by a space (``"thirty- five"`` -> ``"thirty five"``) are
    turned into separate tokens by the whitespace collapse; the hyphen is
    dropped in that case because it no longer sits between two letters.
    """
    if text is None:
        return ""
    cleaned = text.lower().replace("\u2019", "'")
    cleaned = _PUNCTUATION_RE.sub(" ", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    # A hyphen that is not between two letters (isolated, leading, trailing)
    # carries no phonetic content: drop it.
    words = []
    for token in cleaned.split(" "):
        # Preserve a standalone clitic ("'s", "'ll", ...) -- it is a real
        # dictionary entry and carries its own pronunciation.
        if token.startswith("'") and token[1:] in _CLITICS:
            words.append(token)
            continue
        token = token.strip("-'")
        if not token:
            continue
        token = re.sub(r"-{2,}", "-", token)
        words.append(token)
    return " ".join(words)


def write_lab(path: Path, text: str) -> None:
    """Write a MFA ``.lab`` file (single line, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalize_text(text) + "\n", encoding="utf-8")


def transcript_to_words(text: str) -> list[str]:
    """Normalise *text* and split it into word tokens."""
    normalized = normalize_text(text)
    return normalized.split(" ") if normalized else []
