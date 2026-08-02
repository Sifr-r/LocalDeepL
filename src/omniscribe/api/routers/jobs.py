import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from omniscribe.api.routers import state

router = APIRouter()


@router.get("/api/jobs")
async def get_jobs():
    """Return the recent job history (newest first)."""
    return state.job_history.list()


@router.delete("/api/jobs")
async def clear_jobs():
    """Clear recent job history and current text artifacts."""
    await asyncio.to_thread(state.text_artifacts.clear)
    state.job_history.clear()
    return {"status": "ok"}


@router.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a queued or running background OCR job."""
    record = await state.ocr_job_queue.cancel(job_id)
    if record is None:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    return {"status": "cancelled", "job_id": job_id}
