from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, checkins, meta, mock_meddi, notifications, patients, push, queue, replay, stats
from app.services.notifications import start_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_scheduler()
    yield


app = FastAPI(title="MEDDI navigátor", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (meta, patients, checkins, chat, queue, stats, replay, mock_meddi, push, notifications):
    app.include_router(module.router)
