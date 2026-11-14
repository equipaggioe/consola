"""The run of release.yml that a tag fires."""

from app.core.tasks import vps_release


def test_the_run_is_found_by_the_path_of_its_workflow() -> None:
    """The run of release.yml is the newest with its path."""
    answer = {
        "workflow_runs": [
            {"id": 3, "path": ".github/workflows/ci.yml"},
            {"id": 2, "path": ".github/workflows/release.yml"},
            {"id": 1, "path": ".github/workflows/release.yml"},
        ]
    }
    assert vps_release.release_run(answer) == "2"


def test_without_the_run_it_is_empty() -> None:
    """Before GitHub creates the run there is none."""
    assert vps_release.release_run({"workflow_runs": []}) == ""
