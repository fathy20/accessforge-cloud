from fastapi import APIRouter

from .crew_hours.router import router as crew_hours_router


router = APIRouter(prefix="/api/statistics", tags=["statistics"])
router.include_router(crew_hours_router)
