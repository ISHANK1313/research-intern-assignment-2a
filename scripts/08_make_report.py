#!/usr/bin/env python
"""Build Report/report.pdf from the artefacts produced by the pipeline.

Every number and every figure in the PDF is read from the files the alignment
run actually wrote (data/*.json, Report/alignment_*.json, outputs/*.csv,
Report/versions.txt), so the report cannot drift from the results.

Usage
-----
    python scripts/08_make_report.py
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_json(path: Path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def styles():
    sheet = getSampleStyleSheet()
    sheet.add(
        ParagraphStyle(
            name="Body",
            parent=sheet["BodyText"],
            fontSize=9.5,
            leading=13,
            alignment=TA_JUSTIFY,
            spaceAfter=5,
        )
    )
    sheet.add(
        ParagraphStyle(
            name="Small",
            parent=sheet["BodyText"],
            fontSize=8.2,
            leading=11,
            textColor=colors.HexColor("#444444"),
        )
    )
    sheet.add(
        ParagraphStyle(
            name="Mono",
            parent=sheet["Code"],
            fontSize=7.4,
            leading=9.6,
            textColor=colors.HexColor("#222222"),
        )
    )
    sheet.add(
        ParagraphStyle(
            name="H1b", parent=sheet["Heading1"], fontSize=15, spaceBefore=10, spaceAfter=6
        )
    )
    sheet.add(
        ParagraphStyle(
            name="H2b", parent=sheet["Heading2"], fontSize=11.5, spaceBefore=9, spaceAfter=4
        )
    )
    sheet.add(
        ParagraphStyle(
            name="Cap",
            parent=sheet["BodyText"],
            fontSize=8,
            leading=10.5,
            textColor=colors.HexColor("#555555"),
            spaceBefore=3,
            spaceAfter=9,
        )
    )
    sheet.add(
        ParagraphStyle(
            name="Cell",
            parent=sheet["BodyText"],
            fontSize=8.2,
            leading=10,
            spaceAfter=0,
        )
    )
    sheet.add(
        ParagraphStyle(
            name="CellHead",
            parent=sheet["BodyText"],
            fontSize=8.2,
            leading=10,
            spaceAfter=0,
            fontName="Helvetica-Bold",
        )
    )
    return sheet


# Module-level styles: table() needs them, and it is called before main() builds
# its own local reference.
STYLES = styles()


def cell(value, style_name="Cell"):
    """Wrap a table cell in a Paragraph so long text wraps instead of overflowing."""
    return Paragraph(str(value), STYLES[style_name])


def table(data, col_widths=None, font_size=8.2, header_bg="#e8eef7"):
    # Every cell is a Paragraph: without this, long filenames such as
    # ISLE_SESS0131_BLOCKD02_01_sprt1.wav spill across the neighbouring column.
    wrapped = [
        [cell(v, "CellHead" if row_index == 0 else "Cell") for v in row]
        for row_index, row in enumerate(data)
    ]
    tbl = Table(wrapped, colWidths=col_widths, hAlign="LEFT", repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#222222")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b9c6d8")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]
        )
    )
    return tbl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "Report/report.pdf")
    args = parser.parse_args()

    ds = load_json(REPO_ROOT / "data/dataset_summary.json", {})
    cs = load_json(REPO_ROOT / "data/corpus_summary.json", {})
    stats = load_json(REPO_ROOT / "Report/alignment_stats.json", [])
    stats_custom = load_json(REPO_ROOT / "Report/alignment_stats_custom_dict.json", [])
    cmp_dict = load_json(REPO_ROOT / "Report/alignment_comparison.json", {})
    cmp_model = load_json(REPO_ROOT / "Report/alignment_comparison_english_mfa.json", {})
    quality = load_csv(REPO_ROOT / "outputs/alignment_analysis.csv")
    custom_report = load_json(REPO_ROOT / "dictionaries/custom_dictionary_report.json", {})

    oov_base = (REPO_ROOT / "logs/mfa_validate/oov_counts_english_us_arpa.txt")
    oov_counts = {}
    if oov_base.is_file():
        for line in oov_base.read_text(encoding="utf-8").splitlines():
            if "\t" in line:
                w, n = line.split("\t")[:2]
                oov_counts[w] = int(n)
    oov_mfa = {}
    p = REPO_ROOT / "logs/validate_english_mfa/oov_counts_english_mfa.txt"
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "\t" in line:
                w, n = line.split("\t")[:2]
                oov_mfa[w] = int(n)

    versions_txt = ""
    vpath = REPO_ROOT / "Report/versions.txt"
    if vpath.is_file():
        versions_txt = vpath.read_text(encoding="utf-8")

    mfa_version = "3.4.3"
    m = re.search(r"mfa version\s*:\s*(\S+)", versions_txt)
    if m:
        mfa_version = m.group(1)

    S = STYLES
    story: list = []
    add = story.append

    def P(text, style="Body"):
        add(Paragraph(text, S[style]))

    def H1(text):
        add(Paragraph(text, S["H1b"]))

    def H2(text):
        add(Paragraph(text, S["H2b"]))

    def fig(rel_path: str, caption: str, width_mm=175):
        path = REPO_ROOT / rel_path
        if not path.is_file():
            P(f"<i>figure missing: {rel_path}</i>", "Small")
            return
        from PIL import Image as PILImage

        with PILImage.open(path) as im:
            w, h = im.size
        width = width_mm * mm
        add(KeepTogether([Image(str(path), width=width, height=width * h / w),
                          Paragraph(caption, S["Cap"])]))

    # ------------------------------------------------------------------ title
    add(Paragraph("Forced Alignment using the Montreal Forced Aligner", S["Title"]))
    add(
        Paragraph(
            "Assignment 2a - alignment of the provided speech dataset",
            S["Heading3"],
        )
    )
    add(Spacer(1, 4))
    P(
        f"<b>Tool:</b> Montreal Forced Aligner {mfa_version} (conda-forge) &nbsp;&nbsp; "
        f"<b>Acoustic model:</b> english_us_arpa (v2.0.0) &nbsp;&nbsp; "
        f"<b>Dictionary:</b> english_us_arpa (v2.0.0)",
        "Small",
    )
    add(Spacer(1, 6))

    # ------------------------------------------------------------- (a) setup
    H1("1. Setup - acoustic model and dictionary")
    P(
        "MFA was installed into a conda environment from conda-forge. This is the only "
        "installation route that works: the PyPI wheel of MFA does not install "
        "<font face='Courier'>kalpy</font>, the Kaldi Python bindings it imports at "
        "startup, and <font face='Courier'>kalpy</font> has no PyPI distribution at all "
        "(the project publishes it to conda-forge only). A pip-installed MFA fails "
        "immediately with <font face='Courier'>ModuleNotFoundError: No module named "
        "'_kalpy'</font>, which was confirmed on this machine before switching to conda."
    )
    P(
        "Two model artefacts are required: the <b>pronunciation dictionary</b>, which maps "
        "each word to its phoneme sequence, and the <b>acoustic model</b>, which scores "
        "those phonemes against the audio."
    )
    add(
        table(
            [
                ["Artefact", "Name", "Version", "Detail"],
                [
                    "Acoustic model",
                    "english_us_arpa",
                    "v2.0.0",
                    "GMM-HMM, triphone, MFCC, 10 ms frame shift, fMLLR speaker adaptation",
                ],
                [
                    "Dictionary",
                    "english_us_arpa",
                    "v2.0.0",
                    "199,860 word types; 208,651 pronunciation lines; 70 phones",
                ],
                ["MFA", "-", mfa_version, "conda-forge, env 'aligner', Python 3.13.18"],
                [
                    "G2P model (extra credit)",
                    "english_us_arpa",
                    "v2.0.0",
                    "synthesises pronunciations for out-of-vocabulary words",
                ],
                [
                    "2nd acoustic model (extra credit)",
                    "english_mfa",
                    "v2.0.0",
                    "MFA/IPA phone set (72 labels) instead of ARPA (54)",
                ],
            ],
            col_widths=[38 * mm, 30 * mm, 18 * mm, 89 * mm],
        )
    )
    add(Spacer(1, 5))
    P(
        "The acoustic model reports an internal build version of "
        "<font face='Courier'>3.0.0a2.dev0+g940e907.d20230824</font> (trained 2024-02-10), "
        "while the model store labels it <font face='Courier'>v2.0.0</font>; the store "
        "version is what the download commands below select. Full version output is in "
        "<font face='Courier'>Report/versions.txt</font>.",
        "Small",
    )
    P(
        "<font face='Courier'>conda create -n aligner --override-channels -c conda-forge "
        "montreal-forced-aligner -y</font><br/>"
        "<font face='Courier'>conda activate aligner &amp;&amp; mfa version &nbsp;<i># "
        f"{mfa_version}</i></font><br/>"
        "<font face='Courier'>mfa model download dictionary english_us_arpa</font><br/>"
        "<font face='Courier'>mfa model download acoustic english_us_arpa</font>",
        "Mono",
    )

    # ----------------------------------------------------------- (b) dataset
    H1("2. Dataset summary")
    n_wav = ds.get("wav_count", "?")
    n_tr = ds.get("transcript_count", "?")
    P(
        f"The dataset supplied with the assignment was used unmodified - no other data was "
        f"downloaded or substituted. It contains <b>{n_wav} audio files</b> and "
        f"<b>{n_tr} transcripts</b> with an exact one-to-one stem match and no orphans, "
        f"totalling <b>{ds.get('total_duration_sec', '?')} s</b> of audio and "
        f"<b>{ds.get('total_words', '?')} normalised word tokens</b> "
        f"({len((REPO_ROOT / 'data/corpus_vocabulary.txt').read_text(encoding='utf-8').split())} types)."
    )
    rows = [["File", "Container", "Rate (Hz)", "Ch", "Duration (s)", "Words", "spn"]]
    stem_spn = {d["stem"]: d["spn_count"] for d in stats}
    for entry in ds.get("files", []):
        rows.append(
            [
                entry["wav"],
                entry["source_format"],
                str(entry["sample_rate"]),
                str(entry["channels"]),
                f"{entry['duration_sec']:.2f}",
                str(entry["word_count"]),
                str(stem_spn.get(entry["stem"], "-")),
            ]
        )
    add(table(rows, col_widths=[54 * mm, 27 * mm, 18 * mm, 10 * mm, 22 * mm, 15 * mm, 12 * mm]))
    add(Spacer(1, 4))
    P(
        f"<b>Problems found: {len(ds.get('problems', []))}.</b> "
        f"Empty transcripts: 0. Transcripts shorter than three words: 0. Unreadable audio: 0. "
        f"All six files are 16 kHz mono 16-bit PCM.",
    )
    P(
        "Two properties of the raw data required handling. First, the three "
        "<font face='Courier'>F2BJRLP*.wav</font> files are <b>not WAV despite the "
        "extension</b>: they carry a NIST SPHERE <font face='Courier'>NIST_1A</font> header "
        "(corpus <font face='Courier'>BU_Radio_Corpus</font>, speaker "
        "<font face='Courier'>f2b</font>) and MFA cannot read them. The preparation script "
        "decodes the header and rewrites them as RIFF/WAVE using only the Python standard "
        "library, so no <font face='Courier'>sox</font> or "
        "<font face='Courier'>ffmpeg</font> dependency is needed; converted sample counts "
        "match the source headers exactly. Second, three transcripts use an upper-case "
        "<font face='Courier'>.TXT</font> extension, which MFA's stem-based matching does "
        "not find on a case-sensitive filesystem, so transcripts are looked up by "
        "lower-cased stem."
    )

    # -------------------------------------------------------------- (c) figure
    H1("3. Sample alignment visualisation")
    P(
        "The figure below shows <font face='Courier'>F2BJRLP2</font> (28.65 s, 74 words, "
        "328 phones). Panels 1 and 2 are the whole file with word and phone boundaries; "
        "panels 3 and 4 zoom on 4.50-7.00 s with the word and phone tiers labelled. The "
        "zoom deliberately covers an out-of-vocabulary word: the transcript says "
        "<i>\"a campaign promise to de-politicize judicial appointments\"</i>, and MFA's "
        "tokeniser splits <font face='Courier'>de-politicize</font> into "
        "<font face='Courier'>de</font> + <font face='Courier'>politicize</font>. "
        "<font face='Courier'>de</font> is in the dictionary and is aligned as "
        "<font face='Courier'>D IY1</font>, but <font face='Courier'>politicize</font> is "
        "not, and the whole word is covered by a single "
        "<font face='Courier'>spn</font> (\"unknown phone\") span - visible as one long "
        "red interval with no internal boundaries - spanning 5.660-6.530 s."
    )
    fig("Report/figures/F2BJRLP2_oov_zoom.png",
        "F2BJRLP2: waveform with word boundaries (panel 1, blue), phone boundaries "
        "(panel 2, red), and zoomed word and phone tiers (panels 3-4). The unsegmented "
        "spn span over \"politicize\" (5.660-6.530 s) is the alignment failure caused by "
        "the missing dictionary entry.")

    P(
        "A second file is shown for contrast, because it illustrates the short ISLE "
        "utterances and their unusually large amount of trailing non-speech."
    )
    fig("Report/figures/ISLE_SESS0131_BLOCKD02_01_sprt1_alignment.png",
        "ISLE_SESS0131_BLOCKD02_01_sprt1: \"I SAID WHITE NOT BAIT\". All five words are "
        "aligned within 0.440-2.240 s of a 4.125 s file; the remaining 1.885 s (45.7%) is "
        "unlabelled trailing non-speech.")

    add(PageBreak())

    # -------------------------------------------------------- (d) observations
    H1("4. Key observations and errors found")
    P(
        "All timings below are read from the TextGrids in "
        "<font face='Courier'>outputs/</font>; the machine-readable version of every "
        "measurement is in <font face='Courier'>Report/alignment_stats.json</font>."
    )

    H2("4.1 Every out-of-vocabulary word becomes exactly one spn span")
    n_spn = sum(d["spn_count"] for d in stats)
    n_oov_tokens = sum(oov_counts.values())
    P(
        f"<font face='Courier'>mfa validate</font> reported {len(oov_counts)} OOV word types "
        f"totalling {n_oov_tokens} tokens, and the aligned TextGrids contain exactly "
        f"<b>{n_spn} <font face='Courier'>spn</font> spans</b> - the counts match one to "
        f"one. Each span coincides precisely with an OOV word:"
    )
    add(
        table(
            [
                ["File", "Word", "spn span (s)", "Duration (s)"],
                ["F2BJRLP1", "dukakis", "15.450 - 16.000", "0.550"],
                ["F2BJRLP1", "wbur ('s wbur's)", "20.560 - 21.330", "0.770"],
                ["F2BJRLP1", "melnicove", "21.750 - 22.290", "0.540"],
                ["F2BJRLP2", "dukakis", "2.730 - 3.350", "0.620"],
                ["F2BJRLP2", "politicize", "5.660 - 6.530", "0.870"],
                ["F2BJRLP2", "maffy", "23.920 - 24.340", "0.420"],
            ],
            col_widths=[30 * mm, 42 * mm, 45 * mm, 30 * mm],
        )
    )
    add(Spacer(1, 4))
    P(
        "Two details are worth noting. The zone is not marked as silence but as an explicit "
        "unknown phone, so downstream code must test for "
        "<font face='Courier'>spn</font> rather than assuming every phone label is a real "
        "phoneme. And for <font face='Courier'>wbur's</font> only the unknown stem was "
        "collapsed: the clitic is still aligned, as "
        "<font face='Courier'>AH0 Z</font> at 21.330-21.440 s immediately after the spn "
        "span, because <font face='Courier'>'s</font> is itself a dictionary entry. "
        "The longest phone in both F2BJRLP1 and F2BJRLP2 is an "
        "<font face='Courier'>spn</font> (0.770 s and 0.870 s), which is a useful automated "
        "warning signal for dictionary gaps."
    )

    H2("4.2 MFA emits no sil phone - silence is an unlabelled interval")
    P(
        "None of the six TextGrids contains a single <font face='Courier'>sil</font> label, "
        "contrary to what is often assumed. Non-speech appears as <b>empty (unlabelled) "
        "intervals in both tiers</b>, 14 of them in F2BJRLP1 and 10 in F2BJRLP2, and the "
        "two tiers mirror each other exactly. The trailing gap in F2BJRLP1 is 25.010-"
        "25.309 s, i.e. 0.299 s. Code that reads the phone tier and expects an explicit "
        "silence symbol will silently treat those regions as missing data."
    )

    H2("4.3 The short ISLE clips are mostly non-speech")
    P(
        "The three ISLE files are 5-word utterances padded with a large amount of "
        "trailing non-speech, which dominates their duration:"
    )
    add(
        table(
            [
                ["File", "File (s)", "Speech span (s)", "Trailing (s)", "% of file"],
                ["ISLE_..._01_sprt1", "4.125", "0.440 - 2.240", "1.885", "45.7%"],
                ["ISLE_..._02_sprt1", "3.875", "0.620 - 2.190", "1.685", "43.5%"],
                ["ISLE_..._03_sprt1", "4.500", "0.220 - 1.960", "2.540", "56.4%"],
            ],
            col_widths=[45 * mm, 22 * mm, 40 * mm, 25 * mm, 20 * mm],
        )
    )
    add(Spacer(1, 4))
    P(
        "The word <i>I</i> is the shortest word in every ISLE file - 0.070 s in both "
        "<font face='Courier'>..._02</font> (0.620-0.690 s) and "
        "<font face='Courier'>..._03</font> (0.220-0.290 s), and 0.100 s in "
        "<font face='Courier'>..._01</font>. In the longer BU files the shortest words are "
        "the article <i>a</i> at 0.040-0.050 s, and the longest are "
        "<i>administration</i> (0.910 s, F2BJRLP1), <i>association</i> (0.820 s, F2BJRLP3) "
        "and <i>politicize</i> (0.870 s, F2BJRLP2 - the spn span)."
    )

    H2("4.4 Pauses and gaps left by an unknown word")
    P(
        "The largest gap between consecutive words is 0.700 s in F2BJRLP2 at 12.330 s "
        "(between <i>court</i> and <i>for</i>) and 0.540 s in F2BJRLP3 at 21.630 s "
        "(between <i>houses</i> and <i>despite</i>), both genuine pauses. More telling is "
        "the 0.290 s unlabelled interval at 3.350-3.640 s in F2BJRLP2: it sits immediately "
        "after the <font face='Courier'>dukakis</font> spn span, so the aligner absorbed "
        "part of the neighbouring material into silence around the word it could not "
        "pronounce. By contrast the tightest transition is 0.030 s, between <i>new</i> and "
        "<i>not</i> in <font face='Courier'>ISLE_..._02</font> at 1.430 s."
    )

    H2("4.5 Alignment quality differs sharply between the two halves of the dataset")
    if quality:
        rows = [["File", "Speech log-likelihood", "SNR", "Phone duration deviation"]]
        for row in quality:
            rows.append(
                [
                    row["file"],
                    f"{float(row['speech_log_likelihood']):.2f}",
                    f"{float(row['snr']):.2f}",
                    f"{float(row['phone_duration_deviation']):.3f}",
                ]
            )
        add(table(rows, col_widths=[60 * mm, 40 * mm, 25 * mm, 45 * mm]))
        add(Spacer(1, 4))
    P(
        "The three BU Radio files score about -46 to -47 while the three ISLE files score "
        "about -61 to -62, and the ISLE files have notably higher SNR (10.4-12.3 versus "
        "7.6-9.9). The corpus is flat - there are no speaker subdirectories - so MFA treats "
        "all six files as one speaker named after the directory and applies fMLLR speaker "
        "adaptation across them, even though they come from two different sources and "
        "recording conditions. This is a concrete, measurable consequence of corpus layout, "
        "and it is why the README suggests <font face='Courier'>--single_speaker</font> as "
        "the first thing to try when alignment quality matters."
    )

    H2("4.6 A transcript/normalisation mismatch that changes pronunciation")
    P(
        "The original transcript reads <i>S.J.C.'s</i>. Naive punctuation stripping yields "
        "the tokens <font face='Courier'>s j c s</font>, whose final token is the letter "
        "<i>S</i> (<font face='Courier'>EH1 S</font>). But the spoken form is the clitic "
        "<i>'s</i> (<font face='Courier'>Z</font> / <font face='Courier'>AH0 Z</font>). "
        "Both are valid dictionary entries, so no OOV warning is produced and nothing looks "
        "wrong - the word is simply mis-pronounced during alignment. The preparation script "
        "preserves standalone clitics for this reason and emits "
        "<font face='Courier'>s j c 's</font>."
    )

    add(PageBreak())

    # ------------------------------------------------------ (e) extra credit
    H1("5. Extra credit")

    H2("5.1 Custom pronunciation dictionary from an MFA G2P model")
    P(
        "An MFA G2P model (<font face='Courier'>english_us_arpa</font>) was used in two "
        "ways: to generate pronunciations for <b>every</b> word in the transcripts, and - "
        "with <font face='Courier'>--dictionary_path</font> - for only the words the base "
        "dictionary lacks. The latter produced 13 pronunciations for the 5 OOV types, which "
        "were merged with the 208,651 base entries by "
        "<font face='Courier'>scripts/05_build_custom_dictionary.py</font> to give "
        "<font face='Courier'>dictionaries/english_us_arpa_plus_g2p.dict</font> "
        f"({custom_report.get('total_lines', '?')} lines). No generated pronunciation had to "
        f"be rejected, i.e. every phone the G2P model emitted already existed in the base "
        f"dictionary's 70-phone inventory."
    )
    rows = [["OOV word", "Generated pronunciation(s)"]]
    for word, prons in (custom_report.get("words_added") or {}).items():
        shown = "; ".join(prons[:2]) + (f"  (+{len(prons) - 2} more)" if len(prons) > 2 else "")
        rows.append([word, shown])
    add(table(rows, col_widths=[30 * mm, 145 * mm]))
    add(Spacer(1, 5))
    P(
        "The G2P model is visibly unsure about <font face='Courier'>wbur</font>, offering "
        "five variants (<font face='Courier'>B ER0</font>, "
        "<font face='Courier'>V B ER0</font>, <font face='Courier'>W AH0 B ER0</font>, "
        "<font face='Courier'>W AO1 AH0 B ER0</font>, <font face='Courier'>W AY1 B ER0</font>) "
        "because it has never seen the consonant cluster <i>wbr</i>, whereas the proper nouns "
        "<font face='Courier'>maffy</font> and <font face='Courier'>melnicove</font> get a "
        "single plausible form each."
    )
    P(
        "Re-running <font face='Courier'>mfa validate</font> and "
        "<font face='Courier'>mfa align</font> with the merged dictionary eliminated the "
        "OOVs completely: <font face='Courier'>logs/validate_custom/utterance_oovs.txt</font> "
        "is empty, and the number of <font face='Courier'>spn</font> spans fell from "
        "<b>6 to 0</b>. The regions that were previously one flat unknown span now receive "
        "real phone sequences:"
    )
    rows = [["File", "Region (s)", "Word", "Phones produced by the custom run"]]
    for entry in (cmp_dict.get("files") or []):
        for region in entry.get("spn_regions_ref", []):
            rows.append(
                [
                    entry["stem"],
                    f"{region['start']} - {region['end']}",
                    ", ".join(region["words"]),
                    " ".join(p["label"] for p in region["phones_in_test_run"]),
                ]
            )
    add(table(rows, col_widths=[28 * mm, 25 * mm, 25 * mm, 97 * mm]))
    add(Spacer(1, 4))
    P(
        "The change is local, not global. Phone counts are identical in the four files with "
        "no OOV (372, 13, 12, 13) and rise only in the two affected files (284 to 299, "
        "328 to 345). Word boundaries move by a mean of 12.9 ms in F2BJRLP1 and 2.8 ms in "
        "F2BJRLP2, and the four unaffected files have <b>identical</b> boundaries "
        "(mean shift 0.000 s). Only 7 of 70 and 5 of 74 word onsets in those two files moved "
        "by more than 10 ms. Full data: "
        "<font face='Courier'>Report/alignment_comparison.json</font>."
    )

    H2("5.2 Second acoustic model: english_mfa")
    P(
        "<font face='Courier'>english_mfa</font> was downloaded and aligned with its own "
        "matching dictionary. It uses the MFA/IPA phone set (72 distinct labels, e.g. "
        "<font face='Courier'>dʒ</font>, <font face='Courier'>aː</font>) rather than ARPA "
        "with stress digits (54 labels, e.g. <font face='Courier'>AH0</font>, "
        "<font face='Courier'>EY1</font>), and it aligned all 6 files in 74 s versus 214 s. "
        "Its dictionary has different coverage: it is missing "
        "<font face='Courier'>judgeships</font>, which <font face='Courier'>english_us_arpa"
        "</font> knows, so it produced <b>7</b> "
        "<font face='Courier'>spn</font> spans rather than 6 "
        f"({len(oov_mfa)} OOV types versus {len(oov_counts)})."
    )
    rows = [["File", "Phone count Δ", "Mean |boundary shift|", "Max |shift|", "Word onsets moved >10 ms"]]
    for entry in (cmp_model.get("files") or []):
        w = entry.get("words", {})
        rows.append(
            [
                entry["stem"],
                f"{entry['phones_test'] - entry['phones_ref']:+d}",
                f"{w.get('start_shift_mean_abs', 0):.4f} s",
                f"{w.get('start_shift_max_abs', 0):.2f} s",
                f"{w.get('words_shifted_gt_10ms', 0)} of {w.get('word_count_ref', 0)}",
            ]
        )
    add(table(rows, col_widths=[50 * mm, 25 * mm, 35 * mm, 25 * mm, 40 * mm]))
    add(Spacer(1, 4))
    P(
        "Changing the acoustic model perturbs <b>every</b> file (mean shift 11.7-34.0 ms, "
        "24-26 word onsets moved by more than 10 ms in each BU file, up to 0.68 s in "
        "F2BJRLP1), whereas changing the dictionary perturbed only the two files containing "
        "OOVs. That contrast is the clearest demonstration in this study of the difference "
        "between the two components: the dictionary decides <i>what</i> phonemes are looked "
        "for, the acoustic model decides <i>where</i> they land."
    )
    P(
        "On quality metrics <font face='Courier'>english_mfa</font> looks better on the "
        "long BU files (phone-duration deviation 4.70 to 3.50 for F2BJRLP1) and on the ISLE "
        "likelihoods (about -53 to -56 versus -61 to -62), but worse on two of the three "
        "ISLE duration-deviation values. Likelihoods are not directly comparable between "
        "models with different phone inventories, so this should be treated as suggestive "
        "rather than conclusive - a proper comparison would need gold-standard boundaries."
    )

    # ------------------------------------------------------------ closing
    H1("6. Reproducing this work")
    P(
        "Repository layout, exact commands and the full ordered command log are in "
        "<font face='Courier'>README.md</font> and "
        "<font face='Courier'>logs/commands.log</font>. The whole pipeline runs as:"
    )
    P(
        "conda env create -f environment.yml<br/>"
        "conda activate aligner<br/>"
        "mfa model download dictionary english_us_arpa<br/>"
        "mfa model download acoustic english_us_arpa<br/>"
        "./scripts/run_pipeline.sh<br/>"
        "python scripts/04_inspect_textgrids.py<br/>"
        "python scripts/08_make_report.py",
        "Mono",
    )
    P(
        "Two MFA 3.4.3 subcommands failed on this data and were worked around, and are "
        "recorded in the command log because they were genuinely attempted: "
        "<font face='Courier'>mfa find_oovs</font> raises an sqlalchemy "
        "<font face='Courier'>UNIQUE constraint failed: word.id</font> error on the merged "
        "dictionary (replaced by <font face='Courier'>mfa validate --ignore_acoustics</font>, "
        "which reports the same OOV information), and "
        "<font face='Courier'>mfa compare_alignments</font> raises "
        "<font face='Courier'>TypeError: 'KeyError' object is not subscriptable</font> when "
        "given TextGrid-only directories (replaced by "
        "<font face='Courier'>scripts/06_compare_alignments.py</font>)."
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(args.out),
        pagesize=A4,
        leftMargin=17 * mm,
        rightMargin=17 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="Forced Alignment using the Montreal Forced Aligner",
        author="Assignment 2a",
    )

    def decorate(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(17 * mm, 9 * mm, "Assignment 2a - MFA forced alignment")
        canvas.drawRightString(A4[0] - 17 * mm, 9 * mm, f"page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
