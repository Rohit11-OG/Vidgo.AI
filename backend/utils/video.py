"""
Vidgo.AI - FFmpeg Video Processing Module
Creates reels from images + audio with transitions and Ken Burns effects.
Supports 13+ professional transition types.
"""

import os
import subprocess
import logging

logger = logging.getLogger(__name__)

# ── Transition Registry ────────────────────────────────────
TRANSITIONS = {
    "fade":       {"ffmpeg": "fade",        "label": "Fade",        "icon": "✨", "category": "Classic",  "desc": "Smooth cross-dissolve"},
    "slideleft":  {"ffmpeg": "slideleft",   "label": "Slide Left",  "icon": "⬅️", "category": "Slide",   "desc": "Slide from right to left"},
    "slideright": {"ffmpeg": "slideright",  "label": "Slide Right", "icon": "➡️", "category": "Slide",   "desc": "Slide from left to right"},
    "slideup":    {"ffmpeg": "slideup",     "label": "Slide Up",    "icon": "⬆️", "category": "Slide",   "desc": "Slide from bottom to top"},
    "slidedown":  {"ffmpeg": "slidedown",   "label": "Slide Down",  "icon": "⬇️", "category": "Slide",   "desc": "Slide from top to bottom"},
    "zoomin":     {"ffmpeg": "circleopen",  "label": "Zoom In",     "icon": "🔍", "category": "Zoom",    "desc": "Circle expanding from center"},
    "zoomout":    {"ffmpeg": "circleclose", "label": "Zoom Out",    "icon": "🔎", "category": "Zoom",    "desc": "Circle collapsing to center"},
    "wipeleft":   {"ffmpeg": "wipeleft",    "label": "Wipe Left",   "icon": "🌊", "category": "Wipe",    "desc": "Horizontal wipe effect"},
    "wiperight":  {"ffmpeg": "wiperight",   "label": "Wipe Right",  "icon": "🌀", "category": "Wipe",    "desc": "Reverse horizontal wipe"},
    "wipeup":     {"ffmpeg": "wipeup",      "label": "Wipe Up",     "icon": "🔼", "category": "Wipe",    "desc": "Vertical wipe effect"},
    "wipedown":   {"ffmpeg": "wipedown",    "label": "Wipe Down",   "icon": "🔽", "category": "Wipe",    "desc": "Reverse vertical wipe"},
    "dissolve":   {"ffmpeg": "dissolve",    "label": "Dissolve",    "icon": "💫", "category": "Effect",  "desc": "Pixel dissolve effect"},
    "pixelize":   {"ffmpeg": "pixelize",    "label": "Pixelize",    "icon": "🟩", "category": "Effect",  "desc": "Pixelated mosaic transition"},
}

# Backward compat mapping for old transition names
_LEGACY_MAP = {"slide": "slideleft", "zoom": "zoomin"}


def get_ffmpeg_transition(transition_key: str) -> str:
    """Resolve a transition key to its FFmpeg xfade name."""
    key = _LEGACY_MAP.get(transition_key, transition_key)
    entry = TRANSITIONS.get(key)
    if entry:
        return entry["ffmpeg"]
    return "fade"


def get_transition_list() -> list:
    """Return a list of all available transitions for the frontend."""
    return [
        {"id": k, "label": v["label"], "icon": v["icon"], "category": v["category"], "desc": v["desc"]}
        for k, v in TRANSITIONS.items()
    ]


