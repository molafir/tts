# -*- coding: utf-8 -*-
"""Gemini TTS Studio Pro
Persian RTL Streamlit app for Gemini 3.8 Flash TTS / Flash-Lite TTS.

Install:
    pip install -U "google-genai>=2.25.0" "streamlit>=1.42.0" requests
Run:
    streamlit run gemini_tts_studio_pro.py

API key may be supplied through Streamlit secrets (GEMINI_API_KEY), an
environment variable, or the sidebar. Telegram credentials are optional.
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import struct
import time
import wave
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import requests
import streamlit as st

try:
    from google import genai
    from google.genai import types
except ImportError:  # Friendly error in the UI
    genai = None
    types = None


APP_TITLE = "Gemini TTS Studio Pro"
TTS_MODELS = {
    "کیفیت و اجرای طبیعی‌تر — Flash": "gemini-3.8-flash-tts",
    "سرعت و هزینه کمتر — Flash-Lite": "gemini-3.8-flash-lite-tts",
}
TEXT_MODEL = "gemini-3.8-flash"
MAX_CHUNK_CHARS = 3500  # Conservative character-based split; not an API token count.
PREBUILT_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]
AUDIO_MIME = {
    "WAV (پیشنهادی)": "audio/wav",
    "PCM 16-bit / L16": "audio/l16",
    "μ-law": "audio/mulaw",
    "A-law": "audio/alaw",
}
CONSENT_TEXTS = {
    "English (US/UK/India/Australia)": (
        "I am the owner of this voice and I consent to Google using this voice to create a synthetic voice model."
    ),
    "العربية": "أنا مالك هذا الصوت وأوافق على أن تستخدم Google هذا الصوت لإنشاء نموذج صوتي اصطناعي.",
}


# ----------------------------- Generic helpers -----------------------------

def obj_get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def safe_error(exc: Exception) -> str:
    """Keep API errors readable without swallowing their underlying message."""
    message = str(exc).strip() or exc.__class__.__name__
    return message[:1800]


def get_secret(name: str, default: str = "") -> str:
    value = os.environ.get(name, "")
    if value:
        return value
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or default)


def make_client(api_key: str):
    if genai is None:
        raise RuntimeError('کتابخانه google-genai نصب نیست. دستور نصب را در راهنمای برنامه اجرا کنید.')
    if not api_key.strip():
        raise RuntimeError("کلید Gemini API وارد نشده است.")
    return genai.Client(api_key=api_key.strip())


def decode_base64_or_bytes(value: Any) -> bytes:
    if value is None:
        raise ValueError("پاسخ API دادهٔ صوتی نداشت.")
    if isinstance(value, bytes):
        # SDK helpers may expose bytes directly; otherwise API docs use base64 text.
        if value[:4] == b"RIFF":
            return value
        try:
            return base64.b64decode(value, validate=True)
        except Exception:
            return value
    if isinstance(value, str):
        try:
            return base64.b64decode(value, validate=True)
        except Exception as exc:
            raise ValueError("دادهٔ صوتی برگشتی، Base64 معتبر نیست.") from exc
    raise TypeError(f"نوع دادهٔ صوتی ناشناخته است: {type(value).__name__}")


def wav_metadata(wav_bytes: bytes) -> dict[str, Any]:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            return {
                "channels": wf.getnchannels(),
                "sample_rate": wf.getframerate(),
                "sample_width": wf.getsampwidth(),
                "frames": wf.getnframes(),
                "compression": wf.getcomptype(),
                "duration": wf.getnframes() / float(wf.getframerate()),
            }
    except (wave.Error, EOFError) as exc:
        raise ValueError("فایل WAV معتبر یا قابل‌خواندن نیست.") from exc


def pcm16_to_wav(pcm: bytes, sample_rate: int = 24000, channels: int = 1) -> bytes:
    if len(pcm) % 2:
        pcm = pcm[:-1]
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return out.getvalue()


def decode_mulaw_byte(value: int) -> int:
    value = (~value) & 0xFF
    sign = value & 0x80
    exponent = (value >> 4) & 0x07
    mantissa = value & 0x0F
    sample = ((mantissa << 3) + 0x84) << exponent
    sample -= 0x84
    return -sample if sign else sample


def decode_alaw_byte(value: int) -> int:
    value ^= 0x55
    t = (value & 0x0F) << 4
    seg = (value & 0x70) >> 4
    if seg == 0:
        t += 8
    elif seg == 1:
        t += 0x108
    else:
        t += 0x108
        t <<= seg - 1
    return -t if (value & 0x80) == 0 else t


def decode_g711(data: bytes, law: str) -> bytes:
    decoder = decode_mulaw_byte if law == "mulaw" else decode_alaw_byte
    out = bytearray()
    for byte in data:
        out.extend(struct.pack("<h", decoder(byte)))
    return bytes(out)


def encode_mulaw_sample(sample: int) -> int:
    BIAS = 0x84
    CLIP = 32635
    sign = 0x80 if sample < 0 else 0
    sample = min(abs(sample), CLIP) + BIAS
    exponent = 7
    mask = 0x4000
    while exponent > 0 and not (sample & mask):
        exponent -= 1
        mask >>= 1
    mantissa = (sample >> (exponent + 3)) & 0x0F
    return (~(sign | (exponent << 4) | mantissa)) & 0xFF


def encode_alaw_sample(sample: int) -> int:
    # ITU-T G.711 A-law encoder.
    if sample >= 0:
        mask = 0xD5
        pcm = sample
    else:
        mask = 0x55
        pcm = -sample - 1
    pcm = min(pcm, 32767)
    segment_ends = (0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF, 0x3FFF, 0x7FFF)
    segment = 0
    while segment < len(segment_ends) and pcm > segment_ends[segment]:
        segment += 1
    if segment >= 8:
        return 0x7F ^ mask
    value = segment << 4
    if segment < 2:
        value |= (pcm >> 4) & 0x0F
    else:
        value |= (pcm >> (segment + 3)) & 0x0F
    return value ^ mask


def pcm16_to_g711(pcm: bytes, law: str) -> bytes:
    if len(pcm) % 2:
        pcm = pcm[:-1]
    encoder = encode_mulaw_sample if law == "mulaw" else encode_alaw_sample
    return bytes(encoder(s[0]) for s in struct.iter_unpack("<h", pcm))


def wav_to_pcm16(wav_bytes: bytes) -> tuple[bytes, int, int]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        if wf.getcomptype() != "NONE" or wf.getsampwidth() != 2:
            raise ValueError("برای تبدیل فرمت، فقط WAV با PCM خطی 16-bit پشتیبانی می‌شود.")
        channels = wf.getnchannels()
        rate = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    return pcm, rate, channels


def join_wav_files(chunks: list[bytes]) -> bytes:
    if not chunks:
        raise ValueError("هیچ قطعهٔ صوتی برای اتصال وجود ندارد.")
    base_params = None
    frames = []
    for index, chunk in enumerate(chunks, start=1):
        with wave.open(io.BytesIO(chunk), "rb") as wf:
            params = (wf.getnchannels(), wf.getsampwidth(), wf.getframerate(), wf.getcomptype(), wf.getcompname())
            if wf.getcomptype() != "NONE":
                raise ValueError(f"قطعهٔ {index}: WAV فشرده است؛ اتصال مستقیم مجاز نیست.")
            if base_params is None:
                base_params = params
            elif params != base_params:
                raise ValueError(
                    f"مشخصات قطعات WAV یکسان نیست؛ قطعهٔ {index} با قطعهٔ اول تفاوت دارد."
                )
            frames.append(wf.readframes(wf.getnframes()))
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(base_params[0])
        wf.setsampwidth(base_params[1])
        wf.setframerate(base_params[2])
        wf.writeframes(b"".join(frames))
    return out.getvalue()


def split_long_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split without dropping text; paragraph/sentence boundaries are preferred."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    paragraphs = re.split(r"\n\s*\n", text)
    current = ""

    def flush():
        nonlocal current
        if current.strip():
            pieces.append(current.strip())
        current = ""

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        units = re.split(r"(?<=[.!?؟۔؛])\s+|\n", paragraph)
        for unit in units:
            unit = unit.strip()
            if not unit:
                continue
            if len(unit) > max_chars:
                flush()
                # Hard split only when a single sentence/word is itself oversized.
                for start in range(0, len(unit), max_chars):
                    pieces.append(unit[start:start + max_chars].strip())
                continue
            candidate = f"{current}\n{unit}" if current else unit
            if len(candidate) <= max_chars:
                current = candidate
            else:
                flush()
                current = unit
        flush()
    flush()
    return [p for p in pieces if p]


@dataclass
class Turn:
    speaker: str
    text: str
    style: str = ""


def parse_dialogue(raw: str, speaker_a: str, speaker_b: str, style_a: str, style_b: str) -> list[Turn]:
    labels = {
        speaker_a.casefold(): "a",
        speaker_b.casefold(): "b",
        "گوینده اول": "a", "گویندهٔ اول": "a", "گوینده ۱": "a",
        "گوینده دوم": "b", "گویندهٔ دوم": "b", "گوینده ۲": "b",
        "speaker 1": "a", "speaker a": "a", "a": "a", "1": "a",
        "speaker 2": "b", "speaker b": "b", "b": "b", "2": "b",
    }
    turns: list[Turn] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^([^:：]{1,60})\s*[:：]\s*(.*)$", line)
        if match and match.group(1).strip().casefold() in labels:
            who = labels[match.group(1).strip().casefold()]
            text = match.group(2).strip()
        else:
            # Unlabelled lines are assigned to speaker A; no prefix is injected into speech.
            who, text = "a", line
        if text:
            turns.append(Turn(
                speaker=speaker_a if who == "a" else speaker_b,
                text=text,
                style=style_a if who == "a" else style_b,
            ))
    return turns


def chunk_turns(turns: list[Turn], max_chars: int = MAX_CHUNK_CHARS) -> list[list[Turn]]:
    """Split oversized turns and group adjacent turns without losing speaker labels."""
    expanded: list[Turn] = []
    for turn in turns:
        for part in split_long_text(turn.text, max_chars=max_chars):
            expanded.append(Turn(turn.speaker, part, turn.style))
    groups: list[list[Turn]] = []
    current: list[Turn] = []
    current_size = 0
    for turn in expanded:
        add_size = len(turn.text)
        if current and current_size + add_size > max_chars:
            groups.append(current)
            current, current_size = [], 0
        current.append(turn)
        current_size += add_size
    if current:
        groups.append(current)
    return groups


# ------------------------------- Gemini TTS --------------------------------

def make_input_content(turns: list[Turn]) -> list[dict[str, Any]]:
    content = []
    for turn in turns:
        annotation: dict[str, str] = {"type": "speech_metadata"}
        if turn.speaker:
            annotation["speaker"] = turn.speaker
        if turn.style.strip():
            annotation["style"] = turn.style.strip()
        content.append({
            "type": "text",
            "text": turn.text,
            "annotations": [annotation],
        })
    return [{"type": "user_input", "content": content}]


def generate_one_chunk(
    client: Any,
    model: str,
    turns: list[Turn],
    mime_type: str,
    sample_rate: int,
    voice_a: str,
    voice_b: Optional[str] = None,
    speaker_a: str = "Speaker A",
    speaker_b: str = "Speaker B",
    use_stream: bool = False,
) -> bytes:
    content = make_input_content(turns)
    if voice_b:
        speech_config: Any = {
            "mode": "conversational",
            "speakers": [
                {"speaker": speaker_a, "voice": voice_a},
                {"speaker": speaker_b, "voice": voice_b},
            ],
        }
    else:
        speech_config = [{"voice": voice_a}]

    response_format: dict[str, Any] = {"type": "audio"}
    if use_stream:
        # Streaming TTS chunks are headerless 24 kHz mono PCM16 by default.
        stream = client.interactions.create(
            model=model,
            input=content,
            response_format=response_format,
            generation_config={"speech_config": speech_config},
            stream=True,
        )
        pcm_parts: list[bytes] = []
        for event in stream:
            if obj_get(event, "event_type") != "step.delta":
                continue
            delta = obj_get(event, "delta")
            if obj_get(delta, "type") == "audio":
                encoded = obj_get(delta, "data")
                if encoded:
                    pcm_parts.append(decode_base64_or_bytes(encoded))
        pcm = b"".join(pcm_parts)
        if not pcm:
            raise RuntimeError("استریم تمام شد اما قطعهٔ صوتی دریافت نشد.")
        return pcm16_to_wav(pcm, sample_rate=24000, channels=1)

    if mime_type != "audio/wav":
        response_format["mime_type"] = mime_type
        response_format["sample_rate"] = sample_rate
    else:
        response_format["mime_type"] = "audio/wav"

    interaction = client.interactions.create(
        model=model,
        input=content,
        response_format=response_format,
        generation_config={"speech_config": speech_config},
    )
    audio = obj_get(obj_get(interaction, "output_audio"), "data")
    return decode_base64_or_bytes(audio)


def synthesize(
    client: Any,
    model: str,
    text: str,
    mode: str,
    style: str,
    voice_a: str,
    voice_b: str,
    speaker_a: str,
    speaker_b: str,
    style_a: str,
    style_b: str,
    mime_type: str,
    sample_rate: int,
    use_stream: bool,
    progress_callback=None,
) -> tuple[bytes, bytes, str]:
    if mode == "تک‌گوینده":
        chunks = split_long_text(text)
        if not chunks:
            raise ValueError("متن خالی است.")
        turn_groups = [[Turn("", part, style)] for part in chunks]
        voice_b_for_request = None
    else:
        turns = parse_dialogue(text, speaker_a, speaker_b, style_a, style_b)
        if not turns:
            raise ValueError("هیچ خط قابل‌خواندنی در گفت‌وگو پیدا نشد.")
        turn_groups = chunk_turns(turns)
        voice_b_for_request = voice_b

    # For streaming only, force the documented raw PCM default and build WAVs.
    if use_stream:
        raw_chunks = []
        for idx, group in enumerate(turn_groups, 1):
            raw_chunks.append(generate_one_chunk(
                client, model, group, "audio/wav", 24000, voice_a,
                voice_b_for_request, speaker_a, speaker_b, True,
            ))
            if progress_callback:
                progress_callback(idx, len(turn_groups))
        playable_wav = join_wav_files(raw_chunks)
        if mime_type == "audio/wav":
            return playable_wav, playable_wav, "wav"
        pcm, rate, channels = wav_to_pcm16(playable_wav)
        raw = _convert_pcm_output(pcm, mime_type, rate, channels)
        return raw, playable_wav, _extension_for_mime(mime_type)

    audio_chunks = []
    for idx, group in enumerate(turn_groups, 1):
        audio_chunks.append(generate_one_chunk(
            client, model, group, mime_type, sample_rate, voice_a,
            voice_b_for_request, speaker_a, speaker_b, False,
        ))
        if progress_callback:
            progress_callback(idx, len(turn_groups))

    if mime_type == "audio/wav":
        playable_wav = join_wav_files(audio_chunks)
        return playable_wav, playable_wav, "wav"

    raw = b"".join(audio_chunks)
    if mime_type == "audio/l16":
        playable_wav = pcm16_to_wav(raw, sample_rate=sample_rate, channels=1)
    elif mime_type == "audio/mulaw":
        playable_wav = pcm16_to_wav(decode_g711(raw, "mulaw"), sample_rate=sample_rate, channels=1)
    elif mime_type == "audio/alaw":
        playable_wav = pcm16_to_wav(decode_g711(raw, "alaw"), sample_rate=sample_rate, channels=1)
    else:
        raise ValueError(f"فرمت خروجی ناشناخته است: {mime_type}")
    return raw, playable_wav, _extension_for_mime(mime_type)


def _convert_pcm_output(pcm: bytes, mime_type: str, sample_rate: int, channels: int) -> bytes:
    if channels != 1:
        raise ValueError("تبدیل فرمت خروجی فقط برای صدای تک‌کاناله فعال است.")
    if mime_type == "audio/l16":
        return pcm
    if mime_type == "audio/mulaw":
        return pcm16_to_g711(pcm, "mulaw")
    if mime_type == "audio/alaw":
        return pcm16_to_g711(pcm, "alaw")
    return pcm16_to_wav(pcm, sample_rate=sample_rate, channels=channels)


def _extension_for_mime(mime_type: str) -> str:
    return {
        "audio/wav": "wav",
        "audio/l16": "pcm",
        "audio/mulaw": "mulaw",
        "audio/alaw": "alaw",
    }.get(mime_type, "bin")


# ------------------------------ Voice library ------------------------------

def voice_field(voice: Any, field: str, default: Any = "") -> Any:
    value = obj_get(voice, field, default)
    if value is None:
        return default
    return value


def list_voices(client: Any, voice_types: list[str], search: str = "", max_pages: int = 10) -> list[Any]:
    all_voices: list[Any] = []
    page_token = None
    for _ in range(max_pages):
        kwargs: dict[str, Any] = {"type_": voice_types, "page_size": 100}
        if search.strip():
            kwargs["search"] = search.strip()
        if page_token:
            kwargs["page_token"] = page_token
        response = client.voices.list(**kwargs)
        voices = obj_get(response, "voices", []) or []
        all_voices.extend(list(voices))
        page_token = obj_get(response, "next_page_token", None)
        if not page_token:
            break
    return all_voices


def create_designed_voice(
    client: Any, model: str, display_name: str, prompt: str, gender: str, language_code: str
):
    voice: dict[str, Any] = {
        "model": model,
        "type": "prompted",
        "display_name": display_name.strip(),
        "prompted": {"input": prompt.strip()},
    }
    if gender in {"male", "female"}:
        voice["gender"] = gender
    if language_code.strip():
        voice["language_code"] = language_code.strip()
    return client.voices.create(store=True, voice=voice)


def create_remixed_voice(client: Any, base_voice: str, prompt: str, display_name: str):
    # Voice remixing was added to the Gemini API changelog on 2026-11-04.
    return client.voices.create(
        store=True,
        voice={
            "model": "gemini-3.8-flash-tts",
            "type": "prompted",
            "display_name": display_name.strip(),
            "prompted": {
                "base_voice": base_voice.strip(),
                "input": prompt.strip(),
            },
        },
    )


def validate_replication_wav(data: bytes, label: str, require_duration: bool = False) -> dict[str, Any]:
    meta = wav_metadata(data)
    if meta["channels"] != 1 or meta["sample_width"] != 2 or meta["sample_rate"] != 24000 or meta["compression"] != "NONE":
        raise ValueError(
            f"{label}: فایل باید WAV تک‌کاناله، PCM خطی 16-bit و 24000Hz باشد. "
            f"مشخصات فعلی: channels={meta['channels']}, width={meta['sample_width']*8}bit, "
            f"rate={meta['sample_rate']}Hz, compression={meta['compression']}"
        )
    if require_duration and not (10 <= meta["duration"] <= 30):
        raise ValueError(f"{label}: مدت فایل مرجع باید بین 10 تا 30 ثانیه باشد؛ فعلی {meta['duration']:.1f} ثانیه است.")
    return meta


def create_replicated_voice(
    client: Any,
    model: str,
    display_name: str,
    source_audio: bytes,
    consent_audio: bytes,
    store: bool,
):
    validate_replication_wav(source_audio, "صدای مرجع", require_duration=True)
    validate_replication_wav(consent_audio, "صدای رضایت")
    voice: dict[str, Any] = {
        "type": "replicated",
        "display_name": display_name.strip() or "Replicated voice",
        "replicated": {
            "source_audio": {"mime_type": "audio/wav", "data": base64.b64encode(source_audio).decode("ascii")},
            "consent_audio": {"mime_type": "audio/wav", "data": base64.b64encode(consent_audio).decode("ascii")},
        },
    }
    if not store:
        voice["model"] = model
    else:
        # The Gemini API developer docs show model on the stored replication request.
        voice["model"] = model
    return client.voices.create(store=store, voice=voice)


def sample_audio_bytes(voice_obj: Any) -> Optional[bytes]:
    sample = obj_get(voice_obj, "sample_audio")
    data = obj_get(sample, "data")
    if not data:
        return None
    return decode_base64_or_bytes(data)


# ----------------------------- Text generation -----------------------------

def generate_text(client: Any, prompt: str) -> str:
    response = client.models.generate_content(model=TEXT_MODEL, contents=prompt)
    text = obj_get(response, "text", "") or ""
    if not text.strip():
        raise RuntimeError("مدل متن خروجی خالی برگرداند.")
    return text.strip()


def transcribe_audio(client: Any, audio: bytes, mime_type: str, language_hint: str = "") -> str:
    prompt = (
        "Transcribe the supplied audio verbatim. Preserve the original language, "
        "script, names, line breaks, and wording. Do not translate, summarize, "
        "correct, or add commentary."
    )
    if language_hint.strip():
        prompt += f" The likely language is {language_hint.strip()}, but do not translate."
    audio_part = types.Part.from_bytes(data=audio, mime_type=mime_type)
    response = client.models.generate_content(model=TEXT_MODEL, contents=[prompt, audio_part])
    result = obj_get(response, "text", "") or ""
    if not result.strip():
        raise RuntimeError("متنی از فایل صوتی استخراج نشد.")
    return result.strip()


# -------------------------------- Telegram ----------------------------------

def telegram_send(token: str, chat_id: str, audio_wav: bytes, filename: str, as_audio: bool = False) -> dict[str, Any]:
    if not token.strip() or not chat_id.strip():
        raise ValueError("توکن ربات و Chat ID تلگرام باید وارد شوند.")
    method = "sendAudio" if as_audio else "sendDocument"
    field = "audio" if as_audio else "document"
    url = f"https://api.telegram.org/bot{token.strip()}/{method}"
    files = {field: (filename, io.BytesIO(audio_wav), "audio/wav")}
    response = requests.post(url, data={"chat_id": chat_id.strip()}, files=files, timeout=90)
    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError(f"پاسخ تلگرام JSON نبود (HTTP {response.status_code}).")
    if not response.ok or not payload.get("ok"):
        raise RuntimeError(payload.get("description", f"Telegram HTTP {response.status_code}"))
    return payload


# ------------------------------- Streamlit UI -------------------------------

st.set_page_config(page_title=APP_TITLE, page_icon="🎙️", layout="wide")
st.markdown(
    """
    <style>
    html, body, [class*="css"] { direction: rtl; text-align: right; }
    .block-container { padding-top: 1.2rem; padding-bottom: 3rem; }
    textarea, input, .stSelectbox, .stTextInput { direction: rtl; text-align: right; }
    div[data-testid="stFileUploader"] { direction: rtl; }
    .small-note {font-size: .88rem; color: #777;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🎙️ Gemini TTS Studio Pro")
st.caption("تبدیل متن به گفتار، گفت‌وگوی دوگوینده، طراحی و بازترکیب صدا، تکثیر با رضایت، کتابخانهٔ صدا و ارسال تلگرام")

if "last_audio_wav" not in st.session_state:
    st.session_state.last_audio_wav = None
if "last_audio_raw" not in st.session_state:
    st.session_state.last_audio_raw = None
if "last_audio_ext" not in st.session_state:
    st.session_state.last_audio_ext = "wav"
if "last_audio_mime" not in st.session_state:
    st.session_state.last_audio_mime = "audio/wav"
if "last_voice_id" not in st.session_state:
    st.session_state.last_voice_id = ""
if "voice_key" not in st.session_state:
    st.session_state.voice_key = ""
if "generated_text" not in st.session_state:
    st.session_state.generated_text = ""

with st.sidebar:
    st.header("اتصال و تنظیمات")
    api_default = get_secret("GEMINI_API_KEY")
    api_key = st.text_input("Gemini API Key", value=api_default, type="password", help="کلید را می‌توانید در Streamlit Secrets با نام GEMINI_API_KEY ذخیره کنید.")
    model_label = st.selectbox("مدل گفتار", list(TTS_MODELS.keys()), index=0)
    selected_model = TTS_MODELS[model_label]
    st.divider()
    st.subheader("تلگرام — اختیاری")
    tg_token = st.text_input("Bot Token", value=get_secret("TELEGRAM_BOT_TOKEN"), type="password")
    tg_chat_id = st.text_input("Chat ID", value=get_secret("TELEGRAM_CHAT_ID"))
    st.caption("برای WAV، ارسال به‌صورت فایل (sendDocument) انتخاب مناسب‌تری است.")
    st.divider()
    st.caption("مدل‌های TTS این نسخه: Gemini 3.8 Flash TTS و Flash-Lite TTS")


def obtain_client():
    return make_client(api_key)


def _copy_generated_to_tts() -> None:
    value = st.session_state.get("generated_text_view") or st.session_state.get("generated_text", "")
    st.session_state.single_text = value
    st.session_state.transfer_notice = "متن در ورودی تک‌گوینده قرار گرفت."


def _copy_transcript_to_tts() -> None:
    value = st.session_state.get("transcript_result") or st.session_state.get("transcribed_text", "")
    st.session_state.single_text = value
    st.session_state.transcript_transfer_notice = "متن رونویسی‌شده در ورودی تک‌گوینده قرار گرفت."


def _use_selected_voice() -> None:
    value = st.session_state.get("selected_library_voice_id", "")
    if value:
        st.session_state.single_custom_voice = value
        st.session_state.multi_custom_a = value
        st.session_state.last_voice_id = value
        st.session_state.voice_use_notice = "شناسهٔ انتخاب‌شده در فیلد صدای سفارشی قرار گرفت."


tab_tts, tab_text, tab_voices, tab_transcribe, tab_help = st.tabs([
    "تولید گفتار", "استودیوی متن", "مدیریت صداها", "رونویسی فایل صوتی", "راهنما"
])

with tab_tts:
    st.subheader("تبدیل متن به گفتار")
    mode = st.radio("حالت تولید", ["تک‌گوینده", "دوگوینده"], horizontal=True)
    if mode == "تک‌گوینده":
        left, right = st.columns([2, 1])
        with left:
            single_text = st.text_area(
                "متن برای خواندن",
                height=270,
                placeholder="متن را دقیقاً همان‌طور که باید خوانده شود وارد کنید…\nتگ‌های لحظه‌ای مثل <short pause> و <sigh> را می‌توانید داخل متن بگذارید.",
                key="single_text",
            )
            single_style = st.text_input(
                "راهنمای لحن و اجرا (اختیاری)",
                placeholder="مثلاً: warm, clear, cheerful, slow and expressive",
                key="single_style",
            )
        with right:
            voice_a = st.selectbox("صدای گوینده", PREBUILT_VOICES, index=3, key="single_voice")
            custom_voice_a = st.text_input("یا شناسهٔ صدای سفارشی", placeholder="voice_... یا voicekey_...", key="single_custom_voice")
            if custom_voice_a.strip():
                voice_a = custom_voice_a.strip()
            st.caption("متن بدون پاک‌سازی خودکار ارسال می‌شود؛ کلمات، شعر و تگ‌های شما دست‌کاری نمی‌شوند.")
        voice_b = ""
        speaker_a, speaker_b = "Speaker A", "Speaker B"
        style_a, style_b = "", ""
        tts_text = single_text
    else:
        c1, c2 = st.columns(2)
        with c1:
            speaker_a = st.text_input("نام گویندهٔ اول", value="مرد", key="speaker_a")
            voice_a = st.selectbox("صدای گویندهٔ اول", PREBUILT_VOICES, index=1, key="multi_voice_a")
            custom_voice_a = st.text_input("شناسهٔ سفارشی گویندهٔ اول (اختیاری)", key="multi_custom_a", placeholder="voice_... / voicekey_...")
            if custom_voice_a.strip():
                voice_a = custom_voice_a.strip()
            style_a = st.text_input("لحن گویندهٔ اول", placeholder="مثلاً: calm and warm", key="style_a")
        with c2:
            speaker_b = st.text_input("نام گویندهٔ دوم", value="زن", key="speaker_b")
            voice_b = st.selectbox("صدای گویندهٔ دوم", PREBUILT_VOICES, index=3, key="multi_voice_b")
            custom_voice_b = st.text_input("شناسهٔ سفارشی گویندهٔ دوم (اختیاری)", key="multi_custom_b", placeholder="voice_... / voicekey_...")
            if custom_voice_b.strip():
                voice_b = custom_voice_b.strip()
            style_b = st.text_input("لحن گویندهٔ دوم", placeholder="مثلاً: bright and expressive", key="style_b")
        st.info(f"هر نوبت را در یک خط با قالب «{speaker_a}: متن» یا «{speaker_b}: متن» بنویسید. خطوط بدون برچسب به گویندهٔ اول اختصاص می‌یابند.")
        tts_text = st.text_area(
            "متن گفت‌وگو",
            height=270,
            placeholder=f"{speaker_a}: سلام، حالت چطوره؟\n{speaker_b}: ممنون، خوبم. تو چطوری؟",
            key="multi_text",
        )
        voice_style = ""

    st.divider()
    cfmt, crate, cstream = st.columns([1.3, 1, 1])
    with cfmt:
        output_label = st.selectbox("فرمت خروجی", list(AUDIO_MIME.keys()), index=0)
        output_mime = AUDIO_MIME[output_label]
    with crate:
        sample_rate = st.selectbox("نرخ نمونه‌برداری برای فرمت خام", [24000, 16000, 8000], index=0)
    with cstream:
        use_stream = st.checkbox("تولید استریم‌شده", value=False, help="استریم به PCM خام 24kHz مونو می‌آید و در پایان به WAV تبدیل می‌شود.")
    if use_stream and output_mime != "audio/wav":
        st.caption("در حالت استریم، دریافت اولیه PCM است؛ برنامه در پایان آن را به فرمت انتخاب‌شده تبدیل می‌کند.")

    if st.button("🎧 تولید صدا", type="primary", use_container_width=True, key="generate_tts"):
        if not tts_text.strip():
            st.error("ابتدا متن را وارد کنید.")
        elif mode == "دوگوینده" and (not speaker_a.strip() or not speaker_b.strip() or speaker_a.strip() == speaker_b.strip()):
            st.error("نام دو گوینده باید خالی نباشد و با هم تفاوت داشته باشد.")
        else:
            try:
                client = obtain_client()
                progress_slot = st.empty()
                progress_bar = st.progress(0)
                def update_progress(done, total):
                    progress_bar.progress(min(1.0, done / max(total, 1)))
                    progress_slot.caption(f"در حال تولید قطعهٔ {done} از {total}…")
                with st.spinner("در حال تولید صدا با Gemini…"):
                    raw_audio, playable_wav, ext = synthesize(
                        client=client,
                        model=selected_model,
                        text=tts_text,
                        mode=mode,
                        style=single_style if mode == "تک‌گوینده" else "",
                        voice_a=voice_a,
                        voice_b=voice_b,
                        speaker_a=speaker_a,
                        speaker_b=speaker_b,
                        style_a=style_a,
                        style_b=style_b,
                        mime_type=output_mime,
                        sample_rate=sample_rate,
                        use_stream=use_stream,
                        progress_callback=update_progress,
                    )
                st.session_state.last_audio_raw = raw_audio
                st.session_state.last_audio_wav = playable_wav
                st.session_state.last_audio_ext = ext
                st.session_state.last_audio_mime = output_mime
                meta = wav_metadata(playable_wav)
                st.success(f"تولید انجام شد. مدت تقریبی: {meta['duration']:.1f} ثانیه | نرخ نمونه‌برداری: {meta['sample_rate']}Hz")
            except Exception as exc:
                st.error("تولید صدا ناموفق بود.")
                st.code(safe_error(exc))

    if st.session_state.last_audio_wav:
        st.divider()
        st.subheader("خروجی آماده")
        st.audio(st.session_state.last_audio_wav, format="audio/wav")
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "دانلود WAV قابل پخش",
                data=st.session_state.last_audio_wav,
                file_name="gemini_tts_output.wav",
                mime="audio/wav",
                use_container_width=True,
            )
        with d2:
            ext = st.session_state.last_audio_ext
            raw_mime = st.session_state.last_audio_mime
            st.download_button(
                f"دانلود خروجی اصلی ({ext})",
                data=st.session_state.last_audio_raw or st.session_state.last_audio_wav,
                file_name=f"gemini_tts_output.{ext}",
                mime=raw_mime,
                use_container_width=True,
            )
        with st.expander("ارسال به تلگرام"):
            telegram_mode = st.radio("نوع ارسال", ["ارسال به‌صورت فایل (مناسب WAV)", "ارسال به‌صورت Audio"], horizontal=True)
            if st.button("ارسال به تلگرام", key="send_telegram"):
                try:
                    result = telegram_send(
                        tg_token,
                        tg_chat_id,
                        st.session_state.last_audio_wav,
                        "gemini_tts_output.wav",
                        as_audio=telegram_mode == "ارسال به‌صورت Audio",
                    )
                    st.success("فایل با موفقیت به تلگرام ارسال شد.")
                except Exception as exc:
                    st.error("ارسال تلگرام ناموفق بود.")
                    st.code(safe_error(exc))

