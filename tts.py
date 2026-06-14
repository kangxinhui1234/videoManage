"""TTS via SiliconFlow CosyVoice 2 — 8 system voices + custom voice cloning."""

import os, re, time, base64
import requests, urllib3
import config

urllib3.disable_warnings()

SF_API_KEY = ""
_p = os.path.join(config.BASE_DIR, ".api_key_siliconflow")
if os.path.exists(_p):
    with open(_p) as f:
        SF_API_KEY = f.read().strip()

SF_BASE = "https://api.siliconflow.cn/v1"

# ---- 8 System Preset Voices ----
VOICES = {
    # Male
    "alex":     ("FunAudioLLM/CosyVoice2-0.5B:alex",     "Alex 沉稳男声"),
    "benjamin": ("FunAudioLLM/CosyVoice2-0.5B:benjamin", "Benjamin 低沉男声"),
    "charles":  ("FunAudioLLM/CosyVoice2-0.5B:charles",  "Charles 磁性男声"),
    "david":    ("FunAudioLLM/CosyVoice2-0.5B:david",    "David 欢快男声"),
    # Female
    "anna":     ("FunAudioLLM/CosyVoice2-0.5B:anna",     "Anna 沉稳女声"),
    "bella":    ("FunAudioLLM/CosyVoice2-0.5B:bella",    "Bella 激情女声"),
    "claire":   ("FunAudioLLM/CosyVoice2-0.5B:claire",   "Claire 温柔女声"),
    "diana":    ("FunAudioLLM/CosyVoice2-0.5B:diana",    "Diana 欢快女声"),
}


def cosy_speak(text, voice="FunAudioLLM/CosyVoice2-0.5B:anna",
               output_path=None, speed=1.0):
    """TTS via CosyVoice 2. speed: 0.25-4.0, lower=slower."""
    if not SF_API_KEY:
        raise RuntimeError("SiliconFlow API key not found")

    text = re.sub(r'https?://\S+', '', text).strip()
    if not text:
        raise ValueError("Text empty after URL removal")

    if output_path is None:
        filename = f"cosy_{int(time.time())}.mp3"
        output_path = os.path.join(config.OUTPUT_DIR, "audio", filename)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    body = {
        "model": "FunAudioLLM/CosyVoice2-0.5B",
        "input": text,
        "voice": voice,
        "response_format": "mp3",
    }
    if speed != 1.0:
        body["speed"] = round(speed, 2)

    resp = requests.post(f"{SF_BASE}/audio/speech", json=body,
        headers={"Authorization": f"Bearer {SF_API_KEY}"},
        timeout=(15, 120), verify=False, proxies={"http": None, "https": None})
    resp.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(resp.content)

    rel = os.path.relpath(output_path, config.BASE_DIR)
    return "/" + rel.replace("\\", "/")


# ---- Custom Voice Cloning ----

def upload_voice(audio_path, custom_name, reference_text):
    """Upload a reference audio file to create a custom voice. Returns voice URI."""
    if not SF_API_KEY:
        raise RuntimeError("SiliconFlow API key not found")

    with open(audio_path, "rb") as f:
        audio_data = f.read()

    ext = os.path.splitext(audio_path)[1].lower()
    mime_map = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".opus": "audio/opus"}
    mime = mime_map.get(ext, "audio/mpeg")

    body = {
        "model": "FunAudioLLM/CosyVoice2-0.5B",
        "customName": custom_name,
        "audio": f"data:{mime};base64,{base64.b64encode(audio_data).decode()}",
        "text": reference_text,
    }
    resp = requests.post(f"{SF_BASE}/uploads/audio/voice",
        json=body,
        headers={"Authorization": f"Bearer {SF_API_KEY}"},
        timeout=30, verify=False, proxies={"http": None, "https": None})
    resp.raise_for_status()
    return resp.json().get("uri", "")


def list_custom_voices():
    """List user's custom voices."""
    if not SF_API_KEY:
        return []
    resp = requests.get(f"{SF_BASE}/audio/voice/list",
        headers={"Authorization": f"Bearer {SF_API_KEY}"},
        timeout=10, verify=False, proxies={"http": None, "https": None})
    return resp.json() if resp.ok else []


def delete_voice(uri):
    """Delete a custom voice by URI."""
    resp = requests.post(f"{SF_BASE}/audio/voice/deletions",
        json={"uri": uri},
        headers={"Authorization": f"Bearer {SF_API_KEY}"},
        timeout=10, verify=False, proxies={"http": None, "https": None})
    return resp.ok
