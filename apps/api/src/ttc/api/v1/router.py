from fastapi import APIRouter

from ttc.api.v1.admin import router as admin_router
from ttc.api.v1.assessments import router as assessments_router
from ttc.api.v1.auth import router as auth_router
from ttc.api.v1.candidates import router as candidates_router
from ttc.api.v1.consents import router as consents_router
from ttc.api.v1.evidence import router as evidence_router
from ttc.api.v1.health import router as health_router
from ttc.api.v1.jobs import router as jobs_router
from ttc.api.v1.match import router as match_router
from ttc.api.v1.privacy import router as privacy_router
from ttc.api.v1.progress import router as progress_router
from ttc.api.v1.resumes import router as resumes_router
from ttc.api.v1.voice import router as voice_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(jobs_router)
router.include_router(candidates_router)
router.include_router(consents_router)
router.include_router(resumes_router)
router.include_router(assessments_router)
router.include_router(match_router)
router.include_router(evidence_router)
router.include_router(voice_router)
router.include_router(privacy_router)
router.include_router(admin_router)
router.include_router(progress_router)
