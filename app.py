import streamlit as st
import wave
import requests
import base64
from google import genai
from google.genai import types


# ============================================================
# 🎵 توابع کمکی
# ============================================================

def save_wave(filename, pcm, channels=1, rate=24000, sample_width=2):
    """ذخیره فایل صوتی WAV از داده‌های PCM خام."""
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
    "gemini-2.5-flash-preview-tts": 8192,
    "gemini-2.5-pro-preview-tts": 8192,
}


def get_token_limit(model_name):
    return TOKEN_LIMITS.get(model_name, 8192)


def validate_text_length(client, text, max_tokens=8192):
    try:
        token_count = client.models.count_tokens(
            model="gemini-2.5-flash", contents=text
        ).total_tokens
        return token_count <= max_tokens, token_count
    except Exception:
        estimated = len(text) / 4
        return estimated <= max_tokens, estimated


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
    "نسخه بازنویسی‌شده بر اساس Gemini 3.8 TTS و API جدید Interactions"
)


# ============================================================
# 📚 سایدبار
# ============================================================

with st.sidebar:
    st.header("🎯 راهنما و تنظیمات")

    st.subheader("📮 تنظیمات تلگرام")
    telegram_configured = bool(
        st.secrets.get("TELEGRAM_BOT_TOKEN") and st.secrets.get("TELEGRAM_CHAT_ID")
    )
    if telegram_configured:
        st.success("✅ تلگرام پیکربندی شده است")
    else:
        st.warning("⚠️ تلگرام پیکربندی نشده است")

    st.subheader("🏷️ برچسب‌های صوتی")
    st.info(
        "برچسب‌ها را با براکت زاویه‌ای در متن قرار دهید:\n\n"
        "`<laugh>` خنده | `<sigh>` آه\n"
        "`<cough>` سرفه | `<breath>` نفس\n"
        "`<short pause>` مکث کوتاه\n\n"
        "مثال: `سلام! <laugh> خیلی خوشحالم.`"
    )

    st.subheader("🎭 کنترل سبک")
    st.info(
        "سبک را در فیلد style وارد کنید:\n\n"
        "`cheerful and friendly`\n"
        "`calm and relaxed`\n"
        "`whispered urgently`"
    )

    st.subheader("⚠️ محدودیت‌ها")
    st.warning(
        "- حداکثر ۸,۱۹۲ توکن ورودی\n"
        "- حداکثر ۲ بلندگو\n"
        "- استریمینگ فقط در مدل‌های ۳.x"
    )


# ============================================================
# 🔑 دریافت کلید API
# ============================================================

api_key = st.text_input("🔑 کلید API Gemini خود را وارد کنید:", type="password")

if not api_key:
    st.info("🔐 برای شروع، کلید API خود را وارد کنید.")
    st.markdown(
        "### 📋 راهنمای دریافت کلید API\n"
        "1. به https://aistudio.google.com/apikey بروید\n"
        "2. وارد حساب Google شوید\n"
        "3. یک کلید جدید بسازید\n"
        "4. کلید را در فیلد بالا وارد کنید\n\n"
        "### 🔧 تنظیم تلگرام (اختیاری)\n"
        "در Streamlit Cloud → Settings → Secrets این دو مقدار را وارد کنید:\n\n"
        "- TELEGRAM_BOT_TOKEN\n"
        "- TELEGRAM_CHAT_ID"
    )
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
col1, col2, col3 = st.columns(3)

with col1:
    mode = st.radio("🎭 حالت گفتار:", ["تک‌بلندگو", "چندبلندگو"])

with col2:
    tts_model = st.selectbox(
        "🤖 مدل TTS:",
        [
            "gemini-3.8-flash-tts",
            "gemini-3.8-flash-lite-tts",
            "gemini-3.1-flash-tts-preview",
            "gemini-2.5-flash-preview-tts",
            "gemini-2.5-pro-preview-tts",
        ],
        index=0,
    )

with col3:
    stream_enabled = st.checkbox(
        "🎧 استریمینگ", value=False, help="برای متن‌های طولانی مناسب است."
    )


# ============================================================
# 🔊 لیست صداها
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
    "Orus": "محکم", "Aoede": "نسیم", "Callirrhoe": "آسان‌گیر",
    "Autonoe": "روشن", "Enceladus": "نفس‌گیر", "Iapetus": "شفاف",
    "Umbriel": "آسان‌گیر", "Algieba": "صاف", "Despina": "صاف",
    "Erinome": "پاک", "Algenib": "شنی", "Rasalgethi": "آموزنده",
    "Laomedeia": "خوش‌بین", "Achernar": "نرم", "Alnilam": "محکم",
    "Schedar": "یکنواخت", "Gacrux": "بالغ", "Pulcherrima": "پیشرو",
    "Achird": "دوستانه", "Zubenelgenubi": "غیررسمی", "Vindemiatrix": "ملایم",
    "Sadachbia": "سرزنده", "Sadaltager": "آگاه", "Sulafat": "گرم",
}


