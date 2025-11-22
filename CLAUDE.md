# Captain's Log - Claude Context

Voice-based ship's log for Sailing Vessels with automatic transcription, semantic search, and AI summaries.

## Quick Commands

```bash
# Run the application
./utils/dev.sh

# Run tests
docker compose run --rm test

# Run specific tests
docker compose run --rm test pytest tests/test_specific.py -v

# Format code with Black
./utils/format.sh

# Check code formatting without modifying files
./utils/format.sh --check

# Generate database migrations (NEVER hand-write migrations)
docker compose run --rm --profile=tools make_migrations

# Access at http://captains-log.localhost
```

## Environment
You are running in a worktree in parallel with other development branches. It is critical that you do not interfere with other containers
on the host machine.
**NEVER**:
- alter your `PORT_OFFSET` or `COMPOSE_PROJECT_NAME` envars - these are intentionally set for each worktree
- stop other containers due to port conflicts

**ALWAYS**:
- use the helper docker compose services, they are pre-configured to abstract away the complexity of worktrees.

## Development Approach

This project follows **Test-Driven Development (TDD)**.

## Tech Stack

- **FastAPI** + SQLAlchemy + PostgreSQL with pgvector
- **HTMX** + Jinja2 templates with LCARS styling
- **DBOS** for async audio processing workflows
- **OpenAI** Whisper API + embeddings
- **AWS S3** for audio storage

## Project Structure

```
app/
├── api/           # FastAPI routes
├── models/        # Database models
├── workflows/     # DBOS background tasks
├── static/        # CSS/JS assets
└── templates/     # HTML templates
tests/             # Test suite
```

## Core Features

- Voice log recording with automatic transcription using OpenAI Whisper
- Vectorized semantic search with pgvector
- AI-powered summaries
- Audio playback capability