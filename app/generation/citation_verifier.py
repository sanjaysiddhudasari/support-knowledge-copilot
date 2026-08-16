import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from app.models.answer import Citation


class CitationVerifier:

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

    def verify(
        self,
        citations: list[Citation],
        results,
    ) -> list[Citation]:

        chunks_by_id = {
            result["chunk"].chunk_ids: result["chunk"]
            for result in results
        }

        verified_citations = []

        for citation in citations:

            chunk = chunks_by_id.get(
                citation.chunk_id
            )

            if chunk is None:

                verified_citations.append(
                    citation.model_copy(
                        update={
                            "supported": False,
                            "explanation": (
                                "The cited chunk was not "
                                "found in the retrieved evidence."
                            ),
                        }
                    )
                )

                continue

            if not citation.claim.strip():

                verified_citations.append(
                    citation.model_copy(
                        update={
                            "supported": False,
                            "explanation": (
                                "The citation did not have an "
                                "associated claim."
                            ),
                        }
                    )
                )

                continue

            verdict = self._verify_claim(
                claim=citation.claim,
                evidence=chunk.text,
            )

            verified_citations.append(
                citation.model_copy(
                    update={
                        "supported": verdict["supported"],
                        "explanation": verdict["explanation"],
                    }
                )
            )

        return verified_citations

    def _verify_claim(
        self,
        claim: str,
        evidence: str,
    ):

        prompt = f"""
You are a citation verification system.

Determine whether the EVIDENCE actually supports
the CLAIM.

Rules:
1. Return supported=true only if the evidence directly
   supports the claim.
2. Do not use outside knowledge.
3. Do not infer information that is not stated or clearly
   implied by the evidence.
4. If the evidence contradicts the claim, return false.
5. If the evidence is insufficient, return false.

CLAIM:
{claim}

EVIDENCE:
{evidence}

Return ONLY valid JSON.
Do not include markdown or any additional text.

The JSON must have exactly these fields:

{{
    "supported": true,
    "explanation": "brief explanation"
}}
"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_output = (response.choices[0].message.content or "").strip()

        try:
            result = json.loads(raw_output)
            supported = result["supported"]
            explanation = result["explanation"]

            if not isinstance(supported, bool):
                raise TypeError("'supported' must be a boolean")

            return {
                "supported": supported,
                "explanation": str(explanation),
            }

        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
        ):

            return {
                "supported": False,
                "explanation": (
                    "Citation verification failed "
                    "because the verifier returned "
                    "an invalid response."
                ),
            }
