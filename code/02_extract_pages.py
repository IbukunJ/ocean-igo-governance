"""Extract page-anchored text from PDFs (JSONL per document) and build a page index."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pandas as pd
import fitz  # PyMuPDF

from settings import clean_page_text

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle_root", default=".", help="Root of the Step 2 bundle.")
    args = ap.parse_args()

    bundle_root = Path(args.bundle_root)
    docs_path = bundle_root / "outputs" / "tables" / "step2_corpus_documents.csv"
    out_pages = bundle_root / "outputs" / "tables" / "step2_corpus_pages.csv"
    jsonl_dir = bundle_root / "data" / "interim" / "page_text_jsonl"
    jsonl_dir.mkdir(parents=True, exist_ok=True)

    docs = pd.read_csv(docs_path)
    page_rows = []
    quality_rows = []

    for _, d in docs.iterrows():
        doc_id = d["doc_id"]
        local_path = d["local_path"]
        ext = str(d.get("file_ext","")).lower()
        if ext != ".pdf" or not os.path.exists(local_path):
            continue

        try:
            pdf = fitz.open(local_path)
            page_count = pdf.page_count
        except Exception as e:
            quality_rows.append({
                "doc_id": doc_id,
                "filename": d["filename"],
                "extraction_method": "pymupdf_open_error",
                "page_count": float("nan"),
                "pages_with_text": float("nan"),
                "empty_pages": float("nan"),
                "pct_pages_with_text": float("nan"),
                "page_load_errors": float("nan"),
                "quality_flag": f"open_error:{type(e).__name__}",
            })
            continue

        pages_with_text = 0
        load_errors = 0
        out_jsonl = jsonl_dir / f"{doc_id}_pages.jsonl"
        with out_jsonl.open("w", encoding="utf-8") as f:
            for i in range(page_count):
                try:
                    page = pdf.load_page(i)
                    raw = page.get_text("text") or ""
                except Exception:
                    load_errors += 1
                    raw = ""
                cleaned = clean_page_text(raw)
                char_count = len(cleaned)
                if char_count > 50:
                    pages_with_text += 1
                text_sha1 = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()
                f.write(json.dumps({
                    "doc_id": doc_id,
                    "page_number": i + 1,
                    "text": cleaned,
                    "char_count": char_count,
                    "text_sha1": text_sha1,
                }, ensure_ascii=False) + "\n")
                page_rows.append({
                    "doc_id": doc_id,
                    "page_number": i + 1,
                    "char_count": char_count,
                    "text_sha1": text_sha1,
                })

        empty_pages = page_count - pages_with_text
        pct = pages_with_text / page_count if page_count else float("nan")
        flag = "ok"
        if pct < 0.5:
            flag = "low_text_density"
        if load_errors > 0:
            flag = f"{flag}|page_load_errors" if flag != "ok" else "page_load_errors"

        quality_rows.append({
            "doc_id": doc_id,
            "filename": d["filename"],
            "extraction_method": "pymupdf_text",
            "page_count": page_count,
            "pages_with_text": pages_with_text,
            "empty_pages": empty_pages,
            "pct_pages_with_text": round(pct, 4),
            "page_load_errors": load_errors,
            "quality_flag": flag,
        })

        pdf.close()

    pd.DataFrame(page_rows).to_csv(out_pages, index=False)
    pd.DataFrame(quality_rows).to_csv(bundle_root / "outputs" / "tables" / "step2_extraction_quality_report.csv", index=False)

if __name__ == "__main__":
    main()
