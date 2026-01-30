"""Build a document manifest from the seed mapping and raw files."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import pandas as pd
import fitz  # PyMuPDF

def sha256_file(path: str, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def count_pages(path: str) -> float:
    if Path(path).suffix.lower() != ".pdf":
        return float("nan")
    try:
        with fitz.open(path) as doc:
            return doc.page_count
    except Exception:
        return float("nan")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle_root", default=".", help="Root of the Step 2 bundle.")
    args = ap.parse_args()

    bundle_root = Path(args.bundle_root)
    seed_path = bundle_root / "data" / "processed" / "step2_doc_manifest_seed.csv"
    raw_dir = bundle_root / "data" / "raw" / "igo_documents"
    out_path = bundle_root / "outputs" / "tables" / "step2_corpus_documents.csv"

    seed = pd.read_csv(seed_path)
    rows = []
    for _, r in seed.iterrows():
        fn = r["filename"]
        fp = raw_dir / fn
        rows.append({
            **r.to_dict(),
            "local_path": str(fp),
            "file_ext": fp.suffix.lower(),
            "file_bytes": fp.stat().st_size if fp.exists() else float("nan"),
            "sha256": sha256_file(str(fp)) if fp.exists() else "",
            "page_count": count_pages(str(fp)) if fp.exists() else float("nan"),
        })
    docs = pd.DataFrame(rows)
    docs.to_csv(out_path, index=False)

if __name__ == "__main__":
    main()
