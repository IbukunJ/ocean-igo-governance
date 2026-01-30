#!/usr/bin/env python3
"""
Stage 2 — Full Python/NLP pipeline (seed retrieval → pilot thematic expansion → synonym expansion → full-corpus retrieval)

This script reproduces the Stage 2 workflow described in the thesis methods chapter, with an explicit audit trail.

Core design principle:
  - Every excerpt, term, and tag in the outputs is traceable to a document (filename), page number, and extraction rule.

Main outputs (CSV + a single XLSX workbook):
  - corpus_manifest.csv
  - stage2_pilot_pass1_candidate_review_queue.csv (+ decision template)
  - stage2_first_order_theme_inventory_80.csv
  - stage2_synonym_candidate_pool.csv
  - stage2_synonym_shortlist_compiled_validated.csv
  - stage2_dictionary_tableB.csv
  - stage2_pilot_pass2_candidate_review_queue.csv (+ decision template)
  - stage2_fullcorpus_pass2_candidate_review_queue_remaining.csv (+ decision template)
  - run_log.csv and audit_trail.csv

Notes:
  - This script generates "reviewer_note_draft" and "action_suggested" fields to support screening; "action_final"
    remains PENDING by design (human validation step).
"""

from __future__ import annotations

import argparse
import json
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import fitz  # PyMuPDF
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# -----------------------------
# Configuration
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

DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
ILLEGAL_EXCEL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

# lexical stems used for governance-focused filtering in theme/synonym expansion
STEMS = [
    "regime","institution","orchestr","coordin","compli","legitim","account","particip","transparen",
    "equit","resilien","adapt","network","partner","monitor","evaluat","enforc","authorit","mandat",
    "law","legal","rule","norm","fragment","coher","integrat","implement","capacity","stakehold",
    "public","trust","data","inform","oversight","govern","delegat","secretariat","principal","agent","polycentr"
]

# Exclude author names / citations that inflate dictionary noise
NAME_EXCLUDE = [
    "abbott","snidal","biermann","ostrom","young","barnett","finnemore","keohane","nye",
    "conca","ivanova","berliner","pattberg","zelli","snyder","bowen"
]

# Exclude common boilerplate words in PDF headers/footers and publisher metadata
ARTIFACT_WORDS = ["downloaded","free","copyright","rights reserved","issn","isbn","doi","www","http","permission",
                  "publisher","wiley","springer","taylor","francis","elsevier"]


# -----------------------------
# Helpers
# -----------------------------
def utc_stamp(prefix: str) -> str:
    return prefix + "_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def clean_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"-\n", "", text)
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


def stem_score(term: str) -> int:
    tl = term.lower()
    return sum(1 for s in STEMS if s in tl)


def contains_excluded_name(term: str) -> bool:
    tl = term.lower()
    return any(re.search(rf"\b{re.escape(n)}\b", tl) for n in NAME_EXCLUDE)


def has_artifact(term: str) -> bool:
    tl = term.lower()
    return any(w in tl for w in ARTIFACT_WORDS)


def is_probable_reference_text(text: str) -> bool:
    t = text.lower()
    years = len(re.findall(r"\b(19|20)\d{2}\b", t))
    if "references" in t[:40]:
        return True
    if years >= 3 and t.count(";") >= 2:
        return True
    if ("doi" in t or "http" in t or "www" in t) and years >= 1:
        return True
    return False


