# ============================================================
# 🚀 راه‌اندازی کلاینت
# ============================================================

try:
    client = genai.Client(api_key=api_key)
except Exception as e:
    st.error(f"❌ خطا در اتصال به API: {e}")
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
        "🎧 فعال‌سازی استریمینگ",
        value=False,
        help="فقط مدل‌های ۳.x پشتیبانی می‌کنند.",
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
    "Orus": "محکم", "Aoede": "نسیم ملایم", "Callirrhoe": "آسان‌گیر",
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
        "**قالب چندبلندگو:**\n"
        "هر نوبت را با نام گوینده و دونقطه شروع کنید:\n"
        "```\nعلی: سلام! امروز چطوری؟\nسارا: خوبم ممنون. تو چطور؟\n```"
    )

text_input = st.text_area("📝 متن مورد نظر:", height=200)


# ============================================================
# 👥 تنظیمات صدا
# ============================================================

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
            "🎭 دستور سبک (style):",
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

                    spk_style = style1 if spk == speaker1 else (style2 if spk == speaker2 else "")
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
                    if event.event_type == "step.delta" and event.delta.type == "audio":
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
