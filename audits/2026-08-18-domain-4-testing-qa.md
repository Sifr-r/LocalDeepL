# Domain 4: Testing & QA — Exhaustive Audit Report

**Audit Target:** OmniScribe Test Suite, Fixtures, CI/CD Workflows, Pre-commit Hooks, and QA Infrastructure  
**Auditor:** Lead QA & Test Suite Auditor  
**Date:** August 18, 2026  
**Scope:** `tests/` (all 140+ test files and `conftest.py`), `frontend/src/__tests__/`, `.github/workflows/` (`test.yml`, `nightly.yml`, `security.yml`, `release.yml`), `.pre-commit-config.yaml`, and `pyproject.toml`.

---

## Executive Summary

OmniScribe exhibits a mature, multi-tiered testing discipline with fast-gate unit tests, property-based tests (`hypothesis`), offline mock regressions, deterministic memory models, and separated slow/live/dataset tiers.

However, an exhaustive audit identified **14 specific findings** across test coverage, assertion rigor, marker discipline, and CI/CD pipelines:

### Audit Findings Matrix

| Finding ID | Severity | Category | Target Location | Description |
| :--- | :--- | :--- | :--- | :--- |
| **D4-01** | **CRITICAL** | Coverage Gaps | [`tests/test_pipeline_recall.py:147-160`](file:///d:/OmniScribe/tests/test_pipeline_recall.py#L147-L160)<br>[`tests/test_integration.py:194-196,219-221,258-260`](file:///d:/OmniScribe/tests/test_integration.py#L194-L196) | Regression gates call `pytest.skip` when 0 boxes are emitted or `DocumentResult` is `None`, silently passing total pipeline breaks. |
| **D4-02** | **HIGH** | Coverage Gaps | [`tests/test_state_backend_redis.py:35-55`](file:///d:/OmniScribe/tests/test_state_backend_redis.py#L35-L55) | `RedisStateBackend` runtime connection loss / transient failure during `put`, `get`, `record`, and `list` operations is completely untested. |
| **D4-03** | **HIGH** | Coverage Gaps | [`tests/test_image.py:26-94`](file:///d:/OmniScribe/tests/test_image.py#L26-L94)<br>[`src/omniscribe/core/pdf/rasterizer.py:50-120`](file:///d:/OmniScribe/src/omniscribe/core/pdf/rasterizer.py#L50-L120) | Truncated / malformed PDF and image streams that pass magic byte checks but fail during decoding/rendering in pipeline engines are untested. |
| **D4-11** | **HIGH** | CI/CD & Linters | [`.pre-commit-config.yaml:28-34`](file:///d:/OmniScribe/.pre-commit-config.yaml#L28-L34)<br>[`.github/workflows/test.yml:116`](file:///d:/OmniScribe/.github/workflows/test.yml#L116) | `mypy` type-checks only `src`, leaving all 140+ test files in `tests/` completely unchecked by type analysis in pre-commit and CI. |
| **D4-12** | **HIGH** | CI/CD & Linters | [`.github/workflows/test.yml:119`](file:///d:/OmniScribe/.github/workflows/test.yml#L119) | Test workflow runs `pytest-cov` without `--cov-fail-under`, allowing silent regressions in code coverage without failing CI. |
| **D4-04** | **MEDIUM** | Coverage Gaps | [`tests/test_state_backend_sqlite.py:40-120`](file:///d:/OmniScribe/tests/test_state_backend_sqlite.py#L40-L120) | SQLite lock contention (`sqlite3.OperationalError: database is locked`) under concurrent multi-threaded worker access is untested. |
| **D4-05** | **HIGH** | Assertion Rigor | [`tests/test_live_llm.py:95-96`](file:///d:/OmniScribe/tests/test_live_llm.py#L95-L96) | Live VLM integration test asserts only `len(result.strip()) > 0` with no semantic verification or keyword assertions against the sample image. |
| **D4-06** | **MEDIUM** | Flakiness / Rigor | [`tests/test_ocr_job_queue.py:213,234`](file:///d:/OmniScribe/tests/test_ocr_job_queue.py#L213) | Fixed sleep timeout (`asyncio.sleep(0.55)` vs `0.5`) in job queue cancel test creates CI runner scheduling race condition and flakiness. |
| **D4-07** | **MEDIUM** | Test Quality | [`tests/test_separate_config.py:100-109`](file:///d:/OmniScribe/tests/test_separate_config.py#L100-L109) | `autouse=True` mock for `is_ssrf_target` globally disables SSRF security checks across all tests in `test_separate_config.py`. |
| **D4-13** | **MEDIUM** | CI/CD & Matrix | [`.github/workflows/nightly.yml:35-37`](file:///d:/OmniScribe/.github/workflows/nightly.yml#L35-L37) | Nightly slow and calibration regression tiers run strictly on `ubuntu-latest`, leaving Windows-specific PyMuPDF and Torch regressions untested. |
| **D4-14** | **MEDIUM** | CI/CD & Frontend | [`.github/workflows/test.yml:84-91`](file:///d:/OmniScribe/.github/workflows/test.yml#L84-L91) | Frontend lacks automated accessibility (`axe-core`/`vitest-axe`/Playwright a11y) checks in CI. |
| **D4-08** | **LOW** | Test Quality | [`tests/test_artifact_ttl_cleanup.py:75,109`](file:///d:/OmniScribe/tests/test_artifact_ttl_cleanup.py#L75) | Background cleanup sweeper tests rely on arbitrary `asyncio.sleep(0.05)` rather than deterministic step synchronization. |
| **D4-09** | **LOW** | Markers & Tier | [`tests/test_scripts_smoke.py:40`](file:///d:/OmniScribe/tests/test_scripts_smoke.py#L40) | Smoke test references deprecated `chromadb` optional extra for `ingest_lexicon.py` instead of LanceDB-based store. |
| **D4-10** | **LOW** | Markers & Tier | [`tests/conftest.py`](file:///d:/OmniScribe/tests/conftest.py) | Optional extras lack explicit fast-gate mock suites and rely entirely on `pytest.importorskip`. |

---

## Detailed Findings & Fixes

### D4-01: Silent Skip on Pipeline Failure in Confidence & Integration Regression Gates
- **Impact**: When Surya or PDF embedding fails completely (0 boxes or None DocumentResult), tests call `pytest.skip` and pass CI instead of failing.
- **Fix**: Replace `pytest.skip` with `assert doc_result is not None` and `assert len(boxes) > 0`.

### D4-11 & D4-12: Mypy Unchecked Tests and Missing Coverage Floor in CI
- **Impact**: Test code regressions and typing bugs escape detection; code coverage can drop without failing CI.
- **Fix**: Update `.pre-commit-config.yaml` and `test.yml` to run `mypy src tests` and add `--cov-fail-under=80`.

### D4-05: Vacuous Assertions in Live VLM Tests
- **Impact**: `len(result.strip()) > 0` passes even if the VLM returns hallucinations or error strings.
- **Fix**: Assert presence of expected keywords from fixture ground truth.

### D4-06: Fixed Sleep Race Conditions in Job Queue Tests
- **Impact**: Race condition causes CI test flakiness on slower runner nodes.
- **Fix**: Use `asyncio.Event` synchronization instead of fixed `sleep(0.55)`.
