"""
depmap.py
---------
Loads local DepMap CRISPR gene-effect data and cell line metadata, and
computes dependency statistics for a gene within a specific cancer type.

Unlike cbioportal.py and pubmed.py, this module reads from local CSV files
rather than a live API -- DepMap doesn't offer a public API for this data,
so the files in data/CRISPRGeneEffect.csv and data/Model.csv (downloaded
manually per the project README) are the source of truth.

Expects:
    data/CRISPRGeneEffect.csv  -- rows: ModelID, columns: "GENE (EntrezID)"
    data/Model.csv             -- rows: ModelID, includes OncotreeLineage,
                                   OncotreePrimaryDisease, OncotreeSubtype

A dependency score <= -0.5 (Chronos scale) is the conventional threshold
for "strongly dependent" -- more negative means the cell line relies more
heavily on that gene to survive.
"""

import os

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
GENE_EFFECT_PATH = os.path.join(DATA_DIR, "CRISPRGeneEffect.csv")
MODEL_PATH = os.path.join(DATA_DIR, "Model.csv")

DEPENDENCY_THRESHOLD = -0.5

_gene_effect_cache = None
_model_cache = None


def load_gene_effect():
    """
    Load the full CRISPR gene-effect matrix. This is a large file (hundreds
    of MB) -- loaded once and cached in a module-level variable for the
    life of the process. In the Streamlit app, wrap the call to this with
    st.cache_resource so it's loaded exactly once per app session, not
    re-read from disk on every query.
    """
    global _gene_effect_cache
    if _gene_effect_cache is None:
        _gene_effect_cache = pd.read_csv(GENE_EFFECT_PATH, index_col=0)
    return _gene_effect_cache


def load_model_metadata():
    """Load cell line metadata (cancer type, lineage, etc. per ModelID)."""
    global _model_cache
    if _model_cache is None:
        _model_cache = pd.read_csv(MODEL_PATH)
    return _model_cache


def _find_gene_column(gene_effect_df, hugo_symbol):
    """
    Columns are formatted like "TP53 (7157)" -- match on the symbol prefix
    since the Entrez ID isn't known ahead of time.
    """
    prefix = f"{hugo_symbol.upper()} ("
    for col in gene_effect_df.columns:
        if col.upper().startswith(prefix):
            return col
    return None


_GENERIC_WORDS = {"cancer", "carcinoma", "disease", "of", "the", "tumor", "tumour"}


def _matches_cancer_type(text, query_words):
    """
    True if any significant query word appears in this Oncotree field.
    Matching on individual words (rather than the whole phrase) is what
    lets "multiple myeloma" find DepMap's actual term "Plasma Cell
    Myeloma" -- they share the word "myeloma" but aren't substrings of
    each other as full phrases.
    """
    if pd.isna(text):
        return False
    text_lower = text.lower()
    return any(word in text_lower for word in query_words)


def get_dependency_stats(gene, cancer_type):
    """
    For a given gene and cancer type, return dependency statistics across
    all matching cell lines.

    Returns None if the gene isn't in the dataset, or if no cell lines
    match the cancer type search term.

    Returns a dict:
        {
          "gene": "IRF4",
          "cancer_type": "multiple myeloma",
          "n_cell_lines": 12,
          "n_dependent": 9,
          "pct_dependent": 75.0,
          "mean_score": -0.71,
          "scores": [...]   # per-cell-line detail, useful later for plots
        }
    """
    gene_effect_df = load_gene_effect()
    model_df = load_model_metadata()

    gene_col = _find_gene_column(gene_effect_df, gene)
    if gene_col is None:
        return None

    query_words = [w for w in cancer_type.lower().split() if w not in _GENERIC_WORDS]
    if not query_words:
        query_words = [cancer_type.lower()]

    matching_models = model_df[
        model_df["OncotreeLineage"].apply(lambda t: _matches_cancer_type(t, query_words))
        | model_df["OncotreePrimaryDisease"].apply(lambda t: _matches_cancer_type(t, query_words))
        | model_df["OncotreeSubtype"].apply(lambda t: _matches_cancer_type(t, query_words))
    ]

    if matching_models.empty:
        return None

    model_ids = matching_models["ModelID"]
    # Only keep IDs actually present in the gene-effect matrix -- not every
    # model in Model.csv necessarily has CRISPR screen data available.
    available_ids = [mid for mid in model_ids if mid in gene_effect_df.index]

    if not available_ids:
        return None

    scores = gene_effect_df.loc[available_ids, gene_col].dropna()

    if scores.empty:
        return None

    n_dependent = int((scores <= DEPENDENCY_THRESHOLD).sum())

    return {
        "gene": gene,
        "cancer_type": cancer_type,
        "n_cell_lines": len(scores),
        "n_dependent": n_dependent,
        "pct_dependent": round(100 * n_dependent / len(scores), 1),
        "mean_score": round(float(scores.mean()), 2),
        "scores": scores.tolist(),
    }


if __name__ == "__main__":
    print("Loading DepMap data (this may take a moment for the full file)...")
    result = get_dependency_stats("IRF4", "multiple myeloma")
    if result is None:
        print("No matching data found.")
    else:
        print(f"\n{result['gene']} dependency in {result['cancer_type']}:")
        print(
            f"  {result['n_dependent']}/{result['n_cell_lines']} cell lines "
            f"({result['pct_dependent']}%) strongly dependent"
        )
        print(f"  Mean dependency score: {result['mean_score']}")