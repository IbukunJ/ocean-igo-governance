"""
03_make_figures.py

Generates simple diagnostic figures from the coverage/missingness table:
- coverage_heatmap (IGOs × attributes; value-present)
- missingness_bar (count of missing values by attribute)

The figures are intentionally minimal and rely on default matplotlib settings.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from utils import ensure_dir


ROOT = Path(__file__).resolve().parents[1]
OUT_F = ROOT / "outputs" / "figures"
OUT_T = ROOT / "outputs" / "tables"


def main() -> None:
    ensure_dir(OUT_F)

    cov = pd.read_csv(OUT_T / "partII_coverage_missingness_v2.csv")

    # Heatmap: has_value by IGO × attribute
    pivot = (
        cov.pivot_table(index="Institution", columns="attribute_code", values="has_value", aggfunc="max", fill_value=0)
        .sort_index()
    )

    plt.figure(figsize=(10, max(6, 0.25 * len(pivot))))
    plt.imshow(pivot.values, aspect="auto")
    plt.yticks(range(len(pivot.index)), pivot.index, fontsize=6)
    plt.xticks(range(len(pivot.columns)), pivot.columns, fontsize=10)
    plt.title("Part II coverage heatmap (matrix cell populated)")
    plt.xlabel("Attribute code")
    plt.ylabel("IGO")
    plt.tight_layout()
    heat_path = OUT_F / "partII_coverage_heatmap_v2.png"
    plt.savefig(heat_path, dpi=200)
    plt.close()

    # Missingness by attribute (cells with has_value==0)
    miss = cov.groupby("attribute_code")["has_value"].apply(lambda s: int((s == 0).sum())).reset_index(name="n_missing_cells")
    miss = miss.sort_values("n_missing_cells", ascending=False)

    plt.figure(figsize=(8, 4))
    plt.bar(miss["attribute_code"], miss["n_missing_cells"])
    plt.title("Part II missingness by attribute (target matrix)")
    plt.xlabel("Attribute code")
    plt.ylabel("Number of missing cells")
    plt.tight_layout()
    bar_path = OUT_F / "partII_missingness_bar_v2.png"
    plt.savefig(bar_path, dpi=200)
    plt.close()

    print(f"[figures] wrote: {heat_path}")
    print(f"[figures] wrote: {bar_path}")


if __name__ == "__main__":
    main()
