# End-to-End Tests with Playwright

This directory contains end-to-end tests for the Captain's Log application using Playwright for browser automation.

## Running E2E Tests

### Using Docker Compose (Recommended)

```bash
# Run all E2E tests
docker compose --profile e2e up --build

# Run specific test file
docker compose run --rm playwright pytest tests/e2e/test_recording_page.py -v

# Run with headed browser (visible UI)
docker compose run --rm playwright pytest tests/e2e/ -v --headed

# Run specific test
docker compose run --rm playwright pytest tests/e2e/test_recording_page.py::TestRecordingPage::test_pause_and_resume_recording -v
```

### Local Development

If you prefer to run tests locally:

```bash
# Install dependencies
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium

# Start the application
docker compose up -d app nginx

# Run tests
pytest tests/e2e/ -v --base-url http://localhost
```

## Test Structure

- `conftest.py` - Pytest fixtures for Playwright configuration
- `test_recording_page.py` - Tests for recording page functionality

## What's Being Tested

### Recording Page Tests

1. **Pause and Resume Recording** - Verifies that clicking the viewport pauses and resumes recording
2. **Save Button Behavior** - Tests that save button works correctly without spurious errors
3. **Recording Start Delay** - Ensures recording starts promptly (under 1 second)
4. **Console Errors** - Checks for JavaScript console errors during page load and use

## Known Issues (Bugs Being Tested)

These tests are designed to fail initially, demonstrating the bugs:

1. **Pause/Resume Bug** - Resume recording doesn't work after pause
2. **Save Error Bug** - Save shows error then proceeds anyway
3. **Delay Bug** - Recording takes 3-5 seconds to start instead of <1 second
4. **Console Errors** - Multiple console errors appear during normal use

## Debugging

To see what the browser is doing:

```bash
# Run with headed mode (visible browser)
docker compose run --rm playwright pytest tests/e2e/ -v --headed

# Run with screenshots on failure (automatically captured)
docker compose run --rm playwright pytest tests/e2e/ -v --screenshot on-failure

# Run with video recording
docker compose run --rm playwright pytest tests/e2e/ -v --video on
```

## CI/CD Integration

E2E tests are in a separate Docker Compose profile (`e2e`) to avoid running them by default in CI/CD pipelines where they might be slower or require special setup.
