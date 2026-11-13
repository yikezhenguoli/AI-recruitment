"""POST /api/jobs/parse — Step 1: Parse a job description (cached)."""
from fastapi import APIRouter, HTTPException
from models.schemas import (
    GetSavedJobResponse,
    ListSavedJobsResponse,
    ParseJDRequest,
    ParseJDResponse,
    SaveJobProfileRequest,
    SaveJobProfileResponse,
)
from agents.jd_agent import parse_job_description
from core.logging_config import get_logger
from core.config import get_settings
from server.storage.saved_jobs import SavedJobConflictError, SavedJobStore

logger = get_logger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["jobs"])
saved_job_store = SavedJobStore(get_settings().SAVED_JOBS_FILE)


@router.post("/parse", response_model=ParseJDResponse)
async def parse_jd(body: ParseJDRequest):
    if not body.jd_text.strip():
        raise HTTPException(status_code=400, detail="jd_text cannot be empty")

    try:
        jd_id, structured, scoring_schema = await parse_job_description(body.jd_text)
        return ParseJDResponse(jd_id=jd_id, structured=structured, scoring_schema=scoring_schema)
    except Exception as e:
        logger.error("parse_jd_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"JD parsing failed: {e}")


@router.get("/saved", response_model=ListSavedJobsResponse)
async def list_saved_jobs():
    try:
        return ListSavedJobsResponse(jobs=saved_job_store.list_jobs())
    except Exception as e:
        logger.error("list_saved_jobs_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list saved jobs: {e}")


@router.get("/saved/{name}", response_model=GetSavedJobResponse)
async def get_saved_job(name: str):
    try:
        job = saved_job_store.get_job(name)
    except Exception as e:
        logger.error("get_saved_job_error", name=name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to load saved job: {e}")

    if not job:
        raise HTTPException(status_code=404, detail="Saved job not found")
    return GetSavedJobResponse(job=job)


@router.post("/saved", response_model=SaveJobProfileResponse)
async def save_job_profile(body: SaveJobProfileRequest):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name cannot be empty")
    if not body.jd_text.strip():
        raise HTTPException(status_code=400, detail="jd_text cannot be empty")

    try:
        job = saved_job_store.save_job(
            name=body.name,
            jd_text=body.jd_text,
            structured=body.structured,
            scoring_schema=body.scoring_schema,
        )
        return SaveJobProfileResponse(job=job)
    except SavedJobConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error("save_job_profile_error", name=body.name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to save job profile: {e}")
