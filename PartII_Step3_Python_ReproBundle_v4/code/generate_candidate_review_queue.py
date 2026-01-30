import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import re
from sklearn.feature_extraction.text import TfidfVectorizer

def split_phrases(s: str):
    parts = re.split(r"[;,]", str(s))
    return [p.strip().strip('"').strip("'") for p in parts if p.strip()]

def build_indicator_queries(indicator_matrix: pd.DataFrame):
    # Expect columns: indicator_id, indicator_label, attribute_code, keyword_phrases
    queries = {}
    for _, r in indicator_matrix.iterrows():
        q = f"{r.get('attribute_code','')} {r.get('indicator_label','')} {r.get('keyword_phrases','')}"
        queries[r["indicator_id"]] = q.strip()
    return queries

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paragraphs_csv", required=True, help="Step 2 extracted paragraphs (e.g., step2_corpus_paragraphs.csv)")
    ap.add_argument("--indicator_csv", required=True, help="Indicator matrix (Table XX processed)")
    ap.add_argument("--out_csv", required=True, help="Output candidate review queue (machine-surfaced)")
    ap.add_argument("--max_words_snippet", type=int, default=50)
    args = ap.parse_args()

    paras = pd.read_csv(args.paragraphs_csv)
    ind = pd.read_csv(args.indicator_csv)

    # Build regex patterns
    # If regex_or_pattern exists, use it; otherwise construct a simple OR-pattern from keyword_phrases.
    patterns = {}
    for _, r in ind.iterrows():
        iid = r["indicator_id"]
        if "regex_or_pattern" in r and isinstance(r["regex_or_pattern"], str) and r["regex_or_pattern"].strip():
            patterns[iid] = re.compile(r["regex_or_pattern"], flags=re.IGNORECASE)
        else:
            phrases = split_phrases(r.get("keyword_phrases",""))
            pat = "(?:" + "|".join([re.escape(p).replace(r"\ ", r"\s+") for p in phrases]) + ")"
            patterns[iid] = re.compile(pat, flags=re.IGNORECASE)

    # Prepare snippets
    def make_snippet(text):
        words = str(text).split()
        return " ".join(words[:args.max_words_snippet])

    paras["snippet"] = paras["paragraph_text"].apply(make_snippet)

    # Candidate hits by regex matching
    rows = []
    for _, p in paras.iterrows():
        txt = str(p["paragraph_text"])
        for iid, pat in patterns.items():
            m = pat.search(txt)
            if m:
                rows.append({
                    "doc_id": p.get("doc_id",""),
                    "igo": p.get("igo",""),
                    "page_start": p.get("page_start",""),
                    "page_end": p.get("page_end",""),
                    "trace_key": p.get("trace_key",""),
                    "indicator_id": iid,
                    "trigger_term": m.group(0),
                    "snippet_<=50w": p["snippet"],
                })

    cand = pd.DataFrame(rows)
    if cand.empty:
        cand.to_csv(args.out_csv, index=False)
        print("No candidate hits produced (check indicator patterns and paragraph text).")
        return

    # TF-IDF cosine similarity scoring for ranking / diagnostics
    queries = build_indicator_queries(ind)
    all_texts = cand["snippet_<=50w"].fillna("").astype(str).tolist() + list(queries.values())
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1,2), min_df=1)
    tfidf_all = vectorizer.fit_transform(all_texts)
    tfidf_snip = tfidf_all[:len(cand)]
    tfidf_q = tfidf_all[len(cand):]
    query_ids = list(queries.keys())
    q_index = {iid:i for i,iid in enumerate(query_ids)}

    scores = []
    for i, iid in enumerate(cand["indicator_id"]):
        qi = q_index.get(iid, None)
        if qi is None:
            scores.append(np.nan)
        else:
            scores.append(float(tfidf_snip[i].multiply(tfidf_q[qi]).sum()))
    cand["tfidf_cosine"] = scores
    cand.sort_values(["indicator_id","tfidf_cosine"], ascending=[True, False], inplace=True)
    cand.to_csv(args.out_csv, index=False)
    print(f"Wrote {len(cand)} candidate rows to {args.out_csv}")

if __name__ == "__main__":
    main()