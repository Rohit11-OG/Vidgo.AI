"""
Vidgo.AI - AI Reel Generator
Flask backend serving Jinja2 templates and API endpoints.
Features: Async job processing, AI script generation, background music,
video customization, and social media sharing.
"""

import os
import re
import uuid
import time
import logging
import threading
import base64
from datetime import datetime

from flask import Flask, request, jsonify, send_file, render_template, Response
from dotenv import load_dotenv

from utils.tts import synthesize_speech, get_available_voices, VOICES, GTTS_VOICES, get_gtts_voice
from utils.video import create_reel, create_thumbnail, get_transition_list

load_dotenv(override=True)

# ── Paths ───────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Flask App Setup ─────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB max upload

OUTPUT_FOLDER = os.path.join(BASE_DIR, "output")
MUSIC_FOLDER = os.path.join(BASE_DIR, "static", "music")
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(MUSIC_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "bmp", "gif"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Voice Cache ─────────────────────────────────────────────
_voice_cache: dict = {"key": None, "voices": None, "timestamp": 0}
VOICE_CACHE_TTL = 300  # 5 minutes

# ── Job Tracking (in-memory) ───────────────────────────────
# Each job: { status, progress, message, result, error, created_at }
jobs: dict = {}
jobs_lock = threading.Lock()

ASPECT_RATIOS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
}

# ── Music Library ──────────────────────────────────────────
MUSIC_TRACKS = [
    {"id": "upbeat", "name": "Upbeat Energy", "file": "upbeat.mp3", "category": "Energetic", "duration": "30s"},
    {"id": "chill", "name": "Chill Vibes", "file": "chill.mp3", "category": "Chill", "duration": "30s"},
    {"id": "cinematic", "name": "Cinematic Epic", "file": "cinematic.mp3", "category": "Cinematic", "duration": "30s"},
    {"id": "inspiring", "name": "Inspiring Journey", "file": "inspiring.mp3", "category": "Inspirational", "duration": "30s"},
    {"id": "lofi", "name": "Lo-Fi Beats", "file": "lofi.mp3", "category": "Chill", "duration": "30s"},
]


# ── Helpers ─────────────────────────────────────────────────

JOB_ID_PATTERN = re.compile(r"^[0-9]{8}_[0-9]{6}_[a-f0-9]{8}$")


def is_valid_job_id(job_id: str) -> bool:
    """Prevent directory traversal by validating job_id format."""
    return bool(JOB_ID_PATTERN.match(job_id))


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_job_id():
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def get_cached_voices(api_key: str) -> dict:
    """Return cached categorized voice list, refreshing if stale or key changed."""
    now = time.time()
    if (
        _voice_cache["key"] == api_key
        and _voice_cache["voices"] is not None
        and now - _voice_cache["timestamp"] < VOICE_CACHE_TTL
    ):
        return _voice_cache["voices"]

    voices = get_available_voices(api_key or "")

    _voice_cache["key"] = api_key
    _voice_cache["voices"] = voices
    _voice_cache["timestamp"] = now
    return voices


def update_job(job_id: str, **kwargs):
    """Thread-safe job state update."""
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(kwargs)


def cleanup_old_jobs(max_age_seconds=3600):
    """Remove generated jobs older than max_age_seconds (default 1 hour)."""
    import shutil
    now = time.time()
    cleaned: int = 0
    try:
        for job_id in os.listdir(OUTPUT_FOLDER):
            job_path = os.path.join(OUTPUT_FOLDER, job_id)
            if os.path.isdir(job_path):
                age = now - os.path.getmtime(job_path)
                if age > max_age_seconds:
                    shutil.rmtree(job_path, ignore_errors=True)
                    cleaned += 1
        # Also clean up old job entries from memory
        with jobs_lock:
            stale = [jid for jid, j in jobs.items() if now - j.get("created_at", 0) > max_age_seconds]
            for jid in stale:
                del jobs[jid]
        if cleaned:
            logger.info(f"Cleaned up {cleaned} old job(s) and {len(stale)} memory entries")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")