with tab_text:
    st.subheader("تولید یا آماده‌سازی متن با Gemini")
    text_task = st.selectbox("نوع کار", [
        "تولید متن برای گویندگی", "تبدیل متن به گفت‌وگوی دو نفره", "بازنویسی روان بدون تغییر معنا", "تقسیم متن به بخش‌های مناسب گویندگی"
    ])
    text_prompt = st.text_area("موضوع یا متن ورودی", height=220, key="text_prompt")
    extra_instruction = st.text_input("دستور تکمیلی (اختیاری)", placeholder="مثلاً: فارسی روان، لحن رسمی، حفظ نام‌ها")
    if st.button("ساخت متن", type="primary", key="make_text"):
        if not text_prompt.strip():
            st.error("ورودی خالی است.")
        else:
            prompts = {
                "تولید متن برای گویندگی": "Write a natural spoken script based on the following request. Output only the script, no intro or commentary.\n\n",
                "تبدیل متن به گفت‌وگوی دو نفره": "Convert the following material into a natural two-person dialogue. Label every turn exactly 'گوینده اول:' or 'گوینده دوم:'. Preserve facts and do not invent details. Output only the dialogue.\n\n",
                "بازنویسی روان بدون تغییر معنا": "Rewrite the following text to be clear and natural when spoken aloud. Preserve meaning, names, facts, and important wording. Do not summarize or add facts. Output only the revised text.\n\n",
                "تقسیم متن به بخش‌های مناسب گویندگی": "Divide the following text into logical narration sections. Preserve the wording verbatim; add only section separators and concise headings in square brackets.\n\n",
            }
            prompt = prompts[text_task] + text_prompt.strip()
            if extra_instruction.strip():
                prompt += "\n\nAdditional instruction: " + extra_instruction.strip()
            try:
                with st.spinner("در حال آماده‌سازی متن…"):
                    output = generate_text(obtain_client(), prompt)
                st.session_state.generated_text = output
            except Exception as exc:
                st.error("تولید متن ناموفق بود.")
                st.code(safe_error(exc))
    if st.session_state.generated_text:
        st.text_area("متن تولیدشده", value=st.session_state.generated_text, height=260, key="generated_text_view")
        st.button("انتقال متن به ورودی گفتار", key="transfer_to_tts", on_click=_copy_generated_to_tts)
        if st.session_state.get("transfer_notice"):
            st.success(st.session_state.pop("transfer_notice"))

