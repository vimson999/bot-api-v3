from fastapi import APIRouter, Depends, Query
from app.core.schemas import PaginatedResponse
from bot_api_v1.app.core.dependencies import pagination_params

router = APIRouter(tags=["User Management"])

@router.get("/users", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(1, gt=0, example=1),
    size: int = Query(10, gt=0, le=100, example=10),
    db: Session = Depends(get_db)
):
    total = db.query(User).count()
    users = db.query(User).offset((page-1)*size).limit(size).all()
    
    return PaginatedResponse(
        data={
            "current_page": page,
            "page_size": size,
            "total_items": total,
            "total_pages": (total + size - 1) // size,
            "items": [user.dict() for user in users]
        }
    )