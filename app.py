"""
app.py
------
GeneScout -- Streamlit interface.

Two modes:
1. "Analyze Gene" -- know the gene, want details. Three tabs: literature
   brief (PubMed + Claude), mutation frequency + type breakdown
   (cBioPortal), and CRISPR dependency (DepMap, with a per-cell-line chart).
2. "Discover" -- know the cancer type but not the gene. A volcano plot
   across every gene in the DepMap CRISPR screen, surfacing selectively
   essential genes without needing to name one first.
"""

import altair as alt
import pandas as pd
import streamlit as st

from src.pubmed import search_pubmed, fetch_abstracts
from src.summarize import build_literature_brief
from src.cbioportal import (
    find_studies_by_cancer_type,
    get_mutation_frequency,
    get_mutation_type_breakdown,
)
from src.depmap import (
    load_gene_effect,
    load_model_metadata,
    get_dependency_stats,
    get_volcano_data,
    DEPENDENCY_THRESHOLD,
)

st.set_page_config(page_title="GeneScout", page_icon="\U0001F9EC", layout="centered")

st.title("\U0001F9EC GeneScout")
st.caption(
    "Triage a gene's role in a specific cancer type -- mutation frequency "
    "and CRISPR dependency data, synthesized from recent PubMed literature "
    "via Claude. Don't have a gene in mind? Use Discover mode below."
)


@st.cache_resource(show_spinner=False)
def _preload_depmap_files():
    load_gene_effect()
    load_model_metadata()
    return True


@st.cache_data(show_spinner=False)
def get_brief(gene, cancer_type):
    pmids = search_pubmed(gene, cancer_type, retmax=10)
    if not pmids:
        return None, []
    articles = fetch_abstracts(pmids)
    brief = build_literature_brief(gene, cancer_type, articles)
    return brief, articles


@st.cache_data(show_spinner=False)
def get_mutation_data(gene, cancer_type):
    studies = find_studies_by_cancer_type(cancer_type)
    if not studies:
        return None

    top_study = studies[0]
    try:
        result = get_mutation_frequency(gene, top_study["studyId"])
    except Exception as e:
        return {"error": str(e), "study_name": top_study["name"]}

    result["study_name"] = top_study["name"]
    return result


@st.cache_data(show_spinner=False)
def get_dependency_data(gene, cancer_type):
    _preload_depmap_files()
    return get_dependency_stats(gene, cancer_type)


@st.cache_data(show_spinner=False)
def get_volcano_df(cancer_type):
    _preload_depmap_files()
    return get_volcano_data(cancer_type)


# ---------------------------------------------------------------------
# Mode 1: Analyze Gene (know the gene, want details)
# ---------------------------------------------------------------------
st.header("Analyze a specific gene")

col1, col2 = st.columns(2)
with col1:
    gene_input = st.text_input("Gene symbol", placeholder="e.g. TP53")
with col2:
    cancer_type_input = st.text_input("Cancer type", placeholder="e.g. breast cancer")

