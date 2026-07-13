"""
summarize.py
------------
Sends the gene + cancer-type-scoped abstracts to Claude and gets back a
synthesized research brief.

Key design choice: the prompt explicitly instructs Claude to synthesize
findings in its own words and cite PMIDs rather than quote the abstracts
directly. This is both a copyright-hygiene practice and, more importantly,
produces a more genuinely useful brief -- a researcher wants the synthesized
meaning across papers, not a pile of stitched-together quotes.

Uses the anthropic Python SDK. Reads ANTHROPIC_API_KEY from .env.
"""

import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Haiku is the right choice here: this is a summarization task over a
# handful of abstracts, not complex multi-step reasoning, so the fastest/
# cheapest model gives essentially the same quality at a fraction of the
# cost -- important for a project you'll be running many times while testing.
MODEL = "claude-haiku-4-5-20251001"


def build_literature_brief(gene, cancer_type, articles):
    """
    Given a gene, a cancer type, and a list of article dicts (from
    pubmed.fetch_abstracts), return a synthesized research brief as a
    string.

    Returns None if there are no articles to summarize (caller should
    handle this case in the UI -- e.g. "no literature found for this
    gene/cancer type combination").
    """
    if not articles:
        return None

    references = "\n\n".join(
        f"[PMID {a['pmid']}] {a['title']}\n{a['abstract']}"
        for a in articles
    )

    prompt = f"""You are helping a cancer researcher quickly triage whether {gene} is worth investigating further in {cancer_type}.

Below are {len(articles)} PubMed abstracts about {gene} in {cancer_type}. Write a short research brief (roughly 150-250 words) that synthesizes what these papers collectively say about the gene's role in this cancer type.

Strict rules:
- Paraphrase and synthesize in your own words. Do not quote any abstract directly, even briefly.
- Cite the PMID in brackets after each claim, e.g. [PMID 12345678].
- If the abstracts disagree or show mixed findings, say so explicitly rather than smoothing over it.
- End with one sentence flagging whether this looks like an active, well-studied area or a sparse one, based only on what's in front of you.

Abstracts:

{references}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text


if __name__ == "__main__":
    from pubmed import search_pubmed, fetch_abstracts

    gene = "TP53"
    cancer_type = "breast cancer"

    print(f"Searching PubMed for {gene} AND {cancer_type}...")
    pmids = search_pubmed(gene, cancer_type, retmax=5)
    print(f"  Found {len(pmids)} articles")

    print("Fetching abstracts...")
    articles = fetch_abstracts(pmids)

    print("Asking Claude to synthesize a brief...\n")
    brief = build_literature_brief(gene, cancer_type, articles)
    print(brief)