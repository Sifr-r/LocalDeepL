"""Audit-secondary F26 / Phase 2 fix: ``ProviderManager`` preserves real API keys.

Originally bundled in ``test_phase2_remediations.py``. Split
into its own file for 1:1 traceability.

The original fix: ``ProviderManager.save_provider`` used to
overwrite the real API key with the masked preview string
(``"sk-r...2345"``) when an operator edited a provider and
re-submitted the form with the masked value displayed by
the UI. The fix detects masked previews (``"sk-...XXXX"`` or
``"***"``) and preserves the existing real key.
"""

from __future__ import annotations

from omniscribe.api.services.provider_manager import (
    ProviderConfig,
    ProviderManager,
)


def test_provider_manager_preserves_masked_api_key(tmp_path):
    """Verify save_provider does not overwrite real keys when masked strings are submitted."""
    mgr = ProviderManager(config_path=tmp_path / "providers.yaml")
    original = ProviderConfig(
        id="test-prov",
        display_name="Test Provider",
        format="openai_compatible",
        api_url="http://localhost:1234/v1",
        api_key="sk-real-secret-key-12345",
        configured=True,
    )
    mgr.save_provider(original)

    # Submit update with masked preview
    updated = ProviderConfig(
        id="test-prov",
        display_name="Updated Provider",
        format="openai_compatible",
        api_url="http://localhost:1234/v1",
        api_key="sk-r...2345",
        configured=True,
    )
    saved = mgr.save_provider(updated)
    assert saved.api_key == "sk-real-secret-key-12345"

    # Also test '***'
    updated_stars = ProviderConfig(
        id="test-prov",
        display_name="Updated Stars",
        format="openai_compatible",
        api_url="http://localhost:1234/v1",
        api_key="***",
        configured=True,
    )
    saved_stars = mgr.save_provider(updated_stars)
    assert saved_stars.api_key == "sk-real-secret-key-12345"