if st.button("Analyze Gene", type="primary"):
    gene = gene_input.strip().upper()
    cancer_type = cancer_type_input.strip()

    if not gene or not cancer_type:
        st.warning("Enter both a gene symbol and a cancer type.")
    else:
        tab1, tab2, tab3 = st.tabs([
            "\U0001F4C4 Literature Brief",
            "\U0001F9EC Mutation Frequency",
            "\U0001F3AF Dependency (DepMap)",
        ])

        with tab1:
            with st.spinner(
                f"Searching PubMed for {gene} in {cancer_type} and asking "
                "Claude to synthesize a brief..."
            ):
                brief, articles = get_brief(gene, cancer_type)

            if not articles:
                st.info(
                    f"No PubMed literature found for **{gene}** in **{cancer_type}**. "
                    "Try a broader or differently-phrased cancer type (e.g. "
                    "\"breast cancer\" rather than a specific subtype)."
                )
            else:
                st.markdown(brief)
                st.markdown("---")
                st.markdown(f"**Source papers ({len(articles)}):**")
                for a in articles:
                    pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{a['pmid']}/"
                    st.markdown(
                        f"- **{a['first_author']} et al. ({a['year']})** -- "
                        f"*{a['journal']}* -- [{a['title']}]({pubmed_url}) "
                        f"([PMID {a['pmid']}]({pubmed_url}))"
                    )

        with tab2:
            with st.spinner(f"Querying cBioPortal for {gene} in {cancer_type}..."):
                mutation_data = get_mutation_data(gene, cancer_type)

            if mutation_data is None:
                st.info(
                    f"No cBioPortal study found matching **{cancer_type}**. "
                    "Try a more common cancer type name (e.g. \"breast\", "
                    "\"lung\", \"colorectal\")."
                )
            elif "error" in mutation_data:
                st.error(
                    f"Found a matching study ({mutation_data['study_name']}), "
                    f"but the mutation query failed: {mutation_data['error']}"
                )
            else:
                st.metric(
                    label=f"{gene} mutation frequency",
                    value=f"{mutation_data['frequency_pct']}%",
                    help=(
                        f"{mutation_data['mutated_samples']} of "
                        f"{mutation_data['total_samples']} samples"
                    ),
                )
                st.caption(f"Study: {mutation_data['study_name']}")

                type_counts = get_mutation_type_breakdown(mutation_data["mutations"])
                if type_counts:
                    type_df = pd.DataFrame({
                        "mutation_type": list(type_counts.keys()),
                        "count": list(type_counts.values()),
                    })
                    pie_chart = (
                        alt.Chart(type_df)
                        .mark_arc(innerRadius=60)
                        .encode(
                            theta=alt.Theta("count:Q"),
                            color=alt.Color("mutation_type:N", title="Mutation type"),
                            tooltip=["mutation_type", "count"],
                        )
                        .properties(height=350)
                    )
                    st.altair_chart(pie_chart, use_container_width=True)
                    st.caption(
                        f"Breakdown of {sum(type_counts.values())} individual "
                        f"{gene} mutation events by type, across mutated samples "
                        f"in {mutation_data['study_name']}."
                    )

        with tab3:
            with st.spinner(
                f"Loading DepMap data and computing {gene} dependency "
                f"in {cancer_type} (first query may take ~30s)..."
            ):
                dependency_data = get_dependency_data(gene, cancer_type)

            if dependency_data is None:
                st.info(
                    f"No DepMap dependency data found for **{gene}** in "
                    f"**{cancer_type}**. The gene may not be in the CRISPR "
                    "screen, or no cell lines matched this cancer type."
                )
            else:
                dcol1, dcol2 = st.columns(2)
                with dcol1:
                    st.metric(
                        label="Cell lines dependent",
                        value=f"{dependency_data['pct_dependent']}%",
                        help=(
                            f"{dependency_data['n_dependent']} of "
                            f"{dependency_data['n_cell_lines']} cell lines "
                            "(score \u2264 -0.5)"
                        ),
                    )
                with dcol2:
                    st.metric(
                        label="Mean dependency score",
                        value=dependency_data["mean_score"],
                        help="More negative = stronger dependency (Chronos scale)",
                    )
                st.caption(
                    f"Based on {dependency_data['n_cell_lines']} {cancer_type} "
                    "cell lines in the DepMap CRISPR knockout screen"
                )

                chart_df = pd.DataFrame({
                    "cell_line": dependency_data["cell_line_names"],
                    "score": dependency_data["scores"],
                })
                chart_df["dependent"] = chart_df["score"] <= DEPENDENCY_THRESHOLD
                chart_df = chart_df.sort_values("score")

                bar_chart = (
                    alt.Chart(chart_df)
                    .mark_bar()
                    .encode(
                        x=alt.X("cell_line:N", sort=None, title="Cell line",
                                axis=alt.Axis(labelAngle=-45)),
                        y=alt.Y("score:Q", title="Dependency score"),
                        color=alt.Color(
                            "dependent:N",
                            scale=alt.Scale(
                                domain=[True, False],
                                range=["#e74c3c", "#95a5a6"],
                            ),
                            legend=alt.Legend(title="Strongly dependent"),
                        ),
                        tooltip=["cell_line", "score"],
                    )
                    .properties(height=350)
                )

                threshold_line = (
                    alt.Chart(pd.DataFrame({"y": [DEPENDENCY_THRESHOLD]}))
                    .mark_rule(strokeDash=[4, 4], color="white")
                    .encode(y="y:Q")
                )

                st.altair_chart(bar_chart + threshold_line, use_container_width=True)
                st.caption(
                    f"Dashed line marks the dependency threshold "
                    f"({DEPENDENCY_THRESHOLD}). Red bars = strongly dependent cell lines."
                )

st.divider()

# ---------------------------------------------------------------------
# Mode 2: Discover (know the cancer type, not the gene)
# ---------------------------------------------------------------------
st.header("Discover candidate genes")
st.caption(
    "No gene in mind? Enter just a cancer type. This computes, across "
    "every gene in the DepMap CRISPR screen, how much more dependent "
    "this cancer type's cell lines are compared to everything else -- "
    "surfacing candidates without needing to name a gene first."
)

discover_cancer_type_input = st.text_input(
    "Cancer type", placeholder="e.g. multiple myeloma", key="discover_cancer_type"
)

if st.button("Discover Candidate Genes"):
    discover_cancer_type = discover_cancer_type_input.strip()

    if not discover_cancer_type:
        st.warning("Enter a cancer type.")
    else:
        with st.spinner(
            f"Computing differential dependency across ~18,500 genes for "
            f"{discover_cancer_type} (first query may take ~30s)..."
        ):
            volcano_df = get_volcano_df(discover_cancer_type)

        if volcano_df is None:
            st.info(
                f"Not enough matched cell lines found for "
                f"**{discover_cancer_type}** to compute this reliably. "
                "Try a more common cancer type name."
            )
        else:
            volcano_chart = (
                alt.Chart(volcano_df)
                .mark_circle(size=25, opacity=0.5)
                .encode(
                    x=alt.X("mean_diff:Q", title="Mean dependency difference (more negative = more selectively essential)"),
                    y=alt.Y("neg_log10_p:Q", title="-log10(p-value)"),
                    tooltip=["gene", "mean_diff", "neg_log10_p"],
                    color=alt.condition(
                        (alt.datum.mean_diff < -0.3) & (alt.datum.neg_log10_p > 2),
                        alt.value("#e74c3c"),
                        alt.value("#7f8c8d"),
                    ),
                )
                .properties(height=400)
                .interactive()
            )
            st.altair_chart(volcano_chart, use_container_width=True)
            st.caption(
                "Red points: candidates that are both notably more dependent "
                "and statistically significant. Hover any point to see the gene."
            )

            top_candidates = (
                volcano_df[volcano_df["neg_log10_p"] > 1.3]
                .sort_values("mean_diff")
                .head(15)
            )
            st.markdown("**Top candidate genes** (most selectively dependent, p < 0.05):")
            st.dataframe(
                top_candidates.rename(columns={
                    "gene": "Gene",
                    "mean_diff": "Dependency difference",
                    "neg_log10_p": "-log10(p)",
                }).reset_index(drop=True),
                use_container_width=True,
            )