"""ElevenLabs API access.

Thin wrappers over the REST endpoints. The read-only ones cost nothing. The
paid ones (``tts``, ``tts_with_timestamps``, ``sound_effect``, ``design_voice``) must only be called through
``spend.Guard``, which prices, caps, caches and logs every call.
"""

from __future__ import annotations

import httpx

from .config import api_key

BASE_URL = "https://api.elevenlabs.io"


def _raise_for_status(r: httpx.Response) -> None:
    """Turn API errors into a one-line message (e.g. a key missing a permission)."""
    if r.is_success:
        return
    try:
        detail = r.json().get("detail", {})
        message = detail.get("message") if isinstance(detail, dict) else str(detail)
    except ValueError:
        message = r.text[:200]
    raise SystemExit(f"ElevenLabs {r.status_code} on {r.request.url.path}: {message}")


def _client(timeout: float = 30) -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        headers={"xi-api-key": api_key()},
        timeout=timeout,
        event_hooks={"response": [lambda r: (r.read(), _raise_for_status(r))]},
    )


def _cost_headers(r: httpx.Response) -> dict:
    """Keep response headers that identify the request or report its cost."""
    wanted = ("request-id", "character", "credit", "cost", "usage")
    return {k: v for k, v in r.headers.items() if any(w in k.lower() for w in wanted)}


def subscription() -> dict:
    """Plan tier and credit usage for the current billing period. Costs nothing."""
    with _client() as c:
        r = c.get("/v1/user/subscription")
        return r.json()


def models() -> list[dict]:
    """Models available to this key. Costs nothing."""
    with _client() as c:
        r = c.get("/v1/models")
        return r.json()


def voices(search: str | None = None) -> list[dict]:
    """Voices in the account library (premade plus any saved). Costs nothing."""
    params: dict = {"page_size": 100}
    if search:
        params["search"] = search
    with _client() as c:
        r = c.get("/v2/voices", params=params)
        return r.json()["voices"]


# --- Paid endpoints: call only via spend.Guard ---------------------------------


def tts(
    text: str,
    voice_id: str,
    model_id: str,
    voice_settings: dict | None = None,
    output_format: str = "mp3_44100_128",
) -> tuple[bytes, dict]:
    """Text to speech. Returns (mp3 bytes, response metadata)."""
    body: dict = {"text": text, "model_id": model_id}
    if voice_settings:
        body["voice_settings"] = voice_settings
    with _client(timeout=300) as c:
        r = c.post(
            f"/v1/text-to-speech/{voice_id}", params={"output_format": output_format}, json=body
        )
        return r.content, _cost_headers(r)


def tts_with_timestamps(
    text: str,
    voice_id: str,
    model_id: str,
    previous_text: str | None = None,
    next_text: str | None = None,
    voice_settings: dict | None = None,
    output_format: str = "mp3_44100_128",
) -> tuple[dict, dict]:
    """Text to speech plus per-character timing. Returns (response JSON, metadata).

    The JSON holds ``audio_base64`` and ``alignment`` (characters with start/end
    seconds), which the mixer uses to place sound effects on paragraphs.
    """
    body: dict = {"text": text, "model_id": model_id}
    if previous_text:
        body["previous_text"] = previous_text
    if next_text:
        body["next_text"] = next_text
    if voice_settings:
        body["voice_settings"] = voice_settings
    with _client(timeout=300) as c:
        r = c.post(
            f"/v1/text-to-speech/{voice_id}/with-timestamps",
            params={"output_format": output_format},
            json=body,
        )
        return r.json(), _cost_headers(r)


def sound_effect(
    text: str,
    model_id: str = "eleven_text_to_sound_v2",
    duration_seconds: float | None = None,
    loop: bool = False,
    prompt_influence: float | None = None,
    output_format: str = "mp3_44100_128",
) -> tuple[bytes, dict]:
    """One generated sound effect. Returns (mp3 bytes, response metadata)."""
    body: dict = {"text": text, "model_id": model_id, "loop": loop}
    if duration_seconds is not None:
        body["duration_seconds"] = duration_seconds
    if prompt_influence is not None:
        body["prompt_influence"] = prompt_influence
    with _client(timeout=300) as c:
        r = c.post("/v1/sound-generation", params={"output_format": output_format}, json=body)
        return r.content, _cost_headers(r)


def design_voice(
    description: str,
    text: str,
    model_id: str = "eleven_ttv_v3",
    seed: int | None = None,
    output_format: str = "mp3_44100_128",
) -> tuple[dict, dict]:
    """Voice Design previews (usually three). Nothing is saved to the library."""
    body: dict = {"voice_description": description, "text": text, "model_id": model_id}
    if seed is not None:
        body["seed"] = seed
    with _client(timeout=300) as c:
        r = c.post("/v1/text-to-voice/design", params={"output_format": output_format}, json=body)
        return r.json(), _cost_headers(r)


# --- Library management (no credits) --------------------------------------------


def save_designed_voice(
    name: str,
    description: str,
    generated_voice_id: str,
    labels: dict | None = None,
    not_selected: list[str] | None = None,
) -> dict:
    """Save a Voice Design preview to the library; returns the new voice."""
    body: dict = {
        "voice_name": name,
        "voice_description": description,
        "generated_voice_id": generated_voice_id,
    }
    if labels:
        body["labels"] = labels
    if not_selected:
        body["played_not_selected_voice_ids"] = not_selected
    with _client(timeout=120) as c:
        return c.post("/v1/text-to-voice", json=body).json()


def create_collection(title: str, icon: str) -> dict:
    with _client() as c:
        return c.post("/v1/voices/collections", json={"title": title, "icon": icon}).json()


def add_to_collection(collection_id: str, voice_id: str) -> dict:
    with _client() as c:
        return c.post(f"/v1/voices/collections/{collection_id}/voice/{voice_id}").json()


def delete_voice(voice_id: str) -> dict:
    """Permanently delete a custom voice from the library."""
    with _client() as c:
        return c.delete(f"/v1/voices/{voice_id}").json()
