import json
from pathlib import Path

from app.retrieval.indexer import Indexer


def create_file(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def create_manifest(path: Path, documents: dict):
    path.write_text(
        json.dumps({"documents": documents}, indent=2),
        encoding="utf-8",
    )


def test_new_files(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    manifest_path = tmp_path / "manifest.json"

    create_file(raw_dir / "auth.md", "# Authentication")
    create_file(raw_dir / "docker.md", "# Docker")

    indexer = Indexer(manifest_path=manifest_path)

    changes = indexer._get_changes(raw_dir)

    assert len(changes["new"]) == 2
    assert len(changes["modified"]) == 0
    assert len(changes["unchanged"]) == 0
    assert len(changes["deleted"]) == 0


def test_unchanged_files(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    manifest_path = tmp_path / "manifest.json"

    create_file(raw_dir / "auth.md", "# Authentication")

    indexer = Indexer(manifest_path=manifest_path)

    file_hash = indexer._calculate_hash(raw_dir / "auth.md")

    create_manifest(
        manifest_path,
        {
            "auth.md": {
                "content_hash": file_hash
            }
        },
    )

    changes = indexer._get_changes(raw_dir)

    assert len(changes["new"]) == 0
    assert len(changes["modified"]) == 0
    assert len(changes["unchanged"]) == 1
    assert len(changes["deleted"]) == 0


def test_modified_file(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    manifest_path = tmp_path / "manifest.json"

    create_file(raw_dir / "auth.md", "# Authentication")

    indexer = Indexer(manifest_path=manifest_path)

    old_hash = indexer._calculate_hash(raw_dir / "auth.md")

    create_manifest(
        manifest_path,
        {
            "auth.md": {
                "content_hash": old_hash
            }
        },
    )

    # Modify the document
    create_file(
        raw_dir / "auth.md",
        "# Authentication\n\nNew authentication information",
    )

    changes = indexer._get_changes(raw_dir)

    assert len(changes["new"]) == 0
    assert len(changes["modified"]) == 1
    assert len(changes["unchanged"]) == 0
    assert len(changes["deleted"]) == 0


def test_deleted_file(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    manifest_path = tmp_path / "manifest.json"

    create_file(raw_dir / "auth.md", "# Authentication")

    indexer = Indexer(manifest_path=manifest_path)

    file_hash = indexer._calculate_hash(raw_dir / "auth.md")

    create_manifest(
        manifest_path,
        {
            "auth.md": {
                "content_hash": file_hash
            }
        },
    )

    # Delete the document from disk
    (raw_dir / "auth.md").unlink()

    changes = indexer._get_changes(raw_dir)

    assert len(changes["new"]) == 0
    assert len(changes["modified"]) == 0
    assert len(changes["unchanged"]) == 0
    assert len(changes["deleted"]) == 1

    assert changes["deleted"][0] == "auth.md"


def test_mixed_changes(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    manifest_path = tmp_path / "manifest.json"

    # Current documents
    create_file(raw_dir / "auth.md", "# Authentication")
    create_file(raw_dir / "docker.md", "# Docker\nUpdated")
    create_file(raw_dir / "faq.md", "# FAQ")
    create_file(raw_dir / "new.md", "# New Document")

    indexer = Indexer(manifest_path=manifest_path)

    # Create hashes representing the PREVIOUS state
    auth_hash = indexer._calculate_hash(raw_dir / "auth.md")
    faq_hash = indexer._calculate_hash(raw_dir / "faq.md")

    # docker.md gets an intentionally different old hash
    old_docker_hash = "old-docker-hash"

    create_manifest(
        manifest_path,
        {
            "auth.md": {
                "content_hash": auth_hash
            },
            "docker.md": {
                "content_hash": old_docker_hash
            },
            "faq.md": {
                "content_hash": faq_hash
            },
            "deleted.md": {
                "content_hash": "some-old-hash"
            },
        },
    )

    changes = indexer._get_changes(raw_dir)

    assert {p.name for p in changes["new"]} == {"new.md"}

    assert {p.name for p in changes["modified"]} == {
        "docker.md"
    }

    assert {p.name for p in changes["unchanged"]} == {
        "auth.md",
        "faq.md",
    }

    assert set(changes["deleted"]) == {
        "deleted.md"
    }