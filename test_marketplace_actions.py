from pathlib import Path


def test_marketplace_setup_action_contains_expected_contract():
    action_path = Path(__file__).resolve().parent / "actions" / "setup" / "action.yml"
    assert action_path.exists()
    content = action_path.read_text(encoding="utf-8")
    assert "agentplan-version" in content
    assert "python -m pip install" in content
    assert "id: detect-version" in content


def test_marketplace_run_chain_action_forces_ci_and_emits_summary():
    action_path = Path(__file__).resolve().parent / "actions" / "run-chain" / "action.yml"
    assert action_path.exists()
    content = action_path.read_text(encoding="utf-8")
    assert "project-slug" in content
    assert "AGENTPLAN_CI=1 agentplan chain" in content
    assert "$GITHUB_STEP_SUMMARY" in content
    assert "chain-status" in content
