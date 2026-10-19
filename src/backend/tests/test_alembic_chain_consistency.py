from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _get_script_directory() -> ScriptDirectory:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    return ScriptDirectory.from_config(config)


def test_alembic_has_single_head():
    script = _get_script_directory()
    heads = script.get_heads()

    assert len(heads) == 1, f"Expected a single Alembic head, found: {heads}"


def test_alembic_revision_chain_is_contiguous():
    script = _get_script_directory()
    revisions = list(script.walk_revisions(base="base", head="heads"))

    assert revisions, "Alembic revision history must not be empty."

    known_revisions = {revision.revision for revision in revisions}

    for revision in revisions:
        down_revision = revision.down_revision
        if down_revision is None:
            continue
        if isinstance(down_revision, tuple):
            for parent in down_revision:
                assert parent in known_revisions, (
                    f"Revision {revision.revision} points to missing parent {parent}."
                )
        else:
            assert down_revision in known_revisions, (
                f"Revision {revision.revision} points to missing parent {down_revision}."
            )
