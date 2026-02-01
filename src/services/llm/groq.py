"""Groq LLM service implementation with streaming support."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import groq
from groq import AsyncGroq

from src.config import Settings, get_settings
from src.logging_config import get_logger
from src.services.llm.exceptions import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMServiceError,
)
from src.services.llm.protocol import (
    ConversationContext,
    Message,
    StreamMetadata,
)
from src.services.llm.rate_limiter import TokenBucketRateLimiter
from src.services.llm.token_counter import estimate_llama_tokens

if TYPE_CHECKING:
    pass

logger: Any = get_logger(__name__)

# Groq free tier limits
GROQ_FREE_TIER_TPM = 6000  # Tokens per minute
GROQ_FREE_TIER_RPM = 30  # Requests per minute

# RAG injection limits - prevent prompt explosion
MAX_KNOWLEDGE_TOKENS = 500  # ~375 words, fits within P50 latency budget


class GroqService:
    """Groq LLM service with async streaming and rate limiting."""

    def __init__(
        self,
        settings: Settings | None = None,
        model: str = "llama-3.3-70b-versatile",
    ) -> None:
        self._settings = settings or get_settings()
        self._model = model
        self._client: AsyncGroq | None = None
        self._rate_limiter = TokenBucketRateLimiter(
            tokens_per_minute=GROQ_FREE_TIER_TPM,
            requests_per_minute=GROQ_FREE_TIER_RPM,
        )

    @property
    def client(self) -> AsyncGroq:
        """Lazy initialization of AsyncGroq client."""
        if self._client is None:
            self._client = AsyncGroq(
                api_key=self._settings.groq_api_key.get_secret_value(),
                timeout=30.0,
                max_retries=2,
            )
        return self._client

    async def stream_chat(
        self,
        messages: list[Message],
        context: ConversationContext,
        *,
        max_tokens: int = 256,
        temperature: float = 0.7,
    ) -> tuple[AsyncGenerator[str, None], StreamMetadata]:
        """Stream chat completion with context injection.

        Args:
            messages: Conversation history
            context: Business context for system prompt
            max_tokens: Maximum response tokens (keep low for voice)
            temperature: Response creativity (0.7 good for conversation)

        Returns:
            Tuple of (async content generator, metadata object)

        Raises:
            LLMRateLimitError: When rate limit exceeded
            LLMConnectionError: When API unreachable
            LLMAuthenticationError: When API key invalid
            LLMServiceError: For other API errors
        """
        # Build messages with system prompt
        system_prompt = self._build_system_prompt(context)
        api_messages = self._format_messages(system_prompt, messages)

        # Estimate tokens for rate limiting
        estimated_input_tokens = sum(self.estimate_tokens(m["content"]) for m in api_messages)
        estimated_total = estimated_input_tokens + max_tokens

        # Check rate limit before making request
        await self._rate_limiter.acquire(estimated_total)

        # Create metadata container (populated during streaming)
        metadata = StreamMetadata(model=self._model)

        # Create and return the generator
        generator = self._stream_with_metadata(api_messages, max_tokens, temperature, metadata)

        return generator, metadata

    async def extract_json(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> dict:
        """Extract structured JSON from a conversation.

        Uses Groq's JSON response format for reliable structured output.

        Args:
            messages: List of message dicts with role/content
            max_tokens: Maximum response tokens
            temperature: Low temperature (0.0) for deterministic extraction

        Returns:
            Parsed JSON dict from LLM response

        Raises:
            LLMRateLimitError: When rate limit exceeded
            LLMConnectionError: When API unreachable
            LLMServiceError: For other API errors or JSON parse failure
        """
        # Estimate tokens for rate limiting
        estimated_input_tokens = sum(self.estimate_tokens(m["content"]) for m in messages)
        estimated_total = estimated_input_tokens + max_tokens

        # Check rate limit
        await self._rate_limiter.acquire(estimated_total)

        try:
            response = await self.client.chat.completions.create(  # type: ignore[call-overload]
                messages=messages,
                model=self._model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                raise LLMServiceError("Empty response from Groq JSON extraction")

            # Update rate limiter with actual usage
            if response.usage:
                self._rate_limiter.record_usage(response.usage.total_tokens)

            result: dict[str, Any] = json.loads(content)
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Groq response: {e}")
            raise LLMServiceError(f"Invalid JSON in response: {e}") from e

        except groq.RateLimitError as e:
            logger.warning(f"Groq rate limit hit during extraction: {e}")
            raise LLMRateLimitError(
                "Rate limit exceeded",
                retry_after=self._extract_retry_after(e),
            ) from e

        except groq.APIConnectionError as e:
            logger.error(f"Groq connection error during extraction: {e.__cause__}")
            raise LLMConnectionError("Failed to connect to Groq API") from e

        except groq.AuthenticationError as e:
            logger.error("Groq authentication failed during extraction")
            raise LLMAuthenticationError("Invalid Groq API key") from e

        except groq.APIStatusError as e:
            logger.error(f"Groq API error during extraction: {e.status_code} - {e.message}")
            raise LLMServiceError(f"Groq API error: {e.status_code}") from e

    async def _stream_with_metadata(
        self,
        api_messages: list[dict],
        max_tokens: int,
        temperature: float,
        metadata: StreamMetadata,
    ) -> AsyncGenerator[str, None]:
        """Internal generator that populates metadata during streaming."""
        start_time = time.perf_counter()
        first_token_received = False

        try:
            stream = await self.client.chat.completions.create(
                messages=api_messages,  # type: ignore[arg-type]
                model=self._model,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            async for chunk in stream:  # type: ignore[union-attr]
                pass  # chunk is ChatCompletionChunk

                # Track first token latency
                if not first_token_received:
                    metadata.first_token_ms = (time.perf_counter() - start_time) * 1000
                    first_token_received = True
                    logger.debug(f"First token latency: {metadata.first_token_ms:.1f}ms")

                # Extract content
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

                # Capture finish reason
                if chunk.choices and chunk.choices[0].finish_reason:
                    metadata.finish_reason = chunk.choices[0].finish_reason

                # Groq provides usage in x_groq extension
                if (
                    hasattr(chunk, "x_groq")
                    and chunk.x_groq
                    and hasattr(chunk.x_groq, "usage")
                    and chunk.x_groq.usage
                ):
                    usage = chunk.x_groq.usage
                    metadata.prompt_tokens = usage.prompt_tokens
                    metadata.completion_tokens = usage.completion_tokens
                    metadata.total_tokens = usage.total_tokens

                    # Update rate limiter with actual usage
                    self._rate_limiter.record_usage(usage.total_tokens)

        except groq.RateLimitError as e:
            logger.warning(f"Groq rate limit hit: {e}")
            raise LLMRateLimitError(
                "Rate limit exceeded",
                retry_after=self._extract_retry_after(e),
            ) from e

        except groq.APIConnectionError as e:
            logger.error(f"Groq connection error: {e.__cause__}")
            raise LLMConnectionError("Failed to connect to Groq API") from e

        except groq.AuthenticationError as e:
            logger.error("Groq authentication failed")
            raise LLMAuthenticationError("Invalid Groq API key") from e

        except groq.APIStatusError as e:
            logger.error(f"Groq API error: {e.status_code} - {e.message}")
            raise LLMServiceError(f"Groq API error: {e.status_code}") from e

    def _build_system_prompt(self, context: ConversationContext) -> str:
        """Build system prompt with injected context."""
        # Format operating hours
        hours_lines = []
        for day, hours in context.operating_hours.items():
            hours_lines.append(f"  - {day.capitalize()}: {hours}")
        hours_text = "\n".join(hours_lines)

        # Format current datetime
        dt_text = context.current_datetime.strftime("%A, %B %d, %Y at %I:%M %p")

        prompt = f"""You are a friendly voice assistant for {context.business_name}.

