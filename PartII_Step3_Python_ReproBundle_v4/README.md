# Part II — Step 3 Reproducibility Bundle (Python)

This bundle contains the processed datasets, configuration, scripts, and outputs for **Part II — Step 3**: attribute operationalisation, indicator-linked retrieval, and human-verified coding for **48 globally mandated IGOs**.

## Core logic (what is in Step 3)

- Indicators and keyword/phrase families (Table XX) drive deterministic paragraph-level retrieval.
- Candidate passages are ranked with TF–IDF cosine similarity (vector-space model).
- A human screening protocol records actions (Accept / Reject / Re-tag) and memoed rationales.
- Accepted and retagged passages form the Traceability Long File used in Step 4 matrix integration.

## Contents

### Configuration
- `config/table_xx_attribute_indicator_keyword_matrix.csv`

### Processed datasets (inputs)
- `data/processed/step3_candidate_review_queue.csv`
- `data/processed/step3_decision_log.csv`
- `data/processed/step3_traceability_long_file.csv`

### Derived outputs
- `outputs/tables/step3_summary_stats.csv`
- `outputs/tables/step3_action_breakdown_by_retrieval_set.csv`
- `outputs/tables/step3_coverage_by_igo_attribute.csv`
- `outputs/tables/README_FieldDictionary_Step3.csv`
- `outputs/figures/Figure_Step3_ActionCounts_byAttribute.png`
- `outputs/figures/Figure_Step3_TFIDFScore_Distribution.png`

### Environment and run metadata
- `environment/requirements.txt` (pinned)
- `run_log.csv`

## Attribute codes

The primary coding target is the nine-attribute taxonomy: `YE`, `SJ`, `SMJ`, `SoJ`, `DO`, `STR`, `IIR`, `VC`, `HC`.

A small auxiliary retrieval set appears as `SCL` (retrieval set `scale_gate`). These records document scope statements used to support the global-mandate scale gate in Step 1. They are retained for auditability but are not part of the final 9-attribute matrix.

## Regeneration

Create an environment using `environment/requirements.txt`, then run:

```bash
python code/rebuild_step3_bundle.py --input_dir data/processed --out_dir outputs
python code/validate_step3_outputs.py
```

Optional: regenerate the **machine-surfaced** candidate queue directly from Step 2 paragraph extractions:

```bash
python code/generate_candidate_review_queue.py \
  --paragraphs_csv <PATH_TO_STEP2>/step2_corpus_paragraphs.csv \
  --indicator_csv config/table_xx_attribute_indicator_keyword_matrix.csv \
  --out_csv outputs/tables/step3_candidate_review_queue_machine_only.csv
```

This produces an *unreviewed* (machine-only) candidate queue. The audited queue used in the thesis is `data/processed/step3_candidate_review_queue.csv`, which additionally includes the human screening actions and memos.

## Table XX provenance annex
The Step 3 table bundle includes an additional sheet (02b_TableXX_ProvenanceAnnex) that summarises, per attribute, the theoretical anchor, the documentary expression used for coding, and the rationale for the associated trigger families.


## Table XX provenance annex
A short provenance annex is provided in `outputs/tables/PartII_Step3_AttributeCoding_BUNDLE_v4.xlsx` (sheet `02b_TableXX_ProvenanceAnnex`). It records, for each of the nine attributes: (i) the theoretical anchor used to justify the indicator family, (ii) the documentary expressions expected in IGO materials, and (iii) why the corresponding trigger family is a valid retrieval proxy under the evidence hierarchy.
