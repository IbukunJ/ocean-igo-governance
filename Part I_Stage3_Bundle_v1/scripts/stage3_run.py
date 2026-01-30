#!/usr/bin/env python3
"""
Stage 3 pipeline: reduction (80->56->31->22->5) and attribute derivation (->9) from Stage 2 outputs.

This script is designed to be deterministic and auditable:
- Step 1/3/4 mappings are stored as CSV configs in /config.
- Salience and co-occurrence diagnostics are computed from the Stage 2 S4 excerpt export.

Run:
  python scripts/stage3_run.py --stage2_xlsx "Stage2_Python_NLP_ThemeDiscovery_and_SynonymExpansion_BUNDLE_v1.xlsx" --out_dir outputs --fig_dir figures
"""
from __future__ import annotations

import argparse
import math
import hashlib
from pathlib import Path
import pandas as pd
import numpy as np
import networkx as nx
from collections import Counter, defaultdict
import itertools
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def split_tags(x: object) -> list[str]:
    if pd.isna(x):
        return []
    s=str(x).strip()
    if not s:
        return []
    return [t.strip() for t in s.split(";") if t.strip()]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stage2_xlsx", required=True, help="Path to Stage 2 Excel bundle")
    ap.add_argument("--out_dir", default="outputs", help="Output directory for tables")
    ap.add_argument("--fig_dir", default="figures", help="Output directory for figures")
    ap.add_argument("--npmi_threshold", type=float, default=0.5, help="Edge retention threshold for NPMI network")
    args=ap.parse_args()

    stage2_path=Path(args.stage2_xlsx)
    out_dir=Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir=Path(args.fig_dir); fig_dir.mkdir(parents=True, exist_ok=True)

    # Load Stage 2 inputs
    themes80=pd.read_excel(stage2_path, sheet_name="05_ThemeUniverse_80")
    s4=pd.read_excel(stage2_path, sheet_name="13_Full_Pass2_S4")
    manifest=pd.read_excel(stage2_path, sheet_name="01_CorpusManifest")

    # Filter out methodological outliers (project-specific)
    outlier_patterns=[
        "NLP-driven","web-mining","web mining","text mining","5G","urban policies",
        "Augmenting Qualitative","Leveraging AI","Sustainable Development - 2025","ssrn-3362487",
        "ZP-","978-3-031","Decoding urban policies","Mapping local government priorities",
        "Informing policy with text mining","AI for Strategic Policy Evaluation","Uncovering Semantic Patterns"
    ]
    def is_outlier_file(fn: str) -> bool:
        low=str(fn).lower()
        return any(p.lower() in low for p in outlier_patterns)

    outlier_files=set([fn for fn in manifest["file_name"] if is_outlier_file(fn)])
    s4=s4[~s4["file_name"].isin(outlier_files)].copy()
    manifest=manifest[~manifest["file_name"].isin(outlier_files)].copy()

    # Load config maps
    cfg_dir=Path(__file__).resolve().parent.parent/"config"
    step1_map=pd.read_csv(cfg_dir/"step1_theme_to_concept56.csv")
    step3_map=pd.read_csv(cfg_dir/"step3_concept56_to_construct22.csv")
    cat_map=pd.read_csv(cfg_dir/"step4_construct22_to_category5.csv")
    cat_attr=pd.read_csv(cfg_dir/"category_to_attributes.csv")
    con_attr=pd.read_csv(cfg_dir/"construct_to_attributes.csv")

    theme_to_concept=dict(zip(step1_map["theme_raw"], step1_map["concept_56"]))
    concept_to_construct=dict(zip(step3_map["concept_56"], step3_map["construct_22"]))
    construct_to_cat=dict(zip(cat_map["construct_22"], cat_map["category_5"]))

    # --- Build long tag table ---
    s4["theme_list"]=s4["themes_assigned"].apply(split_tags)
    rows=[]
    for r in s4.itertuples(index=False):
        for t in r.theme_list:
            rows.append((r.excerpt_id, r.doc_id, r.file_name, r.page_in_pdf, str(t)))
    tags=pd.DataFrame(rows, columns=["excerpt_id","doc_id","file_name","page_in_pdf","theme_raw"])
    tags["concept_56"]=tags["theme_raw"].map(lambda t: theme_to_concept.get(t,t))
    tags["construct_22"]=tags["concept_56"].map(lambda c: concept_to_construct.get(c,c))

    # --- Step 2 salience gate ---
    N_docs_with_evidence=int(tags["doc_id"].nunique())
    threshold=int(math.floor(0.8*N_docs_with_evidence))

    concept_metrics=(tags.groupby("concept_56")
                     .agg(doc_freq=("doc_id","nunique"),
                          excerpt_freq=("excerpt_id","nunique"),
                          tag_instances=("concept_56","size"))
                     .reset_index())

    # Ensure full universe (56 concepts)
    concept_universe=sorted(themes80["theme_label"].map(lambda t: theme_to_concept.get(str(t),str(t))).unique())
    concept_metrics=(
        pd.DataFrame({"concept_56":concept_universe})
        .merge(concept_metrics, on="concept_56", how="left")
        .fillna(0)
    )
    concept_metrics[["doc_freq","excerpt_freq","tag_instances"]]=concept_metrics[["doc_freq","excerpt_freq","tag_instances"]].astype(int)
    concept_metrics["step2_keep"]=concept_metrics["doc_freq"]>=threshold

    keep_concepts=set(concept_metrics.loc[concept_metrics["step2_keep"],"concept_56"])

    # --- Build final constructs + categories ---
    tags_keep=tags[tags["concept_56"].isin(keep_concepts)].copy()
    tags_keep["construct_22"]=tags_keep["concept_56"].map(lambda c: concept_to_construct.get(c,c))
    tags_keep["category_5"]=tags_keep["construct_22"].map(lambda c: construct_to_cat.get(c,""))

    # --- Step 1 merge diagnostics (TF-IDF similarity on theme definitions) ---
    themes80["concept_56"]=themes80["theme_label"].map(lambda t: theme_to_concept.get(str(t),str(t)))
    themes80["theme_text"]=(themes80["theme_label"].fillna("").astype(str)+" :: "+
                            themes80["definition_note"].fillna("").astype(str)+" :: "+
                            themes80["boundary_rule"].fillna("").astype(str))
    vec=TfidfVectorizer(stop_words="english", ngram_range=(1,2), min_df=1)
    X=vec.fit_transform(themes80["theme_text"])
    sim=cosine_similarity(X)
    label_to_idx={str(lbl):i for i,lbl in enumerate(themes80["theme_label"].astype(str).tolist())}
    group_members=themes80.groupby("concept_56")["theme_label"].apply(list).to_dict()
    step1_diag=[]
    for concept, members in group_members.items():
        mem=[str(m) for m in members]
        if len(mem)<=1:
            avg_sim=np.nan; max_sim=np.nan
        else:
            idx=[label_to_idx[m] for m in mem if m in label_to_idx]
            vals=[]
            for i in range(len(idx)):
                for j in range(i+1,len(idx)):
                    vals.append(sim[idx[i], idx[j]])
            avg_sim=float(np.mean(vals)) if vals else np.nan
            max_sim=float(np.max(vals)) if vals else np.nan
        step1_diag.append({
            "concept_56":concept,
            "n_members":len(mem),
            "member_themes":"; ".join(mem),
            "avg_def_tfidf_cosine":avg_sim,
            "max_def_tfidf_cosine":max_sim
        })
    step1_diag=pd.DataFrame(step1_diag)
    step1_diag.to_csv(out_dir/"Stage3_Step1_MergeDiagnostics_Similarity.csv", index=False)

    # --- Co-occurrence network (NPMI) on final constructs ---
    excerpt_to_cons={}
    for ex_id, grp in tags_keep.groupby("excerpt_id"):
        excerpt_to_cons[ex_id]=sorted(set(grp["construct_22"].dropna().astype(str)))
    node_counts=Counter()
    pair_counts=Counter()
    for ex_id, cons in excerpt_to_cons.items():
        for c in cons:
            node_counts[c]+=1
        for a,b in itertools.combinations(cons,2):
            pair=tuple(sorted((a,b)))
            pair_counts[pair]+=1

    N_ex=len(excerpt_to_cons)
    p_node={n: node_counts[n]/N_ex for n in node_counts}
    npmi={}
    for (a,b),w in pair_counts.items():
        pab=w/N_ex
        pa=p_node[a]; pb=p_node[b]
        pmi=np.log(pab/(pa*pb))
        npmi[(a,b)]=pmi/(-np.log(pab))

    G=nx.Graph()
    for n in sorted(node_counts.keys()):
        G.add_node(n, excerpt_freq=node_counts[n], category=construct_to_cat.get(n,""))
    for (a,b),val in npmi.items():
        if val>=args.npmi_threshold:
            G.add_edge(a,b, npmi=float(val), cooc=int(pair_counts[(a,b)]))

    # --- Step 3 merge diagnostics (NPMI on member concepts) ---
    # compute NPMI at concept level among salient concepts
    excerpt_to_concepts={}
    for ex_id, grp in tags_keep.groupby("excerpt_id"):
        excerpt_to_concepts[ex_id]=sorted(set(grp["concept_56"].dropna().astype(str)))
    c_node=Counter()
    c_pair=Counter()
    for ex_id, cons in excerpt_to_concepts.items():
        for c in cons:
            c_node[c]+=1
        for a,b in itertools.combinations(cons,2):
            c_pair[tuple(sorted((a,b)))] += 1
    N_ex2=len(excerpt_to_concepts)
    p_c={n: c_node[n]/N_ex2 for n in c_node}
    npmi_c={}
    for (a,b),w in c_pair.items():
        pab=w/N_ex2
        pa=p_c[a]; pb=p_c[b]
        pmi=np.log(pab/(pa*pb))
        npmi_c[(a,b)] = pmi/(-np.log(pab))

    construct_members=defaultdict(list)
    for c in keep_concepts:
        construct_members[concept_to_construct.get(c,c)].append(c)

    step3_diag=[]
    for construct, members in construct_members.items():
        members=sorted(set(members))
        if len(members)<=1:
            avg_npmi=np.nan; max_npmi=np.nan
        else:
            vals=[]
            for a,b in itertools.combinations(members,2):
                vals.append(npmi_c.get(tuple(sorted((a,b))), np.nan))
            vals=[v for v in vals if not pd.isna(v)]
            avg_npmi=float(np.mean(vals)) if vals else np.nan
            max_npmi=float(np.max(vals)) if vals else np.nan
        step3_diag.append({
            "construct_22":construct,
            "n_member_concepts":len(members),
            "member_concepts_56":"; ".join(members),
            "avg_npmi_among_members":avg_npmi,
            "max_npmi_among_members":max_npmi
        })
    pd.DataFrame(step3_diag).to_csv(out_dir/"Stage3_Step3_MergeDiagnostics_NPMI.csv", index=False)

    # --- Export core tables ---
    # Representative snippet lookup (optional)
    s4_lookup=s4.set_index("excerpt_id")[["doc_id","file_name","page_in_pdf","excerpt_text"]]
    def pick_example(theme_raw: str):
        sub=tags[tags["theme_raw"]==theme_raw]
        if sub.empty:
            return ("","","","")
        ex_id=sub.iloc[0]["excerpt_id"]
        info=s4_lookup.loc[ex_id]
        snip=str(info["excerpt_text"]).strip().replace("\n"," ")
        snip=snip[:220]+("…" if len(snip)>220 else "")
        return (ex_id, info["doc_id"], info["page_in_pdf"], snip)

    # Table E (theme ledger)
    ledger=[]
    for r in themes80.itertuples(index=False):
        raw=str(r.theme_label)
        concept=theme_to_concept.get(raw, raw)
        m=concept_metrics[concept_metrics["concept_56"]==concept].iloc[0]
        keep=bool(m["step2_keep"])
        construct=concept_to_construct.get(concept) if keep else ""
        cat=construct_to_cat.get(construct,"") if keep else ""
        ex_id, doc_id, page, snip = pick_example(raw)
        ledger.append({
            "theme_id": getattr(r,"theme_id",""),
            "theme_raw": raw,
            "concept_56": concept,
            "doc_freq": int(m["doc_freq"]),
            "excerpt_freq": int(m["excerpt_freq"]),
            "step2_keep": keep,
            "construct_22": construct,
            "category_5": cat,
            "example_excerpt_id": ex_id,
            "example_doc_id": doc_id,
            "example_page_in_pdf": page,
            "example_snippet": snip
        })
    pd.DataFrame(ledger).to_csv(out_dir/"Table_E_Stage3_Reduction_Ledger.csv", index=False)

    # Table E2 construct metrics
    construct_stats=(tags_keep.groupby("construct_22")
                     .agg(doc_freq=("doc_id","nunique"),
                          excerpt_freq=("excerpt_id","nunique"),
                          tag_instances=("construct_22","size"))
                     .reset_index())

    deg=dict(G.degree())
    strength=dict(G.degree(weight="npmi"))
    betw=nx.betweenness_centrality(G, weight="npmi", normalized=True)
    net_df=pd.DataFrame([{
        "construct_22":n,
        "category_5":G.nodes[n].get("category",""),
        "degree_npmi":deg.get(n,0),
        "strength_npmi":strength.get(n,0.0),
        "betweenness":betw.get(n,0.0),
        "excerpt_freq_node":G.nodes[n].get("excerpt_freq",0)
    } for n in G.nodes()])

    tableE2=construct_stats.merge(net_df, on="construct_22", how="left")
    tableE2.to_csv(out_dir/"Table_E2_Construct_Metrics_and_Coherence.csv", index=False)

    # Crosswalk tables from config
    cat_attr.to_csv(out_dir/"Table_C_Category_to_Attribute_Crosswalk.csv", index=False)
    con_attr.to_csv(out_dir/"Table_C2_Construct_to_Attribute_Map.csv", index=False)

    # Network edge list
    edges=pd.DataFrame([{
        "source":u,"target":v,"npmi":d["npmi"],"cooc":d["cooc"],
        "category_source":construct_to_cat.get(u,""),"category_target":construct_to_cat.get(v,"")
    } for u,v,d in G.edges(data=True)])
    edges.to_csv(out_dir/"Stage3_ConstructCooccurrence_Edges_NPMI.csv", index=False)

    # --- Figure 7 ---
    fig, ax = plt.subplots(figsize=(10,8))
    ax.axis("off")
    pos=nx.spring_layout(G, seed=42, weight="npmi", k=0.6)
    weights=[d["npmi"] for _,_,d in G.edges(data=True)]
    if weights:
        wmin=min(weights); wmax=max(weights)
        widths=[0.5+3*(w-wmin)/(wmax-wmin+1e-9) for w in weights]
    else:
        widths=[]
    nx.draw_networkx_edges(G, pos, ax=ax, width=widths, alpha=0.6)
    nx.draw_networkx_nodes(G, pos, ax=ax, node_size=500, alpha=0.9)
    nx.draw_networkx_labels(G, pos, ax=ax, font_size=8)
    fig.tight_layout()
    fig.savefig(fig_dir/"Figure_7_ConstructCooccurrence_NPMI.png", dpi=300)
    plt.close(fig)

    # --- Metadata ---
    meta=pd.DataFrame([{
        "run_timestamp":pd.Timestamp.utcnow().isoformat(timespec="seconds")+"Z",
        "input_stage2_xlsx":stage2_path.name,
        "input_sha256":sha256_file(stage2_path),
        "N_docs_with_evidence":N_docs_with_evidence,
        "doc_freq_threshold":threshold,
        "npmi_threshold":args.npmi_threshold,
        "n_themes_raw":80,
        "n_concepts_normalised":len(concept_universe),
        "n_concepts_salient":int(concept_metrics["step2_keep"].sum()),
        "n_final_constructs":tags_keep["construct_22"].nunique()
    }])
    meta.to_csv(out_dir/"Stage3_Run_Metadata.csv", index=False)

    print("Stage 3 pipeline complete.")
    print(f"Outputs: {out_dir.resolve()}")
    print(f"Figures: {fig_dir.resolve()}")

if __name__=="__main__":
    main()
