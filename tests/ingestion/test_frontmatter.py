"""Front matter behaviour: declared access levels parse; mangled headers fail."""

import pytest

from app.ingestion.frontmatter import FrontMatterError, parse_front_matter
from app.ingestion.loader import DocumentLoadError, load_document

# Every repo doc that declares a front matter access level must load it --
# a doc whose header says "public" must never silently become the default
# "internal" (the regression this guards against).
FRONTMATTER_EXPECTATIONS = {
    "public-test.md": "public",
    "admin-test.md": "admin",
    "internal-test.md": "internal",
}


@pytest.mark.parametrize(
    "filename,expected",
    FRONTMATTER_EXPECTATIONS.items(),
)
def test_declared_frontmatter_access_level_is_preserved(filename, expected):
    loaded = load_document(f"data/raw/{filename}")

    assert loaded.metadata["access_level"] == expected

    # And the chunks it produces carry that level into the index.
    from app.ingestion.chunker import chunk_document

    chunks = chunk_document(loaded)

    assert chunks
    assert all(chunk.access_level == expected for chunk in chunks)


def test_utils_without_frontmatter_default_to_internal():
    assert parse_front_matter("# just a heading")["access_level"] == "internal"


def test_escaped_frontmatter_raises_not_defaults():
    """A markdown-escaped \\--- header must fail loudly, never fall back."""

    mangled = "\\---\n\naccess\\_level: public\n\n---\n"

    with pytest.raises(FrontMatterError):
        parse_front_matter(mangled)


def test_unclosed_frontmatter_raises():
    with pytest.raises(FrontMatterError):
        parse_front_matter("---\naccess_level: public\n")  # no closing fence


def test_load_document_rejects_mangled_frontmatter(tmp_path):
    """The loader surfaces it as DocumentLoadError (-> 400 on upload)."""

    bad = tmp_path / "bad.md"
    bad.write_text("\\---\n\naccess\\_level: admin\n\n---\n", encoding="utf-8")

    with pytest.raises(DocumentLoadError):
        load_document(str(bad))