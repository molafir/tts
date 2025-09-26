import streamlit as st
import io
import wave
from google import genai
from google.genai import types

# ==============================
# Helper function: Save PCM to WAV
# ==============================
def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)

# ==============================
# Streamlit UI
# ==============================
st.title("🎙️ Gemini TTS Playground")

# API Key input (only from UI)
api_key = st.text_input("🔑 Enter your Gemini API Key:", type="password")

if api_key:
    client = genai.Client(api_key=api_key)

    mode = st.radio("Select Mode:", ["Single Speaker", "Multi Speaker"])
    input_text = st.text_area("Enter your text:", "Hello, this is a Gemini TTS demo!")

    # Voice options (based on docs list)
    voices = ["Kore", "Puck", "Zephyr", "Sharon", "Fenrir", "Leda", "Aoede", "Enceladus"]
    speed = st.slider("Speech Speed", 0.5, 2.0, 1.0, 0.1)
    style = st.text_input("Accent / Style (e.g., spooky whisper, cheerful, slow):", "")

    if mode == "Single Speaker":
        voice_name = st.selectbox("Choose Voice", voices)

    else:  # Multi-speaker config
        speaker1_name = st.text_input("Speaker 1 Name", "Alice")
        speaker1_voice = st.selectbox("Speaker 1 Voice", voices, key="s1")
        speaker2_name = st.text_input("Speaker 2 Name", "Bob")
        speaker2_voice = st.selectbox("Speaker 2 Voice", voices, key="s2")

    # Option to auto-generate transcript
    if st.checkbox("Generate Transcript before TTS"):
        transcript_prompt = st.text_area(
            "Transcript Generation Prompt",
            "Generate a short 50-word transcript about music and culture.",
        )
        if st.button("Generate Transcript"):
            transcript_response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=transcript_prompt
            )
            input_text = transcript_response.text
            st.success("Transcript generated:")
            st.write(input_text)

    # Run TTS
    if st.button("Generate Speech"):
        try:
            if mode == "Single Speaker":
                response = client.models.generate_content(
                    model="gemini-2.5-flash-preview-tts",
                    contents=f"Say in a {style}: {input_text}" if style else input_text,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice_name,
                                )
                            ),
                            speaking_rate=speed,
                        ),
                    ),
                )
            else:  # Multi Speaker
                prompt = f"""TTS the following conversation:
{speaker1_name}: {input_text.splitlines()[0] if input_text else "Hello!"}
{speaker2_name}: {input_text.splitlines()[1] if len(input_text.splitlines()) > 1 else "Hi there!"}"""

                response = client.models.generate_content(
                    model="gemini-2.5-flash-preview-tts",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                                speaker_voice_configs=[
                                    types.SpeakerVoiceConfig(
                                        speaker=speaker1_name,
                                        voice_config=types.VoiceConfig(
                                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                                voice_name=speaker1_voice,
                                            )
                                        ),
                                    ),
                                    types.SpeakerVoiceConfig(
                                        speaker=speaker2_name,
                                        voice_config=types.VoiceConfig(
                                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                                voice_name=speaker2_voice,
                                            )
                                        ),
                                    ),
                                ]
                            ),
                            speaking_rate=speed,
                        ),
                    ),
                )

            data = response.candidates[0].content.parts[0].inline_data.data

            # Save + Play
            file_name = "output.wav"
            wave_file(file_name, data)
            st.audio(io.BytesIO(data), format="audio/wav")

            with open(file_name, "wb") as f:
                f.write(data)
            st.download_button("Download Audio", data, file_name, "audio/wav")

        except Exception as e:
            st.error(f"❌ Error generating TTS: {e}")
