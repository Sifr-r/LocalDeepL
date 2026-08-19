"""Audit-secondary F26 / Phase 2 fix: ``translate_text`` resolves text artifacts.

Originally bundled in ``test_phase2_remediations.py``. Split
into its own file for 1:1 traceability.

The original fix: ``translate_text`` ignored the
``text_artifact_id`` / ``text_artifact_token`` parameters and
tried to translate an empty string, producing an empty
translation. The fix resolves the artifact via the legacy
``state.text_artifacts`` store and feeds the resolved text
into the translation prompt.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from omniscribe.api.schemas.requests import TranslationRequest
from omniscribe.api.services.ai import translate_text
from omniscribe.api.services.artifacts import TextArtifactStore


async def test_translate_text_resolves_text_artifact(tmp_path):
    """Verify translate_text resolves source text from token-bound text artifact store."""
    store = TextArtifactStore(artifact_dir=tmp_path)
    handle = await store.create({"0": ["Line 1 from artifact", "Line 2 from artifact"]})

    config = {
        "translation_api_base": "http://localhost:1234/v1",
        "translation_api_key": "sk-test",
        "translation_model": "test-model",
    }

    req = TranslationRequest(
        text="",
        text_artifact_id=handle.artifact_id,
        text_artifact_token=handle.token,
        target_language="French",
    )

    with patch("omniscribe.api.routers.state.text_artifacts", store):
        with patch(
            "omniscribe.api.services.ai._complete_text", new_callable=AsyncMock
        ) as mock_complete:
            mock_complete.return_value = "Ligne 1 de l'artefact\nLigne 2 de l'artefact"
            res = await translate_text(req, config=config)
            assert res == "Ligne 1 de l'artefact\nLigne 2 de l'artefact"
            assert mock_complete.called
            # Verify prompt contains resolved text
            prompt_arg = mock_complete.call_args[0][1]
            assert "Line 1 from artifact\nLine 2 from artifact" in prompt_arg
