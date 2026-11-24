"""The run of release.yml that a tag fires."""

from app.services.tasks import vps_release


def test_the_run_is_found_by_the_path_of_its_workflow() -> None:
    """The run of release.yml is the newest with its path."""
    answer = {
        "workflow_runs": [
            {"id": 3, "path": ".github/workflows/ci.yml", "head_sha": "a"},
            {"id": 2, "path": ".github/workflows/release.yml", "head_sha": "a"},
            {"id": 1, "path": ".github/workflows/release.yml", "head_sha": "a"},
        ]
    }
    assert vps_release.release_run(answer, "a") == "2"


def test_without_the_run_it_is_empty() -> None:
    """Before GitHub creates the run there is none."""
    assert vps_release.release_run({"workflow_runs": []}, "a") == ""


def test_the_run_of_an_old_tag_with_the_same_name_is_not_the_run() -> None:
    """The deleted v0.1.3 of 2026-11-02 left a run with that name."""
    old = {"id": 41429889281, "path": ".github/workflows/release.yml", "head_sha": "c2e01ba"}
    assert vps_release.release_run({"workflow_runs": [old]}, "9f00e1d") == ""
