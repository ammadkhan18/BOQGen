"""
Thin wrapper around the Groq Python SDK.

Kept separate from ai/extraction.py so the raw "call the model" mechanics
(retries, base64 encoding, model selection) are isolated from the
"parse this into our Pydantic schema" logic.
"""
from __future__ import annotations

import base64
import io
import json
import logging
from typing import List, Optional

from groq import Groq
from PIL import Image

import config

logger = logging.getLogger(__name__)


class GroqClientError(Exception):
    pass


def _image_to_data_url(image: Image.Image, max_dim: int = config.MAX_IMAGE_DIMENSION) -> str:
    img = image.convert("RGB")
    w, h = img.size
    longest = max(w, h)
    if longest > max_dim:
        scale = max_dim / longest
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def get_client(api_key: str) -> Groq:
    if not api_key:
        raise GroqClientError(
            "No Groq API key provided. Get a free key at https://console.groq.com/keys "
            "and enter it in the sidebar, or set GROQ_API_KEY as an environment/secrets variable."
        )
    return Groq(api_key=api_key)


def call_vision_model(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    images: List[Image.Image],
    model: str = config.GROQ_VISION_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 900,
) -> str:
    """Send text + one or more images to a Groq vision-capable model and
    return the raw text response (expected to be a JSON string, validated
    by the caller in ai/extraction.py).
    """
    client = get_client(api_key)

    content = [{"type": "text", "text": user_prompt}]
    for img in images:
        content.append({"type": "image_url", "image_url": {"url": _image_to_data_url(img)}})

    try:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
            reasoning_effort="none",
            reasoning_format="hidden",
        )
        return response.choices[0].message.content
    except Exception as exc:
        logger.exception("Groq vision call failed")
        raise GroqClientError(f"Groq API call failed: {exc}") from exc


def call_text_model(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    model: str = config.GROQ_TEXT_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 1500,
    json_mode: bool = False,
) -> str:
    client = get_client(api_key)
    try:
        kwargs = dict(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    except Exception as exc:
        logger.exception("Groq text call failed")
        raise GroqClientError(f"Groq API call failed: {exc}") from exc
