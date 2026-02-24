"""
Vidgo.AI - AI Script Generation Module
Uses Google Gemini API (new google-genai SDK) to generate narration scripts from images.
"""

import logging
import base64

logger = logging.getLogger(__name__)

TONE_PROMPTS = {
    "professional": "Write in a professional, polished, and informative tone suitable for business or brand content.",
    "casual": "Write in a casual, friendly, and conversational tone like talking to a friend.",
    "funny": "Write in a humorous, witty, and entertaining tone with clever wordplay.",
    "dramatic": "Write in a dramatic, cinematic, and intense tone that builds suspense and emotion.",
    "inspirational": "Write in an uplifting, motivational, and inspiring tone that moves people.",
}


def generate_narration_script(
    image_data: list,
    tone: str = "professional",
    custom_prompt: str = "",
    api_key: str = "",
) -> str:
    """
    Generate a narration script from images using Google Gemini API.
    
    Args:
        image_data: List of dicts with 'data' (base64) and 'mime_type'
        tone: One of professional, casual, funny, dramatic, inspirational
        custom_prompt: Optional additional instructions
        api_key: Gemini API key
    
    Returns:
        Generated narration script text
    """
    if not api_key:
        raise Exception(
            "Gemini API key is required for AI script generation. "
            "Add GEMINI_API_KEY to your .env file or paste it in the API Keys section. "
            "Get a free key at https://aistudio.google.com/apikey"
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise Exception("google-genai package not installed. Run: pip install google-genai")

    client = genai.Client(api_key=api_key)

    tone_instruction = TONE_PROMPTS.get(tone, TONE_PROMPTS["professional"])

    system_prompt = f"""You are a professional video narration scriptwriter for short-form social media reels (Instagram Reels, TikTok, YouTube Shorts).

Your task: Analyze the provided images and write a compelling narration script that tells a story connecting all the images in sequence.

Rules:
- {tone_instruction}
- Keep the script between 50-200 words (ideal for 15-60 second reels)
- Write ONLY the narration text — no stage directions, no timestamps, no formatting markers
- Make it flow naturally as spoken word
- Create smooth transitions between image descriptions
- End with a strong closing line or call-to-action
- Do NOT use emojis in the script
- Do NOT include any headings, bullet points, or labels"""

    if custom_prompt:
        system_prompt += f"\n\nAdditional instructions from the user: {custom_prompt}"

    logger.info(f"[Gemini] Generating script with tone={tone}, {len(image_data)} images")

    # Build content parts: text + images
    parts = [types.Part.from_text(text=system_prompt)]
    for img in image_data:
        img_bytes = base64.b64decode(img["data"])
        parts.append(types.Part.from_bytes(data=img_bytes, mime_type=img["mime_type"]))
    parts.append(types.Part.from_text(text="Now write the narration script for these images:"))

    # Try multiple models in case of quota limits
    models_to_try = ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-2.5-flash"]
    last_error = None

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[types.Content(role="user", parts=parts)],
            )

            script = response.text.strip()

            # Clean up any markdown formatting the model might add
            script = script.replace("**", "").replace("__", "")
            if script.startswith('"') and script.endswith('"'):
                script = script[1:-1]

            logger.info(f"[Gemini] Generated script with {model_name}: {len(script)} chars")
            return script

        except Exception as e:
            last_error = e
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
                logger.warning(f"[Gemini] {model_name} rate-limited, trying next model...")
                continue
            elif "404" in error_str or "not found" in error_str.lower():
                logger.warning(f"[Gemini] {model_name} not found, trying next model...")
                continue
            else:
                raise Exception(f"AI script generation failed: {error_str[:300]}")

    # All models exhausted
    raise Exception(
        "Gemini API rate limit reached. Please wait about 60 seconds and try again. "
        "Free tier has limited requests per minute."
    )
