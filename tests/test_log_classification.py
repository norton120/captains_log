"""Tests for log classification functionality."""
import pytest
import vcr
from pytest import mark as m

from app.services.openai_client import (
    OpenAIService,
    ClassificationError
)


# VCR configuration for these tests
vcr_config = {
    "filter_headers": ["authorization"],
    "record_mode": "once",
    "match_on": ["uri", "method", "body"],
    "cassette_library_dir": "tests/cassettes/classification",
}


@m.describe("Log Classification")
class TestLogClassification:
    """Test log type classification (PERSONAL vs SHIP) using LLM with VCR."""

    @m.context("When classifying explicit personal logs")
    @m.it("classifies logs starting with 'personal log' as PERSONAL")
    @pytest.mark.unit
    @pytest.mark.openai
    @vcr.use_cassette("tests/cassettes/classification/personal_log_lowercase.yaml", **vcr_config)
    async def test_classify_personal_log_lowercase(self, test_settings):
        """Should classify logs explicitly starting with 'personal log' as PERSONAL."""
        # Arrange
        service = OpenAIService(test_settings)
        transcription = "personal log. let's see if this works"

        # Act
        classification = await service.classify_log_type(transcription)

        # Assert
        assert classification == "PERSONAL"

    @m.context("When classifying explicit personal logs")
    @m.it("classifies logs starting with 'Personal log' as PERSONAL")
    @pytest.mark.unit
    @pytest.mark.openai
    @vcr.use_cassette("tests/cassettes/classification/personal_log_capitalized.yaml", **vcr_config)
    async def test_classify_personal_log_capitalized(self, test_settings):
        """Should classify logs starting with 'Personal log' (capitalized) as PERSONAL."""
        # Arrange
        service = OpenAIService(test_settings)
        transcription = "Personal log. Today I'm feeling reflective."

        # Act
        classification = await service.classify_log_type(transcription)

        # Assert
        assert classification == "PERSONAL"

    @m.context("When classifying explicit personal logs")
    @m.it("classifies logs starting with 'PERSONAL LOG' as PERSONAL")
    @pytest.mark.unit
    @pytest.mark.openai
    @vcr.use_cassette("tests/cassettes/classification/personal_log_uppercase.yaml", **vcr_config)
    async def test_classify_personal_log_uppercase(self, test_settings):
        """Should classify logs starting with 'PERSONAL LOG' (all caps) as PERSONAL."""
        # Arrange
        service = OpenAIService(test_settings)
        transcription = "PERSONAL LOG. This is a test entry."

        # Act
        classification = await service.classify_log_type(transcription)

        # Assert
        assert classification == "PERSONAL"

    @m.context("When classifying personal logs not at start")
    @m.it("classifies logs with 'personal log' in middle as PERSONAL")
    @pytest.mark.unit
    @pytest.mark.openai
    @vcr.use_cassette("tests/cassettes/classification/personal_log_in_middle.yaml", **vcr_config)
    async def test_classify_personal_log_in_middle(self, test_settings):
        """Should classify logs with 'personal log' mentioned later as PERSONAL."""
        # Arrange
        service = OpenAIService(test_settings)
        transcription = "This is a test. Personal log, stardate today."

        # Act
        classification = await service.classify_log_type(transcription)

        # Assert
        assert classification == "PERSONAL"

    @m.context("When classifying ship logs")
    @m.it("classifies logs starting with 'Captain's log' as SHIP")
    @pytest.mark.unit
    @pytest.mark.openai
    @vcr.use_cassette("tests/cassettes/classification/captains_log.yaml", **vcr_config)
    async def test_classify_captains_log(self, test_settings):
        """Should classify logs starting with 'Captain's log' as SHIP."""
        # Arrange
        service = OpenAIService(test_settings)
        transcription = "Captain's log, stardate 47634.4. We encountered a spatial anomaly."

        # Act
        classification = await service.classify_log_type(transcription)

        # Assert
        assert classification == "SHIP"

    @m.context("When classifying ship logs")
    @m.it("classifies logs starting with 'Ship's log' as SHIP")
    @pytest.mark.unit
    @pytest.mark.openai
    @vcr.use_cassette("tests/cassettes/classification/ships_log.yaml", **vcr_config)
    async def test_classify_ships_log(self, test_settings):
        """Should classify logs starting with 'Ship's log' as SHIP."""
        # Arrange
        service = OpenAIService(test_settings)
        transcription = "Ship's log. Today's voyage went smoothly."

        # Act
        classification = await service.classify_log_type(transcription)

        # Assert
        assert classification == "SHIP"

    @m.context("When classifying ship logs")
    @m.it("classifies logs with crew role indicators as SHIP")
    @pytest.mark.unit
    @pytest.mark.openai
    @vcr.use_cassette("tests/cassettes/classification/crew_role_log.yaml", **vcr_config)
    async def test_classify_crew_role_log(self, test_settings):
        """Should classify logs with crew role indicators as SHIP."""
        # Arrange
        service = OpenAIService(test_settings)
        transcription = "Chief Engineer's log. The warp core is running at optimal efficiency."

        # Act
        classification = await service.classify_log_type(transcription)

        # Assert
        assert classification == "SHIP"

    @m.context("When classifying ambiguous logs")
    @m.it("defaults to SHIP for logs without clear indicators")
    @pytest.mark.unit
    @pytest.mark.openai
    @vcr.use_cassette("tests/cassettes/classification/ambiguous_log.yaml", **vcr_config)
    async def test_classify_ambiguous_log_defaults_to_ship(self, test_settings):
        """Should default to SHIP for logs without clear personal/ship indicators."""
        # Arrange
        service = OpenAIService(test_settings)
        transcription = "Today was a good day. We made great progress."

        # Act
        classification = await service.classify_log_type(transcription)

        # Assert
        assert classification == "SHIP"

    @m.context("When classifying empty transcriptions")
    @m.it("raises ClassificationError for empty transcriptions")
    @pytest.mark.unit
    async def test_classify_empty_transcription(self, test_settings):
        """Should raise ClassificationError for empty transcriptions."""
        # Arrange
        service = OpenAIService(test_settings)

        # Act & Assert
        with pytest.raises(ClassificationError, match="Empty transcription"):
            await service.classify_log_type("")

    @m.context("When classifying whitespace-only transcriptions")
    @m.it("raises ClassificationError for whitespace-only transcriptions")
    @pytest.mark.unit
    async def test_classify_whitespace_transcription(self, test_settings):
        """Should raise ClassificationError for whitespace-only transcriptions."""
        # Arrange
        service = OpenAIService(test_settings)

        # Act & Assert
        with pytest.raises(ClassificationError, match="Empty transcription"):
            await service.classify_log_type("   \n\t  ")

    @m.context("When classifying multiline transcriptions")
    @m.it("handles multiline content correctly")
    @pytest.mark.unit
    @pytest.mark.openai
    @vcr.use_cassette("tests/cassettes/classification/multiline_personal.yaml", **vcr_config)
    async def test_classify_multiline_personal(self, test_settings):
        """Should handle multiline transcriptions correctly."""
        # Arrange
        service = OpenAIService(test_settings)
        transcription = """Personal log, this is my entry.
Line 2 of content.
Line 3 of content.
Line 4 of more content."""

        # Act
        classification = await service.classify_log_type(transcription)

        # Assert
        assert classification == "PERSONAL"

    @m.context("When personal log has variations")
    @m.it("handles 'personal log' with punctuation variations")
    @pytest.mark.unit
    @pytest.mark.openai
    @vcr.use_cassette("tests/cassettes/classification/personal_log_with_comma.yaml", **vcr_config)
    async def test_classify_personal_log_with_comma(self, test_settings):
        """Should handle 'personal log' followed by comma."""
        # Arrange
        service = OpenAIService(test_settings)
        transcription = "personal log, stardate today. This is my entry."

        # Act
        classification = await service.classify_log_type(transcription)

        # Assert
        assert classification == "PERSONAL"

    @m.context("When testing edge cases")
    @m.it("handles single word 'personal log'")
    @pytest.mark.unit
    @pytest.mark.openai
    @vcr.use_cassette("tests/cassettes/classification/personal_log_minimal.yaml", **vcr_config)
    async def test_classify_personal_log_minimal(self, test_settings):
        """Should handle minimal 'personal log' input."""
        # Arrange
        service = OpenAIService(test_settings)
        transcription = "personal log"

        # Act
        classification = await service.classify_log_type(transcription)

        # Assert
        assert classification == "PERSONAL"
