"""
pubmed.py
---------
Searches PubMed for literature on a gene within a specific cancer type,
and fetches the abstracts (plus citation metadata) for those results.

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
import re
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


def _extract_year(article):
    """
    Publication year lives in different places depending on how the
    journal issue was catalogued. Try the clean <Year> field first, then
    fall back to pulling a 4-digit year out of <MedlineDate> (used for
    entries like "2020 Jan-Feb" that don't have a separate Year field).
    """
    year_el = article.find(".//Journal/JournalIssue/PubDate/Year")
    if year_el is not None and year_el.text:
        return year_el.text

    medline_date_el = article.find(".//Journal/JournalIssue/PubDate/MedlineDate")
    if medline_date_el is not None and medline_date_el.text:
        match = re.search(r"\d{4}", medline_date_el.text)
        if match:
            return match.group(0)

    return "n.d."


def _extract_first_author(article):
    """
    Returns a display-friendly first author string, e.g. "Smith J".
    Falls back to a group/collective name (common for consortium papers)
    if no individual author is listed.
    """
    author_el = article.find(".//AuthorList/Author")
    if author_el is None:
        return "Unknown"

    collective_el = author_el.find("CollectiveName")
    if collective_el is not None and collective_el.text:
        return collective_el.text

    last_name_el = author_el.find("LastName")
    initials_el = author_el.find("Initials")
    last_name = last_name_el.text if last_name_el is not None else ""
    initials = initials_el.text if initials_el is not None else ""
    name = f"{last_name} {initials}".strip()
    return name if name else "Unknown"

def fetch_abstracts(pmids):
    """
    Fetch title, abstract, and citation metadata for a list of PMIDs.

    Returns a list of dicts:
        [{
            "pmid": "12345678",
            "title": "...",
            "abstract": "...",
            "journal": "Nature Genetics",
            "year": "2021",
            "first_author": "Smith J",
        }, ...]

    Articles with no abstract on record (common for older or non-primary-
    research entries) are skipped rather than returned with empty text --
    an empty abstract is not useful input for the summarization step.
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
        journal_el = article.find(".//Journal/Title")

        if pmid_el is None or not abstract_parts:
            continue

        abstract_text = " ".join(
            "".join(part.itertext()) for part in abstract_parts
        ).strip()

        if not abstract_text:
            continue

        title_text = "".join(title_el.itertext()).strip() if title_el is not None else ""

        results.append({
            "pmid": pmid_el.text,
            "title": title_text,
            "abstract": abstract_text,
            "journal": journal_el.text if journal_el is not None else "Unknown journal",
            "year": _extract_year(article),
            "first_author": _extract_first_author(article),
        })

    return results


if __name__ == "__main__":
    # Quick manual smoke test -- run `python src/pubmed.py`
    print("Searching PubMed for TP53 AND breast cancer...")
    pmids = search_pubmed("TP53", "breast cancer", retmax=5)
    print(f"  Found {len(pmids)} PMIDs: {pmids}")

    if pmids:
        print("\nFetching abstracts...")
        articles = fetch_abstracts(pmids)
        for a in articles:
            print(f"\n  {a['first_author']} et al., {a['year']}, {a['journal']}")
            print(f"  PMID {a['pmid']}: {a['title']}")
            print(f"    {a['abstract'][:150]}...")