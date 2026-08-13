from pathlib import Path


SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md"}


def load_text_file(path: str) -> str:
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if file_path.suffix.lower() not in SUPPORTED_TEXT_EXTENSIONS:
        raise ValueError(
            f"Unsupported text file type: {file_path.suffix}"
        )

    return file_path.read_text(encoding="utf-8")


def load_document(path: str) -> str:
    file_path = Path(path)

    suffix = file_path.suffix.lower()

    if suffix in SUPPORTED_TEXT_EXTENSIONS:
        return load_text_file(path)

    raise ValueError(
        f"Unsupported document type: {suffix}"
    )