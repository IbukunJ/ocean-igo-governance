"""
run_all.py

One-command reproducer for Part II bundle outputs.

Usage:
    python code/run_all.py
    python code/run_all.py --with-step2

Default behaviour regenerates *diagnostics and tables* from the processed datasets
included in the bundle. With `--with-step2`, the script additionally rebuilds the
Step 2 extraction artefacts (page-anchored text + paragraph units) from the raw
PDFs shipped in `data/raw/igo_documents/`.

Outputs are written under:
  - outputs/tables/
  - outputs/figures/
  - data/interim/ (Step 2 extraction artefacts)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"


def _run(path: Path) -> None:
    p = subprocess.run([sys.executable, str(path)], check=True)
    if p.returncode != 0:
        raise SystemExit(p.returncode)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-step2", action="store_true", help="Rebuild Step 2 extraction artefacts from raw PDFs.")
    args = ap.parse_args()

    if args.with_step2:
        _run(CODE / "step2" / "00_build_igo_doc_manifest.py")
        _run(CODE / "step2" / "01_extract_text_and_unitise.py")

    _run(CODE / "00_validate_inputs.py")
    _run(CODE / "01_integrate_matrix.py")
    _run(CODE / "02_build_diagnostics.py")
    _run(CODE / "03_make_figures.py")
    print("[run_all] done")


if __name__ == "__main__":
    main()
