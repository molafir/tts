import streamlit as st
import wave
import requests
import base64
import io
from google import genai

# 🎵 تابع ذخیره wav
def save_wave(filename, pcm, channels=1, rate=24000, sample_width=2):
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)

# 📨 تابع ارسال به تلگرام
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

# 📊 بررسی طول متن
def validate_text_length(client, text, max_tokens=32000):
    try:
        token_count = client.models.count_tokens(
            model="gemini-2.0-flash", contents=text
        ).total_tokens
        return token_count <= max_tokens, token_count
    except Exception as e:
        estimated_tokens = len(text) / 4
        st.warning("شمارش توکن‌ها تقریبی است.")
        return estimated_tokens <= max_tokens, estimated_tokens

# 🎭 تولید رونوشت
def generate_transcript(client, topic, length, speaker1="علی", speaker2="سارا", style="پادکست"):
    prompt = f"""
    یک مکالمه {style} حدود {length} کلمه بین {speaker1} و {speaker2} درباره "{topic}" ایجاد کن.
    قالب خروجی باید دقیقاً به این شکل باشد:
    {speaker1}: متن مکالمه
    {speaker2}: پاسخ مکالمه
    فقط متن مکالمه را برگردان.
    """
    try:
        interaction = client.interactions.create(
            model="gemini-2.0-flash",
            input=prompt
        )
        return interaction.output_text
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
st.caption("نسخه کامل با Interactions API + استریمینگ + تگ‌های صوتی")

# 📚 سایدبار
with st.sidebar:
    st.header("🎯 راهنما و تنظیمات")
    
    st.subheader("📮 تلگرام")
    telegram_configured = st.secrets.get("TELEGRAM_BOT_TOKEN") and st.secrets.get("TELEGRAM_CHAT_ID")
    if telegram_configured:
        st.success("✅ تلگرام فعال است")
    else:
        st.warning("⚠️ تلگرام پیکربندی نشده")
    
    st.subheader("📖 کنترل سبک و تگ‌های صوتی")
    st.info("""
    **دستورات سبک:**
    - `Say cheerfully: ...`
    - `Say in a spooky whisper: ...`
    
    **تگ‌های صوتی محبوب:**
    - `[whispers]` `[shouting]` `[laughs]`
    - `[excitedly]` `[bored]` `[sighs]` `[gasp]`
    - `[sarcastically]` `[tired]` `[crying]` `[giggles]`
    
    **مثال:**
    ```
    [excitedly] سلام!
    [whispers] این یک راز است...
    [laughs] جدی می‌گم!
    ```
    """)
    
    st.subheader("⚠️ نکات مهم")
    st.warning("""
    - استریمینگ فقط روی مدل **3.1** کار می‌کند
    - حداکثر ۳۲٬۰۰۰ توکن
    - حداکثر ۲ گوینده
    - مدل‌ها هنوز در پیش‌نمایش هستند
    """)

# 🔑 کلید API
api_key = st.text_input("🔑 کلید API Gemini:", type="password")

