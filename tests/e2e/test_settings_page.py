"""
End-to-end tests for the settings page.

These tests verify the settings page functionality including:
1. Settings page load
2. Settings form fields populate correctly
3. Settings save functionality
4. Settings persistence after save
"""

import pytest
from playwright.sync_api import Page, expect


class TestSettingsPage:
    """Test suite for settings page functionality."""

    def test_settings_page_loads(self, page: Page, base_url: str):
        """
        Test that the settings page loads successfully.
        """
        # Navigate to the settings page
        page.goto(f"{base_url}/settings")

        # Wait for page to load
        page.wait_for_load_state("networkidle")

        # Verify page title
        expect(page.locator("h1")).to_contain_text("SYSTEM CONFIGURATION")

        # Verify save button is present
        save_button = page.locator('button:has-text("Save Configuration")')
        expect(save_button).to_be_visible()

    def test_settings_form_populates(self, page: Page, base_url: str):
        """
        Test that settings form fields populate with current values.
        """
        # Navigate to the settings page
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Wait for settings to load (status indicator should show loading then success)
        page.wait_for_timeout(2000)

        # Verify key fields have values
        app_name = page.locator("#app_name")
        expect(app_name).not_to_be_empty()

        vessel_name = page.locator("#vessel_name")
        expect(vessel_name).not_to_be_empty()

        vessel_designation = page.locator("#vessel_designation")
        expect(vessel_designation).not_to_be_empty()

    def test_settings_save_succeeds(self, page: Page, base_url: str):
        """
        Test that saving settings works without errors.

        ISSUE: Clicking save button responds with a 503 error.
        This test documents the expected behavior: save should succeed.
        """
        # Set up console message tracking
        console_messages = []
        page.on("console", lambda msg: console_messages.append({"type": msg.type, "text": msg.text}))

        # Navigate to the settings page
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Wait for settings to load
        page.wait_for_timeout(2000)

        # Get the save button
        save_button = page.locator('button:has-text("Save Configuration")')

        # Make a small change to a setting
        app_name_field = page.locator("#app_name")
        original_value = app_name_field.input_value()
        app_name_field.fill(f"{original_value} Test")

        # Click save button
        save_button.click()

        # Wait for the save operation to complete
        page.wait_for_timeout(2000)

        # Check for status indicator showing success
        status_indicator = page.locator("#status-indicator")

        # THIS IS THE BUG: Save should succeed but returns 503
        # The status indicator should show "success" class
        expect(status_indicator).to_have_class("status-indicator success show", timeout=5000)
        expect(status_indicator).to_contain_text("Settings saved successfully")

        # Also verify no error console messages
        error_messages = [msg for msg in console_messages if msg["type"] == "error"]
        assert len(error_messages) == 0, f"Found console errors: {error_messages}"

    def test_settings_save_network_error(self, page: Page, base_url: str):
        """
        Test that documents the actual 503 error when saving settings.

        ISSUE: This test captures the bug - saving settings returns 503.
        This test is expected to PASS initially (confirming the bug exists),
        then FAIL after the bug is fixed.
        """
        # Track network requests
        responses = []
        page.on(
            "response",
            lambda response: responses.append(
                {"url": response.url, "status": response.status, "method": response.request.method}
            ),
        )

        # Navigate to the settings page
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Wait for settings to load
        page.wait_for_timeout(2000)

        # Clear previous responses
        responses.clear()

        # Make a small change
        app_name_field = page.locator("#app_name")
        original_value = app_name_field.input_value()
        app_name_field.fill(f"{original_value} Test")

        # Click save
        save_button = page.locator('button:has-text("Save Configuration")')
        save_button.click()

        # Wait for the save request
        page.wait_for_timeout(2000)

        # Find the PUT request to /api/settings/preferences
        save_requests = [r for r in responses if "/api/settings/preferences" in r["url"] and r["method"] == "PUT"]

        assert len(save_requests) > 0, "No save request was made"

        save_request = save_requests[0]

        # THIS IS THE BUG: The save request returns 503
        # This assertion documents the bug - it should be 200, but is currently 503
        assert save_request["status"] == 503, f"Expected 503 (bug), but got {save_request['status']}"

    def test_settings_save_and_reload_persistence(self, page: Page, base_url: str):
        """
        Test that saved settings persist after page reload.

        This test will only pass once the save bug is fixed.
        """
        # Navigate to the settings page
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Update a setting
        test_value = "SV TEST VESSEL"
        vessel_name_field = page.locator("#vessel_name")
        vessel_name_field.fill(test_value)

        # Save settings
        save_button = page.locator('button:has-text("Save Configuration")')
        save_button.click()

        # Wait for save to complete
        status_indicator = page.locator("#status-indicator")
        expect(status_indicator).to_contain_text("Settings saved successfully", timeout=5000)

        # Reload the page
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify the setting persisted
        vessel_name_field = page.locator("#vessel_name")
        expect(vessel_name_field).to_have_value(test_value)

    def test_settings_no_console_errors_on_load(self, page: Page, base_url: str):
        """
        Test that the settings page loads without console errors.
        """
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # Navigate to the settings page
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Wait for settings to load
        page.wait_for_timeout(2000)

        # Should have no console errors
        assert len(console_errors) == 0, f"Found console errors: {console_errors}"
