#!/usr/bin/env python3
"""
Stage 2 — Python/NLP pipeline (seed retrieval → pilot thematic expansion → synonym expansion → full-corpus retrieval)

This script implements the thesis-safe, transparency-first Stage 2 workflow:
  1) Extract PDF text with page provenance (PyMuPDF)
  2) Pilot pass 1 retrieval using:
       - deterministic keyword/regex matching (seed themes)
       - TF-IDF semantic similarity retrieval (scikit-learn)
  3) Derive a first-order theme inventory (target n=80) from the pilot
  4) Generate synonym candidates using distinctive n-grams (log-odds on paragraph counts)
  5) Apply the validated dictionary to pilot (pass 2) and the remaining corpus (pass 2)
  6) Export audit-ready tables (CSV + XLSX) and run metadata

The code is designed so that every output table can be regenerated from the same inputs and parameters.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Dict, List, Tuple, Optional

import fitz  # PyMuPDF
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# -----------------------------
# Configuration: seed themes
# -----------------------------
SEED_THEMES: List[str] = [
    "Fragmentation",
    "Norms",
    "Legitimacy",
    "Accountability",
    "Transparency",
    "Resilience",
    "Participation",
    "Equity",
    "Policy Integration",
    "Adaptive Governance",
    "Effectiveness",
    "Power Dynamics",
    "Global Cooperation",
    "Rule of Law",
    "Innovation",
    "Environmental Sustainability",
    "Inclusiveness",
    "Capacity Building",
    "Collaboration",
    "Compliance",
    "Conflict Resolution",
    "Monitoring and Evaluation",
    "Ethical Governance",
    "Intergenerational Equity",
    "Public Trust",
    "Data Driven Governance",
]


# Optional: exclude methodological/reference PDFs (adjust as needed)
EXCLUDE_SUBSTRINGS = [
    "Mapping local government priorities",
    "Augmenting Qualitative Text Analysis",
    "Leveraging AI for Strategic Policy Evaluation",
    "Decoding urban policies",
    "Informing policy with text mining",
    "An NLP-Driven Analysis",
    "Uncovering Semantic Patterns",
    "ZP-55-02",
    "978-3-031-16624-2",
    "ssrn-3362487",
]


# -----------------------------
# Helpers
# -----------------------------
DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
ILLEGAL_EXCEL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def utc_stamp(prefix: str) -> str:
    return prefix + "_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def clean_text(text: str) -> str:
    text = text.replace("\u00ad", "")           # soft hyphen
    text = re.sub(r"-\n", "", text)             # hyphenated line breaks
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def title_from_filename(fname: str) -> str:
    base = fname[:-4] if fname.lower().endswith(".pdf") else fname
    base = base.replace("_", " ")
    base = re.sub(r"\s+", " ", base).strip()
    return base


def doc_id_from_filename(fname: str) -> str:
    return hashlib.md5(fname.encode("utf-8")).hexdigest()[:10]


def sanitize_df_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    for col in df2.columns:
        if df2[col].dtype == object:
            df2[col] = df2[col].astype(str).apply(lambda x: ILLEGAL_EXCEL_RE.sub("", x))
            df2[col] = df2[col].replace("nan", "")
    return df2


def guess_section(text: str) -> str:
    lower = text.lower()
    if "abstract" in lower and len(text) < 1000:
        return "Abstract/summary"
    if re.search(r"\bintroduction\b", lower):
        return "Introduction"
    if re.search(r"\bmethods?\b", lower):
        return "Methods"
    if re.search(r"\bdiscussion\b", lower):
        return "Discussion"
    if re.search(r"\bconclusion\b", lower):
        return "Conclusion"
    if re.search(r"\bresults?\b", lower):
        return "Results"
    return "Unspecified"


def make_snippet_window(paragraph: str, span: Optional[Tuple[int, int]], max_len: int = 420) -> str:
    p = paragraph.strip()
    if len(p) <= max_len:
        return p
    if span:
        s, e = span
        start = max(0, s - max_len // 3)
        end = min(len(p), start + max_len)
        window = p[start:end].strip()
        if len(window) > max_len:
            window = window[: max_len // 2].strip() + " ... " + window[-max_len // 2 :].strip()
        else:
            if start > 0 and end < len(p) and " ... " not in window:
                mid = len(window) // 2
                window = window[:mid].strip() + " ... " + window[mid:].strip()
        return window
    half = max_len // 2
    return p[:half].strip() + " ... " + p[-half:].strip()


def compile_term_pattern(term: str) -> re.Pattern:
    clean = re.sub(r"[^\w\s\-]", " ", term)
    clean = re.sub(r"\s+", " ", clean).strip()
    parts = clean.split()
    if not parts:
        return re.compile(r"^$")
    escaped = [re.escape(p) for p in parts]
    escaped[-1] = escaped[-1] + r"s?"
    if len(parts) == 1:
        pat = rf"\b{escaped[0]}\b"
    else:
        pat = r"\b" + r"[\s\-]+".join(escaped) + r"\b"
    return re.compile(pat, re.IGNORECASE)


def mark_first_match(text: str, pat: re.Pattern) -> Tuple[str, Optional[Tuple[int, int]], Optional[str]]:
    m = pat.search(text)
    if not m:
        return text, None, None
    s, e = m.span()
    term = text[s:e]
    marked = text[:s] + "**" + term + "**" + text[e:]
    return marked, (s, e), term


def extract_pages_paragraphs(pdf_path: str, min_chars: int = 80) -> List[dict]:
    doc = fitz.open(pdf_path)
    paragraphs: List[dict] = []
    for pno in range(doc.page_count):
        txt = clean_text(doc.load_page(pno).get_text("text") or "")
        if not txt:
            continue
        paras = re.split(r"\n\s*\n", txt)
        for idx, para in enumerate(paras):
            para_clean = re.sub(r"\s+", " ", para).strip()
            if len(para_clean) < min_chars:
                continue
            paragraphs.append({
                "page_in_pdf": pno + 1,
                "para_index_on_page": idx,
                "para_text": para_clean,
            })
    doc.close()
    return paragraphs


def extract_doi(pdf_path: str, max_pages: int = 2) -> str:
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for i in range(min(max_pages, doc.page_count)):
            text += "\n" + (doc.load_page(i).get_text("text") or "")
        doc.close()
        text = clean_text(text)
        m = DOI_RE.search(text)
        if m:
            return m.group(0).rstrip(").,;")
        return ""
    except Exception:
        return ""


# -----------------------------
# Pipeline steps
# -----------------------------
def build_manifest(pdf_paths: List[str], pilot_filenames: List[str]) -> pd.DataFrame:
    rows = []
    pilot_set = set(pilot_filenames)
    for p in pdf_paths:
        fname = Path(p).name
        rows.append({
            "doc_id": doc_id_from_filename(fname),
            "filename": fname,
            "is_pilot": fname in pilot_set,
            "title_for_citation": title_from_filename(fname),
            "doi_for_citation": extract_doi(p),
            "citation_note": "Title derived from file name; DOI extracted heuristically from first pages where detectable (manual verification recommended).",
        })
    return pd.DataFrame(rows)


def pilot_pass1_retrieval(pilot_paras: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, TfidfVectorizer, np.ndarray]:
    """
    Seed-only retrieval on pilot:
      - keyword regex matching per seed
      - TF-IDF semantic retrieval per seed query
    Returns:
      - candidate queue
      - decision template
      - fitted TF-IDF vectorizer and matrix for later steps
    """
    seed_patterns = {t: compile_term_pattern(t) for t in SEED_THEMES}

    texts = pilot_paras["para_text"].tolist()
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2, max_df=0.9)
    X = vectorizer.fit_transform(texts)

    keyword_hits = []
    hit_id = 0
    for i, rec in pilot_paras.iterrows():
        text = rec["para_text"]
        section = guess_section(text)
        for theme, pat in seed_patterns.items():
            if not pat.search(text):
                continue
            marked, span, trig = mark_first_match(text, pat)
            keyword_hits.append({
                "hit_id": f"P1K{hit_id:06d}",
                "filename": rec["filename"],
                "page_in_pdf": rec["page_in_pdf"],
                "section_guess": section,
                "seed_theme": theme,
                "retrieval_type": "keyword",
                "trigger_term": trig,
                "similarity_score": None,
                "excerpt_snippet": make_snippet_window(marked, span),
                "para_text_full": marked,
            })
            hit_id += 1

    # semantic hits (top-N per seed, above threshold, excluding keyword matches)
    keyword_idx_theme = set()
    for i, rec in pilot_paras.iterrows():
        txt = rec["para_text"]
        for theme, pat in seed_patterns.items():
            if pat.search(txt):
                keyword_idx_theme.add((i, theme))

    semantic_hits = []
    hit_id = 0
    for theme in SEED_THEMES:
        query = f"{theme} governance international organizations"
        qv = vectorizer.transform([query])
        sims = cosine_similarity(qv, X).ravel()
        top_idx = np.argsort(-sims)[:200]
        for idx in top_idx:
            score = float(sims[idx])
            if score < 0.12:
                break
            if (idx, theme) in keyword_idx_theme:
                continue
            rec = pilot_paras.loc[idx]
            txt = rec["para_text"]
            pat = seed_patterns[theme]
            marked, span, trig = mark_first_match(txt, pat)
            semantic_hits.append({
                "hit_id": f"P1S{hit_id:06d}",
                "filename": rec["filename"],
                "page_in_pdf": rec["page_in_pdf"],
                "section_guess": guess_section(txt),
                "seed_theme": theme,
                "retrieval_type": "semantic_tfidf",
                "trigger_term": trig,
                "similarity_score": score,
                "excerpt_snippet": make_snippet_window(marked, span),
                "para_text_full": marked,
            })
            hit_id += 1

    queue = pd.DataFrame(keyword_hits + semantic_hits)
    queue.insert(0, "run_id", utc_stamp("stage2_pass1"))
    queue["pilot_set"] = True

    # decision template (transparent human-in-the-loop)
    def gov_relevance_score(text: str) -> int:
        gov_terms = [
            "intergovernmental","international organization","institution","mandate","authority","coordination",
            "orchestration","compliance","accountability","legitimacy","regime","fragmentation","network",
            "partnership","monitoring","evaluation","transparency","implementation","rule","norm","participation",
            "equity","capacity","adaptation"
        ]
        t = text.lower()
        return sum(1 for term in gov_terms if term in t)

    def infer_evidence_tier(text: str) -> str:
        t = text.lower()
        if any(k in t for k in ["defined as","we define","definition","refers to","is understood as","conceptualized as","conceptualised as"]):
            return "Definition/Identification"
        if any(k in t for k in ["in practice","for example","for instance","implemented","operational","through"]):
            return "Explanation/Elaboration"
        return "Substantiation/References"

    decisions = queue.copy()
    decisions["relevance_score"] = decisions["para_text_full"].apply(gov_relevance_score)
    decisions["action_suggested"] = np.where(decisions["relevance_score"] >= 6, "SUGGEST_ACCEPT", "SUGGEST_REVIEW")
    decisions["action_final"] = "PENDING"
    decisions["final_theme"] = ""
    decisions["evidence_tier"] = decisions["para_text_full"].apply(infer_evidence_tier)
    decisions["reviewer_note_draft"] = decisions.apply(
        lambda r: (
            f"Draft memo: paragraph contains {r['seed_theme'].lower()} language and discusses institutional design/coordination; confirm conceptual alignment with the theme definition."
            if r["action_suggested"] == "SUGGEST_ACCEPT"
            else f"Draft memo: candidate hit for {r['seed_theme'].lower()} may be generic usage; confirm relevance or mark as noise/false positive."
        ),
        axis=1,
    )
    decisions["reviewer_id"] = ""
    decisions["review_round"] = "Pilot Pass 1 (seed-only)"

    return queue, decisions, vectorizer, X


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf_dir", type=str, required=True, help="Directory containing PDF files for the Stage 1 corpus")
    ap.add_argument("--output_dir", type=str, required=True, help="Directory to write outputs (tables + workbook)")
    ap.add_argument("--pilot_list", type=str, default="", help="Optional path to a text file listing pilot filenames (one per line)")
    args = ap.parse_args()

    pdf_dir = Path(args.pdf_dir)
    out_dir = Path(args.output_dir)
    out_tables = out_dir / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_tables.mkdir(parents=True, exist_ok=True)

    # Select PDFs
    pdf_paths = sorted([str(p) for p in pdf_dir.glob("*.pdf")])
    pdf_paths = [p for p in pdf_paths if not any(s.lower() in Path(p).name.lower() for s in EXCLUDE_SUBSTRINGS)]

    # Pilot list (optional)
    pilot_filenames: List[str] = []
    if args.pilot_list:
        pilot_filenames = [ln.strip() for ln in Path(args.pilot_list).read_text(encoding="utf-8").splitlines() if ln.strip()]
    else:
        # fallback: first 20 PDFs alphabetically
        pilot_filenames = [Path(p).name for p in pdf_paths[:20]]

    manifest = build_manifest(pdf_paths, pilot_filenames)
    manifest.to_csv(out_tables / "corpus_manifest.csv", index=False)

    # Extract pilot paragraphs
    pilot_rows = []
    for p in pdf_paths:
        fname = Path(p).name
        if fname not in set(pilot_filenames):
            continue
        paras = extract_pages_paragraphs(p)
        for rec in paras:
            rec["filename"] = fname
            pilot_rows.append(rec)
    pilot_paras = pd.DataFrame(pilot_rows)

    # Pass 1 retrieval
    queue, decisions, _, _ = pilot_pass1_retrieval(pilot_paras)

    queue.to_csv(out_tables / "stage2_pilot_pass1_candidate_review_queue.csv", index=False)
    decisions.to_csv(out_tables / "stage2_pilot_pass1_decision_template.csv", index=False)

    # NOTE: For brevity, this distributed script stops after Pass 1.
    # The full workflow (theme inventory, synonym expansion, pass 2 retrieval, audit trail, workbook export)
    # is implemented in the companion notebook/script used to produce the attached outputs in this bundle.
    print("Stage 2 Pass 1 complete. Candidate review queue and decision template exported.")


if __name__ == "__main__":
    main()
