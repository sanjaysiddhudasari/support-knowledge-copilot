from datetime import date
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

router = APIRouter(
    prefix="/api",
    tags=["Documents"],
)


RAW_DIR = Path("data/raw")

# 20 MB is generous for text documentation while keeping ingestion bounded.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

SUPPORTED_FORMATS_LABEL = "MD, TXT, PDF, DOCX, HTML"


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):

    if current_user.access_level != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required.",
        )

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required.",
        )

    # Prevent path traversal. The stored name is the bare filename only.
    filename = Path(file.filename).name

    if not filename or filename in {".", ".."}:
        raise HTTPException(
            status_code=400,
            detail="Filename is required.",
        )

    # Backend-side validation; the UI check is never trusted on its own.
    extension = Path(filename).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{extension or filename}'. "
                f"Supported formats: {SUPPORTED_FORMATS_LABEL}."
            ),
        )

    contents = await file.read()

    if not contents:
        raise HTTPException(
            status_code=400,
            detail="The uploaded document is empty.",
        )

    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                "The uploaded document exceeds the "
                f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB size limit."
            ),
        )

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = RAW_DIR / filename

    destination.write_bytes(
        contents
    )

    # Parse before indexing so malformed or scanned documents are rejected
    # cleanly instead of poisoning the index (and the file is removed again).
    try:

        load_document(str(destination))

    except UnsupportedFormatError as error:

        destination.unlink(missing_ok=True)

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except DocumentLoadError as error:

        destination.unlink(missing_ok=True)

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception:

        destination.unlink(missing_ok=True)

        raise HTTPException(
            status_code=400,
            detail="The uploaded document could not be parsed.",
        )

    try:

        indexer = __import__("app.retrieval.indexer", fromlist=["Indexer"]).Indexer()

        indexer.index_incremental(
            directory=str(RAW_DIR)
        )

    except Exception as error:

        # Surface a useful message without leaking stack traces.
        raise HTTPException(
            status_code=500,
            detail=(
                f"Document indexing failed: {error}"
            ),
        )

    return {
        "status": "success",
        "message": "Document uploaded and indexed.",
        "filename": filename,
        "indexed_at": str(date.today()),
    }
