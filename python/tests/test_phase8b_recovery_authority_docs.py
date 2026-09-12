from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = [ROOT / "CURRENT_STATE.md", ROOT / "AI_HANDOFF.md"]


def test_phase8b_recovery_docs_fetch_main_explicitly_and_label_snapshot_shas():
    for path in DOCS:
        text = path.read_text()
        assert "git fetch origin refs/heads/main:refs/remotes/origin/main" in text, path
        assert "Recovery snapshot" in text, path
        assert "Origins main     =" not in text, path