## Current Information
- Current date/time: {dt_text} ({context.timezone})
- Business type: {context.business_type}

## Operating Hours
{hours_text}

## Reservation Rules
- Minimum party size: {context.reservation_rules.get('min_party_size', 1)}
- Maximum party size (phone): {context.reservation_rules.get('max_phone_party_size', 10)} people
- Total capacity: {context.reservation_rules.get('total_seats', 40)} seats
"""

        if context.current_capacity is not None:
            prompt += f"- Current available seats: {context.current_capacity}\n"

        if context.menu_summary:
            prompt += f"\n## Menu Highlights\n{context.menu_summary}\n"

        if context.caller_history:
            prompt += f"\n## Caller History\n{context.caller_history}\n"

        # Inject retrieved knowledge from RAG with token budget
        if context.retrieved_knowledge and context.retrieved_knowledge.has_results:
            knowledge_section = context.retrieved_knowledge.to_prompt_section()
            knowledge_tokens = self.estimate_tokens(knowledge_section)

            if knowledge_tokens > MAX_KNOWLEDGE_TOKENS:
                # Truncate by reducing items until within budget
                logger.warning(
                    f"Knowledge section exceeds budget: {knowledge_tokens} > {MAX_KNOWLEDGE_TOKENS} tokens"
                )
                # Take fewer items - rebuild with reduced set
                items = context.retrieved_knowledge.items
                truncated_items = []
                running_tokens = 50  # Reserve for section headers

                for item in items:
                    item_text = item.to_prompt_text()
                    item_tokens = self.estimate_tokens(item_text)
                    if running_tokens + item_tokens <= MAX_KNOWLEDGE_TOKENS:
                        truncated_items.append(item)
                        running_tokens += item_tokens
                    else:
                        break

                if truncated_items:
                    # Rebuild section with truncated items
                    from src.services.knowledge.protocol import KnowledgeResult

                    truncated_result = KnowledgeResult(
                        query=context.retrieved_knowledge.query,
                        items=truncated_items,
                        retrieval_time_ms=context.retrieved_knowledge.retrieval_time_ms,
                    )
                    knowledge_section = truncated_result.to_prompt_section()
                    logger.info(
                        f"Truncated knowledge from {len(items)} to {len(truncated_items)} items"
                    )
                else:
                    knowledge_section = ""  # Skip if even first item exceeds budget

            if knowledge_section:
                prompt += f"\n{knowledge_section}\n"

        # Use custom prompt template if available, otherwise default guidelines
        if context.prompt_template:
            prompt += f"\n## Guidelines\n{context.prompt_template}\n"
        else:
            prompt += """
