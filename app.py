--- /dev/null
+++ b/gemini_tts_studio.py
@@ -0,0 +1,1387 @@
+# Gemini 3.8 TTS Studio Pro
+# هم‌تراز با راهنمای AI Studio تا ۲۸ اکتبر ۲۰۲۶ و صفحه مدل تا ۴ نوامبر ۲۰۲۶
+# سقف رسمی: ۸۱۹۲ توکن ورودی، ۱۶۳۸۴ توکن خروجی. هر دو مدل ۳.۸ یک طرح درخواست دارند.
+# pip install "google-genai>=2.25.0" streamlit requests
+# streamlit run gemini_tts_studio.py
+import base64
+import io
+import re
+import time
+import traceback
+import wave
+
+import requests
+import streamlit as st
+from google import genai
+
+st.set_page_config(page_title="Gemini TTS Studio Pro", page_icon="🎙️", layout="wide")
+
+RTL_CSS = """
+<style>
+@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600&family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
+html, body, p, h1, h2, h3, h4, h5, h6, label, .stMarkdown, .stText { font-family: 'Vazirmatn', 'Tahoma', sans-serif; }
+.material-symbols-rounded, .material-icons, [data-testid="stIconMaterial"], span[class*="material-symbols"] {
+    font-family: 'Material Symbols Rounded' !important; direction: ltr !important; font-feature-settings: 'liga' !important;
+}
+textarea, .stTextArea textarea, .stTextInput input { direction: rtl; text-align: right; font-family: 'Vazirmatn', 'Tahoma', sans-serif; }
+.stCodeBlock pre, .stCode pre { direction: rtl; text-align: right; font-size: 14px; line-height: 1.8; }
+.stButton > button { white-space: normal; height: auto; line-height: 1.35; }
+@media (max-width: 700px) {
+  div[data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
+  div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
+    flex: 1 1 48% !important;
+    width: 48% !important;
+    min-width: 48% !important;
+  }
+  .stButton > button { font-size: 0.78rem; padding: 0.4rem 0.35rem; }
+}
+</style>
+"""
+st.markdown(RTL_CSS, unsafe_allow_html=True)
+st.title("🎙️ Gemini TTS Studio Pro")
+st.caption("Gemini 3.8 · Interactions API · کتابخانه صدا، طراحی صدا، استریم و تلگرام")
+
+# ----------------------------- Constants -----------------------------
+
+SAMPLE_RATES = [24000, 16000, 8000]
+INPUT_TOKEN_LIMIT = 8192
+OUTPUT_TOKEN_LIMIT = 16384
+HISTORY_LIMIT = 8
+RETRY_ATTEMPTS = 3
+RETRY_BASE_DELAY = 1.5
+CUSTOM_TURN_LIMIT = 40
+
+ALL_VOICES = [
+    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
+    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
+    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
+    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
+    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
+]
+VOICE_DESCRIPTIONS = {
+    "Zephyr": "روشن", "Puck": "خوش‌بین", "Charon": "آموزنده", "Kore": "محکم",
+    "Fenrir": "هیجان‌انگیز", "Leda": "جوان", "Orus": "محکم", "Aoede": "ملایم",
+    "Callirrhoe": "آسان‌گیر", "Autonoe": "روشن", "Enceladus": "نفس‌گیر",
+    "Iapetus": "شفاف", "Umbriel": "آسان‌گیر", "Algieba": "صاف", "Despina": "صاف",
+    "Erinome": "پاک", "Algenib": "شنی", "Rasalgethi": "آموزنده", "Laomedeia": "خوش‌بین",
+    "Achernar": "نرم", "Alnilam": "محکم", "Schedar": "یکنواخت", "Gacrux": "بالغ",
+    "Pulcherrima": "پیشرو", "Achird": "دوستانه", "Zubenelgenubi": "غیررسمی",
+    "Vindemiatrix": "ملایم", "Sadachbia": "سرزنده", "Sadaltager": "آگاه", "Sulafat": "گرم",
+}
+MODELS = ["gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts"]
+MIME_TYPES = {
+    "WAV (پیشنهادی)": "audio/wav",
+    "PCM خطی L16": "audio/l16",
+    "mu-law تلفنی": "audio/mulaw",
+    "A-law تلفنی": "audio/alaw",
+}
+RAW_EXT = {"audio/l16": "pcm", "audio/mulaw": "mulaw", "audio/alaw": "alaw"}
+PREDEFINED_STYLES = {
+    "— (بدون سبک خاص / پیش‌فرض)": "",
+    "گرم و مشتاق (Warm and enthusiastic)": "warm and enthusiastic, clear pacing",
+    "آرام و عمیق (Calm and deep)": "calm and deep, steady pacing",
+    "دوستانه و صمیمی (Friendly and gentle)": "friendly and gentle, approachable",
+    "هیجان‌زده و پرانرژی (Excited and energetic)": "excited and energetic",
+    "غمگین و آهسته (Sad and slow)": "sad and slow",
+    "گوینده خبر رسمی (News anchor)": "professional news anchor, formal tone",
+    "نجوا و مرموز (Whispering)": "whispering, mysterious",
+    "طنز و کنایه (Sarcastic)": "sarcastic, playful",
+    "سریع و هیجانی (Fast paced)": "speaking rapidly, excited",
+    "سفارشی (Custom)": "custom",
+}
+QUICK_TAGS = [
+    "<short pause>", "<long pause>", "<laugh>", "<sigh>",
+    "<breath>", "<gasp>", "<cough>", "<whispers>",
+    "|oh hmm|", "|oh really?|", "|absolutely|", "|ok|",
+]
+
+# ★ مطابق سند اکتبر ۲۰۲۶: در Interactions API از type و threshold کوچک استفاده می‌شود.
+INTERACTION_SAFETY_SETTINGS = [
+    {"type": "harassment", "threshold": "off"},
+    {"type": "hate_speech", "threshold": "off"},
+    {"type": "sexually_explicit", "threshold": "off"},
+    {"type": "dangerous_content", "threshold": "off"},
+]
+# ★ models.generate_content هنوز ساختار قدیمی category/threshold را می‌گیرد.
+TEXT_SAFETY_SETTINGS = [
+    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "OFF"},
+    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "OFF"},
+    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "OFF"},
+    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "OFF"},
+]
+
+# ----------------------------- Utilities -----------------------------
+
+def get_secret(name, default=""):
+    try:
+        return st.secrets.get(name, default)
+    except Exception:
+        return default
+
+def decode_b64(value):
+    if not value:
+        return b""
+    if isinstance(value, (bytes, bytearray)):
+        return bytes(value)
+    return base64.b64decode(value)
+
+def pcm_to_wav_bytes(pcm, rate=24000, channels=1, sample_width=2):
+    out = io.BytesIO()
+    with wave.open(out, "wb") as wf:
+        wf.setnchannels(channels)
+        wf.setsampwidth(sample_width)
+        wf.setframerate(int(rate))
+        wf.writeframes(pcm)
+    return out.getvalue()
+
+def wav_pcm(data):
+    if not data.startswith(b"RIFF"):
+        return data, None
+    with wave.open(io.BytesIO(data), "rb") as wf:
+        return wf.readframes(wf.getnframes()), wf.getframerate()
+
+def join_wavs(wav_list):
+    frames = []
+    rate = 24000
+    width = 2
+    channels = 1
+    for blob in wav_list:
+        with wave.open(io.BytesIO(blob), "rb") as wf:
+            channels = wf.getnchannels()
+            width = wf.getsampwidth()
+            rate = wf.getframerate()
+            frames.append(wf.readframes(wf.getnframes()))
+    out = io.BytesIO()
+    with wave.open(out, "wb") as wf:
+        wf.setnchannels(channels)
+        wf.setsampwidth(width)
+        wf.setframerate(rate)
+        wf.writeframes(b"".join(frames))
+    return out.getvalue()
+
+def mulaw_to_pcm16(data):
+    out = bytearray()
+    for value in data:
+        u = (~value) & 0xFF
+        t = (((u & 0x0F) << 3) + 0x84) << ((u & 0x70) >> 4)
+        sample = 0x84 - t if (u & 0x80) else t - 0x84
+        out.extend(int(max(-32768, min(32767, sample))).to_bytes(2, "little", signed=True))
+    return bytes(out)
+
+def alaw_to_pcm16(data):
+    out = bytearray()
+    for value in data:
+        a = value ^ 0x55
+        t = (a & 0x0F) << 4
+        seg = (a & 0x70) >> 4
+        if seg == 0:
+            t += 8
+        elif seg == 1:
+            t += 0x108
+        else:
+            t += 0x108
+            t <<= seg - 1
+        sample = t if (a & 0x80) else -t
+        out.extend(int(sample).to_bytes(2, "little", signed=True))
+    return bytes(out)
+
+def estimate_tokens(text):
+    """تخمین محافظه‌کارانه. شمارش توکن روی خود مدل TTS در مستند Enterprise پشتیبانی نشده."""
+    return max(1, (len(text or "") + 1) // 2)
+
+
+def is_custom_voice(voice):
+    v = (voice or "").strip()
+    return v.startswith("voice_") or v.startswith("voicekey_")
+
+def parse_speaker_line(line, spk1, spk2):
+    line = line.strip()
+    if not line:
+        return None, None
+    normalized = line.replace("：", ":").replace("﹕", ":")
+    if ":" in normalized:
+        prefix, txt = normalized.split(":", 1)
+        prefix, txt = prefix.strip(), txt.strip()
+        if prefix in (spk1, spk2):
+            return prefix, txt
+    return spk1, line
+
+def clean_text(text):
+    result = []
+    for line in text.splitlines():
+        line = re.sub(r"^[*_\s]+", "", line)
+        line = re.sub(r"[*_\s]+$", "", line)
+        result.append(line.strip("`\"'«»").strip())
+    return "\n".join(result)
+
+def sanitize_input_text(text):
+    if not text:
+        return text
+    replacements = {
+        "کشتار": "درگیری", "کشتن": "متوقف کردن", "مرگ": "پایان", "مرده": "بی‌حرکت",
+        "خون": "مایع قرمز", "خونی": "قرمز", "مواد مخدر": "مواد", "مخدر": "ماده",
+        "تجاوز": "تخطی", "اسلحه": "ابزار", "تفنگ": "ابزار", "بمب": "وسیله",
+        "انفجار": "صدا", "جنگ": "درگیری", "خودکشی": "آسیب به خود",
+        "قتل": "درگیری", "دزدی": "برداشتن", "فحش": "کلام نامناسب",
+        "kill": "stop", "murder": "incident", "death": "end", "dead": "still",
+        "blood": "red liquid", "drug": "substance", "gun": "tool", "weapon": "tool",
+        "bomb": "device", "war": "conflict", "suicide": "self-harm", "hate": "dislike",
+    }
+    sanitized = text
+    for word, replacement in replacements.items():
+        if re.search(r"[A-Za-z]", word):
+            sanitized = re.sub(rf"\b{re.escape(word)}\b", replacement, sanitized, flags=re.IGNORECASE)
+        else:
+            sanitized = sanitized.replace(word, replacement)
+    return sanitized
+
+def detect_strategy(text):
+    lines = [x.strip() for x in clean_text(text).splitlines() if x.strip()]
+    if not lines:
+        return "line"
+    dashes = sum(x.startswith(("-", "—", "–")) for x in lines)
+    if len(lines) >= 4 and dashes >= len(lines) * 0.5:
+        return "dash"
+    if text.count("\n\n") >= 2:
+        return "stanza"
+    if len(lines) >= 4 and sum(map(len, lines)) / len(lines) < 70:
+        return "couplet"
+    return "line"
+
+def format_multispeaker(raw, strategy, spk1, spk2, separator="---", mapping="", n_lines=2):
+    if strategy == "mapping":
+        pairs = {}
+        for pair in mapping.split(","):
+            if "=" in pair:
+                k, v = pair.split("=", 1)
+                pairs[k.strip()] = v.strip()
+        out = []
+        for line in clean_text(raw).splitlines():
+            if not line.strip():
+                continue
+            normalized = line.replace("：", ":")
+            if ":" in normalized:
+                prefix, txt = normalized.split(":", 1)
+                target = pairs.get(prefix.strip(), "1")
+                out.append(f"{spk1 if target in ('1', spk1) else spk2}: {txt.strip()}")
+            else:
+                out.append(f"{spk1}: {line.strip()}")
+        return "\n".join(out)
+    if strategy == "separator":
+        if not separator:
+            return ""
+        parts = [p.strip() for p in raw.split(separator) if p.strip()]
+        out = []
+        for i, part in enumerate(parts):
+            who = spk1 if i % 2 == 0 else spk2
+            out.extend(f"{who}: {line}" for line in clean_text(part).splitlines() if line.strip())
+        return "\n".join(out)
+    cleaned = clean_text(raw)
+    lines = [x.strip() for x in cleaned.splitlines() if x.strip()]
+    if strategy == "stanza":
+        stanzas, cur = [], []
+        for line in cleaned.splitlines():
+            if line.strip():
+                cur.append(line.strip())
+            elif cur:
+                stanzas.append(cur)
+                cur = []
+        if cur:
+            stanzas.append(cur)
+        return "\n".join(
+            f"{spk1 if i % 2 == 0 else spk2}: {line}"
+            for i, stanza in enumerate(stanzas) for line in stanza
+        )
+    out = []
+    for i, line in enumerate(lines):
+        if strategy == "dash":
+            has_dash = line.startswith(("-", "—", "–"))
+            spoken = line.lstrip("-—–").strip() if has_dash else line
+            out.append(f"{spk1 if has_dash else spk2}: {spoken}")
+        elif strategy == "couplet":
+            out.append(f"{spk1 if (i // 2) % 2 == 0 else spk2}: {line}")
+        elif strategy == "n_lines":
+            n = max(1, int(n_lines))
+            out.append(f"{spk1 if (i // n) % 2 == 0 else spk2}: {line}")
+        else:
+            out.append(f"{spk1 if i % 2 == 0 else spk2}: {line}")
+    return "\n".join(out)
+
+def split_text_safely(text, max_chars=3500):
+    text = text.strip()
+    if len(text) <= max_chars:
+        return [text]
+    chunks, current = [], ""
+    units = re.split(r"(?<=[.!?؟。])\s+|\n", text)
+    for unit in units:
+        unit = unit.strip()
+        if not unit:
+            continue
+        while len(unit) > max_chars:
+            if current:
+                chunks.append(current.strip())
+                current = ""
+            cut = unit.rfind(" ", 0, max_chars)
+            if cut < max_chars // 2:
+                cut = max_chars
+            chunks.append(unit[:cut].strip())
+            unit = unit[cut:].strip()
+        candidate = f"{current}\n{unit}".strip() if current else unit
+        if len(candidate) > max_chars and current:
+            chunks.append(current.strip())
+            current = unit
+        else:
+            current = candidate
+    if current:
+        chunks.append(current.strip())
+    return chunks
+
+def split_multispeaker_lines(text, max_chars=3500):
+    lines = [line for line in text.splitlines() if line.strip()]
+    chunks, current = [], ""
+    for line in lines:
+        if len(line) > max_chars:
+            if current:
+                chunks.append(current)
+                current = ""
+            chunks.append(line)
+            continue
+        candidate = f"{current}\n{line}".strip() if current else line
+        if current and len(candidate) > max_chars:
+            chunks.append(current)
+            current = line
+        else:
+            current = candidate
+    if current:
+        chunks.append(current)
+    return chunks or [text.strip()]
+
+def build_client(api_key):
+    return genai.Client(api_key=api_key)
+
+def is_retriable(exc):
+    msg = str(exc).lower()
+    tokens = ("429", "quota", "rate limit", "rate_limit", "timeout", "timed out", "temporarily", "500", "502", "503", "504")
+    return any(token in msg for token in tokens)
+
+def safety_rejected(exc):
+    msg = str(exc).lower()
+    if "safety_setting" in msg or "safety_settings" in msg:
+        return True
+    return "safety" in msg and any(k in msg for k in ("extra", "unknown", "unexpected", "forbidden", "invalid", "validation"))
+
+def drop_mode(kwargs):
+    gen = kwargs.get("generation_config")
+    if not isinstance(gen, dict):
+        return False
+    sc = gen.get("speech_config")
+    if isinstance(sc, dict) and "mode" in sc:
+        sc.pop("mode", None)
+        return True
+    return False
+
+def create_with_retry(client, **kwargs):
+    last_exc = None
+    dropped_safety = False
+    dropped_mode = False
+    for attempt in range(RETRY_ATTEMPTS):
+        try:
+            return client.interactions.create(**kwargs)
+        except Exception as exc:
+            last_exc = exc
+            low = str(exc).lower()
+            if not dropped_safety and safety_rejected(exc):
+                kwargs.pop("safety_settings", None)
+                dropped_safety = True
+                continue
+            if not dropped_mode and ("mode" in low or "extra_forbidden" in low or "unknown field" in low):
+                if drop_mode(kwargs):
+                    dropped_mode = True
+                    continue
+            if attempt == RETRY_ATTEMPTS - 1 or not is_retriable(exc):
+                raise
+            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
+    raise last_exc
+
+def generate_text_with_retry(client, model, prompt):
+    last_exc = None
+    for attempt in range(RETRY_ATTEMPTS):
+        try:
+            return client.models.generate_content(
+                model=model,
+                contents=prompt,
+                config={"safety_settings": TEXT_SAFETY_SETTINGS},
+            )
+        except TypeError:
+            return client.models.generate_content(model=model, contents=prompt)
+        except Exception as exc:
+            last_exc = exc
+            if safety_rejected(exc):
+                try:
+                    return client.models.generate_content(model=model, contents=prompt)
+                except Exception as inner:
+                    last_exc = inner
+            if attempt == RETRY_ATTEMPTS - 1 or not is_retriable(exc):
+                raise last_exc
+            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
+    raise last_exc
+
+def build_single_input(text, voice, style):
+    content_item = {"type": "text", "text": text}
+    style = (style or "").strip()
+    if style:
+        content_item["annotations"] = [{"type": "speech_metadata", "style": style}]
+    return [{"type": "user_input", "content": [content_item]}], [{"voice": voice}]
+
+def build_multi_input(text, spk1, spk2, voice1, voice2, style1, style2, conversational=False):
+    blocks = []
+    for line in text.splitlines():
+        if not line.strip():
+            continue
+        speaker, content = parse_speaker_line(line, spk1, spk2)
+        if not content:
+            continue
+        style = style1 if speaker == spk1 else style2
+        annotation = {"type": "speech_metadata", "speaker": speaker}
+        if (style or "").strip():
+            annotation["style"] = style.strip()
+        blocks.append({"type": "text", "text": content, "annotations": [annotation]})
+    if not blocks:
+        raise ValueError("هیچ خط معتبری پیدا نشد. هر خط باید «نام: متن» باشد و نام‌ها با تنظیمات یکی باشند.")
+    config = {
+        "speakers": [
+            {"speaker": spk1, "voice": voice1},
+            {"speaker": spk2, "voice": voice2},
+        ]
+    }
+    if conversational:
+        config["mode"] = "conversational"
+    return [{"type": "user_input", "content": blocks}], config
+
+def response_format_for(stream, mime_type, sample_rate):
+    rate = int(sample_rate or 24000)
+    if stream and rate == 24000:
+        return {"type": "audio"}
+    if stream:
+        return {"type": "audio", "mime_type": "audio/l16", "sample_rate": rate}
+    fmt = {"type": "audio", "mime_type": mime_type}
+    if rate != 24000:
+        fmt["sample_rate"] = rate
+    return fmt
+
+def raw_to_wav(raw, mime_type, sample_rate):
+    rate = int(sample_rate or 24000)
+    if raw.startswith(b"RIFF"):
+        return raw
+    if mime_type == "audio/mulaw":
+        return pcm_to_wav_bytes(mulaw_to_pcm16(raw), rate=rate)
+    if mime_type == "audio/alaw":
+        return pcm_to_wav_bytes(alaw_to_pcm16(raw), rate=rate)
+    return pcm_to_wav_bytes(raw, rate=rate)
+
+def generate_audio(client, model, input_blocks, speech_config, stream, mime_type, sample_rate):
+    started = time.time()
+    fmt = response_format_for(stream, mime_type, sample_rate)
+    rate = int(sample_rate or 24000)
+    kwargs = {
+        "model": model,
+        "input": input_blocks,
+        "response_format": fmt,
+        "generation_config": {"speech_config": speech_config},
+        "safety_settings": INTERACTION_SAFETY_SETTINGS,
+    }
+    if stream:
+        kwargs["stream"] = True
+        last_exc = None
+        dropped_safety = False
+        dropped_mode = False
+        for attempt in range(RETRY_ATTEMPTS):
+            try:
+                response = client.interactions.create(**kwargs)
+                chunks = []
+                for event in response:
+                    event_type = getattr(event, "event_type", None)
+                    if event_type in ("error", "interaction.error"):
+                        raise RuntimeError(f"خطای استریم: {getattr(event, 'error', event)}")
+                    if event_type == "step.delta":
+                        delta = getattr(event, "delta", None)
+                        if getattr(delta, "type", None) == "audio" and getattr(delta, "data", None):
+                            chunks.append(decode_b64(delta.data))
+                raw = b"".join(chunks)
+                if not raw:
+                    raise RuntimeError("استریم تمام شد اما داده صوتی نیامد.")
+                return raw_to_wav(raw, "audio/l16", rate), raw, time.time() - started
+            except Exception as exc:
+                last_exc = exc
+                low = str(exc).lower()
+                if not dropped_safety and safety_rejected(exc):
+                    kwargs.pop("safety_settings", None)
+                    dropped_safety = True
+                    continue
+                if not dropped_mode and ("mode" in low or "extra_forbidden" in low or "unknown field" in low):
+                    if drop_mode(kwargs):
+                        dropped_mode = True
+                        continue
+                if attempt == RETRY_ATTEMPTS - 1 or not is_retriable(exc):
+                    raise
+                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
+        raise last_exc
+
+    try:
+        response = create_with_retry(client, **kwargs)
+    except Exception as exc:
+        msg = str(exc).lower()
+        if "content_blocked" in msg or "policy" in msg or "prohibited" in msg:
+            raise RuntimeError(
+                "متن توسط فیلتر ایمنی Gemini مسدود شد. واژه‌ها را عوض کنید یا «نرم‌سازی واژه‌ها» را روشن کنید."
+            ) from exc
+        raise
+    raw = decode_b64(getattr(getattr(response, "output_audio", None), "data", None))
+    if not raw:
+        raise RuntimeError("API پاسخی بدون داده صوتی برگرداند.")
+    return raw_to_wav(raw, mime_type, rate), raw, time.time() - started
+
+def explain_error(exc):
+    err = str(exc)
+    low = err.lower()
+    if "429" in err or "rate" in low or "quota" in low:
+        return "سقف درخواست پر شده است. کمی صبر کنید یا مدل lite را انتخاب کنید."
+    if "404" in err or "not_found" in low:
+        return "مدل یا شناسه صدا پیدا نشد. voice_ را دوباره بسازید یا نام پیش‌ساخته را چک کنید."
+    if "content_blocked" in low or "policy" in low:
+        return "فیلتر ایمنی پاسخ را بست."
+    if "extra_forbidden" in low or "unknown field" in low:
+        return "یک فیلد درخواست با این نسخه از SDK سازگار نیست. حالت conversational را خاموش کنید."
+    if "safety" in low:
+        return "تنظیمات ایمنی یا متن را تغییر دهید."
+    return "کلید API، مدل و شناسه صدا را بررسی کنید."
+
+# ----------------------------- Sample / tag callbacks -----------------------------
+
+def load_single_sample():
+    st.session_state.single_text_value = (
+        "سلام! به Gemini TTS Studio Pro خوش آمدید. <short pause> امیدوارم روز فوق‌العاده‌ای داشته باشید."
+    )
+
+def load_multi_sample():
+    spk1 = st.session_state.get("speaker_name_1", "مرد")
+    spk2 = st.session_state.get("speaker_name_2", "زن")
+    st.session_state.multi_text_value = (
+        f"{spk1}: سلام! امروز چطوری؟\n"
+        f"{spk2}: خوبم، ممنون. تو چطور؟\n"
+        f"{spk1}: عالی‌ام! <laugh> آماده‌ای شروع کنیم؟\n"
+        f"{spk2}: همیشه آماده‌ام!"
+    )
+
+def load_poem_sample():
+    spk1 = st.session_state.get("speaker_name_1", "مرد")
+    spk2 = st.session_state.get("speaker_name_2", "زن")
+    st.session_state.multi_text_value = (
+        f"{spk1}: منی دل، منی نوجوانی توئے\n"
+        f"{spk1}: منی زینت و زندگانی توئے\n"
+        f"{spk2}: گمانی، سیائے دَنز و مُجاں\n"
+        f"{spk2}: من شاداں، منی شادمانی توئے"
+    )
+
+def load_backchannel_sample():
+    spk1 = st.session_state.get("speaker_name_1", "مرد")
+    spk2 = st.session_state.get("speaker_name_2", "زن")
+    st.session_state.multi_text_value = (
+        f"{spk1}: پس انتشار چهارشنبه است |جدی؟| واقعاً آماده‌ایم؟\n"
+        f"{spk2}: |آها| فکر کنم بله. <short pause> یک بار دیگر متن را بخوانیم."
+    )
+
+def append_tag(key, tag):
+    current = st.session_state.get(key, "") or ""
+    st.session_state[key] = (current.rstrip() + " " + tag).strip()
+
+def remember_voice(voice_id):
+    st.session_state.pending_voice_id = voice_id
+
+# ----------------------------- Telegram -----------------------------
+
+def send_to_telegram(file_bytes, filename, caption="", as_document=False):
+    token = get_secret("TELEGRAM_BOT_TOKEN")
+    chat_id = get_secret("TELEGRAM_CHAT_ID")
+    if not token or not chat_id:
+        return False, "توکن یا شناسه چت تلگرام در Secrets تنظیم نشده است."
+    method = "sendDocument" if as_document else "sendAudio"
+    field = "document" if as_document else "audio"
+    url = f"https://api.telegram.org/bot{token}/{method}"
+    try:
+        response = requests.post(
+            url,
+            data={"chat_id": chat_id, "caption": caption[:1024], "title": "Gemini TTS"},
+            files={field: (filename, io.BytesIO(file_bytes))},
+            timeout=(10, 90),
+        )
+        try:
+            payload = response.json()
+        except ValueError:
+            payload = {}
+        if response.ok and payload.get("ok"):
+            return True, "فایل به تلگرام ارسال شد."
+        description = payload.get("description", response.text[:500])
+        return False, f"تلگرام خطا داد ({response.status_code}): {description}"
+    except requests.RequestException as exc:
+        return False, f"خطای اتصال به تلگرام: {exc}"
+
+# ----------------------------- Sidebar -----------------------------
+
+with st.sidebar:
+    st.header("راهنما")
+    st.markdown(
+        "**مدل‌ها**\n"
+        "- `gemini-3.8-flash-lite-tts` پیش‌فرض\n"
+        "- `gemini-3.8-flash-tts` کیفیت بالاتر"
+    )
+    st.info(
+        "تک‌بلندگو: `speech_config` آرایه است.\n\n"
+        "چندبلندگو با صدای پیش‌ساخته: شیء `speakers`.\n\n"
+        "استریم پیش‌فرض PCM خام ۲۴ کیلوهرتز است و اینجا به WAV تبدیل می‌شود."
+    )
+    st.markdown(
+        "**برچسب داخل متن** (خوانده نمی‌شود، اجرا می‌شود)\n\n"
+        "`<short pause>` `<laugh>` `<sigh>` `<breath>` `<gasp>` `<cough>`\n\n"
+        "برای متن غیرانگلیسی هم خودِ برچسب را انگلیسی بگذارید.\n\n"
+        "**واکنش شنونده** با خط عمودی، داخل همان نوبت (بهتر با مدل flash):\n\n"
+        "`|oh hmm|` `|oh really?|` `|absolutely|`"
+    )
+    st.warning(
+        "صدای `voice_` و `voicekey_` را نمی‌توان در یک درخواست چندبلندگو گذاشت. "
+        "هر نوبت جدا ساخته و بعد به هم وصل می‌شود. سقف ۲۰۰ صدای ذخیره‌شده، ماندگاری یک سال.\n\n"
+        f"سقف ورودی هر درخواست **{INPUT_TOKEN_LIMIT:,}** توکن و سقف خروجی صوتی **{OUTPUT_TOKEN_LIMIT:,}** توکن است. "
+        "مدل lite برای حجم بالا و تک‌گویی روزمره است؛ برای دیالوگ پیچیده و لهجه، flash را انتخاب کنید. "
+        "مدل‌های پیش‌نمایش ۲.۵ و ۳.۱ این طرح `speech_metadata` را ندارند."
+    )
+    if get_secret("TELEGRAM_BOT_TOKEN") and get_secret("TELEGRAM_CHAT_ID"):
+        st.success("تلگرام پیکربندی شده")
+    else:
+        st.caption("تلگرام: TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID را در Secrets بگذارید.")
+
+# ----------------------------- API key -----------------------------
+
+secret_api_key = get_secret("GEMINI_API_KEY")
+with st.expander("🔑 دسترسی API", expanded=not bool(secret_api_key)):
+    if secret_api_key:
+        st.success("کلید از Secrets خوانده می‌شود.")
+        api_key = secret_api_key
+    else:
+        api_key = st.text_input("کلید API Gemini", type="password", key="api_key_input")
+        st.caption("در میزبانی، GEMINI_API_KEY را در Secrets بگذارید. کلید از https://aistudio.google.com/apikey")
+if not api_key:
+    st.info("برای شروع، کلید API را وارد کنید.")
+    st.stop()
+try:
+    client = build_client(api_key)
+except Exception as exc:
+    st.error(f"ساخت کلاینت ناموفق بود: {exc}")
+    st.stop()
+
+# ----------------------------- Session -----------------------------
+
+for key, value in {
+    "generated_transcript": "",
+    "history": [],
+    "single_text_value": "",
+    "multi_text_value": "",
+    "formatted_preview": "",
+    "last_created_voice": None,
+    "created_voices": [],
+    "library_rows": [],
+    "library_page_token": "",
+    "pending_voice_id": "",
+    "last_result": None,
+}.items():
+    if key not in st.session_state:
+        st.session_state[key] = value
+
+# ----------------------------- Voice design -----------------------------
+
+def sanitize_voice_prompt(prompt_text):
+    if not prompt_text:
+        return ""
+    forbidden = [
+        "کودک", "نوجوان", "بچه", "نابالغ", "دختر بچه", "پسر بچه",
+        "teen", "teenager", "child", "kid", "minor", "young girl", "young boy",
+    ]
+    sanitized = prompt_text
+    for word in forbidden:
+        sanitized = re.sub(re.escape(word), "", sanitized, flags=re.IGNORECASE)
+    return re.sub(r"\s+", " ", sanitized).strip()
+
+def create_prompted_voice(client, model_name, display_name, prompt_text, gender="", language_code=""):
+    safe_prompt = sanitize_voice_prompt(prompt_text)
+    if not safe_prompt:
+        raise ValueError("بعد از پاک‌سازی، توضیح صدا خالی شد.")
+    voice_payload = {
+        "model": model_name,
+        "type": "prompted",
+        "display_name": (display_name or "Custom Voice").strip()[:80] or "Custom Voice",
+        "prompted": {"input": safe_prompt[:2000]},
+    }
+    if gender and gender != "—":
+        voice_payload["gender"] = gender
+    if language_code and language_code.strip():
+        voice_payload["language_code"] = language_code.strip()
+    try:
+        return client.voices.create(store=True, voice=voice_payload)
+    except Exception as exc:
+        if "safety" in str(exc).lower():
+            raise ValueError(
+                "توضیح صدا توسط فیلتر ایمنی بسته شد. سن و توصیف ظاهری حساس را حذف کنید."
+            ) from exc
+        raise
+
+def voice_sample_wav(created):
+    sample = getattr(created, "sample_audio", None)
+    if sample is None:
+        return None
+    raw = decode_b64(getattr(sample, "data", None))
+    if not raw:
+        return None
+    mime = (getattr(sample, "mime_type", "") or "").lower()
+    if raw.startswith(b"RIFF"):
+        return raw
+    if "mulaw" in mime:
+        return pcm_to_wav_bytes(mulaw_to_pcm16(raw))
+    if "alaw" in mime:
+        return pcm_to_wav_bytes(alaw_to_pcm16(raw))
+    return pcm_to_wav_bytes(raw)
+
+def voice_identifier(created, store=True):
+    if not store:
+        return getattr(created, "key", None) or getattr(created, "id", "") or ""
+    return getattr(created, "id", None) or getattr(created, "key", "") or ""
+
+def register_voice(created, display_name, store=True):
+    ident = voice_identifier(created, store)
+    entry = {
+        "id": ident,
+        "display_name": display_name or ident,
+        "sample": voice_sample_wav(created),
+    }
+    st.session_state.last_created_voice = entry
+    st.session_state.created_voices = [v for v in st.session_state.created_voices if v.get("id") != ident]
+    st.session_state.created_voices.insert(0, entry)
+    st.session_state.created_voices = st.session_state.created_voices[:20]
+    if ident:
+        st.session_state.pending_voice_id = ident
+    return ident
+
+CONSENT_EN = (
+    "I am the owner of this voice and I consent to Google using this voice "
+    "to create a synthetic voice model."
+)
+
+with st.expander("🎨 طراحی صدای سفارشی", expanded=False):
+    st.caption("POST voices با type=prompted و store=true. شناسه voice_ را بعداً در منبع صدای سفارشی بگذارید. سقف ۲۰۰ صدا.")
+    vd1, vd2 = st.columns(2)
+    with vd1:
+        vd_display_name = st.text_input("نام نمایشی", value="راوی گرم فارسی", key="vd_name")
+        vd_gender = st.selectbox("جنسیت", ["—", "female", "male", "neutral"], key="vd_gender")
+        vd_lang = st.text_input("کد زبان", value="fa-IR", key="vd_lang")
+    with vd2:
+        vd_model = st.selectbox("مدل ساخت", MODELS, index=0, key="vd_model")
+        st.caption("شخصیت را یک‌بار اینجا بسازید. در style گفتار، سن و لهجه را تکرار نکنید.")
+    vd_prompt = st.text_area(
+        "توضیح شخصیت",
+        height=90,
+        key="vd_prompt",
+        value="یک راوی بزرگسال با صدای گرم، آرام و واضح، مناسب پادکست.",
+    )
+    b1, b2 = st.columns(2)
+    if b1.button("ساخت صدا", type="primary", use_container_width=True, key="vd_create_btn"):
+        try:
+            with st.spinner("در حال طراحی صدا..."):
+                created = create_prompted_voice(client, vd_model, vd_display_name, vd_prompt, vd_gender, vd_lang)
+            voice_id = register_voice(created, vd_display_name, store=True)
+            st.success(f"ساخته شد: {voice_id}")
+        except Exception as exc:
+            st.error(f"ساخت صدا ناموفق بود: {exc}")
+            with st.expander("جزئیات"):
+                st.code(traceback.format_exc(), language="text")
+    if b2.button("صداهای ذخیره‌شده پروژه", use_container_width=True, key="vd_list_btn"):
+        try:
+            with st.spinner("دریافت لیست..."):
+                response = client.voices.list(type_=["prompted", "replicated"], page_size=20)
+            remote = list(response.voices or [])
+            if not remote:
+                st.info("صدای سفارشی ذخیره‌شده‌ای نیست.")
+            else:
+                for voice in remote:
+                    vid = getattr(voice, "id", "")
+                    prompted = getattr(voice, "prompted", None)
+                    base = getattr(prompted, "base_voice", "") if prompted else ""
+                    if vid and not any(x.get("id") == vid for x in st.session_state.created_voices):
+                        st.session_state.created_voices.append({
+                            "id": vid,
+                            "display_name": getattr(voice, "display_name", "") or vid,
+                            "sample": None,
+                            "base": base or "",
+                            "kind": getattr(voice, "type", "") or "",
+                        })
+                st.success(f"{len(remote)} صدا بارگذاری شد.")
+        except Exception as exc:
+            st.error(f"لیست صداها ناموفق بود. google-genai>=2.25.0 لازم است. {exc}")
+    if st.session_state.last_created_voice:
+        lv = st.session_state.last_created_voice
+        st.markdown(f"آخرین شناسه: `{lv['id']}`")
+        if lv.get("sample"):
+            st.audio(lv["sample"], format="audio/wav")
+        if st.button("استفاده از این شناسه در گفتار", key="use_last_voice"):
+            remember_voice(lv["id"])
+            st.rerun()
+
+with st.expander("بازترکیب صدا", expanded=False):
+    st.caption(
+        "همان POST voices با type=prompted، به‌اضافه prompted.base_voice. "
+        "صدای پایه عوض نمی‌شود؛ یک voice_ تازه ذخیره می‌شود. ساخت با flash است و شناسه روی هر دو مدل کار می‌کند. طرح پولی لازم است."
+    )
+    r1, r2 = st.columns(2)
+    with r1:
+        remix_base_pick = st.selectbox("صدای پایه پیش‌ساخته", ALL_VOICES, index=ALL_VOICES.index("Puck"), key="remix_base_pick")
+        remix_base_custom = st.text_input("یا شناسه پایهٔ دیگر", placeholder="voice_... یا نام کتابخانه", key="remix_base_custom")
+    with r2:
+        remix_name = st.text_input("نام نمایشی", value="نسخه بازترکیب‌شده", key="remix_name")
+        st.caption("یک یا دو ویژگی را عوض کنید: سن، زیروبم، انرژی، لهجه یا سرعت.")
+    remix_prompt = st.text_area(
+        "تغییر نسبت به صدای پایه",
+        height=80,
+        key="remix_prompt",
+        value="Make the voice slightly older, warmer, and a little lower in pitch.",
+    )
+    if st.button("ساخت نسخه تازه", type="primary", key="remix_btn"):
+        base = (remix_base_custom or "").strip() or remix_base_pick
+        instruction = sanitize_voice_prompt(remix_prompt)
+        if not instruction:
+            st.error("توضیح تغییر را بنویسید.")
+        else:
+            try:
+                with st.spinner("در حال بازترکیب..."):
+                    created = client.voices.create(
+                        store=True,
+                        voice={
+                            "model": "gemini-3.8-flash-tts",
+                            "type": "prompted",
+                            "display_name": (remix_name or "Remixed").strip()[:80],
+                            "prompted": {"base_voice": base, "input": instruction[:2000]},
+                        },
+                    )
+                ident = register_voice(created, remix_name, store=True)
+                st.success(f"نسخه تازه: {ident}")
+            except Exception as exc:
+                st.error(f"بازترکیب ناموفق بود: {exc}")
+
+with st.expander("تکثیر صدا", expanded=False):
+    st.caption(
+        "دو فایل WAV از یک گویندهٔ بزرگسال: ۱۰ تا ۳۰ ثانیه گفتار، و خواندن دقیق جملهٔ رضایت. "
+        "۲۴ کیلوهرتز، مونو، ۱۶ بیت بهتر است. طرح پولی لازم است. واترمارک SynthID روی خروجی می‌ماند."
+    )
+    st.code(CONSENT_EN, language=None)
+    st.caption("فارسی در فهرست ۳۰ زبان جملهٔ رضایت نیست. جمله باید همان متن یکی از زبان‌های سند، مثلاً انگلیسی، باشد.")
+    rep1, rep2 = st.columns(2)
+    with rep1:
+        source_file = st.file_uploader("گفتار مرجع", type=["wav"], key="rep_source")
+        consent_file = st.file_uploader("فایل رضایت", type=["wav"], key="rep_consent")
+    with rep2:
+        rep_name = st.text_input("نام نمایشی", value="گوینده تکثیرشده", key="rep_name")
+        rep_store = st.checkbox("ذخیره در پروژه (voice_)", value=True, key="rep_store", help="خاموش یعنی کلید بی‌حالت voicekey_ با عمر ۷ روز.")
+        rep_model = st.selectbox("مدل ساخت", MODELS, index=1 if len(MODELS) > 1 else 0, key="rep_model")
+    if st.button("تکثیر", type="primary", key="rep_btn"):
+        if source_file is None or consent_file is None:
+            st.error("هر دو فایل WAV لازم است.")
+        else:
+            try:
+                source_b64 = base64.b64encode(source_file.getvalue()).decode("utf-8")
+                consent_b64 = base64.b64encode(consent_file.getvalue()).decode("utf-8")
+                voice_body = {
+                    "model": rep_model,
+                    "type": "replicated",
+                    "replicated": {
+                        "source_audio": {"mime_type": "audio/wav", "data": source_b64},
+                        "consent_audio": {"mime_type": "audio/wav", "data": consent_b64},
+                    },
+                }
+                if rep_store:
+                    voice_body["display_name"] = (rep_name or "Replicated").strip()[:80]
+                with st.spinner("در حال تأیید و تکثیر..."):
+                    created = client.voices.create(store=rep_store, voice=voice_body)
+                ident = register_voice(created, rep_name, store=rep_store)
+                st.success(f"ساخته شد: {ident}")
+                if not rep_store:
+                    st.caption("این کلید ۷ روز اعتبار دارد. برای تمدید، همان دو فایل را دوباره بفرستید.")
+            except Exception as exc:
+                st.error(f"تکثیر ناموفق بود: {exc}")
+
+with st.expander("مدیریت صداهای ذخیره‌شده", expanded=False):
+    st.caption("لیست، sample_audio را برنمی‌گرداند. پیش‌نمایش با voices.get و حذف با voices.delete است.")
+    manage_id = st.text_input("شناسه voice_", key="manage_voice_id", placeholder="voice_...")
+    g1, g2, g3 = st.columns(3)
+    if g1.button("پیش‌نمایش", key="manage_get", use_container_width=True):
+        if not manage_id.strip():
+            st.error("شناسه را وارد کنید.")
+        else:
+            try:
+                info = client.voices.get(id=manage_id.strip())
+                sample = voice_sample_wav(info)
+                name = getattr(info, "display_name", "") or manage_id.strip()
+                st.session_state.managed_preview = {"id": manage_id.strip(), "name": name, "sample": sample}
+            except Exception as exc:
+                st.error(f"دریافت صدا ناموفق بود: {exc}")
+    if g2.button("استفاده در گفتار", key="manage_use", use_container_width=True):
+        if manage_id.strip():
+            remember_voice(manage_id.strip())
+            st.rerun()
+    confirm_delete = g3.checkbox("حذف", key="manage_confirm_delete")
+    if confirm_delete and st.button("حذف دائمی این صدا", key="manage_delete"):
+        if not manage_id.strip():
+            st.error("شناسه را وارد کنید.")
+        else:
+            try:
+                client.voices.delete(id=manage_id.strip())
+                st.session_state.created_voices = [
+                    v for v in st.session_state.created_voices if v.get("id") != manage_id.strip()
+                ]
+                st.success("حذف شد.")
+            except Exception as exc:
+                st.error(f"حذف ناموفق بود: {exc}")
+    preview = st.session_state.get("managed_preview")
+    if preview and preview.get("sample"):
+        st.caption(preview.get("name") or preview.get("id"))
+        st.audio(preview["sample"], format="audio/wav")
+
+with st.expander("📚 کتابخانه صدای گسترده", expanded=False):
+    st.caption("client.voices.list — فیلترها با AND و مقدارهای هر فیلتر با OR ترکیب می‌شوند.")
+    f1, f2, f3, f4 = st.columns(4)
+    with f1:
+        lib_search = st.text_input("جستجو", key="lib_search")
+    with f2:
+        lib_lang = st.text_input("زبان", value="fa-IR", key="lib_lang")
+    with f3:
+        lib_gender = st.selectbox("جنسیت", ["—", "female", "male", "neutral"], key="lib_gender")
+    with f4:
+        lib_type = st.selectbox("نوع", ["prebuilt", "prompted", "replicated"], key="lib_type")
+    f5, f6 = st.columns(2)
+    with f5:
+        lib_pitch = st.selectbox("زیروبم", ["—", "low", "medium", "high"], key="lib_pitch")
+    with f6:
+        lib_context = st.selectbox(
+            "کاربرد",
+            ["—", "Conversational", "Audiobook", "News"],
+            key="lib_context",
+        )
+    if st.button("جستجو", key="lib_search_btn"):
+        try:
+            kwargs = {"page_size": 30, "type_": [lib_type]}
+            if lib_search.strip():
+                kwargs["search"] = lib_search.strip()
+            if lib_lang.strip():
+                kwargs["language_code"] = [lib_lang.strip()]
+            if lib_gender != "—":
+                kwargs["gender"] = [lib_gender]
+            if lib_pitch != "—":
+                kwargs["pitch"] = [lib_pitch]
+            if lib_context != "—":
+                kwargs["contexts"] = [lib_context]
+            page = client.voices.list(**kwargs)
+            rows = []
+            for voice in page.voices or []:
+                rows.append({
+                    "id": getattr(voice, "id", "") or "",
+                    "name": getattr(voice, "display_name", "") or "",
+                    "language": getattr(voice, "language_code", "") or "",
+                    "accent": getattr(voice, "accent", "") or "",
+                    "gender": getattr(voice, "gender", "") or "",
+                    "pitch": getattr(voice, "pitch", "") or "",
+                })
+            st.session_state.library_rows = rows
+            st.session_state.library_page_token = getattr(page, "next_page_token", "") or ""
+        except Exception as exc:
+            st.error(f"جستجو ناموفق بود: {exc}")
+    rows = st.session_state.library_rows
+    if rows:
+        labels = [f"{r['id']} — {r['name']} ({r['language']}, {r['gender']})" for r in rows]
+        pick = st.selectbox("نتیجه", labels, key="lib_pick")
+        picked_id = rows[labels.index(pick)]["id"]
+        st.caption(picked_id)
+        if st.button("گذاشتن این شناسه در فیلد صدای سفارشی", key="use_library_voice"):
+            remember_voice(picked_id)
+            st.rerun()
+        if st.session_state.library_page_token:
+            st.caption("نتیجه بیشتر از یک صفحه است. page_size روی ۳۰ صدا است؛ جستجو را دقیق‌تر کنید.")
+
+if st.session_state.pending_voice_id:
+    vid = st.session_state.pending_voice_id
+    st.session_state.single_voice_source = "سفارشی (voice_... / voicekey_...)"
+    st.session_state.single_custom_voice = vid
+    st.session_state.voice1_source = "سفارشی"
+    st.session_state.custom_voice_1 = vid
+    st.session_state.pending_voice_id = ""
+
+# ----------------------------- Generation config -----------------------------
+
+st.header("تنظیمات تولید")
+c1, c2, c3 = st.columns(3)
+with c1:
+    mode = st.radio("حالت", ["تک‌بلندگو", "چندبلندگو"], horizontal=True)
+with c2:
+    model = st.selectbox(
+        "مدل",
+        MODELS,
+        index=0,
+        help="lite: حجم بالا و تأخیر کم. flash: وفاداری استودیویی، دیالوگ چندگوینده و لهجه. طرح درخواست هر دو یکی است.",
+    )
+    if model.endswith("lite-tts"):
+        st.caption("lite برای تولید روزمره و تک‌گویی است. دیالوگ سنگین را با flash امتحان کنید.")
+with c3:
+    streaming = st.checkbox("استریمینگ", value=False, help="تکه‌های PCM خام تا پایان جمع می‌شوند و یک WAV ساخته می‌شود.")
+
+mime_label = st.selectbox("فرمت API در حالت غیر استریم", list(MIME_TYPES), disabled=streaming)
+mime_type = MIME_TYPES[mime_label]
+sample_rate = st.selectbox(
+    "نرخ نمونه",
+    SAMPLE_RATES,
+    index=0,
+    format_func=lambda r: f"{r:,} Hz",
+    help="۲۴۰۰۰ پیش‌فرض سند است. در استریم، نرخ غیر از ۲۴۰۰۰ با mime_type برابر audio/l16 فرستاده می‌شود.",
+)
+if mime_type in ("audio/mulaw", "audio/alaw") and sample_rate != 8000:
+    st.caption("برای تلفن، mu-law و A-law معمولاً ۸۰۰۰ هرتز هستند.")
+
+# ----------------------------- Transcript -----------------------------
+
+with st.expander("تولید خودکار متن", expanded=False):
+    g1, g2, g3 = st.columns(3)
+    with g1:
+        topic = st.text_input("موضوع", "تکنولوژی و هوش مصنوعی")
+    with g2:
+        transcript_style = st.selectbox("سبک متن", ["پادکست", "مصاحبه", "گفت‌وگوی دوستانه", "بحث علمی", "داستان"])
+    with g3:
+        language = st.selectbox("زبان", ["فارسی", "بلوچی", "تشخیص خودکار"])
+    word_count = st.slider("حدود کلمه", 50, 500, 150, step=25)
+    if st.button("نوشتن با Gemini", use_container_width=True):
+        try:
+            with st.spinner("در حال نوشتن..."):
+                spk1_name = st.session_state.get("speaker_name_1", "مرد")
+                spk2_name = st.session_state.get("speaker_name_2", "زن")
+                if language == "تشخیص خودکار":
+                    lang_instruction = "اگر موضوع بلوچی است بلوچی بنویس، وگرنه فارسی روان."
+                else:
+                    lang_instruction = f"متن دقیقاً به زبان {language} باشد."
+                if mode == "تک‌بلندگو":
+                    prompt = (
+                        f"یک متن گفتاری حدود {word_count} کلمه بنویس. {lang_instruction} "
+                        f"سبک {transcript_style}، درباره «{topic}». "
+                        "فقط خود گفتار را برگردان. نام گوینده، عنوان و توضیح صحنه ننویس."
+                    )
+                else:
+                    prompt = (
+                        f"یک گفت‌وگو حدود {word_count} کلمه بنویس. {lang_instruction} "
+                        f"سبک {transcript_style}، درباره «{topic}». "
+                        f"فقط خطوط «{spk1_name}: متن» و «{spk2_name}: متن». توضیح اضافه ننویس."
+                    )
+                response = generate_text_with_retry(client, model="gemini-2.5-flash", prompt=prompt)
+                st.session_state.generated_transcript = response.text or ""
+                st.session_state.generated_preview = st.session_state.generated_transcript
+            st.success("متن آماده شد.")
+        except Exception as exc:
+            st.error(f"تولید متن ناموفق بود: {exc}")
+    if st.session_state.generated_transcript:
+        st.text_area("متن تولیدشده", key="generated_preview", height=120)
+        if st.button("بردن به ویرایشگر"):
+            target = "single_text_value" if mode == "تک‌بلندگو" else "multi_text_value"
+            st.session_state[target] = st.session_state.generated_transcript
+            st.rerun()
+
+# ----------------------------- Speakers and text -----------------------------
+
+speaker1, speaker2 = "مرد", "زن"
+voice1, voice2, style1, style2 = "Kore", "Aoede", "", ""
+selected_voice, style_single = "Kore", ""
+conversational = False
+
+def style_picker(label, key_prefix):
+    choice = st.selectbox(label, list(PREDEFINED_STYLES.keys()), key=f"{key_prefix}_choice")
+    if choice == "سفارشی (Custom)":
+        return st.text_input("سبک انگلیسی", placeholder="warm and enthusiastic", key=f"{key_prefix}_custom")
+    return PREDEFINED_STYLES[choice]
+
+if mode == "تک‌بلندگو":
+    voice_source = st.radio(
+        "منبع صدا",
+        ["پیش‌ساخته", "سفارشی (voice_... / voicekey_...)"],
+        horizontal=True,
+        key="single_voice_source",
+    )
+    v1, v2 = st.columns(2)
+    with v1:
+        if voice_source == "پیش‌ساخته":
+            selected_voice = st.selectbox(
+                "صدا",
+                ALL_VOICES,
+                index=ALL_VOICES.index("Kore"),
+                format_func=lambda v: f"{v} — {VOICE_DESCRIPTIONS.get(v, '')}",
+                key="single_prebuilt_voice",
+            )
+        else:
+            selected_voice = st.text_input(
+                "شناسه صدا",
+                placeholder="voice_... یا voicekey_... یا نام کتابخانه",
+                key="single_custom_voice",
+            ).strip()
+    with v2:
+        style_single = style_picker("سبک بیان", "single_style")
+    text_input = st.text_area("متن", key="single_text_value", height=220, placeholder="متن را اینجا بنویسید. نام گوینده نگذارید.")
+else:
+    v1, v2 = st.columns(2)
+    with v1:
+        speaker1 = st.text_input("نام گوینده ۱", "مرد", key="speaker_name_1")
+        voice1_source = st.radio("منبع صدای ۱", ["پیش‌ساخته", "سفارشی"], horizontal=True, key="voice1_source")
+        if voice1_source == "پیش‌ساخته":
+            voice1 = st.selectbox(
+                "صدای ۱", ALL_VOICES, index=ALL_VOICES.index("Kore"),
+                format_func=lambda v: f"{v} — {VOICE_DESCRIPTIONS.get(v, '')}", key="voice_1",
+            )
+        else:
+            voice1 = st.text_input("شناسه صدای ۱", placeholder="voice_...", key="custom_voice_1").strip()
+        style1 = style_picker("سبک ۱", "style_1")
+    with v2:
+        speaker2 = st.text_input("نام گوینده ۲", "زن", key="speaker_name_2")
+        voice2_source = st.radio("منبع صدای ۲", ["پیش‌ساخته", "سفارشی"], horizontal=True, key="voice2_source")
+        if voice2_source == "پیش‌ساخته":
+            voice2 = st.selectbox(
+                "صدای ۲", ALL_VOICES, index=ALL_VOICES.index("Aoede"),
+                format_func=lambda v: f"{v} — {VOICE_DESCRIPTIONS.get(v, '')}", key="voice_2",
+            )
+        else:
+            voice2 = st.text_input("شناسه صدای ۲", placeholder="voice_...", key="custom_voice_2").strip()
+        style2 = style_picker("سبک ۲", "style_2")
+    if not speaker1.strip() or not speaker2.strip() or speaker1.strip() == speaker2.strip():
+        st.warning("نام دو گوینده باید پر و متفاوت باشد. نام‌ها خوانده نمی‌شوند.")
+    split_needed = is_custom_voice(voice1) or is_custom_voice(voice2)
+    if split_needed:
+        st.info("حداقل یک صدا سفارشی است. نوبت‌ها جدا با audio/l16 ساخته و به یک WAV وصل می‌شوند.")
+    else:
+        conversational = st.checkbox(
+            "افزودن mode: conversational",
+            value=False,
+            help="نمونه رسمی پایتون فقط speakers را می‌فرستد. این گزینه فیلد REST را هم اضافه می‌کند.",
+        )
+    with st.expander("قالب‌بندی شعر و دیالوگ", expanded=False):
+        raw = st.text_area("متن خام", height=140, key="raw_multi")
+        strategy_label = st.selectbox(
+            "روش",
+            ["تشخیص خودکار", "خط به خط", "بیت به بیت (هر دو خط)", "بند به بند", "خط تیره", "تعداد خط در هر نوبت", "نگاشت نام گوینده", "جداکننده سفارشی"],
+        )
+        sep, mapping, n_lines = "---", f"{speaker1}=1, {speaker2}=2", 2
+        if strategy_label == "جداکننده سفارشی":
+            sep = st.text_input("جداکننده", "---")
+        if strategy_label == "نگاشت نام گوینده":
+            mapping = st.text_input("نگاشت", mapping)
+        if strategy_label == "تعداد خط در هر نوبت":
+            n_lines = st.number_input("تعداد خط", min_value=1, max_value=20, value=2)
+        if st.button("پیش‌نمایش", use_container_width=True):
+            strategies = {
+                "تشخیص خودکار": detect_strategy(raw),
+                "خط به خط": "line",
+                "بیت به بیت (هر دو خط)": "couplet",
+                "بند به بند": "stanza",
+                "خط تیره": "dash",
+                "تعداد خط در هر نوبت": "n_lines",
+                "نگاشت نام گوینده": "mapping",
+                "جداکننده سفارشی": "separator",
+            }
+            st.session_state.formatted_preview = format_multispeaker(
+                raw, strategies[strategy_label], speaker1, speaker2, sep, mapping, n_lines
+            )
+        if st.session_state.formatted_preview:
+            st.code(st.session_state.formatted_preview, language=None)
+            if st.button("اعمال در متن نهایی", type="primary"):
+                st.session_state.multi_text_value = st.session_state.formatted_preview
+                st.rerun()
+    text_input = st.text_area(
+        "متن نهایی",
+        key="multi_text_value",
+        height=260,
+        placeholder=f"{speaker1}: سلام\n{speaker2}: سلام",
+        help="نام قبل از دونقطه فقط برچسب است و داخل text API نمی‌رود.",
+    )
+
+text_key = "single_text_value" if mode == "تک‌بلندگو" else "multi_text_value"
+st.caption("افزودن برچسب به انتهای متن. در موبایل دکمه‌ها دو ستونه می‌شکنند.")
+tag_cols = st.columns(4)
+for i, tag in enumerate(QUICK_TAGS):
+    tag_cols[i % 4].button(tag, key=f"tagbtn_{mode}_{i}", on_click=append_tag, args=(text_key, tag), use_container_width=True)
+
+st.subheader("نمونه")
+s1, s2, s3, s4 = st.columns(4)
+s1.button("تک‌گوینده", use_container_width=True, on_click=load_single_sample)
+s2.button("گفت‌وگو", use_container_width=True, on_click=load_multi_sample)
+s3.button("شعر", use_container_width=True, on_click=load_poem_sample)
+s4.button("واکنش شنونده", use_container_width=True, on_click=load_backchannel_sample)
+
+# ----------------------------- Validate -----------------------------
+
+with st.expander("متن طولانی و نرم‌سازی", expanded=False):
+    soften = st.checkbox("جایگزینی واژه‌های حساس قبل از ارسال", value=False, help="اگر روشن باشد، متنِ خوانده‌شده با نسخه سندِ کلمه‌به‌کلمه فرق می‌کند.")
+    chunk_long_text = st.checkbox("تقسیم متن طولانی به چند درخواست", value=False)
+    chunk_size = st.slider("سقف کاراکتر هر بخش", 1000, 6000, 3500, 250, disabled=not chunk_long_text)
+text_input = text_input or ""
+token_est = estimate_tokens(text_input)
+st.caption(f"{len(text_input):,} کاراکتر · تخمین محافظه‌کارانه {token_est:,} از {INPUT_TOKEN_LIMIT:,} توکن ورودی")
+if not text_input.strip():
+    st.info("متن را وارد کنید.")
+elif token_est > INPUT_TOKEN_LIMIT and not chunk_long_text:
+    st.warning("احتمالاً از سقف ۸۱۹۲ توکن ورودی رد می‌شود. تقسیم متن را روشن کنید یا متن را کوتاه کنید.")
+elif len(text_input) > 18000 and not chunk_long_text:
+    st.warning("متن خیلی بلند است. تقسیم را روشن کنید یا کوتاه‌ترش کنید.")
+
+multi_valid = bool(speaker1.strip() and speaker2.strip() and speaker1.strip() != speaker2.strip())
+voice_valid = bool(str(selected_voice).strip()) if mode == "تک‌بلندگو" else bool(str(voice1).strip() and str(voice2).strip())
+can_generate = (
+    bool(text_input.strip())
+    and voice_valid
+    and (mode != "چندبلندگو" or multi_valid)
+    and (token_est <= INPUT_TOKEN_LIMIT or chunk_long_text)
+)
+if text_input.strip() and not voice_valid:
+    st.warning("صدا را انتخاب یا شناسه را وارد کنید.")
+
+split_custom = mode == "چندبلندگو" and (is_custom_voice(voice1) or is_custom_voice(voice2))
+preview_blocks, preview_config = None, None
+preview_error = ""
+try:
+    if text_input.strip() and voice_valid and mode == "تک‌بلندگو":
+        preview_blocks, preview_config = build_single_input(text_input.strip()[:500], selected_voice, style_single)
+    elif text_input.strip() and voice_valid and multi_valid and not split_custom:
+        preview_blocks, preview_config = build_multi_input(
+            "\n".join(text_input.splitlines()[:4]), speaker1, speaker2, voice1, voice2, style1, style2, conversational
+        )
+except ValueError as exc:
+    preview_error = str(exc)
+
+with st.expander("شکل درخواست، مطابق سند", expanded=False):
+    if split_custom:
+        st.write("هر خط یک درخواست تک‌بلندگو با `audio/l16` است و PCMها به هم وصل می‌شوند.")
+    elif preview_error:
+        st.warning(preview_error)
+    elif preview_blocks is not None:
+        st.json({
+            "model": model,
+            "input": preview_blocks,
+            "response_format": response_format_for(streaming, mime_type, sample_rate),
+            "generation_config": {"speech_config": preview_config},
+            "stream": streaming,
+        })
+    else:
+        st.caption("بعد از وارد کردن متن، بدنه درخواست اینجا دیده می‌شود.")
+
+telegram_ready = bool(get_secret("TELEGRAM_BOT_TOKEN") and get_secret("TELEGRAM_CHAT_ID"))
+send_telegram = st.checkbox("بعد از تولید به تلگرام بفرست", value=False, disabled=not telegram_ready)
+
+# ----------------------------- Generate -----------------------------
+
+if st.button("🎧 تولید صدا", type="primary", use_container_width=True, disabled=not can_generate):
+    try:
+        sent = sanitize_input_text(text_input) if soften else text_input
+        if sent != text_input:
+            st.warning("برخی واژه‌ها قبل از ارسال جایگزین شدند.")
+            with st.expander("متن ارسال‌شده"):
+                st.text(sent)
+
+        jobs = []
+        if split_custom:
+            for line in sent.splitlines():
+                if not line.strip():
+                    continue
+                spk, content = parse_speaker_line(line, speaker1, speaker2)
+                if not content:
+                    continue
+                voice = voice1 if spk == speaker1 else voice2
+                style = style1 if spk == speaker1 else style2
+                blocks, config = build_single_input(content, voice, style)
+                jobs.append((blocks, config, False, "audio/l16"))
+            if not jobs:
+                raise ValueError("نوبت معتبری برای چسباندن پیدا نشد.")
+            if len(jobs) > CUSTOM_TURN_LIMIT:
+                raise ValueError(f"برای صدای سفارشی حداکثر {CUSTOM_TURN_LIMIT} نوبت در هر بار. متن را کوتاه کنید.")
+        else:
+            if chunk_long_text:
+                chunks = split_multispeaker_lines(sent, int(chunk_size)) if mode == "چندبلندگو" else split_text_safely(sent, int(chunk_size))
+            else:
+                chunks = [sent.strip()]
+            for chunk in chunks:
+                if mode == "تک‌بلندگو":
+                    blocks, config = build_single_input(chunk, selected_voice, style_single)
+                else:
+                    blocks, config = build_multi_input(
+                        chunk, speaker1, speaker2, voice1, voice2, style1, style2, conversational
+                    )
+                jobs.append((blocks, config, streaming, mime_type))
+
+        progress = st.progress(0, text="شروع")
+        wav_parts = []
+        raw_parts = []
+        elapsed = 0.0
+        for i, (blocks, config, stream_flag, job_mime) in enumerate(jobs):
+            progress.progress(i / len(jobs), text=f"بخش {i + 1} از {len(jobs)}")
+            wav_data, raw, took = generate_audio(
+                client, model, blocks, config, stream_flag, job_mime, sample_rate
+            )
+            wav_parts.append(wav_data)
+            raw_parts.append(raw)
+            elapsed += took
+        progress.progress(1.0, text="آماده")
+        merged = wav_parts[0] if len(wav_parts) == 1 else join_wavs(wav_parts)
+        label = f"{mode} · {model} · {sample_rate} Hz · {len(sent)} کاراکتر · {elapsed:.1f}s"
+        st.session_state.last_result = {
+            "wav": merged,
+            "raw": b"".join(raw_parts) if len(raw_parts) == 1 else None,
+            "raw_mime": jobs[0][3] if len(jobs) == 1 and not streaming else None,
+            "label": label,
+            "sent": sent,
+        }
+        st.session_state.history.insert(0, {"wav": merged, "label": label})
+        st.session_state.history = st.session_state.history[:HISTORY_LIMIT]
+        if send_telegram:
+            ok, msg = send_to_telegram(merged, "gemini-tts.wav", label)
+            (st.success if ok else st.error)(msg)
+    except Exception as exc:
+        st.error(f"{exc}")
+        st.info(explain_error(exc))
+        with st.expander("جزئیات فنی"):
+            st.code(traceback.format_exc(), language="text")
+
+result = st.session_state.last_result
+if result and result.get("wav"):
+    st.success("صدا آماده است.")
+    st.audio(result["wav"], format="audio/wav")
+    d1, d2 = st.columns(2)
+    d1.download_button("دانلود WAV", data=result["wav"], file_name="gemini-tts.wav", mime="audio/wav", use_container_width=True)
+    raw_mime = result.get("raw_mime")
+    if result.get("raw") and raw_mime in RAW_EXT:
+        d2.download_button(
+            f"دانلود {RAW_EXT[raw_mime]}",
+            data=result["raw"],
+            file_name=f"gemini-tts.{RAW_EXT[raw_mime]}",
+            mime="application/octet-stream",
+            use_container_width=True,
+        )
+    st.caption(result["label"])
+    if telegram_ready and st.button("ارسال همین فایل به تلگرام"):
+        ok, msg = send_to_telegram(result["wav"], "gemini-tts.wav", result["label"])
+        (st.success if ok else st.error)(msg)
+
+if st.session_state.history:
+    st.subheader("تاریخچه این نشست")
+    for i, item in enumerate(st.session_state.history):
+        st.caption(item["label"])
+        st.audio(item["wav"], format="audio/wav")
+        st.download_button(
+            "دانلود",
+            data=item["wav"],
+            file_name=f"gemini-tts-{i + 1}.wav",
+            mime="audio/wav",
+            key=f"hist_dl_{i}",
+        )
@@ -1,8 +1,14 @@
     return bytes(out)
 
 def estimate_tokens(text):
-    """تخمین محافظه‌کارانه. شمارش توکن روی خود مدل TTS در مستند Enterprise پشتیبانی نشده."""
-    return max(1, (len(text or "") + 1) // 2)
+    """تخمین رو به بالا (محافظه‌کارانه) برای هشدار سقف توکن ورودی."""
+    s = text or ""
+    if not s:
+        return 1
+    non_ascii = sum(1 for ch in s if ord(ch) > 127)
+    ascii_len = len(s) - non_ascii
+    # لاتین ≈ ۴ کاراکتر/توکن (اینجا ۳ برای احتیاط)، غیرلاتین (فارسی و…) ≈ ۱ کاراکتر/توکن
+    return max(1, ascii_len // 3 + non_ascii)
 
 
 def is_custom_voice(voice):
@@ -1,34 +1,18 @@
         return True
     return "safety" in msg and any(k in msg for k in ("extra", "unknown", "unexpected", "forbidden", "invalid", "validation"))
 
-def drop_mode(kwargs):
-    gen = kwargs.get("generation_config")
-    if not isinstance(gen, dict):
-        return False
-    sc = gen.get("speech_config")
-    if isinstance(sc, dict) and "mode" in sc:
-        sc.pop("mode", None)
-        return True
-    return False
-
 def create_with_retry(client, **kwargs):
     last_exc = None
     dropped_safety = False
-    dropped_mode = False
     for attempt in range(RETRY_ATTEMPTS):
         try:
             return client.interactions.create(**kwargs)
         except Exception as exc:
             last_exc = exc
-            low = str(exc).lower()
             if not dropped_safety and safety_rejected(exc):
                 kwargs.pop("safety_settings", None)
                 dropped_safety = True
                 continue
-            if not dropped_mode and ("mode" in low or "extra_forbidden" in low or "unknown field" in low):
-                if drop_mode(kwargs):
-                    dropped_mode = True
-                    continue
             if attempt == RETRY_ATTEMPTS - 1 or not is_retriable(exc):
                 raise
             time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
@@ -1,7 +1,7 @@
         content_item["annotations"] = [{"type": "speech_metadata", "style": style}]
     return [{"type": "user_input", "content": [content_item]}], [{"voice": voice}]
 
-def build_multi_input(text, spk1, spk2, voice1, voice2, style1, style2, conversational=False):
+def build_multi_input(text, spk1, spk2, voice1, voice2, style1, style2):
     blocks = []
     for line in text.splitlines():
         if not line.strip():
@@ -1,8 +1,6 @@
             {"speaker": spk2, "voice": voice2},
         ]
     }
-    if conversational:
-        config["mode"] = "conversational"
     return [{"type": "user_input", "content": blocks}], config
 
 def response_format_for(stream, mime_type, sample_rate):
@@ -1,7 +1,6 @@
         kwargs["stream"] = True
         last_exc = None
         dropped_safety = False
-        dropped_mode = False
         for attempt in range(RETRY_ATTEMPTS):
             try:
                 response = client.interactions.create(**kwargs)
@@ -1,15 +1,10 @@
                 return raw_to_wav(raw, "audio/l16", rate), raw, time.time() - started
             except Exception as exc:
                 last_exc = exc
-                low = str(exc).lower()
                 if not dropped_safety and safety_rejected(exc):
                     kwargs.pop("safety_settings", None)
                     dropped_safety = True
                     continue
-                if not dropped_mode and ("mode" in low or "extra_forbidden" in low or "unknown field" in low):
-                    if drop_mode(kwargs):
-                        dropped_mode = True
-                        continue
                 if attempt == RETRY_ATTEMPTS - 1 or not is_retriable(exc):
                     raise
                 time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
@@ -1,7 +1,7 @@
     if "content_blocked" in low or "policy" in low:
         return "فیلتر ایمنی پاسخ را بست."
     if "extra_forbidden" in low or "unknown field" in low:
-        return "یک فیلد درخواست با این نسخه از SDK سازگار نیست. حالت conversational را خاموش کنید."
+        return "یک فیلد درخواست با این نسخه از SDK سازگار نیست."
     if "safety" in low:
         return "تنظیمات ایمنی یا متن را تغییر دهید."
     return "کلید API، مدل و شناسه صدا را بررسی کنید."
@@ -1,7 +1,6 @@
 speaker1, speaker2 = "مرد", "زن"
 voice1, voice2, style1, style2 = "Kore", "Aoede", "", ""
 selected_voice, style_single = "Kore", ""
-conversational = False
 
 def style_picker(label, key_prefix):
     choice = st.selectbox(label, list(PREDEFINED_STYLES.keys()), key=f"{key_prefix}_choice")
@@ -1,12 +1,6 @@
     split_needed = is_custom_voice(voice1) or is_custom_voice(voice2)
     if split_needed:
         st.info("حداقل یک صدا سفارشی است. نوبت‌ها جدا با audio/l16 ساخته و به یک WAV وصل می‌شوند.")
-    else:
-        conversational = st.checkbox(
-            "افزودن mode: conversational",
-            value=False,
-            help="نمونه رسمی پایتون فقط speakers را می‌فرستد. این گزینه فیلد REST را هم اضافه می‌کند.",
-        )
     with st.expander("قالب‌بندی شعر و دیالوگ", expanded=False):
         raw = st.text_area("متن خام", height=140, key="raw_multi")
         strategy_label = st.selectbox(
@@ -1,7 +1,7 @@
         preview_blocks, preview_config = build_single_input(text_input.strip()[:500], selected_voice, style_single)
     elif text_input.strip() and voice_valid and multi_valid and not split_custom:
         preview_blocks, preview_config = build_multi_input(
-            "\n".join(text_input.splitlines()[:4]), speaker1, speaker2, voice1, voice2, style1, style2, conversational
+            "\n".join(text_input.splitlines()[:4]), speaker1, speaker2, voice1, voice2, style1, style2
         )
 except ValueError as exc:
     preview_error = str(exc)
@@ -1,7 +1,7 @@
                     blocks, config = build_single_input(chunk, selected_voice, style_single)
                 else:
                     blocks, config = build_multi_input(
-                        chunk, speaker1, speaker2, voice1, voice2, style1, style2, conversational
+                        chunk, speaker1, speaker2, voice1, voice2, style1, style2
                     )
                 jobs.append((blocks, config, streaming, mime_type))
 