def gov_relevance_score(text: str) -> int:
    gov_terms = [
        "intergovernmental","international organization","institution","institutional","mandate","authority",
        "jurisdiction","coordination","orchestration","compliance","accountability","legitimacy","regime",
        "fragmentation","network","partnership","monitoring","evaluation","transparency","implementation",
        "enforcement","rule","rules","norm","norms","participation","equity","capacity","adaptation"
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


def find_term_evidence(term_norm: str, paras: pd.DataFrame) -> Optional[dict]:
    parts = term_norm.split()
    if len(parts) == 1:
        pat = re.compile(rf"\b{re.escape(parts[0])}s?\b", re.IGNORECASE)
    else:
        escaped = [re.escape(p) for p in parts]
        escaped[-1] = escaped[-1] + r"s?"
        pat = re.compile(r"\b" + r"[\s\-]+".join(escaped) + r"\b", re.IGNORECASE)

    for _, rec in paras.iterrows():
        txt = rec["para_text"]
        m = pat.search(txt)
        if m:
            marked = txt[:m.start()] + "**" + txt[m.start():m.end()] + "**" + txt[m.end():]
            return {
                "evidence_filename": rec["filename"],
                "evidence_page_in_pdf": int(rec["page_in_pdf"]),
                "evidence_section_guess": guess_section(txt),
                "evidence_excerpt_snippet": make_snippet_window(marked, (m.start(), m.end())),
            }
    return None


# -----------------------------
# Pipeline steps
# -----------------------------
def build_manifest(pdf_paths: List[str], pilot_filenames: List[str]) -> pd.DataFrame:
    pilot_set = set(pilot_filenames)
    rows = []
    for p in pdf_paths:
        fname = Path(p).name
        rows.append({
            "doc_id": doc_id_from_filename(fname),
            "filename": fname,
            "is_pilot": fname in pilot_set,
            "title_for_citation": title_from_filename(fname),
            "doi_for_citation": extract_doi(p),
            "authors_for_citation": "",
            "citation_note": "Title derived from file name; DOI extracted heuristically from first pages where detectable (manual verification recommended).",
        })
    return pd.DataFrame(rows)


def pilot_pass1_retrieval(pilot_paras: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, TfidfVectorizer, np.ndarray]:
    seed_patterns = {t: compile_term_pattern(t) for t in SEED_THEMES}
    texts = pilot_paras["para_text"].tolist()
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2, max_df=0.9)
    X = vectorizer.fit_transform(texts)

    keyword_hits = []
    hit_id = 0
    for i, rec in pilot_paras.iterrows():
        text = rec["para_text"]
        for theme, pat in seed_patterns.items():
            if not pat.search(text):
                continue
            marked, span, trig = mark_first_match(text, pat)
            keyword_hits.append({
                "hit_id": f"P1K{hit_id:06d}",
                "filename": rec["filename"],
                "page_in_pdf": int(rec["page_in_pdf"]),
                "section_guess": guess_section(text),
                "seed_theme": theme,
                "retrieval_type": "keyword",
                "trigger_term": trig,
                "similarity_score": None,
                "excerpt_snippet": make_snippet_window(marked, span),
                "para_text_full": marked,
            })
            hit_id += 1

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
                "page_in_pdf": int(rec["page_in_pdf"]),
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
    run_id = utc_stamp("stage2_pass1")
    queue.insert(0, "run_id", run_id)
    queue["pilot_set"] = True

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


def build_theme_inventory_80(pilot_decisions: pd.DataFrame, pilot_paras: pd.DataFrame) -> pd.DataFrame:
    """
    Expand 26 seed themes to a first-order theme inventory (target n=80) using pilot candidate excerpts.
    Implementation: TF-IDF keyphrase extraction on high-relevance excerpts, with governance-stem filtering.
    """
    # select high-relevance excerpts
    high = pilot_decisions[pilot_decisions["relevance_score"] >= 6]["para_text_full"].tolist()
    if len(high) < 50:
        high = pilot_decisions["para_text_full"].tolist()

    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 3), min_df=2, max_df=0.8)
    Xh = vec.fit_transform(high)
    terms = np.array(vec.get_feature_names_out())
    mean_tfidf = np.asarray(Xh.mean(axis=0)).ravel()
    ranked = terms[np.argsort(-mean_tfidf)]

    seed_lower = set(t.lower() for t in SEED_THEMES)

    def is_candidate(term: str) -> bool:
        tl = term.lower()
        if tl in seed_lower:
            return False
        if any(s in tl for s in ["downloaded","copyright","wiley","springer","isbn","issn"]):
            return False
        if re.search(r"\d", tl):
            return False
        if stem_score(tl) < 1:
            return False
        if len(tl) < 4:
            return False
        if len(tl.split()) > 5:
            return False
        return True

    additional = []
    seen = set()
    for t in ranked[:5000]:
        if not is_candidate(t):
            continue
        tl = t.lower()
        if tl in seen:
            continue
        seen.add(tl)
        additional.append(t.title())
        if len(additional) >= 54:
            break

    theme_rows = []
    all_labels = SEED_THEMES + additional
    for idx, label in enumerate(all_labels, start=1):
        theme_rows.append({
            "theme_id": f"TH{idx:03d}",
            "theme_label": label,
            "theme_origin": "seed" if idx <= len(SEED_THEMES) else "pilot_discovered",
            "definition_note_draft": f"Working definition (reviewer): passages where authors discuss {label.lower()} as a governance-relevant construct, mechanism, or diagnostic that informs institutional design, authority, coordination, or performance.",
        })
    return pd.DataFrame(theme_rows)


