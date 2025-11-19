# Captain's Log

Voice-based ship's log for SV Defiant with automatic transcription, semantic search, and AI summaries.

![picard log](picard.webp)

## Quick Start

```bash
# Run the application
docker compose up

# Run tests
docker compose run --rm test

# Access at http://captains-log.localhost
```

## What It Does

Record voice logs that are automatically:
- Transcribed using OpenAI Whisper
- Vectorized for semantic search with pgvector
- Summarized using AI
- Stored with audio playback capability

## Development

This project follows **Test-Driven Development (TDD)**:

```bash
# Run tests during development
docker compose run --rm test

# Run specific tests
docker compose run --rm test pytest tests/test_specific.py -v

# Run tests with coverage
docker compose run --rm test pytest --cov=app tests/

# Live reload development
docker compose up app  # Auto-reloads on file changes
```

## Required Environment Variables

Create `.env` file:
```bash
OPENAI_API_KEY=your_openai_key
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_REGION=us-east-2
```

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