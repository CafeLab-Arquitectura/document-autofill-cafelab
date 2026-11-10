from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Estado del servicio")
def health() -> dict[str, str]:
    return {"status": "UP"}
