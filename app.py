import streamlit as st
import wave
import requests
import io
from google import genai
from google.genai import types

# 🎵 تابع ذخیره wav
def save_wave(filename, pcm, channels=1, rate=24000, sample_width=2):
    """ذخیره فایل صوتی با پارامترهای قابل تنظیم"""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)

# 📨 تابع ارسال فایل به تلگرام
def send_to_telegram(file_path, caption=""):
    """ارسال فایل به ربات تلگرام از طریق Secrets"""
    try:
        # خواندن تنظیمات تلگرام از Secrets
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "")
        
        if not bot_token or not chat_id:
            st.warning("⚠️ تنظیمات تلگرام در Secrets یافت نشد")
            return False
        
        url = f"https://api.telegram.org/bot{bot_token}/sendAudio"
        
        with open(file_path, "rb") as audio_file:
            files = {"audio": audio_file}
            data = {
                "chat_id": chat_id,
                "caption": caption,
                "title": "Gemini TTS Output"
            }
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
    """بررسی محدودیت طول متن بر اساس توکن با استفاده از API"""
    try:
        token_count = client.models.count_tokens(
            model="gemini-2.0-flash", contents=text
        ).total_tokens
        return token_count <= max_tokens, token_count
    except Exception as e:
        st.error(f"خطا در شمارش توکن‌ها: {e}")
        # در صورت خطا، تخمین تقریبی
        estimated_tokens = len(text) / 4
        st.warning("شمارش توکن‌ها تقریبی است (۴ کاراکتر ≈ ۱ توکن).")
        return estimated_tokens <= max_tokens, estimated_tokens

# 🎭 تابع تولید رونوشت خودکار
def generate_transcript(client, topic, length, speaker1="علی", speaker2="سارا", style="پادکست"):
    """تولید خودکار رونوشت با Gemini"""
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
        if "404" in str(e):
            st.error("مدل gemini-2.0-flash در دسترس نیست. لطفاً کلید API یا دستابی به مدل را بررسی کنید.")
        return None

