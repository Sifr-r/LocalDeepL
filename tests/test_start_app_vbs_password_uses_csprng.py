"""Hygiene test: the Redis password generator in start_app.vbs must
not use a non-CSPRNG (VBScript Rnd / Randomize). The audit finding
P0 #2 is that the consumer-side --requirepass was added but the
generator was left as VBScript Rnd, which is an LCG seeded by the
wall clock — guessable in multi-user environments.

VBScript cannot be unit-tested in the standard pytest framework, so
this is a source-level hygiene test: it asserts the VBS no longer
contains the forbidden generator primitives. A manual smoke run
(delete redis-password.txt, run start_app.vbs, inspect the new file)
is the complementary validation.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
START_APP_VBS = REPO_ROOT / "start_app.vbs"


def _read_vbs() -> str:
    assert START_APP_VBS.exists(), f"missing: {START_APP_VBS}"
    return START_APP_VBS.read_text(encoding="utf-8")


def test_no_vbscript_rnd() -> None:
    """The VBS must not call Rnd() (the LCG primitive)."""
    source = _read_vbs()
    # Match Rnd( as a function call, but not in comments. The grep is
    # intentionally simple — false positives in comments are OK; the
    # commit author can correct a comment if needed.
    assert "Rnd(" not in source, (
        "start_app.vbs still calls Rnd(); the Redis password generator "
        "must use a CSPRNG (System.Security.Cryptography.RandomNumberGenerator)"
    )


def test_no_vbscript_randomize() -> None:
    """The VBS must not call Randomize (seeds the LCG)."""
    source = _read_vbs()
    assert "Randomize" not in source, (
        "start_app.vbs still calls Randomize; the Redis password generator "
        "must use a CSPRNG instead of seeding the VBScript LCG"
    )


def test_uses_csprng_identifier() -> None:
    """The VBS must reference the System.Security.Cryptography RNG."""
    source = _read_vbs()
    assert "System.Security.Cryptography.RandomNumberGenerator" in source, (
        "start_app.vbs does not reference System.Security.Cryptography.RandomNumberGenerator; "
        "add a Shell.Run call to a PowerShell one-liner using that class"
    )
