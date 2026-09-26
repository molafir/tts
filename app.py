import streamlit as st
import wave
import requests
import io
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


# 🎯 محدودیت توکن پویا بر اساس مدل (مستندات رسمی)
TOKEN_LIMITS = {
    "gemini-3.8-flash-tts": 8192,
    "gemini-3.8-flash-lite-tts": 8192,
    "gemini-3.1-flash-tts-preview": 8192,
    "gemini-2.5-flash-preview-tts": 8192,
    "gemini-2.5-pro-preview-tts": 8192,
}


def get_token_limit(model_name: str) -> int:
    """بازگرداندن محدودیت توکن ورودی بر اساس مدل."""
    return TOKEN_LIMITS.get(model_name, 8192)


def validate_text_length(client, text, max_tokens=8192):
    """بررسی طول متن بر اساس شمارش توکن."""
    try:
        token_count = client.models.count_tokens(
            model="gemini-2.5-flash", contents=text
        ).total_tokens
        return token_count <= max_tokens, token_count
    except Exception:
        estimated = len(text) / 4
        return estimated <= max_tokens, estimated


def generate_transcript(client, topic, length, speaker1="علی", speaker2="سارا", style="پادکست"):
    """تولید خودکار رونوشت با Gemini."""
    prompt = (
        f"یک مکالمه {style} حدود {length} کلمه بین {speaker1} و {speaker2} "
        f'درباره "{topic}" ایجاد کن.\n'
        f"قالب خروجی:\n{speaker1}: متن\n{speaker2}: پاسخ\n"
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
    "نسخه بازنویسی‌شده بر اساس Gemini 3.8 TTS و API جدید Interactions "
    "— پشتیبانی از حالت مکالمه، برچسب‌های صوتی، استریمینگ و ۳۰ صدای استودیویی"
)


# ============================================================
# 📚 سایدبار
# ============================================================

with st.sidebar:
    st.header("🎯 راهنما و تنظیمات")

    # --- تلگرام ---
    st.subheader("📮 تنظیمات تلگرام")
    telegram_configured = bool(
        st.secrets.get("TELEGRAM_BOT_TOKEN") and st.secrets.get("TELEGRAM_CHAT_ID")
    )
    if telegram_configured:
        st.success("✅ تلگرام پیکربندی شده است")
        st.info("فایل‌ها به‌طور خودکار ارسال می‌شوند")
    else:
        st.warning("⚠️ تلگرام پیکربندی نشده است")
        st.info("برای فعال‌سازی، Secrets را در تنظیمات وارد کنید")

    # --- برچسب‌های صوتی ---
    st.subheader("🏷️ برچسب‌های صوتی (Inline Tags)")
    st.info(
        "برچسب‌ها را با **براکت زاویه‌ای** و در محل تغییر لحن قرار دهید:\n\n"
        "`<laugh>` خنده  |  `<sigh>` آه\n"
        "`<cough>` سرفه  |  `<breath>` نفس\n"
        "`<short pause>` مکث کوتاه  |  `<long pause>` مکث بلند\n\n"
        "مثال: `سلام، چطوری؟ <laugh> خیلی خوشحالم!`"
    )

    # --- سبک گفتار ---
    st.subheader("🎭 کنترل سبک (speech_metadata.style)")
    st.info(
        "سبک را در فیلد `style` وارد کنید (نه در متن):\n\n"
        "`cheerful and friendly`\n"
        "`calm and relaxed`\n"
        "`whispered urgently`\n"
        "`warm and enthusiastic`\n"
        "`out of breath`"
    )

    # --- محدودیت‌ها ---
    st.subheader("⚠️ محدودیت‌ها")
    st.warning(
        "- حداکثر **۸,۱۹۲ توکن** ورودی در هر درخواست\n"
        "- حداکثر **۲ بلندگو** در حالت چندبلندگو\n"
        "- فقط ورودی متنی\n"
        "- استریمینگ فقط در مدل‌های ۳.x\n"
        "- برای متن‌های طولانی، استریمینگ توصیه می‌شود"
    )

    # --- زبان ---
    st.subheader("🌐 زبان")
    st.info(
        "مدل‌های TTS زبان ورودی را **به‌طور خودکار** تشخیص می‌دهند.\n"
        "- Gemini 3.8 Flash TTS: **۱۳۰+ زبان**\n"
        "- Gemini 3.8 Flash-Lite TTS: **۱۰۰+ زبان**"
    )


# ============================================================
# 🔑 دریافت کلید API
# ============================================================

api_key = st.text_input("🔑 کلید API Gemini خود را وارد کنید:", type="password")

if not api_key:
    st.info("🔐 برای شروع، کلید API خود را وارد کنید.")
    st.markdown(
        """
### 📋 راهنمای دریافت کلید API
1. به [Google AI Studio](https://aistudio.google.com/apikey) بروید
2. وارد حساب Google خود شوید
3. یک کلید جدید ایجاد کنید
4. کلید را در فیلد بالا وارد کنید

### 🔧 راهنمای تنظیم تلگرام
در Streamlit Cloud → Settings → Secrets:
```toml
TELEGRAM_BOT_TOKEN = "توکن_ربات"
TELEGRAM_CHAT_ID = "چت_آیدی"
