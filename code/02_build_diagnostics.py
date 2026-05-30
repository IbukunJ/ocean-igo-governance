"""
02_build_diagnostics.py

Computes coverage, missingness, and integrity diagnostics for Part II.

This script compares:
- evidence availability (from the traceability long file), against
- populated matrix cells (from the target matrix file).

The purpose is to make gaps visible and auditable:
- "orphan evidence": evidence exists but the target matrix cell is empty
- "missing evidence": target matrix cell has content but no traceability evidence is present
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from utils import canon_text, ensure_dir


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
CONFIG = ROOT / "configs"
OUT = ROOT / "outputs" / "tables"


def _is_nonempty(x) -> int:
    return 1 if len(canon_text(x)) > 0 else 0


def main() -> None:
    ensure_dir(OUT)

    attr_map = pd.read_csv(CONFIG / "attribute_column_map.csv")
    trace = pd.read_csv(DATA / "partII_traceability_long_file.csv")
    matrix = pd.read_excel(DATA / "final_matrix_target.xlsx")

    # Canonical join keys
    trace["igo_canon"] = trace["igo"].map(canon_text)
    matrix["igo_canon"] = matrix["Institution"].map(canon_text)

    # Evidence counts per IGO-attribute
    ev = (
        trace.groupby(["igo_canon", "attribute_code"])
        .agg(
            n_evidence_records=("record_id", "count"),
            n_sources=("source_title", "nunique"),
            n_subst=("evidence_tier", lambda s: int((s == "Substantiation/References").sum())),
        )
        .reset_index()
    )
    ev["has_evidence"] = (ev["n_evidence_records"] > 0).astype(int)

    # Melt target matrix into long form
    matrix_long = matrix.melt(
        id_vars=["Institution", "igo_canon"],
        var_name="matrix_column",
        value_name="matrix_value",
    )

    # Keep only attribute-relevant columns
    matrix_long = matrix_long.merge(
        attr_map.rename(columns={"matrix_column": "matrix_column"}),
        on="matrix_column",
        how="inner",
    )
    matrix_long["has_value"] = matrix_long["matrix_value"].map(_is_nonempty)

    # Join evidence counts
    cov = matrix_long.merge(ev, on=["igo_canon", "attribute_code"], how="left")
    cov[["n_evidence_records", "n_sources", "n_subst"]] = cov[["n_evidence_records", "n_sources", "n_subst"]].fillna(0).astype(int)
    cov["has_evidence"] = cov["has_evidence"].fillna(0).astype(int)

    # Categorise
    def _status(row) -> str:
        if row["has_value"] == 1 and row["has_evidence"] == 1:
            return "ok"
        if row["has_value"] == 0 and row["has_evidence"] == 1:
            return "orphan_evidence"
        if row["has_value"] == 1 and row["has_evidence"] == 0:
            return "missing_evidence"
        return "missing_both"

    cov["status"] = cov.apply(_status, axis=1)

    cov_out = OUT / "partII_coverage_missingness_v2.csv"
    cov.to_csv(cov_out, index=False)

    # Build integrity summary
    n_igos = matrix["igo_canon"].nunique()
    n_attrs = attr_map["attribute_code"].nunique()
    total_cells = n_igos * n_attrs

    summary_rows = [
        {"metric": "n_igos", "value": n_igos},
        {"metric": "n_attributes", "value": n_attrs},
        {"metric": "total_cells", "value": total_cells},
        {"metric": "cells_with_value", "value": int(cov["has_value"].sum())},
        {"metric": "cells_with_evidence", "value": int(cov["has_evidence"].sum())},
        {"metric": "cells_ok", "value": int((cov["status"] == "ok").sum())},
        {"metric": "cells_orphan_evidence", "value": int((cov["status"] == "orphan_evidence").sum())},
        {"metric": "cells_missing_evidence", "value": int((cov["status"] == "missing_evidence").sum())},
        {"metric": "cells_missing_both", "value": int((cov["status"] == "missing_both").sum())},
        {"metric": "total_evidence_records_in_traceability", "value": int(len(trace))},
    ]
    summary = pd.DataFrame(summary_rows)
    summary_out = OUT / "partII_integrity_checks_report_v2.csv"
    summary.to_csv(summary_out, index=False)

    # Orphan evidence register: list IGO-attribute pairs + representative snippets
    orphans = cov[cov["status"] == "orphan_evidence"][["igo_canon", "Institution", "attribute_code", "matrix_column", "n_evidence_records", "n_sources"]].copy()

    # Attach representative evidence (first 2 substantiation excerpts + sources)
    def rep_text(igo_canon: str, attribute_code: str) -> str:
        sub = trace[(trace["igo_canon"] == igo_canon) & (trace["attribute_code"] == attribute_code) & (trace["evidence_tier"] == "Substantiation/References")].head(2)
        if sub.empty:
            sub = trace[(trace["igo_canon"] == igo_canon) & (trace["attribute_code"] == attribute_code)].head(2)
        parts = []
        for _, r in sub.iterrows():
            loc = canon_text(r.get("article_section_page")) or f"p.{r.get('page_in_pdf')}"
            src = canon_text(r.get("source_title"))
            ex = canon_text(r.get("excerpt_<=50w"))
            parts.append(f'"{ex}" ({src}, {loc})')
        return " | ".join(parts)

    orphans["representative_evidence"] = [
        rep_text(row["igo_canon"], row["attribute_code"]) for _, row in orphans.iterrows()
    ]

    orphans_out = OUT / "partII_orphan_evidence_v2.csv"
    orphans.to_csv(orphans_out, index=False)

    print(f"[diagnostics] wrote: {cov_out}")
    print(f"[diagnostics] wrote: {summary_out}")
    print(f"[diagnostics] wrote: {orphans_out}")


if __name__ == "__main__":
    main()