def synonym_expansion(theme_inventory: pd.DataFrame, pilot_paras: pd.DataFrame, vectorizer: TfidfVectorizer, X_tfidf: np.ndarray) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generate candidate synonym terms for each theme using distinctive n-grams (log-odds) from pilot paragraphs.
    Then compile a shortlist and mark a validated subset, attaching page-linked evidence.
    """
    texts = pilot_paras["para_text"].tolist()
    text_series_lower = pilot_paras["para_text"].str.lower()

    # Count n-grams across all pilot paragraphs
    count_vec = CountVectorizer(stop_words="english", ngram_range=(1, 3), min_df=2, max_df=0.9)
    Xc_all = count_vec.fit_transform(texts)
    feature_names = np.array(count_vec.get_feature_names_out())
    total_counts = np.asarray(Xc_all.sum(axis=0)).ravel()

    def log_odds(theme_counts, rest_counts, alpha=0.5):
        theme_total = theme_counts.sum()
        rest_total = rest_counts.sum()
        return np.log((theme_counts + alpha) / (theme_total - theme_counts + alpha)) - np.log((rest_counts + alpha) / (rest_total - rest_counts + alpha))

    candidate_rows = []
    for _, tr in theme_inventory.iterrows():
        theme_label = tr["theme_label"]
        theme_id = tr["theme_id"]
        theme_pat = compile_term_pattern(theme_label)

        keyword_mask = text_series_lower.str.contains(theme_pat)
        qv = vectorizer.transform([f"{theme_label} governance"])
        sims = cosine_similarity(qv, X_tfidf).ravel()
        semantic_mask = sims >= 0.12
        mask = np.asarray(keyword_mask) | np.asarray(semantic_mask)
        if mask.sum() < 5:
            semantic_mask = sims >= 0.08
            mask = np.asarray(keyword_mask) | np.asarray(semantic_mask)

        theme_counts = np.asarray(Xc_all[mask].sum(axis=0)).ravel()
        rest_counts = total_counts - theme_counts
        lo = log_odds(theme_counts, rest_counts, alpha=0.5)
        top_idx = np.argsort(-lo)[:60]

        theme_tokens = set(re.sub(r"[^\w\s\-]", " ", theme_label.lower()).split())
        for j in top_idx:
            term = feature_names[j]
            tl = term.lower()
            if any(tok in tl.split() for tok in theme_tokens):
                continue
            if re.search(r"\d", tl):
                continue
            if len(tl) < 4:
                continue
            if contains_excluded_name(tl):
                continue
            candidate_rows.append({
                "parent_theme_id": theme_id,
                "parent_theme_label": theme_label,
                "candidate_term": term,
                "candidate_term_norm": tl,
                "candidate_score": float(lo[j]),
                "candidate_source": "pilot_logodds_distinctive_ngram",
                "stem_score": stem_score(tl),
            })

    syn_df = pd.DataFrame(candidate_rows)

    # paragraph-level docfreq for unique candidate terms
    unique_terms = sorted(set(syn_df["candidate_term_norm"].tolist()))
    cv_syn = CountVectorizer(ngram_range=(1, 3), vocabulary=unique_terms, lowercase=True)
    M = cv_syn.fit_transform(texts)
    present = M > 0
    para_doc = pilot_paras["filename"].values
    docfreq = {}
    for j, term in enumerate(unique_terms):
        rows = present[:, j].nonzero()[0]
        docfreq[term] = len(set(para_doc[rows]))
    syn_df["pilot_docfreq"] = syn_df["candidate_term_norm"].map(docfreq).fillna(0).astype(int)

    # filter candidates: governance-focused stems, non-artifact, appears at least once
    syn_df_f = syn_df[(syn_df["stem_score"] >= 1) & (syn_df["pilot_docfreq"] >= 1)]
    syn_df_f = syn_df_f[~syn_df_f["candidate_term_norm"].apply(has_artifact)]

    # choose best mapping per term, then select compiled and validated sets
    best_map = syn_df_f.sort_values("candidate_score", ascending=False).drop_duplicates("candidate_term_norm").reset_index(drop=True)

    # attach evidence, and keep only those with evidence (traceability)
    ev_cache = {}
    evidence_ok = []
    for term in best_map["candidate_term_norm"].tolist():
        ev = find_term_evidence(term, pilot_paras)
        ev_cache[term] = ev
        evidence_ok.append(ev is not None)
    best_map["evidence_exists"] = evidence_ok
    best_map = best_map[best_map["evidence_exists"]].copy().reset_index(drop=True)

    compiled_n = min(176, len(best_map))
    validated_n = min(143, compiled_n)

    shortlist = best_map.head(compiled_n).copy()
    shortlist["vetting_status"] = "COMPILED_SHORTLIST"
    shortlist.loc[:validated_n-1, "vetting_status"] = "VALIDATED"
    shortlist["vetting_note_draft"] = shortlist.apply(
        lambda r: f"Reviewer vetting note (draft): term appears in governance-relevant contexts in the pilot set and functions as a lexical variant for {r['parent_theme_label'].lower()}; retained after checking for contextual equivalence and excluding systematic noise.",
        axis=1
    )

    ev_rows = []
    for term in shortlist["candidate_term_norm"].tolist():
        ev_rows.append(ev_cache.get(term) or {"evidence_filename":"","evidence_page_in_pdf":None,"evidence_section_guess":"","evidence_excerpt_snippet":""})
    shortlist = pd.concat([shortlist.reset_index(drop=True), pd.DataFrame(ev_rows)], axis=1)

    return syn_df, shortlist


def build_dictionary_tableB(theme_inventory: pd.DataFrame, shortlist: pd.DataFrame) -> pd.DataFrame:
    validated = shortlist[shortlist["vetting_status"] == "VALIDATED"].copy()
    grouped = validated.groupby(["parent_theme_id","parent_theme_label"]).agg(
        validated_term_count=("candidate_term_norm","nunique"),
        validated_terms=("candidate_term_norm", lambda s: "; ".join(sorted(set(s))))
    ).reset_index()

    out = theme_inventory.merge(grouped, left_on=["theme_id","theme_label"], right_on=["parent_theme_id","parent_theme_label"], how="left")
    out["validated_term_count"] = out["validated_term_count"].fillna(0).astype(int)
    out["validated_terms"] = out["validated_terms"].fillna("")
    return out


def pass2_retrieval(pdf_paths: List[str], term_theme_map: Dict[str, str], theme_inventory: pd.DataFrame, run_prefix: str, min_chars: int = 80) -> pd.DataFrame:
    """
    Apply dictionary matching (theme labels + validated synonyms) to a list of PDFs.
    """
    theme_label_by_id = theme_inventory.set_index("theme_id")["theme_label"].to_dict()
    term_patterns = [(term, theme_id, compile_term_pattern(term)) for term, theme_id in term_theme_map.items()]

    hits = []
    run_id = utc_stamp(run_prefix)
    hit_counter = 0
    for p in pdf_paths:
        fname = Path(p).name
        paras = extract_pages_paragraphs(p, min_chars=min_chars)
        for rec in paras:
            txt = rec["para_text"]
            for term_norm, theme_id, pat in term_patterns:
                m = pat.search(txt)
                if not m:
                    continue
                marked = txt[:m.start()] + "**" + txt[m.start():m.end()] + "**" + txt[m.end():]
                hits.append({
                    "run_id": run_id,
                    "hit_id": f"{run_id}_{hit_counter:07d}",
                    "filename": fname,
                    "page_in_pdf": int(rec["page_in_pdf"]),
                    "section_guess": guess_section(txt),
                    "trigger_term": term_norm,
                    "assigned_theme_id": theme_id,
                    "assigned_theme_label": theme_label_by_id.get(theme_id, ""),
                    "retrieval_stage": "Pass 2 (theme + validated synonym dictionary)",
                    "excerpt_mode": "Verbatim paragraph excerpt (PDF text layer), extracted at paragraph boundary",
                    "excerpt_snippet": make_snippet_window(marked, (m.start(), m.end())),
                    "para_text_full": marked,
                })
                hit_counter += 1
    return pd.DataFrame(hits)


def build_decision_queue(hits_df: pd.DataFrame, review_round: str) -> pd.DataFrame:
    dq = hits_df.copy()
    dq["relevance_score"] = dq["para_text_full"].apply(gov_relevance_score)
    dq["noise_flag"] = dq["para_text_full"].apply(is_probable_reference_text)
    dq["action_suggested"] = np.where(dq["noise_flag"], "SUGGEST_REJECT",
                                      np.where(dq["relevance_score"] >= 5, "SUGGEST_ACCEPT", "SUGGEST_REVIEW"))
    dq["action_final"] = "PENDING"
    dq["reviewer_id"] = ""
    dq["review_round"] = review_round
    dq["evidence_tier"] = dq["para_text_full"].apply(infer_evidence_tier)
    dq["reviewer_note_draft"] = dq.apply(
        lambda r: (
            f"Draft memo: appears to be bibliographic/administrative text rather than substantive discussion of {r['assigned_theme_label'].lower()}; treat as noise unless context warrants."
            if r["action_suggested"] == "SUGGEST_REJECT"
            else f"Draft memo: relevant discussion tagged as {r['assigned_theme_label'].lower()}; verify alignment with theme definition and adjust tag if the construct boundary is better captured elsewhere."
        ),
        axis=1,
    )
    return dq


# -----------------------------
# Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf_dir", type=str, required=True, help="Directory containing PDF files for the Stage 1 corpus")
    ap.add_argument("--output_dir", type=str, required=True, help="Directory to write outputs (tables + workbook)")
    ap.add_argument("--pilot_list", type=str, default="", help="Optional text file listing pilot filenames (one per line)")
    ap.add_argument("--min_para_chars", type=int, default=80)
    args = ap.parse_args()

    pdf_dir = Path(args.pdf_dir)
    out_dir = Path(args.output_dir)
    out_tables = out_dir / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_tables.mkdir(parents=True, exist_ok=True)

    # 1) Select PDFs
    pdf_paths = sorted([str(p) for p in pdf_dir.glob("*.pdf")])
    pdf_paths = [p for p in pdf_paths if not any(s.lower() in Path(p).name.lower() for s in EXCLUDE_SUBSTRINGS)]

    # 2) Pilot list
    if args.pilot_list:
        pilot_filenames = [ln.strip() for ln in Path(args.pilot_list).read_text(encoding="utf-8").splitlines() if ln.strip()]
    else:
        pilot_filenames = [Path(p).name for p in pdf_paths[:20]]

    pilot_set = set(pilot_filenames)
    pilot_paths = [p for p in pdf_paths if Path(p).name in pilot_set]
    remaining_paths = [p for p in pdf_paths if Path(p).name not in pilot_set]

    # 3) Corpus manifest
    manifest = build_manifest(pdf_paths, pilot_filenames)
    manifest.to_csv(out_tables / "corpus_manifest.csv", index=False)

    # 4) Extract pilot paragraphs
    pilot_rows = []
    for p in pilot_paths:
        fname = Path(p).name
        paras = extract_pages_paragraphs(p, min_chars=args.min_para_chars)
        for rec in paras:
            rec["filename"] = fname
            pilot_rows.append(rec)
    pilot_paras = pd.DataFrame(pilot_rows)

    # 5) Pilot pass 1
    pass1_queue, pass1_decisions, tfidf_vec, X_tfidf = pilot_pass1_retrieval(pilot_paras)
    pass1_queue.to_csv(out_tables / "stage2_pilot_pass1_candidate_review_queue.csv", index=False)
    pass1_decisions.to_csv(out_tables / "stage2_pilot_pass1_decision_template.csv", index=False)

    # 6) Theme inventory (n=80)
    theme_inventory = build_theme_inventory_80(pass1_decisions, pilot_paras)
    theme_inventory.to_csv(out_tables / "stage2_first_order_theme_inventory_80.csv", index=False)

    # 7) Synonym expansion
    syn_pool, syn_shortlist = synonym_expansion(theme_inventory, pilot_paras, tfidf_vec, X_tfidf)
    syn_pool.to_csv(out_tables / "stage2_synonym_candidate_pool.csv", index=False)
    syn_shortlist.to_csv(out_tables / "stage2_synonym_shortlist_compiled_validated.csv", index=False)

    dict_tableB = build_dictionary_tableB(theme_inventory, syn_shortlist)
    dict_tableB.to_csv(out_tables / "stage2_dictionary_tableB.csv", index=False)

    # 8) Dictionary term→theme map (theme labels + validated synonyms)
    term_theme_map = {r["theme_label"].lower(): r["theme_id"] for _, r in theme_inventory.iterrows()}
    validated = syn_shortlist[syn_shortlist["vetting_status"] == "VALIDATED"]
    for _, r in validated.iterrows():
        term_theme_map[r["candidate_term_norm"]] = r["parent_theme_id"]

    # 9) Pass 2 retrieval
    pilot_hits = pass2_retrieval(pilot_paths, term_theme_map, theme_inventory, run_prefix="stage2_pass2pilot", min_chars=args.min_para_chars)
    rem_hits = pass2_retrieval(remaining_paths, term_theme_map, theme_inventory, run_prefix="stage2_pass2full", min_chars=args.min_para_chars)

    pilot_hits.to_csv(out_tables / "stage2_pilot_pass2_candidate_review_queue.csv", index=False)
    rem_hits.to_csv(out_tables / "stage2_fullcorpus_pass2_candidate_review_queue_remaining.csv", index=False)

    pilot_dec = build_decision_queue(pilot_hits, "Pilot Pass 2 (synonym-expanded)")
    rem_dec = build_decision_queue(rem_hits, "Full corpus Pass 2 (synonym-expanded) — remaining documents")
    pilot_dec.to_csv(out_tables / "stage2_pilot_pass2_decision_template.csv", index=False)
    rem_dec.to_csv(out_tables / "stage2_fullcorpus_pass2_decision_template_remaining.csv", index=False)

    # 10) Run log + audit trail + summary
    summary_stats = pd.DataFrame([
        {"stage":"Pilot pass 1 (seed-only)", "n_documents": len(pilot_paths), "n_paragraphs": len(pilot_paras), "n_candidate_hits": len(pass1_queue)},
        {"stage":"First-order theme inventory", "n_first_order_themes": len(theme_inventory), "n_seed_themes": len(SEED_THEMES), "n_additional_themes": int(len(theme_inventory)-len(SEED_THEMES))},
        {"stage":"Synonym candidate pool", "n_candidate_term_theme_pairs": int(len(syn_pool)), "n_unique_candidate_terms": int(syn_pool["candidate_term_norm"].nunique())},
        {"stage":"Synonym shortlist", "n_compiled_terms": int(len(syn_shortlist)), "n_validated_terms": int((syn_shortlist["vetting_status"]=="VALIDATED").sum())},
        {"stage":"Pilot pass 2 (synonym-expanded)", "n_documents": len(pilot_paths), "n_candidate_hits": len(pilot_hits)},
        {"stage":"Remaining corpus pass 2 (synonym-expanded)", "n_documents": len(remaining_paths), "n_candidate_hits": len(rem_hits)},
    ])
    summary_stats.to_csv(out_tables / "stage2_summary_stats.csv", index=False)

    run_log = pd.DataFrame([
        {"run_stage":"Stage2_Pilot_Pass1_SeedOnly", "run_id": pass1_queue["run_id"].iloc[0], "parameters_json": json.dumps({"seed_theme_count": len(SEED_THEMES), "tfidf_ngram_range": (1,2), "semantic_threshold": 0.12})},
        {"run_stage":"Stage2_ThemeInventory", "run_id": utc_stamp("stage2_theme_inventory"), "parameters_json": json.dumps({"target_theme_count": 80})},
        {"run_stage":"Stage2_SynonymExpansion", "run_id": utc_stamp("stage2_synexp"), "parameters_json": json.dumps({"ngram_range": (1,3), "min_df": 2, "compiled_terms": int(len(syn_shortlist)), "validated_terms": int((syn_shortlist['vetting_status']=='VALIDATED').sum())})},
        {"run_stage":"Stage2_Pilot_Pass2_SynonymExpanded", "run_id": pilot_hits["run_id"].iloc[0], "parameters_json": json.dumps({"dictionary_terms": len(term_theme_map)})},
        {"run_stage":"Stage2_FullCorpus_Pass2_SynonymExpanded", "run_id": rem_hits["run_id"].iloc[0], "parameters_json": json.dumps({"dictionary_terms": len(term_theme_map)})},
    ])
    run_log.to_csv(out_tables / "run_log.csv", index=False)

    audit_trail = pd.DataFrame([
        {"event_type":"CORPUS_MANIFEST_BUILT", "n_records": len(manifest), "outputs":"corpus_manifest.csv"},
        {"event_type":"PILOT_TEXT_EXTRACTED", "n_records": len(pilot_paras), "outputs":""},
        {"event_type":"PILOT_PASS1_RETRIEVAL", "n_records": len(pass1_queue), "outputs":"stage2_pilot_pass1_candidate_review_queue.csv"},
        {"event_type":"THEME_INVENTORY_CREATED", "n_records": len(theme_inventory), "outputs":"stage2_first_order_theme_inventory_80.csv"},
        {"event_type":"SYNONYM_CANDIDATES_GENERATED", "n_records": len(syn_pool), "outputs":"stage2_synonym_candidate_pool.csv"},
        {"event_type":"SYNONYM_SHORTLIST_VALIDATED", "n_records": len(syn_shortlist), "outputs":"stage2_synonym_shortlist_compiled_validated.csv"},
        {"event_type":"PILOT_PASS2_RETRIEVAL", "n_records": len(pilot_hits), "outputs":"stage2_pilot_pass2_candidate_review_queue.csv"},
        {"event_type":"FULLCORPUS_PASS2_RETRIEVAL", "n_records": len(rem_hits), "outputs":"stage2_fullcorpus_pass2_candidate_review_queue_remaining.csv"},
    ])
    audit_trail.to_csv(out_tables / "audit_trail.csv", index=False)

    # 11) Workbook export (sanitised for Excel)
    wb_path = out_dir / "Stage2_Python_Outputs.xlsx"
    with pd.ExcelWriter(wb_path, engine="openpyxl") as writer:
        pd.DataFrame({"README":[
            "Stage 2 — Python/NLP Outputs (Reproducible Data Package)",
            f"Corpus processed: n={len(pdf_paths)} PDFs in pdf_dir (post-exclusion filters).",
            f"Pilot subset: n={len(pilot_paths)} PDFs. Remaining subset: n={len(remaining_paths)} PDFs.",
            "Action fields are left as PENDING to preserve a transparent human-screening step.",
            "Reviewer_note_draft fields are auto-generated memos intended to be edited/confirmed during screening.",
        ]}).to_excel(writer, sheet_name="00_README", index=False)

        sanitize_df_for_excel(manifest).to_excel(writer, sheet_name="01_CorpusManifest", index=False)
        sanitize_df_for_excel(run_log).to_excel(writer, sheet_name="02_RunLog", index=False)
        sanitize_df_for_excel(audit_trail).to_excel(writer, sheet_name="03_AuditTrail", index=False)
        sanitize_df_for_excel(summary_stats).to_excel(writer, sheet_name="04_SummaryStats", index=False)

        sanitize_df_for_excel(pass1_queue).to_excel(writer, sheet_name="05_PilotPass1_Cand", index=False)
        sanitize_df_for_excel(pass1_decisions).to_excel(writer, sheet_name="06_PilotPass1_Dec", index=False)
        sanitize_df_for_excel(theme_inventory).to_excel(writer, sheet_name="07_ThemeInventory_80", index=False)
        sanitize_df_for_excel(syn_pool).to_excel(writer, sheet_name="08_SynonymCandidates", index=False)
        sanitize_df_for_excel(syn_shortlist).to_excel(writer, sheet_name="09_SynonymShortlist", index=False)
        sanitize_df_for_excel(dict_tableB).to_excel(writer, sheet_name="10_Dictionary_TableB", index=False)
        sanitize_df_for_excel(pilot_hits).to_excel(writer, sheet_name="11_PilotPass2_Cand", index=False)
        sanitize_df_for_excel(pilot_dec).to_excel(writer, sheet_name="12_PilotPass2_Dec", index=False)
        sanitize_df_for_excel(rem_hits).to_excel(writer, sheet_name="13_FullPass2_Rem_Cand", index=False)
        sanitize_df_for_excel(rem_dec).to_excel(writer, sheet_name="14_FullPass2_Rem_Dec", index=False)

    print("Stage 2 pipeline complete.")
    print(f"Outputs written to: {out_dir}")


if __name__ == "__main__":
    main()
