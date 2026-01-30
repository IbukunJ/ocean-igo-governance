"""Run all Part II Step 2 scripts in sequence."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

def run(cmd: list[str]) -> None:
    subprocess.check_call(cmd)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle_root", default=".", help="Root of the Step 2 bundle.")
    args = ap.parse_args()

    root = Path(args.bundle_root)

    # Ensure scripts resolve local imports
    env = dict(**__import__("os").environ)
    env["PYTHONPATH"] = str(root / "code")

    run(["python", str(root / "code" / "01_build_documents_table.py"), "--bundle_root", str(root)])
    run(["python", str(root / "code" / "02_extract_pages.py"), "--bundle_root", str(root)])
    run(["python", str(root / "code" / "03_segment_paragraphs.py"), "--bundle_root", str(root)])
    run(["python", str(root / "code" / "04_generate_bundle.py"), "--bundle_root", str(root)])

if __name__ == "__main__":
    main()
