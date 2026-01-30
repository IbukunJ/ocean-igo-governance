# Part II — Step 2 (Systematic data collection) — Reproducibility bundle

This bundle contains the **document corpus** used for Part II, Step 2 (systematic data collection), together with page-anchored text extraction outputs and paragraph-level screening units. The purpose is to preserve **legal fidelity** (foundational instruments) while enabling comparable downstream retrieval and coding for the nine governance attributes (YE, SJ, SMJ, SoJ, DO, STR, IIR, VC, HC).

## What is included

### Inputs
- `data/raw/igo_documents/`: source files (PDFs and one legacy `.doc`) corresponding to the **48 IGOs** in the evaluation cohort.
- `data/processed/step2_doc_manifest_seed.csv`: the seed manifest mapping each file to an IGO and document type.

### Interim products (page fidelity + unitisation)
- `data/interim/page_text_jsonl/`: one JSONL per PDF (`DOC_XXXX_pages.jsonl`) containing page-anchored extracted text.
- `outputs/tables/step2_corpus_pages.csv`: page index (doc_id, page_number, char_count, text hash).
- `outputs/tables/step2_corpus_paragraphs.csv`: paragraph-level units (within-page), used as the retrieval/screening unit.

### Reports
- `outputs/tables/step2_corpus_documents.csv`: document manifest with hashes, page counts, extraction method, and quality flags.
- `outputs/tables/step2_extraction_quality_report.csv`: extraction diagnostics (pages with text, low-text-density flags).
- `outputs/tables/step2_igo_document_coverage.csv`: coverage summary by IGO.
- `PartII_Step2_DocumentCorpus_BUNDLE_v1.xlsx`: Excel bundle containing the same tables plus the attribute evidence guide (Table F) and run metadata.

### Reproducibility
- `code/`: Python scripts that rebuild the outputs from the raw files and the manifest seed.
- `environment/requirements.txt`: pinned environment for replication.
- `outputs/reports/run_log.csv`: run metadata for this build (`run_id=partii_step2_20260130_094327`).

## Notes on extraction quality
Some PDFs are flagged `low_text_density`. These are typically scanned or image-heavy instruments. No OCR is applied in Step 2; the flag indicates that OCR may be required in a separate controlled step if those documents are needed for text-based retrieval.

## How to regenerate
1. Create and activate a Python environment, then install dependencies:

```bash
pip install -r environment/requirements.txt
```

2. Run the pipeline:

```bash
python code/99_run_all.py --bundle_root .
```

All outputs will be regenerated under `outputs/` and `data/interim/`.