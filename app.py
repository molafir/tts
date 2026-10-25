import base64
import io
import re
import time
import traceback
import wave

import requests
import streamlit as st
from google import genai

# Gemini 3.8 TTS Studio Pro — نسخه پایدار (اصلاح باگ آیکون‌ها)
# Requires: streamlit, google-genai>=2.25.0, requests

st.set_page_config(page_title="Gemini TTS Studio Pro", page_icon="🎙️", layout="wide")

# ---------------------------------------------------------
# اصلاح CSS: جلوگیری از خرابی آیکون‌ها و راست‌چین کردن متن
# ---------------------------------------------------------
RTL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');

/* اعمال فونت فارسی فقط روی متن‌ها (نه کلاس‌های st- که آیکون‌ها را خراب می‌کند) */
html, body, p, h1, h2, h3, h4, h5, h6, label, .stMarkdown, .stText {
    font-family: 'Vazirmatn', 'Tahoma', sans-serif;
}

/* استثنا کردن فونت آیکون‌های Streamlit */
.material-symbols-rounded,
.material-icons,
[data-testid="stIconMaterial"],
span[class*="material-symbols"] {
    font-family: 'Material Symbols Rounded' !important;
    direction: ltr !important;
    font-feature-settings: 'liga' !important;
}

/* راست‌چین کردن کادرهای متن */
textarea, .stTextArea textarea, .stTextInput input {
    direction: rtl;
    text-align: right;
    font-family: 'Vazirmatn', 'Tahoma', sans-serif;
}

