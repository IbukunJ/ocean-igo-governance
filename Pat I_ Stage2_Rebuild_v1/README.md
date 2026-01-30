# Stage 2 — Python/NLP Outputs + Code Bundle (Rebuild v1)

This bundle contains:

- **Outputs** (CSV tables + an XLSX workbook) generated from the Stage 2 pipeline.
- **Reproducible code** implementing the Stage 2 workflow, with transparent run logs and an audit trail.

## Folder structure

- `outputs/Stage2_Python_Outputs.xlsx` — consolidated workbook (all tables as sheets)
- `outputs/figures/` — workflow figures used in the thesis (if present)
- `data/tables/` — the same tables as CSV (preferred for reproducibility/versioning)
- `code/`
  - `run_stage2_pipeline_full.py` — end-to-end pipeline
  - `run_stage2_pipeline.py` — minimal pipeline (pilot pass 1 only)
- `environment/requirements.txt` — Python dependencies

## What the tables are for

- `corpus_manifest.csv` — document inventory with stable `doc_id` and pilot flag.
- `stage2_pilot_pass1_candidate_review_queue.csv` — seed-only candidate excerpts (keyword + TF-IDF semantic retrieval).
- `stage2_pilot_pass1_decision_template.csv` — screening template (action fields are **PENDING** by design).
- `stage2_first_order_theme_inventory_80.csv` — first-order theme universe (26 seed + 54 additional = 80).
- `stage2_synonym_candidate_pool.csv` — candidate term/theme pairs suggested by distinctive n-gram extraction.
- `stage2_synonym_shortlist_compiled_validated.csv` — compiled shortlist and validated synonym set with page-linked evidence.
- `stage2_dictionary_tableB.csv` — theme-level dictionary view (validated terms aggregated by theme).
- `stage2_pilot_pass2_candidate_review_queue.csv` — synonym-expanded retrieval applied to the pilot.
- `stage2_fullcorpus_pass2_candidate_review_queue_remaining.csv` — synonym-expanded retrieval applied to the remaining corpus.
- `run_log.csv` and `audit_trail.csv` — reproducibility + process transparency.

## Running the pipeline

1. Put the Stage 1 corpus PDFs into a directory (e.g., `data/raw_pdfs/`).
2. Optional: provide a pilot list file with **one filename per line**.
3. Run:

```bash
python code/run_stage2_pipeline_full.py --pdf_dir data/raw_pdfs --output_dir outputs --pilot_list data/pilot_list.txt
```

If you omit `--pilot_list`, the script uses the first 20 PDFs alphabetically as the pilot.

## Notes

- The pipeline assumes PDFs have a usable text layer. OCR is not used in this build.
- Titles are derived from filenames; DOI extraction is heuristic and should be manually verified for final references.

Generated on: 2026-01-25 (UTC)
