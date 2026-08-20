"""Diagnostic: minimal ``pytest-asyncio + AsyncClient`` smoke.

Audit-secondary F24: moved out of ``tests/_diag/`` so the file
is no longer auto-collected by pytest. The old exclude
mechanism in ``conftest.py:collect_ignore_glob`` was a fragile
single-line guard; a future contributor "fixing" the conftest
would silently re-enable collection and break the fast tier
on a hidden ``sys.path.insert``.

How to run::

    uv run python scripts/diagnostics/test_minimal.py

What it checks: a bare FastAPI app with an ``AsyncClient`` +
``ASGITransport`` returns 200 for a trivial endpoint. Useful
when pytest-asyncio is acting up and you want to isolate
"is the runtime broken" from "is my test broken".
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow ``import omniscribe.*`` from the working tree without ``pip install -e .``.
# _common.py lives in the parent ``scripts/`` directory; add it to sys.path
# before importing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common import setup_sys_path  # noqa: E402

setup_sys_path()

import httpx
from fastapi import FastAPI
from httpx import ASGITransport

app = FastAPI()


@app.get("/ping")
async def ping():
    return {"pong": True}


async def test_minimal():
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/ping")
        assert response.status_code == 200
        assert response.json() == {"pong": True}
        print("OK")


if __name__ == "__main__":
    asyncio.run(test_minimal())
