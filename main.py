from fastapi import FastAPI
from api.v1.auth.routes import router, google_router, feedback_router, workspace_router
from core.db.base import Base
from core.db.session import engine
import os
from dotenv import load_dotenv
from pathlib import Path
from fastapi import Request

# ✅ Load .env
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

# ✅ Create tables
Base.metadata.create_all(bind=engine)

# ✅ FastAPI app
app = FastAPI()
app.include_router(router)
app.include_router(google_router)
app.include_router(feedback_router)
app.include_router(workspace_router)

@app.middleware("http")
async def extract_subdomain(request: Request, call_next):
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host and host.endswith(".feedback.com"):
        subdomain = host.replace(".feedback.com", "")
        request.state.subdomain = subdomain
    else:
        request.state.subdomain = None  # Ensure it's always set
    response = await call_next(request)
    return response

@app.get("/")
def root():
    return {"message": "Service is running"}
