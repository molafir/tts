import streamlit as st
import wave
from google.cloud import genai
from google.cloud.genai import types

# 🎵 تابع ذخیره wav
def save_wave(filename, pcm, channels=1, rate=24000, sample_width=2):
    """ذخیره فایل صوتی با پارامترهای قابل تنظیم"""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)

# 📊 تابع بررسی طول متن
def validate_text_length(client, text, max_tokens=10000):
    """بررسی محدودیت طول متن بر اساس توکن با استفاده از API"""
    try:
        token_count = client.count_tokens(
            model="models/gemini-2.0-flash", contents=[{"parts": [{"text": text}]}]
        ).total_tokens
        return token_count <= max_tokens, token_count
    except Exception as e:
        st.error(f"خطا در شمارش توکن‌ها: {e}")
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
        response = client.generate_content(
            model="models/gemini-2.0-flash",
            contents=[{"parts": [{"text": prompt}]}]
        )
        if not response or not response.candidates or not response.candidates[0].content:
            st.error("پاسخ API برای تولید رونوشت نامعتبر است.")
            return None
        return response.candidates[0].content.parts[0].text
    except Exception as e:
        st.error(f"خطا در تولید رونوشت: {e}")
        if "429" in str(e):
            st.error("محدودیت نرخ درخواست (RPM/TPM/RPD) نقض شده است. لطفاً چند دقیقه صبر کنید.")
        elif "404" in str(e):
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
st.caption("تبدیل متن به گفتار حرفه‌ای با Gemini TTS - با پشتیبانی از کتابخانه google-genai")

# 📚 سایدبار برای راهنما و تنظیمات پیشرفته
with st.sidebar:
    st.header("🎯 راهنما و تنظیمات")
    st.subheader("📖 دستورات سبک گفتار")
    st.info("""
    **برای کنترل سبک از این قالب‌ها استفاده کنید:**
    - `با لحن شاد: متن شما`
    - `به صورت هیجان‌زده: متن شما`
    - `با صدای آرام: متن شما`
    **توجه**: دستورات پیچیده ممکن است با مدل‌های TTS پیش‌نمایش ناسازگار باشند.
    """)
    st.subheader("🔊 گزینه‌های صوتی و لهجه")
    st.caption("۳۰ گزینه صوتی و ۲۴ لهجه (کد BCP-47) از مستندات پشتیبانی می‌شوند")
    st.subheader("⚠️ محدودیت‌ها")
    st.warning("""
    - حداکثر ۱۰۰۰۰ توکن در دقیقه برای مدل‌های TTS
    - ۳ درخواست در دقیقه (RPM) و ۱۵ درخواست در روز (RPD) برای مدل‌های TTS در ردیف رایگان
    - فقط ورودی متنی پشتیبانی می‌شود
    - حداکثر ۲ بلندگو در حالت چندبلندگو
    - مدل‌های TTS در حالت پیش‌نمایش هستند و ممکن است پاسخ‌های خالی یا ناپایدار برگردانند
    - تنظیم سرعت گفتار پشتیبانی نمی‌شود
    - از کتابخانه google-genai استفاده کنید
    """)
    st.subheader("🌐 زبان و لهجه")
    st.info("زبان و لهجه به‌صورت خودکار تشخیص داده می‌شود، اما می‌توانید کد BCP-47 خاصی را انتخاب کنید. برای پایداری، از پرامپت‌های ساده استفاده کنید.")

# 🔑 دریافت کلید API از کاربر
api_key = st.text_input("🔑 کلید API Gemini خود را وارد کنید:", type="password")

