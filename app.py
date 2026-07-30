import streamlit as st
import wave
import requests
import base64
from google import genai

# 🎵 تابع ذخیره wav
def save_wave(filename, pcm, channels=1, rate=24000, sample_width=2):
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)

# 📨 تابع ارسال فایل به تلگرام
def send_to_telegram(file_path, caption=""):
    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        
        if not bot_token or not chat_id:
            st.warning("⚠️ تنظیمات تلگرام در Secrets یافت نشد")
            return False
        
        url = f"https://api.telegram.org/bot{bot_token}/sendAudio"
        with open(file_path, "rb") as audio_file:
            files = {"audio": audio_file}
            data = {"chat_id": chat_id, "caption": caption, "title": "Gemini TTS"}
            response = requests.post(url, files=files, data=data, timeout=30)
        
        if response.status_code == 200:
            st.success("✅ فایل با موفقیت به تلگرام ارسال شد")
            return True
        else:
            st.error(f"❌ خطا در ارسال به تلگرام: {response.status_code}")
            return False
    except Exception as e:
        st.error(f"❌ خطا در ارسال به تلگرام: {e}")
        return False

# 📊 تابع بررسی طول متن
def validate_text_length(client, text, max_tokens=32000):
    try:
        token_count = client.models.count_tokens(
            model="gemini-2.0-flash", contents=text
        ).total_tokens
        return token_count <= max_tokens, token_count
    except Exception as e:
        st.error(f"خطا در شمارش توکن‌ها: {e}")
        estimated_tokens = len(text) / 4
        st.warning("شمارش توکن‌ها تقریبی است (۴ کاراکتر ≈ ۱ توکن).")
        return estimated_tokens <= max_tokens, estimated_tokens

