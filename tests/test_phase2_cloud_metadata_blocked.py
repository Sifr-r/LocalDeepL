"""Audit-secondary F26 / Phase 2 fix: cloud metadata endpoint is unconditionally blocked.

Originally bundled in ``test_phase2_remediations.py``. Split
into its own file for 1:1 traceability.

The original fix: the SSRF guard used to allow the cloud
metadata endpoint (``169.254.169.254``) when
``ALLOW_SSRF_LOCAL=true``. The fix makes the cloud-metadata
block unconditional — it is a credential-leak vector on every
major cloud, and the local-dev default should not relax it.
"""

from __future__ import annotations

from omniscribe.utils.security import is_blocked_host, is_ssrf_target


async def test_cloud_metadata_unconditionally_blocked(monkeypatch):
    """Verify 169.254.169.254 is rejected even if ALLOW_SSRF_LOCAL is true."""
    monkeypatch.setenv("ALLOW_SSRF_LOCAL", "true")

    res = await is_ssrf_target("http://169.254.169.254/latest/meta-data/")
    assert not res.allowed
    assert res.reason == "metadata-endpoint"

    assert is_blocked_host("169.254.169.254")
    assert is_blocked_host("metadata.google.internal")
