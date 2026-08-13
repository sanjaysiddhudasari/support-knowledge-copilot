import re

from app.models.answer import Citation


CITATION_PATTERN = re.compile(
    r"\[([^\[\]]+)\]"
)


def parse_citations(answer: str) -> list[Citation]:

    citations = []

    for match in CITATION_PATTERN.finditer(answer):

        chunk_id = match.group(1).strip()

        text_before_citation = answer[
            :match.start()
        ]

        paragraphs = text_before_citation.split("\n\n")

        claim = paragraphs[-1].strip()

        citations.append(
            Citation(
                chunk_id=chunk_id,
                claim=claim,
                supported=False,
            )
        )

    return citations