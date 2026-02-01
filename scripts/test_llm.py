#!/usr/bin/env python3
"""Quick test script to verify LLM connection and extraction."""

import asyncio

from src.services.llm.groq import GroqService
from src.services.llm.extractor import ReservationExtractor


async def test_groq_connection():
    """Test basic Groq API connection."""
    print("Testing Groq API connection...")

    service = GroqService()

    try:
        healthy = await service.health_check()
        if healthy:
            print("✓ Groq API connection successful!")
        else:
            print("✗ Groq API health check failed")
            return False
    except Exception as e:
        print(f"✗ Groq API error: {e}")
        return False
    finally:
        await service.close()

    return True


async def test_extraction():
    """Test extraction from a sample conversation."""
    print("\nTesting reservation extraction...")

    extractor = ReservationExtractor()

    try:
        # Test Hindi reservation request
        result = await extractor.extract(
            user_message="Kal shaam 7 baje 4 logon ke liye table book karna hai",
            assistant_response="Zaroor! Kal shaam 7 baje, 4 logon ke liye. Booking ke liye aapka naam?",
        )

        if result:
            print(f"✓ Extraction successful!")
            print(f"  Intent: {result.intent.name}")
            print(f"  Party size: {result.party_size}")
            print(f"  Date: {result.reservation_date}")
            print(f"  Time: {result.reservation_time}")
            print(f"  Missing fields: {result.missing_fields}")
        else:
            print("✗ Extraction returned None")
            return False

    except Exception as e:
        print(f"✗ Extraction error: {e}")
        return False
    finally:
        await extractor.close()

    return True


async def test_conversation():
    """Test a full conversation turn."""
    print("\nTesting conversation response...")

    from src.core.session import CallSession

    session = CallSession(business_id="himalayan_kitchen")

    try:
        response, metadata = await session.process_user_input(
            "Hello, I want to book a table"
        )

        print(f"✓ Got response: {response[:100]}...")
        print(f"  Model: {metadata.model}")
        print(f"  First token: {metadata.first_token_ms:.0f}ms" if metadata.first_token_ms else "")

    except Exception as e:
        print(f"✗ Conversation error: {e}")
        return False
    finally:
        await session.close()

    return True


async def main():
    print("=" * 60)
    print("Vartalaap Voice Bot - LLM Test")
    print("=" * 60)

    # Test 1: Basic connection
    if not await test_groq_connection():
        return

    # Test 2: Extraction
    if not await test_extraction():
        return

    # Test 3: Full conversation
    if not await test_conversation():
        return

    print("\n" + "=" * 60)
    print("All tests passed! LLM is working correctly.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
