"""Part II — Step 2: Build an IGO document manifest from raw PDFs.

This script scans `data/raw/igo_documents/` and assigns stable doc_ids and
provisional IGO mappings based on a lightweight alias table. It then writes:

  - data/processed/igo_document_manifest_v1.csv

Notes
-----
* The IGO mapping here is intentionally conservative and designed for reproducibility:
  it is a deterministic heuristic, not an authority on institutional identity.
* If you adjust file names or add documents, re-run this script to refresh the manifest.
"""

from __future__ import annotations
import re
import hashlib
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]  # bundle root
RAW_DIR = ROOT / "data" / "raw" / "igo_documents"
IGO_MASTER = ROOT / "data" / "processed" / "igo_master_48.csv"
OUT_PATH = ROOT / "data" / "processed" / "igo_document_manifest_v1.csv"

INSTRUMENT_KW = [
    "constitution","convention","statute","agreement","resolution","rules",
    "charter","articles of agreement","basic","principles","procedures","operating",
]

# Minimal alias map for matching filenames -> IGO ids.
# Extend as needed; keep deterministic.
IGO_ALIASES = {
    "WTO": ["wto", "world trade organization", "world trade organisation", "marrakesh"],
    "WBG": ["world bank", "ibrd"],
    "IPCC": ["ipcc"],
    "UNFCCC": ["unfccc", "framework convention on climate change", "climate change secretariat"],
    "IOM": ["iom", "international organization for migration"],
    "UNDP": ["undp"],
    "UNICEF": ["unicef"],
    "UNODC": ["unodc"],
    "UNOOSA": ["unoosa"],
    "WFP": ["wfp", "world food programme", "world food program"],
    "MINAMATA": ["minamata"],
    "IPBES": ["ipbes"],
    "UNGC": ["global compact"],
    "UNCCD": ["unccd"],
    "CBD": ["cbd", "biodiversity"],
    "CITES": ["cites"],
    "CMS": ["migratory species"],
    "RAMSAR": ["ramsar"],
    "ITU": ["itu"],
    "IHO": ["iho"],
    "FAO": ["fao"],
    "IAEA": ["iaea"],
    "ICES": ["ices"],
    "ILO": ["ilo"],
    "IMF": ["imf"],
    "IMO": ["imo", "intergovernmental maritime consultative"],
    "ISA": ["isa", "seabed authority", "part-xi", "uncclos", "unclos"],
    "OECD": ["oecd"],
    "OHCHR": ["ohchr"],
    "UNCTAD": ["unctad"],
    "UN_DOALOS": ["daolos", "doalos", "law of the sea"],
    "UN_HABITAT": ["un habitat", "habitat"],
    "UNFPA": ["unfpa", "population fund"],
    "UN_WOMEN": ["un women"],
    "UNDRR": ["undrr"],
    "UNEP": ["unep"],
    "UNIDO": ["unido"],
    "UNOPS": ["unops"],
    "UNRISD": ["unrisd"],
    "UNWTO": ["unwto", "world tourism"],
    "WHO": ["who"],
    "WIPO": ["wipo"],
    "WMO": ["wmo"],
    "IOC": ["ioc", "intergovernmental oceanographic commission"],
    "UNHCR_OHCHR": ["high commissioner for refugees", "unhcr"],
}

def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def classify_doc_family(filename: str) -> tuple[str, str]:
    lname = filename.lower()
    if "strategic" in lname or "strategy" in lname or "annual report" in lname:
        return "Strategic / operational", "Strategic plan / report"
    if "constitution" in lname:
        return "Foundational / legal", "Constitution"
    if "convention" in lname:
        return "Foundational / legal", "Convention / treaty"
    if "statute" in lname:
        return "Foundational / legal", "Statute"
    if "articles of agreement" in lname:
        return "Foundational / legal", "Articles of agreement"
    if "agreement" in lname:
        return "Foundational / legal", "Agreement"
    if "resolution" in lname:
        return "Foundational / legal", "Resolution / decision"
    if "rules" in lname:
        return "Foundational / legal", "Rules / regulations"
    if "charter" in lname:
        return "Foundational / legal", "Charter"
    if "principles" in lname or "procedures" in lname or "operating" in lname:
        return "Foundational / legal", "Procedures / principles"
    return "Other / governance instrument", "Document"

def match_igo_id(filename: str, igo_ids: set[str]) -> str | None:
    lname = filename.lower()
    # Exact id hits (helps for short ids like WTO, IMO)
    for igo_id in igo_ids:
        if re.search(r"(^|[^a-z0-9])" + re.escape(igo_id.lower()) + r"([^a-z0-9]|$)", lname):
            return igo_id
    # Alias hits
    for igo_id, aliases in IGO_ALIASES.items():
        if igo_id not in igo_ids:
            continue
        for a in aliases:
            if a in lname:
                return igo_id
    return None

def main() -> None:
    igo_master = pd.read_csv(IGO_MASTER)
    igo_ids = set(igo_master["igo_id"].astype(str).tolist())

    files = sorted([p for p in RAW_DIR.iterdir() if p.is_file() and p.suffix.lower() in [".pdf", ".doc", ".docx"]],
                   key=lambda p: p.name.lower())

    rows = []
    for i, p in enumerate(files, start=1):
        family, doc_type = classify_doc_family(p.name)
        igo_id = match_igo_id(p.name, igo_ids)
        rows.append({
            "doc_id": f"DOC_{i:04d}",
            "igo_id": igo_id,
            "filename": p.name,
            "bundle_relpath": f"data/raw/igo_documents/{p.name}",
            "file_ext": p.suffix.lower(),
            "file_bytes": p.stat().st_size,
            "sha256": sha256_file(p),
            "doc_family": family,
            "doc_type": doc_type,
        })

    df = pd.DataFrame(rows)
    df.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(df)} rows to {OUT_PATH}")

if __name__ == "__main__":
    main()
