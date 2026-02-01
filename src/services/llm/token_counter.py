"""Token estimation for Llama models.

Groq doesn't provide a tokenizer, so we estimate based on
typical Llama tokenization patterns. This is for rate limiting
purposes - actual usage comes from API response.
"""


def estimate_llama_tokens(text: str) -> int:
    """Estimate token count for Llama models.

    Uses a simple heuristic: ~4 characters per token for English,
    ~2 characters per token for Hindi/Devanagari script.

    Args:
        text: Input text to estimate

    Returns:
        Estimated token count
    """
    if not text:
        return 0

    # Count Devanagari characters (Hindi script)
    devanagari_count = sum(1 for char in text if "\u0900" <= char <= "\u097F")

    # Estimate based on script mix
    non_devanagari = len(text) - devanagari_count

    # Devanagari: ~2 chars/token, Latin: ~4 chars/token
    estimated = (devanagari_count / 2) + (non_devanagari / 4)

    # Add 10% buffer for safety
    return int(estimated * 1.1) + 1
