# Stage 3 Python Bundle (v1)

This bundle regenerates the Stage 3 reduction and attribute-derivation outputs from the Stage 2 Excel bundle.

## Inputs
- `Stage2_Python_NLP_ThemeDiscovery_and_SynonymExpansion_BUNDLE_v1.xlsx` (SHA256: `0e27ebe66b816c7e5ecdbdf7bb8141345828a5049288c7128c9942eeb69df855`)

## Key outputs
- `Stage3_Python_NLP_Reduction_BUNDLE_v1.xlsx`
- `Table_E_Stage3_Reduction_Ledger.csv`
- `Table_E2_Construct_Metrics_and_Coherence.csv`
- `Table_E3_Category_Induction_Evidence.csv`
- `Table_C_Category_to_Attribute_Crosswalk.csv`
- `Table_C2_Construct_to_Attribute_Map.csv`
- `Table_D2_Attribute_Derivation_Ledger.csv`
- Figures in `/figures`:
  - `Figure_3_4_Stage3_Workflow_Python_v1.png`
  - `Figure_3_4b_Stage3_ReductionPath_Python_v1.png`
  - `Figure_7_ConstructCooccurrence_NPMI_v1.png`

## Re-run instructions
1. Create an environment and install requirements:
   - `pip install -r requirements.txt`
2. Run:
   - `python scripts/stage3_run.py --stage2_xlsx "Stage2_Python_NLP_ThemeDiscovery_and_SynonymExpansion_BUNDLE_v1.xlsx" --out_dir outputs --fig_dir figures`

## Notes
- Step 1, Step 3, Step 4 mappings are stored in `/config` as CSV files and can be edited if you revise merge or category decisions.
- The Decision and Computation Log and environment snapshot are stored in `/logs`.

## Additional diagnostics
- `Stage3_Step1_MergeDiagnostics_Similarity.csv`
- `Stage3_Step3_MergeDiagnostics_NPMI.csv`
