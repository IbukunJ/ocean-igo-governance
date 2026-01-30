import argparse
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input_dir", required=True)
    ap.add_argument("--out_dir", required=True)
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    out_dir = Path(args.out_dir)
    (out_dir/"tables").mkdir(parents=True, exist_ok=True)
    (out_dir/"figures").mkdir(parents=True, exist_ok=True)

    cand = pd.read_csv(input_dir/"step3_candidate_review_queue.csv")
    trace = pd.read_csv(input_dir/"step3_traceability_long_file.csv")

    # Normalise action labels
    action_map = {"Accept":"ACCEPT", "Reject":"REJECT", "Re-tag":"RETAG"}
    cand["coder_action_std"] = cand["coder_action"].map(action_map).fillna(cand["coder_action"])
    trace["coder_action_std"] = trace["coder_action"].map(action_map).fillna(trace["coder_action"])

    # Summary stats
    summary = pd.DataFrame([
        {"metric":"total_reviewed_candidates", "value":len(cand)},
        {"metric":"accepted", "value":(cand["coder_action_std"]=="ACCEPT").sum()},
        {"metric":"retagged", "value":(cand["coder_action_std"]=="RETAG").sum()},
        {"metric":"rejected", "value":(cand["coder_action_std"]=="REJECT").sum()},
        {"metric":"n_igos", "value":cand["igo"].nunique()},
    ])
    summary.to_csv(out_dir/"tables"/"step3_summary_stats.csv", index=False)

    # Breakdown by retrieval set
    if "retrieval_set" in cand.columns:
        breakdown = cand.groupby("retrieval_set")["coder_action_std"].value_counts().unstack(fill_value=0)
        breakdown.to_csv(out_dir/"tables"/"step3_action_breakdown_by_retrieval_set.csv")

    # Coverage by IGO and attribute from retained evidence
    attr_col = "attribute_code_final" if "attribute_code_final" in trace.columns else "attribute_code"
    cov = trace.groupby(["igo",attr_col]).size().unstack(fill_value=0).reset_index()
    cov.to_csv(out_dir/"tables"/"step3_coverage_by_igo_attribute.csv", index=False)

    # Figure 1: action counts by attribute
    attr_after = "attribute_code_after" if "attribute_code_after" in cand.columns else "attribute_code"
    action_by_attr = cand.groupby(attr_after)["coder_action_std"].value_counts().unstack(fill_value=0)
    for col in ["ACCEPT","RETAG","REJECT"]:
        if col not in action_by_attr.columns:
            action_by_attr[col] = 0
    action_by_attr = action_by_attr[["ACCEPT","RETAG","REJECT"]]

    plt.figure(figsize=(10,5))
    action_by_attr.plot(kind="bar")
    plt.xlabel("Attribute code")
    plt.ylabel("Count of candidate passages")
    plt.tight_layout()
    plt.savefig(out_dir/"figures"/"Figure_Step3_ActionCounts_byAttribute.png", dpi=200)
    plt.close()

    # Figure 2: TF-IDF cosine distribution (if present)
    if "tfidf_cosine" in cand.columns:
        plt.figure(figsize=(8,4))
        cand[cand["coder_action_std"]=="ACCEPT"]["tfidf_cosine"].hist(alpha=0.7, bins=30, label="ACCEPT")
        cand[cand["coder_action_std"]=="REJECT"]["tfidf_cosine"].hist(alpha=0.7, bins=30, label="REJECT")
        plt.xlabel("TF-IDF cosine similarity (snippet vs indicator query)")
        plt.ylabel("Count")
        plt.legend()
        plt.tight_layout()
        plt.savefig(out_dir/"figures"/"Figure_Step3_TFIDFScore_Distribution.png", dpi=200)
        plt.close()

if __name__ == "__main__":
    main()