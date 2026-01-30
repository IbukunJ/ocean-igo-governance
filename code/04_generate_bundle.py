"""Generate coverage summaries and the Excel bundle for Step 2."""

from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

def build_table_f() -> pd.DataFrame:
    return pd.DataFrame([
        {"attribute_code":"YE","attribute":"Year of Establishment","primary_evidence":"Founding instrument (treaty/charter/constitution/establishing resolution); basic texts","secondary_evidence":"Official organisational portal (history page); annual report front matter","notes":"Use earliest constitutive act; record year and citation anchor (article/preamble if present)."},
        {"attribute_code":"SJ","attribute":"Spatial Jurisdiction","primary_evidence":"Founding instrument scope/jurisdiction clauses; convention applicability articles","secondary_evidence":"Programme statutes; rules of procedure describing geographic remit","notes":"Code global/ABNJ/regional scope as defined; retain verbatim scope language."},
        {"attribute_code":"SMJ","attribute":"Subject Matter Jurisdiction","primary_evidence":"Mandate/objective articles; competence clauses; annexes defining thematic remit","secondary_evidence":"Strategic plans and programme descriptions (where founding texts are broad)","notes":"Capture thematic remit as it conditions comparison; do not treat issue domains as governance mechanisms."},
        {"attribute_code":"SoJ","attribute":"Source of Jurisdiction","primary_evidence":"Treaty/charter/statute article citations; UNGA/ECOSOC/Conference resolutions establishing body","secondary_evidence":"Authoritative treaty collections or basic documents reproducing legal texts","notes":"Record formal legal basis with article/section identifiers and page anchors."},
        {"attribute_code":"DO","attribute":"Defined Objectives","primary_evidence":"Mandate objectives clauses; preambles; strategic frameworks that specify goals","secondary_evidence":"Annual reports and programme documents that formalise objectives","notes":"Prefer formally adopted objective statements; where absent, use the most authoritative strategic articulation and justify."},
        {"attribute_code":"STR","attribute":"Strategies","primary_evidence":"Strategic plans; implementation frameworks; programmes of work; action plans","secondary_evidence":"Annual reports; flagship programme documents","notes":"Code instrument mix and strategic modalities, with time-bounded references."},
        {"attribute_code":"IIR","attribute":"Inter-Institutional Relationships","primary_evidence":"MoUs; partnership agreements; joint workplans; formal cooperation clauses","secondary_evidence":"Annual reports listing partnerships; inter-agency platform documentation","notes":"Distinguish formal from informal relationships; record partner, mechanism, and year where available."},
        {"attribute_code":"VC","attribute":"Vertical Coordination","primary_evidence":"Subsidiary-body statutes; national focal point arrangements; implementation mechanisms","secondary_evidence":"Regional programme structures; country office frameworks; national reporting systems","notes":"Capture cross-level linkage mechanisms; retain evidence for national/regional uptake pathways."},
        {"attribute_code":"HC","attribute":"Horizontal Coordination","primary_evidence":"Inter-agency committees; joint programmes; coordination platforms; shared standards bodies","secondary_evidence":"Operational portals describing coordination; annual report cooperation sections","notes":"Capture same-level coordination across IGOs and sectors; record mechanism and membership where available."},
    ])

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle_root", default=".", help="Root of the Step 2 bundle.")
    args = ap.parse_args()

    bundle_root = Path(args.bundle_root)
    docs = pd.read_csv(bundle_root / "outputs" / "tables" / "step2_corpus_documents.csv")
    quality = pd.read_csv(bundle_root / "outputs" / "tables" / "step2_extraction_quality_report.csv")
    paras = pd.read_csv(bundle_root / "outputs" / "tables" / "step2_corpus_paragraphs.csv")

    docs["igo_id"] = docs["igo_id"].astype(str).str.lower().str.replace("-", "_")

    cov = docs.groupby(["igo_id","igo_name"]).agg(
        n_docs=("doc_id","nunique"),
        n_pages=("page_count","sum"),
        n_docs_low_text=("doc_id", lambda s: 0),
    ).reset_index()

    # mark low-text documents per IGO
    low = quality[quality["quality_flag"].astype(str).str.contains("low_text_density", na=False)]
    low_docs = docs.merge(low[["doc_id"]], on="doc_id", how="inner")
    if not low_docs.empty:
        low_counts = low_docs.groupby("igo_id").size().reset_index(name="n_docs_low_text")
        cov = cov.drop(columns=["n_docs_low_text"]).merge(low_counts, on="igo_id", how="left").fillna({"n_docs_low_text":0})

    cov.to_csv(bundle_root / "outputs" / "tables" / "step2_igo_document_coverage.csv", index=False)

    # Excel bundle
    out_xlsx = bundle_root / "PartII_Step2_DocumentCorpus_BUNDLE_v1.xlsx"
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as w:
        docs.to_excel(w, sheet_name="02_DocManifest", index=False)
        quality.to_excel(w, sheet_name="03_ExtractionQuality", index=False)
        paras.head(5000).to_excel(w, sheet_name="04_ParagraphUnits_sample", index=False)  # sample for readability
        cov.to_excel(w, sheet_name="05_IGOCoverage", index=False)
        build_table_f().to_excel(w, sheet_name="06_EvidenceHierarchy_TableF", index=False)

if __name__ == "__main__":
    main()