# 🎭 تابع تولید رونوشت خودکار
def generate_transcript(client, topic, length, speaker1="علی", speaker2="سارا", style="پادکست"):
    prompt = f"""
    یک مکالمه {style} حدود {length} کلمه بین {speaker1} و {speaker2} درباره "{topic}" ایجاد کن.
    قالب خروجی باید به این شکل باشد:
    {speaker1}: متن مکالمه
    {speaker2}: پاسخ مکالمه
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return response.text
    except Exception as e:
        st.error(f"خطا در تولید رونوشت: {e}")
        return None

# 🎨 تنظیمات صفحه
st.set_page_config(
    page_title="Gemini TTS Studio Pro",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🎙️ Gemini TTS Studio Pro")
st.caption("تبدیل متن به گفتار حرفه‌ای با Gemini TTS - مبتنی بر Interactions API")

# 📚 سایدبار
with st.sidebar:
    st.header("🎯 راهنما و تنظیمات")
    
    st.subheader("📮 تنظیمات تلگرام")
    telegram_configured = st.secrets.get("TELEGRAM_BOT_TOKEN") and st.secrets.get("TELEGRAM_CHAT_ID")
    if telegram_configured:
        st.success("✅ تلگرام پیکربندی شده است")
    else:
        st.warning("⚠️ تلگرام پیکربندی نشده است")
    
    st.subheader("📖 دستورات سبک گفتار")
    st.info("""
    **برای کنترل سبک از این قالب‌ها استفاده کنید:**
    - `Say cheerfully: متن شما`
    - `Say in an excited voice: متن شما`
    - `Say slowly: متن شما`
    - `Say at a moderate pace: متن شما`
    - `Say quickly: متن شما`
    - `Make speaker1 sound tired and bored: متن شما`
    """)
    
    st.subheader("⚠️ محدودیت‌ها")
    st.warning("""
    - حداکثر ۳۲,۰۰۰ توکن (مدل‌های Flash)، ۸,۱۹۲ توکن (مدل Pro)
    - فقط ورودی متنی پشتیبانی می‌شود
    - حداکثر ۲ بلندگو در حالت چندبلندگو
    - سرعت گفتار از طریق دستورات متنی قابل کنترل است
    """)

# 🔑 دریافت کلید API
api_key = st.text_input("🔑 کلید API Gemini خود را وارد کنید:", type="password")

if api_key:
    try:
        client = genai.Client(api_key=api_key)

        # 🎛️ تنظیمات پیشرفته
        st.header("⚙️ تنظیمات پیشرفته")
        col1, col2, col3 = st.columns(3)

        with col1:
            mode = st.radio("🎭 حالت گفتار:", ["تک‌بلندگو", "چندبلندگو"])

        with col2:
            tts_model = st.selectbox(
                "🤖 مدل TTS:",
                [
                    "gemini-2.5-flash-tts-preview",
                    "gemini-3.1-flash-tts-preview",
                    "gemini-2.5-pro-preview-tts"   # نام صحیح مطابق مستندات رسمی
                ],
                help="مدل Pro کیفیت بالاتری دارد اما محدودیت ورودی آن ۸,۱۹۲ توکن است."
            )

        with col3:
            speech_rate_option = st.selectbox(
                "🎚️ سرعت گفتار:",
                ["پیش‌فرض", "آهسته", "متوسط", "سریع"],
            )
            
            speed_commands = {
                "پیش‌فرض": "",
                "آهسته": "Say slowly",
                "متوسط": "Say at a moderate pace", 
                "سریع": "Say quickly"
            }

        # 🌐 لهجه‌ها
        accent_options = {
            "تشخیص خودکار": None,
            "عربی (مصر)": "ar-EG", "آلمانی (آلمان)": "de-DE", "انگلیسی (آمریکا)": "en-US",
            "اسپانیایی (آمریکا)": "es-US", "فرانسوی (فرانسه)": "fr-FR", "هندی (هند)": "hi-IN",
            "اندونزیایی (اندونزی)": "id-ID", "ایتالیایی (ایتالیا)": "it-IT", "ژاپنی (ژاپن)": "ja-JP",
            "کره‌ای (کره)": "ko-KR", "پرتغالی (برزیل)": "pt-BR", "روسی (روسیه)": "ru-RU",
            "هلندی (هلند)": "nl-NL", "لهستانی (لهستان)": "pl-PL", "تایلندی (تایلند)": "th-TH",
            "ترکی (ترکیه)": "tr-TR", "ویتنامی (ویتنام)": "vi-VN", "رومانیایی (رومانی)": "ro-RO",
            "اوکراینی (اوکراین)": "uk-UA", "بنگالی (بنگلادش)": "bn-BD", 
            "انگلیسی (هند)": "en-IN", "مراتی (هند)": "mr-IN", "تامیل (هند)": "ta-IN", "تلوگو (هند)": "te-IN"
        }

        # 🔊 لیست صداها
        all_voices = [
            "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", 
            "Orus", "Aoede", "Callirrhoe", "Autonoe", "Enceladus", "Iapetus",
            "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi",
            "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux", "Pulcherrima",
            "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat"
        ]

        voice_descriptions = {
            "Zephyr": "Bright", "Puck": "Upbeat", "Charon": "Informative",
            "Kore": "Firm", "Fenrir": "Excitable", "Leda": "Youthful",
            "Orus": "Firm", "Aoede": "Breezy", "Callirrhoe": "Easy-going",
            "Autonoe": "Bright", "Enceladus": "Breathy", "Iapetus": "Clear",
            "Umbriel": "Easy-going", "Algieba": "Smooth", "Despina": "Smooth",
            "Erinome": "Clear", "Algenib": "Gravelly", "Rasalgethi": "Informative",
            "Laomedeia": "Upbeat", "Achernar": "Soft", "Alnilam": "Firm",
            "Schedar": "Even", "Gacrux": "Mature", "Pulcherrima": "Forward",
            "Achird": "Friendly", "Zubenelgenubi": "Casual", "Vindemiatrix": "Gentle",
            "Sadachbia": "Lively", "Sadaltager": "Knowledgeable", "Sulafat": "Warm"
        }

        # 🎤 تولید خودکار رونوشت
        auto_generate = st.checkbox("🤖 تولید خودکار رونوشت")
        if auto_generate:
            st.subheader("🤖 تولید خودکار رونوشت")
            gen_col1, gen_col2, gen_col3 = st.columns(3)
            with gen_col1:
                topic = st.text_input("🎯 موضوع مکالمه:", "تکنولوژی و هوش مصنوعی")
            with gen_col2:
                style = st.selectbox("📝 سبک رونوشت:", ["پادکست", "مصاحبه", "گفتگوی دوستانه", "بحث علمی", "داستان"])
            with gen_col3:
                length = st.slider("📏 طول رونوشت (کلمه):", 50, 300, 150)
            if st.button("🪄 تولید رونوشت", key="generate_transcript"):
                with st.spinner("در حال تولید رونوشت..."):
                    transcript = generate_transcript(client, topic, length, style=style)
                    if transcript:
                        st.session_state.generated_transcript = transcript
                        st.success("رونوشت با موفقیت تولید شد!")

        # 📝 متن ورودی
        st.header("📝 متن ورودی")
        if mode == "چندبلندگو":
            st.info("""
            **قالب پیشنهادی برای چندبلندگو:**
            ```
            TTS the following conversation between علی and سارا:
            علی: سلام سارا! امروز چطوری؟
            سارا: سلام علی! خوبم ممنون. تو چطور؟
            ```
            """)

        if 'generated_transcript' in st.session_state and auto_generate:
            text_input = st.text_area("📝 متن مورد نظر:", value=st.session_state.generated_transcript, height=200)
        else:
            text_input = st.text_area("📝 متن مورد نظر:", height=200,
                                      placeholder='مثال: Say cheerfully: Have a wonderful day!')

        # 👥 انتخاب صداها
        if mode == "تک‌بلندگو":
            st.subheader("👤 تنظیمات تک‌بلندگو")
            col1, col2, col3 = st.columns(3)
            with col1:
                selected_voice = st.selectbox("انتخاب صدا:", options=all_voices,
                                              format_func=lambda x: f"{x} - {voice_descriptions.get(x, '')}",
                                              index=all_voices.index("Kore"))
            with col2:
                style_instruction = st.text_input("🎭 دستور سبک (اختیاری):", placeholder='مثال: Say cheerfully')
            with col3:
                selected_accent = st.selectbox("🎤 لهجه (اختیاری):", list(accent_options.keys()), index=0)
        else:
            st.subheader("👥 تنظیمات چندبلندگو")
            col1, col2 = st.columns(2)
            with col1:
                speaker1 = st.text_input("👤 نام گوینده ۱:", "علی")
                voice1 = st.selectbox("صدا گوینده ۱:", options=all_voices,
                                      index=all_voices.index("Kore"),
                                      format_func=lambda x: f"{x} - {voice_descriptions.get(x, '')}", key="v1")
                style1 = st.text_input("🎭 سبک گوینده ۱ (اختیاری):", placeholder="مثال: tired and bored")
                accent1 = st.selectbox("🎤 لهجه گوینده ۱ (اختیاری):", list(accent_options.keys()), index=0, key="a1")
            with col2:
                speaker2 = st.text_input("👤 نام گوینده ۲:", "سارا")
                voice2 = st.selectbox("صدا گوینده ۲:", options=all_voices,
                                      index=all_voices.index("Puck"),
                                      format_func=lambda x: f"{x} - {voice_descriptions.get(x, '')}", key="v2")
                style2 = st.text_input("🎭 سبک گوینده ۲ (اختیاری):", placeholder="مثال: excited and happy")
                accent2 = st.selectbox("🎤 لهجه گوینده ۲ (اختیاری):", list(accent_options.keys()), index=0, key="a2")

        # تعیین محدودیت توکن بر اساس مدل
        max_tokens = 8192 if "pro" in tts_model else 32000

        # 📊 بررسی طول متن
        if text_input:
            is_valid, token_count = validate_text_length(client, text_input, max_tokens)
            progress = min(token_count / max_tokens, 1.0)
            st.progress(progress)
            if not is_valid:
                st.error(f"❌ متن بسیار طولانی! تعداد توکن‌ها: {token_count:.0f} از {max_tokens}")
            else:
                st.success(f"✅ طول متن مناسب است. تعداد توکن‌ها: {token_count:.0f} از {max_tokens}")

        # 🎧 دکمه تولید صدا
        if st.button("🎧 تولید صدا", type="primary", use_container_width=True,
                     disabled=not text_input.strip() or (text_input and not is_valid)):
            try:
                with st.spinner("🔮 در حال تولید صدا..."):
                    processed_text = text_input
                    speed_command = speed_commands[speech_rate_option]
                    if speed_command:
                        processed_text = f"{speed_command}: {processed_text}"
                    
                    if mode == "تک‌بلندگو":
                        if style_instruction:
                            processed_text = f"{style_instruction}: {processed_text}"
                        if selected_accent != "تشخیص خودکار":
                            processed_text = f"Language {accent_options[selected_accent]}: {processed_text}"

                        interaction = client.interactions.create(
                            model=tts_model,
                            input=processed_text,
                            response_format={"type": "audio"},
                            generation_config={
                                "speech_config": [{"voice": selected_voice}]
                            }
                        )
                    else:
                        prefix_parts = []
                        if style1 or style2:
                            style_parts = []
                            if style1: style_parts.append(f"Make {speaker1} sound {style1}")
                            if style2: style_parts.append(f"{speaker2} sound {style2}")
                            if style_parts: prefix_parts.append(" and ".join(style_parts) + ":\n")
                        if accent1 != "تشخیص خودکار" or accent2 != "تشخیص خودکار":
                            accent_parts = []
                            if accent1 != "تشخیص خودکار": accent_parts.append(f"{speaker1} with {accent_options[accent1]} accent")
                            if accent2 != "تشخیص خودکار": accent_parts.append(f"{speaker2} with {accent_options[accent2]} accent")
                            if accent_parts: prefix_parts.append(" and ".join(accent_parts) + ":\n")
                        prefix = "".join(prefix_parts)
                        processed_text = prefix + processed_text
                        if not processed_text.startswith("TTS the following conversation"):
                            processed_text = f"TTS the following conversation between {speaker1} and {speaker2}:\n{processed_text}"

                        speech_config = [
                            {"speaker": speaker1, "voice": voice1},
                            {"speaker": speaker2, "voice": voice2}
                        ]
                        interaction = client.interactions.create(
                            model=tts_model,
                            input=processed_text,
                            response_format={"type": "audio"},
                            generation_config={"speech_config": speech_config}
                        )

                    # ذخیره صدا
                    audio_b64 = interaction.output_audio.data
                    pcm_data = base64.b64decode(audio_b64)
                    file_name = "output.wav"
                    save_wave(file_name, pcm_data)

                    st.success("✅ تولید صدا با موفقیت انجام شد!")
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.audio(file_name, format="audio/wav")
                    with col2:
                        with open(file_name, "rb") as f:
                            st.download_button("⬇️ دانلود فایل صوتی", data=f, file_name=file_name, mime="audio/wav",
                                               use_container_width=True)

                    if telegram_configured:
                        with st.spinner("📤 در حال ارسال به تلگرام..."):
                            caption = f"Gemini TTS Studio Pro\nمدل: {tts_model}\nکاراکترها: {len(text_input)}"
                            send_to_telegram(file_name, caption)

                    st.subheader("📊 اطلاعات تولید")
                    info_col1, info_col2, info_col3 = st.columns(3)
                    with info_col1:
                        st.metric("طول متن", f"{len(text_input)} کاراکتر")
                    with info_col2:
                        st.metric("تعداد توکن‌ها", f"{token_count:.0f}")
                    with info_col3:
                        if mode == "تک‌بلندگو":
                            st.metric("صدا", f"{selected_voice} (سرعت: {speech_rate_option})")
                        else:
                            st.metric("بلندگوها", f"{speaker1}: {voice1}, {speaker2}: {voice2}")

            except Exception as e:
                st.error(f"❌ خطا در تولید صدا: {e}")

        # 📚 نمونه‌های آماده
        st.header("🎭 نمونه‌های آماده")
        sample_col1, sample_col2, sample_col3 = st.columns(3)
        with sample_col1:
            if st.button("نمونه تک‌بلندگو - خوش‌آمدگویی", use_container_width=True):
                st.session_state.sample_text = 'Say cheerfully: Have a wonderful day!'
        with sample_col2:
            if st.button("نمونه چندبلندگو - گفتگوی روزمره", use_container_width=True):
                st.session_state.sample_text = f"""TTS the following conversation between {speaker1} and {speaker2}:
{speaker1}: سلام! امروز چطوری؟
{speaker2}: خوبم ممنون. تو چطور؟"""
        with sample_col3:
            if st.button("نمونه دراماتیک - داستان", use_container_width=True):
                st.session_state.sample_text = 'Say in a dramatic voice: In a land far away, a hero embarked on an epic journey.'

        if 'sample_text' in st.session_state:
            text_input = st.text_area("📝 متن مورد نظر:", st.session_state.sample_text, height=150, key="sample_text_area")

    except Exception as e:
        st.error(f"❌ خطا در اتصال به API: {e}")
else:
    st.info("🔐 برای شروع، کلید API خود را وارد کنید.")
