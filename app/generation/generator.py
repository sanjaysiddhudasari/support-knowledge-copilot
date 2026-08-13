import os

from dotenv import load_dotenv
from openai import OpenAI

from app.models.answer import GeneratedAnswer
from app.generation.citation_parser import parse_citations

class AnswerGenerator:

    def __init__(
        self,
        model: str = "deepseek-v4-flash",
    ):
        load_dotenv()

        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing DeepSeek credentials. Set DEEPSEEK_API_KEY in the "
                "project .env file or in your environment before starting the app."
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
        )

        self.model = model

    def generate(
        self,
        query: str,
        results,
    ) -> GeneratedAnswer:

        context_parts = []

        for result in results:

            chunk = result["chunk"]

            context_parts.append(
                f"""
[CHUNK_ID: {chunk.chunk_ids}]
[SECTION: {chunk.section}]
[SOURCE: {chunk.source}]

{chunk.text}
"""
            )

        context = "\n\n".join(context_parts)

        prompt = f"""
You are a support knowledge assistant.

Answer the user's question using ONLY the provided
documentation.

Rules:
1. Do not use outside knowledge.
2. Do not invent information.
3. Every factual claim must have a citation.
4. Every factual claim must have a citation.
5. Only include information that directly helps answer the user's question.
6. Do not include unrelated facts from the documentation.
7. If the documentation does not contain enough information,
   clearly say that you could not verify the answer.

User question:
{query}

Documentation:
{context}

Return the answer with citations in this format:

[chunk_id]

Example:
You can reset your password from Account Settings.
[password-policy.md_chunk_2]
"""

        response = self.client.responses.create(
            model=self.model,
            input=prompt,
        )

        answer = response.output_text
        citations=parse_citations(answer)

        return GeneratedAnswer(
            answer=answer,
            citations=citations,
        )
