from datetime import date
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from app.auth.models import User
from app.auth.dependencies import get_current_user
from app.ingestion.loader import (
    SUPPORTED_EXTENSIONS,
    DocumentLoadError,
    UnsupportedFormatError,
    load_document,
)
from app.services.document_storage import (
    DocumentAccessDenied,
    DocumentError,
    DocumentNotFound,
    DocumentService,
)

router = APIRouter(
    prefix="/api",
    tags=["Documents"],
)

# 20 MB is generous for text documentation while keeping ingestion bounded.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

SUPPORTED_FORMATS_LABEL = "MD, TXT, PDF, DOCX, HTML"

_service: DocumentService | None = None


def get_document_service() -> DocumentService:
    global _service

    if _service is None:
        _service = DocumentService()

    return _service


def _get_indexer():
    return __import__(
        "app.retrieval.indexer", fromlist=["Indexer"]
    ).Indexer()


def _index_documents(path: Path, version: int, content_hash: str | None):
    """Chunk and index one uploaded file via the existing loaders/chunkers.

    Uses the per-file path (rebuild.index_uploaded_file), NOT
    Indexer.index_incremental: that diffs the whole directory against the
    manifest and would mark every other corpus document as deleted when
    pointed at a temp dir.
    """

    from app.retrieval.rebuild import index_uploaded_file

    return index_uploaded_file(
        path, version=version, content_hash=content_hash
    )


def _parse_error(error: Exception) -> HTTPException:
    if isinstance(error, UnsupportedFormatError):
        return HTTPException(status_code=400, detail=str(error))

    if isinstance(error, DocumentLoadError):
        return HTTPException(status_code=400, detail=str(error))

    return HTTPException(
        status_code=400,
        detail="The uploaded document could not be parsed.",
    )


def _validate(file: UploadFile) -> tuple[str, bytes]:
    if not file.filename:
        raise HTTPException(400, "Filename is required.")

    clean = Path(file.filename).name

    if not clean or clean in {".", ".."}:
        raise HTTPException(400, "Filename is required.")

    extension = Path(clean).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            400,
            (
                f"Unsupported file type '{extension or clean}'. "
                f"Supported formats: {SUPPORTED_FORMATS_LABEL}."
            ),
        )

    contents = file.file.read() if hasattr(file, "file") else file.read()

    if not contents:
        raise HTTPException(400, "The uploaded document is empty.")

    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            (
                "The uploaded document exceeds the "
                f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB size limit."
            ),
        )

    return clean, contents


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
):
    """Upload -> Storage -> Postgres -> existing ingestion -> Qdrant + BM25."""

    if current_user.access_level != "admin":
        raise HTTPException(403, "Admin access required.")

    clean_name, contents = _validate(file)

    # Parse before storing anything so malformed/scanned files are rejected
    # without touching Storage or the index.
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / clean_name
        probe.write_bytes(contents)

        try:
            loaded = load_document(str(probe))
        except (UnsupportedFormatError, DocumentLoadError) as error:
            raise _parse_error(error)
        except Exception as error:
            raise _parse_error(error)

        try:
            document = service.upload(
                user_id=current_user.id,
                filename=clean_name,
                data=contents,
                file_type=loaded.file_type,
            )
        except DocumentError as error:
            raise HTTPException(503, f"Document storage failed: {error}")

        try:
            # Re-download through the service so the indexed bytes are the
            # stored bytes, not just the request body.
            stored_path = service.download(
                current_user.id, document["id"], tmp
            )

            _index_documents(
                stored_path,
                version=document["version"],
                content_hash=document["content_hash"],
            )

            service.mark_status(current_user.id, document["id"], "ready")

        except Exception as error:
            service.mark_status(current_user.id, document["id"], "failed")

            raise HTTPException(
                500,
                f"Document indexing failed: {error}",
            )

    return {
        "status": "success",
        "message": "Document uploaded and indexed.",
        "document_id": document["id"],
        "filename": document["filename"],
        "file_type": loaded.file_type,
        "version": document["version"],
        "indexed_at": str(date.today()),
    }


# Backwards-compatible alias for the previous endpoint path.
@router.post("/documents")
async def upload_document_legacy(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
):
    return await upload_document(
        file=file,
        current_user=current_user,
        service=service,
    )


@router.get("/documents")
def list_documents(
    current_user: User = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
):
    return service.list_documents(current_user.id)


@router.get("/documents/{document_id}")
def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
):
    try:
        return service.get_document(current_user.id, document_id)
    except DocumentNotFound:
        raise HTTPException(404, "Document not found")
    except DocumentError as error:
        raise HTTPException(503, f"Document storage failed: {error}")


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
):
    """Delete metadata + blob + Qdrant chunks, then rebuild BM25."""

    try:
        row = service.delete_document(current_user.id, document_id)
    except DocumentNotFound:
        raise HTTPException(404, "Document not found")
    except DocumentError as error:
        raise HTTPException(503, f"Document storage failed: {error}")

    try:
        from app.retrieval.rebuild import remove_document_chunks

        remove_document_chunks(row)
    except Exception as error:
        # Metadata/blob deletion succeeded; index cleanup failed.
        raise HTTPException(
            500,
            f"Document deleted but index cleanup failed: {error}",
        )

    return {"status": "deleted", "document_id": document_id}


@router.post("/documents/reindex")
def reindex_documents(
    current_user: User = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
):
    """Rebuild derived indexes (BM25) from durable documents.

    Admin-only today: the corpus is shared, so one user's rebuild covers all
    documents in the manifest.
    """

    if current_user.access_level != "admin":
        raise HTTPException(403, "Admin access required.")

    from app.retrieval.rebuild import rebuild_bm25

    with tempfile.TemporaryDirectory() as tmp:
        try:
            result = rebuild_bm25(service, current_user.id, tmp)
        except DocumentError as error:
            raise HTTPException(503, f"Reindex failed: {error}")
        except Exception as error:
            raise HTTPException(
                500,
                f"Reindex failed: {error}",
            )

    return result
