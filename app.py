"""
app.py
------
GeneScout -- Streamlit interface.

MVP v1: literature brief only (cBioPortal mutation-frequency and DepMap
dependency tabs are built separately and will be layered in next; this
ships a working, demoable tool with the piece that's fully tested).
"""

import streamlit as st

from src.pubmed import search_pubmed, fetch_abstracts
from src.summarize import build_literature_brief
from src.cbioportal import find_studies_by_cancer_type, get_mutation_frequency

st.set_page_config(page_title="GeneScout", page_icon="\U0001F9EC", layout="centered")

st.title("\U0001F9EC GeneScout")
st.caption(
    "Triage a gene's role in a specific cancer type -- mutation frequency "
    "from cBioPortal, synthesized from recent PubMed literature via Claude."
)

col1, col2 = st.columns(2)
with col1:
    gene_input = st.text_input("Gene symbol", placeholder="e.g. TP53")
with col2:
    cancer_type_input = st.text_input("Cancer type", placeholder="e.g. breast cancer")


@st.cache_data(show_spinner=False)
def get_brief(gene, cancer_type):
    """
    Cached end-to-end literature pipeline: search -> fetch abstracts ->
    synthesize. Cached on (gene, cancer_type) so repeat lookups don't
    re-hit PubMed or re-spend on the Claude call.
    """
    pmids = search_pubmed(gene, cancer_type, retmax=5)
    if not pmids:
        return None, []
    articles = fetch_abstracts(pmids)
    brief = build_literature_brief(gene, cancer_type, articles)
    return brief, articles


@st.cache_data(show_spinner=False)
def get_mutation_data(gene, cancer_type):
    """
    Cached cBioPortal lookup: find the best-matching (largest) study for
    the cancer type, then get mutation frequency for the gene within it.

    Returns None if no matching study exists for this cancer type search
    term, or an error dict if the API call itself fails (e.g. the
    "{study_id}_mutations" naming assumption doesn't hold for this
    particular study -- see the caveat in cbioportal.py).
    """
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


if st.button("Analyze Gene", type="primary"):
    gene = gene_input.strip().upper()
    cancer_type = cancer_type_input.strip()

    if not gene or not cancer_type:
        st.warning("Enter both a gene symbol and a cancer type.")
    else:
        tab1, tab2 = st.tabs(["\U0001F4C4 Literature Brief", "\U0001F9EC Mutation Frequency"])

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