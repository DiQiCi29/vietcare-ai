from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from backend.app.core.config import settings
from backend.app.core.database import engine, Base
import backend.app.models # Register all models

# Initialize Database tables if not exist
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.DEBUG else None
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import FileResponse
from backend.app.api.v1.endpoints import router as api_router
from backend.app.rag.retriever import sync_policies_to_vector_store
from backend.app.core.database import SessionLocal

# Ensure upload and static directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs("frontend/static", exist_ok=True)

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
# Incident attachments are served through authenticated API endpoints.

# Include API v1 router
app.include_router(api_router, prefix="/api/v1")

@app.on_event("startup")
def on_startup():
    # Sync policies to vector store on startup
    db = SessionLocal()
    try:
        sync_policies_to_vector_store(db)
    finally:
        db.close()

@app.get("/")
def serve_dashboard():
    return FileResponse("frontend/templates/login.html")

@app.get("/customer")
def serve_customer_portal():
    return FileResponse("frontend/templates/customer.html")

@app.get("/login")
def serve_login():
    return FileResponse("frontend/templates/login.html")

@app.get("/staff")
def serve_staff_portal():
    return FileResponse("frontend/templates/staff.html")

@app.get("/manager")
def serve_manager_portal():
    return FileResponse("frontend/templates/staff.html")

@app.get("/health")
def health_check():
    return {"status": "healthy", "app": settings.PROJECT_NAME}
