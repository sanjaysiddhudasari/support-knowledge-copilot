import json
from pathlib import Path

from app.services.qa_service import QAService


DATASET_PATH = "data/golden/golden_dataset.json"
OUTPUT_PATH = "data/golden/answer_eval.json"


class AnswerEvaluator:

    def __init__(
        self,
        dataset_path: str = DATASET_PATH,
    ):

        path = Path(dataset_path)

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:

            self.questions = json.load(file)

        self.qa_service = QAService()

    def evaluate(self):

        results = []

        for index, item in enumerate(
            self.questions,
            start=1,
        ):

            print(
                f"[{index}/{len(self.questions)}] "
                f"{item['id']}"
            )

            question = item["question"]

            expected_answerable = item.get(
                "answerable"
            )

            expected_chunks = item.get(
                "expected_chunks",
                [],
            )

            result = self.qa_service.answer(
                query=question
            )

            generated_answer = result["answer"]

            actual_answerable = result[
                "answerability"
            ].answerable

            citations = result["citations"]

            confidence = result["confidence"]

            total_citations = len(citations)

            valid_citations = 0
            supported_citations = 0

            citation_results = []

            for citation in citations:

                if isinstance(
                    citation,
                    dict,
                ):
                    chunk_id = citation.get(
                        "chunk_id"
                    )

                    supported = citation.get(
                        "supported",
                        False,
                    )

                    explanation = citation.get(
                        "explanation"
                    )

                else:
                    chunk_id = getattr(
                        citation,
                        "chunk_id",
                        None,
                    )

                    supported = getattr(
                        citation,
                        "supported",
                        False,
                    )

                    explanation = getattr(
                        citation,
                        "explanation",
                        None,
                    )

                # A citation is valid if the verifier
                # was able to find the cited chunk
                # in the retrieved evidence.
                #
                # The verifier uses:
                #
                # "The cited chunk was not found
                #  in the retrieved evidence."
                #
                # to identify an invalid citation.

                valid = (
                    explanation
                    != (
                        "The cited chunk was not "
                        "found in the retrieved evidence."
                    )
                )

                if valid:
                    valid_citations += 1

                if supported:
                    supported_citations += 1

                citation_results.append(
                    {
                        "chunk_id": chunk_id,
                        "valid": valid,
                        "supported": supported,
                        "explanation": explanation,
                    }
                )

            citation_validity_rate = (
                valid_citations / total_citations
                if total_citations
                else 0.0
            )

            citation_support_rate = (
                supported_citations / total_citations
                if total_citations
                else 0.0
            )

            citation_support = [
                citation["supported"]
                for citation in citation_results
            ]

            unsupported_citations = sum(
                1
                for supported in citation_support
                if not supported
            )

            citation_chunks = [
                citation.get("chunk_id")
                if isinstance(citation, dict)
                else getattr(
                    citation,
                    "chunk_id",
                    None,
                )
                for citation in citation_results
            ]

            results.append(
                {
                    "id": item["id"],
                    "question": question,

                    "expected_answerable": (
                        expected_answerable
                    ),

                    "actual_answerable": (
                        actual_answerable
                    ),

                    "expected_chunks": (
                        expected_chunks
                    ),

                    "generated_answer": (
                        generated_answer
                    ),

                    "citations": citation_results,

                    "citation_validity_rate": round(
                        citation_validity_rate,
                        4,
                    ),

                    "citation_support_rate": round(
                        citation_support_rate,
                        4,
                    ),

                    "unsupported_citations": (
                        unsupported_citations
                    ),

                    "confidence": confidence,

                    "citation_chunks": (
                        citation_chunks
                    ),
                }
            )

        return results
    

    @staticmethod
    def summarize(results):

        if not results:
            return {}

        answerability_correct = 0

        answerable_questions = 0
        no_answer_questions = 0

        valid_citations = 0
        supported_citations = 0
        total_citations = 0

        confidence_values = []

        for result in results:

            expected = result[
                "expected_answerable"
            ]

            actual = result[
                "actual_answerable"
            ]

            if expected == actual:
                answerability_correct += 1

            if expected is True:
                answerable_questions += 1

            elif expected is False:
                no_answer_questions += 1

            for citation in result[
                "citations"
            ]:

                total_citations += 1

                if citation["valid"]:
                    valid_citations += 1

                if citation["supported"]:
                    supported_citations += 1

            confidence = result[
                "confidence"
            ]

            if isinstance(
                confidence,
                dict,
            ):

                value = confidence.get(
                    "confidence"
                )

            else:

                value = confidence

            if isinstance(
                value,
                (int, float),
            ):

                confidence_values.append(
                    value
                )

        return {
            "total_questions": len(results),

            "answerability_accuracy": round(
                answerability_correct
                / len(results),
                4,
            ),

            "answerable_questions": (
                answerable_questions
            ),

            "no_answer_questions": (
                no_answer_questions
            ),

            "citation_validity_rate": round(
                valid_citations
                / total_citations,
                4,
            )
            if total_citations
            else 0.0,

            "citation_support_rate": round(
                supported_citations
                / total_citations,
                4,
            )
            if total_citations
            else 0.0,

            "total_citations": (
                total_citations
            ),

            "average_confidence": round(
                sum(confidence_values)
                / len(confidence_values),
                4,
            )
            if confidence_values
            else 0.0,
        }


def main():

    evaluator = AnswerEvaluator()

    results = evaluator.evaluate()

    summary = evaluator.summarize(
        results
    )

    output = {
        "summary": summary,
        "questions": results,
    }

    output_path = Path(
        OUTPUT_PATH
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            output,
            file,
            indent=2,
            default=str,
        )

    print("\n" + "=" * 70)
    print("ANSWER EVALUATION COMPLETE")
    print("=" * 70)

    for key, value in summary.items():

        print(
            f"{key}: {value}"
        )

    print(
        f"\nSaved to: {output_path}"
    )


if __name__ == "__main__":
    main()
