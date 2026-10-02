"""Regression guards: the multi-format change must not alter the existing
Markdown corpus, its chunk IDs or the golden evaluation targets.
"""

import json
from datetime import date
from pathlib import Path

from app.ingestion.chunker import chunk_document
from app.ingestion.loader import load_document


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
MANIFEST = ROOT / "data" / "index" / "manifest.json"
CHUNK_MAP = ROOT / "data" / "golden" / "chunk_map.json"
GOLDEN_DATASET = ROOT / "data" / "golden" / "golden_dataset.json"


def _load(path: Path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _corpus_chunks():
    corpus = {}
    for path in sorted(RAW_DIR.iterdir()):
        if path.suffix.lower() == ".md":
            corpus[path.name] = chunk_document(load_document(str(path)))
    return corpus


def test_markdown_chunk_ids_match_committed_manifest():
    """Every existing Markdown document reproduces its committed chunk IDs."""

    manifest = _load(MANIFEST)["documents"]
    corpus = _corpus_chunks()

    assert set(corpus) == set(manifest)

    for filename, chunks in corpus.items():
        assert [
            chunk.chunk_ids for chunk in chunks
        ] == manifest[filename]["chunk_ids"], filename


def test_markdown_chunk_count_is_unchanged():
    corpus = _corpus_chunks()

    assert sum(len(chunks) for chunks in corpus.values()) == 120


def test_golden_chunk_map_still_resolves():
    """The 70-question evaluation's chunk map must still resolve exactly."""

    chunk_map = _load(CHUNK_MAP)
    corpus = _corpus_chunks()

    resolved = 0

    for document, entries in chunk_map["documents"].items():
        by_id = {
            chunk.chunk_ids: chunk.section
            for chunk in corpus[document]
        }

        for entry in entries:
            chunk_id = entry["chunk_id"]
            assert chunk_id in by_id, chunk_id
            assert by_id[chunk_id] == entry["heading"], chunk_id
            resolved += 1

    assert resolved == chunk_map["total_chunks"]


def test_all_golden_question_targets_are_producible():
    """Every expected_chunk in the 70-question set still exists."""

    dataset = _load(GOLDEN_DATASET)
    corpus = _corpus_chunks()

    available = {
        chunk.chunk_ids
        for chunks in corpus.values()
        for chunk in chunks
    }

    expected = {
        chunk_id
        for question in dataset
        for chunk_id in question["expected_chunks"]
    }

    assert expected <= available
    assert len(expected) > 0


def test_front_matter_regression():
    """Front matter parsing behaviour is unchanged for the corpus."""

    document = load_document(str(RAW_DIR / "authentication.md"))

    assert document.metadata["last_updated"] == date(2026, 7, 16)
    assert document.document_type == "guide"
    assert document.metadata["access_level"] == "public"
    assert document.text.startswith("# Authentication")
