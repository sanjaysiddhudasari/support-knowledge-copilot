import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from app.models.answer import Answerability


class AnswerabilityDetector:

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

    def check(
        self,
        query: str,
        results,
    ) -> Answerability:

        context_parts = []

        for result in results:

            chunk = result["chunk"]

            context_parts.append(
                f"""
[CHUNK_ID: {chunk.chunk_ids}]
{chunk.text}
"""
            )

        context = "\n\n".join(context_parts)

        prompt = f"""
You are an answerability classifier for a support
knowledge system.

Determine whether the provided documentation contains
enough information to answer the user's question.

Rules:
1. Use ONLY the provided documentation.
2. Do not use outside knowledge.
3. Return answerable=true only when the documentation
   contains enough information to give a grounded answer.
4. If the evidence is only loosely related or insufficient,
   return answerable=false.

USER QUESTION:
{query}

DOCUMENTATION:
{context}

Return ONLY valid JSON:

{{
    "answerable": true or false,
    "explanation": "brief explanation"
}}
"""

        response = self.client.responses.create(
            model=self.model,
            input=prompt,
        )

        raw_output = response.output_text.strip()

        try:
            result = json.loads(raw_output)
            answerable = result["answerable"]
            explanation = result["explanation"]

            if not isinstance(answerable, bool):
                raise TypeError("'answerable' must be a boolean")

            return Answerability(
                answerable=answerable,
                explanation=str(explanation),
            )

        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
        ):

            return Answerability(
                answerable=False,
                explanation=(
                    "Answerability detection failed."
                ),
            )