with tab_voices:
    st.subheader("ساخت، بازترکیب و مدیریت صدا")
    voice_tabs = st.tabs(["طراحی صدا", "بازترکیب صدا", "تکثیر صدا", "کتابخانه و مدیریت"])

    with voice_tabs[0]:
        st.markdown("یک شخصیت صوتی تازه را با توصیف طبیعی بسازید. توصیف سن، جنسیت، بافت صدا، لهجه و ویژگی‌های پایدار را همین‌جا بنویسید؛ سبک اجرای هر متن را در بخش TTS تنظیم کنید.")
        design_name = st.text_input("نام صدا", value="صدای سفارشی", key="design_name")
        design_prompt = st.text_area(
            "توصیف صدا",
            height=140,
            placeholder="A mature female narrator with a clear, warm timbre, measured pacing, and a gentle natural accent.",
            key="design_prompt",
        )
        gd1, gd2 = st.columns(2)
        with gd1:
            design_gender = st.selectbox("جنسیت صوتی", ["unspecified", "female", "male"], index=0)
        with gd2:
            design_language = st.text_input("کد زبان (اختیاری)", value="fa-IR", help="مثلاً fa-IR، en-US، ar-XA")
        if st.button("ساخت صدای جدید", type="primary", key="create_design"):
            if not design_prompt.strip():
                st.error("توصیف صدا را وارد کنید.")
            else:
                try:
                    with st.spinner("در حال طراحی صدا…"):
                        created = create_designed_voice(obtain_client(), selected_model, design_name, design_prompt, design_gender, design_language)
                    voice_id = obj_get(created, "id", "") or ""
                    st.session_state.last_voice_id = voice_id
                    st.success(f"صدا ساخته شد: {voice_id}")
                    preview = sample_audio_bytes(created)
                    if preview:
                        st.audio(preview, format="audio/wav")
                        st.download_button("دانلود نمونهٔ صدای طراحی‌شده", preview, file_name="voice_design_preview.wav", mime="audio/wav")
                except Exception as exc:
                    st.error("طراحی صدا ناموفق بود.")
                    st.code(safe_error(exc))

    with voice_tabs[1]:
        st.markdown("یک صدای آماده، صدای کتابخانه یا شناسهٔ صدای سفارشی را انتخاب کنید و تغییرات نسبی را توصیف کنید. خروجی، صدای جدیدی است و صدای پایه دست‌نخورده می‌ماند.")
        remix_base_type = st.radio("منبع صدای پایه", ["صدای پیش‌ساخته", "شناسهٔ صدا"], horizontal=True, key="remix_base_type")
        if remix_base_type == "صدای پیش‌ساخته":
            remix_base = st.selectbox("صدای پایه", PREBUILT_VOICES, index=1, key="remix_prebuilt")
        else:
            remix_base = st.text_input("شناسهٔ صدای پایه", placeholder="voice_...", key="remix_custom_base")
        remix_name = st.text_input("نام صدای جدید", value="نسخهٔ بازترکیب‌شده", key="remix_name")
        remix_prompt = st.text_area("تغییرات موردنظر", height=120, placeholder="Soften the delivery, slightly lower the pitch, and add a subtle regional accent.", key="remix_prompt")
        if st.button("بازترکیب و ساخت صدا", type="primary", key="do_remix"):
            if not remix_base.strip() or not remix_prompt.strip():
                st.error("صدای پایه و توضیح تغییرات هر دو لازم‌اند.")
            else:
                try:
                    with st.spinner("در حال بازترکیب صدا…"):
                        created = create_remixed_voice(obtain_client(), remix_base, remix_prompt, remix_name)
                    voice_id = obj_get(created, "id", "") or ""
                    st.session_state.last_voice_id = voice_id
                    st.success(f"صدای مستقل جدید ساخته شد: {voice_id}")
                    preview = sample_audio_bytes(created)
                    if preview:
                        st.audio(preview, format="audio/wav")
                        st.download_button("دانلود نمونهٔ صدای بازترکیب‌شده", preview, file_name="voice_remix_preview.wav", mime="audio/wav")
                except Exception as exc:
                    st.error("بازترکیب صدا ناموفق بود.")
                    st.code(safe_error(exc))

    with voice_tabs[2]:
        st.warning("فقط صدای خودتان یا صدایی را تکثیر کنید که مجوز روشن و معتبر برای استفاده از آن دارید. فایل رضایت باید از همان گوینده باشد و متن رضایت را دقیقاً بخواند.")
        consent_language = st.selectbox("زبان متن رضایت", list(CONSENT_TEXTS.keys()), key="consent_language")
        st.code(CONSENT_TEXTS[consent_language])
        st.caption("فایل مرجع: ۱۰ تا ۳۰ ثانیه گفتار طبیعی. هر دو فایل باید WAV مونو، PCM 16-bit و 24kHz باشند.")
        source_upload = st.file_uploader("فایل صوتی مرجع گوینده", type=["wav"], key="source_upload")
        consent_upload = st.file_uploader("فایل ضبط‌شدهٔ رضایت همان گوینده", type=["wav"], key="consent_upload")
        rep_name = st.text_input("نام صدای تکثیرشده", value="صدای تکثیرشده", key="rep_name")
        rep_store = st.checkbox("ذخیرهٔ پایدار در پروژه (voice_...)", value=True, help="در حالت غیرفعال، API یک کلید voicekey_... با عمر محدود می‌دهد.")
        consent_confirm = st.checkbox("تأیید می‌کنم مجوز لازم برای این صدا را دارم و گوینده متن رضایت را آگاهانه ضبط کرده است.")
        if st.button("ایجاد صدای تکثیرشده", type="primary", key="create_replica"):
            if not source_upload or not consent_upload:
                st.error("هر دو فایل مرجع و رضایت لازم هستند.")
            elif not consent_confirm:
                st.error("ابتدا تأیید رضایت و حق استفاده را فعال کنید.")
            else:
                try:
                    with st.spinner("در حال اعتبارسنجی فایل‌ها و ایجاد صدای تکثیرشده…"):
                        created = create_replicated_voice(
                            obtain_client(), selected_model, rep_name,
                            source_upload.getvalue(), consent_upload.getvalue(), rep_store,
                        )
                    voice_id = obj_get(created, "id", "") or ""
                    voice_key_value = obj_get(created, "key", "") or ""
                    if rep_store and voice_id:
                        st.session_state.last_voice_id = voice_id
                        st.success(f"صدای تکثیرشده ذخیره شد: {voice_id}")
                    elif voice_key_value:
                        st.session_state.voice_key = voice_key_value
                        st.success("کلید صدای تکثیرشده ساخته شد. آن را در جای امن نگه دارید؛ زمان‌دار است.")
                        st.code(voice_key_value)
                    else:
                        st.warning("در پاسخ API شناسه یا کلید صدا پیدا نشد.")
                except Exception as exc:
                    st.error("تکثیر صدا ناموفق بود.")
                    st.code(safe_error(exc))

    with voice_tabs[3]:
        st.markdown("صداهای ذخیره‌شدهٔ پروژه را فهرست، جست‌وجو، دریافت یا حذف کنید. فهرست API صفحه‌بندی می‌شود.")
        filter_types = st.multiselect("نوع صدا", ["prompted", "replicated", "prebuilt"], default=["prompted", "replicated"])
        library_search = st.text_input("جست‌وجو در صداها", key="library_search")
        if st.button("بارگذاری کتابخانهٔ صدا", key="load_voice_library"):
            try:
                with st.spinner("در حال دریافت کتابخانه…"):
                    voices = list_voices(obtain_client(), filter_types or ["prompted", "replicated"], library_search)
                st.session_state.voice_library_rows = voices
                st.success(f"{len(voices)} صدا دریافت شد.")
            except Exception as exc:
                st.error("دریافت کتابخانه ناموفق بود.")
                st.code(safe_error(exc))
        voice_rows = st.session_state.get("voice_library_rows", [])
        if voice_rows:
            options = {}
            for v in voice_rows:
                vid = voice_field(v, "id", "") or voice_field(v, "key", "")
                title = voice_field(v, "display_name", "بدون نام")
                vtype = voice_field(v, "type", "نامشخص")
                if vid:
                    options[f"{title} | {vtype} | {vid}"] = vid
            if options:
                selected_voice_label = st.selectbox("صدای موردنظر", list(options.keys()), key="selected_library_voice")
                selected_voice_id = options[selected_voice_label]
                st.session_state.selected_library_voice_id = selected_voice_id
                a, b, c = st.columns(3)
                with a:
                    if st.button("دریافت جزئیات", key="get_voice_details"):
                        try:
                            details = obtain_client().voices.get(id=selected_voice_id)
                            st.json({
                                "id": obj_get(details, "id"),
                                "display_name": obj_get(details, "display_name"),
                                "type": obj_get(details, "type"),
                                "gender": obj_get(details, "gender"),
                                "language_code": obj_get(details, "language_code"),
                            })
                            sample = sample_audio_bytes(details)
                            if sample:
                                st.audio(sample, format="audio/wav")
                        except Exception as exc:
                            st.error(safe_error(exc))
                with b:
                    st.button("استفاده در تولید گفتار", key="use_library_voice", on_click=_use_selected_voice)
                    if st.session_state.get("voice_use_notice"):
                        st.success(st.session_state.pop("voice_use_notice"))
                with c:
                    confirm_delete = st.checkbox("حذف را تأیید می‌کنم", key="confirm_voice_delete")
                    if st.button("حذف صدای ذخیره‌شده", disabled=not confirm_delete, key="delete_library_voice"):
                        try:
                            obtain_client().voices.delete(id=selected_voice_id)
                            st.success("درخواست حذف به API ارسال شد.")
                            st.session_state.voice_library_rows = []
                        except Exception as exc:
                            st.error(safe_error(exc))
        if st.session_state.last_voice_id:
            st.caption("آخرین شناسهٔ صدای ساخته‌شده/انتخاب‌شده:")
            st.code(st.session_state.last_voice_id)
        if st.session_state.voice_key:
            st.caption("کلید stateless صدای تکثیرشده:")
            st.code(st.session_state.voice_key)

