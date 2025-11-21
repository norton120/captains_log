import pytest
from playwright.sync_api import Page, BrowserContext, Browser, expect
import os


@pytest.fixture(scope="session")
def base_url():
    """Get the base URL for the application."""
    return os.environ.get("BASE_URL", "http://localhost")


@pytest.fixture
def context(browser: Browser):
    """Create a new browser context with permissions for media devices."""
    context = browser.new_context(
        permissions=["microphone", "camera"],
        viewport={"width": 1280, "height": 720},
    )
    yield context
    context.close()


@pytest.fixture
def page(context: BrowserContext):
    """Create a new page in the browser context."""
    page = context.new_page()

    # Mock getUserMedia to avoid actual media device access
    page.add_init_script("""
        // Store original getUserMedia
        const originalGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);

        // Create a mock audio/video stream
        navigator.mediaDevices.getUserMedia = async function(constraints) {
            console.log('Mock getUserMedia called with:', constraints);

            // Create a canvas for video track
            const canvas = document.createElement('canvas');
            canvas.width = 640;
            canvas.height = 480;
            const canvasStream = canvas.captureStream(30);

            // Create audio context for audio track
            const audioContext = new AudioContext();
            const oscillator = audioContext.createOscillator();
            const dest = audioContext.createMediaStreamDestination();
            oscillator.connect(dest);
            oscillator.start();

            const tracks = [];
            if (constraints.audio) {
                tracks.push(...dest.stream.getAudioTracks());
            }
            if (constraints.video) {
                tracks.push(...canvasStream.getVideoTracks());
            }

            return new MediaStream(tracks);
        };
    """)

    yield page
    page.close()
