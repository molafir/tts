# -*- coding: utf-8 -*-
"""Gemini TTS Balochi Studio — نسخه یکپارچه
تمرکز: دکلمه، سرودن و تحلیل شعر بلوچی + تمام صداها + ارسال خودکار تلگرام
"""
import base64, io, json, os, re, time, traceback, wave
import requests
import streamlit as st
from google import genai

st.set_page_config(page_title="Gemini TTS Balochi Studio", page_icon="🎙️", layout="wide")

RTL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600&display=swap');
html, body, [class*="st-"], p, h1, h2, h3, h4, h5, h6, label { font-family: 'Vazirmatn','Tahoma',sans-serif; }
.material-symbols-rounded, .material-icons, [data-testid="stIconMaterial"],
span[class*="material-symbols"] { font-family: 'Material Symbols Rounded' !important; direction: ltr !important; font-feature-settings: 'liga' !important; }
textarea, .stTextArea textarea, .stTextInput input { direction: rtl; text-align: right; }
.stButton > button { white-space: normal; height: auto; line-height: 1.35; }
@media (max-width: 700px) {
  div[data-testid="stHorizontalBlock"] > div[data-testid="column"] { flex: 1 1 48% !important; width: 48% !important; }
}
</style>
"""
st.markdown(RTL_CSS, unsafe_allow_html=True)
st.title("🎙️ Gemini TTS Balochi Studio")
st.caption("دکلمه، سرودن و تحلیل شعر بلوچی با Gemini 3.8 · همه صداها · ارسال خودکار به تلگرام")

# ============ Constants ============

ALL_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]
VOICE_DESCRIPTIONS = {
    "Zephyr": "روشن و متین", "Puck": "جوان و پرانرژی", "Charon": "کهن و آگاه",
    "Kore": "آرام و شمرده", "Fenrir": "بم و حماسی", "Leda": "جوان و نازک",
    "Orus": "قوی و مصمم", "Aoede": "نرم و شاعرانه", "Callirrhoe": "آسان‌گیر",
    "Autonoe": "روشن", "Enceladus": "نفس‌گیر", "Iapetus": "شفاف",
    "Umbriel": "ملایم", "Algieba": "صاف", "Despina": "نرم",
    "Erinome": "پاک", "Algenib": "شنی و خشن", "Rasalgethi": "آموزنده",
    "Laomedeia": "شاد", "Achernar": "نرم", "Alnilam": "محکم",
    "Schedar": "یکنواخت", "Gacrux": "بالغ", "Pulcherrima": "پیشرو",
    "Achird": "دوستانه", "Zubenelgenubi": "غیررسمی", "Vindemiatrix": "ملایم",
    "Sadachbia": "سرزنده", "Sadaltager": "آگاه", "Sulafat": "گرم",
}

# توصیه‌های صدای بلوچی — این صداها در لیست بالای انتخابگر می‌آیند
VOICE_BALOCHI_HINTS = {
    "Fenrir": "شاهری، باصلابت، طنین سینه، دلاورانه",
    "Charon": "پیر دانا، راوی کهن تاریخ بلوچستان",
    "Puck": "جوان پرشور، شتابان و پرانرژی",
    "Aoede": "بانوی نغمه‌خوان مکرانی، سوزناک و شاعرانه",
    "Kore": "آرام، نرم، شمرده — مناسب آموزش و غزل",
    "Zephyr": "متین و رادیویی، گوینده رسمی",
}
SORTED_VOICES = list(VOICE_BALOCHI_HINTS.keys()) + [v for v in ALL_VOICES if v not in VOICE_BALOCHI_HINTS]

def format_voice(v):
    if v in VOICE_BALOCHI_HINTS:
        return f"🎭 {v} — {VOICE_BALOCHI_HINTS[v]}"
    return f"{v} — {VOICE_DESCRIPTIONS.get(v, '')}"

MODELS_TTS = {
    "Flash (کیفیت بالاتر، بلوچی پیشنهادی)": "gemini-3.8-flash-tts",
    "Lite (سریع‌تر و ارزان‌تر)": "gemini-3.8-flash-lite-tts",
}
TEXT_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro"]

MIME_TYPES = {
    "WAV (پیشنهادی)": "audio/wav",
    "PCM خطی L16": "audio/l16",
    "mu-law": "audio/mulaw",
    "A-law": "audio/alaw",
}
RAW_EXT = {"audio/l16": "pcm", "audio/mulaw": "mulaw", "audio/alaw": "alaw"}
SAMPLE_RATES = [24000, 16000, 8000]
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 1.5
HISTORY_LIMIT = 8

# سبک‌های عمومی
GENERAL_STYLES = {
    "— (پیش‌فرض)": "",
    "گرم و مشتاق": "warm and enthusiastic, clear pacing",
    "آرام و عمیق": "calm and deep, steady pacing",
    "دوستانه و صمیمی": "friendly and gentle, approachable",
    "هیجان‌زده و پرانرژی": "excited and energetic",
    "غمگین و آهسته": "sad and slow",
    "گوینده خبر": "professional news anchor, formal tone",
    "نجوا و مرموز": "whispering, mysterious",
    "طنز و کنایه": "sarcastic, playful",
    "سریع و هیجانی": "speaking rapidly, excited",
}

# سبک‌های بلوچی — این‌ها را حفظ می‌کنیم
BALOCHI_STYLES = {
    "بدون سبک بلوچی (فقط متن)": "",
    "دکلمه حماسی شاهری": "Passionate, heroic Balochi master poet declaiming with majestic cadence, rolling r, and rhythmic dignity",
    "زهیروک و سوزناک": "Sorrowful, deeply emotional Balochi zahirok lamentation style, melodic pauses, soulful breathing",
    "نغمگی و لِیکو": "Rhythmic, melodious Balochi liko chanting with musical cadence and flowing prosody",
    "شمرده و آموزشی": "Articulate, slow educational native Balochi reciter, precise vowels and retroflex consonants",
    "نجوای آرام و شبانه": "Gentle, lyrical nocturnal Balochi poetry recitation with warm intimate tones and smooth transitions",
    "گفت‌وگوی نمایشی": "Dramatic dialogue, sharp responsive theatrical delivery with dynamic emotional shifts",
    "سرود شادی و جشن": "Uplifting, joyous Balochi festive chant celebrating courage, unity, and bright dawn",
}

# انتخابگر یکپارچه سبک (عمومی + بلوچی)
ALL_STYLES = {**GENERAL_STYLES}
for name, prompt in BALOCHI_STYLES.items():
    key = f"🎭 {name}" if prompt else name
    ALL_STYLES[key] = prompt

SAFETY_INTERACTIONS = [
    {"type": "harassment", "threshold": "off"},
    {"type": "hate_speech", "threshold": "off"},
    {"type": "sexually_explicit", "threshold": "off"},
    {"type": "dangerous_content", "threshold": "off"},
]
SAFETY_TEXT = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "OFF"},
]

INLINE_TAGS = ["<short pause>", "<long pause>", "<laugh>", "<sigh>", "<breath>", "<whispers>"]

# ============ Utilities ============

def get_secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

def decode_b64(v):
    if not v: return b""
    if isinstance(v, (bytes, bytearray)): return bytes(v)
    return base64.b64decode(v)

def pcm_to_wav_bytes(pcm, rate=24000, channels=1, sample_width=2):
    if len(pcm) % 2: pcm = pcm[:-1]
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(channels); wf.setsampwidth(sample_width)
        wf.setframerate(int(rate)); wf.writeframes(pcm)
    return out.getvalue()

def join_wavs(blobs):
    if not blobs: raise ValueError("هیچ قطعه‌ای برای اتصال نیست")
    params, frames = None, []
    for blob in blobs:
        with wave.open(io.BytesIO(blob), "rb") as wf:
            p = (wf.getnchannels(), wf.getsampwidth(), wf.getframerate())
            if params is None: params = p
            elif params != p: raise ValueError("WAV نامنطبق")
            frames.append(wf.readframes(wf.getnframes()))
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(params[0]); wf.setsampwidth(params[1])
        wf.setframerate(params[2]); wf.writeframes(b"".join(frames))
    return out.getvalue()

def mulaw_to_pcm16(data):
    out = bytearray()
    for v in data:
        u = (~v) & 0xFF
        t = (((u & 0x0F) << 3) + 0x84) << ((u & 0x70) >> 4)
        s = 0x84 - t if (u & 0x80) else t - 0x84
        out.extend(int(max(-32768, min(32767, s))).to_bytes(2, "little", signed=True))
    return bytes(out)

def alaw_to_pcm16(data):
    out = bytearray()
    for v in data:
        a = v ^ 0x55
        t = (a & 0x0F) << 4
        seg = (a & 0x70) >> 4
        if seg == 0: t += 8
        elif seg == 1: t += 0x108
        else: t += 0x108; t <<= seg - 1
        s = t if (a & 0x80) else -t
        out.extend(int(s).to_bytes(2, "little", signed=True))
    return bytes(out)

def raw_to_wav(raw, mime_type, sample_rate):
    rate = int(sample_rate or 24000)
    if raw.startswith(b"RIFF"): return raw
    if mime_type == "audio/mulaw": return pcm_to_wav_bytes(mulaw_to_pcm16(raw), rate=rate)
    if mime_type == "audio/alaw": return pcm_to_wav_bytes(alaw_to_pcm16(raw), rate=rate)
    return pcm_to_wav_bytes(raw, rate=rate)

def is_retriable(exc):
    m = str(exc).lower()
    return any(t in m for t in ("429", "quota", "rate limit", "timeout", "500", "502", "503", "504", "temporarily"))

def safety_rejected(exc):
    m = str(exc).lower()
    if "safety_setting" in m or "safety_settings" in m: return True
    return "safety" in m and any(k in m for k in ("extra", "unknown", "forbidden", "invalid", "validation"))

# ============ Multispeaker parsing ============

def parse_speaker_line(line, spk1, spk2):
    line = line.strip()
    if not line: return None, None
    norm = line.replace("：", ":").replace("﹕", ":")
    if ":" in norm:
        p, t = norm.split(":", 1)
        p, t = p.strip(), t.strip()
        if p in (spk1, spk2): return p, t
    return spk1, line

# ============ Core TTS ============

def build_single_input(text, voice, style):
    item = {"type": "text", "text": text}
    if (style or "").strip():
        item["annotations"] = [{"type": "speech_metadata", "style": style.strip()}]
    return [{"type": "user_input", "content": [item]}], [{"voice": voice}]

def build_multi_input(text, spk1, spk2, v1, v2, s1, s2):
    blocks = []
    for line in text.splitlines():
        if not line.strip(): continue
        spk, txt = parse_speaker_line(line, spk1, spk2)
        if not txt: continue
        style = s1 if spk == spk1 else s2
        ann = {"type": "speech_metadata", "speaker": spk}
        if (style or "").strip(): ann["style"] = style.strip()
        blocks.append({"type": "text", "text": txt, "annotations": [ann]})
    if not blocks:
        raise ValueError("هیچ خط معتبری با «نام: متن» پیدا نشد")
    return [{"type": "user_input", "content": blocks}], {
        "speakers": [{"speaker": spk1, "voice": v1}, {"speaker": spk2, "voice": v2}]
    }

def response_format_for(stream, mime_type, sample_rate):
    rate = int(sample_rate or 24000)
    if stream and rate == 24000: return {"type": "audio"}
    if stream: return {"type": "audio", "mime_type": "audio/l16", "sample_rate": rate}
    fmt = {"type": "audio", "mime_type": mime_type}
    if rate != 24000: fmt["sample_rate"] = rate
    return fmt

def generate_audio(client, model, blocks, config, stream, mime_type, sample_rate):
    """تولید یکپارچه صدا با retry و fallback ایمنی."""
    started = time.time()
    rate = int(sample_rate or 24000)
    kwargs = {
        "model": model, "input": blocks,
        "response_format": response_format_for(stream, mime_type, rate),
        "generation_config": {"speech_config": config},
        "safety_settings": SAFETY_INTERACTIONS,
    }
    if stream:
        kwargs["stream"] = True
        last, dropped = None, False
        for attempt in range(RETRY_ATTEMPTS):
            try:
                resp = client.interactions.create(**kwargs)
                chunks = []
                for ev in resp:
                    et = getattr(ev, "event_type", None)
                    if et in ("error", "interaction.error"):
                        raise RuntimeError(f"خطای استریم: {getattr(ev, 'error', ev)}")
                    if et == "step.delta":
                        d = getattr(ev, "delta", None)
                        if getattr(d, "type", None) == "audio" and getattr(d, "data", None):
                            chunks.append(decode_b64(d.data))
                raw = b"".join(chunks)
                if not raw: raise RuntimeError("استریم بدون صدا تمام شد")
                return raw_to_wav(raw, "audio/l16", rate), raw, time.time() - started
            except Exception as e:
                last = e
                if not dropped and safety_rejected(e):
                    kwargs.pop("safety_settings", None); dropped = True; continue
                if attempt == RETRY_ATTEMPTS - 1 or not is_retriable(e): raise
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
        raise last
    last, dropped = None, False
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = client.interactions.create(**kwargs)
            raw = decode_b64(getattr(getattr(resp, "output_audio", None), "data", None))
            if not raw: raise RuntimeError("API داده صوتی برنگرداند")
            return raw_to_wav(raw, mime_type, rate), raw, time.time() - started
        except Exception as e:
            last = e
            if not dropped and safety_rejected(e):
                kwargs.pop("safety_settings", None); dropped = True; continue
            if attempt == RETRY_ATTEMPTS - 1 or not is_retriable(e): raise
            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
    raise last

# ============ Telegram (auto) ============

def telegram_send(file_bytes, filename, caption=""):
    token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "تلگرام تنظیم نشده"
    url = f"https://api.telegram.org/bot{token}/sendAudio"
    try:
        r = requests.post(url,
            data={"chat_id": chat_id, "caption": caption[:1024], "title": "Gemini TTS"},
            files={"audio": (filename, io.BytesIO(file_bytes))},
            timeout=(10, 90))
        try: payload = r.json()
        except: payload = {}
        if r.ok and payload.get("ok"): return True, "ارسال شد"
        return False, payload.get("description", r.text[:300])
    except requests.RequestException as e:
        return False, f"خطای اتصال: {e}"

# ============ Balochi AI ============

def call_gemini_json(client, system_instruction, user_prompt):
    last = None
    for model in TEXT_MODELS:
        try:
            cfg = {"safety_settings": SAFETY_TEXT}
            if system_instruction:
                cfg["system_instruction"] = system_instruction
            resp = client.models.generate_content(model=model, contents=user_prompt, config=cfg)
            text = (resp.text or "").strip()
            if not text: raise ValueError("پاسخ خالی")
            m = re.search(r"\{[\s\S]*\}", text)
            return json.loads(m.group(0) if m else text)
        except Exception as e:
            last = e
            continue
    raise last

def compose_balochi_poem(client, theme, form, dialect, mood, verse_count):
    sys = (
        "You are a renowned master Balochi poet and literary scholar. "
        "Compose authentic Balochi poetry (not Persian/Urdu disguised as Balochi). "
        "Use traditional Arabic-Balochi script (letters ݔ، ۏ، ئے، ء، ڈ، ٹ، ڑ). "
        "Provide Romanized transliteration and faithful Persian translation per verse. "
        "Output strictly valid JSON."
    )
    prompt = (
        f"Compose an original Balochi poem:\n- Theme: {theme}\n- Form: {form}\n"
        f"- Dialect: {dialect}\n- Mood: {mood}\n- Couplets: {verse_count}\n\n"
        'Return JSON: {"title":"","dialect":"","verses":[{"balochi":"","transliteration":"","translation":""}],'
        '"fullBalochiText":"","explanation":"","vocabulary":[{"word":"","meaning":""}]}'
    )
    return call_gemini_json(client, sys, prompt)

def analyze_balochi_text(client, text):
    sys = (
        "You are a native Balochi literary scholar and phoneticist. "
        "Parse verse by verse: exact Romanized transliteration, Persian translation, "
        "optimized recitation script, and vocabulary. Output valid JSON."
    )
    prompt = (
        "Analyze this Balochi poetry:\n\"\"\"\n" + text.strip() + "\n\"\"\"\n\n"
        'Return JSON: {"verses":[{"balochi":"","transliteration":"","translation":""}],'
        '"optimizedRecitationText":"","phoneticGuide":"","vocabulary":[{"word":"","meaning":""}]}'
    )
    return call_gemini_json(client, sys, prompt)

def split_balochi_multispeaker(client, text):
    sys = (
        "You are an expert native Balochi theatrical director. "
        "Segment the poem for 2 distinct speakers (پیر/راوی and جوان/ورنا) for dramatic recitation. "
        "Output valid JSON."
    )
    prompt = (
        "Partition this Balochi poetry for 2 speakers:\n\"\"\"\n" + text.strip() + "\n\"\"\"\n\n"
        'Return JSON: {"speakers":[{"id":"spk1","name":"","voice":"Charon"},{"id":"spk2","name":"","voice":"Puck"}],'
        '"segments":[{"id":"seg-1","speakerId":"spk1","speakerName":"","balochiText":"",'
        '"transliteration":"","translation":"","deliveryHint":""}]}'
    )
    return call_gemini_json(client, sys, prompt)

# ============ Voice helpers ============

def sanitize_voice_prompt(p):
    if not p: return ""
    for w in ["کودک","نوجوان","بچه","نابالغ","teen","teenager","child","kid","minor"]:
        p = re.sub(re.escape(w), "", p, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", p).strip()

def voice_sample_wav(created):
    s = getattr(created, "sample_audio", None)
    if not s: return None
    raw = decode_b64(getattr(s, "data", None))
    if not raw: return None
    if raw.startswith(b"RIFF"): return raw
    return pcm_to_wav_bytes(raw)

# ============ Streamlit UI ============

# Sidebar
with st.sidebar:
    st.header("⚙️ تنظیمات")
    api_key = st.text_input("Gemini API Key", value=get_secret("GEMINI_API_KEY"), type="password")
    model_label = st.selectbox("مدل TTS", list(MODELS_TTS.keys()), index=0)
    model = MODELS_TTS[model_label]
    
    telegram_ready = bool(get_secret("TELEGRAM_BOT_TOKEN") and get_secret("TELEGRAM_CHAT_ID"))
    auto_send = st.checkbox(
        "📤 ارسال خودکار همه فایل‌ها به تلگرام",
        value=telegram_ready, disabled=not telegram_ready,
        help="هر فایل صوتی که تولید می‌شود (دکلمه، پیش‌نمایش صدا) خودکار ارسال می‌شود.",
    )
    if telegram_ready: st.success("✅ تلگرام آماده است")
    else: st.warning("تلگرام: توکن و chat id را در Secrets بگذارید")
    
    st.divider()
    st.caption("🎭 صداهای پیشنهادی بلوچی:")
    st.caption("Fenrir، Charon، Puck، Aoede، Kore، Zephyr")
    st.caption("🎨 سبک‌های بلوچی: شاهری، زهیروک، لیکو، شبانه و...")

if not api_key:
    st.info("کلید API را وارد کنید.")
    st.stop()

try:
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
except Exception as e:
    st.error(f"ساخت کلاینت ناموفق: {e}")
    st.stop()

for k, v in {
    "history": [], "single_text": "", "multi_text": "",
    "last_audio": None, "last_label": "",
    "composed_poem": None, "analysis": None, "split_result": None,
}.items():
    if k not in st.session_state: st.session_state[k] = v

# ============ Tabs ============

tab_tts, tab_balochi, tab_voices = st.tabs([
    "🎙️ تولید صدا", "📜 ابزار بلوچی", "🎨 مدیریت صدا"
])

# ---------- Tab 1: TTS ----------
with tab_tts:
    st.subheader("🎧 تولید صدا")
    
    mode = st.radio("حالت", ["تک‌گوینده", "چندگوینده"], horizontal=True, key="tts_mode")
    
    if mode == "تک‌گوینده":
        c1, c2 = st.columns([3, 2])
        with c1:
            text_input = st.text_area(
                "متن",
                key="single_text", height=280,
                placeholder="متن بلوچی یا فارسی...\nاز برچسب‌های <laugh> <sigh> <short pause> هم می‌توانید استفاده کنید.",
            )
        with c2:
            voice = st.selectbox(
                "صدا", SORTED_VOICES, index=0,
                format_func=format_voice, key="single_voice",
            )
            if voice in VOICE_BALOCHI_HINTS:
                st.caption(f"✨ {VOICE_BALOCHI_HINTS[voice]}")
            style_choice = st.selectbox("سبک بیان", list(ALL_STYLES.keys()), key="single_style")
            style = ALL_STYLES[style_choice]
        voice1, voice2 = voice, None
        speaker1, speaker2 = "Speaker A", "Speaker B"
        style1, style2 = style, ""
        tts_text = text_input
    
    else:
        c1, c2 = st.columns(2)
        with c1:
            speaker1 = st.text_input("نام گوینده ۱", value="راوی", key="spk1_name")
            voice1 = st.selectbox(
                "صدای گوینده ۱", SORTED_VOICES, index=1,
                format_func=format_voice, key="spk1_voice",
            )
            if voice1 in VOICE_BALOCHI_HINTS: st.caption(f"✨ {VOICE_BALOCHI_HINTS[voice1]}")
            style1_choice = st.selectbox("سبک گوینده ۱", list(ALL_STYLES.keys()), key="spk1_style")
            style1 = ALL_STYLES[style1_choice]
        with c2:
            speaker2 = st.text_input("نام گوینده ۲", value="جوان", key="spk2_name")
            voice2 = st.selectbox(
                "صدای گوینده ۲", SORTED_VOICES, index=2,
                format_func=format_voice, key="spk2_voice",
            )
            if voice2 in VOICE_BALOCHI_HINTS: st.caption(f"✨ {VOICE_BALOCHI_HINTS[voice2]}")
            style2_choice = st.selectbox("سبک گوینده ۲", list(ALL_STYLES.keys()), key="spk2_style")
            style2 = ALL_STYLES[style2_choice]
        
        if speaker1.strip() == speaker2.strip():
            st.warning("نام دو گوینده باید متفاوت باشد.")
        st.info(f"هر خط را با `{speaker1}:` یا `{speaker2}:` شروع کنید.")
        tts_text = st.text_area(
            "متن گفت‌وگو",
            key="multi_text", height=280,
            placeholder=f"{speaker1}: سلام، امروز چطوری؟\n{speaker2}: خوبم، ممنون.",
        )
        style = ""
    
    # Quick tags
    st.caption("افزودن برچسب:")
    text_key = "single_text" if mode == "تک‌گوینده" else "multi_text"
    tag_cols = st.columns(6)
    for i, tag in enumerate(INLINE_TAGS):
        def _append(t=tag, k=text_key):
            cur = st.session_state.get(k, "") or ""
            st.session_state[k] = (cur.rstrip() + " " + t).strip()
        tag_cols[i].button(tag, key=f"tag_{mode}_{i}", on_click=_append, use_container_width=True)
    
    # Settings
    c1, c2, c3 = st.columns(3)
    with c1:
        mime_label = st.selectbox("فرمت", list(MIME_TYPES.keys()), index=0)
        mime_type = MIME_TYPES[mime_label]
    with c2:
        sample_rate = st.selectbox("نرخ نمونه", SAMPLE_RATES, index=0, format_func=lambda r: f"{r:,} Hz")
    with c3:
        streaming = st.checkbox("استریمینگ", value=False)
    
    can_generate = bool((tts_text or "").strip())
    if mode == "چندگوینده":
        can_generate = can_generate and speaker1.strip() != speaker2.strip()
    
    if st.button("🎧 تولید و ارسال به تلگرام", type="primary", use_container_width=True, disabled=not can_generate):
        try:
            with st.spinner("در حال تولید..."):
                if mode == "تک‌گوینده":
                    blocks, config = build_single_input(tts_text.strip(), voice1, style1)
                else:
                    blocks, config = build_multi_input(
                        tts_text.strip(), speaker1, speaker2, voice1, voice2, style1, style2
                    )
                wav, raw, took = generate_audio(client, model, blocks, config, streaming, mime_type, sample_rate)
            
            st.session_state.last_audio = wav
            label = f"{mode} · {model} · {len(tts_text)} chars · {took:.1f}s"
            st.session_state.last_label = label
            st.session_state.history.insert(0, {"wav": wav, "label": label})
            st.session_state.history = st.session_state.history[:HISTORY_LIMIT]
            
            if auto_send and telegram_ready:
                with st.spinner("📤 ارسال به تلگرام..."):
                    ok, msg = telegram_send(wav, "gemini_tts.wav", label)
                st.success(f"✅ تولید شد · {'📤 ارسال شد' if ok else '⚠️ ' + msg}")
            else:
                st.success(f"✅ تولید شد: {label}")
        except Exception as e:
            st.error(f"تولید ناموفق: {e}")
            with st.expander("جزئیات فنی"):
                st.code(traceback.format_exc(), language="text")
    
    if st.session_state.last_audio:
        st.divider()
        st.audio(st.session_state.last_audio, format="audio/wav")
        st.caption(st.session_state.last_label)
        c1, c2 = st.columns(2)
        c1.download_button("⬇️ دانلود WAV", data=st.session_state.last_audio,
                           file_name="gemini_tts.wav", mime="audio/wav", use_container_width=True)
        if not auto_send and telegram_ready:
            if c2.button("📤 ارسال دستی به تلگرام", use_container_width=True):
                ok, msg = telegram_send(st.session_state.last_audio, "gemini_tts.wav", st.session_state.last_label)
                (st.success if ok else st.error)(msg)
    
    if st.session_state.history:
        with st.expander(f"📚 تاریخچه ({len(st.session_state.history)})"):
            for i, item in enumerate(st.session_state.history):
                st.caption(item["label"])
                st.audio(item["wav"], format="audio/wav")
                st.download_button("دانلود", data=item["wav"],
                                   file_name=f"history_{i}.wav", mime="audio/wav", key=f"h_{i}")

# ---------- Tab 2: Balochi tools ----------
with tab_balochi:
    st.subheader("📜 ابزار هوشمند بلوچی")
    
    sub_c, sub_a, sub_s = st.tabs(["✍️ سرودن", "🔍 تحلیل", "🎭 تقسیم دو صدایی"])
    
    # Compose
    with sub_c:
        c1, c2 = st.columns(2)
        with c1:
            theme = st.text_input("موضوع", "دلیری و غیرت بلوچ", key="cmp_t")
            form = st.selectbox("قالب", ["دوبیتی", "غزل", "رباعی", "شعر آزاد", "غزل و دوبیتی حماسی"], key="cmp_f")
        with c2:
            dialect = st.selectbox("گویش", ["مکرانی", "رخشانی", "سرحدی", "لاشاری"], key="cmp_d")
            mood = st.selectbox("حال", ["حماسی و انگیزشی", "سوزناک و عاشقانه", "امیدبخش", "حکیمانه"], key="cmp_m")
        vc = st.slider("تعداد بیت", 2, 12, 4, key="cmp_v")
        
        if st.button("✍️ سرودن", type="primary", use_container_width=True, key="cmp_go"):
            try:
                with st.spinner("در حال سرودن..."):
                    st.session_state.composed_poem = compose_balochi_poem(client, theme, form, dialect, mood, vc)
            except Exception as e:
                st.error(f"سرودن ناموفق: {e}")
        
        poem = st.session_state.composed_poem
        if poem:
            st.markdown(f"### {poem.get('title', 'شعر بلوچی')}")
            for v in poem.get("verses", []):
                st.markdown(f"**{v.get('balochi', '')}**")
                if v.get("transliteration"): st.caption(v["transliteration"])
                if v.get("translation"): st.caption(v["translation"])
            vocab = poem.get("vocabulary", [])
            if vocab:
                with st.expander("📖 واژه‌نامه"):
                    for w in vocab:
                        st.markdown(f"**{w.get('word', '')}** — {w.get('meaning', '')}")
            full = poem.get("fullBalochiText") or "\n".join(v.get("balochi", "") for v in poem.get("verses", []))
            if full.strip():
                if st.button("📥 استفاده در تک‌گوینده", type="primary", key="cmp_u1"):
                    st.session_state.single_text = full
                    st.success("به تب «تولید صدا» منتقل شد.")
                if st.button("📥 استفاده در چندگوینده", key="cmp_u2"):
                    lines = [l for l in full.splitlines() if l.strip()]
                    half = max(1, len(lines) // 2)
                    dialogue = [f"{'راوی' if i < half else 'جوان'}: {l}" for i, l in enumerate(lines)]
                    st.session_state.multi_text = "\n".join(dialogue)
                    st.success("به تب «تولید صدا» منتقل شد (راوی/جوان).")
    
    # Analyze
    with sub_a:
        at = st.text_area("متن بلوچی", height=180, key="an_t", placeholder="شعر را بچسبانید...")
        if st.button("🔍 تحلیل", type="primary", use_container_width=True, key="an_go"):
            if not at.strip(): st.error("متن را وارد کنید.")
            else:
                try:
                    with st.spinner("در حال تحلیل..."):
                        st.session_state.analysis = analyze_balochi_text(client, at)
                except Exception as e:
                    st.error(f"تحلیل ناموفق: {e}")
        
        an = st.session_state.analysis
        if an:
            for v in an.get("verses", []):
                st.markdown(f"**{v.get('balochi', '')}**")
                if v.get("transliteration"): st.caption(v["transliteration"])
                if v.get("translation"): st.caption(v["translation"])
            if an.get("phoneticGuide"):
                with st.expander("🗣️ راهنمای تلفظ"):
                    st.write(an["phoneticGuide"])
            vocab = an.get("vocabulary", [])
            if vocab:
                with st.expander("📖 واژه‌نامه"):
                    for w in vocab:
                        st.markdown(f"**{w.get('word', '')}** — {w.get('meaning', '')}")
            recit = an.get("optimizedRecitationText") or at
            if recit.strip():
                if st.button("📥 استفاده در تک‌گوینده", key="an_u"):
                    st.session_state.single_text = recit
                    st.success("به تب «تولید صدا» منتقل شد.")
    
    # Split
    with sub_s:
        stt = st.text_area("شعر برای تقسیم دو صدایی", height=180, key="sp_t", placeholder="شعر بلوچی...")
        if st.button("🎭 تقسیم", type="primary", use_container_width=True, key="sp_go"):
            if not stt.strip(): st.error("متن را وارد کنید.")
            else:
                try:
                    with st.spinner("در حال تقسیم..."):
                        st.session_state.split_result = split_balochi_multispeaker(client, stt)
                except Exception as e:
                    st.error(f"تقسیم ناموفق: {e}")
        
        sp = st.session_state.split_result
        if sp:
            segs = sp.get("segments", [])
            for seg in segs:
                name = seg.get("speakerName") or seg.get("speakerId", "?")
                st.markdown(f"**{name}:** {seg.get('balochiText', '')}")
            if segs:
                lines = []
                for seg in segs:
                    who = "راوی" if seg.get("speakerId") == "spk1" else "جوان"
                    txt = seg.get("balochiText", "")
                    if txt: lines.append(f"{who}: {txt}")
                if st.button("📥 استفاده در چندگوینده", type="primary", key="sp_u"):
                    st.session_state.multi_text = "\n".join(lines)
                    st.success("به تب «تولید صدا» منتقل شد. صداهای Charon و Puck را انتخاب کنید.")

# ---------- Tab 3: Voice management ----------
with tab_voices:
    st.subheader("🎨 مدیریت صداهای سفارشی")
    
    v1, v2, v3, v4 = st.tabs(["✨ طراحی", "🔀 بازترکیب", "👤 تکثیر", "📚 کتابخانه"])
    
    with v1:
        vn = st.text_input("نام نمایشی", value="راوی بلوچ", key="vd_n")
        vg = st.selectbox("جنسیت", ["—", "male", "female", "neutral"], key="vd_g")
        vl = st.text_input("کد زبان", value="bal", key="vd_l", help="bal برای بلوچی")
        vp = st.text_area("توضیح شخصیت", height=100, key="vd_p",
                          value="A mature Baloch male narrator with deep, resonant, heroic voice for epic Balochi poetry.")
        if st.button("✨ ساخت", type="primary", key="vd_go"):
            if not vp.strip(): st.error("توضیح را وارد کنید.")
            else:
                try:
                    with st.spinner("در حال ساخت..."):
                        payload = {
                            "model": "gemini-3.8-flash-tts", "type": "prompted",
                            "display_name": vn.strip()[:80],
                            "prompted": {"input": sanitize_voice_prompt(vp)[:2000]},
                        }
                        if vg != "—": payload["gender"] = vg
                        if vl.strip(): payload["language_code"] = vl.strip()
                        created = client.voices.create(store=True, voice=payload)
                    vid = getattr(created, "id", "") or ""
                    st.success(f"✅ ساخته شد: `{vid}`")
                    sample = voice_sample_wav(created)
                    if sample:
                        st.audio(sample, format="audio/wav")
                        if auto_send and telegram_ready:
                            ok, _ = telegram_send(sample, f"voice_{vid[:16]}.wav", f"Voice design: {vn}")
                            if ok: st.caption("📤 پیش‌نمایش به تلگرام ارسال شد")
                except Exception as e:
                    st.error(f"ساخت ناموفق: {e}")
    
    with v2:
        rb = st.text_input("صدای پایه", value="Puck", key="rm_b")
        rn = st.text_input("نام نسخه", value="نسخه بازترکیب", key="rm_n")
        rp = st.text_area("تغییرات", height=100, key="rm_p",
                          value="Make the voice older, warmer, slightly lower pitch, with a subtle Makrani accent.")
        if st.button("🔀 بازترکیب", type="primary", key="rm_go"):
            try:
                with st.spinner("در حال بازترکیب..."):
                    created = client.voices.create(store=True, voice={
                        "model": "gemini-3.8-flash-tts", "type": "prompted",
                        "display_name": rn.strip()[:80],
                        "prompted": {"base_voice": rb.strip(), "input": sanitize_voice_prompt(rp)[:2000]},
                    })
                vid = getattr(created, "id", "") or ""
                st.success(f"✅ ساخته شد: `{vid}`")
                sample = voice_sample_wav(created)
                if sample:
                    st.audio(sample, format="audio/wav")
                    if auto_send and telegram_ready:
                        telegram_send(sample, f"remix_{vid[:16]}.wav", f"Remix: {rn}")
            except Exception as e:
                st.error(f"بازترکیب ناموفق: {e}")
    
    with v3:
        st.code("I am the owner of this voice and I consent to Google using this voice to create a synthetic voice model.")
        st.caption("فایل مرجع ۱۰-۳۰ ثانیه WAV mono 16-bit 24kHz")
        rn2 = st.text_input("نام", value="صدای تکثیر", key="rp_n")
        rs = st.file_uploader("فایل مرجع", type=["wav"], key="rp_s")
        rc = st.file_uploader("فایل رضایت", type=["wav"], key="rp_c")
        store_flag = st.checkbox("ذخیره در پروژه", value=True, key="rp_store")
        if st.button("👤 تکثیر", type="primary", key="rp_go"):
            if not rs or not rc: st.error("هر دو فایل لازم است.")
            else:
                try:
                    with st.spinner("در حال تکثیر..."):
                        payload = {
                            "model": "gemini-3.8-flash-tts", "type": "replicated",
                            "replicated": {
                                "source_audio": {"mime_type": "audio/wav", "data": base64.b64encode(rs.getvalue()).decode()},
                                "consent_audio": {"mime_type": "audio/wav", "data": base64.b64encode(rc.getvalue()).decode()},
                            },
                        }
                        if store_flag: payload["display_name"] = rn2.strip()[:80]
                        created = client.voices.create(store=store_flag, voice=payload)
                    vid = getattr(created, "id", "") or ""
                    vkey = getattr(created, "key", "") or ""
                    if store_flag and vid: st.success(f"✅ ذخیره شد: `{vid}`")
                    elif vkey: st.success(f"✅ کلید ۷ روزه:"); st.code(vkey)
                except Exception as e:
                    st.error(f"تکثیر ناموفق: {e}")
    
    with v4:
        if st.button("📚 بارگذاری", key="lib_load"):
            try:
                with st.spinner("در حال دریافت..."):
                    resp = client.voices.list(type_=["prompted", "replicated"], page_size=50)
                voices = list(resp.voices or [])
                if not voices: st.info("صدایی در پروژه نیست.")
                for v in voices:
                    vid = getattr(v, "id", "")
                    name = getattr(v, "display_name", "")
                    st.code(vid, language=None)
                    if name: st.caption(name)
                    if st.button("استفاده", key=f"use_{vid}"):
                        st.session_state.single_voice = vid
                        st.success(f"در انتخاب‌گر تک‌گوینده قرار گرفت. به تب تولید صدا بروید.")
            except Exception as e:
                st.error(f"بارگذاری ناموفق: {e}")

st.divider()
st.caption("🎙️ Gemini TTS Balochi Studio · تمام صداها · ارسال خودکار تلگرام")
