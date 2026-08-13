from app.services.qa_service import QAService


def main():

    qa_service = QAService()

    query = (
    "How many failed login attempts are allowed "
    "before the account is locked?"
)

    result = qa_service.answer(query)

    print("\n" + "=" * 60)
    print("ANSWER")
    print("=" * 60)

    print(result["answer"])

    print("\n" + "=" * 60)
    print("ANSWERABILITY")
    print("=" * 60)

    print(
        f"Answerable: "
        f"{result['answerability'].answerable}"
    )

    print(
        f"Explanation: "
        f"{result['answerability'].explanation}"
    )

    print("\n" + "=" * 60)
    print("VERIFIED CITATIONS")
    print("=" * 60)

    for citation in result["citations"]:

        print(
            f"Chunk ID: {citation.chunk_id}"
        )

        print(
            f"Supported: "
            f"{citation.supported}"
        )

        print(
            f"Explanation: "
            f"{citation.explanation}"
        )

        print()

    print("=" * 60)
    print("CONFIDENCE")
    print("=" * 60)

    print(
        f"Overall: "
        f"{result['confidence']}"
    )

    print(
        result["confidence_breakdown"]
    )


if __name__ == "__main__":
    main()