if api_key:
    try:
        client = genai.Client(api_key=api_key)

        # تنظیمات
        st.header("⚙️ تنظیمات پیشرفته")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            mode = st.radio("🎭 حالت:", ["تک‌بلندگو", "چندبلندگو"])

        with col2:
            tts_model = st.selectbox(
                "🤖 مدل TTS:",
                [
                    "gemini-3.1-flash-tts-preview",
                    "gemini-2.5-flash-preview-tts",
                    "gemini-2.5-pro-preview-tts"
                ]
            )

        with col3:
            speech_rate_option = st.selectbox(
                "🎚️ سرعت:",
                ["پیش‌فرض", "آهسته", "متوسط", "سریع"]
            )
            speed_commands = {
                "پیش‌فرض": "",
                "آهسته": "Say slowly",
                "متوسط": "Say at a moderate pace",
                "سریع": "Say quickly"
            }

        with col4:
            use_streaming = st.checkbox(
                "📡 استریمینگ",
                value=True if "3.1" in tts_model else False,
                help="فقط روی مدل gemini-3.1-flash-tts-preview پشتیبانی می‌شود"
            )
            if use_streaming and "3.1" not in tts_model:
                st.warning("استریمینگ فقط روی مدل 3.1 فعال است")

        # لیست صداها
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

        # تولید رونوشت
        auto_generate = st.checkbox("🤖 تولید خودکار رونوشت")
        if auto_generate:
            st.subheader("🤖 تولید رونوشت")
            g1, g2, g3 = st.columns(3)
            with g1:
                topic = st.text_input("موضوع:", "تکنولوژی و هوش مصنوعی")
            with g2:
                style = st.selectbox("سبک:", ["پادکست", "مصاحبه", "گفتگوی دوستانه", "بحث علمی", "داستان"])
            with g3:
                length = st.slider("طول (کلمه):", 50, 300, 150)

            if st.button("🪄 تولید رونوشت"):
                with st.spinner("در حال تولید..."):
                    transcript = generate_transcript(client, topic, length, style=style)
                    if transcript:
                        st.session_state.generated_transcript = transcript
                        st.success("رونوشت آماده شد!")

        # متن ورودی
        st.header("📝 متن ورودی")
        
        if mode == "چندبلندگو":
            st.info("""
            **قالب پیشنهادی:**
            ```
            TTS the following conversation between علی and سارا:
            علی: [sighs] امروز خیلی خسته‌ام...
            سارا: [excitedly] من یه خبر خیلی خوب دارم!
            ```
            """)

        default_text = st.session_state.get("generated_transcript", "")
        text_input = st.text_area(
            "متن مورد نظر:",
            value=default_text,
            height=220,
            placeholder="مثال:\nSay cheerfully: Have a wonderful day!\n\nیا با تگ:\n[excitedly] سلام! [whispers] این یک راز است..."
        )

        # انتخاب صدا
        if mode == "تک‌بلندگو":
            st.subheader("👤 تک‌بلندگو")
            c1, c2 = st.columns(2)
            with c1:
                selected_voice = st.selectbox(
                    "صدا:",
                    all_voices,
                    format_func=lambda x: f"{x} - {voice_descriptions.get(x, '')}",
                    index=all_voices.index("Kore")
                )
            with c2:
                style_instruction = st.text_input("دستور سبک (اختیاری):", placeholder="Say in a warm voice")
        else:
            st.subheader("👥 چندبلندگو")
            c1, c2 = st.columns(2)
            with c1:
                speaker1 = st.text_input("گوینده ۱:", "علی")
                voice1 = st.selectbox("صدا ۱:", all_voices, index=all_voices.index("Kore"),
                                      format_func=lambda x: f"{x} - {voice_descriptions.get(x, '')}", key="v1")
                style1 = st.text_input("سبک ۱:", placeholder="tired and bored")
            with c2:
                speaker2 = st.text_input("گوینده ۲:", "سارا")
                voice2 = st.selectbox("صدا ۲:", all_voices, index=all_voices.index("Puck"),
                                      format_func=lambda x: f"{x} - {voice_descriptions.get(x, '')}", key="v2")
                style2 = st.text_input("سبک ۲:", placeholder="excited and happy")

        # اعتبارسنجی طول
        is_valid = True
        token_count = 0
        if text_input.strip():
            is_valid, token_count = validate_text_length(client, text_input)
            st.progress(min(token_count / 32000, 1.0))
            if is_valid:
                st.success(f"✅ تعداد توکن‌ها: {token_count:.0f} / 32,000")
            else:
                st.error(f"❌ متن خیلی طولانی است! ({token_count:.0f} توکن)")

        # دکمه تولید
        if st.button("🎧 تولید صدا", type="primary", use_container_width=True,
                     disabled=not text_input.strip() or not is_valid):
            
            try:
                processed_text = text_input

                # سرعت
                if speed_commands[speech_rate_option]:
                    processed_text = f"{speed_commands[speech_rate_option]}: {processed_text}"

                if mode == "تک‌بلندگو":
                    if style_instruction:
                        processed_text = f"{style_instruction}: {processed_text}"
                    speech_config = [{"voice": selected_voice}]
                else:
                    if style1 or style2:
                        parts = []
                        if style1:
                            parts.append(f"Make {speaker1} sound {style1}")
                        if style2:
                            parts.append(f"{speaker2} sound {style2}")
                        processed_text = " and ".join(parts) + ":\n" + processed_text

                    if not processed_text.lower().startswith("tts the following"):
                        processed_text = f"TTS the following conversation between {speaker1} and {speaker2}:\n{processed_text}"

                    speech_config = [
                        {"speaker": speaker1, "voice": voice1},
                        {"speaker": speaker2, "voice": voice2}
                    ]

                file_name = "output.wav"
                audio_bytes = b""

                # ========== حالت استریمینگ ==========
                if use_streaming and "3.1" in tts_model:
                    with st.spinner("📡 در حال استریم صدا..."):
                        stream = client.interactions.create(
                            model=tts_model,
                            input=processed_text,
                            response_format={"type": "audio"},
                            generation_config={"speech_config": speech_config},
                            stream=True
                        )

                        chunk_count = 0
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        for event in stream:
                            if hasattr(event, "event_type") and event.event_type == "step.delta":
                                if hasattr(event, "delta") and getattr(event.delta, "type", None) == "audio":
                                    chunk = base64.b64decode(event.delta.data)
                                    audio_bytes += chunk
                                    chunk_count += 1
                                    status_text.text(f"دریافت تکه صوتی شماره {chunk_count}...")
                                    progress_bar.progress(min(chunk_count * 5, 100))

                        progress_bar.progress(100)
                        status_text.text(f"✅ استریم کامل شد — {chunk_count} تکه دریافت شد")

                # ========== حالت عادی (غیر استریم) ==========
                else:
                    with st.spinner("🔮 در حال تولید صدا..."):
                        interaction = client.interactions.create(
                            model=tts_model,
                            input=processed_text,
                            response_format={"type": "audio"},
                            generation_config={"speech_config": speech_config}
                        )
                        audio_bytes = base64.b64decode(interaction.output_audio.data)

                # ذخیره و پخش
                if audio_bytes:
                    save_wave(file_name, audio_bytes)
                    st.success("✅ صدا با موفقیت تولید شد!")

                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.audio(file_name, format="audio/wav")
                    with col2:
                        with open(file_name, "rb") as f:
                            st.download_button(
                                "⬇️ دانلود فایل",
                                data=f,
                                file_name=file_name,
                                mime="audio/wav",
                                use_container_width=True
                            )

                    if telegram_configured:
                        with st.spinner("📤 ارسال به تلگرام..."):
                            caption = f"Gemini TTS\nمدل: {tts_model}\nاستریم: {'بله' if use_streaming else 'خیر'}"
                            send_to_telegram(file_name, caption)

                    # اطلاعات
                    st.subheader("📊 اطلاعات")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("کاراکتر", len(text_input))
                    m2.metric("توکن", f"{token_count:.0f}")
                    m3.metric("حالت", "استریمینگ" if (use_streaming and "3.1" in tts_model) else "عادی")

                else:
                    st.error("هیچ داده صوتی دریافت نشد.")

            except Exception as e:
                st.error(f"❌ خطا: {e}")
                st.info("مدل‌های TTS هنوز در پیش‌نمایش هستند. کلید API و دسترسی را بررسی کنید.")

        # نمونه‌ها
        st.header("🎭 نمونه‌های آماده")
        s1, s2, s3 = st.columns(3)

        with s1:
            if st.button("تک‌بلندگو شاد", use_container_width=True):
                st.session_state.sample_text = "Say cheerfully: Have a wonderful day! Welcome to Gemini TTS Studio Pro!"
        with s2:
            if st.button("چندبلندگو", use_container_width=True):
                st.session_state.sample_text = """TTS the following conversation between علی and سارا:
علی: سلام! امروز چطوری؟
سارا: خوبم ممنون. تو چطور؟"""
        with s3:
            if st.button("با تگ صوتی", use_container_width=True):
                st.session_state.sample_text = """[excitedly] سلام دوستان!
[whispers] امروز یه راز بزرگ دارم...
[laughs] آماده‌اید بشنوید؟"""

        if "sample_text" in st.session_state:
            st.text_area("متن نمونه:", st.session_state.sample_text, height=140)

    except Exception as e:
        st.error(f"❌ خطا در اتصال: {e}")
else:
    st.info("🔐 کلید API خود را وارد کنید تا شروع کنید.")
    st.markdown("""
    ### 🆕 قابلیت‌های این نسخه:
    - ✅ **Interactions API** (روش رسمی جدید)
    - ✅ مدل **gemini-3.1-flash-tts-preview**
    - ✅ **استریمینگ** صدا (دریافت تدریجی)
    - ✅ تگ‌های صوتی پیشرفته (`[whispers]`, `[laughs]` و ...)
    - ✅ تولید رونوشت خودکار
    - ✅ ارسال خودکار به تلگرام
    """)
