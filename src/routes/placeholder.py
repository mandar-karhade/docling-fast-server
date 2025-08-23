from fastapi import APIRouter

router = APIRouter()


@router.post("/serialize")
async def serialize_endpoint():
    """Placeholder serialize endpoint"""
    return {"status": "success", "message": "Serialize endpoint - not implemented yet"}


@router.post("/chunk")
async def chunk_endpoint():
    """Placeholder chunk endpoint"""
    return {"status": "success", "message": "Chunk endpoint - not implemented yet"}
