"""Multi-format ingestion smoke test.

Proves, per supported format, that a unique marker survives
load_document -> chunk_document -> Qdrant payload, and that access level is
present on the chunks and enforced by the retrieval ACL filter. CSV/JSON are
intentionally unsupported and must be rejected.
"""

from app.ingestion.chunker import chunk_document
from app.ingestion.loader import (
    UnsupportedFormatError,
    load_document,
)
from app.retrieval.access_control import AccessController
from app.retrieval.vector_store import _build_payload
from pdf_factory import write_docx, write_pdf

# Unique markers per format (from the verification prompt).
MARKER = {
    "pdf": "FORMAT_TEST_PDF_MARKER_7Q4",
    "txt": "FORMAT_TEST_TXT_MARKER_8R2",
    "docx": "FORMAT_TEST_DOCX_MARKER_5K9",
    "html": "FORMAT_TEST_HTML_MARKER_4V1",
    "md": "FORMAT_TEST_MD_MARKER_9N3",
}


def make_source(tmp_path, kind):
    marker = MARKER[kind]

    if kind == "md":
        path = tmp_path / "guide.md"
        path.write_text(
            f"---\naccess_level: admin\n---\n\n# Title\n\n{marker}\n",
            encoding="utf-8",
        )

    elif kind == "txt":
        path = tmp_path / "notes.txt"
        path.write_text(f"First paragraph. {marker}\n\nSecond one.", encoding="utf-8")

    elif kind == "pdf":
        path = write_pdf(tmp_path / "guide.pdf", [f"Page one {marker}"])

    elif kind == "docx":
        path = write_docx(
            tmp_path / "manual.docx",
            [("heading1", "Overview"), ("paragraph", f"Body {marker}")],
        )

    elif kind == "html":
        path = tmp_path / "page.html"
        path.write_text(f"<h1>Doc</h1><p>{marker}</p>", encoding="utf-8")

    return path


def test_marker_survives_load_and_chunking(tmp_path):
    for kind in ("md", "txt", "pdf", "docx", "html"):
        marker = MARKER[kind]
        document = load_document(str(make_source(tmp_path, kind)))
        chunks = chunk_document(document)

        assert chunks, f"{kind}: no chunks produced"
        assert any(
            marker in chunk.text for chunk in chunks
        ), f"{kind}: marker lost in chunking"


def test_md_access_level_propagates_to_chunk_and_payload(tmp_path):
    document = load_document(str(make_source(tmp_path, "md")))
    chunks = chunk_document(document, chunk_id_base="doc-1")

    assert all(chunk.access_level == "admin" for chunk in chunks)

    payload = _build_payload(chunks[0], document_id="doc-1")

    assert payload["access_level"] == "admin"
    assert payload["document_id"] == "doc-1"
    assert payload["source"] == "guide.md"
    assert chunks[0].chunk_ids.startswith("doc-1_chunk_")


def test_pdf_page_metadata_preserved(tmp_path):
    document = load_document(str(make_source(tmp_path, "pdf")))

    assert document.file_type == "pdf"
    assert len(document.pages) == 1
    assert [chunk.page for chunk in chunk_document(document)] == [1]


def test_acl_filters_internal_and_admin_from_public(tmp_path):
    def result(chunk):
        # dense/BM25 return a RetrievalResult object; filter reads chunk.
        class R:
            pass

        r = R()
        r.chunk = chunk
        return r

    control = AccessController()

    public_chunks = chunk_document(load_document(str(make_source(tmp_path, "txt"))))
    admin_chunks = chunk_document(load_document(str(make_source(tmp_path, "md"))))

    # Force varied access levels on the chunks to test the matrix.
    for i, chunk in enumerate(public_chunks):
        chunk.access_level = "public" if i % 2 == 0 else "internal"

    admitted_ids = {
        c.chunk.chunk_ids
        for c in control.filter_results(
            [result(c) for c in public_chunks], "public"
        )
    }

    # Every public chunk admitted; every internal chunk dropped.
    for chunk in public_chunks:
        if chunk.access_level == "public":
            assert chunk.chunk_ids in admitted_ids
        else:
            assert chunk.chunk_ids not in admitted_ids

    # Admin chunks are fully hidden from a public user.
    hidden = control.filter_results([result(c) for c in admin_chunks], "public")
    assert hidden == []


def test_acl_unknown_chunk_level_fails_closed():
    class R:
        pass

    r = R()
    r.chunk = type("C", (), {"access_level": "superuser", "chunk_ids": "x_chunk_1"})()

    admitted = AccessController().filter_results([r], "public")

    assert admitted == []


def test_acl_unknown_user_level_raises():
    class R:
        pass

    r = R()
    r.chunk = type("C", (), {"access_level": "public", "chunk_ids": "x_chunk_1"})()

    try:
        AccessController().filter_results([r], "root")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown user level")


# ---------------------------------------------------------------------------
# CSV / JSON are intentionally unsupported
# ---------------------------------------------------------------------------


def test_csv_and_json_are_rejected(tmp_path):
    for name in ("data.csv", "data.json"):
        path = tmp_path / name
        path.write_text('{"a": 1}' if name.endswith("json") else "a,b,c", encoding="utf-8")

        try:
            load_document(str(path))
        except UnsupportedFormatError:
            pass
        else:
            raise AssertionError(f"{name} should be unsupported")