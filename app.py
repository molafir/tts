# Gemini 3.8 TTS Studio Pro
# هم‌تراز با راهنمای AI Studio تا ۲۸ اکتبر ۲۰۲۶ و صفحه مدل تا ۴ نوامبر ۲۰۲۶
# سقف رسمی: ۸۱۹۲ توکن ورودی، ۱۶۳۸۴ توکن خروجی. هر دو مدل ۳.۸ یک طرح درخواست دارند.
# pip install "google-genai>=2.25.0" streamlit requests
# streamlit run gemini_tts_studio.py
import base64
import io
import re
import time
import traceback
import wave

import requests
import streamlit as st
from google import genai

st.set_page_config(page_title="Gemini TTS Studio Pro", page_icon="🎙️", layout="wide")

RTL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600&family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
html, body, p, h1, h2, h3, h4, h5, h6, label, .stMarkdown, .stText { font-family: 'Vazirmatn', 'Tahoma', sans-serif; }
.material-symbols-rounded, .material-icons, [data-testid="stIconMaterial"], span[class*="material-symbols"] {
    font-family: 'Material Symbols Rounded' !important; direction: ltr !important; font-feature-settings: 'liga' !important;
}
textarea, .stTextArea textarea, .stTextInput input { direction: rtl; text-align: right; font-family: 'Vazirmatn', 'Tahoma', sans-serif; }
.stCodeBlock pre, .stCode pre { direction: rtl; text-align: right; font-size: 14px; line-height: 1.8; }
.stButton > button { white-space: normal; height: auto; line-height: 1.35; }
@media (max-width: 700px) {
  div[data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    flex: 1 1 48% !important;
    width: 48% !important;
    min-width: 48% !important;
  }
  .stButton > button { font-size: 0.78rem; padding: 0.4rem 0.35rem; }
}
</style>
"""
st.markdown(RTL_CSS, unsafe_allow_html=True)
st.title("🎙️ Gemini TTS Studio Pro")
st.caption("Gemini 3.8 · Interactions API · کتابخانه صدا، طراحی صدا، استریم و تلگرام")

# ----------------------------- Constants -----------------------------

SAMPLE_RATES = [24000, 16000, 8000]
INPUT_TOKEN_LIMIT = 8192
OUTPUT_TOKEN_LIMIT = 16384
HISTORY_LIMIT = 8
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 1.5
CUSTOM_TURN_LIMIT = 40

ALL_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]
VOICE_DESCRIPTIONS = {
    "Zephyr": "روشن", "Puck": "خوش‌بین", "Charon": "آموزنده", "Kore": "محکم",
    "Fenrir": "هیجان‌انگیز", "Leda": "جوان", "Orus": "محکم", "Aoede": "ملایم",
    "Callirrhoe": "آسان‌گیر", "Autonoe": "روشن", "Enceladus": "نفس‌گیر",
    "Iapetus": "شفاف", "Umbriel": "آسان‌گیر", "Algieba": "صاف", "Despina": "صاف",
    "Erinome": "پاک", "Algenib": "شنی", "Rasalgethi": "آموزنده", "Laomedeia": "خوش‌بین",
    "Achernar": "نرم", "Alnilam": "محکم", "Schedar": "یکنواخت", "Gacrux": "بالغ",
    "Pulcherrima": "پیشرو", "Achird": "دوستانه", "Zubenelgenubi": "غیررسمی",
    "Vindemiatrix": "ملایم", "Sadachbia": "سرزنده", "Sadaltager": "آگاه", "Sulafat": "گرم",
}
MODELS = ["gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts"]
MIME_TYPES = {
    "WAV (پیشنهادی)": "audio/wav",
    "PCM خطی L16": "audio/l16",
    "mu-law تلفنی": "audio/mulaw",
    "A-law تلفنی": "audio/alaw",
}
RAW_EXT = {"audio/l16": "pcm", "audio/mulaw": "mulaw", "audio/alaw": "alaw"}
PREDEFINED_STYLES = {
    "— (بدون سبک خاص / پیش‌فرض)": "",
    "گرم و مشتاق (Warm and enthusiastic)": "warm and enthusiastic, clear pacing",
    "آرام و عمیق (Calm and deep)": "calm and deep, steady pacing",
    "دوستانه و صمیمی (Friendly and gentle)": "friendly and gentle, approachable",
    "هیجان‌زده و پرانرژی (Excited and energetic)": "excited and energetic",
    "غمگین و آهسته (Sad and slow)": "sad and slow",
    "گوینده خبر رسمی (News anchor)": "professional news anchor, formal tone",
    "نجوا و مرموز (Whispering)": "whispering, mysterious",
    "طنز و کنایه (Sarcastic)": "sarcastic, playful",
    "سریع و هیجانی (Fast paced)": "speaking rapidly, excited",
    "سفارشی (Custom)": "custom",
}
QUICK_TAGS = [
    "<short pause>", "<long pause>", "<laugh>", "<sigh>",
    "<breath>", "<gasp>", "<cough>", "<whispers>",
    "|oh hmm|", "|oh really?|", "|absolutely|", "|ok|",
]

# ★ مطابق سند اکتبر ۲۰۲۶: در Interactions API از type و threshold کوچک استفاده می‌شود.
INTERACTION_SAFETY_SETTINGS = [
    {"type": "harassment", "threshold": "off"},
    {"type": "hate_speech", "threshold": "off"},
    {"type": "sexually_explicit", "threshold": "off"},
    {"type": "dangerous_content", "threshold": "off"},
]
# ★ models.generate_content هنوز ساختار قدیمی category/threshold را می‌گیرد.
TEXT_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "OFF"},
]

# ----------------------------- Utilities -----------------------------

def get_secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

def decode_b64(value):
    if not value:
        return b""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return base64.b64decode(value)

def pcm_to_wav_bytes(pcm, rate=24000, channels=1, sample_width=2):
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(int(rate))
        wf.writeframes(pcm)
    return out.getvalue()

def wav_pcm(data):
    if not data.startswith(b"RIFF"):
        return data, None
    with wave.open(io.BytesIO(data), "rb") as wf:
        return wf.readframes(wf.getnframes()), wf.getframerate()

def join_wavs(wav_list):
    frames = []
    rate = 24000
    width = 2
    channels = 1
    for blob in wav_list:
        with wave.open(io.BytesIO(blob), "rb") as wf:
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            rate = wf.getframerate()
            frames.append(wf.readframes(wf.getnframes()))
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(width)
        wf.setframerate(rate)
        wf.writeframes(b"".join(frames))
    return out.getvalue()

def mulaw_to_pcm16(data):
    out = bytearray()
    for value in data:
        u = (~value) & 0xFF
        t = (((u & 0x0F) << 3) + 0x84) << ((u & 0x70) >> 4)
        sample = 0x84 - t if (u & 0x80) else t - 0x84
        out.extend(int(max(-32768, min(32767, sample))).to_bytes(2, "little", signed=True))
    return bytes(out)

def alaw_to_pcm16(data):
    out = bytearray()
    for value in data:
        a = value ^ 0x55
        t = (a & 0x0F) << 4
        seg = (a & 0x70) >> 4
        if seg == 0:
            t += 8
        elif seg == 1:
            t += 0x108
        else:
            t += 0x108
            t <<= seg - 1
        sample = t if (a & 0x80) else -t
        out.extend(int(sample).to_bytes(2, "little", signed=True))
    return bytes(out)

def estimate_tokens(text):
    """تخمین رو به بالا (محافظه‌کارانه) برای هشدار سقف توکن ورودی."""
    s = text or ""
    if not s:
        return 1
    non_ascii = sum(1 for ch in s if ord(ch) > 127)
    ascii_len = len(s) - non_ascii
    # لاتین ≈ ۴ کاراکتر/توکن (اینجا ۳ برای احتیاط)، غیرلاتین (فارسی و…) ≈ ۱ کاراکتر/توکن
    return max(1, ascii_len // 3 + non_ascii)


def is_custom_voice(voice):
    v = (voice or "").strip()
    return v.startswith("voice_") or v.startswith("voicekey_")

def parse_speaker_line(line, spk1, spk2):
    line = line.strip()
    if not line:
        return None, None
    normalized = line.replace("：", ":").replace("﹕", ":")
    if ":" in normalized:
        prefix, txt = normalized.split(":", 1)
        prefix, txt = prefix.strip(), txt.strip()
        if prefix in (spk1, spk2):
            return prefix, txt
    return spk1, line

def clean_text(text):
    result = []
    for line in text.splitlines():
        line = re.sub(r"^[*_\s]+", "", line)
        line = re.sub(r"[*_\s]+$", "", line)
        result.append(line.strip("`\"'«»").strip())
    return "\n".join(result)

def sanitize_input_text(text):
    if not text:
        return text
    replacements = {
        "کشتار": "درگیری", "کشتن": "متوقف کردن", "مرگ": "پایان", "مرده": "بی‌حرکت",
        "خون": "مایع قرمز", "خونی": "قرمز", "مواد مخدر": "مواد", "مخدر": "ماده",
        "تجاوز": "تخطی", "اسلحه": "ابزار", "تفنگ": "ابزار", "بمب": "وسیله",
        "انفجار": "صدا", "جنگ": "درگیری", "خودکشی": "آسیب به خود",
        "قتل": "درگیری", "دزدی": "برداشتن", "فحش": "کلام نامناسب",
        "kill": "stop", "murder": "incident", "death": "end", "dead": "still",
        "blood": "red liquid", "drug": "substance", "gun": "tool", "weapon": "tool",
        "bomb": "device", "war": "conflict", "suicide": "self-harm", "hate": "dislike",
    }
    sanitized = text
    for word, replacement in replacements.items():
        if re.search(r"[A-Za-z]", word):
            sanitized = re.sub(rf"\b{re.escape(word)}\b", replacement, sanitized, flags=re.IGNORECASE)
        else:
            sanitized = sanitized.replace(word, replacement)
    return sanitized

def detect_strategy(text):
    lines = [x.strip() for x in clean_text(text).splitlines() if x.strip()]
    if not lines:
        return "line"
    dashes = sum(x.startswith(("-", "—", "–")) for x in lines)
    if len(lines) >= 4 and dashes >= len(lines) * 0.5:
        return "dash"
    if text.count("\n\n") >= 2:
        return "stanza"
    if len(lines) >= 4 and sum(map(len, lines)) / len(lines) < 70:
        return "couplet"
    return "line"

def format_multispeaker(raw, strategy, spk1, spk2, separator="---", mapping="", n_lines=2):
    if strategy == "mapping":
        pairs = {}
        for pair in mapping.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                pairs[k.strip()] = v.strip()
        out = []
        for line in clean_text(raw).splitlines():
            if not line.strip():
                continue
            normalized = line.replace("：", ":")
            if ":" in normalized:
                prefix, txt = normalized.split(":", 1)
                target = pairs.get(prefix.strip(), "1")
                out.append(f"{spk1 if target in ('1', spk1) else spk2}: {txt.strip()}")
            else:
                out.append(f"{spk1}: {line.strip()}")
        return "\n".join(out)
    if strategy == "separator":
        if not separator:
            return ""
        parts = [p.strip() for p in raw.split(separator) if p.strip()]
        out = []
        for i, part in enumerate(parts):
            who = spk1 if i % 2 == 0 else spk2
            out.extend(f"{who}: {line}" for line in clean_text(part).splitlines() if line.strip())
        return "\n".join(out)
    cleaned = clean_text(raw)
    lines = [x.strip() for x in cleaned.splitlines() if x.strip()]
    if strategy == "stanza":
        stanzas, cur = [], []
        for line in cleaned.splitlines():
            if line.strip():
                cur.append(line.strip())
            elif cur:
                stanzas.append(cur)
                cur = []
        if cur:
            stanzas.append(cur)
        return "\n".join(
            f"{spk1 if i % 2 == 0 else spk2}: {line}"
            for i, stanza in enumerate(stanzas) for line in stanza
        )
    out = []
    for i, line in enumerate(lines):
        if strategy == "dash":
            has_dash = line.startswith(("-", "—", "–"))
            spoken = line.lstrip("-—–").strip() if has_dash else line
            out.append(f"{spk1 if has_dash else spk2}: {spoken}")
        elif strategy == "couplet":
            out.append(f"{spk1 if (i // 2) % 2 == 0 else spk2}: {line}")
        elif strategy == "n_lines":
            n = max(1, int(n_lines))
            out.append(f"{spk1 if (i // n) % 2 == 0 else spk2}: {line}")
        else:
            out.append(f"{spk1 if i % 2 == 0 else spk2}: {line}")
    return "\n".join(out)

def split_text_safely(text, max_chars=3500):
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    chunks, current = [], ""
    units = re.split(r"(?<=[.!?؟。])\s+|\n", text)
    for unit in units:
        unit = unit.strip()
        if not unit:
            continue
        while len(unit) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            cut = unit.rfind(" ", 0, max_chars)
            if cut < max_chars // 2:
                cut = max_chars
            chunks.append(unit[:cut].strip())
            unit = unit[cut:].strip()
        candidate = f"{current}\n{unit}".strip() if current else unit
        if len(candidate) > max_chars and current:
            chunks.append(current.strip())
            current = unit
        else:
            current = candidate
    if current:
        chunks.append(current.strip())
    return chunks

def split_multispeaker_lines(text, max_chars=3500):
    lines = [line for line in text.splitlines() if line.strip()]
    chunks, current = [], ""
    for line in lines:
        if len(line) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line)
            continue
        candidate = f"{current}\n{line}".strip() if current else line
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text.strip()]

def build_client(api_key):
    return genai.Client(api_key=api_key)

def is_retriable(exc):
    msg = str(exc).lower()
    tokens = ("429", "quota", "rate limit", "rate_limit", "timeout", "timed out", "temporarily", "500", "502", "503", "504")
    return any(token in msg for token in tokens)

def safety_rejected(exc):
    msg = str(exc).lower()
    if "safety_setting" in msg or "safety_settings" in msg:
        return True
    return "safety" in msg and any(k in msg for k in ("extra", "unknown", "unexpected", "forbidden", "invalid", "validation"))

def create_with_retry(client, **kwargs):
    last_exc = None
    dropped_safety = False
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return client.interactions.create(**kwargs)
        except Exception as exc:
            last_exc = exc
            if not dropped_safety and safety_rejected(exc):
                kwargs.pop("safety_settings", None)
                dropped_safety = True
                continue
            if attempt == RETRY_ATTEMPTS - 1 or not is_retriable(exc):
                raise
            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
    raise last_exc

def generate_text_with_retry(client, model, prompt):
    last_exc = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return client.models.generate_content(
                model=model,
                contents=prompt,
                config={"safety_settings": TEXT_SAFETY_SETTINGS},
            )
        except TypeError:
            return client.models.generate_content(model=model, contents=prompt)
        except Exception as exc:
            last_exc = exc
            if safety_rejected(exc):
                try:
                    return client.models.generate_content(model=model, contents=prompt)
                except Exception as inner:
                    last_exc = inner
            if attempt == RETRY_ATTEMPTS - 1 or not is_retriable(exc):
                raise last_exc
            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
    raise last_exc

def build_single_input(text, voice, style):
    content_item = {"type": "text", "text": text}
    style = (style or "").strip()
    if style:
        content_item["annotations"] = [{"type": "speech_metadata", "style": style}]
    return [{"type": "user_input", "content": [content_item]}], [{"voice": voice}]

def build_multi_input(text, spk1, spk2, voice1, voice2, style1, style2):
    blocks = []
    for line in text.splitlines():
        if not line.strip():
            continue
        speaker, content = parse_speaker_line(line, spk1, spk2)
        if not content:
            continue
        style = style1 if speaker == spk1 else style2
        annotation = {"type": "speech_metadata", "speaker": speaker}
        if (style or "").strip():
            annotation["style"] = style.strip()
        blocks.append({"type": "text", "text": content, "annotations": [annotation]})
    if not blocks:
        raise ValueError("هیچ خط معتبری پیدا نشد. هر خط باید «نام: متن» باشد و نام‌ها با تنظیمات یکی باشند.")
    config = {
        "speakers": [
            {"speaker": spk1, "voice": voice1},
            {"speaker": spk2, "voice": voice2},
        ]
    }
    return [{"type": "user_input", "content": blocks}], config

def response_format_for(stream, mime_type, sample_rate):
    rate = int(sample_rate or 24000)
    if stream and rate == 24000:
        return {"type": "audio"}
    if stream:
        return {"type": "audio", "mime_type": "audio/l16", "sample_rate": rate}
    fmt = {"type": "audio", "mime_type": mime_type}
    if rate != 24000:
        fmt["sample_rate"] = rate
    return fmt

def raw_to_wav(raw, mime_type, sample_rate):
    rate = int(sample_rate or 24000)
    if raw.startswith(b"RIFF"):
        return raw
    if mime_type == "audio/mulaw":
        return pcm_to_wav_bytes(mulaw_to_pcm16(raw), rate=rate)
    if mime_type == "audio/alaw":
        return pcm_to_wav_bytes(alaw_to_pcm16(raw), rate=rate)
    return pcm_to_wav_bytes(raw, rate=rate)

def generate_audio(client, model, input_blocks, speech_config, stream, mime_type, sample_rate):
    started = time.time()
    fmt = response_format_for(stream, mime_type, sample_rate)
    rate = int(sample_rate or 24000)
    kwargs = {
        "model": model,
        "input": input_blocks,
        "response_format": fmt,
        "generation_config": {"speech_config": speech_config},
        "safety_settings": INTERACTION_SAFETY_SETTINGS,
    }
    if stream:
        kwargs["stream"] = True
        last_exc = None
        dropped_safety = False
        for attempt in range(RETRY_ATTEMPTS):
            try:
                response = client.interactions.create(**kwargs)
                chunks = []
                for event in response:
                    event_type = getattr(event, "event_type", None)
                    if event_type in ("error", "interaction.error"):
                        raise RuntimeError(f"خطای استریم: {getattr(event, 'error', event)}")
                    if event_type == "step.delta":
                        delta = getattr(event, "delta", None)
                        if getattr(delta, "type", None) == "audio" and getattr(delta, "data", None):
                            chunks.append(decode_b64(delta.data))
                raw = b"".join(chunks)
                if not raw:
                    raise RuntimeError("استریم تمام شد اما داده صوتی نیامد.")
                return raw_to_wav(raw, "audio/l16", rate), raw, time.time() - started
