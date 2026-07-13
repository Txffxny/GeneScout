"""
app.py
------
GeneScout -- Streamlit interface.

Three tabs: literature brief (PubMed + Claude), mutation frequency
(cBioPortal), and CRISPR dependency (DepMap, local data).
"""

import streamlit as st

from src.pubmed import search_pubmed, fetch_abstracts
from src.summarize import build_literature_brief
from src.cbioportal import find_studies_by_cancer_type, get_mutation_frequency
from src.depmap import load_gene_effect, load_model_metadata, get_dependency_stats

st.set_page_config(page_title="GeneScout", page_icon="\U0001F9EC", layout="centered")

st.title("\U0001F9EC GeneScout")
st.caption(
    "Triage a gene's role in a specific cancer type -- mutation frequency "
    "and CRISPR dependency data, synthesized from recent PubMed literature "
    "via Claude."
)

col1, col2 = st.columns(2)
with col1:
    gene_input = st.text_input("Gene symbol", placeholder="e.g. TP53")
with col2:
    cancer_type_input = st.text_input("Cancer type", placeholder="e.g. breast cancer")


@st.cache_data(show_spinner=False)
def get_brief(gene, cancer_type):
    pmids = search_pubmed(gene, cancer_type, retmax=5)
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


@st.cache_resource(show_spinner=False)
def _preload_depmap_files():
    load_gene_effect()
    load_model_metadata()
    return True


@st.cache_data(show_spinner=False)
def get_dependency_data(gene, cancer_type):
    _preload_depmap_files()
    return get_dependency_stats(gene, cancer_type)


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
            with st.spinner(f"Searching PubMed for {gene} in {cancer_type}..."):
                brief, articles = get_brief(gene, cancer_type)

            if not articles:
                st.info(
                    f"No PubMed literature found for **{gene}** in **{cancer_type}**. "
                    "Try a broader or differently-phrased cancer type (e.g. "
                    "\"breast cancer\" rather than a specific subtype)."
                )
            else:
                st.markdown(brief)
                with st.expander(f"View {len(articles)} source abstracts"):
                    for a in articles:
                        st.markdown(f"**[PMID {a['pmid']}]** {a['title']}")
                        st.caption(a["abstract"])

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