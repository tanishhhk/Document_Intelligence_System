from types import SimpleNamespace

from app.services import llm


def test_generate_answer_uses_configured_model_and_document_context(monkeypatch):
    calls = {}

    class FakeModels:
        def generate_content(self, *, model, contents):
            calls["model"] = model
            calls["contents"] = contents
            return SimpleNamespace(text="  Grounded answer  ")

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(llm, "_create_client", lambda: FakeClient())
    monkeypatch.setattr(llm.settings, "gemini_model", "gemini-3.8-flash")

    answer = llm.generate_answer("What does the report say?", "The report states that sales increased.")

    assert answer == "Grounded answer"
    assert calls["model"] == "gemini-3.8-flash"
    assert "The report states that sales increased." in calls["contents"]
    assert "What does the report say?" in calls["contents"]