def stream_video(video_path: str):
    """Generator to stream video in chunks for memory efficiency."""
    CHUNK_SIZE = 1024 * 1024  # 1 MB chunks
    with open(video_path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            yield chunk


# ── Periodic Cleanup (background thread) ───────────────────
def _start_cleanup_scheduler():
    def run():
        while True:
            time.sleep(1800)  # Every 30 minutes
            cleanup_old_jobs()

    t = threading.Thread(target=run, daemon=True)
    t.start()


_start_cleanup_scheduler()


# ── Rate limiter (simple in-memory) ────────────────────────
_rate_limits: dict[str, float] = {}
RATE_LIMIT_SECONDS = 10  # Min seconds between generate requests per IP


def check_rate_limit(ip: str) -> bool:
    """Returns True if request is allowed, False if rate-limited."""
    now = time.time()
    last = _rate_limits.get(ip, 0)
    if now - last < RATE_LIMIT_SECONDS:
        return False
    _rate_limits[ip] = now
    return True


# ═══════════════════════════════════════════════════════════
#  API Routes
# ═══════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Serve the main page."""
    return render_template("index.html")


@app.route("/api/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": "Vidgo.AI",
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/api/voices", methods=["POST"])
def voices():
    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key", "") or os.getenv("ELEVENLABS_API_KEY", "")
    return jsonify(get_cached_voices(api_key))


@app.route("/api/transitions")
def transitions():
    """Return list of available video transitions."""
    return jsonify(get_transition_list())


@app.route("/api/voice-preview", methods=["POST"])
def voice_preview():
    """Generate a short voice preview clip."""
    try:
        data = request.get_json(silent=True) or {}
        voice_id = data.get("voice_id", "gtts_us")
        preview_text = "Hello! This is a preview of how your narration will sound."

        gtts_voice = get_gtts_voice(voice_id)
        if not gtts_voice:
            return jsonify({"error": "Voice preview is only available for free voices"}), 400

        import tempfile
        from gtts import gTTS
        tts = gTTS(text=preview_text, lang=gtts_voice["lang"], tld=gtts_voice["tld"], slow=False)
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tts.save(temp.name)
        temp.close()

        response = send_file(temp.name, mimetype="audio/mpeg")

        @response.call_on_close
        def cleanup():
            try:
                os.unlink(temp.name)
            except Exception:
                pass

        return response
    except Exception as e:
        logger.error(f"Voice preview error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate", methods=["POST"])
def generate():
    try:
        # Rate limiting
        if not check_rate_limit(request.remote_addr):
            return jsonify({"error": "Please wait a few seconds before generating again."}), 429

        if "photos" not in request.files:
            return jsonify({"error": "No photos uploaded"}), 400

        files = request.files.getlist("photos")
        valid_files = [f for f in files if f and f.filename and allowed_file(f.filename)]

        if not valid_files:
            return jsonify({"error": "No valid image files. Supported: PNG, JPG, JPEG, WebP, BMP, GIF"}), 400
        if len(valid_files) > 20:
            return jsonify({"error": "Maximum 20 images allowed"}), 400

        script = request.form.get("script", "").strip()
        voice = request.form.get("voice", "rachel")
        transition = request.form.get("transition", "fade")
        user_api_key = request.form.get("api_key", "").strip()
        api_key = user_api_key or os.getenv("ELEVENLABS_API_KEY", "")

        # New customization params
        aspect_ratio = request.form.get("aspect_ratio", "9:16")
        custom_duration = request.form.get("duration_per_image", "").strip()
        title_text = request.form.get("title_text", "").strip()
        title_position = request.form.get("title_position", "top")
        music_id = request.form.get("music", "").strip()
        music_volume = float(request.form.get("music_volume", "0.15"))
        transition_duration = float(request.form.get("transition_duration", "0.5"))
        speech_speed = request.form.get("speech_speed", "normal")

        if not script:
            return jsonify({"error": "Please provide a narration script"}), 400
        if len(script) > 5000:
            return jsonify({"error": "Script too long. Maximum 5000 characters."}), 400

        resolution = ASPECT_RATIOS.get(aspect_ratio, (1080, 1920))
        duration_per_image = float(custom_duration) if custom_duration else None

        job_id = generate_job_id()
        job_dir = os.path.join(OUTPUT_FOLDER, job_id)
        os.makedirs(job_dir, exist_ok=True)

        logger.info(f"Job {job_id}: {len(valid_files)} images, voice={voice}, transition={transition}, ratio={aspect_ratio}")

        # Save uploaded images synchronously (fast)
        image_paths = []
        for i, file in enumerate(valid_files):
            ext = file.filename.rsplit(".", 1)[1].lower()
            filepath = os.path.join(job_dir, f"img_{i:03d}.{ext}")
            file.save(filepath)
            image_paths.append(filepath)

        # Initialize job tracking
        with jobs_lock:
            jobs[job_id] = {
                "status": "processing",
                "progress": 10,
                "message": "Uploading images...",
                "result": None,
                "error": None,
                "created_at": time.time(),
            }

        # Run heavy processing in background thread
        def process_job():
            try:
                update_job(job_id, progress=20, message="Generating narration...")

                # Synthesize narration
                audio_path = os.path.join(job_dir, "narration.mp3")
                voice_id = VOICES.get(voice, voice)
                synthesize_speech(text=script, output_path=audio_path, api_key=api_key if api_key else None, voice_id=voice_id, speech_speed=speech_speed)

                update_job(job_id, progress=40, message="Mixing audio...")

                # Mix with background music if selected
                final_audio = audio_path
                if music_id:
                    music_track = next((t for t in MUSIC_TRACKS if t["id"] == music_id), None)
                    if music_track:
                        music_path = os.path.join(MUSIC_FOLDER, music_track["file"])
                        if os.path.exists(music_path):
                            from utils.audio import mix_audio
                            mixed_path = os.path.join(job_dir, "mixed_audio.mp3")
                            mix_audio(audio_path, music_path, mixed_path, music_volume=music_volume)
                            final_audio = mixed_path

                update_job(job_id, progress=55, message="Creating video with transitions...")

                # Generate video
                output_video = os.path.join(job_dir, "reel.mp4")
                create_reel(
                    image_paths=image_paths,
                    audio_path=final_audio,
                    output_path=output_video,
                    transition=transition,
                    transition_duration=transition_duration,
                    resolution=resolution,
                    duration_per_image=duration_per_image,
                    title_text=title_text,
                    title_position=title_position,
                )

                update_job(job_id, progress=85, message="Generating thumbnail...")

                # Generate thumbnail
                thumbnail_path = os.path.join(job_dir, "thumbnail.jpg")
                create_thumbnail(output_video, thumbnail_path)

                video_size = os.path.getsize(output_video) / (1024 * 1024)
                tts_used = "ElevenLabs" if api_key else "Google TTS"

                update_job(
                    job_id,
                    status="done",
                    progress=100,
                    message="Reel generated successfully!",
                    result={
                        "job_id": job_id,
                        "video_url": f"/api/stream/{job_id}",
                        "download_url": f"/api/download/{job_id}",
                        "thumbnail_url": f"/api/thumbnail/{job_id}",
                        "video_size_mb": round(video_size, 2),
                        "num_images": len(image_paths),
                        "tts_engine": tts_used,
                    },
                )
                logger.info(f"Job {job_id}: Done ({video_size:.1f} MB)")

            except Exception as e:
                logger.error(f"Job {job_id} error: {e}", exc_info=True)
                update_job(job_id, status="error", progress=0, message=str(e), error=str(e))

        threading.Thread(target=process_job, daemon=True).start()

        return jsonify({"success": True, "job_id": job_id})

    except Exception as e:
        logger.error(f"Generation error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/status/<job_id>")
def job_status(job_id):
    """Poll for job progress."""
    if not is_valid_job_id(job_id):
        return jsonify({"error": "Invalid job ID"}), 400
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "result": job["result"],
        "error": job["error"],
    })


