"""app.platform.paths: kořen repozitáře v repozitáři, v release i v Docker image."""

from pathlib import PurePosixPath

from app.platform.paths import BACKEND_ROOT, _fallback_root, repo_root


def test_repo_root_found_by_marker_in_checkout():
    assert (repo_root() / ".novu-repo-root").is_file()
    assert repo_root() / "src" / "backend" == BACKEND_ROOT


def test_fallback_for_src_layout_without_marker():
    assert _fallback_root(PurePosixPath("/opt/novuconstruct/src/backend")) == PurePosixPath("/opt/novuconstruct")


def test_fallback_in_docker_image_keeps_pre_refactor_storage_default():
    # Backend v /app (Dockerfile WORKDIR); dřív parents[3] souboru app/storage/... == "/".
    assert _fallback_root(PurePosixPath("/app")) == PurePosixPath("/")
