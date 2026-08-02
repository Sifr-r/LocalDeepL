"""
Dictionary-based spellcheck post-processing.
Uses pyspellchecker to snap near-miss typos to valid dictionary roots.
Implements 'safe auto-correction': only replaces words if there is a single,
high-confidence match to avoid corrupting text.

Supports pre-downloaded Tesseract langdata wordlists from 'resources/langdata',
supporting over 100+ languages offline with Unicode-aware diacritic handling and
Levenshtein distance 1 edit space for exceptional performance.
"""

import asyncio
import functools
import gzip
import json
import logging
import os
import re
import unicodedata
from importlib import resources, util
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from spellchecker import SpellChecker

# Setup module-level logger
logger = logging.getLogger("pdf_ocr.postprocess")

# Lock to prevent concurrent dictionary compilation across pages
_compile_lock = asyncio.Lock()


@functools.lru_cache(maxsize=8)
def load_dictionary(key: str, kind: str = "builtin") -> "SpellChecker | None":
    """Load and cache a ``SpellChecker`` instance.

    Parameters
    ----------
    key:
        Either a dictionary file path (``kind="custom"``) or a language
        code such as ``"en"`` (``kind="builtin"``).
    kind:
        ``"builtin"`` (default) selects the pyspellchecker built-in
        dictionary for ``key``. ``"custom"`` loads a compiled
        ``json.gz`` dictionary from ``key`` as a file path.

    Returns
    -------
    The cached :class:`SpellChecker` instance, or ``None`` if pyspellchecker
    is unavailable or the language cannot be located.

    The cache is process-local and LRU-bounded at 8 entries — enough for
    the languages and curated dictionaries the API surface actually
    surfaces without leaking memory on stray inputs.
    """
    if not key:
        return None
    if kind == "custom":
        return _load_custom_dictionary(key)
    return _load_builtin_dictionary(key)


def _load_custom_dictionary(dict_path: str) -> "SpellChecker":
    """Synchronous SpellChecker init from a custom dictionary file — call via asyncio.to_thread."""
    from spellchecker import SpellChecker

    spell = SpellChecker(language=None, distance=1)
    spell.word_frequency.load_dictionary(dict_path)
    return spell


def _load_builtin_dictionary(base_lang: str) -> "SpellChecker":
    """Synchronous SpellChecker init from a built-in language dictionary — call via asyncio.to_thread."""
    from spellchecker import SpellChecker

    return SpellChecker(language=base_lang, distance=1)


# Mapping from standard language codes to Tesseract 3-letter folder names
_ISO_639_MAP = {
    "en": "eng",
    "eng": "eng",
    "english": "eng",
    "ar": "ara",
    "ara": "ara",
    "arabic": "ara",
    "de": "deu",
    "deu": "deu",
    "german": "deu",
    "es": "spa",
    "spa": "spa",
    "spanish": "spa",
    "fr": "fra",
    "fra": "fra",
    "french": "fra",
    "pt": "por",
    "por": "por",
    "portuguese": "por",
    "ru": "rus",
    "rus": "rus",
    "russian": "rus",
    "it": "ita",
    "ita": "ita",
    "italian": "ita",
    "nl": "nld",
    "nld": "nld",
    "dutch": "nld",
    "sv": "swe",
    "swe": "swe",
    "swedish": "swe",
    "pl": "pol",
    "pol": "pol",
    "polish": "pol",
    "tr": "tur",
    "tur": "tur",
    "turkish": "tur",
    "zh": "chi_sim",
    "ja": "jpn",
    "ko": "kor",
    "vi": "vie",
    "hi": "hin",
    "fa": "fas",
    "el": "ell",
    "he": "heb",
    "uk": "ukr",
    "cs": "ces",
    "da": "dan",
    "fi": "fin",
    "hu": "hun",
    "id": "ind",
    "no": "nor",
    "ro": "ron",
    "sk": "slk",
    "th": "tha",
}


