"""Guards for the AcmeCloud golden evaluation dataset.

Validates the invariants the RAG eval harness depends on: chunk IDs in
`expected_chunks` must resolve against the chunk map, counts must match the
intended distribution, and answerable questions must obey the chunks contract.
Stdlib-only; no project dependencies required.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "data" / "golden"

EXPECTED_COUNTS = {
    "simple_factual": 15,
    "paraphrased": 10,
    "multi_chunk": 10,
    "multi_document": 10,
    "ambiguous": 5,
    "exact_keyword": 5,
    "outdated_conflicting": 5,
    "no_answer": 10,
}


def _load(name: str):
    with open(GOLDEN / name, encoding="utf-8") as f:
        return json.load(f)


def test_chunk_map_is_well_formed():
    cm = _load("chunk_map.json")
    assert cm["total_chunks"] == 106
    ids = [c["chunk_id"] for chunks in cm["documents"].values() for c in chunks]
    assert len(ids) == len(set(ids)) == 106


def test_dataset_counts_and_unique_ids():
    ds = _load("golden_dataset.json")
    assert len(ds) == 70
    assert len({q["id"] for q in ds}) == 70
    cats = {}
    for q in ds:
        cats[q["category"]] = cats.get(q["category"], 0) + 1
    assert cats == EXPECTED_COUNTS


def test_expected_chunks_resolve_and_contract():
    cm = _load("chunk_map.json")
    valid = {c["chunk_id"] for chunks in cm["documents"].values() for c in chunks}
    for q in _load("golden_dataset.json"):
        assert all(c in valid for c in q["expected_chunks"]), q["id"]
        if q["answerable"]:
            assert q["expected_chunks"], f"{q['id']}: answerable but empty chunks"
        else:
            assert q["expected_chunks"] == [], f"{q['id']}: unanswerable but has chunks"


def test_required_fields_present():
    for q in _load("golden_dataset.json"):
        for k in ("id", "question", "category", "answerable", "expected_chunks", "reasoning"):
            assert k in q, (q.get("id"), k)


if __name__ == "__main__":
    checks = (
        test_chunk_map_is_well_formed,
        test_dataset_counts_and_unique_ids,
        test_expected_chunks_resolve_and_contract,
        test_required_fields_present,
    )
    for fn in checks:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"all {len(checks)} checks passed")
