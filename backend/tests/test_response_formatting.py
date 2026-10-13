import tempfile
import unittest
from fastapi.testclient import TestClient
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage

import main


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return next(self.responses)


class ResponseFormattingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path_patch = patch.object(
            main, "DB_PATH", Path(self.temp_dir.name) / "test.db"
        )
        self.db_path_patch.start()
        self.addCleanup(self.db_path_patch.stop)
        main.init_db()

    def test_extracts_text_from_supported_response_shapes(self):
        cases = (
            ("A plain answer.", "A plain answer."),
            (
                {"content": [{"type": "text", "text": "A block answer."}]},
                "A block answer.",
            ),
            (
                [
                    {"type": "text", "text": "Text only."},
                    {"type": "image", "data": "ignored metadata"},
                ],
                "Text only.",
            ),
            (
                AIMessage(
                    content=[
                        {"type": "text", "text": "First paragraph."},
                        {"type": "svg", "data": "ignored markup"},
                    ]
                ),
                "First paragraph.",
            ),
        )
        for response, expected in cases:
            with self.subTest(response_type=type(response).__name__):
                self.assertEqual(main.extract_response_text(response), expected)

    def test_empty_or_non_text_response_is_rejected(self):
        for response in ({"type": "image", "data": "ignored"}, {"content": []}):
            with self.subTest(response=response):
                with self.assertRaises(ValueError):
                    main.extract_response_text(response)

    def test_provider_errors_are_not_returned_to_the_user(self):
        class BrokenModel:
            def invoke(self, messages):
                raise RuntimeError("private provider diagnostics")

        with TestClient(main.app) as client, patch.object(main, "get_model", return_value=BrokenModel()):
            response = client.post(
                "/api/chat",
                json={
                    "session_id": "provider-error-session",
                    "message": "What is a computer?",
                },
            )

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private provider diagnostics", response.json()["detail"])

    def test_chat_returns_text_and_preserves_follow_up_context(self):
        session_id = "formatting-test-session"
        model = FakeModel(
            [
                {"content": [{"type": "text", "text": "A computer processes data."}]},
                SimpleNamespace(
                    content=[{"type": "text", "text": "It follows stored instructions."}]
                ),
            ]
        )
        with TestClient(main.app) as client, patch.object(main, "get_model", return_value=model):
            first = client.post(
                "/api/chat",
                json={"session_id": session_id, "message": "What is a computer?"},
            )
            second = client.post(
                "/api/chat",
                json={"session_id": session_id, "message": "How does it work?"},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["answer"], "A computer processes data.")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["answer"], "It follows stored instructions.")
        self.assertEqual(model.calls[1][-2].content, "A computer processes data.")
        self.assertEqual(
            [message["content"] for message in main.history(session_id)],
            [
                "What is a computer?",
                "A computer processes data.",
                "How does it work?",
                "It follows stored instructions.",
            ],
        )

    def test_chat_keeps_uploaded_pdf_context(self):
        model = FakeModel(
            [SimpleNamespace(content=[{"type": "text", "text": "According to your notes, photosynthesis..."}])]
        )
        with (
            TestClient(main.app) as client,
            patch.object(main, "get_model", return_value=model),
            patch.object(main, "document_context", return_value="Photosynthesis uses light energy."),
        ):
            response = client.post(
                "/api/chat",
                json={
                    "session_id": "pdf-context-session",
                    "message": "Explain photosynthesis from my notes.",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["used_uploaded_notes"])
        self.assertIn("Photosynthesis uses light energy.", model.calls[0][0].content)

    def test_summary_and_quiz_return_markdown_text(self):
        model = FakeModel(
            [
                SimpleNamespace(content=[{"type": "text", "text": "## Summary\n\nKey idea"}]),
                {"result": [{"type": "text", "text": "1. First question"}]},
            ]
        )
        request = main.ActionRequest(session_id="study-actions", topic="Algorithms")
        with TestClient(main.app) as client, patch.object(main, "get_model", return_value=model):
            summary = client.post(
                "/api/summary",
                json={"session_id": request.session_id, "topic": request.topic},
            )
            quiz = client.post(
                "/api/quiz",
                json={"session_id": request.session_id, "topic": request.topic},
            )

        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json(), {"result": "## Summary\n\nKey idea"})
        self.assertEqual(quiz.status_code, 200)
        self.assertEqual(quiz.json(), {"result": "1. First question"})


if __name__ == "__main__":
    unittest.main()
