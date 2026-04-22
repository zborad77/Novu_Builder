from types import SimpleNamespace
from pathlib import Path

from app.case_workflow.transitions import apply_transition_plan, plan_transition


def _make_project(status: str = "draft") -> SimpleNamespace:
    return SimpleNamespace(
        id="prj_transition_1",
        status=status,
        status_changed_at=None,
        status_changed_by_user_id=None,
        status_history=[],
    )


def test_plan_transition_is_pure_decision() -> None:
    project = _make_project(status="draft")

    transition = plan_transition(
        project,
        "intake",
        actor_user_id="usr_1",
        reason="submit",
    )

    assert project.status == "draft"
    assert project.status_changed_at is None
    assert project.status_changed_by_user_id is None
    assert project.status_history == []
    assert transition.from_status == "draft"
    assert transition.to_status == "intake"


def test_apply_transition_plan_mutates_after_decision() -> None:
    project = _make_project(status="draft")
    transition = plan_transition(project, "intake", actor_user_id="usr_1")

    apply_transition_plan(project, transition)

    assert project.status == "intake"
    assert project.status_changed_at == transition.transitioned_at
    assert project.status_changed_by_user_id == "usr_1"
    assert len(project.status_history) == 1
    assert project.status_history[0].from_status == "draft"
    assert project.status_history[0].to_status == "intake"


def test_transition_module_has_no_inline_project_status_assignment() -> None:
    source = Path("python-backend/app/case_workflow/transitions.py").read_text(encoding="utf-8")

    assert "project.status =" not in source