/* راست‌چین کردن بلوک‌های کد */
.stCodeBlock pre, .stCode pre {
    direction: rtl;
    text-align: right;
    font-size: 14px;
    line-height: 1.8;
}
</style>
"""
st.markdown(RTL_CSS, unsafe_allow_html=True)

st.title("🎙️ Gemini TTS Studio Pro")
st.caption("نسخه پایدار · تولید صدا، گفت‌وگوی دوگوینده، استریمینگ، تاریخچه و تلگرام")

# ----------------------------- Constants -----------------------------

SAMPLE_RATES = [24000, 16000, 8000]
STREAM_SAMPLE_RATE = 24000      # استریم طبق مستندات همیشه L16/24kHz است
HISTORY_LIMIT = 10
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 1.5

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
MODELS = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]
MIME_TYPES = {
    "WAV (پیشنهادی)": "audio/wav",
    "PCM خطی L16": "audio/l16",
    "mu-law تلفنی": "audio/mulaw",
    "A-law تلفنی": "audio/alaw",
}

# ----------------------------- Utilities -----------------------------

def get_secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def decode_b64(value):
    if not value:
        return b""
    return base64.b64decode(value)


def pcm_to_wav_bytes(pcm, rate=24000, channels=1, sample_width=2):
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return out.getvalue()


def mulaw_to_pcm16(data):
    out = bytearray()
    for value in data:
        u = (~value) & 0xFF
        t = (((u & 0x0F) << 3) + 0x84) << ((u & 0x70) >> 4)
        sample = 0x84 - t if (u & 0x80) else t - 0x84
        out.extend(int(sample).to_bytes(2, "little", signed=True))
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
            out.append(f"{spk1 if has_dash else spk2}: {line.lstrip('-—–').strip() if has_dash else line}")
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
    retriable_tokens = ("429", "quota", "rate limit", "rate_limit",
                        "timeout", "timed out", "temporarily",
                        "500", "502", "503", "504")
    return any(token in msg for token in retriable_tokens)


def create_with_retry(client, **kwargs):
    last_exc = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return client.interactions.create(**kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt == RETRY_ATTEMPTS - 1 or not is_retriable(exc):
                raise
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
        style = (style1 if speaker == spk1 else style2) or ""
        annotation = {"type": "speech_metadata", "speaker": speaker}
        if style.strip():
            annotation["style"] = style.strip()
        blocks.append({"type": "text", "text": content, "annotations": [annotation]})
    if not blocks:
        raise ValueError("هیچ خط معتبری برای تولید صدا پیدا نشد. برچسب گوینده و متن را بررسی کنید.")
    return [{"type": "user_input", "content": blocks}], {
        "speakers": [{"speaker": spk1, "voice": voice1}, {"speaker": spk2, "voice": voice2}]
    }


# ----------------------------- TTS Engine -----------------------------

def generate_audio(client, model, input_blocks, speech_config, stream, mime_type, sample_rate):
    started = time.time()

    if stream:
        response = client.interactions.create(
            model=model, input=input_blocks,
            response_format={"type": "audio"},
            generation_config={"speech_config": speech_config},
            stream=True,
        )
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
            raise RuntimeError("استریم پایان یافت اما داده صوتی دریافت نشد.")
        return pcm_to_wav_bytes(raw, rate=STREAM_SAMPLE_RATE), "wav", time.time() - started, len(raw)

    response_format = {"type": "audio", "mime_type": mime_type}
    if sample_rate:
        response_format["sample_rate"] = int(sample_rate)

    response = create_with_retry(
        client,
        model=model, input=input_blocks,
        response_format=response_format,
        generation_config={"speech_config": speech_config},
    )
    raw = decode_b64(getattr(getattr(response, "output_audio", None), "data", None))
    if not raw:
        raise RuntimeError("API پاسخی بدون داده صوتی برگرداند.")

    if mime_type == "audio/wav":
        return raw, "wav", time.time() - started, len(raw)
    if mime_type == "audio/l16":
        return pcm_to_wav_bytes(raw, rate=sample_rate), "wav", time.time() - started, len(raw)
    if mime_type == "audio/mulaw":
        pcm = mulaw_to_pcm16(raw)
        return pcm_to_wav_bytes(pcm, rate=sample_rate), "wav", time.time() - started, len(raw)
    if mime_type == "audio/alaw":
        pcm = alaw_to_pcm16(raw)
        return pcm_to_wav_bytes(pcm, rate=sample_rate), "wav", time.time() - started, len(raw)
    raise ValueError(f"فرمت خروجی پشتیبانی نمی‌شود: {mime_type}")


# ----------------------------- Sample loaders -----------------------------

def load_single_sample():
    st.session_state.single_text_value = (
        "سلام! به Gemini TTS Studio Pro خوش آمدید. <short pause> امیدوارم روز فوق‌العاده‌ای داشته باشید."
    )


def load_multi_sample():
    spk1 = st.session_state.get("speaker_name_1", "مرد")
    spk2 = st.session_state.get("speaker_name_2", "زن")
    st.session_state.multi_text_value = (
        f"{spk1}: سلام! امروز چطوری؟\n"
        f"{spk2}: خوبم، ممنون. تو چطور؟\n"
        f"{spk1}: عالی‌ام! <laugh> آماده‌ای شروع کنیم؟\n"
        f"{spk2}: همیشه آماده‌ام!"
    )


def load_poem_sample():
    spk1 = st.session_state.get("speaker_name_1", "مرد")
    spk2 = st.session_state.get("speaker_name_2", "زن")
    st.session_state.multi_text_value = (
        f"{spk1}: منی دل، منی نوجوانی توئے\n"
        f"{spk1}: منی زینت و زندگانی توئے\n"
        f"{spk2}: گمانی، سیائے دَنز و مُجاں\n"
        f"{spk2}: من شاداں، منی شادمانی توئے"
    )


# ----------------------------- Telegram -----------------------------

def send_to_telegram(file_bytes, filename, caption="", as_document=False):
    token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "توکن یا شناسه چت تلگرام در Secrets تنظیم نشده است."
    method = "sendDocument" if as_document else "sendAudio"
    field = "document" if as_document else "audio"
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        response = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption[:1024], "title": "Gemini TTS"},
            files={field: (filename, io.BytesIO(file_bytes))},
            timeout=(10, 90),
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.ok and payload.get("ok"):
            return True, "فایل با موفقیت به تلگرام ارسال شد."
        description = payload.get("description", response.text[:500])
        return False, f"تلگرام پاسخ خطا داد ({response.status_code}): {description}"
    except requests.RequestException as exc:
        return False, f"خطای اتصال به تلگرام: {exc}"


# ----------------------------- Sidebar -----------------------------

with st.sidebar:
    st.header("⚙️ تنظیمات و راهنما")
    st.markdown("**مدل‌ها**\n- `gemini-3.8-flash-tts`\n- `gemini-3.8-flash-lite-tts`")
    st.info("استریم به‌صورت L16 خام 24kHz دریافت و در پایان به WAV تبدیل می‌شود.")
    st.markdown("**برچسب‌های درون متن**\n`<short pause>` · `<long pause>` · `<laugh>` · `<sigh>` · `<breath>` · `<whisper>`")
    st.caption("SDK: google-genai >= 2.25.0")
    if get_secret("TELEGRAM_BOT_TOKEN") and get_secret("TELEGRAM_CHAT_ID"):
        st.success("تلگرام: پیکربندی شده")
    else:
        st.warning("تلگرام: Secrets تنظیم نشده")

# ----------------------------- API Key -----------------------------

secret_api_key = get_secret("GEMINI_API_KEY")
with st.expander("🔑 دسترسی API", expanded=not bool(secret_api_key)):
    if secret_api_key:
        st.success("کلید Gemini از Secrets خوانده می‌شود.")
        api_key = secret_api_key
    else:
        api_key = st.text_input("کلید API Gemini", type="password", key="api_key_input")
        st.caption("در محیط میزبانی، GEMINI_API_KEY را در Secrets تنظیم کنید.")
if not api_key:
    st.info("برای شروع، کلید API را وارد کنید یا GEMINI_API_KEY را در Secrets تنظیم کنید.")
    st.stop()
try:
    client = build_client(api_key)
except Exception as exc:
    st.error(f"ساخت کلاینت Gemini ناموفق بود: {exc}")
    st.stop()

# ----------------------------- Session state -----------------------------

if "generated_transcript" not in st.session_state:
    st.session_state.generated_transcript = ""
if "history" not in st.session_state:
    st.session_state.history = []
if "single_text_value" not in st.session_state:
    st.session_state.single_text_value = ""
if "multi_text_value" not in st.session_state:
    st.session_state.multi_text_value = ""
if "formatted_preview" not in st.session_state:
    st.session_state.formatted_preview = ""

# ----------------------------- Generation config -----------------------------

st.header("⚙️ تنظیمات تولید")
c1, c2, c3 = st.columns(3)
with c1:
    mode = st.radio("حالت تولید", ["تک‌بلندگو", "چندبلندگو"], horizontal=True)
with c2:
    model = st.selectbox("مدل TTS", MODELS, index=0)
with c3:
    streaming = st.checkbox("استریمینگ", value=False, help="در استریم، نرخ نمونه همیشه 24kHz است.")

mime_label = st.selectbox("فرمت درخواستی API", list(MIME_TYPES), disabled=streaming)
mime_type = MIME_TYPES[mime_label]

if streaming:
    sample_rate = STREAM_SAMPLE_RATE
    st.caption(f"🔒 استریم: نرخ نمونه ثابت {STREAM_SAMPLE_RATE:,} Hz (طبق مستندات).")
else:
    sample_rate = st.selectbox("نرخ نمونه", SAMPLE_RATES, index=0,
                               format_func=lambda r: f"{r:,} Hz")

# ----------------------------- Transcript generator -----------------------------

with st.expander("🪄 تولید خودکار متن/گفت‌وگو", expanded=False):
    g1, g2, g3 = st.columns(3)
    with g1:
        topic = st.text_input("موضوع", "تکنولوژی و هوش مصنوعی")
    with g2:
        transcript_style = st.selectbox("سبک", ["پادکست", "مصاحبه", "گفت‌وگوی دوستانه", "بحث علمی", "داستان"])
    with g3:
        word_count = st.slider("حدود کلمه", 50, 500, 150, step=25)
    if st.button("تولید متن با Gemini", use_container_width=True):
        try:
            with st.spinner("در حال نوشتن متن..."):
                prompt = (
                    f"یک متن گفت‌وگوی حدود {word_count} کلمه‌ای به فارسی، سبک {transcript_style}، "
                    f"دربارهٔ «{topic}» بنویس. فقط خطوط گفت‌وگو را با قالب دقیق «گوینده ۱: متن» و "
                    "«گوینده ۲: متن» برگردان؛ توضیح اضافی ننویس."
                )
                response = create_with_retry(
                    client, model="gemini-2.5-flash", contents=prompt
                )
                st.session_state.generated_transcript = response.text or ""
            st.success("متن آماده شد.")
        except Exception as exc:
            st.error(f"تولید متن ناموفق بود: {exc}")
    if st.session_state.generated_transcript:
        st.text_area("متن تولیدشده", key="generated_preview",
                     value=st.session_state.generated_transcript, height=120)
        if st.button("استفاده از متن تولیدشده"):
            if mode == "تک‌بلندگو":
                st.session_state.single_text_value = st.session_state.generated_transcript
            else:
                st.session_state.multi_text_value = st.session_state.generated_transcript
            st.rerun()

# ----------------------------- Speaker & text editor -----------------------------

speaker1, speaker2 = "گوینده ۱", "گوینده ۲"
voice1, voice2, style1, style2 = "Kore", "Aoede", "", ""
selected_voice, style_single = "Kore", ""

if mode == "تک‌بلندگو":
    v1, v2 = st.columns(2)
    with v1:
        selected_voice = st.selectbox(
            "صدای گوینده", ALL_VOICES, index=ALL_VOICES.index("Kore"),
            format_func=lambda v: f"{v} — {VOICE_DESCRIPTIONS.get(v, '')}",
        )
    with v2:
        style_single = st.text_input("سبک بیان", placeholder="warm and enthusiastic, clear pacing")
    text_input = st.text_area("متن برای خواندن", key="single_text_value", height=240,
                              placeholder="متن را اینجا وارد کنید...")
else:
    v1, v2 = st.columns(2)
    with v1:
        speaker1 = st.text_input("نام گوینده ۱", "مرد", key="speaker_name_1")
        voice1 = st.selectbox(
            "صدای گوینده ۱", ALL_VOICES, index=ALL_VOICES.index("Kore"),
            format_func=lambda v: f"{v} — {VOICE_DESCRIPTIONS.get(v, '')}", key="voice_1",
        )
        style1 = st.text_input("سبک گوینده ۱", placeholder="calm and deep", key="style_1")
    with v2:
        speaker2 = st.text_input("نام گوینده ۲", "زن", key="speaker_name_2")
        voice2 = st.selectbox(
            "صدای گوینده ۲", ALL_VOICES, index=ALL_VOICES.index("Aoede"),
            format_func=lambda v: f"{v} — {VOICE_DESCRIPTIONS.get(v, '')}", key="voice_2",
        )
        style2 = st.text_input("سبک گوینده ۲", placeholder="warm and gentle", key="style_2")

    if not speaker1.strip() or not speaker2.strip() or speaker1.strip() == speaker2.strip():
        st.warning("نام دو گوینده باید غیرخالی و متفاوت باشد.")

    with st.expander("🧩 قالب‌بندی خودکار شعر و دیالوگ", expanded=False):
        raw = st.text_area("متن خام", height=150, key="raw_multi",
                           placeholder="هر خط یک جمله یا مصراع؛ می‌توانید بندها را با خط خالی جدا کنید.")
        strategy_label = st.selectbox("روش تقسیم", [
            "تشخیص خودکار", "خط به خط", "بیت به بیت (هر دو خط)", "بند به بند",
            "خط تیره", "تعداد خط در هر نوبت", "نگاشت نام گوینده", "جداکننده سفارشی",
        ])
        sep, mapping, n_lines = "---", f"{speaker1}=1, {speaker2}=2", 2
        if strategy_label == "جداکننده سفارشی":
            sep = st.text_input("جداکننده", "---")
        if strategy_label == "نگاشت نام گوینده":
            mapping = st.text_input("نگاشت نام=شماره", mapping)
        if strategy_label == "تعداد خط در هر نوبت":
            n_lines = st.number_input("تعداد خط", min_value=1, max_value=20, value=2)
        if st.button("پیش‌نمایش قالب‌بندی", use_container_width=True):
            strategies = {
                "تشخیص خودکار": detect_strategy(raw),
                "خط به خط": "line",
                "بیت به بیت (هر دو خط)": "couplet",
                "بند به بند": "stanza",
                "خط تیره": "dash",
                "تعداد خط در هر نوبت": "n_lines",
                "نگاشت نام گوینده": "mapping",
                "جداکننده سفارشی": "separator",
            }
            st.session_state.formatted_preview = format_multispeaker(
                raw, strategies[strategy_label], speaker1, speaker2, sep, mapping, n_lines
            )
        if st.session_state.formatted_preview:
            st.code(st.session_state.formatted_preview, language=None)
            if st.button("اعمال متن قالب‌بندی‌شده", type="primary"):
                st.session_state.multi_text_value = st.session_state.formatted_preview
                st.rerun()

    text_input = st.text_area(
        "متن نهایی چندگوینده", key="multi_text_value", height=280,
        placeholder=f"{speaker1}: سلام\n{speaker2}: سلام، حالت چطور است؟",
    )

# ----------------------------- Samples -----------------------------

st.subheader("🎭 نمونه‌های آماده")
s1, s2, s3 = st.columns(3)
with s1:
    st.button("نمونه تک‌گوینده", use_container_width=True, on_click=load_single_sample)
with s2:
    st.button("نمونه گفت‌وگو", use_container_width=True, on_click=load_multi_sample)
with s3:
    st.button("نمونه شعر", use_container_width=True, on_click=load_poem_sample)

# ----------------------------- Chunking & Validation -----------------------------

with st.expander("📏 کنترل متن و تقسیم متن طولانی", expanded=False):
    chunk_long_text = st.checkbox("متن طولانی را به چند درخواست تقسیم کن", value=False)
    chunk_size = st.slider("حد تقریبی کاراکتر در هر بخش",
                           min_value=1000, max_value=6000, value=3500, step=250,
                           disabled=not chunk_long_text)
    st.caption("تقسیم متن، مصرف سهمیه را افزایش می‌دهد و پیوستگی لحن بین بخش‌ها تضمین نمی‌شود.")

text_input = text_input or ""
st.caption(f"تعداد کاراکترها: {len(text_input):,}")

if len(text_input.strip()) == 0:
    st.info("متن را وارد کنید تا امکان تولید صدا فعال شود.")
elif len(text_input) > 18000 and not chunk_long_text:
    st.warning("متن بسیار طولانی است؛ تقسیم متن را فعال کنید یا متن را کوتاه‌تر کنید.")

multi_valid = (speaker1.strip() and speaker2.strip() and speaker1.strip() != speaker2.strip())
can_generate = (
    bool(text_input.strip())
    and (mode != "چندبلندگو" or multi_valid)
    and (len(text_input) <= 18000 or chunk_long_text)
)

# ----------------------------- Generate -----------------------------

if st.button("🎧 تولید صدا", type="primary", use_container_width=True, disabled=not can_generate):
    try:
        if chunk_long_text:
            if mode == "چندبلندگو":
                chunks = split_multispeaker_lines(text_input, int(chunk_size))
            else:
                chunks = split_text_safely(text_input, int(chunk_size))
        else:
            chunks = [text_input.strip()]

        all_wav = []
        started_all = time.time()
        progress = st.progress(0, text="آماده‌سازی درخواست...")

        for i, chunk in enumerate(chunks):
            progress.progress(i / len(chunks), text=f"تولید بخش {i+1} از {len(chunks)}...")
            if mode == "تک‌بلندگو":
                input_blocks, speech_config = build_single_input(chunk, selected_voice, style_single)
            else:
                input_blocks, speech_config = build_multi_input(
                    chunk, speaker1, speaker2, voice1, voice2, style1, style2
                )

            wav_data, ext, elapsed, raw_size = generate_audio(
                client, model, input_blocks, speech_config, streaming, mime_type, sample_rate
            )

            with wave.open(io.BytesIO(wav_data), "rb") as wf:
                params = wf.getparams()
                pcm = wf.readframes(wf.getnframes())

            if all_wav and params[:3] != all_wav[0][0][:3]:
                raise RuntimeError(
                    "پارامترهای صوتی بخش‌ها یکسان نیستند "
                    f"({params[:3]} != {all_wav[0][0][:3]})؛ اتصال ایمن ممکن نیست."
                )
            all_wav.append((params, pcm))

        progress.progress(1.0, text="تکمیل شد")
        if not all_wav:
            raise RuntimeError("هیچ داده صوتی تولید نشد.")

        first_params = all_wav[0][0]
        combined_pcm = b"".join(item[1] for item in all_wav)
        output_bytes = pcm_to_wav_bytes(
            combined_pcm,
            rate=first_params.framerate,
            channels=first_params.nchannels,
            sample_width=first_params.sampwidth,
        )
        elapsed_total = time.time() - started_all
        filename = f"gemini_tts_{time.strftime('%Y%m%d_%H%M%S')}.wav"

        st.session_state.last_audio = output_bytes
        st.session_state.last_filename = filename
        st.session_state.last_meta = {
            "model": model,
            "mode": mode,
            "voice": selected_voice if mode == "تک‌بلندگو" else f"{voice1} / {voice2}",
            "characters": len(text_input),
            "chunks": len(chunks),
            "seconds": elapsed_total,
            "streaming": streaming,
            "sample_rate": sample_rate,
            "mime": mime_type,
        }
        st.success(f"تولید صدا انجام شد · {len(chunks)} بخش · {elapsed_total:.1f} ثانیه")

    except Exception as exc:
        st.error(f"تولید صدا ناموفق بود: {exc}")
        msg = str(exc).lower()
        if "429" in msg or "quota" in msg or "rate" in msg:
            st.info("احتمالاً محدودیت درخواست یا سهمیه رخ داده است. کمی صبر کنید یا Flash-Lite را امتحان کنید.")
        elif "404" in msg or "not found" in msg:
            st.info("مدل/endpoint برای این کلید یا پروژه در دسترس نیست؛ نام مدل و دسترسی API را بررسی کنید.")
        elif "403" in msg or "api key" in msg or "permission" in msg:
            st.info("کلید API و مجوزهای پروژه Google AI را بررسی کنید.")
        elif "پارامترهای صوتی" in msg:
            st.info("بین بخش‌ها نرخ/کانال/عرض نمونه متفاوت شده است. تقسیم متن را غیرفعال کنید یا اندازه چانک را افزایش دهید.")
        with st.expander("🔍 جزئیات فنی خطا", expanded=False):
            st.code(traceback.format_exc(), language="text")

# ----------------------------- Output panel -----------------------------

if st.session_state.get("last_audio"):
    st.header("🔊 خروجی")
    audio_bytes = st.session_state.last_audio
    filename = st.session_state.last_filename
    st.audio(audio_bytes, format="audio/wav")
    st.download_button("⬇️ دانلود WAV", data=audio_bytes,
                       file_name=filename, mime="audio/wav", use_container_width=True)

    meta = st.session_state.last_meta
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("کاراکتر", f"{meta['characters']:,}")
    m2.metric("تعداد بخش", meta["chunks"])
    m3.metric("زمان تولید", f"{meta['seconds']:.1f} ثانیه")
    m4.metric("مدل", meta["model"])
    st.caption(
        f"صدا: {meta.get('voice')} · نرخ: {meta.get('sample_rate', 24000):,} Hz · "
        f"فرمت API: {meta.get('mime', 'audio/wav')} · استریم: {'بله' if meta.get('streaming') else 'خیر'}"
    )

    if st.button("📤 ارسال خروجی به تلگرام", use_container_width=True):
        with st.spinner("در حال ارسال به تلگرام..."):
            caption = (
                f"Gemini TTS\nمدل: {meta['model']}\nحالت: {meta['mode']}\n"
                f"کاراکتر: {meta['characters']}\nنرخ: {meta.get('sample_rate', 24000):,} Hz"
            )
            ok, message = send_to_telegram(audio_bytes, filename, caption)
        (st.success if ok else st.error)(message)

    if st.button("🗂️ افزودن به تاریخچه نشست", use_container_width=True):
        st.session_state.history.insert(0, {
            "filename": filename,
            "model": meta["model"],
            "mode": meta["mode"],
            "characters": meta["characters"],
            "audio": audio_bytes,
        })
        st.session_state.history = st.session_state.history[:HISTORY_LIMIT]
        st.success(f"به تاریخچه اضافه شد (حداکثر {HISTORY_LIMIT} مورد نگه‌داری می‌شود).")

# ----------------------------- History -----------------------------

if st.session_state.history:
    with st.expander(f"🕘 تاریخچهٔ این نشست ({len(st.session_state.history)})", expanded=False):
        for idx, item in enumerate(st.session_state.history):
            st.markdown(
                f"**{item['filename']}** · {item['model']} · {item['mode']} · {item['characters']} کاراکتر"
            )
            st.audio(item["audio"], format="audio/wav")
            st.download_button(
                "دانلود", data=item["audio"], file_name=item["filename"],
                mime="audio/wav", key=f"history_download_{idx}",
            )
