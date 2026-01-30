"""Segment extracted page text into paragraph-level units (within-page)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import pandas as pd

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle_root", default=".", help="Root of the Step 2 bundle.")
    args = ap.parse_args()

    bundle_root = Path(args.bundle_root)
    jsonl_dir = bundle_root / "data" / "interim" / "page_text_jsonl"
    out_paras = bundle_root / "outputs" / "tables" / "step2_corpus_paragraphs.csv"

    rows = []
    for jsonl_path in sorted(jsonl_dir.glob("DOC_*_pages.jsonl")):
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                doc_id = rec["doc_id"]
                page = rec["page_number"]
                text = rec.get("text","") or ""
                if not text:
                    continue
                paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
                for j, para in enumerate(paras, start=1):
                    rows.append({
                        "para_id": f"{doc_id}_P{page:04d}_{j:02d}",
                        "doc_id": doc_id,
                        "page_number": page,
                        "para_index_on_page": j,
                        "para_char_count": len(para),
                        "para_text": para,
                    })

    pd.DataFrame(rows).to_csv(out_paras, index=False)

if __name__ == "__main__":
    main()
