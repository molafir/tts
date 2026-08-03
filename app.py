import streamlit as st
import wave
import requests
import base64
import time
import re
from google import genai

# 🎵 ذخیره فایل صوتی
def save_wave(filename, pcm, channels=1, rate=24000, sample_width=2):
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)

# 📨 ارسال به تلگرام
def send_to_telegram(file_path, caption=""):
    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id:
            st.warning("⚠️ تنظیمات تلگرام یافت نشد")
            return False
        url = f"https://api.telegram.org/bot{bot_token}/sendAudio"
        with open(file_path, "rb") as audio_file:
            files = {"audio": audio_file}
            data = {"chat_id": chat_id, "caption": caption, "title": "Gemini TTS"}
            response = requests.post(url, files=files, data=data, timeout=30)
        if response.status_code == 200:
            st.success("✅ به تلگرام ارسال شد")
            return True
        else:
            st.error(f"❌ خطای تلگرام: {response.status_code}")
            return False
    except Exception as e:
        st.error(f"❌ خطای تلگرام: {e}")
        return False

# 📊 بررسی طول متن با محدودیت متغیر
def validate_text_length(client, text, max_tokens):
    try:
        token_count = client.models.count_tokens(
            model="gemini-2.0-flash", contents=text
        ).total_tokens
        return token_count <= max_tokens, token_count
    except Exception as e:
        st.error(f"خطا در شمارش توکن‌ها: {e}")
        estimated = len(text) / 4
        st.warning("شمارش تقریبی (۴ کاراکتر ≈ ۱ توکن).")
        return estimated <= max_tokens, estimated

# 🎭 تولید خودکار رونوشت
def generate_transcript(client, topic, length, speaker1="علی", speaker2="سارا", style="پادکست"):
    prompt = f"""
    یک مکالمه {style} حدود {length} کلمه بین {speaker1} و {speaker2} درباره "{topic}" ایجاد کن.
    قالب خروجی:
    {speaker1}: متن مکالمه
    {speaker2}: پاسخ مکالمه
    """
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        return response.text
    except Exception as e:
        st.error(f"خطا در تولید رونوشت: {e}")
        return None

# 🎨 تنظیمات صفحه
st.set_page_config(page_title="Gemini TTS Studio Pro", page_icon="🎙️", layout="wide")
st.title("🎙️ Gemini TTS Studio Pro")
st.caption("تبدیل متن به گفتار حرفه‌ای با Gemini TTS – Interactions API")

# سایدبار
with st.sidebar:
    st.header("🎯 راهنما")
    telegram_configured = st.secrets.get("TELEGRAM_BOT_TOKEN") and st.secrets.get("TELEGRAM_CHAT_ID")
    if telegram_configured:
        st.success("✅ تلگرام متصل است")
    else:
        st.warning("⚠️ تلگرام پیکربندی نشده")
    st.markdown("### 📖 دستورات سبک")
    st.info("""
    - `Say cheerfully: متن`
    - `Say slowly: متن`
    - `Make speaker1 sound tired and bored: متن`
    """)
    st.markdown("### ⚠️ محدودیت‌ها")
    st.warning("""
    - ۳۲۰۰۰ توکن (فقط 3.1 Flash)، ۸۱۹۲ توکن (بقیه)
    - حداکثر ۲ بلندگو
    """)

