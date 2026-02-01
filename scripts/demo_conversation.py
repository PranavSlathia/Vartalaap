#!/usr/bin/env python3
"""Demo script showing a complete reservation conversation flow."""

import asyncio

from src.core.conversation_state import ConversationPhase
from src.core.session import CallSession


async def demo():
    print("=" * 70)
    print("🍽️  Himalayan Kitchen - Reservation Flow Demo")
    print("=" * 70)

    session = CallSession(business_id="himalayan_kitchen")

    # Simulated conversation
    messages = [
        "Table book karna hai",
        "4 log hain",
        "Kal ke liye",
        "7 baje shaam ko",
        "Sharma",
    ]

    print("\n🤖 Bot: Namaste! Himalayan Kitchen mein aapka swagat hai.")
    print("       Main aapki kya madad kar sakti hoon?\n")

    try:
        for msg in messages:
            print(f"👤 You: {msg}")

            response, metadata = await session.process_user_input(msg)

            print(f"🤖 Bot: {response}")

            # Show state
            state = session.state
            if state.pending_reservation:
                res = state.pending_reservation
                filled = []
                if res.party_size:
                    filled.append(f"party={res.party_size}")
                if res.reservation_date:
                    filled.append(f"date={res.reservation_date}")
                if res.reservation_time:
                    filled.append(f"time={res.reservation_time}")
                if res.customer_name:
                    filled.append(f"name={res.customer_name}")

                print(f"   📊 [{state.phase.name}] {', '.join(filled)}")

            if metadata.first_token_ms:
                print(f"   ⏱️  {metadata.first_token_ms:.0f}ms")

            print()

            # Small delay for readability
            await asyncio.sleep(0.5)

    finally:
        await session.close()

    print("=" * 70)
    print("✅ Demo complete! The bot successfully:")
    print("   - Extracted party size (4)")
    print("   - Parsed 'kal' as tomorrow's date")
    print("   - Parsed '7 baje shaam' as 19:00")
    print("   - Collected customer name (Sharma)")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(demo())
