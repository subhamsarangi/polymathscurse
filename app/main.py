from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.auth import router as auth_router
from app.routers.me import router as me_router
from app.routers.interests import router as interests_router
from app.routers.targets import router as targets_router

app = FastAPI(title="Polymath Focus API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(me_router)
app.include_router(interests_router)
app.include_router(targets_router)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}
