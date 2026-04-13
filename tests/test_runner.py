from injection_lab.providers import MockProvider
from injection_lab.runner import evaluate, write_report


def test_offline_mock_runs_suite_without_saving_transcripts(tmp_path):
    report = evaluate("You are a concise assistant.", MockProvider())
    assert report["counts"] == {
        "fixture_passed": 3,
        "attack_indicator": 0,
        "inconclusive": 0,
        "error": 0,
    }
    assert report["transcripts_saved"] is False
    assert "canary" not in str(report["cases"]).lower()

    target = tmp_path / "results.json"
    write_report(report, target)
    serialized = target.read_text(encoding="utf-8")
    assert "ILAB_PRIVATE_EVAL_CANARY_" not in serialized
    assert "The meeting is Thursday" not in serialized

