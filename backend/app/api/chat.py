import json
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.adapters.meddi_json import load_patient
from app.agent import navigator
from app.config import settings
from app.models import Lang, NavigatorReply

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    author: Literal["pacient", "pecujici"] = "pacient"
    lang: Lang | None = None


def _check_patient(patient_id: str):
    try:
        return load_patient(patient_id)
    except KeyError:
        raise HTTPException(404, f"Neznámý pacient {patient_id}")


@router.get("/chat/{patient_id}/messages")
def list_messages(patient_id: str) -> list[dict]:
    _check_patient(patient_id)
    return navigator.history(patient_id)


@router.post("/chat/{patient_id}/hide")
def hide_messages(patient_id: str) -> list[dict]:
    _check_patient(patient_id)
    navigator.hide_history(patient_id)
    return navigator.history(patient_id)


@router.post("/chat/{patient_id}/messages")
async def post_message(patient_id: str, body: ChatRequest) -> NavigatorReply:
    _check_patient(patient_id)
    return await navigator.chat_turn(patient_id, body.text, body.author, body.lang)


def _sse(event: str, data) -> str:
    payload = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat/{patient_id}/stream")
async def stream_message(patient_id: str, body: ChatRequest) -> StreamingResponse:
    _check_patient(patient_id)

    async def events():
        async for event in navigator.stream_chat_turn(patient_id, body.text, body.author, body.lang):
            yield _sse(event["event"], event["data"])

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/chat/{patient_id}/transcribe")
async def transcribe(patient_id: str, audio: UploadFile = File(...)) -> dict:
    patient = _check_patient(patient_id)
    if not settings.openai_api_key:
        raise HTTPException(503, "Přepis řeči není k dispozici")
    from openai import AsyncOpenAI

    content = await audio.read()
    if len(content) > 10_000_000:
        raise HTTPException(413, "Nahrávka je příliš dlouhá")
    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30)
    result = await client.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe", language=patient.demografie.jazyk, file=(audio.filename or "audio.webm", content, audio.content_type or "audio/webm")
    )
    return {"text": result.text}