@app.route("/api/download/<job_id>")
def download(job_id):
    if not is_valid_job_id(job_id):
        return jsonify({"error": "Invalid job ID"}), 400
    video_path = os.path.join(OUTPUT_FOLDER, job_id, "reel.mp4")
    if not os.path.exists(video_path):
        return jsonify({"error": "Video not found"}), 404
    return send_file(video_path, mimetype="video/mp4", as_attachment=True, download_name=f"vidgo_reel_{job_id}.mp4")


@app.route("/api/stream/<job_id>")
def stream(job_id):
    if not is_valid_job_id(job_id):
        return jsonify({"error": "Invalid job ID"}), 400
    video_path = os.path.join(OUTPUT_FOLDER, job_id, "reel.mp4")
    if not os.path.exists(video_path):
        return jsonify({"error": "Video not found"}), 404

    file_size = os.path.getsize(video_path)
    return Response(
        stream_video(video_path),
        mimetype="video/mp4",
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
        },
    )


@app.route("/api/thumbnail/<job_id>")
def thumbnail(job_id):
    if not is_valid_job_id(job_id):
        return jsonify({"error": "Invalid job ID"}), 400
    thumb_path = os.path.join(OUTPUT_FOLDER, job_id, "thumbnail.jpg")
    if not os.path.exists(thumb_path):
        return jsonify({"error": "Thumbnail not found"}), 404
    return send_file(thumb_path, mimetype="image/jpeg")


