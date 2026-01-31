from fastapi import APIRouter, Request

router = APIRouter()


@router.post("/plivo/webhook")
async def plivo_webhook(request: Request):
    return {"ok": True}
