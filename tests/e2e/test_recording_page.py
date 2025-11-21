"""
End-to-end tests for the recording page.

These tests verify the recording page functionality including:
1. Pause/resume recording functionality
2. Save button behavior
3. Recording start delay
4. Console error handling
"""

import pytest
from playwright.sync_api import Page, expect
import time


class TestRecordingPage:
    """Test suite for recording page functionality."""

    def test_pause_and_resume_recording(self, page: Page, base_url: str):
        """
        Test that clicking on the viewport while recording pauses and resumes correctly.

        Issues:
        - Clicking on viewport while recording should pause
        - Clicking again should resume recording
        - Currently, resume doesn't work properly
        """
        # Navigate to the recording page
        page.goto(f"{base_url}/record")

        # Wait for page to load
        page.wait_for_load_state("networkidle")

        # Get the recording overlay element
        overlay = page.locator("#recording-overlay")
        timer = page.locator("#timer")

        # Verify we're on the page
        expect(overlay).to_be_visible()
        expect(overlay).to_contain_text("START RECORDING")

        # Start recording by clicking the overlay
        overlay.click()
        page.wait_for_timeout(500)  # Wait for recording to start

        # Verify recording started
        expect(overlay).to_have_class("recording-overlay transparent")
        expect(overlay).to_have_text("")

        # Wait for timer to show recording is in progress
        page.wait_for_timeout(1500)
        timer_text = timer.text_content()
        assert timer_text != "00:00", "Timer should have started"

        # Click overlay to pause recording
        overlay.click()
        page.wait_for_timeout(500)

        # Verify recording paused - overlay should show "RESUME RECORDING"
        expect(overlay).not_to_have_class("recording-overlay transparent")
        expect(overlay).to_contain_text("RESUME RECORDING")

        # Get the timer value when paused
        paused_timer = timer.text_content()

        # Click overlay again to resume recording
        overlay.click()
        page.wait_for_timeout(500)

        # THIS IS THE BUG: Resume should work but doesn't
        # Verify recording resumed - overlay should be transparent again
        expect(overlay).to_have_class("recording-overlay transparent")
        expect(overlay).to_have_text("")

        # Wait and verify timer is progressing
        page.wait_for_timeout(1500)
        resumed_timer = timer.text_content()
        assert resumed_timer > paused_timer, "Timer should continue after resume"

    def test_save_button_shows_error_then_saves(self, page: Page, base_url: str):
        """
        Test save button behavior.

        Issues:
        - Clicking save shows error "no video/audio data to save"
        - Then several seconds later, it begins saving anyway
        - This should not show an error if data exists
        """
        # Navigate to the recording page
        page.goto(f"{base_url}/record")
        page.wait_for_load_state("networkidle")

        # Get elements
        overlay = page.locator("#recording-overlay")
        save_btn = page.locator("#save-btn")
        alerts = page.locator("#alerts")

        # Start recording
        overlay.click()
        page.wait_for_timeout(2000)  # Record for 2 seconds

        # Stop recording by clicking overlay
        overlay.click()
        page.wait_for_timeout(500)

        # Verify save button is visible
        expect(save_btn).to_be_visible()

        # Monitor console for errors
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg.text))

        # Click save button
        save_btn.click()

        # Wait a moment for any immediate errors
        page.wait_for_timeout(500)

        # Check if error alert appears
        error_alert = page.locator(".lcars-alert.error")

        # THIS IS THE BUG: Should not show error if we have data
        if error_alert.is_visible():
            expect(error_alert).to_contain_text("No")  # "No audio data to save" or similar

            # Wait to see if it starts saving anyway (the bug)
            page.wait_for_timeout(3000)

            # Check if upload progress appears despite the error
            upload_progress = page.locator("#upload-progress")
            # This should NOT happen - if there's an error, it shouldn't then proceed
            assert not upload_progress.is_visible(), "Should not start upload after showing error"

    def test_recording_start_delay(self, page: Page, base_url: str):
        """
        Test that recording starts without excessive delay.

        Issues:
        - 3-5 second delay before recording actually starts
        - Should start within 1 second
        """
        # Navigate to the recording page
        page.goto(f"{base_url}/record")
        page.wait_for_load_state("networkidle")

        # Get elements
        overlay = page.locator("#recording-overlay")
        timer = page.locator("#timer")

        # Record start time
        start_time = time.time()

        # Click to start recording
        overlay.click()

        # Wait for overlay to become transparent (indicating recording started)
        expect(overlay).to_have_class("recording-overlay transparent", timeout=2000)

        # Calculate actual delay
        actual_delay = time.time() - start_time

        # THIS IS THE BUG: Delay should be under 1 second, but is 3-5 seconds
        assert actual_delay < 1.0, f"Recording took {actual_delay:.2f}s to start, should be under 1s"

    def test_no_console_errors_on_page_load(self, page: Page, base_url: str):
        """
        Test that the recording page loads without console errors.

        Issues:
        - Multiple console errors appear on page use
        """
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # Navigate to the recording page
        page.goto(f"{base_url}/record")
        page.wait_for_load_state("networkidle")

        # Wait a bit for any async errors
        page.wait_for_timeout(2000)

        # THIS IS THE BUG: Should have no console errors
        assert len(console_errors) == 0, f"Found console errors: {console_errors}"

    def test_no_console_errors_during_recording(self, page: Page, base_url: str):
        """
        Test that no console errors appear during recording operations.

        Issues:
        - Multiple console errors pop up on every use of the page
        """
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # Navigate to the recording page
        page.goto(f"{base_url}/record")
        page.wait_for_load_state("networkidle")

        # Get elements
        overlay = page.locator("#recording-overlay")

        # Start recording
        overlay.click()
        page.wait_for_timeout(2000)

        # Stop recording
        overlay.click()
        page.wait_for_timeout(500)

        # THIS IS THE BUG: Should have no console errors during normal operation
        assert len(console_errors) == 0, f"Found console errors during recording: {console_errors}"

    def test_complete_recording_workflow(self, page: Page, base_url: str):
        """
        Test the complete recording workflow from start to save.

        This is an integration test that covers the happy path.
        """
        # Navigate to the recording page
        page.goto(f"{base_url}/record")
        page.wait_for_load_state("networkidle")

        # Get elements
        overlay = page.locator("#recording-overlay")
        timer = page.locator("#timer")
        save_btn = page.locator("#save-btn")
        cancel_btn = page.locator("#cancel-btn")

        # Initial state checks
        expect(overlay).to_contain_text("START RECORDING")
        expect(timer).to_have_text("00:00")
        expect(save_btn).not_to_be_visible()
        expect(cancel_btn).not_to_be_visible()

        # Start recording
        overlay.click()
        page.wait_for_timeout(1000)

        # Recording state checks
        expect(overlay).to_have_class("recording-overlay transparent")
        expect(cancel_btn).to_be_visible()
        expect(save_btn).not_to_be_visible()

        # Wait for recording to progress
        page.wait_for_timeout(2000)
        timer_text = timer.text_content()
        assert timer_text >= "00:02", f"Timer should show at least 2 seconds, got {timer_text}"

        # Pause recording
        overlay.click()
        page.wait_for_timeout(500)

        # Paused state checks
        expect(overlay).to_contain_text("RESUME RECORDING")
        expect(save_btn).to_be_visible()
        expect(cancel_btn).to_be_visible()

        # Note: We won't actually save in tests to avoid hitting the backend
        # but we verify the button is available and enabled
        expect(save_btn).not_to_have_class("disabled")
