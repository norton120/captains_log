#!/usr/bin/env python3
"""
Generate sample audio files for testing.
Creates mock WAV files with different characteristics for testing upload scenarios.
"""
import wave
import struct
import os
from pathlib import Path

# Audio parameters
SAMPLE_RATE = 44100
CHANNELS = 1  # Mono
SAMPLE_WIDTH = 2  # 16-bit

def create_sine_wave(frequency, duration_seconds, amplitude=0.5):
    """Generate sine wave audio data."""
    import math
    num_samples = int(SAMPLE_RATE * duration_seconds)
    audio_data = []
    
    for i in range(num_samples):
        time = i / SAMPLE_RATE
        sample = amplitude * math.sin(2 * math.pi * frequency * time)
        # Convert to 16-bit integer
        sample_int = int(sample * 32767)
        audio_data.append(sample_int)
    
    return audio_data

def create_test_audio_file(filename, duration_seconds=5, frequency=440):
    """Create a test WAV file with sine wave."""
    fixtures_dir = Path(__file__).parent
    filepath = fixtures_dir / filename
    
    # Generate audio data
    audio_data = create_sine_wave(frequency, duration_seconds)
    
    # Write WAV file
    with wave.open(str(filepath), 'wb') as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(SAMPLE_RATE)
        
        # Pack audio data as bytes
        for sample in audio_data:
            wav_file.writeframes(struct.pack('<h', sample))
    
    return filepath

def main():
    """Create all test audio fixtures."""
    fixtures_dir = Path(__file__).parent
    fixtures_dir.mkdir(exist_ok=True)
    
    print("Creating test audio fixtures...")
    
    # Valid test files
    create_test_audio_file("test_audio_short.wav", duration_seconds=2, frequency=440)  # A4 note
    create_test_audio_file("test_audio_medium.wav", duration_seconds=10, frequency=523)  # C5 note  
    create_test_audio_file("test_audio_long.wav", duration_seconds=30, frequency=330)  # E4 note
    
    # Edge case files
    create_test_audio_file("test_audio_tiny.wav", duration_seconds=0.1, frequency=880)  # Very short
    create_test_audio_file("test_audio_large.wav", duration_seconds=60, frequency=262)  # Large file
    
    # Create an empty file for error testing
    empty_file = fixtures_dir / "empty_file.wav"
    empty_file.touch()
    
    # Create a corrupted WAV file (invalid header)
    corrupted_file = fixtures_dir / "corrupted_audio.wav"
    with open(corrupted_file, 'wb') as f:
        f.write(b"This is not a valid WAV file content")
    
    print(f"Created test audio fixtures in {fixtures_dir}")
    
    # Print file sizes for reference
    for wav_file in fixtures_dir.glob("*.wav"):
        size_kb = wav_file.stat().st_size / 1024
        print(f"  {wav_file.name}: {size_kb:.1f} KB")

if __name__ == "__main__":
    main()