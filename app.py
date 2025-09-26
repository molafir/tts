import streamlit as st
import wave
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
            model="gemini-2.0-flash",  # مدل به‌روز برای تولید متن
            contents=prompt
        )
        return response.text
    except Exception as e:
        st.error(f"خطا در تولید رونوشت: {e}")
        if "404" in str(e):
            st.error("مدل gemini-2.0-flash در دسترس نیست. لطفاً کلید API یا دسترسی به مدل را بررسی کنید.")
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
st.caption("تبدیل متن به گفتار حرفه‌ای با Gemini TTS - از تمام قابلیت‌های مستندات استفاده شده است")

# 📚 سایدبار برای راهنما و تنظیمات پیشرفته
with st.sidebar:
    st.header("🎯 راهنما و تنظیمات")
    st.subheader("📖 دستورات سبک گفتار")
    st.info("""
    **برای کنترل سبک از این قالب‌ها استفاده کنید:**
    - `با لحن شاد: متن شما`
    - `به صورت هیجان‌زده: متن شما`
    - `با صدای آرام: متن شما`
    """)
    st.subheader("🔊 گزینه‌های صوتی")
    st.caption("۳۰ گزینه صوتی از مستندات پشتیبانی می‌شوند")
    st.subheader("⚠️ محدودیت‌ها")
    st.warning("""
    - حداکثر ۳۲,۰۰۰ توکن در هر درخواست
    - فقط ورودی متنی پشتیبانی می‌شود
    - حداکثر ۲ بلندگو در حالت چندبلندگو
    - مدل‌های TTS در حالت پیش‌نمایش هستند و ممکن است ناپایدار باشند
    """)
    st.subheader("🌐 زبان")
    st.info("زبان به‌صورت خودکار تشخیص داده می‌شود، اما می‌توانید زبان خاصی را انتخاب کنید.")

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
            speech_rate = st.slider("🎤 سرعت گفتار:", 0.5, 2.0, 1.0, 0.1)

        # 🌐 انتخاب زبان (اختیاری)
        language_options = {
            "تشخیص خودکار": None,
            "فارسی": "fa-IR",
            "انگلیسی": "en-US",
            "عربی": "ar-EG",
            "فرانسوی": "fr-FR",
            "اسپانیایی": "es-US"
        }
        language = st.selectbox(
            "🌐 زبان (اختیاری - پیش‌فرض: تشخیص خودکار):",
            list(language_options.keys()),
            help="زبان به‌صورت خودکار تشخیص داده می‌شود، اما می‌توانید کد BCP-47 خاصی را انتخاب کنید."
        )

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
            **قالب پیشنهادی برای چندبلندگو:**
            ```
            گوینده۱: متن مورد نظر
            گوینده۲: پاسخ گوینده دوم
            ```
            یا از دستورات سبک استفاده کنید:
            ```
            گوینده۱ را خسته و بی‌حال و گوینده۲ را هیجان‌زده و شاد نشان بده:
            گوینده۱: خب... برنامۀ امروز چیه؟
            گوینده۲: هرگز حدس نمی‌زنی!
            ```
            """)

        if 'generated_transcript' in st.session_state and auto_generate:
            text_input = st.text_area(
                "📝 متن مورد نظر:",
                value=st.session_state.generated_transcript,
                height=200,
                placeholder="مثال: با لحن شاد: متن شما..."
            )
        else:
            text_input = st.text_area(
                "📝 متن مورد نظر:",
                height=200,
                placeholder="مثال: با لحن شاد: متن شما... یا برای چندبلندگو از قالب بالا استفاده کنید"
            )

        # 🔊 لیست کامل گزینه‌های صوتی
        all_voices = [
            "Zephyr", "Puck", "Sharon", "Kore", "Aurorus", "Fenrir",
            "Spring", "Leda", "Aoede", "Callirrhoe", "Autonoe", "Enceladus",
            "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome", "Algenib",
            "Rasalgethi", "Laomedeia", "Achernar", "Elnath", "Schedar", "Gacrux",
            "Pulcherrima", "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia",
            "Sadaltager", "Sulafat"
        ]

        voice_descriptions = {
            "Zephyr": "روشن و شفاف", "Puck": "شاداب و پرانرژی", "Sharon": "آموزنده و واضح",
            "Kore": "محکم و مطمئن", "Aurorus": "گرم و دوستانه", "Fenrir": "هیجان‌انگیز",
            "Spring": "تازه و جوان", "Leda": "ملایم و آرام", "Aoede": "نسیمی و سبک",
            "Callirrhoe": "آسان‌گیر", "Autonoe": "درخشان", "Enceladus": "نفس‌گیر",
            "Iapetus": "روشن", "Umbriel": "آسان‌گیر", "Algieba": "صاف و نرم",
            "Despina": "صاف", "Erinome": "درخشان", "Algenib": "زبر و سنگریزه‌ای",
            "Rasalgethi": "آموزنده", "Laomedeia": "خوش‌بین", "Achernar": "نرم",
            "Elnath": "محکم", "Schedar": "یکنواخت", "Gacrux": "بالغ",
            "Pulcherrima": "رو به جلو", "Achird": "دوستانه", "Zubenelgenubi": "گاه‌به‌گاه",
            "Vindemiatrix": "ملایم", "Sadachbia": "سرزنده", "Sadaltager": "دانا",
            "Sulafat": "گرم"
        }

        # 👥 بخش انتخاب صداها
        if mode == "تک‌بلندگو":
            st.subheader("👤 تنظیمات تک‌بلندگو")
            col1, col2 = st.columns(2)

            with col1:
                selected_voice = st.selectbox(
                    "انتخاب صدا:",
                    options=all_voices,
                    format_func=lambda x: f"{x} - {voice_descriptions.get(x, '')}"
                )

            with col2:
                style_instruction = st.text_input(
                    "🎭 دستور سبک (اختیاری):",
                    placeholder="مثال: با لحن شاد بگو"
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
                style1 = st.text_input("🎭 سبک گوینده ۱ (اختیاری):", placeholder="مثال: خسته و بی‌حال")

            with col2:
                speaker2 = st.text_input("👤 نام گوینده ۲:", "سارا")
                voice2 = st.selectbox(
                    "صدا گوینده ۲:",
                    options=all_voices,
                    index=all_voices.index("Puck"),
                    format_func=lambda x: f"{x} - {voice_descriptions.get(x, '')}",
                    key="v2"
                )
                style2 = st.text_input("🎭 سبک گوینده ۲ (اختیاری):", placeholder="مثال: هیجان‌زده و شاد")

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
            disabled=not text_input.strip() or not is_valid
        ):
            try:
                with st.spinner("🔮 در حال تولید صدا..."):
                    processed_text = text_input
                    if language != "تشخیص خودکار":
                        processed_text = f"Language {language_options[language]}: {text_input}"

                    if mode == "تک‌بلندگو":
                        if style_instruction:
                            processed_text = f"{style_instruction}: {text_input}"

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
                                    ),
                                    rate=speech_rate
                                )
                            )
                        )
                    else:
                        style_prefix = ""
                        if style1 or style2:
                            style_parts = []
                            if style1:
                                style_parts.append(f"{speaker1} را {style1}")
                            if style2:
                                style_parts.append(f"{speaker2} را {style2}")
                            style_prefix = " و ".join(style_parts) + " نشان بده:\n"
                            processed_text = style_prefix + processed_text

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
                                    ),
                                    rate=speech_rate
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

                    st.subheader("📊 اطلاعات تولید")
                    info_col1, info_col2, info_col3 = st.columns(3)
                    with info_col1:
                        st.metric("طول متن", f"{len(text_input)} کاراکتر")
                    with info_col2:
                        st.metric("تعداد توکن‌ها", f"{token_count:.0f}")
                    with info_col3:
                        if mode == "تک‌بلندگو":
                            st.metric("صدا", selected_voice)
                        else:
                            st.metric("بلندگوها", "2")

            except Exception as e:
                st.error(f"❌ خطا در تولید صدا: {e}")
                if "404" in str(e):
                    st.error(f"مدل {tts_model} در دسترس نیست. لطفاً کلید API یا دسترسی به مدل را بررسی کنید.")
                else:
                    st.info("💡 ممکن است کلید API نامعتبر باشد یا سرویس دچار مشکل شده باشد. مدل‌های TTS در حالت پیش‌نمایش هستند.")

        # 📚 بخش نمونه‌های آماده
        st.header("🎭 نمونه‌های آماده")
        sample_col1, sample_col2, sample_col3 = st.columns(3)

        with sample_col1:
            if st.button("نمونه تک‌بلندگو - خوش‌آمدگویی", use_container_width=True):
                st.session_state.sample_text = "با لحن گرم و دوستانه: به استودیوی جمینی خوش آمدید! امیدواریم از قابلیت‌های متن به گفتار لذت ببرید."

        with sample_col2:
            if st.button("نمونه چندبلندگو - گفتگوی روزمره", use_container_width=True):
                st.session_state.sample_text = f"""علی: سلام سارا! امروز چطوری؟
سارا: سلام علی! خوبم ممنون. تو چطور؟
علی: عالیم! یه پروژه جدید شروع کردم.
سارا: چه جالب! برام بیشتر تعریف کن."""

        with sample_col3:
            if st.button("نمونه دراماتیک - داستان", use_container_width=True):
                st.session_state.sample_text = "با لحن دراماتیک و پراحساس: در سرزمینی دور، قهرمانی بود که با شجاعت به دنبال حقیقت می‌گشت. راه پرخطری پیش رو داشت اما هرگز تسلیم نشد."

        if 'sample_text' in st.session_state:
            text_input = st.text_area("📝 متن مورد نظر:", st.session_state.sample_text, height=150)

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
    """)
