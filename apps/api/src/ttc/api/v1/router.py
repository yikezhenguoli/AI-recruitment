from fastapi import APIRouter

from ttc.api.v1.admin import router as admin_router
from ttc.api.v1.applications import router as applications_router
from ttc.api.v1.assessments import router as assessments_router
from ttc.api.v1.auth import router as auth_router
from ttc.api.v1.backup import router as backup_router
from ttc.api.v1.candidates import router as candidates_router
from ttc.api.v1.consents import router as consents_router
from ttc.api.v1.evidence import router as evidence_router
from ttc.api.v1.health import router as health_router
from ttc.api.v1.interviews import router as interviews_router
from ttc.api.v1.jobs import router as jobs_router
from ttc.api.v1.match import router as match_router
from ttc.api.v1.members import router as members_router
from ttc.api.v1.notifications import router as notifications_router
from ttc.api.v1.offers import router as offers_router
from ttc.api.v1.portal import router as portal_router
from ttc.api.v1.privacy import router as privacy_router
from ttc.api.v1.progress import router as progress_router
from ttc.api.v1.resumes import router as resumes_router
from ttc.api.v1.talent import router as talent_router
from ttc.api.v1.voice import router as voice_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(jobs_router)
router.include_router(candidates_router)
router.include_router(applications_router)
router.include_router(consents_router)
router.include_router(resumes_router)
router.include_router(assessments_router)
router.include_router(match_router)
router.include_router(portal_router)
router.include_router(offers_router)
router.include_router(interviews_router)
router.include_router(evidence_router)
router.include_router(voice_router)
router.include_router(privacy_router)
router.include_router(admin_router)
router.include_router(members_router)
router.include_router(notifications_router)
router.include_router(talent_router)
router.include_router(backup_router)
router.include_router(progress_router)
