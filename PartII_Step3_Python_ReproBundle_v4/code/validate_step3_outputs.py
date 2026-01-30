from pathlib import Path
import pandas as pd

def main():
    base = Path(__file__).resolve().parents[1]
    cand = pd.read_csv(base/"data/processed/step3_candidate_review_queue.csv")
    trace = pd.read_csv(base/"data/processed/step3_traceability_long_file.csv")

    action_map = {"Accept":"ACCEPT", "Reject":"REJECT", "Re-tag":"RETAG"}
    cand["coder_action_std"] = cand["coder_action"].map(action_map).fillna(cand["coder_action"])

    total = len(cand)
    accepted = (cand["coder_action_std"]=="ACCEPT").sum()
    retagged = (cand["coder_action_std"]=="RETAG").sum()
    rejected = (cand["coder_action_std"]=="REJECT").sum()

    assert total == accepted + retagged + rejected, "Action counts do not sum to total."
    assert len(trace) == accepted + retagged, "Traceability long file rows should equal accepted + retagged."

    # Basic TF-IDF sanity check if present
    if "tfidf_cosine" in cand.columns:
        assert cand["tfidf_cosine"].between(0,1).all(), "TF-IDF cosine should be within [0,1]."

    print("OK: Step 3 counts and basic diagnostics consistent")
    print({"total":int(total), "accepted":int(accepted), "retagged":int(retagged), "rejected":int(rejected), "trace_rows":int(len(trace))})

if __name__ == "__main__":
    main()