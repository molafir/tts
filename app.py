import streamlit as st
import wave
import requests
import base64
from google import genai


# ============================================================
# 🎵 توابع کمکی
# ============================================================

def save_wave(filename, pcm, channels=1, rate=24000, sample_width=2):
    """ذخیره فایل WAV از داده‌های PCM خام (برای حالت استریمینگ)."""
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


# محدودیت توکن ورودی (طبق مستندات رسمی: 8,192 توکن)
TOKEN_LIMITS = {
    "gemini-3.8-flash-tts": 8192,
    "gemini-3.8-flash-lite-tts": 8192,
    "gemini-3.1-flash-tts-preview": 8192,
    "gemini-2.5-pro-preview-tts": 8192,
}


def get_token_limit(model_name):
    return TOKEN_LIMITS.get(model_name, 8192)


def validate_text_length(client, text, max_tokens=8192):
    """شمارش توکن؛ در صورت خطا تخمین می‌زند."""
    try:
        result = client.models.count_tokens(
            model="gemini-2.5-flash", contents=text
        )
        count = result.total_tokens
        return count <= max_tokens, count
    except Exception:
        estimated = len(text) / 4
        return estimated <= max_tokens, estimated


def generate_transcript(client, topic, length, speaker1, speaker2, style):
    """تولید خودکار رونوشت با Gemini."""
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

st.title("🎙️ Gemini TTS Studio Pro")
st.caption(
    "نسخه نهایی بر اساس Gemini 3.8 Flash TTS — Interactions API، "
    "برچسب‌های صوتی، حالت مکالمه، استریمینگ و ۳۰ صدای استودیویی"
)


# ============================================================
# 📚 سایدبار
# ============================================================

SIDEBAR_TAGS = (
    "**برچسب‌های صوتی درون‌خطی** (با براکت زاویه‌ای):\n\n"
    "`<laugh>` | `<sigh>` | `<cough>` | `<breath>`\n"
    "`<gasp>` | `<giggle>` | `<chuckle>` | `<cry>`\n"
    "`<whispers>` | `<shout>` | `<yawn>` | `<snort>`\n"
    "`<short pause>` | `<long pause>`\n\n"
    "مثال:\n"
    "`سلام! <laugh> چطوری؟ <short pause> خوبم.`"
)

SIDEBAR_STYLE = (
    "سبک را در فیلد **style** (نه در متن) وارد کنید:\n\n"
    "`cheerful and friendly`\n"
    "`calm and relaxed`\n"
    "`whispered urgently`\n"
    "`out of breath`\n"
    "`warm and enthusiastic`\n"
    "`speaking slowly`\n"
    "`speaking rapidly`\n"
    "`monotone and flat`"
)

SIDEBAR_LIMITS = (
    "- حداکثر **۸,۱۹۲ توکن** ورودی\n"
    "- حداکثر **۲ بلندگو**\n"
    "- فقط ورودی متنی\n"
    "- استریمینگ → PCM خام\n"
    "- غیر استریم → WAV با هدر"
)