with tab_transcribe:
    st.subheader("تبدیل فایل صوتی به متن")
    audio_file = st.file_uploader("فایل صوتی", type=["wav", "mp3", "m4a", "flac", "ogg", "aac", "webm"], key="transcribe_upload")
    language_hint = st.text_input("زبان احتمالی (اختیاری)", placeholder="مثلاً Persian, Balochi, English")
    if st.button("رونویسی دقیق", type="primary", key="do_transcribe"):
        if not audio_file:
            st.error("یک فایل صوتی انتخاب کنید.")
        else:
            try:
                mime = audio_file.type or "audio/wav"
                with st.spinner("در حال شنیدن و رونویسی با Gemini…"):
                    transcript = transcribe_audio(obtain_client(), audio_file.getvalue(), mime, language_hint)
                st.session_state.transcribed_text = transcript
            except Exception as exc:
                st.error("رونویسی ناموفق بود.")
                st.code(safe_error(exc))
    if st.session_state.get("transcribed_text"):
        transcript_value = st.text_area("متن استخراج‌شده", value=st.session_state.transcribed_text, height=260, key="transcript_result")
        st.button("انتقال رونویسی به ورودی تک‌گوینده", key="transcript_to_tts", on_click=_copy_transcript_to_tts)
        if st.session_state.get("transcript_transfer_notice"):
            st.success(st.session_state.pop("transcript_transfer_notice"))

