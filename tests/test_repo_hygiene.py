"""
Repo-hygiene sanity tests for the DX/infra files added in Phase 5.

Each test pins a small but meaningful invariant about the
infrastructure files so a drive-by refactor doesn't silently
disconnect them. The expected shape is documented in
``compose.yaml`` / ``Dockerfile`` / ``.pre-commit-config.yaml`` /
``.github/workflows/nightly.yml``.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dockerfile_pins_python_and_uv_installs_extras():
    dockerfile = _read(ROOT / "Dockerfile")

    # Pinned Python - keeps the build deterministic.
    assert re.search(r"^FROM python:3\.12-slim", dockerfile, re.MULTILINE), (
        "Dockerfile must pin a specific Python base image"
    )

    # Must install web extras so the API server can boot.
    for extra in ("--extra web", "--extra async-translation"):
        assert extra in dockerfile, f"Dockerfile missing `{extra}` flag"

    # Uses ``omniscribe-server`` so the console script is on PATH.
    assert "omniscribe-server" in dockerfile


def test_compose_yaml_defines_api_redis_and_async_profile_worker():
    compose = yaml.safe_load(_read(ROOT / "compose.yaml"))

    services = compose["services"]
    assert "api" in services, "compose.yaml must define an `api` service"
    assert "redis" in services, "compose.yaml must define a `redis` service"
    assert "worker" in services, "compose.yaml must define a `worker` service"

    # Worker must be opt-in via profile so synchronous users don't pay
    # the Celery footprint.
    assert "async" in services["worker"].get("profiles", []), (
        "worker must be opt-in via `profiles: [async]`"
    )

    # Default profile must include api + redis.
    api_profiles = services["api"].get("profiles", ["default"])
    redis_profiles = services["redis"].get("profiles", [])
    assert "default" in api_profiles, "api should be on the default profile"
    assert "default" in redis_profiles, (
        "redis must be on the default profile so api's depends_on resolves"
    )

    # Worker command must use the --pool=solo flag the README documents.
    worker_cmd = services["worker"].get("command")
    assert isinstance(worker_cmd, list) and "--pool=solo" in worker_cmd, (
        "Celery worker should declare --pool=solo for sqlite/transformer safety"
    )


def test_precommit_config_pins_ruff_and_uvlock_hooks():
    cfg = yaml.safe_load(_read(ROOT / ".pre-commit-config.yaml"))
    repos = {repo["repo"] for repo in cfg["repos"]}
    assert "https://github.com/astral-sh/ruff-pre-commit" in repos
    assert "https://github.com/astral-sh/uv-pre-commit" in repos


def test_nightly_workflow_targets_slow_tests_with_hf_cache():
    workflow = _read(ROOT / ".github/workflows/nightly.yml")

    # Must explicitly opt-in to slow tests; otherwise nightly is a no-op
    # duplicate of the fast tier.
    assert re.search(r"pytest[^\n]*-m slow", workflow), (
        "nightly workflow must run `pytest -m slow`"
    )

    assert "huggingface" in workflow, (
        "nightly workflow should cache the HF Hub snapshot for Surya"
    )
    assert "schedule:" in workflow, "nightly workflow must be cron-triggered"
    assert "workflow_dispatch" in workflow, (
        "manual dispatch should be available for ad-hoc runs"
    )


def test_pyproject_extras_present_for_docker_layering():
    """The Dockerfile's ``uv sync --extra web --extra async-translation``
    must reference real extras declared in ``pyproject.toml``.
    """
    extras = tomllib.loads((ROOT / "pyproject.toml").read_bytes().decode("utf-8"))[
        "project"
    ]["optional-dependencies"]
    assert "web" in extras
    assert "async-translation" in extras
