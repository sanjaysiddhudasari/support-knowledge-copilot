from app.generation.citation_parser import parse_citations


answer = """
The standard API rate limit is 1,000 requests per minute per API key.
[api.md_chunk_7] [troubleshooting.md_chunk_6]
"""

citations = parse_citations(answer)

for citation in citations:
    print("CHUNK:", citation.chunk_id)
    print("CLAIM:", citation.claim)
    print()