if api_key:
    try:
        genai.configure(api_key=api_key)
        client = genai.GenerativeModel()

        # 🎛️ بخش تنظیمات پیشرفته
        st.header("⚙️ تنظیمات پیشرفته")
        col1, col2, col3 = st.columns(3)

        with col1:
            mode = st.radio("🎭 حالت گفتار:", ["تک‌بلندگو", "چندبلندگو"])

        with col2:
            tts_model = st.selectbox(
                "🤖 مدل TTS:",
                ["gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"],
                help="مدل‌های TTS در حالت پیش‌نمایش هستند. gemini-2.5-pro-preview-tts توصیه می‌شود."
            )

        with col3:
            st.markdown("🎤 **سرعت گفتار**: در حال حاضر غیرقابل تنظیم (پیش‌فرض: 1.0)")

        # 🌐 لیست لهجه‌ها (کدهای BCP-47)
        accent_options = {
            "تشخیص خودکار": None,
            "فارسی (ایران)": "fa-IR",
            "انگلیسی (آمریکا)": "en-US",
            "انگلیسی (هند)": "en-IN",
            "عربی (مصر)": "ar-EG",
            "فرانسوی (فرانسه)": "fr-FR",
            "اسپانیایی (آمریکا)": "es-US",
            "آلمانی (آلمان)": "de-DE",
            "هندی (هند)": "hi-IN",
            "اندونزیایی (اندونزی)": "id-ID",
            "ایتالیایی (ایتالیا)": "it-IT",
            "ژاپنی (ژاپن)": "ja-JP",
            "کره‌ای (کره)": "ko-KR",
            "پرتغالی (برزیل)": "pt-BR",
            "روسی (روسیه)": "ru-RU",
            "هلندی (هلند)": "nl-NL",
            "لهستانی (لهستان)": "pl-PL",
            "تایلندی (تایلند)": "th-TH",
            "ترکی (ترکیه)": "tr-TR",
            "ویتنامی (ویتنام)": "vi-VN",
            "رومانیایی (رومانی)": "ro-RO",
            "اوکراینی (اوکراین)": "uk-UA",
            "بنگالی (بنگلادش)": "bn-BD",
            "مراتی (هند)": "mr-IN",
            "تامیل (هند)": "ta-IN",
            "تلوگو (هند)": "te-IN"
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
            **قالب پیشنهادی برای چندبلندگو:**
            ```
            گوینده۱: متن مورد نظر
            گوینده۲: پاسخ گوینده دوم
            ```
            **توجه**: از دستورات پیچیده (مثل ترکیب لهجه و سبک) خودداری کنید.
            """)

        if 'generated_transcript' in st.session_state and auto_generate:
            text_input = st.text_area(
                "📝 متن مورد نظر:",
                value=st.session_state.generated_transcript,
                height=200,
                placeholder="مثال: متن ساده یا با قالب چندبلندگو..."
            )
        else:
            text_input = st.text_area(
                "📝 متن مورد نظر:",
                height=200,
                placeholder="مثال: متن ساده یا با قالب چندبلندگو..."
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

        # 👥 بخش انتخاب صداها و لهجه‌ها
        if mode == "تک‌بلندگو":
            st.subheader("👤 تنظیمات تک‌بلندگو")
            col1, col2, col3 = st.columns(3)

            with col1:
                selected_voice = st.selectbox(
                    "انتخاب صدا:",
                    options=all_voices,
                    format_func=lambda x: f"{x} - {voice_descriptions.get(x, '')}"
                )

            with col2:
                style_instruction = st.text_input(
                    "🎭 دستور سبک (اختیاری):",
                    placeholder="مثال: با لحن شاد بگو",
                    help="برای پایداری، سبک را ساده نگه دارید یا خالی بگذارید."
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
                style1 = st.text_input("🎭 سبک گوینده ۱ (اختیاری):", placeholder="مثال: خسته و بی‌حال")
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
                style2 = st.text_input("🎭 سبک گوینده ۲ (اختیاری):", placeholder="مثال: هیجان‌زده و شاد")
                accent2 = st.selectbox(
                    "🎤 لهجه گوینده ۲ (اختیاری):",
                    list(accent_options.keys()),
                    index=0,
                    key="a2"
                )

        # 📊 بررسی طول متن
        if text_input:
            is_valid, token_count = validate_text_length(client, text_input)
            progress = min(token_count / 10000, 1.0)

            st.progress(progress)

            if not is_valid:
                st.error(f"❌ متن بسیار طولانی! تعداد توکن‌ها: {token_count:.0f} از 10,000")
                st.warning("لطفاً متن را کوتاه کنید.")
            else:
                st.success(f"✅ طول متن مناسب است. تعداد توکن‌ها: {token_count:.0f} از 10,000")

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
                    if mode == "تک‌بلندگو":
                        if selected_accent != "تشخیص خودکار":
                            processed_text = f"Language {accent_options[selected_accent]}: {text_input}"
                        if style_instruction:
                            processed_text = f"{style_instruction}: {processed_text}"

                        response = client.generate_content(
                            model=f"models/{tts_model}",
                            contents=[{"parts": [{"text": processed_text}]}],
                            generation_config=types.GenerationConfig(
                                response_mime_type="audio/wav",
                                audio_config=types.AudioConfig(
                                    voice_config=types.VoiceConfig(
                                        prebuilt_voice=types.PrebuiltVoice(
                                            voice_name=selected_voice
                                        )
                                    )
                                )
                            ),
                            stream=False
                        )
                    else:
                        style_prefix = ""
                        accent_prefix = ""
                        if style1 or style2 or accent1 != "تشخیص خودکار" or accent2 != "تشخیص خودکار":
                            style_parts = []
                            if style1:
                                style_parts.append(f"{speaker1} را {style1}")
                            if style2:
                                style_parts.append(f"{speaker2} را {style2}")
                            if style_parts:
                                style_prefix = " و ".join(style_parts) + " نشان بده:\n"

                            accent_parts = []
                            if accent1 != "تشخیص خودکار":
                                accent_parts.append(f"{speaker1} با لهجه {accent_options[accent1]}")
                            if accent2 != "تشخیص خودکار":
                                accent_parts.append(f"{speaker2} با لهجه {accent_options[accent2]}")
                            if accent_parts:
                                accent_prefix = " و ".join(accent_parts) + ":\n"

                        processed_text = accent_prefix + style_prefix + text_input

                        response = client.generate_content(
                            model=f"models/{tts_model}",
                            contents=[{"parts": [{"text": processed_text}]}],
                            generation_config=types.GenerationConfig(
                                response_mime_type="audio/wav",
                                audio_config=types.AudioConfig(
                                    multi_speaker_config=types.MultiSpeakerConfig(
                                        speakers=[
                                            types.SpeakerConfig(
                                                speaker_name=speaker1,
                                                voice_name=voice1
                                            ),
                                            types.SpeakerConfig(
                                                speaker_name=speaker2,
                                                voice_name=voice2
                                            )
                                        ]
                                    )
                                )
                            ),
                            stream=False
                        )

                    # بررسی پاسخ API
                    if not response or not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
                        st.error("❌ پاسخ API نامعتبر است. ممکن است مدل TTS در دسترس نباشد یا پرامپت نادرست باشد.")
                        st.info(f"💡 لطفاً موارد زیر را بررسی کنید:\n"
                                f"- کلید API معتبر است و دسترسی به {tts_model} دارد.\n"
                                f"- متن ورودی ساده و بدون دستورات پیچیده است.\n"
                                f"- محدودیت‌های نرخ (۳ RPM، ۱۵ RPD، ۱۰۰۰۰ TPM) رعایت شده‌اند.")
                        st.warning(f"مدل {tts_model} در حالت پیش‌نمایش است. مدل gemini-2.5-pro-preview-tts را امتحان کنید.")
                        

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
                            st.metric("صدا", f"{selected_voice} ({selected_accent})")
                        else:
                            st.metric("بلندگوها", f"{speaker1}: {voice1} ({accent1}), {speaker2}: {voice2} ({accent2})")

            except Exception as e:
                st.error(f"❌ خطا در تولید صدا: {e}")
                if "429" in str(e):
                    st.error("محدودیت نرخ درخواست (RPM/TPM/RPD) نقض شده است. لطفاً چند دقیقه صبر کنید.")
                    st.info("محدودیت‌های مدل TTS: ۳ درخواست در دقیقه، ۱۵ درخواست در روز، ۱۰۰۰۰ توکن در دقیقه.")
                elif "404" in str(e):
                    st.error(f"مدل {tts_model} در دسترس نیست. لطفاً کلید API یا دسترسی به مدل را بررسی کنید.")
                elif "NoneType" in str(e):
                    st.error("پاسخ API خالی است. ممکن است مدل TTS ناپایدار باشد یا پرامپت نامعتبر باشد.")
                    st.info(f"💡 لطفاً موارد زیر را بررسی کنید:\n"
                            f"- متن ورودی ساده (مثلاً بدون لهجه/سبک پیچیده).\n"
                            f"- مدل {tts_model} در منطقه شما در دسترس است.\n"
                            f"- کلید API دسترسی به TTS دارد.")
                    st.warning("مدل gemini-2.5-pro-preview-tts را امتحان کنید یا از نمونه‌های آماده استفاده کنید.")
                else:
                    st.info("💡 ممکن است کلید API نامعتبر باشد یا سرویس دچار مشکل شده باشد.")

        # 📚 بخش نمونه‌های آماده
        st.header("🎭 نمونه‌های آماده")
        sample_col1, sample_col2, sample_col3 = st.columns(3)

        with sample_col1:
            if st.button("نمونه تک‌بلندگو - خوش‌آمدگویی", use_container_width=True):
                st.session_state.sample_text = "به استودیوی جمینی خوش آمدید! امیدواریم از قابلیت‌های متن به گفتار لذت ببرید."

        with sample_col2:
            if st.button("نمونه چندبلندگو - گفتگوی روزمره", use_container_width=True):
                st.session_state.sample_text = f"""علی: سلام سارا! امروز چطوره؟
سارا: سلام علی! عالیه، تو چی؟
علی: منم خوبم! یه پروژه جدید شروع کردم.
سارا: واقعاً؟ بگو ببینم چیه!"""

        with sample_col3:
            if st.button("نمونه دراماتیک - داستان", use_container_width=True):
                st.session_state.sample_text = "در سرزمینی دور، قهرمانی بود که با شجاعت به دنبال حقیقت می‌گشت."

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
    1. به [Google AI Studio](https://aistudio.google.com) بروید
    2. وارد حساب Google خود شوید
    3. از بخش API Keys یک کلید جدید ایجاد کنید
    4. کلید را در فیلد بالا وارد کنید
    5. اطمینان حاصل کنید که پروژه شما در ردیف مناسب (رایگان یا پولی) برای دسترسی به مدل‌های TTS است
    """)