# 🎨 تنظیمات صفحه
st.set_page_config(
    page_title="Gemini TTS Studio Pro",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 🎯 عنوان و راهنما
st.title("🎙️ Gemini TTS Studio Pro")
st.caption("تبدیل متن به گفتار حرفه‌ای با Gemini TTS - نسخه به‌روز شده بر اساس مستندات رسمی")

# 📚 سایدبار برای راهنما و تنظیمات پیشرفته
with st.sidebar:
    st.header("🎯 راهنما و تنظیمات")
    
    # بخش تنظیمات تلگرام (فقط برای نمایش اطلاعات)
    st.subheader("📮 تنظیمات تلگرام")
    telegram_configured = st.secrets.get("TELEGRAM_BOT_TOKEN") and st.secrets.get("TELEGRAM_CHAT_ID")
    if telegram_configured:
        st.success("✅ تلگرام پیکربندی شده است")
        st.info("فایل‌ها به طور خودکار ارسال می‌شوند")
    else:
        st.warning("⚠️ تلگرام پیکربندی نشده است")
        st.info("برای فعال‌سازی، Secrets را در تنظیمات تنظیم کنید")
    
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
    
    st.subheader("🔊 گزینه‌های صوتی و لهجه")
    st.caption("۳۰ گزینه صوتی و ۲۴ لهجه (کد BCP-47) از مستندات پشتیبانی می‌شوند")
    
    st.subheader("⚠️ محدودیت‌ها")
    st.warning("""
    - حداکثر ۳۲,۰۰۰ توکن در هر درخواست
    - فقط ورودی متنی پشتیبانی می‌شود
    - حداکثر ۲ بلندگو در حالت چندبلندگو
    - مدل‌های TTS در حالت پیش‌نمایش هستند
    - سرعت گفتار از طریق دستورات متنی قابل کنترل است
    """)
    
    st.subheader("🌐 زبان و لهجه")
    st.info("زبان و لهجه به‌صورت خودکار تشخیص داده می‌شود، اما می‌توانید کد BCP-47 خاصی را برای لهجه انتخاب کنید.")

# 🔑 دریافت کلید API از کاربر
api_key = st.text_input("🔑 کلید API Gemini خود را وارد کنید:", type="password")

if api_key:
    try:
        client = genai.Client(api_key=api_key)

        # 🎛️ بخش تنظیمات پیشرفته
        st.header("⚙️ تنظیمات پیشرفته")
        col1, col2, col3 = st.columns(3)

        with col1:
            mode = st.radio("🎭 حالت گفتار:", ["تک‌بلندگو", "چندبلندگو"])

        with col2:
            tts_model = st.selectbox(
                "🤖 مدل TTS:",
                ["gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"],
                help="مدل‌های TTS در حالت پیش‌نمایش هستند."
            )

        with col3:
            speech_rate_option = st.selectbox(
                "🎚️ سرعت گفتار:",
                ["پیش‌فرض", "آهسته", "متوسط", "سریع"],
                help="سرعت گفتار از طریق دستورات متنی کنترل می‌شود"
            )
            
            # نگاشت سرعت به دستورات متنی مطابق مستندات
            speed_commands = {
                "پیش‌فرض": "",
                "آهسته": "Say slowly",
                "متوسط": "Say at a moderate pace", 
                "سریع": "Say quickly"
            }

        # 🌐 لیست کامل لهجه‌ها (کدهای BCP-47 از مستندات TTS)
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

        # 🔊 لیست کامل گزینه‌های صوتی (۳۰ گزینه مطابق مستندات)
        all_voices = [
            "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", 
            "Orus", "Aoede", "Callirrhoe", "Autonoe", "Enceladus", "Iapetus",
            "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi",
            "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux", "Pulcherrima",
            "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat"
        ]

        # 🎵 توصیفات صداها (مطابق مستندات رسمی)
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

        # 🎤 بخش تولید رونوشت خودکار
        auto_generate = st.checkbox("🤖 تولید خودکار رونوشت")
        if auto_generate:
            st.subheader("🤖 تولید خودکار رونوشت")
            gen_col1, gen_col2, gen_col3 = st.columns(3)

            with gen_col1:
                topic = st.text_input("🎯 موضوع مکالمه:", "تکنولوژی و هوش مصنوعی")

            with gen_col2:
                style = st.selectbox(
                    "📝 سبک رونوشت:",
                    ["پادکست", "مصاحبه", "گفتگوی دوستانه", "بحث علمی", "داستان"]
                )

            with gen_col3:
                length = st.slider("📏 طول رونوشت (کلمه):", 50, 300, 150)

            if st.button("🪄 تولید رونوشت", key="generate_transcript"):
                with st.spinner("در حال تولید رونوشت..."):
                    transcript = generate_transcript(client, topic, length, style=style)
                    if transcript:
                        st.session_state.generated_transcript = transcript
                        st.success("رونوشت با موفقیت تولید شد!")

        # 📝 بخش متن ورودی
        st.header("📝 متن ورودی")
        
        if mode == "چندبلندگو":
            st.info("""
            **قالب پیشنهادی برای چندبلندگو (مطابق مستندات):**
            ```
            TTS the following conversation between علی and سارا:
            علی: سلام سارا! امروز چطوری؟
            سارا: سلام علی! خوبم ممنون. تو چطور؟
            ```
            **یا با دستورات سبک:**
            ```
            Make علی sound tired and bored, and سارا sound excited and happy:
            علی: So... what's on the agenda today?
            سارا: You're never going to guess!
            ```
            """)

        if 'generated_transcript' in st.session_state and auto_generate:
            text_input = st.text_area(
                "📝 متن مورد نظر:",
                value=st.session_state.generated_transcript,
                height=200,
                placeholder='مثال: Say cheerfully: Have a wonderful day!'
            )
        else:
            text_input = st.text_area(
                "📝 متن مورد نظر:",
                height=200,
                placeholder='مثال: Say cheerfully: Have a wonderful day! یا برای چندبلندگو از قالب بالا استفاده کنید'
            )

        # 👥 بخش انتخاب صداها و لهجه‌ها
        if mode == "تک‌بلندگو":
            st.subheader("👤 تنظیمات تک‌بلندگو")
            col1, col2, col3 = st.columns(3)

            with col1:
                selected_voice = st.selectbox(
                    "انتخاب صدا:",
                    options=all_voices,
                    format_func=lambda x: f"{x} - {voice_descriptions.get(x, '')}",
                    index=all_voices.index("Kore")
                )

            with col2:
                style_instruction = st.text_input(
                    "🎭 دستور سبک (اختیاری):",
                    placeholder='مثال: Say cheerfully'
                )

            with col3:
                selected_accent = st.selectbox(
                    "🎤 لهجه (اختیاری):",
                    list(accent_options.keys()),
                    index=0,
                    help="لهجه با کد BCP-47 مشخص می‌شود."
                )

        else:
            st.subheader("👥 تنظیمات چندبلندگو")
            col1, col2 = st.columns(2)

            with col1:
                speaker1 = st.text_input("👤 نام گوینده ۱:", "علی")
                voice1 = st.selectbox(
                    "صدا گوینده ۱:",
                    options=all_voices,
                    index=all_voices.index("Kore"),
                    format_func=lambda x: f"{x} - {voice_descriptions.get(x, '')}",
                    key="v1"
                )
                style1 = st.text_input("🎭 سبک گوینده ۱ (اختیاری):", placeholder="مثال: tired and bored")
                accent1 = st.selectbox(
                    "🎤 لهجه گوینده ۱ (اختیاری):",
                    list(accent_options.keys()),
                    index=0,
                    key="a1"
                )

            with col2:
                speaker2 = st.text_input("👤 نام گوینده ۲:", "سارا")
                voice2 = st.selectbox(
                    "صدا گوینده ۲:",
                    options=all_voices,
                    index=all_voices.index("Puck"),
                    format_func=lambda x: f"{x} - {voice_descriptions.get(x, '')}",
                    key="v2"
                )
                style2 = st.text_input("🎭 سبک گوینده ۲ (اختیاری):", placeholder="مثال: excited and happy")
                accent2 = st.selectbox(
                    "🎤 لهجه گوینده ۲ (اختیاری):",
                    list(accent_options.keys()),
                    index=0,
                    key="a2"
                )

        # 📊 بررسی طول متن
        if text_input:
            is_valid, token_count = validate_text_length(client, text_input)
            progress = min(token_count / 32000, 1.0)

            st.progress(progress)

            if not is_valid:
                st.error(f"❌ متن بسیار طولانی! تعداد توکن‌ها: {token_count:.0f} از 32,000")
                st.warning("لطفاً متن را کوتاه کنید.")
            else:
                st.success(f"✅ طول متن مناسب است. تعداد توکن‌ها: {token_count:.0f} از 32,000")

        # 🎧 دکمه تولید صدا
        if st.button(
            "🎧 تولید صدا",
            type="primary",
            use_container_width=True,
            disabled=not text_input.strip() or (text_input and not is_valid)
        ):
            try:
                with st.spinner("🔮 در حال تولید صدا..."):
                    processed_text = text_input
                    
                    # افزودن دستور سرعت به متن (اگر انتخاب شده باشد)
                    speed_command = speed_commands[speech_rate_option]
                    if speed_command:
                        processed_text = f"{speed_command}: {processed_text}"
                    
                    if mode == "تک‌بلندگو":
                        # افزودن دستورات سبک و لهجه به صورت متنی
                        if style_instruction:
                            processed_text = f"{style_instruction}: {processed_text}"
                        
                        if selected_accent != "تشخیص خودکار":
                            processed_text = f"Language {accent_options[selected_accent]}: {processed_text}"

                        response = client.models.generate_content(
                            model=tts_model,
                            contents=processed_text,
                            config=types.GenerateContentConfig(
                                response_modalities=["AUDIO"],
                                speech_config=types.SpeechConfig(
                                    voice_config=types.VoiceConfig(
                                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                            voice_name=selected_voice
                                        )
                                    )
                                )
                            )
                        )
                    else:
                        # ساخت قالب چندبلندگو مطابق مستندات
                        style_prefix = ""
                        accent_prefix = ""
                        
                        # ساخت پیشوند دستورات سبک
                        if style1 or style2:
                            style_parts = []
                            if style1:
                                style_parts.append(f"Make {speaker1} sound {style1}")
                            if style2:
                                style_parts.append(f"{speaker2} sound {style2}")
                            style_prefix = " and ".join(style_parts) + ":\n"
                        
                        # ساخت پیشوند دستورات لهجه
                        if accent1 != "تشخیص خودکار" or accent2 != "تشخیص خودکار":
                            accent_parts = []
                            if accent1 != "تشخیص خودکار":
                                accent_parts.append(f"{speaker1} with {accent_options[accent1]} accent")
                            if accent2 != "تشخیص خودکار":
                                accent_parts.append(f"{speaker2} with {accent_options[accent2]} accent")
                            if accent_parts:
                                accent_prefix = " and ".join(accent_parts) + ":\n"
                        
                        # ترکیب تمام پیشوندها
                        prefix = accent_prefix + style_prefix
                        if prefix:
                            processed_text = prefix + processed_text
                        
                        # اضافه کردن قالب TTS برای چندبلندگو
                        if not processed_text.startswith("TTS the following conversation"):
                            processed_text = f"TTS the following conversation between {speaker1} and {speaker2}:\n{processed_text}"

                        response = client.models.generate_content(
                            model=tts_model,
                            contents=processed_text,
                            config=types.GenerateContentConfig(
                                response_modalities=["AUDIO"],
                                speech_config=types.SpeechConfig(
                                    multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                                        speaker_voice_configs=[
                                            types.SpeakerVoiceConfig(
                                                speaker=speaker1,
                                                voice_config=types.VoiceConfig(
                                                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                                        voice_name=voice1
                                                    )
                                                )
                                            ),
                                            types.SpeakerVoiceConfig(
                                                speaker=speaker2,
                                                voice_config=types.VoiceConfig(
                                                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                                        voice_name=voice2
                                                    )
                                                )
                                            )
                                        ]
                                    )
                                )
                            )
                        )

                    data = response.candidates[0].content.parts[0].inline_data.data
                    file_name = "output.wav"
                    save_wave(file_name, data)

                    st.success("✅ تولید صدا با موفقیت انجام شد!")

                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.audio(file_name, format="audio/wav")
                    with col2:
                        with open(file_name, "rb") as f:
                            st.download_button(
                                "⬇️ دانلود فایل صوتی",
                                data=f,
                                file_name=file_name,
                                mime="audio/wav",
                                use_container_width=True
                            )

                    # 📮 ارسال خودکار به تلگرام
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
                if "404" in str(e) or "model_not_found" in str(e):
                    st.error(f"مدل {tts_model} در دسترس نیست. لطفاً کلید API یا دسترسی به مدل را بررسی کنید.")
                elif "extra_forbidden" in str(e):
                    st.error("تنظیمات غیرمجاز در API شناسایی شد. لطفاً تنظیمات را بررسی کنید.")
                else:
                    st.info("💡 ممکن است کلید API نامعتبر باشد یا سرویس دچار مشکل شده باشد. مدل‌های TTS در حالت پیش‌نمایش هستند.")

        # 📚 بخش نمونه‌های آماده
        st.header("🎭 نمونه‌های آماده")
        sample_col1, sample_col2, sample_col3 = st.columns(3)

        with sample_col1:
            if st.button("نمونه تک‌بلندگو - خوش‌آمدگویی", use_container_width=True):
                st.session_state.sample_text = 'Say cheerfully: Have a wonderful day! Welcome to Gemini TTS Studio Pro!'

        with sample_col2:
            if st.button("نمونه چندبلندگو - گفتگوی روزمره", use_container_width=True):
                st.session_state.sample_text = f"""TTS the following conversation between {speaker1} and {speaker2}:
{speaker1}: سلام! امروز چطوری؟
{speaker2}: خوبم ممنون. تو چطور؟"""

        with sample_col3:
            if st.button("نمونه دراماتیک - داستان", use_container_width=True):
                st.session_state.sample_text = 'Say in a dramatic voice: In a land far away, a hero embarked on an epic journey filled with challenges and triumphs.'

        if 'sample_text' in st.session_state:
            text_input = st.text_area("📝 متن مورد نظر:", st.session_state.sample_text, height=150, key="sample_text_area")

    except ValueError as e:
        st.error(f"❌ خطای کلید API: کلید نامعتبر است. لطفاً کلید را بررسی کنید.")
    except Exception as e:
        st.error(f"❌ خطا در اتصال به API: {e}")
        st.info("🔑 لطفاً از صحت کلید API اطمینان حاصل کنید")
