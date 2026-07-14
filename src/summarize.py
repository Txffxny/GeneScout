"""
summarize.py
------------
Sends the gene + cancer-type-scoped abstracts to Claude and gets back a
structured, comprehensive research brief with full citations.

Design choices:
- Uses Sonnet 5, not Haiku -- synthesizing across ~10 abstracts into a
  genuinely non-generic, well-organized brief benefits from the stronger
  model; cost per query is still roughly 1-2 cents.
- The prompt requires explicit sections (mechanism, clinical relevance,
  therapeutic implications, evidence gaps) rather than one free-form
  paragraph, and requires the brief to actually draw from the full spread
  of abstracts provided, not just the first couple.
- Citations include first author, year, and journal (not just a bare PMID
  number), so the brief reads like an actual literature review rather than
  a list of anonymous reference tags.
- Still requires paraphrasing, never direct quotation -- same copyright-
  hygiene and readability rationale as before.
"""

import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODEL = "claude-sonnet-5"


def build_literature_brief(gene, cancer_type, articles):
    """
    Given a gene, a cancer type, and a list of article dicts (from
    pubmed.fetch_abstracts, including journal/year/first_author), return
    a structured research brief as a markdown string.

    Returns None if there are no articles to summarize.
    """
    if not articles:
        return None

    references = "\n\n".join(
        f"[{a['first_author']} et al., {a['year']}, {a['journal']}, PMID {a['pmid']}]\n"
        f"{a['title']}\n{a['abstract']}"
        for a in articles
    )

    prompt = f"""You are helping a cancer researcher quickly but thoroughly triage whether {gene} is worth investigating further in {cancer_type}.

Below are {len(articles)} PubMed abstracts about {gene} in {cancer_type}, each labeled with its citation. Write a structured research brief using the following sections, in this order:

## Mechanism
How {gene} functions in this cancer type -- its normal role and how that role is altered or exploited in {cancer_type}.

## Clinical Relevance
What these papers show about prognosis, disease subtypes, patient stratification, or biomarker value.

## Therapeutic Implications
Any treatment response, resistance mechanisms, or drug-target implications discussed.

## Evidence Gaps
Where the abstracts disagree, show mixed findings, or leave open questions -- name these explicitly rather than smoothing over them. If one section above has little or no supporting evidence in these abstracts, say so plainly instead of padding it.

Strict rules:
- Paraphrase and synthesize in your own words. Never quote any abstract directly, even briefly.
- Cite every claim using this exact format: (First Author et al., Year, Journal) [PMID xxxxxxxx] -- for example: (Smith et al., 2021, Nature Genetics) [PMID 12345678]. Use the citation exactly as labeled above each abstract; do not invent or abbreviate it differently.
- Draw from across the full set of {len(articles)} abstracts provided -- do not build the brief around only the first one or two and ignore the rest. If several abstracts say the same thing, cite them together; if one is an outlier, say so.
- Avoid generic filler sentences that could apply to any gene (e.g. "further research is needed" as a throwaway line). Every sentence should reflect something specific found in these particular abstracts.
- End with one sentence assessing whether this is an active, well-studied area or a sparse one, based only on what's in front of you.

Abstracts:

{references}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    # Sonnet 5 can include a "thinking" content block before the actual
    # text response, so content[0] isn't reliably the answer -- filter by
    # block type instead of assuming position.
    text_blocks = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_blocks) if text_blocks else None


if __name__ == "__main__":
    from pubmed import search_pubmed, fetch_abstracts

    gene = "TP53"
    cancer_type = "breast cancer"

    print(f"Searching PubMed for {gene} AND {cancer_type}...")
    pmids = search_pubmed(gene, cancer_type, retmax=10)
    print(f"  Found {len(pmids)} articles")

    print("Fetching abstracts...")
    articles = fetch_abstracts(pmids)

    print("Asking Claude to synthesize a brief...\n")
    brief = build_literature_brief(gene, cancer_type, articles)
    print(brief)