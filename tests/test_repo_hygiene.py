"""Repo-hygiene sanity tests for the DX/infra files added in Phase 5.

Each test pins a small but meaningful invariant about the
infrastructure files so a drive-by refactor doesn't silently
disconnect them. The expected shape is documented in
``compose.yaml`` / ``Dockerfile`` / ``.pre-commit-config.yaml`` /
``.github/workflows/nightly.yml``.

A second cluster of tests pins architecture-boundary invariants from
``ARCHITECTURE.md`` so a refactor doesn't silently collapse the seams
that the recent god-module decompositions established (see the
``core.workflows`` engine split and the OCR router / state module
decomposition entries).
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _imports_from(path: Path, *module_prefixes: str) -> list[tuple[str, int]]:
    """Return ``[(full_module, lineno)]`` for every import matching a prefix.

    Uses :mod:`ast` so docstrings, comments, and dunder strings don't
    produce false positives — only actual ``import`` and ``from … import``
    statements are considered. A match is any module whose dotted path
    equals one of ``module_prefixes`` or starts with one of them
    followed by ``.``.
    """
    tree = ast.parse(_read(path))
    matches: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            for alias in node.names:
                full = f"{node.module}.{alias.name}"
                if any(
                    full == prefix or full.startswith(prefix + ".")
                    for prefix in module_prefixes
                ):
                    matches.append((full, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if any(
                    alias.name == prefix or alias.name.startswith(prefix + ".")
                    for prefix in module_prefixes
                ):
                    matches.append((alias.name, node.lineno))
    return matches


#: Engine-implementation submodules of ``omniscribe.core.workflows``. Callers
#: outside the package itself must reach the engines via
#: ``omniscribe.OCRPipeline`` (or the public ``omniscribe.core.workflows``
#: re-exports). The ``base`` module is intentionally excluded — it exposes the
#: public ``DocumentResultWriter`` protocol and callback type aliases that
#: peers (e.g. ``core/pdf/__init__.py``) reasonably need.
_WORKFLOW_INTERNAL_SUBMODULES: tuple[str, ...] = ("hybrid", "grounded", "utils")


def test_dockerfile_pins_python_and_uv_installs_extras():
    dockerfile = _read(ROOT / "Dockerfile")

    # Pinned Python - keeps the build deterministic.
    assert re.search(r"^FROM python:3\.12-slim", dockerfile, re.MULTILINE), (
        "Dockerfile must pin a specific Python base image"
    )

    # Must install web extras so the API server can boot, plus
    # preprocessing so the default-on whitespace recall pass has cv2.
    for extra in ("--extra web", "--extra async-translation", "--extra preprocessing"):
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

    # api + redis must start on a plain `docker compose up`. Compose has
    # no implicit default profile, so a `profiles:` key would *exclude*
    # the service — the always-on pair must carry no profiles at all.
    # (Audit P0-4: `profiles: ["default"]` made `compose up` start nothing.)
    assert "profiles" not in services["api"], (
        "api must carry no `profiles:` key so a plain `compose up` starts it"
    )
    assert "profiles" not in services["redis"], (
        "redis must carry no `profiles:` key so api's depends_on resolves "
        "on a plain `compose up`"
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


def test_precommit_mypy_runs_in_the_project_environment():
    """The mypy hook must type-check with the project venv, not an
    isolated mirror env.

    ``mirrors-mypy`` installs mypy into a clean pre-commit env with no
    project dependencies, so import resolution diverges from CI's
    ``uv run mypy src`` (audit backlog). A ``language: system`` hook
    that shells out to ``uv run mypy`` keeps both gates on the same
    interpreter and dependency set.
    """
    cfg = yaml.safe_load(_read(ROOT / ".pre-commit-config.yaml"))
    mypy_hooks = [
        hook
        for repo in cfg["repos"]
        for hook in repo.get("hooks", [])
        if hook.get("id") == "mypy"
    ]
    assert mypy_hooks, "pre-commit config lost its mypy hook"
    hook = mypy_hooks[0]
    assert hook.get("language") == "system", (
        "mypy hook must run in the project environment "
        "(language: system), not an isolated mirror env"
    )
    assert "uv run mypy" in hook.get("entry", ""), (
        "mypy hook entry must delegate to `uv run mypy` so it picks "
        "up the synced project venv"
    )


def test_stop_app_covers_current_entry_points_and_redis_container():
    """``stop_app.bat`` must terminate what ``start_app.vbs`` starts.

    The launcher entry points moved to the installed-package module
    path (``omniscribe.server:app`` / ``celery -A omniscribe.api.tasks``);
    a stop script still matching only the old ``src.*`` forms would
    leave both processes running. The ``redis-local-ocr`` broker
    container must also be stopped (audit backlog).
    """
    stop = _read(ROOT / "stop_app.bat")
    assert "omniscribe.server:app" in stop
    assert "celery -A omniscribe.api.tasks" in stop
    assert "redis-local-ocr" in stop, (
        "stop_app.bat must stop the redis-local-ocr container created by start_app.vbs"
    )


def test_install_scripts_avoid_elevation_and_blind_remote_execution():
    """Installer hygiene invariants (audit backlog).

    - Nothing in the install flow writes to machine locations, so the
      bat wrapper must not self-elevate.
    - The ps1 must never pipe a remote script straight into the
      interpreter (``| iex``); the uv bootstrap downloads to a file
      (or uses winget) instead.
    - Frontend deps install from the lockfile (``npm ci``) and every
      npm step is exit-code checked.
    """
    bat = _read(ROOT / "install.bat")
    assert "RunAs" not in bat and "NET SESSION" not in bat, (
        "install.bat must not self-elevate — shortcuts and uv are per-user"
    )
    ps1 = _read(ROOT / "install.ps1")
    assert "| iex" not in ps1 and "| Invoke-Expression" not in ps1, (
        "install.ps1 must not execute a remote script sight-unseen"
    )
    assert "npm ci" in ps1, "frontend deps must install from package-lock.json"
    assert "npm install" not in ps1.replace("npm ci", ""), (
        "install.ps1 should use `npm ci`, not `npm install`"
    )
    npm_calls = ps1.count("$LASTEXITCODE -ne 0")
    assert npm_calls >= 4, (
        "uv sync, npm ci, npm run build, and the uv-run verification "
        "must all be exit-code checked"
    )


def test_pyproject_has_no_duplicate_deps_across_extras():
    """A package pinned in the base deps must not be re-declared in an
    extra (audit backlog: duplicated declarations drifted across
    extras). torch / torchvision must also carry an upper major bound
    so an upstream major can't silently break surya.
    """
    project = tomllib.loads((ROOT / "pyproject.toml").read_bytes().decode("utf-8"))[
        "project"
    ]

    def _name(dep: str) -> str:
        return re.split(r"[<>=!~\[;\s]", dep, maxsplit=1)[0].lower()

    base = {_name(dep) for dep in project["dependencies"]}
    # Deliberate repeats that document a feature surface and are pinned
    # by another contract test (test_optional_extras_split_chromadb_into_memory).
    allowed_overlaps = {("memory", "chromadb")}
    for extra_name, deps in project["optional-dependencies"].items():
        overlap = {_name(dep) for dep in deps} & base
        overlap -= {pkg for (ex, pkg) in allowed_overlaps if ex == extra_name}
        assert not overlap, (
            f"extra `{extra_name}` re-declares base dependencies: "
            f"{sorted(overlap)} — remove the duplicate from the extra"
        )

    by_name = {_name(dep): dep for dep in project["dependencies"]}
    for pkg in ("torch", "torchvision"):
        assert "<" in by_name[pkg], (
            f"{pkg} must carry an upper major bound ({by_name[pkg]!r})"
        )


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


def test_celery_and_uvicorn_targets_match_installed_package_path():
    """Launcher entry points must use the ``omniscribe.*`` module path.

    ``start_app.vbs`` historically started the worker with
    ``-A src.omniscribe.api.celery_app`` while ``compose.yaml`` used
    ``-A omniscribe.api.tasks``. The ``src.*`` form resolves via a PEP 420
    namespace copy, so tasks registered on the installed ``omniscribe.*``
    module copy were invisible to the worker (audit DevOps High #6).
    Keep every launcher on the same installed-package path.
    """
    vbs = _read(ROOT / "start_app.vbs")
    compose = yaml.safe_load(_read(ROOT / "compose.yaml"))

    assert "celery -A omniscribe.api.tasks" in vbs, (
        "start_app.vbs must start the Celery worker with the "
        "installed-package module path `omniscribe.api.tasks`"
    )
    assert "src.omniscribe" not in vbs, (
        "start_app.vbs must not reference `src.omniscribe.*` — the "
        "namespace copy registers tasks in a second module instance"
    )

    worker_cmd = compose["services"]["worker"]["command"]
    assert "omniscribe.api.tasks" in worker_cmd, (
        "compose worker must keep using `-A omniscribe.api.tasks` so "
        "both launchers agree on the Celery app module"
    )


def test_pyproject_extras_present_for_docker_layering():
    """The Dockerfile's ``uv sync --extra web --extra async-translation
    --extra preprocessing`` must reference real extras declared in
    ``pyproject.toml``.
    """
    extras = tomllib.loads((ROOT / "pyproject.toml").read_bytes().decode("utf-8"))[
        "project"
    ]["optional-dependencies"]
    assert "web" in extras
    assert "async-translation" in extras
    assert "preprocessing" in extras


# ---------------------------------------------------------------------------
# Architecture-boundary assertions (ARCHITECTURE.md)
# ---------------------------------------------------------------------------
#
# Pin the single-responsibility invariants that the most recent god-module
# decompositions put in place. A drive-by refactor that quietly imports a
# workflow implementation submodule, or that bypasses the state singleton,
# would collapse the seams these boundaries protect. These tests assert
# against the file tree statically (AST) so they run without booting the
# OCR pipeline or touching the VLM client.


def _is_workflow_internal(module: str) -> bool:
    """Return True iff ``module`` points at one of the engine implementation
    submodules (``hybrid`` / ``grounded`` / ``utils``) rather than the public
    re-export surface ``omniscribe.core.workflows``.
    """
    parts = module.split(".")
    return (
        len(parts) >= 4
        and parts[0] == "omniscribe"
        and parts[1] == "core"
        and parts[2] == "workflows"
        and parts[3] in _WORKFLOW_INTERNAL_SUBMODULES
    )


def test_ocr_router_does_not_import_workflow_internals():
    """``api/routers/ocr.py`` is a thin orchestrator per ARCHITECTURE.md.

    It must delegate to ``OCRPipeline`` + ``api/services/ocr_*.py`` and
    never reach into ``omniscribe.core.workflows.hybrid`` /
    ``omniscribe.core.workflows.grounded`` directly. Importing either
    engine implementation would collapse the ``OCRPipeline`` facade and
    let the FastAPI router depend on internal engine layout that the
    engine-split refactor intentionally hid behind the public package
    surface.
    """
    ocr_path = ROOT / "src/omniscribe/api/routers/ocr.py"
    offenders = [
        (mod, lineno)
        for mod, lineno in _imports_from(ocr_path, "omniscribe.core.workflows")
        if _is_workflow_internal(mod)
    ]
    assert not offenders, (
        "OCR router must not import `omniscribe.core.workflows.{hybrid,grounded,utils}` "
        "directly; go through `omniscribe.OCRPipeline` and `api/services/ocr_*.py`. "
        f"Found: {offenders}"
    )


def test_api_layer_does_not_import_workflow_internals():
    """Generalization of the OCR router boundary to the whole API surface.

    Every router and service under ``src/omniscribe/api/`` must keep the
    engine implementation details behind the ``OCRPipeline`` facade.
    This walker-driven test catches the same boundary violation in any
    router or service, not just the one highlighted by the dedicated
    OCR router test above.
    """
    api_root = ROOT / "src/omniscribe/api"
    offenders: list[str] = []
    for path in sorted(api_root.rglob("*.py")):
        for mod, lineno in _imports_from(path, "omniscribe.core.workflows"):
            if _is_workflow_internal(mod):
                rel = path.relative_to(ROOT).as_posix()
                offenders.append(f"{rel}:{lineno}: {mod}")
    assert not offenders, (
        "API layer must not import `omniscribe.core.workflows.{hybrid,grounded,utils}` "
        "directly; go through `omniscribe.OCRPipeline` and `api/services/ocr_*.py`.\n"
        + "\n".join(offenders)
    )


def test_state_module_is_singleton_boundary():
    """``api/routers/state.py`` is the single source of state singletons.

    Per ARCHITECTURE.md, the ``StateBackend`` protocol is the swap-point
    for alternative backends (Redis, file-backed). To keep that promise,
    the module must hold exactly one ``backend`` instance and every
    module-level alias must point at the same instance on the backend;
    otherwise a backend swap would leave orphan references behind.

    ``glossary_library`` is intentionally a peer instance (its
    ``artifact_dir`` is configured separately so the on-disk glossary
    index is preserved across swaps), so this test only asserts the six
    backend-backed aliases.
    """
    state_path = ROOT / "src/omniscribe/api/routers/state.py"
    state_text = _read(state_path)

    # Exactly one `backend = ...` assignment at module level. A second
    # one would be a recipe for two state surfaces with no clear winner.
    backend_assignments = re.findall(r"^backend\s*=", state_text, re.MULTILINE)
    assert len(backend_assignments) == 1, (
        f"state.py must declare exactly one `backend = ...` assignment; "
        f"found {len(backend_assignments)}"
    )

    # Runtime: the singleton is a LocalStateBackend and the six
    # backend-backed aliases resolve to the same instance on the backend.
    from omniscribe.api.routers import state as router_state
    from omniscribe.api.services.state_backend import (
        LocalStateBackend,
        StateBackend,
    )

    assert isinstance(router_state.backend, LocalStateBackend)
    assert isinstance(router_state.backend, StateBackend)

    for name in (
        "text_artifacts",
        "metadata_artifacts",
        "export_artifacts",
        "job_history",
        "progress_service",
        "ocr_job_queue",
    ):
        bound = getattr(router_state.backend, name)
        aliased = getattr(router_state, name)
        assert bound is not None and aliased is bound, (
            f"state.{name} must be the same instance as state.backend.{name} "
            "so a backend swap stays transparent to all consumers"
        )