SIDEBAR_LANGS = (
    "زبان به‌طور **خودکار** تشخیص داده می‌شود:\n\n"
    "- **3.8 Flash TTS:** ۱۳۰+ زبان\n"
    "- **3.8 Flash-Lite TTS:** ۱۰۰+ زبان\n"
    "- فارسی، عربی، انگلیسی، فرانسه، آلمانی و ..."
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

    st.subheader("🏷️ برچسب‌های صوتی")
    st.info(SIDEBAR_TAGS)

    st.subheader("🎭 کنترل سبک")
    st.info(SIDEBAR_STYLE)

    st.subheader("⚠️ محدودیت‌ها")
    st.warning(SIDEBAR_LIMITS)

    st.subheader("🌐 زبان‌ها")
    st.info(SIDEBAR_LANGS)


# ============================================================
# 🔑 دریافت کلید API
# ============================================================

api_key = st.text_input("🔑 کلید API Gemini:", type="password")

if not api_key:
    st.info("🔐 برای شروع، کلید API خود را وارد کنید.")

    help_text = (
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
    st.markdown(help_text)
    st.stop()


# ============================================================
# 🚀 راه‌اندازی کلاینت
# ============================================================

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
        help="تکه‌های PCM خام را بدون هدر برمی‌گرداند. برای متن‌های طولانی مناسب است.",
    )

with c4:
    mime_label = st.selectbox(
        "🎚️ فرمت خروجی:",
        list(MIME_TYPES.keys()),
        index=0,
        disabled=stream_enabled,
        help="در حالت استریمینگ، خروجی همیشه PCM خام (L16) است.",
    )

mime_type = MIME_TYPES[mime_label]

# برچسب مناسب برای پسوند فایل
ext_map = {
    "audio/wav": "wav",
    "audio/L16": "pcm",
    "audio/mulaw": "mulaw",
    "audio/alaw": "alaw",
}
file_ext = ext_map.get(mime_type, "wav")


# ============================================================
# 🤖 تولید خودکار رونوشت
# ============================================================

auto_generate = st.checkbox("🤖 تولید خودکار رونوشت")

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
# 📝 متن ورودی
# ============================================================

st.header("📝 متن ورودی")

if mode == "چندبلندگو":
    st.info(
        "**قالب چندبلندگو:** هر نوبت را در یک خط جدا بنویسید.\n\n"
        "```\nعلی: سلام! امروز چطوری؟\nسارا: خوبم ممنون. تو چطور؟\n```"
    )

if "generated_transcript" in st.session_state and auto_generate:
    text_input = st.text_area(
        "📝 متن مورد نظر:",
        value=st.session_state.generated_transcript,
        height=200,
    )
else:
    text_input = st.text_area("📝 متن مورد نظر:", height=200)


# ============================================================
# 👥 تنظیمات صدا
# ============================================================

speaker1, speaker2 = "علی", "سارا"
voice1, voice2 = "Kore", "Puck"
style1, style2 = "", ""
selected_voice = "Kore"
style_instruction = ""

if mode == "تک‌بلندگو":
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
else:
    st.subheader("👥 تنظیمات چندبلندگو")
    v1, v2 = st.columns(2)

    with v1:
        speaker1 = st.text_input("👤 نام گوینده ۱:", "علی")
        voice1 = st.selectbox(
            "صدا گوینده ۱:",
            options=ALL_VOICES,
            index=ALL_VOICES.index("Kore"),
            format_func=lambda x: f"{x} — {VOICE_DESCRIPTIONS.get(x, '')}",
            key="v1",
        )
        style1 = st.text_input(
            "🎭 سبک گوینده ۱:", placeholder="cheerful and friendly", key="s1"
        )
    with v2:
        speaker2 = st.text_input("👤 نام گوینده ۲:", "سارا")
        voice2 = st.selectbox(
            "صدا گوینده ۲:",
            options=ALL_VOICES,
            index=ALL_VOICES.index("Puck"),
            format_func=lambda x: f"{x} — {VOICE_DESCRIPTIONS.get(x, '')}",
            key="v2",
        )
        style2 = st.text_input(
            "🎭 سبک گوینده ۲:", placeholder="calm and relaxed", key="s2"
        )


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
                # چندبلندگو: هر خط یک بلوک جدا با speaker و style
                lines = [ln.strip() for ln in text_input.splitlines() if ln.strip()]
                content_blocks = []

                for line in lines:
                    if ":" in line:
                        spk, txt = line.split(":", 1)
                        spk, txt = spk.strip(), txt.strip()
                    else:
                        spk, txt = speaker1, line

                    spk_style = ""
                    if spk == speaker1:
                        spk_style = style1.strip()
                    elif spk == speaker2:
                        spk_style = style2.strip()

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
                # استریمینگ: خروجی PCM خام (بدون هدر)
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

                # اضافه کردن هدر WAV برای پخش در Streamlit
                file_name = "output.wav"
                save_wave(file_name, pcm_data)
            else:
                # غیر استریم: ممکن است WAV یا PCM برگردد بسته به mime_type
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
                    # PCM خام → اضافه کردن هدر WAV برای پخش
                    file_name = f"output.{file_ext}"
                    with open(file_name, "wb") as f:
                        f.write(audio_bytes)
                    # یک کپی WAV برای پخش‌کننده Streamlit
                    playable = "output.wav"
                    save_wave(playable, audio_bytes)
                    file_name = playable

            # ---------- نمایش نتیجه ----------
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

            # ---------- ارسال به تلگرام ----------
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
                "سقف درخواست‌های روزانه شما در پلن رایگان پر شده است.\n\n"
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
    if st.button("دراماتیک — داستان", use_container_width=True):
        st.session_state.sample_text = (
            "در سرزمینی دور، قهرمانی سفری حماسی را آغاز کرد. "
            "<short pause> چالش‌ها در انتظار او بودند..."
        )

if "sample_text" in st.session_state:
    st.text_area(
        "📝 متن نمونه (برای استفاده، کپی کنید):",
        st.session_state.sample_text,
        height=150,
        key="sample_text_area",
    )
