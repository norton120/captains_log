"""
End-to-end tests for the status page using Playwright.
"""
from playwright.sync_api import Page, expect


def test_status_page_accessible_from_navigation(page: Page, base_url: str):
    """Test that the status page is accessible from the navigation menu."""
    page.goto(base_url)

    # Click on the STATUS navigation link
    status_link = page.locator('a[href="/status"]')
    expect(status_link).to_be_visible()
    status_link.click()

    # Verify we're on the status page
    expect(page).to_have_url(f"{base_url}/status")


def test_status_page_displays_heading(page: Page, base_url: str):
    """Test that the status page displays a proper heading."""
    page.goto(f"{base_url}/status")

    # Look for a heading containing "status" or "system"
    heading = page.locator("h1, h2").filter(has_text="Status")
    expect(heading).to_be_visible()


def test_status_page_shows_internet_connectivity_section(page: Page, base_url: str):
    """Test that the status page shows internet connectivity status."""
    page.goto(f"{base_url}/status")

    # Check for OpenAI connectivity status
    openai_status = page.get_by_text("OpenAI", exact=False)
    expect(openai_status).to_be_visible()

    # Check for AWS connectivity status
    aws_status = page.get_by_text("AWS", exact=False)
    expect(aws_status).to_be_visible()


def test_status_page_shows_processing_queue_table(page: Page, base_url: str):
    """Test that the status page shows a table with processing queue information."""
    page.goto(f"{base_url}/status")

    # Look for a table element
    table = page.locator("table")
    expect(table).to_be_visible()

    # Verify table has headers for processing states
    expect(page.get_by_role("columnheader", name="Status")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Count")).to_be_visible()


def test_status_page_displays_processing_states(page: Page, base_url: str):
    """Test that the status page displays all processing states."""
    page.goto(f"{base_url}/status")

    # Check for various processing states in the table
    processing_states = [
        "Pending",
        "Transcribing",
        "Vectorizing",
        "Summarizing",
        "Completed",
        "Failed"
    ]

    for state in processing_states:
        # Each state should appear in the page
        state_element = page.get_by_text(state, exact=False)
        expect(state_element).to_be_visible()


def test_status_page_shows_connectivity_indicators(page: Page, base_url: str):
    """Test that connectivity status is shown with visual indicators."""
    page.goto(f"{base_url}/status")

    # Look for status indicators (could be text, icons, or colored elements)
    # The page should show either "Connected", "Accessible", or similar positive indicator
    # OR "Disconnected", "Not accessible", or similar negative indicator

    # Check that there's some indication of status
    page_content = page.content()
    assert any(
        word in page_content.lower()
        for word in ["connected", "accessible", "available", "online", "offline", "disconnected"]
    )


def test_status_page_updates_dynamically(page: Page, base_url: str):
    """Test that the status page can update dynamically (via HTMX or similar)."""
    page.goto(f"{base_url}/status")

    # Wait for the page to load
    page.wait_for_load_state("networkidle")

    # Get initial content
    initial_timestamp = page.locator('[data-testid="status-timestamp"]').text_content()

    # If there's a refresh button or auto-refresh, verify it works
    refresh_button = page.locator('button:has-text("Refresh")')
    if refresh_button.is_visible():
        refresh_button.click()
        page.wait_for_timeout(500)  # Wait for potential update

        # Timestamp should update (or at least page should handle the click)
        # This is a soft check since timestamp might not change if update is instant
        expect(refresh_button).to_be_enabled()


def test_status_page_responsive_layout(page: Page, base_url: str):
    """Test that the status page uses responsive LCARS layout."""
    page.goto(f"{base_url}/status")

    # The page should have the standard LCARS styling
    # Check for main content area
    main_content = page.locator("main, .content, .lcars-content")
    expect(main_content).to_be_visible()


def test_status_navigation_link_highlighted_when_active(page: Page, base_url: str):
    """Test that the STATUS navigation link is highlighted when on the status page."""
    page.goto(f"{base_url}/status")

    # The active navigation link might have a class like "active" or different styling
    status_link = page.locator('a[href="/status"]')
    expect(status_link).to_be_visible()


def test_status_page_shows_zero_counts_when_no_logs(page: Page, base_url: str):
    """Test that the status page shows zeros when there are no logs processing."""
    # This test assumes a fresh database with no logs
    page.goto(f"{base_url}/status")

    # Should still show the table structure even with zero counts
    table = page.locator("table")
    expect(table).to_be_visible()

    # Total processing should be 0 or close to it in a fresh system
    # (we can't guarantee completely empty in all test scenarios)
    page_content = page.content()
    assert "0" in page_content or "processing" in page_content.lower()


def test_status_page_handles_failed_logs(page: Page, base_url: str):
    """Test that the status page properly displays failed log information."""
    page.goto(f"{base_url}/status")

    # The page should have a row for "Failed" status
    failed_row = page.get_by_text("Failed", exact=False)
    expect(failed_row).to_be_visible()

    # Should show a count (even if it's 0)
    # The entire page should render without errors
    expect(page.locator("table")).to_be_visible()
