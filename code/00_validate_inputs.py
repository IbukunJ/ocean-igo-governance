"""
00_validate_inputs.py

Validates that the processed inputs required to reproduce Part II diagnostics and integration
are structurally consistent and match expected record counts.

This script is designed to be run *before* integration/diagnostics.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from utils import canon_text, sha256_file, ensure_dir


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
CONFIG = ROOT / "configs"
OUT = ROOT / "outputs" / "tables"


def main() -> None:
    ensure_dir(OUT)

    expected = json.loads((CONFIG / "expected_counts.json").read_text(encoding="utf-8"))
    attr_map = pd.read_csv(CONFIG / "attribute_column_map.csv")

    cand_path = DATA / "partII_candidate_review_queue.csv"
    trace_path = DATA / "partII_traceability_long_file.csv"
    matrix_path = DATA / "final_matrix_target.xlsx"

    cand = pd.read_csv(cand_path)
    trace = pd.read_csv(trace_path)
    matrix = pd.read_excel(matrix_path)

    # Canonical join keys
    cand["igo_canon"] = cand["igo"].map(canon_text)
    trace["igo_canon"] = trace["igo"].map(canon_text)
    matrix["igo_canon"] = matrix["Institution"].map(canon_text)

    # --- checks ---
    checks = []

    def add_check(name: str, ok: bool, details: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "details": details})

    # Candidate queue counts
    add_check(
        "candidate_queue_total",
        len(cand) == expected["candidate_review_queue"]["total_candidates_reviewed"],
        f"observed={len(cand)} expected={expected['candidate_review_queue']['total_candidates_reviewed']}",
    )
    observed_actions = cand["coder_action"].value_counts().to_dict()
    for action, exp in expected["candidate_review_queue"]["by_action"].items():
        obs = int(observed_actions.get(action, 0))
        add_check(
            f"candidate_queue_action_{action}",
            obs == int(exp),
            f"observed={obs} expected={exp}",
        )

    # IGO count
    n_igos_trace = trace["igo_canon"].nunique()
    add_check(
        "igos_in_traceability",
        n_igos_trace == expected["n_igos_expected"],
        f"observed={n_igos_trace} expected={expected['n_igos_expected']}",
    )
    n_igos_matrix = matrix["igo_canon"].nunique()
    add_check(
        "igos_in_matrix_target",
        n_igos_matrix == expected["n_igos_expected"],
        f"observed={n_igos_matrix} expected={expected['n_igos_expected']}",
    )

    # Attribute coverage
    observed_attr = sorted(trace["attribute_code"].dropna().unique().tolist())
    expected_attr = sorted(attr_map["attribute_code"].unique().tolist())
    add_check(
        "attribute_codes_match",
        observed_attr == expected_attr,
        f"observed={observed_attr} expected={expected_attr}",
    )

    # Full cross product coverage in traceability (should be 48×10=480)
    cross = trace.groupby(["igo_canon", "attribute_code"]).size().reset_index(name="n_records")
    add_check(
        "traceability_has_all_igo_attribute_pairs",
        len(cross) == expected["n_igos_expected"] * expected["n_attributes_expected"],
        f"pairs={len(cross)} expected_pairs={expected['n_igos_expected'] * expected['n_attributes_expected']}",
    )

    # Evidence tiers presence
    tiers = sorted(trace["evidence_tier"].dropna().unique().tolist())
    add_check(
        "evidence_tiers_present",
        set(tiers) >= {"Definition/Identification", "Explanation/Elaboration", "Substantiation/References"},
        f"tiers={tiers}",
    )

    # Joinability: matrix institutions should be alignable to traceability igos
    missing_in_matrix = sorted(set(trace["igo_canon"]) - set(matrix["igo_canon"]))
    missing_in_trace = sorted(set(matrix["igo_canon"]) - set(trace["igo_canon"]))
    add_check(
        "igo_name_alignment",
        len(missing_in_matrix) == 0 and len(missing_in_trace) == 0,
        f"missing_in_matrix={len(missing_in_matrix)} missing_in_trace={len(missing_in_trace)}",
    )

    # Hashes for inputs
    input_hashes = {
        "partII_candidate_review_queue.csv": sha256_file(cand_path),
        "partII_traceability_long_file.csv": sha256_file(trace_path),
        "partII_decision_log.csv": sha256_file(DATA / "partII_decision_log.csv"),
        "final_matrix_target.xlsx": sha256_file(matrix_path),
        "run_log.csv": sha256_file(DATA / "run_log.csv"),
    }

    report = pd.DataFrame(checks)
    report_path = OUT / "partII_validation_report.csv"
    report.to_csv(report_path, index=False)

    hashes_path = OUT / "partII_input_hashes_sha256.json"
    hashes_path.write_text(json.dumps(input_hashes, indent=2), encoding="utf-8")

    # Lightweight console output for users
    n_ok = int(report["ok"].sum())
    print(f"[validate_inputs] checks_passed={n_ok}/{len(report)}")
    print(f"[validate_inputs] wrote: {report_path}")
    print(f"[validate_inputs] wrote: {hashes_path}")


if __name__ == "__main__":
    main()
