import streamlit as st
import wave
import requests
import base64
import re
import io
import time
from pathlib import Path
from google import genai

# ============================================================
# صفحه و CSS
# ============================================================
st.set_page_config(
    page_title="Gemini TTS Studio Pro",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

RTL_CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,400,0,0');
@import url('https://fonts.googleapis.com/icon?family=Material+Icons');

html, body, [class*="css"] {
    font-family: Tahoma, Arial, sans-serif;
}
textarea, .stTextArea textarea, input, .stTextInput input {
    direction: rtl;
    text-align: right;
    font-family: Tahoma, Arial, sans-serif;
}
.stCodeBlock pre, .stCode pre {
    direction: rtl;
    text-align: right;
    font-family: Tahoma, monospace;
    font-size: 14px;
    line-height: 1.8;
}
/* Streamlit آیکون‌های داخلی را با ligature فونت Material نمایش می‌دهد.
   این قوانین نام آیکون را به متن معمولی تبدیل نمی‌کنند؛ فونت مناسب را فراهم می‌کنند. */
.material-symbols-rounded,
.material-symbols-outlined,
.material-icons,
.material-icons-outlined,
[data-testid="stIconMaterial"],
[data-testid="stExpanderToggleIcon"],
[data-testid="stSidebarCollapseButton"] span,
[data-testid="stToolbar"] span {
    font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
    font-weight: normal !important;
    font-style: normal !important;
    letter-spacing: normal !important;
    text-transform: none !important;
    white-space: nowrap !important;
    word-wrap: normal !important;
    direction: ltr !important;
    font-feature-settings: 'liga' !important;
    -webkit-font-feature-settings: 'liga' !important;
    -webkit-font-smoothing: antialiased;
}
</style>
"""
st.markdown(RTL_CSS, unsafe_allow_html=True)

# ============================================================
# تنظیمات ثابت
# ============================================================
ALL_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]
VOICE_DESCRIPTIONS = {
    "Zephyr": "روشن", "Puck": "خوش‌بین", "Charon": "آموزنده",
    "Kore": "محکم", "Fenrir": "هیجان‌انگیز", "Leda": "جوان",
    "Orus": "محکم", "Aoede": "ملایم", "Callirrhoe": "آسان‌گیر",
    "Autonoe": "روشن", "Enceladus": "نفس‌گیر", "Iapetus": "شفاف",
    "Umbriel": "آسان‌گیر", "Algieba": "صاف", "Despina": "صاف",
    "Erinome": "پاک", "Algenib": "شنی", "Rasalgethi": "آموزنده",
    "Laomedeia": "خوش‌بین", "Achernar": "نرم", "Alnilam": "محکم",
    "Schedar": "یکنواخت", "Gacrux": "بالغ", "Pulcherrima": "پیشرو",
    "Achird": "دوستانه", "Zubenelgenubi": "غیررسمی",
    "Vindemiatrix": "ملایم", "Sadachbia": "سرزنده",
    "Sadaltager": "آگاه", "Sulafat": "گرم",
}
MODELS = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]
MIME_TYPES = {
    "WAV (پیش‌فرض)": "audio/wav",
    "PCM خطی L16": "audio/l16",
    "mu-law": "audio/mulaw",
    "A-law": "audio/alaw",
}
EXT_MAP = {
    "audio/wav": "wav", "audio/l16": "pcm",
    "audio/mulaw": "mulaw", "audio/alaw": "alaw",
}

def clean_text(text):
    lines = []
    for line in text.splitlines():
        s = re.sub(r"^[\*_\s]+", "", line)
        s = re.sub(r"[\*_\s]+$", "", s)
        lines.append(s.strip("`\"'«»").strip())
    return "\n".join(lines)

def normalize_colons(text):
    return text.replace("：", ":").replace("﹕", ":")

def clean_lines(text):
    return [line.strip() for line in clean_text(normalize_colons(text)).splitlines() if line.strip()]

def detect_best_strategy(raw_text):
    lines = clean_lines(raw_text)
    if not lines:
        return "line"
    dash_count = sum(1 for line in lines if line.startswith(("-", "—", "–")))
    if len(lines) >= 4 and dash_count >= len(lines) * 0.5:
        return "dash"
    if raw_text.count("\n\n") >= 2:
        return "stanza"
    if len(lines) >= 4 and sum(len(x) for x in lines) / len(lines) < 70:
        return "couplet"
    return "line"

def auto_format_multispeaker(raw_text, strategy, spk1, spk2):
    lines = clean_lines(raw_text)
    result = []
    if strategy == "couplet":
        for i, line in enumerate(lines):
            result.append(f"{spk1 if (i // 2) % 2 == 0 else spk2}: {line}")
    elif strategy == "line":
        for i, line in enumerate(lines):
            result.append(f"{spk1 if i % 2 == 0 else spk2}: {line}")
    elif strategy == "stanza":
        stanzas, current = [], []
        for line in clean_text(normalize_colons(raw_text)).splitlines():
            if line.strip():
                current.append(line.strip())
            elif current:
                stanzas.append(current)
                current = []
        if current:
            stanzas.append(current)
        for i, stanza in enumerate(stanzas):
            spk = spk1 if i % 2 == 0 else spk2
            result.extend(f"{spk}: {line}" for line in stanza)
    elif strategy == "dash":
        for line in lines:
            stripped = line.lstrip("-—–").strip()
            result.append(f"{spk1}: {stripped}" if stripped != line else f"{spk2}: {line}")
    return "\n".join(result)

def custom_format(raw_text, mode, spk1, spk2, separator="", mapping="", n_lines=2):
    if mode == "separator":
        if not separator.strip():
            return ""
        parts = [p.strip() for p in raw_text.split(separator) if p.strip()]
        out = []
        for i, part in enumerate(parts):
            out.extend(f"{spk1 if i % 2 == 0 else spk2}: {line}" for line in clean_lines(part))
        return "\n".join(out)
    if mode == "mapping":
        map_dict = {}
        for pair in mapping.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                map_dict[k.strip()] = v.strip()
        out = []
        for line in clean_text(normalize_colons(raw_text)).splitlines():
            if not line.strip():
                continue
            if ":" in line:
                prefix, body = line.split(":", 1)
                target = map_dict.get(prefix.strip(), "1")
                out.append(f"{spk1 if target == '1' else spk2}: {body.strip()}")
            else:
                out.append(f"{spk1}: {line.strip()}")
        return "\n".join(out)
    n = max(1, int(n_lines))
    return "\n".join(
        f"{spk1 if (i // n) % 2 == 0 else spk2}: {line}"
        for i, line in enumerate(clean_lines(raw_text))
    )

def parse_speaker_line(line, spk1, spk2):
    line = line.strip()
    if not line:
        return None, None
    normalized = normalize_colons(line)
    if ":" in normalized:
        prefix, body = normalized.split(":", 1)
        prefix, body = prefix.strip(), body.strip()
        if prefix == spk1 or prefix == spk2:
            return prefix, body
    return spk1, line

def save_wave(filename, pcm, channels=1, rate=24000, sample_width=2):
    with wave.open(str(filename), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)

def pcm_to_wav_bytes(pcm, rate=24000, channels=1, sample_width=2):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buffer.getvalue()

def send_to_telegram(file_bytes, filename, caption=""):
    try:
        token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            st.warning("تنظیمات تلگرام در Secrets یافت نشد.")
            return False
        endpoint = f"https://api.telegram.org/bot{token}/sendDocument"
        response = requests.post(
            endpoint,
            data={"chat_id": chat_id, "caption": caption[:1024]},
            files={"document": (filename, file_bytes, "audio/wav")},
            timeout=60,
        )
        payload = response.json()
        if response.ok and payload.get("ok"):
            st.success("فایل به تلگرام ارسال شد.")
            return True
        st.error(f"تلگرام: {payload.get('description', response.status_code)}")
    except Exception as exc:
        st.error(f"خطا در ارسال تلگرام: {exc}")
    return False

def validate_text_length(client, text, max_tokens=8192):
    try:
        result = client.models.count_tokens(model="gemini-2.5-flash", contents=text)
        count = int(result.total_tokens)
        return count <= max_tokens, count
    except Exception:
        count = int(len(text) / 4)
        return count <= max_tokens, count

def generate_transcript(client, topic, length, speaker1, speaker2, style):
    prompt = (
        f"یک مکالمه {style} حدود {length} کلمه بین {speaker1} و {speaker2} "
        f'درباره «{topic}» بنویس. فقط خطوط گفتگو را با قالب دقیق زیر برگردان:\n'
        f"{speaker1}: متن\n{speaker2}: پاسخ"
    )
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return response.text or ""

# ============================================================
# سربرگ و سایدبار
# ============================================================
st.title("🎙️ Gemini TTS Studio Pro")
st.caption("تولید صدا، گفت‌وگوی دوگوینده، قالب‌بندی متن و ارسال به تلگرام")

with st.sidebar:
    st.header("راهنما و تنظیمات")
    try:
        telegram_configured = bool(st.secrets.get("TELEGRAM_BOT_TOKEN") and st.secrets.get("TELEGRAM_CHAT_ID"))
    except Exception:
        telegram_configured = False
    st.write("تلگرام: پیکربندی شده" if telegram_configured else "تلگرام: پیکربندی نشده")
    st.info("در حالت چندگوینده، نام‌ها برای تعیین نقش گوینده استفاده می‌شوند و نباید جزو متن گفتاری باشند.")
    st.caption("برچسب‌های صوتی ممکن است بسته به مدل فعال پشتیبانی متفاوتی داشته باشند.")
    st.caption("استریمینگ این نسخه قطعات صوتی را جمع‌آوری می‌کند و در پایان فایل WAV می‌سازد؛ پخش زنده هم‌زمان نیست.")

# ============================================================
# کلید API
# ============================================================
try:
    default_api_key = st.secrets.get("GEMINI_API_KEY", "")
except Exception:
    default_api_key = ""
api_key = st.text_input("کلید API Gemini", value=default_api_key, type="password",
                        help="می‌توانید GEMINI_API_KEY را در Streamlit Secrets تنظیم کنید.")
if not api_key:
    st.info("برای شروع، کلید API را وارد کنید یا GEMINI_API_KEY را در Secrets قرار دهید.")
    st.markdown("کلید API را از Google AI Studio دریافت کنید: https://aistudio.google.com/apikey")
    st.stop()
try:
    client = genai.Client(api_key=api_key)
except Exception as exc:
    st.error(f"ساخت کلاینت ناموفق بود: {exc}")
    st.stop()

# ============================================================
# تنظیمات تولید
# ============================================================
st.header("تنظیمات تولید")
c1, c2, c3 = st.columns(3)
with c1:
    mode = st.radio("حالت", ["تک‌گوینده", "دوگوینده"], horizontal=True)
with c2:
    model = st.selectbox("مدل TTS", MODELS)
with c3:
    streaming = st.checkbox("دریافت استریمینگ", value=False)

mime_label = st.selectbox("فرمت خروجی", list(MIME_TYPES), disabled=streaming)
mime_type = MIME_TYPES[mime_label]

auto_generate = st.checkbox("تولید خودکار متن گفت‌وگو")
if auto_generate:
    a, b, c = st.columns(3)
    with a:
        topic = st.text_input("موضوع", "تکنولوژی و هوش مصنوعی")
    with b:
        transcript_style = st.selectbox("سبک متن", ["پادکست", "مصاحبه", "گفتگوی دوستانه", "بحث علمی", "داستان"])
    with c:
        length = st.slider("تعداد کلمات تقریبی", 50, 300, 150)
    if st.button("تولید متن"):
        try:
            with st.spinner("در حال تولید متن..."):
                st.session_state.generated_transcript = generate_transcript(
                    client, topic, length, "علی", "سارا", transcript_style
                )
        except Exception as exc:
            st.error(f"تولید متن ناموفق بود: {exc}")

if mode == "تک‌گوینده":
    text_value = st.session_state.get("single_text_value", st.session_state.get("generated_transcript", ""))
    text_input = st.text_area("متن ورودی", value=text_value, height=220, key="single_text")
    left, right = st.columns(2)
    with left:
        selected_voice = st.selectbox(
            "صدا", ALL_VOICES, index=ALL_VOICES.index("Kore"),
            format_func=lambda v: f"{v} — {VOICE_DESCRIPTIONS.get(v, '')}",
        )
    with right:
        style_instruction = st.text_input("سبک بیان", placeholder="cheerful and friendly")
    speaker1, speaker2 = "علی", "سارا"
else:
    lcol, rcol = st.columns(2)
    with lcol:
        speaker1 = st.text_input("نام گوینده اول", "مرد", key="speaker1_name")
        voice1 = st.selectbox("صدای گوینده اول", ALL_VOICES, index=ALL_VOICES.index("Kore"), key="voice1")
        style1 = st.text_input("سبک گوینده اول", placeholder="calm and deep", key="style1")
    with rcol:
        speaker2 = st.text_input("نام گوینده دوم", "زن", key="speaker2_name")
        voice2 = st.selectbox("صدای گوینده دوم", ALL_VOICES, index=ALL_VOICES.index("Aoede"), key="voice2")
        style2 = st.text_input("سبک گوینده دوم", placeholder="warm and gentle", key="style2")

    with st.expander("قالب‌بندی خودکار شعر یا گفت‌وگو"):
        raw_text = st.text_area("متن خام", height=160, key="raw_text")
        strategy_names = {
            "بیت‌به‌بیت": "couplet", "خط‌به‌خط": "line",
            "بندبه‌بند": "stanza", "خط تیره": "dash",
        }
        strategy_label = st.selectbox("روش تقسیم", list(strategy_names) + ["تشخیص خودکار", "سفارشی"])
        custom_mode = "n_lines"
        custom_sep, custom_map, custom_n = "---", f"{speaker1}=1, {speaker2}=2", 2
        if strategy_label == "سفارشی":
            custom_choice = st.radio("روش سفارشی", ["جداکننده", "نگاشت نام‌ها", "تعداد خط"], horizontal=True)
            if custom_choice == "جداکننده":
                custom_mode = "separator"
                custom_sep = st.text_input("جداکننده", "---")
            elif custom_choice == "نگاشت نام‌ها":
                custom_mode = "mapping"
                custom_map = st.text_input("نگاشت نام=شماره", f"{speaker1}=1, {speaker2}=2")
            else:
                custom_mode = "n_lines"
                custom_n = st.number_input("تعداد خط هر نوبت", min_value=1, max_value=20, value=2)
        if raw_text.strip():
            if strategy_label == "سفارشی":
                preview = custom_format(raw_text, custom_mode, speaker1, speaker2, custom_sep, custom_map, custom_n)
            else:
                strat = detect_best_strategy(raw_text) if strategy_label == "تشخیص خودکار" else strategy_names[strategy_label]
                preview = auto_format_multispeaker(raw_text, strat, speaker1, speaker2)
            st.code(preview)
            if st.button("اعمال متن قالب‌بندی‌شده"):
                st.session_state.multispeaker_text_value = preview
                st.rerun()

    initial_multi = st.session_state.get("multispeaker_text_value", st.session_state.get("generated_transcript", ""))
    text_input = st.text_area(
        "متن نهایی دوگوینده", value=initial_multi, height=260, key="multispeaker_text",
        help="هر خط را با نام گوینده و دونقطه آغاز کنید؛ برای نمونه: مرد: سلام",
    )

# نمونه‌ها در انتخابگر قرار می‌گیرند و با کلیک به متن اصلی کپی می‌شوند.
st.subheader("نمونه‌های آماده")
sample_choice = st.selectbox("انتخاب نمونه", ["بدون نمونه", "خوش‌آمدگویی تک‌گوینده", "گفت‌وگوی روزمره", "نمونه شعر"])
if st.button("قرار دادن نمونه در متن"):
    if sample_choice == "خوش‌آمدگویی تک‌گوینده":
        sample = "سلام! به Gemini TTS Studio Pro خوش آمدید. <short pause> امیدوارم روز خوبی داشته باشید."
    elif sample_choice == "گفت‌وگوی روزمره":
        sample = f"{speaker1}: سلام! امروز چطوری؟\n{speaker2}: خوبم ممنون. تو چطور؟\n{speaker1}: عالی‌ام!\n{speaker2}: خوشحالم!"
    elif sample_choice == "نمونه شعر":
        sample = f"{speaker1}: منی دل، منی نوجوانی توئے\n{speaker1}: منی زینت و زندگانی توئے\n{speaker2}: گمانی، سیائیں دَنز و مُجاں\n{speaker2}: من شاداں، منی شادمانی توئے"
    else:
        sample = ""
    if mode == "تک‌گوینده":
        st.session_state.single_text = sample
    else:
        st.session_state.multispeaker_text = sample
    st.rerun()

# ============================================================
# اعتبارسنجی متن
# ============================================================
valid = bool(text_input.strip())
token_count = 0
if valid:
    valid, token_count = validate_text_length(client, text_input)
    st.progress(min(token_count / 8192, 1.0))
    st.caption(f"برآورد توکن: {token_count:,} از 8,192")
    if not valid:
        st.error("متن بیش از حد طولانی است. آن را کوتاه‌تر کنید.")

# ============================================================
# تولید صدا
# ============================================================
if st.button("تولید صدا", type="primary", use_container_width=True, disabled=not valid):
    if mode == "دوگوینده" and (not speaker1.strip() or not speaker2.strip() or speaker1 == speaker2):
        st.error("نام دو گوینده باید خالی نباشد و با هم تفاوت داشته باشد.")
        st.stop()
    try:
        with st.spinner("در حال تولید صدا..."):
            if mode == "تک‌گوینده":
                annotations = []
                if style_instruction.strip():
                    annotations.append({"type": "speech_metadata", "style": style_instruction.strip()})
                input_blocks = [{
                    "type": "user_input",
                    "content": [{"type": "text", "text": text_input, "annotations": annotations}],
                }]
                speech_config = [{"voice": selected_voice}]
            else:
                content_blocks = []
                for line in text_input.splitlines():
                    if not line.strip():
                        continue
                    spk, body = parse_speaker_line(line, speaker1, speaker2)
                    if not body:
                        continue
                    if spk not in (speaker1, speaker2):
                        st.warning(f"نام گوینده در این خط تشخیص داده نشد؛ خط به {speaker1} نسبت داده شد.")
                        spk = speaker1
                    style = style1.strip() if spk == speaker1 else style2.strip()
                    annotation = {"type": "speech_metadata", "speaker": spk}
                    if style:
                        annotation["style"] = style
                    content_blocks.append({"type": "text", "text": body, "annotations": [annotation]})
                if not content_blocks:
                    st.error("هیچ متن قابل تبدیل به صدا وجود ندارد.")
                    st.stop()
                input_blocks = [{"type": "user_input", "content": content_blocks}]
                speech_config = {
                    "mode": "conversational",
                    "speakers": [
                        {"speaker": speaker1, "voice": voice1},
                        {"speaker": speaker2, "voice": voice2},
                    ],
                }

            if streaming:
                stream = client.interactions.create(
                    model=model, input=input_blocks,
                    response_format={"type": "audio"},
                    generation_config={"speech_config": speech_config},
                    stream=True,
                )
                chunks = []
                for event in stream:
                    if getattr(event, "event_type", "") == "step.delta":
                        delta = getattr(event, "delta", None)
                        if delta is not None and getattr(delta, "type", None) == "audio":
                            data = getattr(delta, "data", None)
                            if data:
                                chunks.append(base64.b64decode(data))
                audio_bytes = b"".join(chunks)
                if not audio_bytes:
                    raise RuntimeError("استریم تمام شد اما داده صوتی دریافت نشد.")
                wav_bytes = pcm_to_wav_bytes(audio_bytes)
                filename = "gemini_tts_stream.wav"
            else:
                interaction = client.interactions.create(
                    model=model, input=input_blocks,
                    response_format={"type": "audio", "mime_type": mime_type},
                    generation_config={"speech_config": speech_config},
                )
                audio_bytes = base64.b64decode(interaction.output_audio.data)
                if mime_type == "audio/wav":
                    wav_bytes = audio_bytes
                    filename = "gemini_tts.wav"
                elif mime_type == "audio/l16":
                    wav_bytes = pcm_to_wav_bytes(audio_bytes, sample_width=2)
                    filename = "gemini_tts.wav"
                elif mime_type in ("audio/mulaw", "audio/alaw"):
                    st.warning("این خروجی کدک تلفنی است؛ برای جلوگیری از ساخت WAV نادرست، فایل اصلی با پسوند صحیح ارائه می‌شود.")
                    filename = f"gemini_tts.{EXT_MAP[mime_type]}"
                    st.download_button("دانلود فایل صوتی خام", data=audio_bytes, file_name=filename, mime=mime_type)
                    st.stop()
                else:
                    raise RuntimeError(f"فرمت خروجی پشتیبانی نمی‌شود: {mime_type}")

            st.success("تولید صدا انجام شد.")
            st.audio(wav_bytes, format="audio/wav")
            st.download_button("دانلود فایل WAV", data=wav_bytes, file_name=filename,
                               mime="audio/wav", use_container_width=True)
            st.caption(f"کاراکتر: {len(text_input):,} | توکن تقریبی: {token_count:,} | مدل: {model}")
            if telegram_configured:
                if st.button("ارسال فایل به تلگرام"):
                    send_to_telegram(wav_bytes, filename, f"Gemini TTS | مدل: {model} | حالت: {mode}")
    except Exception as exc:
        message = str(exc)
        st.error(f"خطا در تولید صدا: {message}")
        if "429" in message or "quota" in message.lower():
            st.info("محدودیت سهمیه یا تعداد درخواست رخ داده است؛ وضعیت سهمیه و دسترسی مدل را بررسی کنید.")
        elif "404" in message or "model_not_found" in message.lower():
            st.info("مدل انتخاب‌شده در پروژه یا منطقه فعلی در دسترس نیست.")
        elif "annotation" in message.lower() or "speech_metadata" in message.lower():
            st.info("ساختار annotations یا پشتیبانی مدل از فراداده گفتار را بررسی کنید.")

st.caption("نکته: آیکون‌های داخلی Streamlit وابسته به فونت و نسخه Streamlit هستند. اگر شبکه فونت Google را مسدود کند، CSS به‌تنهایی تضمین‌کننده رفع مشکل نیست.")
