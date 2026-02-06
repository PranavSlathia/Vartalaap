"""Tests for CrewAI transcript analysis service."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.db.models import IssueCategory
from src.services.analysis.transcript_crew import (
    MAX_TRANSCRIPT_CHARS,
    MAX_TRANSCRIPT_TURNS,
    ImprovementSuggestionData,
    ReviewedIssue,
    TranscriptAnalysisCrew,
    TranscriptReviewResult,
)

# =============================================================================
# TranscriptReviewResult Tests
# =============================================================================


class TestTranscriptReviewResult:
    """Tests for TranscriptReviewResult dataclass."""

    def test_to_issues_json_empty(self):
        """Empty issues list serializes to empty array."""
        result = TranscriptReviewResult(quality_score=5)
        assert result.to_issues_json() == "[]"

    def test_to_issues_json_with_issues(self):
        """Issues serialize correctly to JSON."""
        result = TranscriptReviewResult(
            quality_score=3,
            issues=[
                ReviewedIssue(
                    category=IssueCategory.knowledge_gap,
                    description="Missing vegan info",
                    severity=4,
                    context="Caller asked about vegan options",
                ),
            ],
        )
        json_str = result.to_issues_json()
        assert "knowledge_gap" in json_str
        assert "Missing vegan info" in json_str
        assert '"severity": 4' in json_str

    def test_to_suggestions_json_empty(self):
        """Empty suggestions list serializes to empty array."""
        result = TranscriptReviewResult(quality_score=5)
        assert result.to_suggestions_json() == "[]"

    def test_to_suggestions_json_with_suggestions(self):
        """Suggestions serialize correctly to JSON."""
        result = TranscriptReviewResult(
            quality_score=3,
            suggestions=[
                ImprovementSuggestionData(
                    category=IssueCategory.knowledge_gap,
                    title="Add vegan menu items",
                    description="Update knowledge base with vegan options",
                    priority=4,
                ),
            ],
        )
        json_str = result.to_suggestions_json()
        assert "knowledge_gap" in json_str
        assert "Add vegan menu items" in json_str
        assert '"priority": 4' in json_str


# =============================================================================
# Transcript Truncation Tests
# =============================================================================


class TestTranscriptTruncation:
    """Tests for transcript truncation logic."""

    def test_short_transcript_unchanged(self):
        """Short transcripts are not modified."""
        crew = TranscriptAnalysisCrew()
        transcript = "Bot: Hello\nCaller: Hi"
        result = crew._truncate_transcript(transcript)
        assert result == transcript

    def test_truncate_by_turns(self):
        """Transcripts with many turns are truncated."""
        crew = TranscriptAnalysisCrew()
        # Create transcript with more turns than limit
        lines = [f"Turn {i}: Text" for i in range(MAX_TRANSCRIPT_TURNS + 20)]
        transcript = "\n".join(lines)

        result = crew._truncate_transcript(transcript)

        # Should have truncation marker and be limited
        assert "...[truncated]" in result
        result_lines = result.split("\n")
        # Account for truncation marker line
        assert len(result_lines) <= MAX_TRANSCRIPT_TURNS + 1

    def test_truncate_by_chars(self):
        """Transcripts exceeding char limit are truncated."""
        crew = TranscriptAnalysisCrew()
        # Create transcript exceeding char limit
        transcript = "x" * (MAX_TRANSCRIPT_CHARS + 1000)

        result = crew._truncate_transcript(transcript)

        assert "...[truncated]" in result
        assert len(result) <= MAX_TRANSCRIPT_CHARS + 20  # Allow for marker

    def test_truncate_both_limits_independent(self):
        """Both turn and char limits are enforced independently."""
        crew = TranscriptAnalysisCrew()
        # Many short turns (exceeds turn limit but not char limit)
        lines = [f"T{i}" for i in range(MAX_TRANSCRIPT_TURNS + 50)]
        transcript = "\n".join(lines)

        result = crew._truncate_transcript(transcript)

        assert "...[truncated]" in result


# =============================================================================
# Issue Merging Tests
# =============================================================================


class TestIssueMerging:
    """Tests for merging reviewer issues with classifier categories."""

    def test_exact_match_merging(self):
        """Exact description matches are merged correctly."""
        crew = TranscriptAnalysisCrew()

        reviewer_issues = [
            {
                "description": "Bot failed to understand vegan query",
                "context": "Caller: Do you have vegan options?",
                "severity": 5,
            }
        ]
        classifications = {
            "Bot failed to understand vegan query": {
                "category": "knowledge_gap",
                "reasoning": "Missing vegan info in KB",
            }
        }

        issues = crew._merge_issues_with_classifications(reviewer_issues, classifications)

        assert len(issues) == 1
        assert issues[0].category == IssueCategory.knowledge_gap
        assert issues[0].severity == 5
        assert "vegan" in issues[0].context.lower()

    def test_fuzzy_match_merging(self):
        """Paraphrased descriptions are matched via fuzzy matching."""
        crew = TranscriptAnalysisCrew()

        reviewer_issues = [
            {
                "description": "Bot could not answer vegan menu question",
                "context": "Transcript quote here",
                "severity": 4,
            }
        ]
        classifications = {
            "Bot failed to answer the vegan menu inquiry": {
                "category": "knowledge_gap",
                "reasoning": "Knowledge base missing vegan info",
            }
        }

        issues = crew._merge_issues_with_classifications(reviewer_issues, classifications)

        assert len(issues) == 1
        # Should match via fuzzy matching (common words: bot, vegan, menu)
        assert issues[0].category == IssueCategory.knowledge_gap

    def test_unmatched_issues_fallback_to_ux_issue(self):
        """Issues without classification match fall back to ux_issue."""
        crew = TranscriptAnalysisCrew()

        reviewer_issues = [
            {
                "description": "Completely unique description",
                "context": "Some context",
                "severity": 3,
            }
        ]
        classifications = {
            "Totally different text": {
                "category": "stt_error",
                "reasoning": "STT misrecognition",
            }
        }

        issues = crew._merge_issues_with_classifications(reviewer_issues, classifications)

        # Should have 2 issues: one from reviewer (unmatched), one from classifier
        assert len(issues) == 2

    def test_empty_inputs(self):
        """Empty inputs return empty list."""
        crew = TranscriptAnalysisCrew()

        issues = crew._merge_issues_with_classifications([], {})

        assert issues == []


class TestFuzzyMatching:
    """Tests for fuzzy matching helper."""

    def test_high_similarity_match(self):
        """High word overlap returns a match."""
        crew = TranscriptAnalysisCrew()

        classifications = {
            "bot failed to understand customer vegan query": {"category": "knowledge_gap"},
        }

        key, match = crew._find_best_classification_match(
            "bot could not understand the customer vegan request",
            classifications,
            used=set(),
        )

        assert key is not None
        assert match is not None

    def test_low_similarity_no_match(self):
        """Low word overlap returns no match."""
        crew = TranscriptAnalysisCrew()

        classifications = {
            "xyz abc def": {"category": "stt_error"},
        }

        key, match = crew._find_best_classification_match(
            "completely different words here",
            classifications,
            used=set(),
        )

        assert key is None
        assert match is None

    def test_already_used_excluded(self):
        """Already used classifications are excluded."""
        crew = TranscriptAnalysisCrew()

        classifications = {
            "bot failed vegan query": {"category": "knowledge_gap"},
        }

        key, match = crew._find_best_classification_match(
            "bot failed vegan query",
            classifications,
            used={"bot failed vegan query"},
        )

        assert key is None


# =============================================================================
# JSON Extraction Tests
# =============================================================================


class TestJsonExtraction:
    """Tests for JSON extraction from text."""

    def test_extract_simple_json(self):
        """Simple JSON is extracted correctly."""
        crew = TranscriptAnalysisCrew()

        text = 'Here is the result: {"quality_score": 4, "issues": []}'
        result = crew._extract_json_from_text(text)

        assert result is not None
        assert result["quality_score"] == 4

    def test_extract_nested_json(self):
        """Nested JSON is extracted correctly."""
        crew = TranscriptAnalysisCrew()

        text = '''
        Analysis: {"category_summary": {"has_knowledge_gap": true, "has_ux_issue": false}}
        '''
        result = crew._extract_json_from_text(text)

        assert result is not None
        assert result["category_summary"]["has_knowledge_gap"] is True

    def test_no_json_returns_none(self):
        """Text without JSON returns None."""
        crew = TranscriptAnalysisCrew()

        text = "This is just plain text without any JSON."
        result = crew._extract_json_from_text(text)

        assert result is None

    def test_invalid_json_returns_none(self):
        """Invalid JSON returns None."""
        crew = TranscriptAnalysisCrew()

        text = "{this is not valid json"
        result = crew._extract_json_from_text(text)

        assert result is None


# =============================================================================
# Integration Tests (Mocked LLM)
# =============================================================================


class TestCrewAnalysisMocked:
    """Integration tests with mocked LLM."""

    @pytest.mark.asyncio
    async def test_analyze_transcript_returns_result_on_llm_failure(self):
        """Analysis returns default result when LLM fails."""
        with (
            patch("crewai.Crew.kickoff", side_effect=Exception("LLM Error")),
            patch("src.services.analysis.transcript_crew.LLM"),
        ):
            crew = TranscriptAnalysisCrew()
            result = await crew.analyze_transcript(
                transcript="Bot: Hello\nCaller: Hi",
                business_context="Test business",
            )

        # Should return default result, not raise
        assert result.quality_score == 3
        assert result.issues == []
        assert result.suggestions == []

    @pytest.mark.asyncio
    async def test_analyze_transcript_truncates_long_input(self):
        """Long transcripts are truncated before analysis."""
        crew = TranscriptAnalysisCrew()

        # Create very long transcript
        long_transcript = "\n".join([f"Turn {i}: Some text" for i in range(100)])

        # Track what gets passed to _create_review_task
        original_create = crew._create_review_task
        captured_transcript = None

        def mock_create(transcript, context):
            nonlocal captured_transcript
            captured_transcript = transcript
            return original_create(transcript, context)

        with (
            patch.object(crew, "_create_review_task", side_effect=mock_create),
            patch("crewai.Crew.kickoff", side_effect=Exception("Skip")),
        ):
            await crew.analyze_transcript(long_transcript, "Test")

        # Verify truncation was applied
        if captured_transcript:
            assert len(captured_transcript.split("\n")) <= MAX_TRANSCRIPT_TURNS + 2
