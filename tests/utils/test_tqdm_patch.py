"""
Tests for omniscribe.utils.tqdm_patch soft import and monkeypatching.
"""

from __future__ import annotations

from omniscribe.utils.tqdm_patch import SilentTqdm, apply


def test_silent_tqdm_basic() -> None:
    pbar = SilentTqdm([1, 2, 3])
    items = list(pbar)
    assert items == [1, 2, 3]

    # ``update`` and ``close`` are the only side-effecting methods the
    # patch promises; ``set_description`` was removed as YAGNI because no
    # production caller uses it on a SilentTqdm.
    pbar.update(1)
    pbar.close()

    with SilentTqdm() as p:
        assert p is not None


def test_tqdm_patch_apply_runs_without_error() -> None:
    apply()
