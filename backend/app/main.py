from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, checkins, meta, mock_meddi, patients, push, queue, replay, stats

app = FastAPI(title="MEDDI navigátor")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (meta, patients, checkins, chat, queue, stats, replay, mock_meddi, push):
    app.include_router(module.router)
