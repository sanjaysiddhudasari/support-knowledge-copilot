import os
import time

from dotenv import load_dotenv
from openai import OpenAI

from app.models.answer import GeneratedAnswer
from app.generation.citation_parser import parse_citations
from app.evaluation.citation_utils import (
    deduplicate_citations,
)
from app.observability.tracing import span, usage_metadata

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

    def _build_context(self, results) -> str:
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
        return "\n\n".join(context_parts)

    def _build_prompt(self, query: str, context: str) -> str:
        return f"""
You are a support knowledge assistant.

Answer the user's question using ONLY the provided
documentation.

Rules:
1. Do not use outside knowledge.
2. Do not invent information.
3. Only include information that directly helps answer the user's question.
4. Do not include unrelated facts from the documentation.
5. If the documentation does not contain enough information,
   clearly say that you could not verify the answer.

CITATION RULES:

1. Every factual claim based on retrieved documentation must have
   a citation.
2. Cite the SINGLE chunk that most directly supports the claim.
3. Do NOT cite multiple chunks when one chunk is sufficient.
4. Only cite multiple chunks when the claim genuinely requires
   information from multiple pieces of evidence.
5. Do NOT cite a chunk merely because it is related to the topic.
6. Do NOT repeat the same citation for the same claim.
7. Keep citations immediately after the claim they support.
8. Do not place citations inside code blocks.
9. Do not add citations to statements that are not supported
   by the cited evidence.
10. If evidence is insufficient, say that the documentation
    does not provide enough information instead of guessing.

Example:

The default upload limit is 10 GB per file.
[file-storage.md_chunk_3]

BAD:

The default upload limit is 10 GB per file.
[file-storage.md_chunk_3]
[security.md_chunk_4]
[release-notes.md_chunk_4]

unless all three chunks independently support the claim.

GOOD:

The default upload limit is 10 GB per file.
[file-storage.md_chunk_3]

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

    def _build_messages(
        self, prompt: str, history: list[dict] | None = None
    ) -> list[dict]:
        messages = [{"role": "user", "content": prompt}]
        if history:
            history_messages = [
                {"role": turn["role"], "content": turn["content"]}
                for turn in history
                if turn.get("role") in ("user", "assistant") and turn.get("content")
            ]
            messages = history_messages + messages
        return messages

    def generate(
        self,
        query: str,
        results,
        history: list[dict] | None = None,
    ) -> GeneratedAnswer:

        context_started = time.perf_counter()

        with span(
            "Context Preparation",
            run_type="chain",
            tags=["rag", "context"],
            metadata={"chunk_count": len(results)},
        ) as preparation:

            context = self._build_context(results)

            preparation.add_metadata(
                {
                    "context_chars": len(context),
                    "latency_ms": round(
                        (time.perf_counter() - context_started) * 1000, 2
                    ),
                }
            )

        prompt = self._build_prompt(query, context)

        generation_started = time.perf_counter()

        with span(
            "Generation",
            run_type="llm",
            tags=["rag", "generation"],
            metadata={
                "model": self.model,
                "provider": "deepseek",
                "chunk_count": len(results),
            },
            inputs={"query": query, "context_chars": len(context)},
        ) as run:

            messages = self._build_messages(prompt, history)

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )

            answer = response.choices[0].message.content or ""

            # Inputs/outputs of the model are not logged; only sizes, counts
            # and provider-reported token usage.
            generation_metadata = {
                "latency_ms": round(
                    (time.perf_counter() - generation_started) * 1000, 2
                ),
            }

            generation_metadata.update(
                usage_metadata(getattr(response, "usage", None))
            )

            run.add_metadata(generation_metadata)

            citations=parse_citations(answer)
            citations=deduplicate_citations(citations=citations)

            run.add_outputs(
                {
                    "answer_chars": len(answer),
                    "citation_count": len(citations),
                    "citation_chunk_ids": [
                        citation.chunk_id
                        for citation in citations
                    ],
                }
            )

            return GeneratedAnswer(
                answer=answer,
                citations=citations,
            )

    def generate_stream(
        self,
        query: str,
        results,
        history: list[dict] | None = None,
    ):
        """Yield generated answer tokens progressively as they stream from the LLM."""
        context = self._build_context(results)
        prompt = self._build_prompt(query, context)
        messages = self._build_messages(prompt, history)

        response_stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
        )
        for chunk in response_stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
