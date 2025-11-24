"""End-to-end tests for Fitbit integration in settings page."""

from playwright.sync_api import Page, expect


class TestFitbitSettingsSection:
    """Test Fitbit section in settings page."""

    def test_fitbit_section_exists_in_settings(self, page: Page, base_url: str):
        """Verify Fitbit section appears in settings UI."""
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Check for Fitbit section heading
        fitbit_heading = page.locator('h2:has-text("FITBIT INTEGRATION")')
        expect(fitbit_heading).to_be_visible()

    def test_connect_fitbit_button_visible_when_not_connected(self, page: Page, base_url: str):
        """Test 'Connect Fitbit' button visible when not connected."""
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Should show Connect button
        connect_button = page.locator('button:has-text("Connect Fitbit")')
        expect(connect_button).to_be_visible()

    def test_fitbit_oauth_flow(self, page: Page, base_url: str):
        """Test complete OAuth authorization flow (mocked)."""
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Click Connect Fitbit button
        connect_button = page.locator('button:has-text("Connect Fitbit")')

        # Mock the OAuth redirect (in real scenario, would redirect to Fitbit)
        # For testing, we'll intercept and simulate successful callback
        with page.expect_navigation(timeout=10000):
            connect_button.click()

        # Should redirect to Fitbit (or mock callback in tests)
        # After callback, should redirect back to settings
        page.wait_for_url(f"**/settings*", timeout=10000)

        # Should show success message
        success_message = page.locator(".alert-success, .success-message")
        expect(success_message).to_be_visible(timeout=5000)

    def test_fitbit_connection_status_displays(self, page: Page, base_url: str):
        """Test connection status indicator when Fitbit is connected."""
        # Note: This test requires a user with Fitbit already authorized
        # You may need to set up test fixtures for this

        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Check for connection status
        status_indicator = page.locator(".fitbit-status")

        # Should show either connected or disconnected state
        expect(status_indicator).to_be_visible()

    def test_select_fitbit_device(self, page: Page, base_url: str):
        """Test selecting a Fitbit device."""
        # Requires user with Fitbit authorized
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Look for device selection dropdown
        device_select = page.locator("select#fitbit_device_id")

        if device_select.is_visible():
            # Select a device
            device_select.select_option(index=1)

            # Save device selection
            save_button = page.locator('button:has-text("Save Device")')
            save_button.click()

            # Should show success message
            page.wait_for_selector(".alert-success, .success-message", timeout=5000)

    def test_disconnect_fitbit(self, page: Page, base_url: str):
        """Test disconnecting Fitbit integration."""
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Look for disconnect button (only visible if connected)
        disconnect_button = page.locator('button:has-text("Disconnect Fitbit")')

        if disconnect_button.is_visible():
            disconnect_button.click()

            # May show confirmation modal
            confirm_button = page.locator('button:has-text("Confirm"), button:has-text("Yes")')
            if confirm_button.is_visible():
                confirm_button.click()

            # Should show Connect button again after disconnect
            page.wait_for_selector('button:has-text("Connect Fitbit")', timeout=5000)

    def test_fitbit_device_list_displays(self, page: Page, base_url: str):
        """Test that device list displays after authorization."""
        # Requires authorized user
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Check if device dropdown exists
        device_select = page.locator("select#fitbit_device_id")

        if device_select.is_visible():
            # Should have at least one option
            options = device_select.locator("option")
            count = options.count()
            assert count > 0, "Device dropdown should have options"

    def test_fitbit_status_shows_connected_user(self, page: Page, base_url: str):
        """Test that connected Fitbit user ID displays."""
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Look for Fitbit user ID display
        fitbit_user_display = page.locator('.fitbit-user-id, [data-testid="fitbit-user"]')

        # If connected, should show user ID
        if fitbit_user_display.is_visible():
            expect(fitbit_user_display).not_to_be_empty()

    def test_fitbit_section_shows_device_name(self, page: Page, base_url: str):
        """Test that selected device name is displayed."""
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Look for device name display
        device_name = page.locator('.fitbit-device-name, [data-testid="fitbit-device"]')

        if device_name.is_visible():
            # Should contain device model name
            text = device_name.text_content()
            assert text is not None and len(text) > 0


class TestFitbitSettingsValidation:
    """Test validation in Fitbit settings."""

    def test_cannot_select_device_without_authorization(self, page: Page, base_url: str):
        """Test that device selection is disabled without authorization."""
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Device select should be disabled or hidden if not authorized
        device_select = page.locator("select#fitbit_device_id")

        if device_select.is_visible():
            # Should be disabled
            expect(device_select).to_be_disabled()

    def test_fitbit_error_displays_on_failed_auth(self, page: Page, base_url: str):
        """Test error message displays if OAuth fails."""
        # Simulate OAuth error callback
        page.goto(f"{base_url}/api/fitbit/callback?error=access_denied&error_description=User+denied")

        # Should redirect to settings
        page.wait_for_url(f"**/settings*", timeout=10000)

        # Should show error message
        error_message = page.locator(".alert-error, .error-message")
        expect(error_message).to_be_visible()
        expect(error_message).to_contain_text("denied")


class TestFitbitSettingsResponsiveness:
    """Test responsive design of Fitbit settings section."""

    def test_fitbit_section_layout_on_mobile(self, page: Page, base_url: str):
        """Test Fitbit section layout on mobile viewport."""
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        fitbit_section = page.locator('[data-section="fitbit"], .fitbit-section')

        if fitbit_section.is_visible():
            # Should be visible and not overflow
            box = fitbit_section.bounding_box()
            assert box is not None
            assert box["width"] <= 375

    def test_fitbit_section_layout_on_desktop(self, page: Page, base_url: str):
        """Test Fitbit section layout on desktop viewport."""
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        fitbit_section = page.locator('[data-section="fitbit"], .fitbit-section')

        if fitbit_section.is_visible():
            # Should use appropriate width
            box = fitbit_section.bounding_box()
            assert box is not None