def create_reel(
    image_paths: list,
    audio_path: str,
    output_path: str,
    duration_per_image: float = None,
    resolution: tuple = (1080, 1920),
    fps: int = 30,
    transition: str = "fade",
    transition_duration: float = 0.5,
    title_text: str = "",
    title_position: str = "top",
) -> str:
    if not image_paths:
        raise ValueError("No images provided")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    width, height = resolution
    num_images = len(image_paths)

    # Clamp transition duration
    transition_duration = max(0.3, min(1.5, transition_duration))

    if duration_per_image is None and audio_path and os.path.exists(audio_path):
        from utils.tts import get_audio_duration
        total_audio = get_audio_duration(audio_path)
        duration_per_image = max(total_audio / num_images, 1.5)
    elif duration_per_image is None:
        duration_per_image = 3.0

    # Ensure each image is longer than the transition
    duration_per_image = max(duration_per_image, transition_duration + 0.5)

    logger.info(f"Creating reel: {num_images} images, {duration_per_image:.1f}s each, {width}x{height}, transition={transition} ({transition_duration}s)")

    filter_parts = []
    input_args = []

    for i, img_path in enumerate(image_paths):
        input_args.extend(["-loop", "1", "-t", str(duration_per_image), "-i", img_path])
        direction = i % 4
        zoom_start, zoom_end = 1.0, 1.08
        dur_frames = int(duration_per_image * fps)

        if direction == 0:
            zoom_expr = f"{zoom_start}+({zoom_end}-{zoom_start})*on/{dur_frames}"
            x_expr, y_expr = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        elif direction == 1:
            zoom_expr = f"{zoom_start}+({zoom_end}-{zoom_start})*on/{dur_frames}"
            x_expr, y_expr = f"(iw-iw/zoom)*on/{dur_frames}", "ih/2-(ih/zoom/2)"
        elif direction == 2:
            zoom_expr = f"{zoom_end}-({zoom_end}-{zoom_start})*on/{dur_frames}"
            x_expr, y_expr = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        else:
            zoom_expr = f"{zoom_start}+({zoom_end}-{zoom_start})*on/{dur_frames}"
            x_expr, y_expr = "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*on/{dur_frames}"

        filter_parts.append(
            f"[{i}:v]scale={width*2}:{height*2}:force_original_aspect_ratio=increase,"
            f"crop={width*2}:{height*2},"
            f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}'"
            f":d={dur_frames}:s={width}x{height}:fps={fps},"
            f"setsar=1,format=yuva420p[v{i}]"
        )

    if audio_path and os.path.exists(audio_path):
        input_args.extend(["-i", audio_path])
        audio_index = num_images
    else:
        audio_index = None

    # Resolve the ffmpeg transition name
    ffmpeg_transition = get_ffmpeg_transition(transition)

    if num_images == 1:
        filter_complex = f"{filter_parts[0]}; [v0]format=yuv420p[outv]"
    else:
        crossfade_parts = list(filter_parts)
        prev = "v0"
        for i in range(1, num_images):
            offset = max(i * duration_per_image - i * transition_duration, (i - 1) * 0.5 + 0.5)
            curr = f"v{i}"
            out = f"cf{i}" if i < num_images - 1 else "outv"
            crossfade_parts.append(f"[{prev}][{curr}]xfade=transition={ffmpeg_transition}:duration={transition_duration}:offset={offset:.2f},format=yuv420p[{out}]")
            prev = out if i < num_images - 1 else None
        filter_complex = "; ".join(crossfade_parts)

    cmd = ["ffmpeg", "-y"] + input_args + ["-filter_complex", filter_complex, "-map", "[outv]"]
    if audio_index is not None:
        cmd += ["-map", f"{audio_index}:a", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-movflags", "+faststart", output_path]

    logger.info("Running FFmpeg...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            return _create_simple_reel(image_paths, audio_path, output_path, duration_per_image, resolution, fps)

        # Add title text overlay if provided
        if title_text:
            _add_title_overlay(output_path, title_text, title_position, resolution)

        logger.info(f"Reel created: {output_path} ({os.path.getsize(output_path)/1024/1024:.1f} MB)")
        return output_path
    except subprocess.TimeoutExpired:
        raise Exception("Video generation timed out.")
    except FileNotFoundError:
        raise Exception("FFmpeg is not installed. Please install FFmpeg and add it to your PATH.")


def _create_simple_reel(image_paths, audio_path, output_path, duration_per_image, resolution, fps):
    width, height = resolution
    concat_file = output_path.replace(".mp4", "_concat.txt")
    with open(concat_file, "w") as f:
        for img_path in image_paths:
            f.write(f"file '{img_path.replace(chr(92), '/')}'\nduration {duration_per_image}\n")
        f.write(f"file '{image_paths[-1].replace(chr(92), '/')}'\n")

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file]
    if audio_path and os.path.exists(audio_path):
        cmd += ["-i", audio_path]
    cmd += ["-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-pix_fmt", "yuv420p", "-movflags", "+faststart", output_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr[:500]}")
        return output_path
    finally:
        if os.path.exists(concat_file):
            os.remove(concat_file)


def create_thumbnail(video_path: str, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    try:
        subprocess.run(["ffmpeg", "-y", "-i", video_path, "-ss", "00:00:01", "-vframes", "1", "-q:v", "2", output_path],
                       capture_output=True, text=True, timeout=30)
        return output_path
    except Exception:
        return None


def _add_title_overlay(video_path: str, title_text: str, position: str, resolution: tuple):
    """Burn a title text overlay onto the first 4 seconds of the video."""
    width, height = resolution
    temp_path = video_path.replace(".mp4", "_titled.mp4")

    # Escape special characters for FFmpeg drawtext
    safe_text = title_text.replace("'", "\\'").replace(":", "\\:")

    # Position mapping
    if position == "center":
        x_expr = "(w-text_w)/2"
        y_expr = "(h-text_h)/2"
    elif position == "bottom":
        x_expr = "(w-text_w)/2"
        y_expr = "h-text_h-80"
    else:  # top (default)
        x_expr = "(w-text_w)/2"
        y_expr = "80"

    font_size = max(32, int(width * 0.04))

    # Show title for first 4 seconds with fade in/out
    drawtext = (
        f"drawtext=text='{safe_text}'"
        f":fontsize={font_size}"
        f":fontcolor=white"
        f":borderw=3:bordercolor=black@0.6"
        f":x={x_expr}:y={y_expr}"
        f":enable='between(t,0,4)'"
        f":alpha='if(lt(t,0.5),t/0.5,if(gt(t,3.5),(4-t)/0.5,1))'"
    )

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", drawtext,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        "-movflags", "+faststart",
        temp_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            os.replace(temp_path, video_path)
            logger.info(f"Title overlay added: '{title_text}' at {position}")
        else:
            logger.warning(f"Title overlay failed: {result.stderr[:200]}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
    except Exception as e:
        logger.warning(f"Title overlay error: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
