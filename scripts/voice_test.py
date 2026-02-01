#!/usr/bin/env python3
"""Voice test script - talk to the bot using your microphone.

Uses:
- Deepgram for speech-to-text
- Groq LLM for conversation
- gTTS for voice responses (Google TTS)
"""

import asyncio
import os
import sys
import tempfile

import numpy as np
import sounddevice as sd
from gtts import gTTS
from pydub import AudioSegment

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.session import CallSession
from src.services.stt.deepgram import DeepgramService


# Audio settings
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.1  # 100ms chunks
SILENCE_THRESHOLD = 300  # Lower threshold for better detection
SILENCE_DURATION = 1.2  # Seconds of silence before processing

# TTS playback rate
TTS_SAMPLE_RATE = 24000


def get_input_device():
    """Find a working input device."""
    devices = sd.query_devices()
    # Try to find default input
    try:
        default = sd.query_devices(kind='input')
        if default:
            return default['index']
    except Exception:
        pass

    # Find any input device
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            return i
    return None


def calculate_rms(audio_data: np.ndarray) -> float:
    """Calculate RMS of audio data."""
    return float(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)))


def speak_text_gtts(text: str, lang: str = 'hi') -> None:
    """Convert text to speech using gTTS and play it."""
    try:
        # Generate speech with gTTS
        tts = gTTS(text=text, lang=lang, slow=False)

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
            temp_path = f.name
            tts.save(temp_path)

        # Load and convert to playable format
        audio = AudioSegment.from_mp3(temp_path)
        audio = audio.set_frame_rate(TTS_SAMPLE_RATE).set_channels(1)

        # Convert to numpy array
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
        samples = samples / 32768.0  # Normalize

        # Play
        sd.play(samples, samplerate=TTS_SAMPLE_RATE)
        sd.wait()

        # Cleanup
        os.unlink(temp_path)

    except Exception as e:
        print(f"    (TTS error: {e})")


async def record_until_silence(device_id: int) -> bytes:
    """Record audio until user stops speaking."""
    print("    [Listening... speak now]")

    chunk_size = int(SAMPLE_RATE * CHUNK_DURATION)
    audio_buffer = []
    silence_chunks = 0
    max_silence_chunks = int(SILENCE_DURATION / CHUNK_DURATION)
    speaking_started = False

    def audio_callback(indata, frames, time_info, status):
        nonlocal silence_chunks, speaking_started

        # Convert to int16
        audio = (indata[:, 0] * 32767).astype(np.int16)
        audio_buffer.append(audio.tobytes())

        rms = calculate_rms(indata[:, 0] * 32767)

        if rms > SILENCE_THRESHOLD:
            speaking_started = True
            silence_chunks = 0
        elif speaking_started:
            silence_chunks += 1

    try:
        with sd.InputStream(
            device=device_id,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=np.float32,
            blocksize=chunk_size,
            callback=audio_callback,
        ):
            timeout_chunks = 0
            while True:
                await asyncio.sleep(CHUNK_DURATION)
                timeout_chunks += 1

                # Stop if we've heard speech and then silence
                if speaking_started and silence_chunks >= max_silence_chunks:
                    break

                # Timeout after 8 seconds of no speech
                if not speaking_started and timeout_chunks > 80:
                    print("    [No speech detected]")
                    return b""

        print("    [Processing...]")
        return b"".join(audio_buffer)

    except Exception as e:
        print(f"    [Microphone error: {e}]")
        return b""


async def transcribe_audio(stt: DeepgramService, audio_data: bytes) -> str:
    """Transcribe audio using Deepgram."""
    if not audio_data:
        return ""

    try:
        transcript, metadata = await stt.transcribe_file(
            audio_data,
            sample_rate=SAMPLE_RATE,
            encoding="linear16",
            language="hi",
        )

        if metadata.first_word_ms:
            print(f"    [STT: {metadata.first_word_ms:.0f}ms]")

        return transcript
    except Exception as e:
        print(f"    [STT error: {e}]")
        return ""


async def main():
    print("=" * 60)
    print("  Vartalaap Voice Bot - Full Voice Test")
    print("=" * 60)
    print("\n  Pipeline: Mic → Deepgram STT → Groq LLM → gTTS")
    print("  Speak in Hindi or English. Press Ctrl+C to exit.\n")

    # Find microphone
    device_id = get_input_device()
    if device_id is None:
        print("ERROR: No microphone found!")
        print("Make sure your microphone is connected and has permission.")
        return

    device_info = sd.query_devices(device_id)
    print(f"  Microphone: {device_info['name']}")

    # Initialize services
    stt = DeepgramService()
    session = CallSession(business_id="himalayan_kitchen")

    # Check STT
    print("  Checking Deepgram... ", end="", flush=True)
    if not await stt.health_check():
        print("FAILED")
        print("ERROR: Deepgram not available. Check DEEPGRAM_API_KEY in .env")
        return
    print("OK")

    print("  TTS: Google TTS (gTTS)")
    print()
    print("-" * 60)

    # Initial greeting
    greeting = "Namaste! Himalayan Kitchen mein aapka swagat hai. Main aapki kya madad kar sakti hoon?"
    print(f"\nBot: {greeting}")
    speak_text_gtts(greeting, lang='hi')
    print()

    try:
        while True:
            # Record
            audio_data = await record_until_silence(device_id)
            if not audio_data:
                continue

            # Transcribe
            transcript = await transcribe_audio(stt, audio_data)
            if not transcript:
                print("    [Could not understand, try again]")
                continue

            print(f"You: {transcript}")

            # Get response from LLM
            response, metadata = await session.process_user_input(transcript)

            print(f"Bot: {response}")
            if metadata.first_token_ms:
                print(f"    [LLM: {metadata.first_token_ms:.0f}ms]")

            # Speak response using gTTS
            speak_text_gtts(response, lang='hi')
            print()

    except KeyboardInterrupt:
        print("\n\nGoodbye!")
    finally:
        await stt.close()
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
