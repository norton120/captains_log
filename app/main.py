"""Captain's Log FastAPI application."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.logs import router as logs_router
from app.api.settings import router as settings_router
from app.api.status import router as status_router
from app.api.auth import router as auth_router
from app.api.fitbit import router as fitbit_router
from app.dependencies import close_db_connection, get_db, get_db_session
from app.models.log_entry import LogEntry
from app.api.settings import get_or_create_user_preferences
from app.middleware import InitializationCheckMiddleware, UserContextMiddleware, AuthenticationMiddleware

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifespan events."""
    # Startup
    logger.info("Starting Captain's Log application...")

    # Load OAuth credentials from database and update settings if needed
    try:
        from app.config import settings
        from app.api.auth import register_oauth_routes

        db_session = None
        credentials_loaded = False

        try:
            async for session in get_db_session():
                db_session = session
                break

            if db_session:
                preferences = await get_or_create_user_preferences(db_session)

                # Update settings with database OAuth credentials if env vars are not set
                if not settings.google_oauth_client_id and preferences.google_oauth_client_id:
                    settings.google_oauth_client_id = preferences.google_oauth_client_id
                    settings.google_oauth_client_secret = preferences.google_oauth_client_secret
                    logger.info("Loaded Google OAuth credentials from database")
                    credentials_loaded = True

                if not settings.github_oauth_client_id and preferences.github_oauth_client_id:
                    settings.github_oauth_client_id = preferences.github_oauth_client_id
                    settings.github_oauth_client_secret = preferences.github_oauth_client_secret
                    logger.info("Loaded GitHub OAuth credentials from database")
                    credentials_loaded = True

                if not settings.facebook_oauth_client_id and preferences.facebook_oauth_client_id:
                    settings.facebook_oauth_client_id = preferences.facebook_oauth_client_id
                    settings.facebook_oauth_client_secret = preferences.facebook_oauth_client_secret
                    logger.info("Loaded Facebook OAuth credentials from database")
                    credentials_loaded = True

                # Re-register OAuth routes with updated credentials
                if credentials_loaded:
                    logger.info("Re-registering OAuth routes with database credentials")
                    register_oauth_routes()
        except Exception as e:
            logger.warning(f"Could not load OAuth credentials from database: {e}")
    except Exception as e:
        logger.warning(f"Error during startup OAuth credential loading: {e}")

    yield
    # Shutdown
    logger.info("Shutting down Captain's Log application...")
    await close_db_connection()


