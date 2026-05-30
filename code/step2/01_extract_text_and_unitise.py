"""Part II — Step 2: Extract page-anchored text and unitise into paragraph units.

Input:
  - data/processed/igo_document_manifest_v1.csv
  - data/raw/igo_documents/*.pdf

Outputs:
  - data/interim/corpus_pages_v1.csv.gz
  - data/interim/corpus_paragraphs_v1.csv.gz
  - data/interim/extraction_log_v1.csv

The unit of retrieval for downstream steps is the paragraph (within a page).
"""

from __future__ import annotations
import re
import hashlib
import unicodedata
from pathlib import Path
import pandas as pd

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "processed" / "igo_document_manifest_v1.csv"
OUT_PAGES = ROOT / "data" / "interim" / "corpus_pages_v1.csv.gz"
OUT_PARAS = ROOT / "data" / "interim" / "corpus_paragraphs_v1.csv.gz"
OUT_LOG = ROOT / "data" / "interim" / "extraction_log_v1.csv"

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join([ln.strip() for ln in text.split("\n")])
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def main() -> None:
    manifest = pd.read_csv(MANIFEST)
    page_rows = []
    para_rows = []
    log_rows = []
    para_counter = 0

    for _, r in manifest.iterrows():
        if str(r.get("file_ext", "")).lower() != ".pdf":
            continue
        doc_id = r["doc_id"]
        igo_id = r.get("igo_id", None)
        rel = Path(r["bundle_relpath"])
        path = ROOT / rel

        try:
            doc = fitz.open(path)
        except Exception as e:
            log_rows.append({"doc_id": doc_id, "filename": r["filename"], "status": "open_error", "error": str(e)})
            continue

        for pno in range(doc.page_count):
            try:
                text = doc.load_page(pno).get_text("text")
            except Exception as e:
                log_rows.append({"doc_id": doc_id, "filename": r["filename"], "page_number": pno + 1,
                                 "status": "page_error", "error": str(e)})
                continue

            text_n = normalize_text(text)
            page_rows.append({
                "doc_id": doc_id,
                "igo_id": igo_id,
                "page_number": pno + 1,
                "char_count": len(text_n),
                "text_sha256": hashlib.sha256(text_n.encode("utf-8")).hexdigest() if text_n else None,
            })

            if text_n:
                paras = re.split(r"\n\s*\n+", text_n)
                para_idx = 0
                for para in paras:
                    para = para.strip()
                    if len(para) < 40:
                        continue
                    para_idx += 1
                    para_counter += 1
                    para_rows.append({
                        "para_id": f"P{para_counter:07d}",
                        "doc_id": doc_id,
                        "igo_id": igo_id,
                        "page_number": pno + 1,
                        "para_index_in_page": para_idx,
                        "para_text": para,
                        "para_char_count": len(para),
                        "para_sha256": hashlib.sha256(para.encode("utf-8")).hexdigest(),
                    })

        doc.close()

    pages = pd.DataFrame(page_rows)
    paras = pd.DataFrame(para_rows)
    log = pd.DataFrame(log_rows)

    OUT_PAGES.parent.mkdir(parents=True, exist_ok=True)
    pages.to_csv(OUT_PAGES, index=False, compression="gzip")
    paras.to_csv(OUT_PARAS, index=False, compression="gzip")
    log.to_csv(OUT_LOG, index=False)

    print(f"Wrote pages: {len(pages)} -> {OUT_PAGES}")
    print(f"Wrote paragraphs: {len(paras)} -> {OUT_PARAS}")
    print(f"Wrote log: {len(log)} -> {OUT_LOG}")

if __name__ == "__main__":
    main()