with tab_help:
    st.subheader("راهنمای اجرا")
    st.markdown(
        """
        **نصب در محیط پایتون یا Termux**
        ```bash
        python -m pip install -U "google-genai>=2.25.0" "streamlit>=1.42.0" requests
        ```
        **اجرا**
        ```bash
        streamlit run gemini_tts_studio_pro.py
        ```
        **تنظیم کلیدها در Streamlit Secrets**
        ```toml
        GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
        TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
        TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"
        ```
        **فرمت گفت‌وگوی دوگوینده**
        ```text
        مرد: سلام، حالت چطوره؟
        زن: ممنون، خوبم. تو چطوری؟
        ```
        **نکات مهم فنی**
        - برای Gemini 3.8 TTS، راهنمای لحن پایدار هر نوبت در `speech_metadata.style` ارسال می‌شود؛ تگ‌های کوتاه مثل `<laugh>`، `<sigh>` و `<short pause>` داخل متن باقی می‌مانند.
        - برنامه متن شما را به‌صورت خودکار سانسور، ترجمه یا اصلاح نمی‌کند.
        - متن بلند به قطعات کوچک‌تر تقسیم می‌شود. برش بر اساس تعداد نویسه محافظه‌کارانه است و جایگزین شمارش دقیق توکن API نیست.
        - در حالت استریم، خروجی PCM خام 24kHz مونو دریافت و در انتها به WAV تبدیل می‌شود.
        - تنظیمات سفارشی `safety_settings` در Interactions API پشتیبانی نمی‌شود؛ برنامه چنین پارامتری را به درخواست TTS اضافه نمی‌کند.
        - تکثیر صدا فقط با فایل مرجع و رضایت همان گوینده انجام شود. برنامه فرمت WAV را بررسی می‌کند؛ اعتبار رضایت را خود سرویس Google ارزیابی می‌کند.
        - شناسه‌های `voice_...` ذخیره‌شده در پروژه مدیریت می‌شوند؛ کلیدهای `voicekey_...` را محرمانه نگه دارید و به‌دلیل زمان‌دار بودن، برای استفادهٔ طولانی‌مدت روی آن‌ها حساب نکنید.
        """
    )
    st.markdown("**مستندات رسمی**")
    st.markdown(
        "- [Speech Generation](https://ai.google.dev/gemini-api/docs/speech-generation)\n"
        "- [Voice Design](https://ai.google.dev/gemini-api/docs/voice-design)\n"
        "- [Voice Replication](https://ai.google.dev/gemini-api/docs/voice-replication)\n"
        "- [Voice Remixing](https://ai.google.dev/gemini-api/docs/voice-remixing)\n"
        "- [Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview)"
    )

st.divider()
st.caption("Gemini TTS Studio Pro — کلید API را در فایل کد قرار ندهید و دسترسی به فایل تنظیمات را محدود نگه دارید.")
