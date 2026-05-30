"""
01_integrate_matrix.py

Builds reproducible integration artefacts for Part II.

Inputs (processed):
- partII_traceability_long_file.csv (retained evidence with page-linked provenance)
- final_matrix_target.xlsx (target matrix layout; treated as an output benchmark, not as evidence)

Outputs:
- partII_matrix_integrated_v2.xlsx (wide target; wide generated; long cell summary)
- CSV exports of the long summary and the generated wide matrix

Note: This step does not attempt to regenerate human screening decisions. It treats the
traceability long file as the screened evidence base, and generates matrices deterministically.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from utils import canon_text, ensure_dir


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
CONFIG = ROOT / "configs"
OUT_T = ROOT / "outputs" / "tables"


def _is_nonempty(x) -> bool:
    s = canon_text(x)
    return len(s) > 0


def main() -> None:
    ensure_dir(OUT_T)

    attr_map = pd.read_csv(CONFIG / "attribute_column_map.csv")

    trace = pd.read_csv(DATA / "partII_traceability_long_file.csv")
    matrix_target = pd.read_excel(DATA / "final_matrix_target.xlsx")

    # Canonical join keys
    trace["igo_canon"] = trace["igo"].map(canon_text)
    matrix_target["igo_canon"] = matrix_target["Institution"].map(canon_text)

    # Build a (igo, attribute) -> matrix_cell_text_full mapping
    cell_text = (
        trace.groupby(["igo_canon", "attribute_code"])["matrix_cell_text_full"]
        .first()
        .reset_index()
    )

    # Evidence counts per (igo, attribute)
    counts = (
        trace.groupby(["igo_canon", "attribute_code"])
        .agg(
            n_evidence_records=("record_id", "count"),
            n_sources=("source_title", "nunique"),
            n_pages=("page_in_pdf", lambda s: s.dropna().nunique()),
        )
        .reset_index()
    )

    cell_summary = cell_text.merge(counts, on=["igo_canon", "attribute_code"], how="left")

    # Generate wide matrix from traceability
    wide_generated = (
        cell_summary.merge(attr_map[["attribute_code", "matrix_column"]], on="attribute_code", how="left")
        .pivot(index="igo_canon", columns="matrix_column", values="matrix_cell_text_full")
        .reset_index()
        .rename(columns={"igo_canon": "Institution_canon"})
    )

    # Add original institution spelling from target where possible
    inst_lookup = (
        matrix_target[["igo_canon", "Institution"]]
        .drop_duplicates()
        .rename(columns={"igo_canon": "Institution_canon"})
    )
    wide_generated = wide_generated.merge(inst_lookup, on="Institution_canon", how="left")
    # Place Institution as the first column
    cols = ["Institution"] + [c for c in wide_generated.columns if c not in {"Institution", "Institution_canon"}]
    wide_generated = wide_generated[cols]

    # Prepare target matrix with canonical key for alignment
    target_cols = matrix_target.columns.tolist()
    wide_target = matrix_target[target_cols].copy()

    # Long cell summary enriched with target matrix value presence
    # Melt target for alignment
    target_long = wide_target.melt(id_vars=["Institution", "igo_canon"], var_name="matrix_column", value_name="matrix_value_target")
    # Map attribute_code to matrix_column
    attr_lookup = attr_map.rename(columns={"matrix_column": "matrix_column"})
    target_long = target_long.merge(attr_lookup[["attribute_code", "matrix_column"]], on="matrix_column", how="inner")

    target_long["has_value_target"] = target_long["matrix_value_target"].map(_is_nonempty)

    cell_summary = cell_summary.merge(target_long[["igo_canon", "attribute_code", "has_value_target"]], on=["igo_canon", "attribute_code"], how="left")

    # Write outputs
    out_xlsx = OUT_T / "partII_matrix_integrated_v2.xlsx"
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as xw:
        wide_target.to_excel(xw, index=False, sheet_name="Matrix_Wide_Target")
        wide_generated.to_excel(xw, index=False, sheet_name="Matrix_Wide_Generated")
        cell_summary.to_excel(xw, index=False, sheet_name="Matrix_Long_CellSummary")
        counts.to_excel(xw, index=False, sheet_name="EvidenceCounts_ByIGOAttribute")

    # CSV exports
    wide_generated.to_csv(OUT_T / "partII_matrix_wide_generated_from_traceability.csv", index=False)
    cell_summary.to_csv(OUT_T / "partII_matrix_long_cellsummary.csv", index=False)

    print(f"[integrate_matrix] wrote: {out_xlsx}")


if __name__ == "__main__":
    main()