# ═══════════════════════════════════════════════════════════
#  AI Script Generation
# ═══════════════════════════════════════════════════════════

@app.route("/api/generate-script", methods=["POST"])
def generate_script():
    """Generate a narration script from uploaded images using Gemini AI."""
    try:
        if "photos" not in request.files:
            return jsonify({"error": "No photos uploaded"}), 400

        files = request.files.getlist("photos")
        valid_files = [f for f in files if f and f.filename and allowed_file(f.filename)]

        if not valid_files:
            return jsonify({"error": "No valid images found"}), 400

        tone = request.form.get("tone", "professional")
        custom_prompt = request.form.get("custom_prompt", "").strip()

        # Convert images to base64 for the AI
        image_data = []
        for f in valid_files[:5]:  # Limit to 5 images for API efficiency
            f.seek(0)
            data = base64.b64encode(f.read()).decode("utf-8")
            mime = f"image/{f.filename.rsplit('.', 1)[1].lower()}"
            if mime == "image/jpg":
                mime = "image/jpeg"
            image_data.append({"data": data, "mime_type": mime})

        from utils.ai_script import generate_narration_script
        user_gemini_key = request.form.get("gemini_api_key", "").strip()
        gemini_key = user_gemini_key or os.getenv("GEMINI_API_KEY", "")
        script = generate_narration_script(
            image_data=image_data,
            tone=tone,
            custom_prompt=custom_prompt,
            api_key=gemini_key,
        )

        return jsonify({"success": True, "script": script})

    except Exception as e:
        logger.error(f"Script generation error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════
#  Music Library
# ═══════════════════════════════════════════════════════════

@app.route("/api/music")
def music_list():
    """Return list of available background music tracks."""
    available = []
    for track in MUSIC_TRACKS:
        music_path = os.path.join(MUSIC_FOLDER, track["file"])
        available.append({
            **track,
            "available": os.path.exists(music_path),
            "preview_url": f"/static/music/{track['file']}",
        })
    return jsonify(available)


# ═══════════════════════════════════════════════════════════
#  Social Media Export
# ═══════════════════════════════════════════════════════════

PLATFORM_SETTINGS = {
    "instagram": {"resolution": (1080, 1920), "max_duration": 90, "label": "Instagram Reels"},
    "tiktok":    {"resolution": (1080, 1920), "max_duration": 180, "label": "TikTok"},
    "youtube":   {"resolution": (1920, 1080), "max_duration": 60, "label": "YouTube Shorts"},
}


@app.route("/api/export/<job_id>/<platform>")
def export_for_platform(job_id, platform):
    """Re-encode video optimized for a specific social media platform."""
    if not is_valid_job_id(job_id):
        return jsonify({"error": "Invalid job ID"}), 400
    if platform not in PLATFORM_SETTINGS:
        return jsonify({"error": f"Unknown platform. Supported: {', '.join(PLATFORM_SETTINGS.keys())}"}), 400

    source_video = os.path.join(OUTPUT_FOLDER, job_id, "reel.mp4")
    if not os.path.exists(source_video):
        return jsonify({"error": "Video not found"}), 404

    settings = PLATFORM_SETTINGS[platform]
    w, h = settings["resolution"]
    export_path = os.path.join(OUTPUT_FOLDER, job_id, f"reel_{platform}.mp4")

    if not os.path.exists(export_path):
        import subprocess
        cmd = [
            "ffmpeg", "-y", "-i", source_video,
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-t", str(settings["max_duration"]),
            "-movflags", "+faststart",
            export_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                logger.error(f"Export error: {result.stderr}")
                return jsonify({"error": "Export encoding failed"}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return send_file(
        export_path,
        mimetype="video/mp4",
        as_attachment=True,
        download_name=f"vidgo_{platform}_{job_id}.mp4",
    )


# ── Error Handlers ──────────────────────────────────────────

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "Upload too large. Max 50 MB."}), 413

@app.errorhandler(429)
def rate_limited(e):
    return jsonify({"error": "Too many requests. Please slow down."}), 429


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    logger.info(f"Vidgo.AI API starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
