# Part II — Step 4 Reproducibility Bundle (Data Integration and Validation)

This bundle regenerates the Step 4 outputs that integrate the Step 3 traceability archive into an analysis-ready IGO attribute matrix.

## Inputs

- **Step 3 Excel bundle**: `PartII_Step3_AttributeCoding_BUNDLE_v4.xlsx`
  - Required sheets:
    - `05_TraceabilityLong`
    - `04_DecisionLog`
    - `03_CandidateReviewQueue`

- **Schema and hierarchy config**: `config/step4_schema_and_hierarchy.json`

## Outputs (in `outputs/`)

- `PartII_Step4_DataIntegration_BUNDLE.xlsx` (multi-sheet workbook)
- `step4_matrix_wide.csv` (chapter-facing matrix)
- `step4_matrix_long.csv` (long format + record id linkage)
- `step4_coverage_missingness.csv`
- `step4_integrity_checks.csv`
- `step4_orphan_evidence.csv`
- `step4_run_log.csv`
- `Figure_Step4_EvidenceVolume_byAttribute.png`

## Reproduce

1. Create a Python environment using `environment/requirements.txt`
2. Run:

   ```bash
   python code/step4_integrate.py \
     --step3_bundle /path/to/PartII_Step3_AttributeCoding_BUNDLE_v4.xlsx \
     --config config/step4_schema_and_hierarchy.json \
     --outdir outputs \
     --make_figure
   ```

The pipeline is deterministic and does not use random seeds.

## Notes on integration logic

- Step 4 **does not** add new evidence. It only:
  - enforces a fixed schema (IGO × attribute),
  - standardises identifiers,
  - collapses retained evidence into one value per IGO × attribute,
  - and writes validation diagnostics.

- Evidence lineage is preserved by carrying forward **record identifiers** (`record_ids`) that link every integrated matrix cell back to the Step 3 traceability long file.
