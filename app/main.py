"""Captain's Log FastAPI application."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.logs import router as logs_router
from app.dependencies import close_db_connection

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
def read_root():
    """Root endpoint."""
    return {
        "message": "Welcome to Captain's Log",
        "docs": "/docs",
        "version": "1.0.0"
    }


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "captains-log"}