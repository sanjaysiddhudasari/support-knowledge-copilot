from datetime import date
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException

from app.retrieval.indexer import Indexer


router = APIRouter(
    prefix="/api",
    tags=["Documents"],
)


RAW_DIR = Path("data/raw")


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...)
):

    # Only Markdown for now.
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required.",
        )

    if not file.filename.lower().endswith(
        ".md"
    ):
        raise HTTPException(
            status_code=400,
            detail="Only Markdown (.md) files are supported.",
        )

    # Prevent path traversal.
    filename = Path(
        file.filename
    ).name

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = RAW_DIR / filename

    contents = await file.read()

    if not contents.strip():
        raise HTTPException(
            status_code=400,
            detail="The uploaded document is empty.",
        )

    destination.write_bytes(
        contents
    )

    try:

        indexer = Indexer()

        indexer.index_all_documents(
            directory=str(RAW_DIR)
        )

    except Exception as error:

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