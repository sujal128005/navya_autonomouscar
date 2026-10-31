"""'Ask Navya': describe what the camera sees with a free vision AI (display only - never drives).

Tap 'Ask Navya' on the phone page (optionally type a question). The current camera
picture plus what the car already measured (mode, nearest obstacle, detected objects)
goes to the first provider in config.ASK_PROVIDERS; if it fails (rate limit, error,
timeout, empty answer) the next one is tried. The answer shows which one replied.

Providers (both have free tiers, each needs its own free key - no billing):
  gemini  Google Gemini API      key: GEMINI_API_KEY  (aistudio.google.com -> Get API key)
  groq    Groq (OpenAI-style)    key: GROQ_API_KEY    (console.groq.com -> API Keys)
  claude  Anthropic Claude       key: ANTHROPIC_API_KEY (paid; only if you add it to the list)

Keys are read from environment variables, or from autopilot/keys.env (KEY=value per
line; that file is git-ignored so keys never reach GitHub).
Note: free tiers may use what you send to improve the provider's products.
"""

import base64
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2

import config

KEYS_FILE = Path(__file__).with_name("keys.env")
MAX_IMAGE_WIDTH = 960
SYSTEM = (
    "You are the eyes of Navya, a small autonomous ride-on car driving through a college "
    "corridor. You get one camera frame from the front of the car plus readings from its depth "
    "camera. Answer in 2-4 short sentences of plain text for a phone screen: people and "
    "obstacles in or near the car's path (left/ahead/right, rough distance), anything unusual, "
    "and any sign or text you can read. Trust the depth readings for distances. You only "
    "describe - you do not control the car."
)
KEY_NAMES = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "claude": "ANTHROPIC_API_KEY"}
NAMES = {"gemini": "Gemini", "groq": "Groq", "claude": "Claude"}


class ProviderError(Exception):
    """A provider could not answer; the message says why in a few words."""


def api_key(provider: str) -> str | None:
    name = KEY_NAMES[provider]
    if os.environ.get(name):
        return os.environ[name].strip()
    if KEYS_FILE.exists():
        for line in KEYS_FILE.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name and value.strip():
                return value.strip().strip('"').strip("'")
    return None


def _post_json(url: str, headers: dict, body: dict) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=config.ASK_TIMEOUT_S) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        reason = {400: "bad request", 401: "invalid key", 403: "key not allowed",
                  404: "model not found", 429: "free limit reached"}.get(e.code, f"HTTP {e.code}")
        raise ProviderError(reason) from e
    except urllib.error.URLError as e:
        raise ProviderError("no internet" if "getaddrinfo" in str(e.reason) else str(e.reason)) from e
    except TimeoutError as e:
        raise ProviderError("timed out") from e


def ask_gemini(key: str, jpeg_b64: str, prompt: str) -> str:
    data = _post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent",
        {"x-goog-api-key": key},
        {"system_instruction": {"parts": [{"text": SYSTEM}]},
         "contents": [{"role": "user", "parts": [
             {"text": prompt},
             {"inline_data": {"mime_type": "image/jpeg", "data": jpeg_b64}}]}],
         "generationConfig": {"maxOutputTokens": 1024}})
    parts = [p.get("text", "") for c in data.get("candidates", []) for p in c.get("content", {}).get("parts", [])]
    return " ".join(parts).strip()


def ask_groq(key: str, jpeg_b64: str, prompt: str) -> str:
    data = _post_json(
        "https://api.groq.com/openai/v1/chat/completions",
        {"Authorization": f"Bearer {key}"},
        {"model": config.GROQ_MODEL,
         "messages": [{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": [
                          {"type": "text", "text": prompt},
                          {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{jpeg_b64}"}}]}],
         "max_completion_tokens": 1024})
    text = data["choices"][0]["message"].get("content") or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()   # drop any reasoning block


def ask_claude(key: str, jpeg_b64: str, prompt: str) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise ProviderError("pip install anthropic") from e
    try:
        response = anthropic.Anthropic(api_key=key).beta.messages.create(
            model="claude-opus-5-5", max_tokens=16000, output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", system=SYSTEM,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": jpeg_b64}},
                {"type": "text", "text": prompt}]}])
    except anthropic.APIError as e:
        raise ProviderError(type(e).__name__) from e
    if response.stop_reason == "refusal":
        raise ProviderError("declined")
    return " ".join(b.text for b in response.content if b.type == "text").strip()


PROVIDERS = {"gemini": ask_gemini, "groq": ask_groq, "claude": ask_claude}


class AskNavya:
    def __init__(self):
        self.answer = "Tap 'Ask Navya' to get a description of what the camera sees."
        self._busy = False

    @staticmethod
    def configured() -> list[str]:
        return [p for p in config.ASK_PROVIDERS if p in PROVIDERS and api_key(p)]

    def ask(self, image_bgr, question: str = "", context: str = "") -> bool:
        """Start a request in the background; False if one is already running."""
        if self._busy or image_bgr is None:
            return False
        h, w = image_bgr.shape[:2]
        if w > MAX_IMAGE_WIDTH:
            image_bgr = cv2.resize(image_bgr, (MAX_IMAGE_WIDTH, int(h * MAX_IMAGE_WIDTH / w)))
        ok, jpg = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return False
        self._busy = True
        self.answer = "Thinking..."
        threading.Thread(target=self._run, daemon=True,
                         args=(jpg.tobytes(), question.strip() or "What do you see?", context)).start()
        return True

    def _run(self, jpeg: bytes, question: str, context: str):
        try:
            self.answer = self.describe(jpeg, question, context)
        finally:
            self._busy = False

    def describe(self, jpeg: bytes, question: str, context: str) -> str:
        """Try each configured provider in turn; return the first answer (or why none worked)."""
        providers = self.configured()
        if not providers:
            keys = " or ".join(KEY_NAMES[p] for p in config.ASK_PROVIDERS if p in KEY_NAMES)
            return f"No AI key set up. Put {keys} in autopilot/keys.env (free keys - see README)."
        jpeg_b64 = base64.standard_b64encode(jpeg).decode("ascii")
        prompt = f"Car readings: {context}\n\nQuestion: {question}"
        failures = []
        for provider in providers:
            started = time.monotonic()
            try:
                text = PROVIDERS[provider](api_key(provider), jpeg_b64, prompt)
                if not text:
                    raise ProviderError("empty answer")
            except (ProviderError, KeyError, IndexError, ValueError) as e:
                failures.append(f"{NAMES[provider]}: {e}")
                continue
            note = f"{NAMES[provider]}, {time.monotonic() - started:.0f} s"
            if failures:
                note += " - " + "; ".join(failures)
            return f"{text}  [{note}]"
        return "No AI could answer: " + "; ".join(failures)
