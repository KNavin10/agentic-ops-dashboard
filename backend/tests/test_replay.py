import app
import tools
from agent import run_agent
from replay import load_fixture, replay_model, run_offline_replay


def test_replay_fixture_uses_run_agent_hook_without_groq(monkeypatch):
    def fail_if_groq_is_requested():
        raise AssertionError("Groq must not be requested during replay")

    monkeypatch.setattr(app, "_get_client", fail_if_groq_is_requested)

    result = run_agent(
        "How many APAC submissions were late?",
        model_fn=replay_model(load_fixture("factual_apac_late_count.json")),
    )

    assert result["status"] == "ok"
    assert result["answer"] == "45 APAC submissions were late."
    assert set(result["trace"][0]) == {
        "step", "tool", "duration_ms", "result_size", "status",
    }
    assert result["trace"][0]["tool"] == "query_submissions"


def test_offline_policy_replay_does_not_call_rag_or_ollama(monkeypatch):
    def fail_if_external_retrieval_is_requested(*_args, **_kwargs):
        raise AssertionError("External policy retrieval must not run during eval")

    monkeypatch.setattr(app, "_get_client", fail_if_external_retrieval_is_requested)
    monkeypatch.setattr(
        tools.rag,
        "search_policy",
        fail_if_external_retrieval_is_requested,
    )
    monkeypatch.setattr(
        tools.rag,
        "embed_chunks",
        fail_if_external_retrieval_is_requested,
    )

    result = run_offline_replay(
        "What is the filing deadline for APAC entities?",
        load_fixture("factual_policy_deadline.json"),
    )

    assert result["status"] == "ok"
    assert result["answer"]
    match = result["_evaluation_trace"][0]["result"]["matches"][0]
    assert match["source"] == "policies/sla_policy.md"
    assert match["chunk_id"] == "policies/sla_policy.md:chunk-0001"


def test_offline_replay_keeps_sqlite_tools_real():
    result = run_offline_replay(
        "How many APAC submissions were late?",
        load_fixture("factual_apac_late_count.json"),
    )

    assert result["status"] == "ok"
    assert len(result["_evaluation_trace"][0]["result"]["rows"]) == 63
