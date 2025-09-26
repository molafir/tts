# streamlit_gemini_tts.py
import streamlit as st
import io
import base64
import wave
import time
from google import genai
from google.genai import types

# --------------------
# Helper utils
# --------------------
def pcm_to_wav_bytes(pcm_bytes: bytes, channels=1, rate=24000, sample_width=2) -> bytes:
    """
    Convert raw PCM bytes into a WAV file bytes (in-memory).
    Assumes pcm_bytes are raw PCM frames (not a WAV file).
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()

def validate_text_length(text: str, max_tokens: int = 32000):
    estimated_tokens = len(text) / 4.0
    return estimated_tokens <= max_tokens, estimated_tokens

def generate_transcript(client, prompt: str, approx_words: int = 150):
    """
    Uses the model recommended in docs for transcript generation.
    Returns text or None on error.
    """
    try:
        # Use gemini-2.0-flash per docs for transcript generation
        # we ask for approx number of words via instruction
        full_prompt = (
            f"Generate a short transcript of about {approx_words} words. {prompt}"
        )
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=full_prompt,
        )
        # Many SDK responses expose .text
        if hasattr(resp, "text") and resp.text:
            return resp.text
        # fallback: try candidates path
        try:
            return resp.candidates[0].content.parts[0].text
        except Exception:
            return None
    except Exception as e:
        st.error(f"خطا در تولید رونوشت: {e}")
        return None

# --------------------
# Streamlit UI
# --------------------
st.set_page_config(page_title="Gemini TTS Studio", page_icon="🎙️", layout="wide")

st.title("🎙️ Gemini TTS Studio Pro (Preview)")
st.caption("کلید API فقط در این جلسه استفاده می‌شود و روی سرور ذخیره نخواهد شد.")

with st.sidebar:
    st.header("🔐 نکات امنیتی")
    st.info("کلید API خود را در این فرم وارد کنید؛ این کلید ذخیره یا لاگ نمی‌شود.")
    st.markdown(
        "برای گرفتن API Key به AI Studio (Google) مراجعه کنید و یک API key جدید ایجاد کنید."
    )
    st.markdown("---")
    st.header("ℹ️ درباره")
    st.write("این اپ بر اساس مستندات Gemini TTS (Gemini 2.5 preview) ساخته شده است.")

# API Key input (only in-session)
api_key = st.text_input("🔑 کلید API Gemini (فقط در مرورگر وارد کنید):", type="password")

if not api_key:
    st.info("برای شروع، کلید API را وارد کنید (در سایدبار یا فیلد بالا).")
    st.stop()

# Create client (only in-memory)
try:
    client = genai.Client(api_key=api_key)
except Exception as e:
    st.error(f"❌ خطا در ساخت Client: {e}")
    st.stop()

# Voices (from docs)
all_voices = [
    "Zephyr","Puck","Sharon","Kore","Aurorus","Fenrir","Spring","Leda","Aoede","Callirrhoe",
    "Autonoe","Enceladus","Iapetus","Umbriel","Algieba","Despina","Erinome","Algenib",
    "Rasalgethi","Laomedeia","Achernar","Elnath","Schedar","Gacrux","Pulcherrima","Achird",
    "Zubenelgenubi","Vindemiatrix","Sadachbia","Sadaltager","Sulafat"
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

# Main controls
col_top = st.columns([3, 1])
with col_top[0]:
    st.header("📝 متن ورودی برای تبدیل به گفتار")
    text_input = st.text_area(
        "متن (قالب تک‌بلندگو یا چندبلندگو):",
        value="با لحن گرم و دوستانه: به Gemini TTS Studio خوش آمدید!",
        height=220,
        placeholder="می‌توانید از قالب چندبلندگو استفاده کنید:\nعلی: ...\nسارا: ..."
    )
with col_top[1]:
    st.header("⚙️ تنظیمات")
    mode = st.radio("حالت:", ["تک‌بلندگو", "چندبلندگو"])
    speed = st.slider("سرعت گفتار (نسبت به طبیعی):", min_value=0.5, max_value=2.0, value=1.0, step=0.05)
    accent = st.text_input("لهجه / سبک (مثال: آرام، هیجان‌زده، زمزمه‌وار):", placeholder="مثال: آرام و گرم")
    use_generated_transcript = st.checkbox("تولید رونوشت خودکار (مدل gemini-2.0-flash)")

# If user wants auto transcript
if use_generated_transcript:
    st.subheader("تولید رونوشت خودکار")
    gen_col1, gen_col2 = st.columns([3,1])
    with gen_col1:
        gen_prompt = st.text_input("موضوع برای تولید رونوشت:", "تکنولوژی و هوش مصنوعی")
    with gen_col2:
        gen_len = st.slider("حدود طول (کلمه):", min_value=30, max_value=300, value=150, step=10)
    if st.button("🪄 تولید رونوشت"):
        with st.spinner("در حال تولید رونوشت..."):
            transcript = generate_transcript(client, gen_prompt, approx_words=gen_len)
            if transcript:
                text_input = transcript
                st.success("رونوشت تولید شد — اکنون می‌توانید مستقیماً آن را تبدیل به گفتار کنید.")
                st.text_area("رونوشت تولید شده:", value=transcript, height=180)

# Single / Multi speaker UI
if mode == "تک‌بلندگو":
    st.subheader("🎤 تنظیمات تک‌بلندگو")
    selected_voice = st.selectbox(
        "انتخاب صدا:",
        options=all_voices,
        format_func=lambda x: f"{x} — {voice_descriptions.get(x, '')}"
    )
else:
    st.subheader("🎭 تنظیمات چندبلندگو (حداکثر 2 گوینده)")
    sp1_col, sp2_col = st.columns(2)
    with sp1_col:
        speaker1 = st.text_input("نام گوینده 1:", "علی")
        voice1 = st.selectbox("صدا برای گوینده 1:", options=all_voices, index=all_voices.index("Kore"), format_func=lambda x: f"{x} — {voice_descriptions.get(x, '')}", key="v1")
        style1 = st.text_input("استایل گوینده 1 (اختیاری):", placeholder="مثال: خسته و آرام")
    with sp2_col:
        speaker2 = st.text_input("نام گوینده 2:", "سارا")
        voice2 = st.selectbox("صدا برای گوینده 2:", options=all_voices, index=all_voices.index("Puck"), format_func=lambda x: f"{x} — {voice_descriptions.get(x, '')}", key="v2")
        style2 = st.text_input("استایل گوینده 2 (اختیاری):", placeholder="مثال: هیجان‌زده")

# Validate length
if text_input and text_input.strip():
    valid, est_tokens = validate_text_length(text_input)
    st.progress(min(est_tokens / 32000.0, 1.0))
    if not valid:
        st.error(f"متن خیلی طولانی است — تخمین توکن: {est_tokens:.0f} از 32000")
    else:
        st.success(f"طول متن مناسب است — تخمین توکن: {est_tokens:.0f} از 32000")

# Generate TTS
if st.button("🎧 تولید صدا"):
    if not text_input.strip():
        st.error("لطفاً متن ورودی را وارد کنید.")
    else:
        with st.spinner("در حال تماس با Gemini و تولید گفتار..."):
            try:
                # Build style prefix from accent + speed
                style_parts = []
                if accent:
                    style_parts.append(f"با لحن {accent}")
                if speed and abs(speed - 1.0) > 1e-6:
                    # natural language instruction for speed
                    style_parts.append(f"با سرعت {speed:.2f} برابر")
                style_prefix = ""
                if style_parts:
                    style_prefix = "، ".join(style_parts) + ":\n"

                processed_text = style_prefix + text_input

                if mode == "تک‌بلندگو":
                    response = client.models.generate_content(
                        model="gemini-2.5-flash-preview-tts",
                        contents=processed_text,
                        config=types.GenerateContentConfig(
                            response_modalities=["AUDIO"],
                            speech_config=types.SpeechConfig(
                                voice_config=types.VoiceConfig(
                                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                        voice_name=selected_voice,
                                    )
                                )
                            ),
                        ),
                    )
                else:
                    # Ensure speaker names in the prompt match the configured speakers.
                    # If user provided a plain text conversation, we pass it through.
                    # If there are no speaker lines, we build simple two-line conversation.
                    lines = [l.strip() for l in text_input.splitlines() if l.strip()]
                    if not any(":" in l for l in lines):
                        # make a default two-line conversation using provided text
                        left = lines[0] if lines else "سلام"
                        right = lines[1] if len(lines) > 1 else "سلام"
                        conversation = f"{speaker1}: {left}\n{speaker2}: {right}"
                    else:
                        conversation = text_input

                    # Prepend style per-speaker if provided
                    per_speaker_prefix = ""
                    per_styles = []
                    if style1:
                        per_styles.append(f"{speaker1} را {style1}")
                    if style2:
                        per_styles.append(f"{speaker2} را {style2}")
                    if per_styles:
                        per_speaker_prefix = " و ".join(per_styles) + " نشان بده:\n"

                    final_contents = style_prefix + per_speaker_prefix + conversation

                    response = client.models.generate_content(
                        model="gemini-2.5-flash-preview-tts",
                        contents=final_contents,
                        config=types.GenerateContentConfig(
                            response_modalities=["AUDIO"],
                            speech_config=types.SpeechConfig(
                                multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                                    speaker_voice_configs=[
                                        types.SpeakerVoiceConfig(
                                            speaker=speaker1,
                                            voice_config=types.VoiceConfig(
                                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                                    voice_name=voice1,
                                                )
                                            ),
                                        ),
                                        types.SpeakerVoiceConfig(
                                            speaker=speaker2,
                                            voice_config=types.VoiceConfig(
                                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                                    voice_name=voice2,
                                                )
                                            ),
                                        ),
                                    ]
                                )
                            ),
                        ),
                    )

                # Extract PCM data from response
                # As per docs: response.candidates[0].content.parts[0].inline_data.data
                raw_data = None
                try:
                    raw_data = response.candidates[0].content.parts[0].inline_data.data
                except Exception as e:
                    st.error(f"پاسخ غیرمنتظره از API — ساختار پاسخ یافت نشد: {e}")
                    st.stop()

                # If API returned a base64 string, decode it; otherwise assume bytes
                if isinstance(raw_data, str):
                    try:
                        pcm_bytes = base64.b64decode(raw_data)
                    except Exception as e:
                        st.error(f"خطا در decode Base64 داده صوتی: {e}")
                        st.stop()
                else:
                    pcm_bytes = raw_data  # assume bytes-like

                # Convert PCM to WAV bytes (in-memory) so we have proper WAV header
                wav_bytes = pcm_to_wav_bytes(pcm_bytes, channels=1, rate=24000, sample_width=2)

                # Play inline (no disk write)
                st.audio(io.BytesIO(wav_bytes), format="audio/wav")

                # Provide download button (still does not persist on server)
                fname = f"gemini_tts_{int(time.time())}.wav"
                st.download_button("⬇️ دانلود فایل WAV", data=wav_bytes, file_name=fname, mime="audio/wav", use_container_width=True)

                # Show metadata
                st.subheader("📊 اطلاعات تولید")
                info_col1, info_col2, info_col3 = st.columns(3)
                info_col1.metric("طول متن (کاراکتر)", f"{len(text_input)}")
                info_col2.metric("تخمین توکن", f"{est_tokens:.0f}" if 'est_tokens' in locals() else f"{len(text_input)/4:.0f}")
                if mode == "تک‌بلندگو":
                    info_col3.metric("صدا", selected_voice)
                else:
                    info_col3.metric("بلندگوها", f"{speaker1} / {speaker2}")

                st.success("✅ تولید گفتار با موفقیت انجام شد (بدون ذخیره‌سازی روی سرور).")

            except Exception as e:
                st.error(f"❌ خطا در تولید گفتار: {e}")
                st.info("اطمینان حاصل کنید که مدل TTS در اکانت شما فعال است و key معتبر است.")

# Footer notes
st.markdown("---")
st.caption("توجه: این برنامه مطابق مستندات رسمی Gemini TTS ساخته شده است. مدل‌های TTS در حالت پیش‌نمایش قرار دارند؛ ممکن است نیاز باشد مجوز TTS در حساب شما فعال باشد.")