# ============================================================
# 📝 متن ورودی
# ============================================================

st.header("📝 متن ورودی")

if mode == "چندبلندگو":
    st.info(
        "**قالب چندبلندگو:**\n\n"
        "علی: سلام! امروز چطوری؟\n\n"
        "سارا: خوبم ممنون. تو چطور؟"
    )

text_input = st.text_area("📝 متن مورد نظر:", height=200)


# ============================================================
# 👥 تنظیمات صدا
# ============================================================

speaker1 = "علی"
speaker2 = "سارا"
style1 = ""
style2 = ""
voice1 = "Kore"
voice2 = "Puck"
selected_voice = "Kore"
style_instruction = ""

if mode == "تک‌بلندگو":
    st.subheader("👤 تنظیمات تک‌بلندگو")
    c1, c2 = st.columns(2)

    with c1:
        selected_voice = st.selectbox(
            "انتخاب صدا:",
            options=ALL_VOICES,
            format_func=lambda x: f"{x} — {VOICE_DESCRIPTIONS.get(x, '')}",
            index=ALL_VOICES.index("Kore"),
        )
    with c2:
        style_instruction = st.text_input(
            "🎭 دستور سبک:",
            placeholder="مثال: cheerful and friendly",
        )
else:
    st.subheader("👥 تنظیمات چندبلندگو")
    c1, c2 = st.columns(2)

    with c1:
        speaker1 = st.text_input("👤 نام گوینده ۱:", "علی")
        voice1 = st.selectbox(
            "صدا گوینده ۱:",
            options=ALL_VOICES,
            index=ALL_VOICES.index("Kore"),
            format_func=lambda x: f"{x} — {VOICE_DESCRIPTIONS.get(x, '')}",
            key="v1",
        )
        style1 = st.text_input("🎭 سبک گوینده ۱:", placeholder="cheerful", key="s1")

    with c2:
        speaker2 = st.text_input("👤 نام گوینده ۲:", "سارا")
        voice2 = st.selectbox(
            "صدا گوینده ۲:",
            options=ALL_VOICES,
            index=ALL_VOICES.index("Puck"),
            format_func=lambda x: f"{x} — {VOICE_DESCRIPTIONS.get(x, '')}",
            key="v2",
        )
        style2 = st.text_input("🎭 سبک گوینده ۲:", placeholder="calm", key="s2")


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
            if mode == "تک‌بلندگو":
                annotations = []
                if style_instruction:
                    annotations.append(
                        {"type": "speech_metadata", "style": style_instruction}
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
                lines = [ln.strip() for ln in text_input.splitlines() if ln.strip()]
                content_blocks = []

                for line in lines:
                    if ":" in line:
                        spk, txt = line.split(":", 1)
                        spk, txt = spk.strip(), txt.strip()
                    else:
                        spk, txt = speaker1, line

                    if spk == speaker1:
                        spk_style = style1
                    elif spk == speaker2:
                        spk_style = style2
                    else:
                        spk_style = ""

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
                data = b"".join(audio_chunks)
            else:
                interaction = client.interactions.create(
                    model=tts_model,
                    input=input_blocks,
                    response_format={"type": "audio"},
                    generation_config={"speech_config": speech_config},
                )
                data = base64.b64decode(interaction.output_audio.data)

            file_name = "output.wav"
            save_wave(file_name, data)

            st.success("✅ تولید صدا با موفقیت انجام شد!")

            col_a, col_b = st.columns([2, 1])
            with col_a:
                st.audio(file_name, format="audio/wav")
            with col_b:
                with open(file_name, "rb") as f:
                    st.download_button(
                        "⬇️ دانلود",
                        data=f,
                        file_name=file_name,
                        mime="audio/wav",
                        use_container_width=True,
                    )

            if telegram_configured:
                with st.spinner("📤 ارسال به تلگرام..."):
                    caption = f"Gemini TTS\nمدل: {tts_model}\nکاراکتر: {len(text_input)}"
                    send_to_telegram(file_name, caption)

    except Exception as e:
        err = str(e)
        st.error(f"❌ خطا: {err}")
        if "404" in err or "model_not_found" in err:
            st.error(f"مدل `{tts_model}` در دسترس نیست.")
        elif "extra_forbidden" in err:
            st.error("تنظیمات غیرمجاز.")
        else:
            st.info("💡 کلید API را بررسی کنید.")