## Guidelines
- Be concise - responses should be 1-2 sentences for voice
- Use natural, conversational language
- Adapt to Hindi, English, or Hinglish based on caller's language
- For Hindi speakers, use polite forms ("ji", "aap")
- Always confirm reservation details before finalizing (date, time, party size, name)
- Do not accept delivery orders - politely redirect to Zomato/Swiggy
- For large parties (>10), redirect to WhatsApp
- If unsure about availability, offer to check and call back via WhatsApp
"""

        # Add few-shot examples if available
        if context.few_shot_examples:
            prompt += "\n## Example Conversations\n"
            for i, example in enumerate(context.few_shot_examples, 1):
                prompt += f"Example {i}:\n"
                prompt += f"  User: {example['user']}\n"
                prompt += f"  Assistant: {example['assistant']}\n\n"

        return prompt

    def _format_messages(self, system_prompt: str, messages: list[Message]) -> list[dict]:
        """Format messages for Groq API."""
        api_messages = [{"role": "system", "content": system_prompt}]

        for msg in messages:
            api_messages.append({
                "role": msg.role.value,
                "content": msg.content,
            })

        return api_messages

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for rate limiting."""
        return estimate_llama_tokens(text)

    def _extract_retry_after(self, error: groq.RateLimitError) -> float:
        """Extract retry-after from rate limit error."""
        if hasattr(error, "response") and error.response:
            retry_after = error.response.headers.get("retry-after")
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass
        return 60.0  # Default to 60 seconds

    async def health_check(self) -> bool:
        """Check if Groq API is reachable."""
        try:
            response = await self.client.chat.completions.create(
                messages=[{"role": "user", "content": "hi"}],
                model=self._model,
                max_tokens=1,
            )
            return bool(response.choices)
        except Exception as e:
            logger.warning(f"Groq health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the client connection."""
        if self._client:
            await self._client.close()
            self._client = None