# Create FastAPI app
app = FastAPI(
    title="Captain's Log",
    description="Voice-based ship's log with automatic transcription, semantic search, and AI summaries",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Initialize templates
templates = Jinja2Templates(directory="app/templates")


def get_template_context(request: Request, **kwargs):
    """
    Get template context with current user injected.

    This helper function extracts the current user from request.state
    (set by UserContextMiddleware) and includes it in the template context.
    """
    context = {"request": request, "current_user": getattr(request.state, "user", None)}
    context.update(kwargs)
    return context


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add middlewares
# Note: Middlewares are executed in reverse order of addition
# Execution order (first to last): InitializationCheckMiddleware -> UserContextMiddleware -> AuthenticationMiddleware
app.add_middleware(AuthenticationMiddleware)  # Runs THIRD - checks if user is authenticated
app.add_middleware(UserContextMiddleware)  # Runs SECOND - sets request.state.user
app.add_middleware(InitializationCheckMiddleware)  # Runs FIRST - checks initialization

# Include API routers
app.include_router(auth_router, prefix="/api")
app.include_router(logs_router)
app.include_router(settings_router)
app.include_router(status_router, prefix="/api/status", tags=["status"])
app.include_router(fitbit_router)


@app.get("/")
async def index_page(
    request: Request,
    db: Session = Depends(get_db),
    db_session: AsyncSession = Depends(get_db_session),
):
    """Main log listing page."""
    preferences = await get_or_create_user_preferences(db_session)
    return templates.TemplateResponse(
        "index.html",
        get_template_context(
            request,
            current_time=datetime.now().strftime("%Y%m%d.%H%M%S"),
            version="1.0.0",
            app_name=preferences.app_name,
            vessel_name=preferences.vessel_name,
            vessel_designation=preferences.vessel_designation,
        ),
    )


@app.get("/record")
async def record_page(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """Recording page."""
    preferences = await get_or_create_user_preferences(db_session)
    return templates.TemplateResponse(
        "record.html",
        get_template_context(
            request,
            current_time=datetime.now().strftime("%Y%m%d.%H%M%S"),
            version="1.0.0",
            app_name=preferences.app_name,
            vessel_name=preferences.vessel_name,
            vessel_designation=preferences.vessel_designation,
        ),
    )


@app.get("/settings")
async def settings_page(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """Settings page."""
    preferences = await get_or_create_user_preferences(db_session)
    return templates.TemplateResponse(
        "settings.html",
        get_template_context(
            request,
            current_time=datetime.now().strftime("%Y%m%d.%H%M%S"),
            version="1.0.0",
            app_name=preferences.app_name,
            vessel_name=preferences.vessel_name,
            vessel_designation=preferences.vessel_designation,
        ),
    )


@app.get("/search")
async def search_page(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """Search page."""
    preferences = await get_or_create_user_preferences(db_session)
    return templates.TemplateResponse(
        "search.html",
        get_template_context(
            request,
            current_time=datetime.now().strftime("%Y%m%d.%H%M%S"),
            version="1.0.0",
            app_name=preferences.app_name,
            vessel_name=preferences.vessel_name,
            vessel_designation=preferences.vessel_designation,
        ),
    )


@app.get("/map")
async def map_page(
    request: Request,
    db: Session = Depends(get_db),
    db_session: AsyncSession = Depends(get_db_session),
):
    """Map view page showing all logs with location data."""
    import json
    from sqlalchemy import and_

    preferences = await get_or_create_user_preferences(db_session)

    # Query all logs that have location data
    logs_with_location = (
        db.query(LogEntry).filter(and_(LogEntry.latitude.isnot(None), LogEntry.longitude.isnot(None))).all()
    )

    # Convert logs to JSON-serializable format
    logs_data = []
    for log in logs_with_location:
        logs_data.append(
            {
                "id": str(log.id),
                "created_at": log.created_at.isoformat(),
                "latitude": log.latitude,
                "longitude": log.longitude,
                "location_name": log.location_name,
                "location_city": log.location_city,
                "location_state": log.location_state,
                "location_country": log.location_country,
                "body_of_water": log.body_of_water,
                "nearest_port": log.nearest_port,
                "log_type": log.log_type.value,
                "summary": log.summary,
                "weather_conditions": log.weather_conditions,
            }
        )

    # Calculate default map center (average of all locations or default)
    if logs_data:
        avg_lat = sum(log["latitude"] for log in logs_data) / len(logs_data)
        avg_lon = sum(log["longitude"] for log in logs_data) / len(logs_data)
        default_zoom = 6
    else:
        # Default to San Francisco Bay area
        avg_lat = 37.7749
        avg_lon = -122.4194
        default_zoom = 10

    return templates.TemplateResponse(
        "map.html",
        get_template_context(
            request,
            current_time=datetime.now().strftime("%Y%m%d.%H%M%S"),
            version="1.0.0",
            logs_json=json.dumps(logs_data),
            log_count=len(logs_data),
            default_lat=avg_lat,
            default_lon=avg_lon,
            default_zoom=default_zoom,
            app_name=preferences.app_name,
            vessel_name=preferences.vessel_name,
            vessel_designation=preferences.vessel_designation,
        ),
    )


@app.get("/status")
async def status_page(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
):
    """Status page showing system health and processing queue."""
    preferences = await get_or_create_user_preferences(db_session)
    return templates.TemplateResponse(
        "status.html",
        get_template_context(
            request,
            current_time=datetime.now().strftime("%Y%m%d.%H%M%S"),
            version="1.0.0",
            app_name=preferences.app_name,
            vessel_name=preferences.vessel_name,
            vessel_designation=preferences.vessel_designation,
        ),
    )


@app.get("/logs/{log_id}")
async def log_detail_page(
    log_id: str,
    request: Request,
    db: Session = Depends(get_db),
    db_session: AsyncSession = Depends(get_db_session),
):
    """Log detail page."""
    from app.dependencies import get_settings
    from app.services.s3 import S3Service
    from uuid import UUID

    preferences = await get_or_create_user_preferences(db_session)
    log_entry = db.query(LogEntry).filter(LogEntry.id == log_id).first()

    if not log_entry:
        # You might want to create a 404 template
        return templates.TemplateResponse(
            "index.html",
            get_template_context(
                request,
                error="Log entry not found",
                app_name=preferences.app_name,
                vessel_name=preferences.vessel_name,
                vessel_designation=preferences.vessel_designation,
            ),
        )

    # Get audio URL if available
    audio_url = None
    if log_entry.audio_s3_key:
        try:
            settings = get_settings()
            s3_service = S3Service(settings)
            audio_url = await s3_service.get_audio_url(log_entry.audio_s3_key)
        except Exception as e:
            logger.warning(f"Failed to get audio URL for {log_id}: {e}")
            audio_url = None

    # Get video URL if available
    video_url = None
    if log_entry.video_s3_key:
        try:
            settings = get_settings()
            s3_service = S3Service(settings)
            video_url = await s3_service.get_video_url(log_entry.video_s3_key)
        except Exception as e:
            logger.warning(f"Failed to get video URL for {log_id}: {e}")
            video_url = None

    # Helper functions for template
    def format_status(status):
        return status.value.replace("_", " ").upper()

    def format_uuid_short(uuid_obj):
        return str(uuid_obj)[:8]

    return templates.TemplateResponse(
        "detail.html",
        get_template_context(
            request,
            log=log_entry,
            audio_url=audio_url,
            video_url=video_url,
            current_time=datetime.now().strftime("%Y%m%d.%H%M%S"),
            version="1.0.0",
            format_duration=format_duration,
            format_file_size=format_file_size,
            format_status=format_status,
            format_uuid_short=format_uuid_short,
            app_name=preferences.app_name,
            vessel_name=preferences.vessel_name,
            vessel_designation=preferences.vessel_designation,
        ),
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

    units = ["B", "KB", "MB", "GB"]
    size = float(bytes_size)
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    return f"{size:.1f} {units[unit_index]}"


@app.get("/login")
async def login_page(request: Request, db_session: AsyncSession = Depends(get_db_session)):
    """Login page."""
    from sqlalchemy import select, func
    from app.models.user import User
    from app.config import settings

    preferences = await get_or_create_user_preferences(db_session)

    # Check if registration is allowed
    result = await db_session.execute(select(func.count(User.id)))
    user_count = result.scalar()
    allow_registration = user_count == 0 or settings.allow_new_user_registration

    # Check which OAuth providers are configured (check both env and database)
    google_oauth_enabled = bool(
        (preferences.google_oauth_client_id and preferences.google_oauth_client_secret) or
        (settings.google_oauth_client_id and settings.google_oauth_client_secret)
    )
    github_oauth_enabled = bool(
        (preferences.github_oauth_client_id and preferences.github_oauth_client_secret) or
        (settings.github_oauth_client_id and settings.github_oauth_client_secret)
    )
    facebook_oauth_enabled = bool(
        (preferences.facebook_oauth_client_id and preferences.facebook_oauth_client_secret) or
        (settings.facebook_oauth_client_id and settings.facebook_oauth_client_secret)
    )

    return templates.TemplateResponse(
        "login.html",
        get_template_context(
            request,
            current_time=datetime.now().strftime("%Y%m%d.%H%M%S"),
            version="1.0.0",
            app_name=preferences.app_name,
            vessel_name=preferences.vessel_name,
            vessel_designation=preferences.vessel_designation,
            allow_registration=allow_registration,
            google_oauth_enabled=google_oauth_enabled,
            github_oauth_enabled=github_oauth_enabled,
            facebook_oauth_enabled=facebook_oauth_enabled,
        ),
    )


@app.get("/signup")
async def signup_page(request: Request, db_session: AsyncSession = Depends(get_db_session)):
    """Signup page."""
    from sqlalchemy import select, func
    from app.models.user import User
    from app.config import settings

    preferences = await get_or_create_user_preferences(db_session)

    # Check if this is the first user or if registration is allowed
    result = await db_session.execute(select(func.count(User.id)))
    user_count = result.scalar()
    is_first_user = user_count == 0
    allow_registration = is_first_user or settings.allow_new_user_registration

    # Check which OAuth providers are configured (check both env and database)
    google_oauth_enabled = bool(
        (preferences.google_oauth_client_id and preferences.google_oauth_client_secret) or
        (settings.google_oauth_client_id and settings.google_oauth_client_secret)
    )
    github_oauth_enabled = bool(
        (preferences.github_oauth_client_id and preferences.github_oauth_client_secret) or
        (settings.github_oauth_client_id and settings.github_oauth_client_secret)
    )
    facebook_oauth_enabled = bool(
        (preferences.facebook_oauth_client_id and preferences.facebook_oauth_client_secret) or
        (settings.facebook_oauth_client_id and settings.facebook_oauth_client_secret)
    )

    return templates.TemplateResponse(
        "signup.html",
        get_template_context(
            request,
            current_time=datetime.now().strftime("%Y%m%d.%H%M%S"),
            version="1.0.0",
            app_name=preferences.app_name,
            vessel_name=preferences.vessel_name,
            vessel_designation=preferences.vessel_designation,
            allow_registration=allow_registration,
            is_first_user=is_first_user,
            google_oauth_enabled=google_oauth_enabled,
            github_oauth_enabled=github_oauth_enabled,
            facebook_oauth_enabled=facebook_oauth_enabled,
        ),
    )


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "captains-log"}
