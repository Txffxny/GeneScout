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

st.set_page_config(page_title="GeneScout", page_icon="\U0001F9EC", layout="centered")

st.title("\U0001F9EC GeneScout")
st.caption(
    "Triage a gene's role in a specific cancer type -- synthesized from "
    "recent PubMed literature via Claude."
)

col1, col2 = st.columns(2)
with col1:
    gene_input = st.text_input("Gene symbol", placeholder="e.g. TP53")
with col2:
    cancer_type_input = st.text_input("Cancer type", placeholder="e.g. breast cancer")


@st.cache_data(show_spinner=False)
def get_brief(gene, cancer_type):
    """
    Cached end-to-end pipeline: search -> fetch abstracts -> synthesize.
    Cached on (gene, cancer_type) so repeat lookups -- including repeat
    demos of the same example -- don't re-hit PubMed or re-spend on the
    Claude call.
    """
    pmids = search_pubmed(gene, cancer_type, retmax=5)
    if not pmids:
        return None, []
    articles = fetch_abstracts(pmids)
    brief = build_literature_brief(gene, cancer_type, articles)
    return brief, articles


if st.button("Get Literature Brief", type="primary"):
    gene = gene_input.strip().upper()
    cancer_type = cancer_type_input.strip()

    if not gene or not cancer_type:
        st.warning("Enter both a gene symbol and a cancer type.")
    else:
        with st.spinner(f"Searching PubMed for {gene} in {cancer_type}..."):
            brief, articles = get_brief(gene, cancer_type)

        if not articles:
            st.info(
                f"No PubMed literature found for **{gene}** in **{cancer_type}**. "
                "Try a broader or differently-phrased cancer type (e.g. "
                "\"breast cancer\" rather than a specific subtype)."
            )
        else:
            st.subheader("Literature Brief")
            st.markdown(brief)

            with st.expander(f"View {len(articles)} source abstracts"):
                for a in articles:
                    st.markdown(f"**[PMID {a['pmid']}]** {a['title']}")
                    st.caption(a["abstract"])