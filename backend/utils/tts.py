"""
Vidgo.AI - Text-to-Speech Module
Supports ElevenLabs (premium) and gTTS (free fallback) with multiple accents.
"""

import os
import requests
import logging

logger = logging.getLogger(__name__)

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"

# ── ElevenLabs Premium Voices ──────────────────────────────
ELEVENLABS_VOICES = {
    "rachel": "21m00Tcm4TlvDq8ikWAM",
    "adam": "pNInz6obpgDQGcFmaJgB",
    "antoni": "ErXwobaYiN019PkySvjV",
    "bella": "EXAVITQu4vr4xnSDxMaL",
    "domi": "AZnzlk1XvdvUeBnXmlld",
    "elli": "MF3mGyEYCl7XYWbV9V6O",
    "josh": "TxGEqnHWrfWFTfGW9XjX",
    "sam": "yoZ06aMxZJJ28mfd3POQ",
}

# Keep backward compat alias
VOICES = ELEVENLABS_VOICES

# ── Free gTTS Voices (accent via TLD) ─────────────────────
GTTS_VOICES = [
    {"id": "gtts_us", "name": "English (US)", "lang": "en", "tld": "com"},
    {"id": "gtts_uk", "name": "English (British)", "lang": "en", "tld": "co.uk"},
    {"id": "gtts_au", "name": "English (Australian)", "lang": "en", "tld": "com.au"},
    {"id": "gtts_in", "name": "English (Indian)", "lang": "en", "tld": "co.in"},
    {"id": "gtts_za", "name": "English (South African)", "lang": "en", "tld": "co.za"},
    {"id": "gtts_ie", "name": "English (Irish)", "lang": "en", "tld": "ie"},
    {"id": "gtts_ca", "name": "English (Canadian)", "lang": "en", "tld": "ca"},
    {"id": "gtts_es", "name": "Spanish", "lang": "es", "tld": "com"},
    {"id": "gtts_fr", "name": "French", "lang": "fr", "tld": "com"},
    {"id": "gtts_pt", "name": "Portuguese", "lang": "pt", "tld": "com"},
    {"id": "gtts_de", "name": "German", "lang": "de", "tld": "com"},
    {"id": "gtts_hi", "name": "Hindi", "lang": "hi", "tld": "com"},
]

DEFAULT_VOICE = "rachel"


def get_gtts_voice(voice_id: str) -> dict | None:
    """Lookup a gTTS voice by its ID."""
    for v in GTTS_VOICES:
        if v["id"] == voice_id:
            return v
    return None


def get_available_voices(api_key: str) -> dict:
    """
    Return categorized voice list.
    Returns: { "free": [...], "premium": [...] }
    """
    free_voices = [{"voice_id": v["id"], "name": v["name"]} for v in GTTS_VOICES]

    premium_voices = []
    if api_key and api_key.strip():
        try:
            headers = {"xi-api-key": api_key}
            response = requests.get(f"{ELEVENLABS_API_URL}/voices", headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            premium_voices = [{"voice_id": v["voice_id"], "name": v["name"]} for v in data.get("voices", [])]
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch ElevenLabs voices: {e}")
            premium_voices = [{"voice_id": vid, "name": name.capitalize()} for name, vid in ELEVENLABS_VOICES.items()]
    else:
        premium_voices = [{"voice_id": vid, "name": name.capitalize()} for name, vid in ELEVENLABS_VOICES.items()]

    return {"free": free_voices, "premium": premium_voices}


def synthesize_speech(
    text: str,
    output_path: str,
    api_key: str = None,
    voice_id: str = None,
    model_id: str = "eleven_monolingual_v1",
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    speech_speed: str = "normal",
) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Check if a gTTS voice was selected
    gtts_voice = get_gtts_voice(voice_id) if voice_id else None

    # If voice is a gTTS voice, go straight to gTTS
    if gtts_voice:
        logger.info(f"Using gTTS voice: {gtts_voice['name']}")
        return _gtts_tts(
            text=text,
            output_path=output_path,
            lang=gtts_voice["lang"],
            tld=gtts_voice["tld"],
            slow=(speech_speed == "slow"),
        )

    # Otherwise try ElevenLabs
    if api_key and api_key.strip():
        try:
            return _elevenlabs_tts(text, api_key.strip(), output_path, voice_id, model_id, stability, similarity_boost)
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg:
                logger.warning("ElevenLabs key invalid (401). Falling back to gTTS...")
            elif "429" in error_msg:
                logger.warning("ElevenLabs quota exceeded (429). Falling back to gTTS...")
            else:
                logger.warning(f"ElevenLabs failed: {e}. Falling back to gTTS...")

    logger.info("Using Google TTS (free fallback)")
    return _gtts_tts(text=text, output_path=output_path, slow=(speech_speed == "slow"))


def _elevenlabs_tts(text, api_key, output_path, voice_id=None, model_id="eleven_monolingual_v1", stability=0.5, similarity_boost=0.75):
    if not voice_id:
        voice_id = ELEVENLABS_VOICES[DEFAULT_VOICE]

    url = f"{ELEVENLABS_API_URL}/text-to-speech/{voice_id}"
    headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": api_key}
    payload = {"text": text, "model_id": model_id, "voice_settings": {"stability": stability, "similarity_boost": similarity_boost}}

    logger.info(f"[ElevenLabs] Synthesizing: '{text[:50]}...'")
    response = requests.post(url, json=payload, headers=headers, timeout=60)

    if response.status_code == 401:
        raise Exception("ElevenLabs API key is invalid or expired (401).")
    elif response.status_code == 429:
        raise Exception("ElevenLabs rate limit exceeded (429).")
    response.raise_for_status()

    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)

    logger.info(f"[ElevenLabs] Audio saved: {output_path} ({os.path.getsize(output_path)} bytes)")
    return output_path


def _gtts_tts(text: str, output_path: str, lang: str = "en", tld: str = "com", slow: bool = False) -> str:
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang=lang, tld=tld, slow=slow)
        tts.save(output_path)
        logger.info(f"[gTTS] Audio saved: {output_path} (lang={lang}, tld={tld}, slow={slow}, {os.path.getsize(output_path)} bytes)")
        return output_path
    except ImportError:
        raise Exception("gTTS not installed. Run: pip install gTTS")
    except Exception as e:
        logger.error(f"[gTTS] Failed: {e}")
        raise Exception(f"TTS failed: {e}")


def get_audio_duration(audio_path: str) -> float:
    import subprocess
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        return 5.0