# کلید API
api_key = st.text_input("🔑 کلید API Gemini:", type="password")
if api_key:
    try:
        client = genai.Client(api_key=api_key)

        # تنظیمات
        st.header("⚙️ تنظیمات")
        col1, col2, col3 = st.columns(3)
        with col1:
            mode = st.radio("🎭 حالت:", ["تک‌بلندگو", "چندبلندگو"])
        with col2:
            tts_model = st.selectbox(
                "🤖 مدل TTS:",
                [
                    "gemini-3.1-flash-tts-preview",        # 32000 توکن
                    "gemini-2.5-flash-preview-tts",        # 8192 توکن
                    "gemini-2.5-pro-preview-tts"           # 8192 توکن
                ],
                help="2.5 Flash اکنون با نام صحیح در دسترس است."
            )
        with col3:
            speech_rate_option = st.selectbox("🎚️ سرعت:", ["پیش‌فرض", "آهسته", "متوسط", "سریع"])
            speed_commands = {
                "پیش‌فرض": "",
                "آهسته": "Say slowly",
                "متوسط": "Say at a moderate pace",
                "سریع": "Say quickly"
            }

        # لهجه‌ها و صداها (بدون تغییر)
        accent_options = {
            "تشخیص خودکار": None, "انگلیسی (آمریکا)": "en-US", "فارسی": "fa",
            "فرانسوی (فرانسه)": "fr-FR", "آلمانی (آلمان)": "de-DE", "عربی (مصر)": "ar-EG",
            "هندی": "hi-IN", "ژاپنی": "ja-JP", "کره‌ای": "ko-KR", "اسپانیایی (آمریکا)": "es-US"
        }
        all_voices = [
            "Zephyr","Puck","Charon","Kore","Fenrir","Leda","Orus","Aoede",
            "Callirrhoe","Autonoe","Enceladus","Iapetus","Umbriel","Algieba",
            "Despina","Erinome","Algenib","Rasalgethi","Laomedeia","Achernar",
            "Alnilam","Schedar","Gacrux","Pulcherrima","Achird","Zubenelgenubi",
            "Vindemiatrix","Sadachbia","Sadaltager","Sulafat"
        ]
        voice_desc = {
            "Zephyr":"Bright","Puck":"Upbeat","Charon":"Informative","Kore":"Firm",
            "Fenrir":"Excitable","Leda":"Youthful","Orus":"Firm","Aoede":"Breezy",
            "Callirrhoe":"Easy-going","Autonoe":"Bright","Enceladus":"Breathy",
            "Iapetus":"Clear","Umbriel":"Easy-going","Algieba":"Smooth","Despina":"Smooth",
            "Erinome":"Clear","Algenib":"Gravelly","Rasalgethi":"Informative",
            "Laomedeia":"Upbeat","Achernar":"Soft","Alnilam":"Firm","Schedar":"Even",
            "Gacrux":"Mature","Pulcherrima":"Forward","Achird":"Friendly",
            "Zubenelgenubi":"Casual","Vindemiatrix":"Gentle","Sadachbia":"Lively",
            "Sadaltager":"Knowledgeable","Sulafat":"Warm"
        }

        # تولید خودکار (مانند قبل)
        auto_generate = st.checkbox("🤖 تولید خودکار رونوشت")
        if auto_generate:
            c1, c2, c3 = st.columns(3)
            with c1: topic = st.text_input("موضوع:", "تکنولوژی")
            with c2: style = st.selectbox("سبک:", ["پادکست","مصاحبه","دوستانه","علمی","داستان"])
            with c3: length = st.slider("طول (کلمه):", 50, 300, 150)
            if st.button("🪄 تولید"):
                with st.spinner():
                    transcript = generate_transcript(client, topic, length, style=style)
                    if transcript:
                        st.session_state.generated_transcript = transcript
                        st.success("رونوشت آماده شد.")

        # متن ورودی
        st.header("📝 متن ورودی")
        if mode == "چندبلندگو":
            st.info("""
            قالب:
            ```
            TTS the following conversation between علی and سارا:
            علی: سلام!
            سارا: سلام، خوبی؟
            ```
            """)

        default_text = st.session_state.get('generated_transcript', '') if auto_generate else ''
        text_input = st.text_area("متن:", value=default_text, height=200,
                                  placeholder='Say cheerfully: Have a wonderful day!')

        # انتخاب صداها
        if mode == "تک‌بلندگو":
            st.subheader("👤 تک‌بلندگو")
            c1, c2, c3 = st.columns(3)
            with c1: selected_voice = st.selectbox("صدا:", all_voices, index=3,
                                                   format_func=lambda x: f"{x} - {voice_desc.get(x,'')}")
            with c2: style_instruction = st.text_input("دستور سبک:", placeholder='Say cheerfully')
            with c3: selected_accent = st.selectbox("لهجه:", list(accent_options.keys()), index=0)
        else:
            st.subheader("👥 چندبلندگو")
            c1, c2 = st.columns(2)
            with c1:
                speaker1 = st.text_input("گوینده ۱:", "علی")
                voice1 = st.selectbox("صدا ۱:", all_voices, index=3, format_func=lambda x: f"{x} - {voice_desc.get(x,'')}", key="v1")
                style1 = st.text_input("سبک ۱:", placeholder="tired and bored")
                accent1 = st.selectbox("لهجه ۱:", list(accent_options.keys()), index=0, key="a1")
            with c2:
                speaker2 = st.text_input("گوینده ۲:", "سارا")
                voice2 = st.selectbox("صدا ۲:", all_voices, index=1, format_func=lambda x: f"{x} - {voice_desc.get(x,'')}", key="v2")
                style2 = st.text_input("سبک ۲:", placeholder="excited and happy")
                accent2 = st.selectbox("لهجه ۲:", list(accent_options.keys()), index=0, key="a2")

        # محدودیت توکن بر اساس مدل
        if tts_model == "gemini-3.1-flash-tts-preview":
            max_tokens = 32000
        else:
            max_tokens = 8192   # 2.5 Flash و Pro هر دو 8192 دارند

        # بررسی طول
        if text_input:
            is_valid, token_count = validate_text_length(client, text_input, max_tokens)
            st.progress(min(token_count / max_tokens, 1.0))
            if not is_valid:
                st.error(f"❌ تعداد توکن‌ها: {token_count:.0f} از {max_tokens} – متن را کوتاه کنید")
            else:
                st.success(f"✅ توکن‌ها: {token_count:.0f} از {max_tokens}")

        # تولید صدا با retry
        if st.button("🎧 تولید صدا", type="primary", use_container_width=True,
                     disabled=not text_input.strip() or (text_input and not is_valid)):
            with st.spinner("🔮 در حال تولید..."):
                max_retries = 3
                retry_delay = 5
                interaction = None

                for attempt in range(max_retries):
                    try:
                        processed = text_input
                        speed_cmd = speed_commands[speech_rate_option]
                        if speed_cmd:
                            processed = f"{speed_cmd}: {processed}"

                        if mode == "تک‌بلندگو":
                            if style_instruction:
                                processed = f"{style_instruction}: {processed}"
                            if selected_accent != "تشخیص خودکار":
                                processed = f"Language {accent_options[selected_accent]}: {processed}"

                            interaction = client.interactions.create(
                                model=tts_model,
                                input=processed,
                                response_format={"type": "audio"},
                                generation_config={"speech_config": [{"voice": selected_voice}]}
                            )
                        else:
                            prefix_parts = []
                            if style1 or style2:
                                parts = []
                                if style1: parts.append(f"Make {speaker1} sound {style1}")
                                if style2: parts.append(f"{speaker2} sound {style2}")
                                if parts: prefix_parts.append(" and ".join(parts) + ":\n")
                            if accent1 != "تشخیص خودکار" or accent2 != "تشخیص خودکار":
                                parts = []
                                if accent1 != "تشخیص خودکار": parts.append(f"{speaker1} with {accent_options[accent1]} accent")
                                if accent2 != "تشخیص خودکار": parts.append(f"{speaker2} with {accent_options[accent2]} accent")
                                if parts: prefix_parts.append(" and ".join(parts) + ":\n")
                            prefix = "".join(prefix_parts)
                            processed = prefix + processed
                            if not processed.startswith("TTS the following conversation"):
                                processed = f"TTS the following conversation between {speaker1} and {speaker2}:\n{processed}"

                            speech_config = [
                                {"speaker": speaker1, "voice": voice1},
                                {"speaker": speaker2, "voice": voice2}
                            ]
                            interaction = client.interactions.create(
                                model=tts_model,
                                input=processed,
                                response_format={"type": "audio"},
                                generation_config={"speech_config": speech_config}
                            )
                        break  # موفقیت

                    except Exception as e:
                        err = str(e)
                        if "429" in err or "too_many_requests" in err:
                            st.warning(f"⚠️ محدودیت نرخ (تلاش {attempt+1})")
                            match = re.search(r'retry in (\d+\.?\d*)s', err)
                            wait = float(match.group(1)) if match else retry_delay
                            st.info(f"⏳ {wait:.1f} ثانیه صبر...")
                            time.sleep(wait)
                            if attempt == max_retries - 1:
                                st.error("❌ همچنان خطای سهمیه. بعداً تلاش کنید.")
                        else:
                            st.error(f"❌ خطا: {e}")
                            break

                if interaction is not None:
                    audio_b64 = interaction.output_audio.data
                    pcm_data = base64.b64decode(audio_b64)
                    save_wave("output.wav", pcm_data)
                    st.success("✅ صدا تولید شد!")
                    col_a, col_b = st.columns([2,1])
                    with col_a: st.audio("output.wav")
                    with col_b:
                        with open("output.wav", "rb") as f:
                            st.download_button("⬇️ دانلود", f, "output.wav", mime="audio/wav")
                    if telegram_configured:
                        send_to_telegram("output.wav", f"مدل: {tts_model}\nحروف: {len(text_input)}")

        # نمونه‌ها (بدون تغییر عمده)
        st.header("🎭 نمونه‌های آماده")
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            if st.button("تک‌بلندگو - خوش‌آمدگویی"):
                st.session_state.sample_text = 'Say cheerfully: Have a wonderful day!'
        with sc2:
            if st.button("چندبلندگو - گفتگو"):
                st.session_state.sample_text = f"TTS the following conversation between علی and سارا:\nعلی: سلام!\nسارا: سلام، خوبی؟"
        with sc3:
            if st.button("دراماتیک"):
                st.session_state.sample_text = 'Say in a dramatic voice: In a land far away...'
        if 'sample_text' in st.session_state:
            text_input = st.text_area("متن:", st.session_state.sample_text, height=150, key="sample")

    except Exception as e:
        st.error(f"❌ خطای اتصال: {e}")
else:
    st.info("🔐 لطفاً کلید API را وارد کنید.")
