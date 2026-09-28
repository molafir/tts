import streamlit as st
import wave
import requests
import base64
import re
from google import genai


# ============================================================
# 🌐 CSS برای RTL
# ============================================================

RTL_CSS = """
<style>
textarea, .stTextArea textarea {
    direction: rtl;
    text-align: right;
    font-family: 'Vazirmatn', 'Tahoma', sans-serif;
}
.stCodeBlock pre, .stCode pre {
    direction: rtl;
    text-align: right;
    font-family: 'Vazirmatn', 'Tahoma', monospace;
    font-size: 14px;
    line-height: 1.8;
}
</style>
"""


# ============================================================
# 🎵 توابع کمکی
# ============================================================

def save_wave(filename, pcm, channels=1, rate=24000, sample_width=2):
    """ذخیره فایل WAV از PCM خام."""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def send_to_telegram(file_path, caption=""):
    """ارسال فایل صوتی به ربات تلگرام از طریق Secrets."""
    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id:
            st.warning("⚠️ تنظیمات تلگرام در Secrets یافت نشد.")
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendAudio"
        with open(file_path, "rb") as audio_file:
            files = {"audio": audio_file}
            data = {
                "chat_id": chat_id,
                "caption": caption,
                "title": "Gemini TTS Output",
            }
            response = requests.post(url, files=files, data=data, timeout=30)

        if response.status_code == 200:
            st.success("✅ فایل با موفقیت به تلگرام ارسال شد.")
            return True
        st.error(f"❌ خطا در ارسال به تلگرام: {response.status_code}")
        return False
    except Exception as e:
        st.error(f"❌ خطا در ارسال به تلگرام: {e}")
        return False


TOKEN_LIMITS = {
    "gemini-3.8-flash-tts": 8192,
    "gemini-3.8-flash-lite-tts": 8192,
    "gemini-3.1-flash-tts-preview": 8192,
    "gemini-2.5-pro-preview-tts": 8192,
}


def get_token_limit(model_name):
    return TOKEN_LIMITS.get(model_name, 8192)


def validate_text_length(client, text, max_tokens=8192):
    try:
        result = client.models.count_tokens(
            model="gemini-2.5-flash", contents=text
        )
        return result.total_tokens <= max_tokens, result.total_tokens
    except Exception:
        estimated = len(text) / 4
        return estimated <= max_tokens, estimated


def generate_transcript(client, topic, length, speaker1, speaker2, style):
    prompt = (
        f"یک مکالمه {style} حدود {length} کلمه بین {speaker1} و {speaker2} "
        f'درباره "{topic}" ایجاد کن.\n'
        f"قالب خروجی دقیقاً به این شکل باشد (هر نوبت در یک خط):\n"
        f"{speaker1}: متن مکالمه\n"
        f"{speaker2}: پاسخ مکالمه\n"
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt
        )
        return response.text
    except Exception as e:
        st.error(f"خطا در تولید رونوشت: {e}")
        return None


# ============================================================
# 🧹 پاک‌سازی متن
# ============================================================

def clean_text(text):
    """حذف نشانه‌های Markdown و کاراکترهای اضافی از هر خط."""
    cleaned = []
    for ln in text.splitlines():
        # حذف * و _ در ابتدا و انتها (Markdown italic/bold)
        s = re.sub(r"^[\*\_\s]+", "", ln)
        s = re.sub(r"[\*\_\s]+$", "", s)
        # حذف بک‌تیک و نقل‌قول‌های اضافی
        s = s.strip("`\"'«»").strip()
        cleaned.append(s)
    return "\n".join(cleaned)


def normalize_colons(text):
    """تبدیل کولون‌های فارسی/عربی به کولون استاندارد."""
    return text.replace("：", ":").replace("﹕", ":")


# ============================================================
# 🤖 قالب‌بندی خودکار
# ============================================================

