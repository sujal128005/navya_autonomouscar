"""'Ask Navya': describe what the camera sees using Claude (display only - never drives).

Tap 'Ask Navya' on the phone page (optionally type a question). The current camera
picture plus what the car already measured (mode, nearest obstacle, detected objects)
goes to Claude, and the answer appears on the phone a few seconds later.

Needs the Anthropic SDK (pip install anthropic) and your own API key, set on the
laptop before starting the program, e.g. in PowerShell:
    $env:ANTHROPIC_API_KEY = "<your key>"
The driving never waits for this and never uses its answer.
"""

import base64
import threading
import time

import cv2

MODEL = "claude-opus-5-5"
MAX_IMAGE_WIDTH = 960
SYSTEM = (
    "You are the eyes of Navya, a small autonomous ride-on car driving through a college "
    "corridor. You get one camera frame from the front of the car plus readings from its depth "
    "camera. Answer in 2-4 short sentences of plain text for a phone screen: people and "
    "obstacles in or near the car's path (left/ahead/right, rough distance), anything unusual, "
    "and any sign or text you can read. Trust the depth readings for distances. You only "
    "describe - you do not control the car."
)


class AskNavya:
    def __init__(self):
        self.answer = "Tap 'Ask Navya' to get a description of what the camera sees."
        self._busy = False
        self._client = None
        # Importing the SDK takes a few seconds; do it now so the first tap answers sooner.
        threading.Thread(target=self._preload, daemon=True).start()

    @staticmethod
    def _preload():
        try:
            import anthropic  # noqa: F401
        except ImportError:
            pass

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

    def build_request(self, jpeg: bytes, question: str, context: str) -> dict:
        return dict(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "low"},     # a quick look, not deep analysis
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",                 # a declined request is retried on Anthropic's recommended model
            system=SYSTEM,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.standard_b64encode(jpeg).decode("ascii")}},
                {"type": "text", "text": f"Car readings: {context}\n\nQuestion: {question}"},
            ]}],
        )

    def _run(self, jpeg: bytes, question: str, context: str):
        started = time.monotonic()
        try:
            import anthropic
        except ImportError:
            self.answer = "Ask Navya needs the Anthropic SDK: pip install anthropic"
            self._busy = False
            return
        try:
            if self._client is None:
                self._client = anthropic.Anthropic()
            response = self._client.beta.messages.create(**self.build_request(jpeg, question, context))
            if response.stop_reason == "refusal":
                text = "Claude declined to describe this picture."
            else:
                text = " ".join(b.text for b in response.content if b.type == "text").strip() or "(no answer)"
            self.answer = f"{text}  [{time.monotonic() - started:.0f} s]"
        except anthropic.AuthenticationError:
            self.answer = "No valid API key. Set ANTHROPIC_API_KEY on the laptop and restart."
        except anthropic.RateLimitError:
            self.answer = "Too many requests - wait a minute and try again."
        except anthropic.APIConnectionError:
            self.answer = "No internet connection from the laptop."
        except anthropic.APIStatusError as e:
            self.answer = f"Claude API error {e.status_code}: {e.message}"
        except anthropic.AnthropicError as e:
            self.answer = f"Ask Navya is not set up: {e}"
        except TypeError as e:
            if "authentication" not in str(e):
                raise
            # The SDK raises TypeError when no API key or other credential is configured at all.
            self.answer = "No API key set. Set ANTHROPIC_API_KEY on the laptop and restart."
        finally:
            self._busy = False
