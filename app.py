import streamlit as st
import wave
from google import genai
from google.genai import types

# 🎵 تابع ذخیره wav
def save_wave(filename, pcm, channels=1, rate=24000, sample_width=2):
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)

st.set_page_config(page_title="Gemini TTS Studio", page_icon="🎙️", layout="centered")
st.title("🎙️ Gemini TTS Studio")
st.caption("تبدیل متن به گفتار با Gemini TTS - کلید API را در همین صفحه وارد کنید.")

# 🗝️ دریافت کلید API از کاربر
api_key = st.text_input("🔑 کلید API Gemini خود را وارد کنید:", type="password")

if api_key:
    client = genai.Client(api_key=api_key)

    # حالت گفتار
    mode = st.radio("حالت گفتار:", ["تک‌بلندگو", "چندبلندگو"])

    # متن ورودی
    text_input = st.text_area("📝 متن مورد نظر:", height=150)

    # انتخاب صداها
    voices = ["Kore","Puck","Zephyr","Enceladus","Sharon","Aurorus"]

    if mode == "تک‌بلندگو":
        voice = st.selectbox("انتخاب صدا:", voices)

    else:
        col1, col2 = st.columns(2)
        with col1:
            speaker1 = st.text_input("👤 نام گوینده ۱:", "علی")
            voice1 = st.selectbox("صدا گوینده ۱:", voices, key="v1")
        with col2:
            speaker2 = st.text_input("👤 نام گوینده ۲:", "سارا")
            voice2 = st.selectbox("صدا گوینده ۲:", voices, key="v2")

    # دکمه تولید صدا
    if st.button("🎧 تولید صدا"):
        try:
            if mode == "تک‌بلندگو":
                response = client.models.generate_content(
                    model="gemini-2.5-flash-preview-tts",
                    contents=text_input,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice,
                                )
                            )
                        ),
                    )
                )
            else:
                response = client.models.generate_content(
                    model="gemini-2.5-flash-preview-tts",
                    contents=text_input,
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
                                        )
                                    ),
                                    types.SpeakerVoiceConfig(
                                        speaker=speaker2,
                                        voice_config=types.VoiceConfig(
                                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                                voice_name=voice2,
                                            )
                                        )
                                    ),
                                ]
                            )
                        )
                    )
                )

            # ذخیره و پخش صدا
            data = response.candidates[0].content.parts[0].inline_data.data
            file_name = "output.wav"
            save_wave(file_name, data)

            st.audio(file_name, format="audio/wav")
            st.download_button("⬇️ دانلود فایل صوتی", data=open(file_name, "rb"), file_name=file_name)

        except Exception as e:
            st.error(f"❌ خطا: {e}")

else:
    st.info("🔐 برای شروع، کلید API خود را وارد کنید.")
