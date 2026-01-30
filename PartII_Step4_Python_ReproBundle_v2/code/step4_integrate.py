"""Part II — Step 4: Data integration, validation, and preparation for analysis.

This script deterministically integrates the Step 3 traceability outputs into a single,
analysis-ready IGO attribute matrix (long + wide formats), plus validation diagnostics.

Inputs
------
- Step 3 Excel bundle (.xlsx) with at least these sheets:
    * 05_TraceabilityLong
    * 04_DecisionLog
    * 03_CandidateReviewQueue
- Config JSON (schema + attribute label mapping)

Outputs
-------
- PartII_Step4_DataIntegration_BUNDLE.xlsx (multi-sheet)
- CSV exports (matrix_long, matrix_wide, coverage/missingness, integrity checks, orphans, run_log)
- Optional figure: evidence volume by attribute

Notes
-----
The script adds no new evidence. It only (i) enforces schema, (ii) canonicalises identifiers,
(iii) collapses retained evidence into one value per IGO×attribute, and (iv) generates checks.
"""

import argparse
import json
import os
import hashlib
import datetime
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import networkx as nx
from dateutil import tz

def md5_file(path, chunk_size=8192):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()

def summarize_group(g: pd.DataFrame) -> pd.Series:
    cell_texts = g["matrix_cell_text_full"].dropna().unique().tolist()
    cell_text = cell_texts[0] if cell_texts else ""
    tier_counts = g["evidence_tier"].value_counts().to_dict()
    n_sources = g["source_title"].replace({"-": np.nan, "—": np.nan}).nunique(dropna=True)

    anchors = g["article_section_page"].replace({"-": np.nan, "—": np.nan, "Not specified": np.nan, "Not specified (see narrative/citations in cell)": np.nan}).dropna().astype(str).unique().tolist()
    pages = g["page_in_pdf"].replace({"-": np.nan, "—": np.nan}).dropna().astype(str).unique().tolist()
    uris = g["source_uri"].replace({"-": np.nan, "—": np.nan}).dropna().astype(str).unique().tolist()

    doc_fam = g["doc_family_inferred"].replace({"-": np.nan, "—": np.nan}).dropna().value_counts().to_dict()
    primary_doc_family = max(doc_fam.items(), key=lambda kv: kv[1])[0] if doc_fam else ""

    return pd.Series({
        "matrix_cell_text": cell_text,
        "n_evidence_records": int(len(g)),
        "n_unique_sources": int(n_sources),
        "anchors_compact": "; ".join(anchors[:8]),
        "pages_compact": "; ".join(pages[:8]),
        "uris_compact": "; ".join(uris[:4]),
        "primary_doc_family": primary_doc_family,
        "record_ids": ";".join(g["record_id"].astype(str).tolist()),
        "n_tier_definition": int(tier_counts.get("Definition/Identification", 0)),
        "n_tier_explanation": int(tier_counts.get("Explanation/Elaboration", 0)),
        "n_tier_substantiation": int(tier_counts.get("Substantiation/References", 0)),
    })

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step3_bundle", required=True, help="Path to Step 3 Excel bundle (.xlsx)")
    ap.add_argument("--config", required=True, help="Path to config JSON (schema + labels)")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--make_figure", action="store_true", help="If set, writes a simple evidence-volume figure.")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    with open(args.config, "r") as f:
        cfg = json.load(f)

    attr_codes = cfg["attribute_codes"]
    attr_labels = cfg["attribute_labels"]

    trace = pd.read_excel(args.step3_bundle, sheet_name="05_TraceabilityLong")
    _decision = pd.read_excel(args.step3_bundle, sheet_name="04_DecisionLog")
    _cand = pd.read_excel(args.step3_bundle, sheet_name="03_CandidateReviewQueue")

    # Retained evidence records (Accept + Re-tag)
    trace = trace[trace["coder_action"].isin(["Accept", "Re-tag"])].copy()
    trace["attribute_code_final"] = trace["attribute_code_final"].astype(str)
    trace["igo"] = trace["igo"].astype(str)

    valid_mask = trace["attribute_code_final"].isin(attr_codes) & trace["igo"].ne("") & trace["igo"].ne("nan")
    orphans = trace.loc[~valid_mask].copy()
    orphans["orphan_reason"] = np.where(~trace["attribute_code_final"].isin(attr_codes), "Invalid attribute_code_final", "Missing IGO")
    trace = trace.loc[valid_mask].copy()

    cell_long = trace.groupby(["igo", "attribute_code_final"]).apply(summarize_group).reset_index()
    cell_long["attribute_label"] = cell_long["attribute_code_final"].map(attr_labels)

    # Coverage table
    coverage = cell_long[["igo","attribute_code_final","n_evidence_records","n_unique_sources","n_tier_definition","n_tier_explanation","n_tier_substantiation"]].copy()
    coverage["is_missing_cell"] = (coverage["n_evidence_records"]==0) | (coverage["n_tier_definition"]!=1) | (coverage["n_tier_explanation"]!=1)

    # Wide matrix
    wide = cell_long.pivot(index="igo", columns="attribute_code_final", values="matrix_cell_text").reset_index()
    for c in attr_codes:
        if c not in wide.columns:
            wide[c] = np.nan
    wide = wide[["igo"] + attr_codes]
    wide_named = wide.rename(columns={"igo":"Institution", **{c:attr_labels[c] for c in attr_codes}})

    # Integrity checks
    checks=[]
    n_igos = cell_long["igo"].nunique()
    expected_cells = n_igos * len(attr_codes)
    n_bad = (trace.groupby(["igo","attribute_code_final"])["matrix_cell_text_full"].nunique() > 1).sum()

    # networkx sanity check: bipartite matrix connectivity
    B = nx.Graph()
    B.add_nodes_from(cell_long["igo"].unique().tolist(), bipartite="igo")
    B.add_nodes_from(attr_codes, bipartite="attr")
    for _, r in cell_long.iterrows():
        if str(r["matrix_cell_text"]).strip() != "":
            B.add_edge(r["igo"], r["attribute_code_final"])
    n_components = nx.number_connected_components(B)

    checks.append({"check":"n_cells", "value": int(len(cell_long)), "expected": int(expected_cells),
                   "status":"PASS" if len(cell_long)==expected_cells else "FAIL",
                   "notes":"One integrated cell per IGO×attribute."})
    checks.append({"check":"conflicting cell text within IGO×attribute", "value": int(n_bad), "expected": 0,
                   "status":"PASS" if n_bad==0 else "FAIL",
                   "notes":"Flags inconsistent consolidation."})
    checks.append({"check":"orphan retained evidence", "value": int(len(orphans)), "expected": 0,
                   "status":"PASS" if len(orphans)==0 else "FAIL",
                   "notes":"Retained evidence not mapped to the matrix schema."})
    checks.append({"check":"bipartite matrix connectivity (networkx)", "value": int(n_components), "expected": 1,
                   "status":"PASS" if n_components==1 else "FAIL",
                   "notes":"IGO nodes + attribute nodes should form one connected component when the matrix is complete."})
    integrity = pd.DataFrame(checks)

    # Run log (ISO timestamp)
    run_id = datetime.datetime.now(tz=tz.UTC).strftime("P2S4_%Y%m%dT%H%M%SZ")
    run_log = pd.DataFrame([{
        "run_id": run_id,
        "pipeline_stage": "PartII",
        "pipeline_step": "Step4_DataIntegration",
        "input_step3_bundle": os.path.basename(args.step3_bundle),
        "input_step3_md5": md5_file(args.step3_bundle),
        "n_igos": int(n_igos),
        "n_attributes": int(len(attr_codes)),
        "n_cells": int(len(cell_long)),
        "n_retained_evidence": int(len(trace)),
        "timestamp_utc": run_id.split("_",1)[1],
        "notes": "Deterministic integration from Step 3 outputs; no new evidence added."
    }])

    # Export bundle workbook
    bundle_xlsx = os.path.join(args.outdir, "PartII_Step4_DataIntegration_BUNDLE.xlsx")
    with pd.ExcelWriter(bundle_xlsx, engine="openpyxl") as writer:
        summary = pd.DataFrame({
            "metric":["n_igos","n_attributes","attribute_codes","n_retained_evidence","n_cells","input_step3_bundle"],
            "value":[int(n_igos), int(len(attr_codes)), ", ".join(attr_codes), int(len(trace)), int(len(cell_long)), os.path.basename(args.step3_bundle)]
        })
        summary.to_excel(writer, sheet_name="00_SummaryStats", index=False)
        cell_long.to_excel(writer, sheet_name="04_Matrix_Long", index=False)
        wide_named.to_excel(writer, sheet_name="05_Matrix_Wide", index=False)
        coverage.to_excel(writer, sheet_name="06_Coverage_Missingness", index=False)
        integrity.to_excel(writer, sheet_name="07_Integrity_Checks", index=False)
        orphans.to_excel(writer, sheet_name="08_Orphan_Evidence", index=False)
        run_log.to_excel(writer, sheet_name="02_RunLog", index=False)

    # CSV exports
    cell_long.to_csv(os.path.join(args.outdir,"step4_matrix_long.csv"), index=False)
    wide_named.to_csv(os.path.join(args.outdir,"step4_matrix_wide.csv"), index=False)
    coverage.to_csv(os.path.join(args.outdir,"step4_coverage_missingness.csv"), index=False)
    integrity.to_csv(os.path.join(args.outdir,"step4_integrity_checks.csv"), index=False)
    orphans.to_csv(os.path.join(args.outdir,"step4_orphan_evidence.csv"), index=False)
    run_log.to_csv(os.path.join(args.outdir,"step4_run_log.csv"), index=False)

    # Optional figure
    if args.make_figure:
        fig_path = os.path.join(args.outdir, "Figure_Step4_EvidenceVolume_byAttribute.png")
        (coverage.groupby("attribute_code_final")["n_evidence_records"].sum().reindex(attr_codes)).plot(kind="bar")
        plt.ylabel("Retained evidence records (count)")
        plt.xlabel("Attribute code")
        plt.tight_layout()
        plt.savefig(fig_path, dpi=200)
        plt.close()

    print("Wrote:", bundle_xlsx)

if __name__ == "__main__":
    main()