class DictionaryPostProcessor:
    def __init__(self, lang: str, resources_dir: str | None = None):
        self.lang = lang
        self.spell: SpellChecker | None = None
        self._custom_resources_dir = resources_dir

        # Resolve clean language code
        clean_lang = self.lang.split("-")[0].lower().strip()
        self.tess_lang = _ISO_639_MAP.get(clean_lang, clean_lang)

    async def ensure_loaded(self) -> None:
        """Lazy load the dictionary."""
        if self.spell is not None:
            return

        await self._init_spellchecker()

    async def _init_spellchecker(self) -> None:
        if util.find_spec("spellchecker") is None:
            logger.warning("pyspellchecker is not installed. Skipping spellcheck.")
            self.spell = None
            return

        (
            packaged_dict,
            dictionaries_dir,
            primary_dict_path,
            fallback_dict_path,
            langdata_dir,
            fallback_dictionaries_dir,
        ) = self._get_resource_paths()

        async with _compile_lock:
            # Strategy 1: Try packaged dictionary
            if await self._try_packaged_dict(packaged_dict):
                return

            # Strategy 2: Check compiled dictionary and Strategy 3: Compile from wordlist
            dict_path = await self._try_compiled_or_compile(
                primary_dict_path=primary_dict_path,
                fallback_dict_path=fallback_dict_path,
                langdata_dir=langdata_dir,
                dictionaries_dir=dictionaries_dir,
                fallback_dictionaries_dir=fallback_dictionaries_dir,
            )

            # Strategy 4: Load from the resolved dict_path
            if dict_path and await self._try_load_custom_dict(dict_path):
                return

        # Strategy 5: Fallback to builtin dict
        await self._try_builtin_dict()

    def _get_resource_paths(self) -> tuple[Any, str, str, str, str, str]:
        # Resolve file paths in workspace
        if self._custom_resources_dir:
            resources_dir = self._custom_resources_dir
            langdata_dir = os.path.join(resources_dir, "langdata")
            dictionaries_dir = os.path.join(resources_dir, "dictionaries")
            packaged_dict = None
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))
            resources_dir = os.path.join(project_root, "resources")
            langdata_dir = os.path.join(resources_dir, "langdata")
            dictionaries_dir = os.path.join(resources_dir, "dictionaries")

        fallback_resources_dir = os.path.join(os.path.expanduser("~"), ".local-deepl")
        fallback_dictionaries_dir = os.path.join(fallback_resources_dir, "dictionaries")

        dict_filename = f"{self.tess_lang}.json.gz"
        if not self._custom_resources_dir:
            packaged_dict = resources.files("local_deepl").joinpath(
                "resources", "dictionaries", dict_filename
            )
        else:
            packaged_dict = None

        primary_dict_path = os.path.join(dictionaries_dir, dict_filename)
        fallback_dict_path = os.path.join(fallback_dictionaries_dir, dict_filename)

        return (
            packaged_dict,
            dictionaries_dir,
            primary_dict_path,
            fallback_dict_path,
            langdata_dir,
            fallback_dictionaries_dir,
        )

    async def _try_packaged_dict(self, packaged_dict: Any) -> bool:
        if packaged_dict is not None and packaged_dict.is_file():
            try:
                with resources.as_file(packaged_dict) as packaged_dict_path:
                    self.spell = await asyncio.to_thread(
                        _load_custom_dictionary,
                        str(packaged_dict_path),
                    )
                logger.info(
                    f"Successfully loaded packaged Tesseract dictionary for '{self.tess_lang}' (Distance: 1)."
                )
                return True
            except Exception as e:
                logger.warning(
                    f"Failed to load packaged dictionary for '{self.tess_lang}': {e}"
                )
        return False

    async def _try_compiled_or_compile(
        self,
        primary_dict_path: str,
        fallback_dict_path: str,
        langdata_dir: str,
        dictionaries_dir: str,
        fallback_dictionaries_dir: str,
    ) -> str | None:
        if os.path.exists(primary_dict_path):
            return primary_dict_path
        if os.path.exists(fallback_dict_path):
            return fallback_dict_path

        wordlist_filename = f"{self.tess_lang}.wordlist"
        raw_wordlist_path = os.path.join(
            langdata_dir, self.tess_lang, wordlist_filename
        )

        if os.path.exists(raw_wordlist_path):
            try:
                os.makedirs(dictionaries_dir, exist_ok=True)
                target_dict_path = primary_dict_path
            except Exception:
                os.makedirs(fallback_dictionaries_dir, exist_ok=True)
                target_dict_path = fallback_dict_path

            logger.info(
                f"Compiling raw Tesseract wordlist for '{self.tess_lang}' to {target_dict_path}..."
            )

            success = await asyncio.to_thread(
                self._compile_wordlist, raw_wordlist_path, target_dict_path
            )
            if success:
                return target_dict_path
        else:
            logger.debug(f"Raw Tesseract wordlist not found at: {raw_wordlist_path}")
        return None

    async def _try_load_custom_dict(self, dict_path: str) -> bool:
        try:
            self.spell = await asyncio.to_thread(
                _load_custom_dictionary,
                dict_path,
            )
            logger.info(
                f"Successfully loaded custom Tesseract dictionary for '{self.tess_lang}' (Distance: 1)."
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to load custom dictionary {dict_path}: {e}")
        return False

    async def _try_builtin_dict(self) -> None:
        base_lang = self.lang.split("-")[0].lower()
        try:
            self.spell = await asyncio.to_thread(
                _load_builtin_dictionary,
                base_lang,
            )
            logger.info(
                f"Loaded default pyspellchecker dictionary for '{base_lang}' (Distance: 1)."
            )
        except ValueError:
            logger.warning(
                f"No spellcheck dictionary available for language '{self.lang}'. Spellcheck disabled."
            )
            self.spell = None

    def _compile_wordlist(self, wordlist_path: str, output_path: str) -> bool:
        """
        Reads a raw Tesseract wordlist, cleans non-spacing Unicode marks,
        lowercases all words, removes duplicates, and saves it as a gzipped JSON dictionary.
        """
        try:
            words_dict = {}
            with open(wordlist_path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    word = line.strip()
                    if not word:
                        continue

                    # Clean Unicode marks (diacritics) to validate that it is purely alphabetical
                    cleaned = "".join(
                        c for c in word if unicodedata.category(c) != "Mn"
                    )
                    if cleaned.isalpha():
                        # We save the original word (with diacritics) lowercased with flat frequency of 1
                        words_dict[word.lower()] = 1

            # Save as gzipped JSON
            with gzip.open(output_path, "wt", encoding="utf-8") as f:
                json.dump(words_dict, f)
            return True
        except Exception as e:
            logger.error(f"Error compiling wordlist {wordlist_path}: {e}")
            return False

    def correct_text(self, text: str) -> str:
        spell = self.spell
        if spell is None:
            return text

        def replace_word(match: re.Match[str]) -> str:
            word = match.group(0)

            # Clean Unicode Nonspacing Marks (Harakat, stress marks) to check if purely alphabetic
            cleaned = "".join(c for c in word if unicodedata.category(c) != "Mn")
            if not cleaned.isalpha():
                return word

            try:
                # If word is already known in dictionary, leave it untouched
                # pyspellchecker internally lowercases all inputs for known check
                if spell.known([word]):
                    return word

                # Get spelling candidates at edit distance 1
                candidates = spell.candidates(word)
            except Exception as exc:
                # Spellcheck is advisory; one bad word must not abort the page.
                # Log so an operator can spot a broken underlying dictionary,
                # but fall through and leave the original word untouched.
                logger.warning("Spellcheck failed for word %r: %s", word, exc)
                return word

            # Safe auto-correction: only replace if there is exactly 1 highly confident candidate
            if candidates and len(candidates) == 1:
                corrected = next(iter(candidates))

                # Match original casing (Title case, UPPERCASE, lowercase)
                if word.isupper():
                    return corrected.upper()
                elif word.istitle():
                    return corrected.title()
                return corrected
            return word

        # Match word boundaries supporting Arabic, Latin, and Cyrillic character classes
        return re.sub(r"[^\W\d_]+", replace_word, text)
