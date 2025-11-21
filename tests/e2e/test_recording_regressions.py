"""
Regression tests for recording page issues discovered after initial fixes.

These tests verify:
1. Clicking viewport during recording actually pauses (MediaRecorder state)
2. Timer reflects actual pause duration
3. Save button works on first click without errors
"""

import pytest
from playwright.sync_api import Page, expect
import re


class TestRecordingRegressions:
    """Test suite for recording page regression issues."""

    def test_viewport_click_actually_pauses_recording(self, page: Page, base_url: str):
        """
        Test that clicking viewport during recording actually pauses the MediaRecorder.

        Issue: Clicking viewport appears to pause, but MediaRecorder continues recording.
        The timer shows the recording never actually paused.
        """
        # Navigate to recording page
        page.goto(f"{base_url}/record")
        page.wait_for_load_state("networkidle")

        overlay = page.locator("#recording-overlay")

        # Start recording
        overlay.click()
        page.wait_for_timeout(1000)

        # Verify recording started by checking MediaRecorder state via JS
        is_recording_before = page.evaluate("""
            () => {
                const recorder = window.recorder;
                return {
                    isRecording: recorder.isRecording,
                    isPaused: recorder.isPaused,
                    mediaRecorderState: recorder.mediaRecorder ? recorder.mediaRecorder.state : null
                };
            }
        """)

        assert is_recording_before["isRecording"] == True, "Should be recording"
        assert is_recording_before["isPaused"] == False, "Should not be paused"
        assert is_recording_before["mediaRecorderState"] == "recording", "MediaRecorder should be in 'recording' state"

        # Click to pause
        overlay.click()
        page.wait_for_timeout(500)

        # Check state after pause attempt
        is_recording_after = page.evaluate("""
            () => {
                const recorder = window.recorder;
                return {
                    isRecording: recorder.isRecording,
                    isPaused: recorder.isPaused,
                    mediaRecorderState: recorder.mediaRecorder ? recorder.mediaRecorder.state : null
                };
            }
        """)

        # THIS IS THE BUG: MediaRecorder should be in 'paused' state
        assert is_recording_after["isRecording"] == False, "Should not be recording"
        assert is_recording_after["isPaused"] == True, "Should be paused"
        assert is_recording_after["mediaRecorderState"] == "paused", f"MediaRecorder should be in 'paused' state, but is '{is_recording_after['mediaRecorderState']}'"

    def test_pause_timer_reflects_actual_pause_duration(self, page: Page, base_url: str):
        """
        Test that timer correctly reflects pause duration.

        Issue: Timer continues counting during pause, showing recording never stopped.
        """
        # Navigate to recording page
        page.goto(f"{base_url}/record")
        page.wait_for_load_state("networkidle")

        overlay = page.locator("#recording-overlay")
        timer = page.locator("#timer")

        # Start recording
        overlay.click()
        page.wait_for_timeout(2000)  # Record for 2 seconds

        # Get timer value (should be around 00:02)
        timer_before_pause = timer.text_content()
        match = re.match(r"(\d+):(\d+)", timer_before_pause)
        assert match, f"Timer should show time format MM:SS, got: {timer_before_pause}"

        minutes_before = int(match.group(1))
        seconds_before = int(match.group(2))
        total_seconds_before = minutes_before * 60 + seconds_before

        # Should be around 2 seconds (allow 1-3 seconds due to timing)
        assert 1 <= total_seconds_before <= 3, f"Timer should show ~2 seconds, got {total_seconds_before}"

        # Pause recording
        overlay.click()
        page.wait_for_timeout(500)

        # Get timer value when paused
        timer_during_pause = timer.text_content()

        # Wait 3 seconds while paused
        page.wait_for_timeout(3000)

        # Get timer value after waiting while paused
        timer_after_pause_wait = timer.text_content()

        # THIS IS THE BUG: Timer should NOT change during pause
        assert timer_during_pause == timer_after_pause_wait, \
            f"Timer should not change during pause. Was '{timer_during_pause}', became '{timer_after_pause_wait}'"

        # Resume recording
        overlay.click()
        page.wait_for_timeout(2000)  # Record for 2 more seconds

        # Get final timer value
        timer_after_resume = timer.text_content()
        match_after = re.match(r"(\d+):(\d+)", timer_after_resume)
        assert match_after, f"Timer should show time format MM:SS, got: {timer_after_resume}"

        minutes_after = int(match_after.group(1))
        seconds_after = int(match_after.group(2))
        total_seconds_after = minutes_after * 60 + seconds_after

        # Should be around 4 seconds (2 before pause + 2 after resume, NOT including 3 second pause)
        # Allow 3-5 seconds due to timing
        assert 3 <= total_seconds_after <= 5, \
            f"Timer should show ~4 seconds total (excluding pause), got {total_seconds_after}"

    def test_save_button_works_on_first_click(self, page: Page, base_url: str):
        """
        Test that save button works on first click without showing error.

        Issue: First click shows "no video/audio data to save" error,
        second click actually saves.
        """
        # Navigate to recording page
        page.goto(f"{base_url}/record")
        page.wait_for_load_state("networkidle")

        overlay = page.locator("#recording-overlay")
        save_btn = page.locator("#save-btn")
        alerts = page.locator("#alerts")

        # Start recording
        overlay.click()
        page.wait_for_timeout(2000)  # Record for 2 seconds

        # Pause recording
        overlay.click()
        page.wait_for_timeout(500)

        # Verify save button is visible
        expect(save_btn).to_be_visible()

        # Track any alerts that appear
        page.on("console", lambda msg: print(f"Console: {msg.type}: {msg.text}"))

        # Click save button ONCE
        save_btn.click()

        # Wait a moment for any alerts
        page.wait_for_timeout(1000)

        # Check for error alerts
        error_alerts = page.locator(".lcars-alert.error").all()

        # THIS IS THE BUG: Should NOT show "no data to save" error on first click
        error_messages = [alert.text_content() for alert in error_alerts if alert.is_visible()]
        no_data_errors = [msg for msg in error_messages if "No" in msg and "data to save" in msg]

        assert len(no_data_errors) == 0, \
            f"Should not show 'no data to save' error on first click. Got errors: {error_messages}"

    def test_save_has_chunks_after_recording(self, page: Page, base_url: str):
        """
        Test that chunks array is populated after recording and pausing.

        This tests the underlying issue: chunks should be available for save.
        """
        # Navigate to recording page
        page.goto(f"{base_url}/record")
        page.wait_for_load_state("networkidle")

        overlay = page.locator("#recording-overlay")

        # Start recording
        overlay.click()
        page.wait_for_timeout(2000)  # Record for 2 seconds

        # Pause recording
        overlay.click()
        page.wait_for_timeout(500)

        # Check chunks array via JavaScript
        chunks_info = page.evaluate("""
            () => {
                const recorder = window.recorder;
                return {
                    chunksLength: recorder.chunks.length,
                    mediaRecorderState: recorder.mediaRecorder ? recorder.mediaRecorder.state : null,
                    hasMediaRecorder: !!recorder.mediaRecorder
                };
            }
        """)

        print(f"Chunks info after pause: {chunks_info}")

        # THIS IS THE BUG: chunks array should have data after recording
        assert chunks_info["chunksLength"] > 0, \
            f"Chunks array should have data after recording. Length: {chunks_info['chunksLength']}, " \
            f"MediaRecorder state: {chunks_info['mediaRecorderState']}"

    def test_complete_pause_resume_save_workflow(self, page: Page, base_url: str):
        """
        Integration test for complete workflow: record -> pause -> resume -> pause -> save.
        """
        # Navigate to recording page
        page.goto(f"{base_url}/record")
        page.wait_for_load_state("networkidle")

        overlay = page.locator("#recording-overlay")
        timer = page.locator("#timer")
        save_btn = page.locator("#save-btn")

        # Start recording
        overlay.click()
        page.wait_for_timeout(2000)  # Record for 2 seconds

        # Get first timer reading
        timer1 = timer.text_content()

        # First pause
        overlay.click()
        page.wait_for_timeout(500)
        timer_paused1 = timer.text_content()

        # Wait while paused
        page.wait_for_timeout(2000)
        timer_still_paused1 = timer.text_content()

        # Timer should not advance during pause
        assert timer_paused1 == timer_still_paused1, "Timer should not advance during pause"

        # Resume
        overlay.click()
        page.wait_for_timeout(2000)  # Record for 2 more seconds

        # Second pause (final)
        overlay.click()
        page.wait_for_timeout(500)

        # Verify save button is available
        expect(save_btn).to_be_visible()
        expect(save_btn).not_to_have_class("disabled")

        # Save should work on first click
        save_btn.click()
        page.wait_for_timeout(1000)

        # Should not show error alert
        error_alert = page.locator(".lcars-alert.error")
        if error_alert.count() > 0:
            error_text = error_alert.first.text_content()
            assert "No" not in error_text or "data to save" not in error_text, \
                f"Should not show 'no data to save' error: {error_text}"
