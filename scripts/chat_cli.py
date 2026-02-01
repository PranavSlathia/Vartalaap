#!/usr/bin/env python3
"""Interactive CLI to test the voice bot conversation flow.

This simulates phone calls without needing Plivo - just type messages
and see how the bot responds with extraction and reservation flow.
"""

import asyncio

from src.core.conversation_state import ConversationPhase
from src.core.session import CallSession


def print_state(session: CallSession) -> None:
    """Print current conversation state."""
    state = session.state
    phase = state.phase.name

    print(f"\n  📊 State: {phase}")

    if state.pending_reservation:
        res = state.pending_reservation
        print(f"  📝 Reservation: party={res.party_size}, date={res.reservation_date}, "
              f"time={res.reservation_time}, name={res.customer_name}")
        if res.missing_fields:
            print(f"  ❓ Missing: {', '.join(res.missing_fields)}")


async def main():
    print("=" * 60)
    print("🍽️  Himalayan Kitchen Voice Bot - Test CLI")
    print("=" * 60)
    print("\nType messages as if you're calling the restaurant.")
    print("Commands: /state (show state), /reset (new call), /quit (exit)\n")

    session = CallSession(business_id="himalayan_kitchen")

    # Initial greeting
    print("🤖 Bot: Namaste! Himalayan Kitchen mein aapka swagat hai.")
    print("       Main aapki kya madad kar sakti hoon?\n")

    try:
        while True:
            # Get user input
            user_input = input("👤 You: ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.lower() == "/quit":
                print("\n👋 Goodbye!")
                break

            if user_input.lower() == "/state":
                print_state(session)
                continue

            if user_input.lower() == "/reset":
                await session.close()
                session = CallSession(business_id="himalayan_kitchen")
                print("\n🔄 New call started!")
                print("🤖 Bot: Namaste! Himalayan Kitchen mein aapka swagat hai.\n")
                continue

            # Process through the bot
            try:
                response, metadata = await session.process_user_input(user_input)

                # Show response
                print(f"\n🤖 Bot: {response}")

                # Show latency
                if metadata.first_token_ms:
                    print(f"   ⏱️  {metadata.first_token_ms:.0f}ms")

                # Show state changes
                print_state(session)
                print()

            except Exception as e:
                print(f"\n❌ Error: {e}\n")

    finally:
        await session.close()


if __name__ == "__main__":
    print("\nStarting... (this may take a moment to load)\n")
    asyncio.run(main())