else:
    st.info("🔐 برای شروع، کلید API خود را وارد کنید.")
    st.markdown("""
    ### 📋 راهنمای دریافت کلید API:
    1. به Google AI Studio بروید
    2. وارد حساب Google خود شوید
    3. از بخش API Keys یک کلید جدید ایجاد کنید
    4. کلید را در فیلد بالا وارد کنید

    ### 🔧 راهنمای تنظیم تلگرام:
    **برای فعال‌سازی ارسال خودکار به تلگرام:**
    1. در Streamlit Cloud، به بخش Settings → Secrets بروید
    2. مقادیر زیر را اضافه کنید:
    ```
    TELEGRAM_BOT_TOKEN = "توکن_ربات_شما"
    TELEGRAM_CHAT_ID = "چت_آیدی_شما"
    ```
    3. ربات را از @BotFather ایجاد کنید و چت آیدی خود را از @userinfobot دریافت کنید

    ### 🆕 قابلیت‌های جدید در این نسخه:
    - ✅ پشتیبانی از مدل‌های Gemini 2.5 Flash/Pro Preview TTS
    - ✅ ۳۰ گزینه صوتی کامل مطابق مستندات
    - ✅ ۲۴ لهجه پشتیبانی شده (کد BCP-47)
    - ✅ قالب چندبلندگو مطابق مستندات رسمی
    - ✅ دستورات سبک به زبان انگلیسی (مطابق مستندات)
    - ✅ ارسال خودکار به تلگرام از طریق Secrets
    - ✅ مدیریت خطاهای بهبود یافته
    - ✅ سازگاری کامل با مستندات جدید Gemini API
    """)
