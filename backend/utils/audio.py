"""
Vidgo.AI - Audio Mixing Module
Mixes narration with background music using FFmpeg.
"""

import os
import subprocess
import logging

logger = logging.getLogger(__name__)


def mix_audio(
    narration_path: str,
    music_path: str,
    output_path: str,
    music_volume: float = 0.15,
) -> str:
    """
    Mix narration audio with background music.
    
    The music is looped to match narration length and faded out at the end.
    Music volume is reduced to sit underneath the voice.
    
    Args:
        narration_path: Path to narration MP3
        music_path: Path to background music MP3
        output_path: Output path for mixed audio
        music_volume: Volume level for music (0.0 - 1.0), default 0.15
    
    Returns:
        Path to the mixed audio file
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if not os.path.exists(narration_path):
        raise FileNotFoundError(f"Narration file not found: {narration_path}")
    if not os.path.exists(music_path):
        logger.warning(f"Music file not found: {music_path}, using narration only")
        return narration_path

    # Clamp volume
    music_volume = max(0.0, min(1.0, music_volume))

    # Get narration duration for fade-out timing
    narration_duration = _get_duration(narration_path)
    fade_start = max(0, narration_duration - 2.0)  # 2-second fade out

    # FFmpeg command:
    # - Input 0: narration
    # - Input 1: music (streamed/looped)
    # - Filter: loop music, reduce volume, fade out, mix with narration
    filter_complex = (
        f"[1:a]aloop=loop=-1:size=2e+09,atrim=0:{narration_duration},"
        f"volume={music_volume},"
        f"afade=t=out:st={fade_start:.1f}:d=2.0[music];"
        f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", narration_path,
        "-i", music_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        output_path,
    ]

    logger.info(f"Mixing audio: narration={narration_duration:.1f}s, music_vol={music_volume}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            logger.error(f"Audio mix error: {result.stderr}")
            # Fallback: return narration without music
            logger.warning("Falling back to narration-only audio")
            return narration_path

        logger.info(f"Mixed audio saved: {output_path} ({os.path.getsize(output_path)} bytes)")
        return output_path

    except subprocess.TimeoutExpired:
        logger.error("Audio mixing timed out")
        return narration_path
    except FileNotFoundError:
        logger.error("FFmpeg not found for audio mixing")
        return narration_path


def _get_duration(audio_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        return 10.0  # Default fallback
