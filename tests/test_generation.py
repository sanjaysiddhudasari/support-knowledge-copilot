import json
from unittest.mock import MagicMock
from app.generation.generator import AnswerGenerator
from app.generation.citation_verifier import CitationVerifier
from app.generation.answerability import AnswerabilityDetector
from app.models.answer import Citation


def test_answer_generator_uses_chat_completions():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Answer text [chunk_1]"
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    gen = AnswerGenerator.__new__(AnswerGenerator)
    gen.client = mock_client
    gen.model = "test-model"

    chunk_mock = MagicMock()
    chunk_mock.chunk_ids = "chunk_1"
    chunk_mock.section = "Overview"
    chunk_mock.source = "overview.md"
    chunk_mock.text = "Evidence content"

    result = gen.generate("test question", [{"chunk": chunk_mock}])

    assert mock_client.chat.completions.create.called
    assert result.answer == "Answer text [chunk_1]"
    assert len(result.citations) == 1
    assert result.citations[0].chunk_id == "chunk_1"


def test_citation_verifier_uses_chat_completions():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"supported": True, "explanation": "Valid"})
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    verifier = CitationVerifier.__new__(CitationVerifier)
    verifier.client = mock_client
    verifier.model = "test-model"

    citation = Citation(chunk_id="chunk_1", claim="Claim", supported=False)
    chunk_mock = MagicMock()
    chunk_mock.chunk_ids = "chunk_1"
    chunk_mock.text = "Evidence text"

    verified = verifier.verify([citation], [{"chunk": chunk_mock}])

    assert mock_client.chat.completions.create.called
    assert len(verified) == 1
    assert verified[0].supported is True


def test_answerability_uses_chat_completions():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"answerable": True, "explanation": "Present"})
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    detector = AnswerabilityDetector.__new__(AnswerabilityDetector)
    detector.client = mock_client
    detector.model = "test-model"

    chunk_mock = MagicMock()
    chunk_mock.chunk_ids = "chunk_1"
    chunk_mock.text = "Evidence"

    result = detector.check("query", [{"chunk": chunk_mock}])

    assert mock_client.chat.completions.create.called
    assert result.answerable is True
