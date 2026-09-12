from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROOF_WORKFLOWS = (
    ROOT / ".github/workflows/originsd.yml",
    ROOT / ".github/workflows/phase3-workspace.yml",
    ROOT / ".github/workflows/phase5-oracle-lumi.yml",
    ROOT / ".github/workflows/stage2-containment.yml",
)


def test_pr_proof_workflows_do_not_regenerate_the_committed_rust_lockfile():
    for workflow in PROOF_WORKFLOWS:
        text = workflow.read_text(encoding="utf-8")
        assert "- name: Generate exact dependency lock\n        run: cargo generate-lockfile --manifest-path rust/Cargo.toml" not in text, workflow.name
        assert "--locked --manifest-path rust/Cargo.toml" in text, workflow.name
