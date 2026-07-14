"""
cbioportal.py
--------------
Handles all queries to the public cBioPortal REST API.

Key design choice: every mutation-frequency query is scoped to a specific
cancer type (a "study" in cBioPortal's terms), not run pan-cancer by default.
This mirrors how a researcher actually approaches a gene -- with a pathology
already in mind.

API docs: https://www.cbioportal.org/api/swagger-ui/index.html
No API key required for the public instance.
"""

import requests

BASE_URL = "https://www.cbioportal.org/api"


def list_cancer_studies():
    """
    Fetch all public studies on cBioPortal.

    Returns a list of dicts like:
        {"studyId": "brca_tcga_pan_can_atlas_2018",
         "name": "Breast Invasive Carcinoma (TCGA, PanCancer Atlas)",
         "cancerType": {"name": "Breast Cancer", ...}}
    """
    resp = requests.get(f"{BASE_URL}/studies", params={"projection": "SUMMARY"})
    resp.raise_for_status()
    return resp.json()


def find_studies_by_cancer_type(cancer_type_query):
    """
    Filter studies whose display name or cancer-type name contains the
    search term. This is what powers the cancer-type dropdown in the UI --
    call this once at app startup, cache the result, and populate the
    dropdown from it rather than hard-coding study IDs.

    Example:
        find_studies_by_cancer_type("breast")
    """
    query = cancer_type_query.lower()
    studies = list_cancer_studies()
    matches = [
        s for s in studies
        if query in s.get("name", "").lower()
        or query in s.get("cancerType", {}).get("name", "").lower()
    ]

    # Rank by sample count (largest first) so well-powered, well-known studies
    # (e.g. TCGA PanCancer Atlas cohorts) surface before small niche subtype
    # studies with only a handful of samples. cBioPortal's SUMMARY projection
    # already includes allSampleCount, so no extra API calls are needed.
    matches.sort(key=lambda s: s.get("allSampleCount", 0), reverse=True)
    return matches


def get_entrez_id(hugo_symbol):
    """Look up the Entrez gene ID cBioPortal needs internally for a HUGO symbol."""
    resp = requests.get(f"{BASE_URL}/genes/{hugo_symbol}")
    resp.raise_for_status()
    return resp.json()["entrezGeneId"]


def get_study_sample_ids(study_id):
    """All sample IDs in a given study -- needed as the denominator for frequency."""
    resp = requests.get(
        f"{BASE_URL}/studies/{study_id}/samples",
        params={"projection": "ID"},
    )
    resp.raise_for_status()
    return [s["sampleId"] for s in resp.json()]


def get_mutation_frequency(hugo_symbol, study_id):
    """
    Core function: what fraction of samples in this specific cancer study
    carry a mutation in this gene?

    Most TCGA-derived studies expose a molecular profile named
    "{study_id}_mutations" -- this is the conventional naming pattern,
    though a small number of studies deviate from it. If this raises a
    404, the fix is to fetch `/studies/{study_id}/molecular-profiles`
    and pick the one with molecularAlterationType == "MUTATION_EXTENDED".

    Uses DETAILED projection (rather than SUMMARY) specifically to
    guarantee the mutationType field is present for each record -- this
    is what powers the mutation-type breakdown chart.

    Returns:
        {
          "gene": "TP53",
          "study_id": "brca_tcga_pan_can_atlas_2018",
          "total_samples": 1084,
          "mutated_samples": 371,
          "frequency_pct": 34.2,
          "mutations": [...]   # raw mutation records, incl. mutationType
        }
    """
    entrez_id = get_entrez_id(hugo_symbol)
    molecular_profile_id = f"{study_id}_mutations"
    sample_ids = get_study_sample_ids(study_id)
    total_samples = len(sample_ids)

    if total_samples == 0:
        return {
            "gene": hugo_symbol,
            "study_id": study_id,
            "total_samples": 0,
            "mutated_samples": 0,
            "frequency_pct": 0.0,
            "mutations": [],
        }

    resp = requests.post(
        f"{BASE_URL}/molecular-profiles/{molecular_profile_id}/mutations/fetch",
        params={"projection": "DETAILED"},
        json={"entrezGeneIds": [entrez_id], "sampleIds": sample_ids},
    )
    resp.raise_for_status()
    mutations = resp.json()

    mutated_samples = {m["sampleId"] for m in mutations}
    frequency_pct = round(100 * len(mutated_samples) / total_samples, 1)

    return {
        "gene": hugo_symbol,
        "study_id": study_id,
        "total_samples": total_samples,
        "mutated_samples": len(mutated_samples),
        "frequency_pct": frequency_pct,
        "mutations": mutations,
    }


def get_mutation_type_breakdown(mutations):
    """
    Given the raw mutation records from get_mutation_frequency, count how
    many fall into each mutationType category (e.g. Missense_Mutation,
    Nonsense_Mutation, Frame_Shift_Del) -- this is the data behind the
    mutation-type pie chart.

    Falls back to "Unknown" for any record missing the field, rather than
    raising, since field completeness can vary slightly between studies.

    Returns a dict: {"Missense_Mutation": 12, "Nonsense_Mutation": 3, ...}
    """
    counts = {}
    for m in mutations:
        mutation_type = m.get("mutationType") or "Unknown"
        counts[mutation_type] = counts.get(mutation_type, 0) + 1
    return counts


if __name__ == "__main__":
    # Quick manual smoke test -- run `python cbioportal.py` to sanity check
    # the pipeline end to end before wiring anything into Streamlit.
    print("Searching for breast cancer studies...")
    studies = find_studies_by_cancer_type("breast")
    for s in studies[:5]:
        print(f"  {s['studyId']}  --  {s['name']}")

    if studies:
        test_study = studies[0]["studyId"]
        print(f"\nChecking TP53 mutation frequency in {test_study}...")
        result = get_mutation_frequency("TP53", test_study)
        print(
            f"  {result['mutated_samples']}/{result['total_samples']} samples "
            f"({result['frequency_pct']}%) carry a TP53 mutation"
        )