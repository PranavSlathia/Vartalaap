#!/usr/bin/env python3
"""Quick TTS test - test voice quality with Google TTS (gTTS).

gTTS is reliable and free. It has decent Hindi voice quality.
This is useful for local testing when Edge TTS is blocked.
"""

import asyncio
import io
import os
import sys
import tempfile

import numpy as np
import sounddevice as sd
from gtts import gTTS
from pydub import AudioSegment

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# gTTS outputs MP3, we'll convert to 24kHz for playback
PLAYBACK_SAMPLE_RATE = 24000

TEST_PHRASES = [
    # Hindi
    ("Namaste! Himalayan Kitchen mein aapka swagat hai.", "hi"),
    ("Aapki reservation 4 logon ke liye kal shaam 7 baje confirm ho gayi hai.", "hi"),
    ("Kya aap vegetarian khana pasand karenge?", "hi"),
    # English
    ("Welcome to Himalayan Kitchen. How may I help you today?", "en"),
    ("Your table for 4 people is confirmed for tomorrow at 7 PM.", "en"),
    # Hinglish (use Hindi voice)
    ("Aapka booking confirm ho gaya hai. Thank you for choosing Himalayan Kitchen!", "hi"),
]


def synthesize_gtts(text: str, lang: str = "hi") -> np.ndarray:
    """Synthesize text using gTTS and return numpy audio array."""
    # Generate speech
    tts = gTTS(text=text, lang=lang, slow=False)

    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
        temp_path = f.name
        tts.save(temp_path)

    try:
        # Load and convert with pydub
        audio = AudioSegment.from_mp3(temp_path)
        audio = audio.set_frame_rate(PLAYBACK_SAMPLE_RATE).set_channels(1)

        # Convert to numpy array
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
        samples = samples / 32768.0  # Normalize to [-1, 1]

        return samples
    finally:
        os.unlink(temp_path)


def main():
    print("=" * 60)
    print("  Google TTS Voice Quality Test")
    print("=" * 60)
    print()
    print("  Using: gTTS (Google Text-to-Speech)")
    print("  Languages: Hindi (hi), English (en)")
    print()
    print("-" * 60)
    print("  Press Enter to play each phrase, or 'q' to quit")
    print("-" * 60)

    for i, (phrase, lang) in enumerate(TEST_PHRASES, 1):
        lang_label = "Hindi" if lang == "hi" else "English"
        print(f"\n[{i}/{len(TEST_PHRASES)}] ({lang_label}) {phrase[:50]}...")

        user_input = input("  Press Enter to play (q to quit): ").strip().lower()
        if user_input == 'q':
            break

        try:
            print("  Synthesizing...", end="", flush=True)
            audio = synthesize_gtts(phrase, lang)
            print(f" done ({len(audio)/PLAYBACK_SAMPLE_RATE:.1f}s)")

            print("  Playing...")
            sd.play(audio, samplerate=PLAYBACK_SAMPLE_RATE)
            sd.wait()

        except Exception as e:
            print(f"\n  Error: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("  Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
