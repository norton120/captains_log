"""Captain's Log FastAPI application."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.logs import router as logs_router
from app.dependencies import close_db_connection, get_db
from app.models.log_entry import LogEntry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifespan events."""
    # Startup
    logger.info("Starting Captain's Log application...")
    yield
    # Shutdown
    logger.info("Shutting down Captain's Log application...")
    await close_db_connection()


# Create FastAPI app
app = FastAPI(
    title="Captain's Log",
    description="Voice-based ship's log with automatic transcription, semantic search, and AI summaries",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Initialize templates
templates = Jinja2Templates(directory="app/templates")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(logs_router)


@app.get("/")
async def index_page(request: Request, db: Session = Depends(get_db)):
    """Main log listing page."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "current_time": datetime.now().strftime("%Y%m%d.%H%M%S"),
            "version": "1.0.0"
        }
    )


@app.get("/record")
async def record_page(request: Request):
    """Recording page."""
    return templates.TemplateResponse(
        "record.html",
        {
            "request": request,
            "current_time": datetime.now().strftime("%Y%m%d.%H%M%S"),
            "version": "1.0.0"
        }
    )


@app.get("/logs/{log_id}")
async def log_detail_page(log_id: str, request: Request, db: Session = Depends(get_db)):
    """Log detail page."""
    log_entry = db.query(LogEntry).filter(LogEntry.id == log_id).first()
    
    if not log_entry:
        # You might want to create a 404 template
        return templates.TemplateResponse(
            "index.html", 
            {"request": request, "error": "Log entry not found"}
        )
    
    # Get audio URL if available
    audio_url = None
    if log_entry.audio_s3_key:
        # This would normally call your S3 service to get a presigned URL
        audio_url = f"/api/logs/{log_id}/audio"
    
    return templates.TemplateResponse(
        "detail.html",
        {
            "request": request,
            "log": log_entry,
            "audio_url": audio_url,
            "current_time": datetime.now().strftime("%Y%m%d.%H%M%S"),
            "version": "1.0.0",
            "format_duration": format_duration,
            "format_file_size": format_file_size
        }
    )


def format_duration(seconds):
    """Format duration in seconds to MM:SS or HH:MM:SS format."""
    if not seconds:
        return "Unknown"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining_seconds = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes}:{remaining_seconds:02d}"


def format_file_size(bytes_size):
    """Format file size in bytes to human-readable format."""
    if not bytes_size:
        return "Unknown"
    
    units = ['B', 'KB', 'MB', 'GB']
    size = float(bytes_size)
    unit_index = 0
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    return f"{size:.1f} {units[unit_index]}"


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "captains-log"}