def _clean_lines(raw_text):
    """بازگرداندن لیست خطوط غیر خالی و تمیز."""
    text = clean_text(normalize_colons(raw_text))
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def auto_format_multispeaker(raw_text, strategy, spk1, spk2):
    """قالب‌بندی استاندارد."""
    lines = _clean_lines(raw_text)
    if not lines:
        return ""

    result = []

    if strategy == "couplet":
        for i, ln in enumerate(lines):
            spk = spk1 if (i // 2) % 2 == 0 else spk2
            result.append(f"{spk}: {ln}")

    elif strategy == "line":
        for i, ln in enumerate(lines):
            spk = spk1 if i % 2 == 0 else spk2
            result.append(f"{spk}: {ln}")

    elif strategy == "stanza":
        raw_cleaned = clean_text(normalize_colons(raw_text))
        stanzas, cur = [], []
        for ln in raw_cleaned.splitlines():
            if ln.strip():
                cur.append(ln.strip())
            elif cur:
                stanzas.append(cur)
                cur = []
        if cur:
            stanzas.append(cur)
        for i, st in enumerate(stanzas):
            spk = spk1 if i % 2 == 0 else spk2
            for ln in st:
                result.append(f"{spk}: {ln}")

    elif strategy == "dash":
        for ln in lines:
            stripped = ln.lstrip("-—–").strip()
            if stripped != ln:
                result.append(f"{spk1}: {stripped}")
            else:
                result.append(f"{spk2}: {ln}")

    return "\n".join(result)


def custom_format_multispeaker(
    raw_text, custom_mode, spk1, spk2,
    separator="", custom_map="", lines_per_turn=2,
):
    """
    قالب‌بندی سفارشی.
    
    custom_mode:
    - "separator": تقسیم بر اساس جداکننده، متناوب بین گوینده‌ها
    - "mapping":   نگاشت نام‌های دلخواه به گوینده‌ها
    - "n_lines":   هر N خط به یک گوینده
    """
    if custom_mode == "separator":
        if not separator.strip():
            return ""
        parts = [p.strip() for p in raw_text.split(separator) if p.strip()]
        result = []
        for i, part in enumerate(parts):
            spk = spk1 if i % 2 == 0 else spk2
            for ln in _clean_lines(part):
                result.append(f"{spk}: {ln}")
        return "\n".join(result)

    elif custom_mode == "mapping":
        # custom_map: "مرد=1, زن=2"  (1=گوینده اول، 2=گوینده دوم)
        map_dict = {}
        for pair in custom_map.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                map_dict[k.strip()] = v.strip()

        raw_cleaned = clean_text(normalize_colons(raw_text))
        result = []
        for ln in raw_cleaned.splitlines():
            if not ln.strip():
                continue
            if ":" in ln:
                prefix, txt = ln.split(":", 1)
                prefix, txt = prefix.strip(), txt.strip()
                if prefix in map_dict:
                    target = map_dict[prefix]
                    spk = spk1 if target == "1" else spk2
                    result.append(f"{spk}: {txt}")
                else:
                    # پیشوند ناشناخته - خط را کامل با گوینده پیش‌فرض
                    result.append(f"{spk1}: {ln.strip()}")
            else:
                result.append(f"{spk1}: {ln.strip()}")
        return "\n".join(result)

    elif custom_mode == "n_lines":
        lines = _clean_lines(raw_text)
        n = max(1, int(lines_per_turn))
        result = []
        for i, ln in enumerate(lines):
            turn = (i // n) % 2
            spk = spk1 if turn == 0 else spk2
            result.append(f"{spk}: {ln}")
        return "\n".join(result)

    return ""


def detect_best_strategy(raw_text):
    """تشخیص خودکار بهترین استراتژی."""
    lines = _clean_lines(raw_text)
    if not lines:
        return "line"

    avg_len = sum(len(ln) for ln in lines) / len(lines)
    dash_count = sum(1 for ln in lines if ln.startswith(("-", "—", "–")))

    # نمایش‌نامه
    if dash_count >= len(lines) * 0.5 and len(lines) >= 4:
        return "dash"

    # بند به بند (خط خالی زیاد)
    if raw_text.count("\n\n") >= 2:
        return "stanza"

    # شعر (خطوط کوتاه، تعداد زیاد)
    if avg_len < 70 and len(lines) >= 4:
        return "couplet"

    # تک‌گویی بلند
    return "line"


# ============================================================
# 🧠 تجزیه‌ی خطوط نهایی برای API
# ============================================================

def parse_speaker_line(line, spk1, spk2):
    """
    تجزیه‌ی یک خط به (نام گوینده، متن).
    
    نکته کلیدی: نام گوینده فقط برای هدایت مدل در annotations استفاده 
    می‌شود و در فیلد text ارسال نمی‌شود، پس هرگز خوانده نمی‌شود.
    """
    line = line.strip()
    if not line:
        return None, None

    # نرمال‌سازی کولون
    normalized = line.replace("：", ":").replace("﹕", ":")

    if ":" in normalized:
        prefix, txt = normalized.split(":", 1)
        prefix, txt = prefix.strip(), txt.strip()

        # اگر پیشوند کوتاه است و شبیه نام گوینده است
        if len(prefix) < 40 and (prefix == spk1 or prefix == spk2):
            return prefix, txt
        # اگر پیشوند گوینده‌ی شناخته‌شده ولی نه دقیقاً نام‌های انتخابی
        # (مثلاً وقتی کاربر نام گوینده را عوض کرده ولی متن قدیمی است)
        elif len(prefix) < 40 and not any(c in prefix for c in "!؟?.,،"):
            # پیشوند = نام گوینده، احتمالاً نام‌های قدیمی
            return spk1, txt

    # خط بدون پیشوند → گوینده اول
    return spk1, line


# ============================================================
# 📋 داده‌های ثابت
# ============================================================

ALL_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda",
    "Orus", "Aoede", "Callirrhoe", "Autonoe", "Enceladus", "Iapetus",
    "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi",
    "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux", "Pulcherrima",
    "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]

VOICE_DESCRIPTIONS = {
    "Zephyr": "روشن", "Puck": "خوش‌بین", "Charon": "آموزنده",
    "Kore": "محکم", "Fenrir": "هیجان‌انگیز", "Leda": "جوان",
    "Orus": "محکم", "Aoede": "نسیم ملایم", "Callirrhoe": "آسان‌گیر",
    "Autonoe": "روشن", "Enceladus": "نفس‌گیر", "Iapetus": "شفاف",
    "Umbriel": "آسان‌گیر", "Algieba": "صاف", "Despina": "صاف",
    "Erinome": "پاک", "Algenib": "شنی", "Rasalgethi": "آموزنده",
    "Laomedeia": "خوش‌بین", "Achernar": "نرم", "Alnilam": "محکم",
    "Schedar": "یکنواخت", "Gacrux": "بالغ", "Pulcherrima": "پیشرو",
    "Achird": "دوستانه", "Zubenelgenubi": "غیررسمی", "Vindemiatrix": "ملایم",
    "Sadachbia": "سرزنده", "Sadaltager": "آگاه", "Sulafat": "گرم",
}

MODELS = [
    "gemini-3.8-flash-tts",
    "gemini-3.8-flash-lite-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-pro-preview-tts",
]

MIME_TYPES = {
    "WAV (پیش‌فرض)": "audio/wav",
    "PCM خطی L16": "audio/L16",
    "mu-law (تلفن آمریکا)": "audio/mulaw",
    "A-law (تلفن اروپا)": "audio/alaw",
}


# ============================================================
# 🎨 تنظیمات صفحه
# ============================================================

st.set_page_config(
    page_title="Gemini TTS Studio Pro",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(RTL_CSS, unsafe_allow_html=True)

st.title("🎙️ Gemini TTS Studio Pro")
st.caption(
    "نسخه نهایی — Gemini 3.8 Flash TTS با قالب‌بندی خودکار و سفارشی چندبلندگو، "
    "برچسب‌های صوتی، استریمینگ و ۳۰ صدای استودیویی"
)


# ============================================================
# 📚 سایدبار
# ============================================================

SIDEBAR_TAGS = (
    "**برچسب‌های صوتی درون‌خطی** (براکت زاویه‌ای):\n\n"
    "`<laugh>` | `<sigh>` | `<cough>` | `<breath>`\n"
    "`<gasp>` | `<giggle>` | `<chuckle>` | `<cry>`\n"
    "`<whispers>` | `<shout>` | `<yawn>` | `<snort>`\n"
    "`<short pause>` | `<long pause>`\n\n"
    "مثال:\n"
    "`سلام! <laugh> چطوری؟ <short pause> خوبم.`"
)

SIDEBAR_STYLE = (
    "سبک را در فیلد **style** وارد کنید (نه در متن):\n\n"
    "`cheerful and friendly`\n"
    "`calm and relaxed`\n"
    "`whispered urgently`\n"
    "`out of breath`\n"
    "`warm and enthusiastic`\n"
    "`speaking slowly` | `speaking rapidly`"
)

SIDEBAR_LIMITS = (
    "- حداکثر **۸,۱۹۲ توکن** ورودی\n"
    "- حداکثر **۲ بلندگو**\n"
    "- فقط ورودی متنی\n"
    "- استریمینگ → PCM خام\n"
    "- غیر استریم → WAV با هدر"
)

SIDEBAR_NOTE = (
    "🔒 **نام گوینده‌ها هرگز خوانده نمی‌شود!**\n\n"
    "نام‌ها فقط برای هدایت مدل در فیلد `annotations.speaker` "
    "استفاده می‌شوند و در متن نهایی به API ارسال نمی‌شوند."
)

with st.sidebar:
    st.header("🎯 راهنما و تنظیمات")

    st.subheader("📮 تلگرام")
    telegram_configured = bool(
        st.secrets.get("TELEGRAM_BOT_TOKEN") and st.secrets.get("TELEGRAM_CHAT_ID")
    )
    if telegram_configured:
        st.success("✅ پیکربندی شده")
    else:
        st.warning("⚠️ پیکربندی نشده")

    st.subheader("🔒 نکته مهم")
    st.success(SIDEBAR_NOTE)

    st.subheader("🏷️ برچسب‌های صوتی")
    st.info(SIDEBAR_TAGS)

    st.subheader("🎭 کنترل سبک")
    st.info(SIDEBAR_STYLE)

    st.subheader("⚠️ محدودیت‌ها")
    st.warning(SIDEBAR_LIMITS)


# ============================================================
# 🔑 دریافت کلید API
# ============================================================

api_key = st.text_input("🔑 کلید API Gemini:", type="password")

if not api_key:
    st.info("🔐 برای شروع، کلید API خود را وارد کنید.")
    st.markdown(
        "### 📋 راهنمای دریافت کلید API\n"
        "1. به https://aistudio.google.com/apikey بروید\n"
        "2. وارد حساب Google شوید\n"
        "3. یک کلید جدید بسازید\n"
        "4. آن را در فیلد بالا وارد کنید\n\n"
        "### 🔧 تنظیم تلگرام (اختیاری)\n"
        "در Streamlit Cloud → Settings → Secrets این دو مقدار را وارد کنید:\n\n"
        "**TELEGRAM_BOT_TOKEN** = توکن ربات\n\n"
        "**TELEGRAM_CHAT_ID** = چت آیدی\n\n"
        "ربات را از @BotFather بسازید و Chat ID را از @userinfobot بگیرید."
    )
    st.stop()


try:
    client = genai.Client(api_key=api_key)
except Exception as e:
    st.error(f"❌ خطا در ساخت کلاینت: {e}")
    st.stop()


# ============================================================
# ⚙️ تنظیمات پیشرفته
# ============================================================

st.header("⚙️ تنظیمات پیشرفته")
c1, c2, c3, c4 = st.columns(4)

with c1:
    mode = st.radio("🎭 حالت:", ["تک‌بلندگو", "چندبلندگو"], horizontal=True)

with c2:
    tts_model = st.selectbox("🤖 مدل TTS:", MODELS, index=0)

with c3:
    stream_enabled = st.checkbox(
        "🎧 استریمینگ",
        value=False,
        help="تکه‌های PCM خام را بدون هدر برمی‌گرداند.",
    )

with c4:
    mime_label = st.selectbox(
        "🎚️ فرمت خروجی:",
        list(MIME_TYPES.keys()),
        index=0,
        disabled=stream_enabled,
    )

mime_type = MIME_TYPES[mime_label]
ext_map = {"audio/wav": "wav", "audio/L16": "pcm",
           "audio/mulaw": "mulaw", "audio/alaw": "alaw"}
file_ext = ext_map.get(mime_type, "wav")


# ============================================================
# 🤖 تولید خودکار رونوشت
# ============================================================

auto_generate = st.checkbox("🤖 تولید خودکار رونوشت با Gemini")

if auto_generate:
    st.subheader("🤖 تولید خودکار رونوشت")
    g1, g2, g3 = st.columns(3)
    with g1:
        topic = st.text_input("🎯 موضوع:", "تکنولوژی و هوش مصنوعی")
    with g2:
        style_name = st.selectbox(
            "📝 سبک:", ["پادکست", "مصاحبه", "گفتگوی دوستانه", "بحث علمی", "داستان"]
        )
    with g3:
        length = st.slider("📏 طول (کلمه):", 50, 300, 150)

    if st.button("🪄 تولید رونوشت", key="gen_transcript_btn"):
        with st.spinner("در حال تولید رونوشت..."):
            txt = generate_transcript(
                client, topic, length,
                speaker1="علی", speaker2="سارا", style=style_name
            )
            if txt:
                st.session_state.generated_transcript = txt
                st.success("رونوشت تولید شد!")


# ============================================================
# 👥 تنظیمات صدا + متن
# ============================================================

speaker1, speaker2 = "علی", "سارا"
voice1, voice2 = "Kore", "Puck"
style1, style2 = "", ""
selected_voice = "Kore"
style_instruction = ""
text_input = ""


# ------------------------------------------------------------
# حالت ۱: تک‌بلندگو
# ------------------------------------------------------------

if mode == "تک‌بلندگو":
    st.header("📝 متن ورودی")

    default_text = ""
    if "generated_transcript" in st.session_state and auto_generate:
        default_text = st.session_state.generated_transcript

    text_input = st.text_area(
        "📝 متن مورد نظر:",
        value=default_text,
        height=200,
        key="single_text",
    )

    st.subheader("👤 تنظیمات تک‌بلندگو")
    v1, v2 = st.columns(2)

    with v1:
        selected_voice = st.selectbox(
            "انتخاب صدا:",
            options=ALL_VOICES,
            format_func=lambda x: f"{x} — {VOICE_DESCRIPTIONS.get(x, '')}",
            index=ALL_VOICES.index("Kore"),
        )
    with v2:
        style_instruction = st.text_input(
            "🎭 سبک (style):",
            placeholder="مثال: cheerful and friendly",
        )


# ------------------------------------------------------------
# حالت ۲: چندبلندگو
# ------------------------------------------------------------

else:
    st.header("👥 تنظیمات چندبلندگو")

    # گام ۱: گوینده‌ها
    v1, v2 = st.columns(2)
    with v1:
        st.markdown("**🎤 گوینده ۱**")
        speaker1 = st.text_input("نام گوینده ۱:", "مرد", key="sp1_name")
        voice1 = st.selectbox(
            "صدا گوینده ۱:",
            options=ALL_VOICES,
            index=ALL_VOICES.index("Kore"),
            format_func=lambda x: f"{x} — {VOICE_DESCRIPTIONS.get(x, '')}",
            key="v1",
        )
        style1 = st.text_input(
            "سبک گوینده ۱:", placeholder="calm and deep", key="s1"
        )
    with v2:
        st.markdown("**🎤 گوینده ۲**")
        speaker2 = st.text_input("نام گوینده ۲:", "زن", key="sp2_name")
        voice2 = st.selectbox(
            "صدا گوینده ۲:",
            options=ALL_VOICES,
            index=ALL_VOICES.index("Aoede"),
            format_func=lambda x: f"{x} — {VOICE_DESCRIPTIONS.get(x, '')}",
            key="v2",
        )
        style2 = st.text_input(
            "سبک گوینده ۲:", placeholder="warm and gentle", key="s2"
        )

    # گام ۲: قالب‌بندی خودکار (Expander)
    with st.expander(
        "🤖 قالب‌بندی خودکار متن (پیشنهاد ویژه برای شعر و دیالوگ)",
        expanded=False,
    ):
        st.caption(
            f"متن خام خود را اینجا Paste کنید تا به‌طور خودکار بین "
            f"**{speaker1}** و **{speaker2}** تقسیم شود. "
            f"نام گوینده‌ها فقط برای هدایت مدل استفاده می‌شود و هرگز خوانده نمی‌شود."
        )

        raw_text = st.text_area(
            "📥 متن خام (بدون نام گوینده):",
            height=180,
            key="auto_raw_input",
            placeholder=(
                "مثال (شعر):\n"
                "منی دل، منی نوجوانی توئے\n"
                "منی زینت و زندگانی توئے\n"
                "گمانی، سیائیں دَنز و مُجاں\n"
                "من شاداں، منی شادمانی توئے"
            ),
        )

        st.markdown("---")
        st.markdown("**🎯 استراتژی تقسیم**")

        STRATEGY_OPTIONS = [
            "🎼 بیت به بیت (هر ۲ خط) — مناسب شعر",
            "📝 خط به خط — مناسب مکالمه متناوب",
            "📚 بند به بند (خط خالی جداکننده)",
            "🎭 تشخیص با خط تیره (- یا —)",
            "🛠️ سفارشی (تنظیمات دلخواه)",
        ]

        ac1, ac2 = st.columns([3, 1])
        with ac1:
            strategy_label = st.selectbox(
                "استراتژی:",
                STRATEGY_OPTIONS,
                key="strategy_select",
            )
        with ac2:
            auto_detect = st.checkbox(
                "🔍 تشخیص خودکار",
                value=True,
                key="auto_detect_chk",
                help="بهترین استراتژی بر اساس ساختار متن.",
            )

        # -- تنظیمات استراتژی سفارشی --
        custom_mode = None
        custom_sep = ""
        custom_map = ""
        custom_n = 2

        if strategy_label == STRATEGY_OPTIONS[4]:
            st.markdown("**🛠️ تنظیمات سفارشی**")

            custom_sub = st.radio(
                "روش سفارشی:",
                [
                    "🔗 جداکننده سفارشی (متن را با علامت خاص می‌برم)",
                    "🏷️ نگاشت نام‌ها (هر جا «مرد:» بود → گوینده ۱)",
                    "🔢 تعداد خط در هر نوبت",
                ],
                horizontal=False,
                key="custom_sub_radio",
            )

            if "جداکننده" in custom_sub:
                custom_mode = "separator"
                custom_sep = st.text_input(
                    "🎯 جداکننده:",
                    value="---",
                    key="custom_sep_input",
                    help="مثال: --- یا *** یا ===  . بین بخش‌ها گوینده عوض می‌شود.",
                )
            elif "نگاشت" in custom_sub:
                custom_mode = "mapping"
                custom_map = st.text_input(
                    "🏷️ نگاشت (نام=شماره):",
                    value=f"{speaker1}=1, {speaker2}=2",
                    key="custom_map_input",
                    help=(
                        "مثال: مرد=1, زن=2, راوی=1\n"
                        "یعنی هر جا «مرد:» بود → گوینده اول، «زن:» → گوینده دوم"
                    ),
                )
            else:
                custom_mode = "n_lines"
                custom_n = st.number_input(
                    "🔢 تعداد خط در هر نوبت:",
                    min_value=1,
                    max_value=20,
                    value=2,
                    key="custom_n_input",
                )

        # -- پردازش --
        if raw_text.strip():
            # تعیین استراتژی نهایی
            if strategy_label == STRATEGY_OPTIONS[4]:
                # سفارشی
                if custom_mode:
                    preview = custom_format_multispeaker(
                        raw_text, custom_mode, speaker1, speaker2,
                        separator=custom_sep,
                        custom_map=custom_map,
                        lines_per_turn=custom_n,
                    )
                    st.info("🛠️ استراتژی: **سفارشی**")
                else:
                    preview = ""
                    st.warning("لطفاً تنظیمات سفارشی را تکمیل کنید.")
            elif auto_detect:
                # تشخیص خودکار
                final_strategy = detect_best_strategy(raw_text)
                strategy_names = {
                    "couplet": "بیت به بیت",
                    "line": "خط به خط",
                    "stanza": "بند به بند",
                    "dash": "تشخیص با خط تیره",
                }
                preview = auto_format_multispeaker(
                    raw_text, final_strategy, speaker1, speaker2
                )
                st.info(
                    f"🔍 استراتژی تشخیص‌داده‌شده: **{strategy_names[final_strategy]}**"
                )
            else:
                strategy_map = {
                    STRATEGY_OPTIONS[0]: "couplet",
                    STRATEGY_OPTIONS[1]: "line",
                    STRATEGY_OPTIONS[2]: "stanza",
                    STRATEGY_OPTIONS[3]: "dash",
                }
                preview = auto_format_multispeaker(
                    raw_text, strategy_map[strategy_label], speaker1, speaker2
                )

            if preview:
                st.markdown("**👁️ پیش‌نمایش:**")
                st.code(preview, language=None)

                pc1, pc2, pc3 = st.columns(3)
                with pc1:
                    st.metric(f"خطوط {speaker1}", preview.count(f"{speaker1}:"))
                with pc2:
                    st.metric(f"خطوط {speaker2}", preview.count(f"{speaker2}:"))
                with pc3:
                    st.metric(
                        "کل خطوط",
                        len([l for l in preview.splitlines() if l.strip()]),
                    )

                if st.button(
                    "✅ اعمال روی متن اصلی",
                    use_container_width=True,
                    type="primary",
                    key="apply_auto_format",
                ):
                    st.session_state.auto_formatted_text = preview
                    st.rerun()

    # گام ۳: متن نهایی
    st.header("📝 متن نهایی (قابل ویرایش)")

    default_text = st.session_state.get("auto_formatted_text", "")
    if (
        not default_text
        and auto_generate
        and "generated_transcript" in st.session_state
    ):
        default_text = st.session_state.generated_transcript

    text_input = st.text_area(
        "📝 متن چندبلندگو:",
        value=default_text,
        height=280,
        key="multispeaker_final_text",
        help=(
            f"هر خط را با «نام گوینده:» شروع کنید. "
            f"نام‌ها فقط برای هدایت مدل استفاده می‌شوند و خوانده نمی‌شوند."
        ),
    )

    # دکمه پاک‌سازی
    cc1, cc2 = st.columns([1, 3])
    with cc1:
        if st.session_state.get("auto_formatted_text"):
            if st.button("🗑️ پاک‌کردن", key="clear_auto"):
                st.session_state.auto_formatted_text = ""
                st.rerun()


# ============================================================
# 📊 بررسی طول متن
# ============================================================

max_tokens = get_token_limit(tts_model)
is_valid = True
token_count = 0

if text_input.strip():
    is_valid, token_count = validate_text_length(client, text_input, max_tokens)
    progress = min(token_count / max_tokens, 1.0)
    st.progress(progress)

    if not is_valid:
        st.error(f"❌ متن بسیار طولانی! {token_count:.0f} از {max_tokens:,} توکن")
    else:
        st.success(f"✅ طول مناسب. {token_count:.0f} از {max_tokens:,} توکن")


# ============================================================
# 🎧 تولید صدا
# ============================================================

if st.button(
    "🎧 تولید صدا",
    type="primary",
    use_container_width=True,
    disabled=not text_input.strip() or not is_valid,
):
    try:
        with st.spinner("🔮 در حال تولید صدا..."):
            # ---------- ساخت input_blocks ----------
            if mode == "تک‌بلندگو":
                annotations = []
                if style_instruction.strip():
                    annotations.append(
                        {"type": "speech_metadata", "style": style_instruction.strip()}
                    )

                input_blocks = [
                    {
                        "type": "user_input",
                        "content": [
                            {
                                "type": "text",
                                "text": text_input,
                                "annotations": annotations,
                            }
                        ],
                    }
                ]
                speech_config = [{"voice": selected_voice}]

            else:
                # چندبلندگو: هر خط → یک بلوک با speaker در annotations
                # 🎯 نام گوینده در فیلد text ارسال نمی‌شود
                lines = [ln.strip() for ln in text_input.splitlines() if ln.strip()]
                content_blocks = []

                for line in lines:
                    spk, txt = parse_speaker_line(line, speaker1, speaker2)
                    if not txt:
                        continue

                    # اگر parse نتوانست گوینده را تشخیص دهد
                    if spk not in (speaker1, speaker2):
                        spk = speaker1

                    spk_style = style1.strip() if spk == speaker1 else style2.strip()

                    ann = [{"type": "speech_metadata", "speaker": spk}]
                    if spk_style:
                        ann[0]["style"] = spk_style

                    content_blocks.append(
                        {"type": "text", "text": txt, "annotations": ann}
                    )

                input_blocks = [{"type": "user_input", "content": content_blocks}]

                speech_config = {
                    "mode": "conversational",
                    "speakers": [
                        {"speaker": speaker1, "voice": voice1},
                        {"speaker": speaker2, "voice": voice2},
                    ],
                }

            # ---------- فراخوانی API ----------
            if stream_enabled:
                stream = client.interactions.create(
                    model=tts_model,
                    input=input_blocks,
                    response_format={"type": "audio"},
                    generation_config={"speech_config": speech_config},
                    stream=True,
                )
                audio_chunks = []
                for event in stream:
                    if (
                        event.event_type == "step.delta"
                        and event.delta.type == "audio"
                    ):
                        audio_chunks.append(base64.b64decode(event.delta.data))
                pcm_data = b"".join(audio_chunks)
                file_name = "output.wav"
                save_wave(file_name, pcm_data)
            else:
                interaction = client.interactions.create(
                    model=tts_model,
                    input=input_blocks,
                    response_format={"type": "audio", "mime_type": mime_type},
                    generation_config={"speech_config": speech_config},
                )
                audio_bytes = base64.b64decode(interaction.output_audio.data)

                if mime_type == "audio/wav":
                    file_name = "output.wav"
                    with open(file_name, "wb") as f:
                        f.write(audio_bytes)
                else:
                    file_name = f"output.{file_ext}"
                    with open(file_name, "wb") as f:
                        f.write(audio_bytes)
                    playable = "output.wav"
                    save_wave(playable, audio_bytes)
                    file_name = playable

            # ---------- نمایش ----------
            st.success("✅ تولید صدا با موفقیت انجام شد!")

            col_a, col_b = st.columns([2, 1])
            with col_a:
                st.audio(file_name, format="audio/wav")
            with col_b:
                with open(file_name, "rb") as f:
                    st.download_button(
                        "⬇️ دانلود فایل صوتی",
                        data=f,
                        file_name=file_name,
                        mime="audio/wav",
                        use_container_width=True,
                    )

            # ---------- تلگرام ----------
            if telegram_configured:
                with st.spinner("📤 در حال ارسال به تلگرام..."):
                    cap = (
                        f"Gemini TTS\n"
                        f"مدل: {tts_model}\n"
                        f"حالت: {mode}\n"
                        f"کاراکتر: {len(text_input)}"
                    )
                    send_to_telegram(file_name, cap)

            # ---------- آمار ----------
            st.subheader("📊 اطلاعات تولید")
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("طول متن", f"{len(text_input)} کاراکتر")
            with m2:
                st.metric("تعداد توکن", f"{token_count:.0f}")
            with m3:
                if mode == "تک‌بلندگو":
                    st.metric("صدا", selected_voice)
                else:
                    st.metric("بلندگوها", f"{speaker1} / {speaker2}")

    except Exception as e:
        err = str(e)
        st.error(f"❌ خطا: {err}")

        if "429" in err or "too_many_requests" in err.lower():
            st.error("🚫 **محدودیت درخواست (Rate Limit)**")
            st.info(
                "سقف درخواست‌های روزانه شما پر شده است.\n\n"
                "**راه‌حل‌ها:**\n"
                "1. چند دقیقه صبر کنید و دوباره تلاش کنید\n"
                "2. از مدل `gemini-3.8-flash-lite-tts` استفاده کنید\n"
                "3. برای افزایش سقف: https://ai.dev/rate-limit"
            )
        elif "404" in err or "model_not_found" in err:
            st.error(f"مدل `{tts_model}` در دسترس نیست.")
        elif "extra_forbidden" in err:
            st.error("تنظیمات غیرمجاز. پارامترها را بررسی کنید.")
        elif "quota" in err.lower():
            st.error("سهمیه API تمام شده است.")
        else:
            st.info("💡 کلید API را بررسی کنید یا از مدل دیگری استفاده کنید.")


# ============================================================
# 🎭 نمونه‌های آماده
# ============================================================

st.header("🎭 نمونه‌های آماده")
s1, s2, s3 = st.columns(3)

with s1:
    if st.button("تک‌بلندگو — خوش‌آمدگویی", use_container_width=True):
        st.session_state.sample_text = (
            "سلام! به Gemini TTS Studio Pro خوش آمدید. "
            "<short pause> امیدوارم روز فوق‌العاده‌ای داشته باشید."
        )

with s2:
    if st.button("چندبلندگو — گفتگوی روزمره", use_container_width=True):
        st.session_state.sample_text = (
            f"{speaker1}: سلام! امروز چطوری؟\n"
            f"{speaker2}: خوبم ممنون. تو چطور؟\n"
            f"{speaker1}: عالیم! <laugh> آماده‌ای برای شروع؟\n"
            f"{speaker2}: همیشه آماده‌ام!"
        )

with s3:
    if st.button("شعر — نمونه میر گلخان نصیر", use_container_width=True):
        st.session_state.sample_text = (
            f"{speaker1}: منی دل، منی نوجوانی توئے\n"
            f"{speaker1}: منی زینت و زندگانی توئے\n"
            f"{speaker2}: گمانی، سیائیں دَنز و مُجاں\n"
            f"{speaker2}: من شاداں، منی شادمانی توئے\n"
            f"{speaker1}: منی گال و گُپتار مُروارد ئنت\n"
            f"{speaker1}: اے دُرّیں زبان ءِ روانی توئے"
        )

if "sample_text" in st.session_state:
    st.text_area(
        "📝 متن نمونه (برای استفاده، کپی کنید):",
        st.session_state.sample_text,
        height=180,
        key="sample_text_area",
    )
