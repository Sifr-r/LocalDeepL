import logging

from local_deepl.api.celery_app import celery_app
from local_deepl.core.translation_config import TranslationSettings

logger = logging.getLogger(__name__)


def _current_translation_settings() -> TranslationSettings:
    """Use mutable web settings when available, otherwise environment settings."""
    try:
        from local_deepl.api.routers.config import get_translation_settings
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.split(".", maxsplit=1)[0] == "fastapi":
            return TranslationSettings.from_env()
        raise

    return get_translation_settings()


@celery_app.task(bind=True, name="process_translation")
def process_translation_task(
    self,
    artifact_id: str,
    token: str,
    target_language: str,
    glossary_entries: list,
):
    """
    Background task to run the LangGraph translation workflow on a DocumentTree.
    """
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        raise ValueError("artifact_id must be a non-empty string")
    
    logger.info(f"Starting tree translation task for artifact_id={artifact_id}")

    # Update state to started
    self.update_state(
        state="PROGRESS",
        meta={"progress": 0, "status": "Loading DocumentTree"},
    )

    from local_deepl.api.routers import state
    try:
        path = state.text_artifacts.get(artifact_id, token)
    except Exception as exc:
        raise ValueError(f"Could not load artifact {artifact_id}") from exc

    import os
    import pickle
    tree_path = f"{path}.tree.pkl"
    if not os.path.exists(tree_path):
        raise ValueError(f"DocumentTree not found at {tree_path}")

    with open(tree_path, "rb") as f:
        tree = pickle.load(f)

    from local_deepl.core.glossary import Glossary
    from local_deepl.core.translation_tree import translate_tree
    
    glossary = Glossary()
    if glossary_entries:
        glossary = Glossary.from_dict({"entries": glossary_entries})

    # Initialize translation graph
    from local_deepl.core.translation import run_translation

    import asyncio
    
    async def translator_fn(prompt: str, lang: str) -> str:
        # Re-use run_translation wrapper for now (which is sync inside run_translation, 
        # wait! run_translation uses the graph which is sync).
        # We can just call run_translation synchronously.
        return run_translation(
            prompt,
            target_language=lang,
            settings=_current_translation_settings(),
        )

    self.update_state(
        state="PROGRESS",
        meta={"progress": 10, "status": "Translating DocumentTree blocks"},
    )

    translated_tree = asyncio.run(
        translate_tree(
            tree,
            target_language=target_language,
            translator=translator_fn,
            glossary=glossary,
            dual_translate=False,
            channel_id=None,
        )
    )

    # Save the translated tree back to the artifact path
    translated_tree_path = f"{path}_translated.tree.pkl"
    with open(translated_tree_path, "wb") as f:
        pickle.dump(translated_tree, f)

    self.update_state(
        state="PROGRESS",
        meta={"progress": 100, "status": "Translation complete"},
    )

    # Return summary dict for status polling
    return {
        "artifact_id": artifact_id,
        "translated_tree_path": translated_tree_path,
        "blocks_translated": len(translated_tree.pages)
    }
