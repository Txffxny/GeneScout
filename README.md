🧬 GeneScout July-14-2026 Tiffany Natalia Lewis Portfolio Piece; TiffanyNataliaLewis@gmail.com

This is a personal portfolio project, not a peer-reviewed clinical tool; outputs should help inform, not replace, primary literature review.

Triage a gene's role in a specific cancer type in under a minute: mutation frequency, CRISPR dependency data, and a synthesized literature brief, pulled live from cBioPortal, DepMap, and PubMed, with the literature review written by Claude.

Built as a portfolio project exploring how LLMs can be applied usefully, not gimmicky, to potential real biomedical research workflows.


Why this exists

*Researchers (like myself) evaluating a candidate gene typically cross-reference several sources by hand: is it mutated in this cancer? Is it functionally essential, even if rarely mutated? What does recent literature actually say? GeneScout attempts to automate that triage step, with two design decisions that came from actually building and testing it against real data rather than assuming upfront:


*Every query is scoped to a specific cancer type, not run pan-cancer. A researcher asking about a gene almost always already has a pathology in mind — a generic "TP53 across all cancers" summary is less useful than "TP53 in breast cancer specifically." This shapes every data source: PubMed queries are "{gene}" AND "{cancer_type}", not the gene alone; DepMap dependency stats are computed only against matching cell lines; cBioPortal mutation frequency uses the best-matching individual study rather than an aggregate.

*A gene-first tool is useless to someone who doesn't have a gene in mind yet. The original design only worked if you already knew what to search for. Discover mode flips this: give it just a cancer type, and it computes a differential-dependency test across all ~18,500 genes in the DepMap CRISPR screen at once (a proper Welch's t-test, vectorized, not a loop), surfacing candidates a researcher could investigate without naming a gene first — the same "volcano plot" logic used in real differential expression/essentiality analysis.



Features

Analyze a specific gene:


📄 Literature Brief — Claude synthesizes ~10 recent PubMed abstracts into a structured brief (Mechanism / Clinical Relevance / Therapeutic Implications / Evidence Gaps), citing (Author et al., Year, Journal) with linked PMIDs; never verbatim-quoted, always paraphrased and attributed

🧬 Mutation Frequency — live cBioPortal query, plus a breakdown of mutation types (missense, nonsense, frameshift, etc.) as a pie chart

🎯 Dependency (DepMap) — % of matching cell lines strongly dependent on the gene, mean Chronos dependency score, and a per-cell-line bar chart showing the actual distribution behind that number


Discover candidate genes:


🌋 Volcano plot: mean dependency difference vs. statistical significance, across every gene in the screen, for cell lines matching a cancer type
Ranked table of top candidates — a genuine "I don't know what I'm looking for yet" entry point



A real example this project surfaced

Querying IRF4 in multiple myeloma turned into an accidental but genuinely instructive case study: only 1.9% mutation frequency, yet 100% of tested myeloma cell lines are strongly dependent on it (mean Chronos score −2.1), and the literature brief explains why — IRF4 is a master transcriptional regulator of plasma cell identity, essential through overexpression and pathway dysregulation rather than mutation. All three data sources tell a coherent, complementary story here, which is the kind of result the tool is actually designed to surface.


Tech stack


Streamlit — UI
Claude (Sonnet 5) via the Anthropic API — literature synthesis
cBioPortal REST API — mutation data (no key required)
NCBI E-utilities — PubMed search/fetch
DepMap (Broad Institute) — CRISPR knockout dependency data (local files, no public API for this dataset)
pandas / scipy / altair — data wrangling, statistics, charts



Setup

bashgit clone https://github.com/Txffxny/GeneScout.git
cd GeneScout
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

API keys

Create a .env file in the project root:

NCBI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here


NCBI key: free, from your NCBI account → Account Settings → API Key Management (raises the shared rate limit; not required to run, but recommended)
Anthropic key: from platform.claude.com — required for the literature brief feature. Cost is small: roughly 1-2 cents per query on Sonnet 5.


DepMap data (required for the Dependency tab and Discover mode)

These files are too large for the repo and must be downloaded manually:


Go to depmap.org/portal/data_page/?tab=currentRelease
Download CRISPRGeneEffect.csv (under "CRISPR KO screens (Broad)") and Model.csv
Place both in a data/ folder in the project root


Run it

bashstreamlit run app.py


Known limitations


cBioPortal mutation frequency uses the single largest matching study, not an aggregate across all matching studies — a deliberate simplicity tradeoff, not an oversight, but worth knowing if a cancer type has multiple large cohorts with differing results

Discover mode's p-values are not corrected for multiple testing across ~18,500 simultaneous comparisons — a proper implementation would apply an FDR correction (e.g. Benjamini-Hochberg); treat the ranked list as a starting point for investigation, not a statistically rigorous gene list
Cancer type matching is text-based (Oncotree lineage/disease/subtype fields), not a curated ontology lookup — very rare or newly-named cancer types may not match well

No true motif/domain-based gene search — if you know a protein feature but not a gene name, this tool doesn't help (yet); see Roadmap



Roadmap

-Multi-gene comparison view
-Pan-cancer comparison toggle (one gene across many cancer types)
F-DR-corrected discovery mode
-A second, separate app for true motif/domain-based gene discovery (UniProt/InterPro), rather than folding an unrelated data domain into this tool
-Visual design pass (currently default Streamlit theming)



Data attribution

DepMap, Broad (2025). DepMap Public 25Q3. Dataset. depmap.org
Cerami et al. Cancer Discov 2012; Gao et al. Sci. Signal. 2013 (cBioPortal)
NCBI PubMed / E-utilities


