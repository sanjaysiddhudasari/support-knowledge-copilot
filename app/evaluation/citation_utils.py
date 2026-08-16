def deduplicate_citations(citations):
    """
    Remove duplicate citations referring to the same
    chunk and same claim.
    """

    seen = set()
    unique = []

    for citation in citations:

        key = (
            citation.chunk_id,
            citation.claim.strip(),
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(citation)

    return unique