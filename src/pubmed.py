"""
pubmed.py
---------
Searches PubMed for literature on a gene within a specific cancer type,
and fetches the abstracts for those results.

Key design choice: queries are always "{gene} AND {cancer_type}", not just
the gene alone. A bare gene search returns hundreds of loosely-related
hits; scoping to the cancer type the researcher already has in mind is
what makes the resulting literature brief actually useful.

Uses NCBI's E-utilities (esearch + efetch). Docs:
https://www.ncbi.nlm.nih.gov/books/NBK25501/

Reads NCBI_API_KEY from a .env file via python-dotenv -- never hard-code
the key directly in this file.
"""

import os
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
API_KEY = os.getenv("NCBI_API_KEY")


def search_pubmed(gene, cancer_type, retmax=10):
    """
    Search PubMed for articles mentioning both the gene and the cancer type.

    Returns a list of PMIDs (PubMed IDs) as strings -- these get passed
    into fetch_abstracts() next.

    Example:
        search_pubmed("TP53", "breast cancer")
    """
    query = f"{gene} AND {cancer_type}"
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": retmax,
        "sort": "relevance",
    }
    if API_KEY:
        params["api_key"] = API_KEY

    resp = requests.get(f"{BASE_URL}/esearch.fcgi", params=params)
    resp.raise_for_status()
    data = resp.json()
    return data.get("esearchresult", {}).get("idlist", [])


def fetch_abstracts(pmids):
    """
    Fetch title + abstract text for a list of PMIDs.

    Returns a list of dicts:
        [{"pmid": "12345678", "title": "...", "abstract": "..."}, ...]

    Articles with no abstract on record are skipped rather than returned
    with empty text -- an empty abstract is not useful input for the
    summarization step.
    """
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "rettype": "abstract",
    }
    if API_KEY:
        params["api_key"] = API_KEY

    resp = requests.get(f"{BASE_URL}/efetch.fcgi", params=params)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    results = []

    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        title_el = article.find(".//ArticleTitle")
        abstract_parts = article.findall(".//AbstractText")

        if pmid_el is None or not abstract_parts:
            continue

        abstract_text = " ".join(
            (part.text or "") for part in abstract_parts
        ).strip()

        if not abstract_text:
            continue

        results.append({
            "pmid": pmid_el.text,
            "title": (title_el.text if title_el is not None else "").strip(),
            "abstract": abstract_text,
        })

    return results


if __name__ == "__main__":
    print("Searching PubMed for TP53 AND breast cancer...")
    pmids = search_pubmed("TP53", "breast cancer", retmax=5)
    print(f"  Found {len(pmids)} PMIDs: {pmids}")

    if pmids:
        print("\nFetching abstracts...")
        articles = fetch_abstracts(pmids)
        for a in articles:
            print(f"\n  PMID {a['pmid']}: {a['title']}")
            print(f"    {a['abstract'][:150]}...")