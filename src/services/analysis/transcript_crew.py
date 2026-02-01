"""CrewAI-based transcript analysis for internal QA.

Uses a multi-agent crew to:
1. Review call transcripts for quality issues
2. Classify issues by category
3. Generate actionable improvement suggestions

NOT real-time or caller-facing - this is admin tooling for continuous improvement.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from crewai import Agent, Crew, LLM, Process, Task

from src.config import get_settings
from src.db.models import IssueCategory
from src.logging_config import get_logger

logger: Any = get_logger(__name__)

# Transcript length limits to fit within model context window
MAX_TRANSCRIPT_TURNS = 50  # Maximum conversation turns to analyze
MAX_TRANSCRIPT_CHARS = 12000  # ~3K tokens, safe for most models


@dataclass
class ReviewedIssue:
    """An issue identified in a transcript."""

    category: IssueCategory
    description: str
    severity: int  # 1-5
    context: str  # Relevant portion of transcript


@dataclass
class ImprovementSuggestionData:
    """An actionable suggestion from the review."""

    category: IssueCategory
    title: str
    description: str
    priority: int  # 1-5


@dataclass
class TranscriptReviewResult:
    """Result of transcript analysis by the agent crew."""

    quality_score: int  # 1-5
    issues: list[ReviewedIssue] = field(default_factory=list)
    suggestions: list[ImprovementSuggestionData] = field(default_factory=list)
    has_unanswered_query: bool = False
    has_knowledge_gap: bool = False
    has_prompt_weakness: bool = False
    has_ux_issue: bool = False
    review_latency_ms: float = 0.0

    def to_issues_json(self) -> str:
        """Serialize issues to JSON for database storage."""
        return json.dumps([
            {
                "category": issue.category.value,
                "description": issue.description,
                "severity": issue.severity,
                "context": issue.context,
            }
            for issue in self.issues
        ])

    def to_suggestions_json(self) -> str:
        """Serialize suggestions to JSON for database storage."""
        return json.dumps([
            {
                "category": suggestion.category.value,
                "title": suggestion.title,
                "description": suggestion.description,
                "priority": suggestion.priority,
            }
            for suggestion in self.suggestions
        ])


class TranscriptAnalysisCrew:
    """CrewAI crew for analyzing call transcripts.

    Uses three specialized agents:
    1. QA Reviewer: Identifies issues and rates call quality
    2. Issue Classifier: Categorizes issues by root cause
    3. Improvement Suggester: Generates actionable fixes

    Example:
        crew = TranscriptAnalysisCrew()
        result = await crew.analyze_transcript(transcript_text, business_context)
    """

    def __init__(
        self,
        groq_api_key: str | None = None,
        model: str = "groq/llama-3.3-70b-versatile",
        temperature: float = 0.1,
    ):
        """Initialize the transcript analysis crew.

        Args:
            groq_api_key: Groq API key (defaults to settings)
            model: LLM model to use (litellm format: provider/model)
            temperature: LLM temperature (lower = more consistent)
        """
        settings = get_settings()
        self._api_key = groq_api_key or settings.groq_api_key
        self._model = model
        self._temperature = temperature
        self._llm = None

    @property
    def llm(self) -> LLM:
        """Lazy initialization of LLM using CrewAI's LLM wrapper."""
        if self._llm is None:
            # Convert SecretStr to plain string if needed
            api_key = self._api_key
            if hasattr(api_key, 'get_secret_value'):
                api_key = api_key.get_secret_value()
            self._llm = LLM(
                model=self._model,
                api_key=api_key,
                temperature=self._temperature,
            )
        return self._llm

    def _truncate_transcript(self, transcript: str) -> str:
        """Truncate transcript to fit model context window.

        Enforces BOTH limits independently:
        - MAX_TRANSCRIPT_TURNS: Maximum conversation turns
        - MAX_TRANSCRIPT_CHARS: Maximum characters (~3K tokens)

        Preserves recent turns (more relevant for analysis).
        """
        truncated = False

        # First limit: number of turns (lines)
        lines = transcript.split('\n')
        if len(lines) > MAX_TRANSCRIPT_TURNS:
            lines = lines[-MAX_TRANSCRIPT_TURNS:]
            transcript = '\n'.join(lines)
            truncated = True

        # Second limit: character count
        if len(transcript) > MAX_TRANSCRIPT_CHARS:
            transcript = transcript[-MAX_TRANSCRIPT_CHARS:]
            # Find first complete line after truncation
            first_newline = transcript.find('\n')
            if first_newline > 0:
                transcript = transcript[first_newline + 1:]
            truncated = True

        # Add truncation marker if any limit was applied
        if truncated:
            transcript = "...[truncated]\n" + transcript

        return transcript

    def _create_qa_reviewer_agent(self) -> Agent:
        """Create the QA reviewer agent."""
        return Agent(
            role="Call Quality Analyst",
            goal="Identify issues in voice bot call transcripts and rate call quality",
            backstory="""You are an expert at analyzing customer service calls for a voice bot
platform. You have deep experience with Hindi/English bilingual calls and understand
the nuances of code-switching (Hinglish). You focus on identifying moments where:
- The bot failed to understand the customer
- The bot provided incorrect or incomplete information
- The conversation flow was awkward or confusing
- The customer expressed frustration or confusion
- Technical issues (STT/TTS) affected the experience

You rate calls on a 1-5 scale where:
5 = Perfect handling, customer satisfied
4 = Minor issues but customer needs met
3 = Some issues, customer partially satisfied
2 = Significant issues, customer frustrated
1 = Complete failure, customer needs unmet""",
            llm=self.llm,
            verbose=True,
        )

    def _create_classifier_agent(self) -> Agent:
        """Create the issue classifier agent."""
        return Agent(
            role="Issue Classifier",
            goal="Categorize identified issues by root cause for prioritization",
            backstory="""You are an expert at root cause analysis for voice bot systems.
You classify issues into these categories:
- knowledge_gap: Missing information in the knowledge base
- prompt_weakness: LLM prompt needs improvement
- ux_issue: User experience friction (flow, timing, tone)
- stt_error: Speech-to-text misrecognition
- tts_issue: Text-to-speech quality problems
- config_error: Business configuration problem

You understand that multiple issues can have the same root cause, and accurate
classification is critical for prioritizing engineering work.""",
            llm=self.llm,
            verbose=True,
        )

    def _create_improver_agent(self) -> Agent:
        """Create the improvement suggester agent."""
        return Agent(
            role="Improvement Specialist",
            goal="Generate specific, actionable suggestions to fix identified issues",
            backstory="""You are a voice bot optimization expert who turns issue analysis
into concrete improvements. For each issue you suggest:
- A clear, specific action (not vague advice)
- The expected impact on call quality
- Priority level (1-5 based on frequency and severity)

For knowledge gaps: suggest exact content to add
For prompt issues: suggest prompt modifications
For UX issues: suggest flow changes
For technical issues: flag for engineering review

You prioritize suggestions that will have the highest impact on customer satisfaction.""",
            llm=self.llm,
            verbose=True,
        )

    def _create_review_task(self, transcript: str, business_context: str) -> Task:
        """Create the initial review task."""
        return Task(
            description=f"""Analyze this voice bot call transcript and identify any issues.

## Business Context
{business_context}

## Transcript
{transcript}

## Your Task
1. Read through the entire transcript carefully
2. Identify any moments where the conversation went poorly
3. Note specific issues with exact quotes from the transcript
4. Rate the overall call quality (1-5)

## Expected Output Format (JSON)
{{
    "quality_score": <1-5>,
    "issues": [
        {{
            "description": "Brief description of the issue",
            "context": "Exact quote from transcript showing the issue",
            "severity": <1-5>
        }}
    ],
    "overall_assessment": "2-3 sentence summary of call quality"
}}""",
            agent=self._create_qa_reviewer_agent(),
            expected_output="JSON object with quality_score, issues array, and overall_assessment",
        )

    def _create_classify_task(self, review_task: Task) -> Task:
        """Create the classification task."""
        return Task(
            description="""Classify each issue identified in the previous analysis by root cause.

## Issue Categories
- knowledge_gap: Missing information in the knowledge base
- prompt_weakness: LLM prompt needs improvement
- ux_issue: User experience friction (flow, timing, tone)
- stt_error: Speech-to-text misrecognition
- tts_issue: Text-to-speech quality problems
- config_error: Business configuration problem

## Expected Output Format (JSON)
{{
    "classified_issues": [
        {{
            "original_description": "From previous analysis",
            "category": "knowledge_gap|prompt_weakness|ux_issue|stt_error|tts_issue|config_error",
            "reasoning": "Why this category was chosen"
        }}
    ],
    "category_summary": {{
        "has_unanswered_query": true/false,
        "has_knowledge_gap": true/false,
        "has_prompt_weakness": true/false,
        "has_ux_issue": true/false
    }}
}}""",
            agent=self._create_classifier_agent(),
            context=[review_task],
            expected_output="JSON with classified_issues array and category_summary flags",
        )

    def _create_improve_task(self, review_task: Task, classify_task: Task) -> Task:
        """Create the improvement suggestion task."""
        return Task(
            description="""Generate actionable improvements based on the identified issues.

## Guidelines
- Be specific (not "improve the prompt" but "add handling for X scenario")
- Include the expected impact
- Prioritize by frequency and severity
- For knowledge gaps, suggest exact content to add

## Expected Output Format (JSON)
{{
    "suggestions": [
        {{
            "category": "knowledge_gap|prompt_weakness|ux_issue|stt_error|tts_issue|config_error",
            "title": "Short actionable title (max 100 chars)",
            "description": "Detailed description with specific fix",
            "priority": <1-5 where 5 is most critical>,
            "expected_impact": "What will improve if this is implemented"
        }}
    ]
}}""",
            agent=self._create_improver_agent(),
            context=[review_task, classify_task],
            expected_output="JSON with suggestions array containing actionable improvements",
        )

    async def analyze_transcript(
        self,
        transcript: str,
        business_context: str = "",
    ) -> TranscriptReviewResult:
        """Analyze a call transcript using the agent crew.

        Args:
            transcript: The call transcript (formatted conversation)
            business_context: Additional context about the business

        Returns:
            TranscriptReviewResult with quality score, issues, and suggestions
        """
        start_time = time.perf_counter()

        # Truncate long transcripts to fit model context window
        transcript = self._truncate_transcript(transcript)

        # Create tasks
        review_task = self._create_review_task(transcript, business_context)
        classify_task = self._create_classify_task(review_task)
        improve_task = self._create_improve_task(review_task, classify_task)

        # Create and run crew
        crew = Crew(
            agents=[
                self._create_qa_reviewer_agent(),
                self._create_classifier_agent(),
                self._create_improver_agent(),
            ],
            tasks=[review_task, classify_task, improve_task],
            process=Process.sequential,
            memory=True,  # Enable short-term memory for context sharing between agents
            verbose=True,
        )

        try:
            # Run the crew (synchronous - CrewAI doesn't support async natively)
            import asyncio
            loop = asyncio.get_event_loop()
            raw_result = await loop.run_in_executor(None, crew.kickoff)

            # Parse results
            result = self._parse_crew_output(raw_result)
            result.review_latency_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                f"Transcript analysis complete: score={result.quality_score}, "
                f"issues={len(result.issues)}, suggestions={len(result.suggestions)}, "
                f"latency={result.review_latency_ms:.0f}ms"
            )

            return result

        except Exception as e:
            logger.error(f"Transcript analysis failed: {e}")
            # Return a default result on failure
            return TranscriptReviewResult(
                quality_score=3,
                review_latency_ms=(time.perf_counter() - start_time) * 1000,
            )

    def _parse_crew_output(self, raw_result: Any) -> TranscriptReviewResult:
        """Parse CrewAI output using built-in json_dict property.

        Merges data from all three tasks:
        - QA Reviewer: quality_score, issues (with severity, context/transcript quote)
        - Classifier: classified_issues (with category), category_summary flags
        - Improver: suggestions
        """
        quality_score = 3
        suggestions: list[ImprovementSuggestionData] = []
        has_unanswered_query = False
        has_knowledge_gap = False
        has_prompt_weakness = False
        has_ux_issue = False

        # Collect raw issues from QA reviewer (has severity + transcript context)
        reviewer_issues: list[dict] = []
        # Collect classifications (has category + reasoning)
        classifications: dict[str, dict] = {}  # keyed by description for matching

        # CrewAI returns CrewOutput with tasks_output list
        # Each TaskOutput has json_dict property for pre-parsed JSON
        try:
            tasks_output = getattr(raw_result, 'tasks_output', [])

            for task_output in tasks_output:
                # Try built-in json_dict first (handles nested JSON correctly)
                data = getattr(task_output, 'json_dict', None)
                if not data:
                    # Fallback: try parsing raw output with proper decoder
                    raw = getattr(task_output, 'raw', '')
                    data = self._extract_json_from_text(raw)

                if not data:
                    continue

                # Extract quality score from reviewer
                if "quality_score" in data:
                    quality_score = int(data.get("quality_score", 3))

                # Extract issues from QA reviewer (has severity + context)
                if "issues" in data and "quality_score" in data:
                    reviewer_issues = data.get("issues", [])

                # Extract classifications from classifier
                if "classified_issues" in data:
                    for ci in data.get("classified_issues", []):
                        desc = ci.get("original_description", "")
                        classifications[desc] = ci

                # Extract category flags from classifier
                if "category_summary" in data:
                    summary = data["category_summary"]
                    has_unanswered_query = summary.get("has_unanswered_query", False)
                    has_knowledge_gap = summary.get("has_knowledge_gap", False)
                    has_prompt_weakness = summary.get("has_prompt_weakness", False)
                    has_ux_issue = summary.get("has_ux_issue", False)

                # Extract suggestions from improver
                if "suggestions" in data:
                    for sugg_data in data["suggestions"]:
                        category_str = sugg_data.get("category", "ux_issue")
                        try:
                            category = IssueCategory(category_str)
                        except ValueError:
                            category = IssueCategory.ux_issue

                        suggestions.append(ImprovementSuggestionData(
                            category=category,
                            title=sugg_data.get("title", "Improvement needed")[:200],
                            description=sugg_data.get("description", "")[:2000],
                            priority=int(sugg_data.get("priority", 3)),
                        ))

        except Exception as e:
            logger.warning(f"Failed to parse crew output via json_dict: {e}")

        # Merge reviewer issues with classifier categories
        issues = self._merge_issues_with_classifications(reviewer_issues, classifications)

        return TranscriptReviewResult(
            quality_score=max(1, min(5, quality_score)),
            issues=issues,
            suggestions=suggestions,
            has_unanswered_query=has_unanswered_query,
            has_knowledge_gap=has_knowledge_gap,
            has_prompt_weakness=has_prompt_weakness,
            has_ux_issue=has_ux_issue,
        )

    def _merge_issues_with_classifications(
        self,
        reviewer_issues: list[dict],
        classifications: dict[str, dict],
    ) -> list[ReviewedIssue]:
        """Merge QA reviewer issues with classifier categories.

        Reviewer provides: description, context (transcript quote), severity
        Classifier provides: category, reasoning

        Uses fuzzy matching since classifier often paraphrases descriptions.
        """
        issues: list[ReviewedIssue] = []
        used_classifications: set[str] = set()

        for issue in reviewer_issues:
            description = issue.get("description", "")
            context = issue.get("context", "")  # Actual transcript quote
            severity = int(issue.get("severity", 3))

            # Find matching classification (exact match first, then fuzzy)
            classification = classifications.get(description)
            matched_key = description if classification else None

            if not classification:
                # Try fuzzy matching
                matched_key, classification = self._find_best_classification_match(
                    description, classifications, used_classifications
                )

            if matched_key:
                used_classifications.add(matched_key)

            category_str = (classification or {}).get("category", "ux_issue")
            try:
                category = IssueCategory(category_str)
            except ValueError:
                category = IssueCategory.ux_issue

            issues.append(ReviewedIssue(
                category=category,
                description=description,
                severity=severity,
                context=context,
            ))

        # Also add any classified issues that weren't matched
        # (in case classifier identified additional issues)
        for desc, ci in classifications.items():
            if desc not in used_classifications:
                category_str = ci.get("category", "ux_issue")
                try:
                    category = IssueCategory(category_str)
                except ValueError:
                    category = IssueCategory.ux_issue

                issues.append(ReviewedIssue(
                    category=category,
                    description=ci.get("original_description", desc),
                    severity=3,  # Default since reviewer didn't see this
                    context=ci.get("reasoning", ""),
                ))

        return issues

    def _find_best_classification_match(
        self,
        description: str,
        classifications: dict[str, dict],
        used: set[str],
    ) -> tuple[str | None, dict | None]:
        """Find best matching classification using word overlap similarity."""
        if not description or not classifications:
            return None, None

        desc_words = set(description.lower().split())
        best_key = None
        best_score = 0.0
        best_match = None

        for key, classification in classifications.items():
            if key in used:
                continue

            key_words = set(key.lower().split())
            if not key_words:
                continue

            # Jaccard similarity: intersection / union
            intersection = len(desc_words & key_words)
            union = len(desc_words | key_words)
            score = intersection / union if union > 0 else 0.0

            # Require at least 30% word overlap to consider a match
            if score > best_score and score >= 0.3:
                best_score = score
                best_key = key
                best_match = classification

        return best_key, best_match

    def _extract_json_from_text(self, text: str) -> dict | None:
        """Extract JSON using proper decoder that handles nested structures."""
        decoder = json.JSONDecoder()
        # Find all potential JSON start positions
        for match in re.finditer(r'\{', text):
            try:
                obj, _ = decoder.raw_decode(text, match.start())
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
        return None
