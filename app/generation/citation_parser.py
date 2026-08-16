import re

from app.models.answer import Citation

CITATION_PATTERN = re.compile(r"\[([^\[\]]+)\]")


def parse_citations(answer: str) -> list[Citation]:

    citations = []

    matches = list(CITATION_PATTERN.finditer(answer))

    for index, match in enumerate(matches):

        chunk_id = match.group(1).strip()

        # Text immediately before this citation
        text_before = answer[: match.start()]

        # Find the beginning of the current claim.
        # Prefer the most recent paragraph boundary.
        paragraphs = text_before.split("\n\n")

        claim = paragraphs[-1].strip()

        # If the citation is immediately after a code block,
        # the paragraph may contain only the code block.
        if claim.startswith("```") and claim.endswith("```"):

            if len(paragraphs) >= 2:
                claim = paragraphs[-2].strip()

        # Remove markdown code fences if they are accidentally
        # included in the claim.
        claim = claim.strip("`").strip()

        # Remove trailing citation(s) from the claim.
        claim = re.sub(
            r"\s*\[[^\[\]]+\]\s*$",
            "",
            claim,
        ).strip()

        # Never send an empty claim to the verifier.
        if not claim:
            claim = (
                "The answer cites the provided evidence for the preceding statement."
            )

        citations.append(
            Citation(
                chunk_id=chunk_id,
                claim=claim,
                supported=False,
            )
        )

    return citations
