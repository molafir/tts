# Gemini 3.8 TTS Studio Pro
# هم‌تراز با راهنمای AI Studio تا ۲۸ اکتبر ۲۰۲۶ و صفحه مدل تا ۴ نوامبر ۲۰۲۶
# سقف رسمی: ۸۱۹۲ توکن ورودی، ۱۶۳۸۴ توکن خروجی. هر دو مدل ۳.۸ یک طرح درخواست دارند.
# pip install "google-genai>=2.25.0" streamlit requests
# streamlit run gemini_tts_studio.py
import base64
import io
import json
import re
import time
import traceback
import wave

import requests
import streamlit as st
from google import genai

st.set_page_config(page_title="Gemini TTS Studio Pro", page_icon="🎙️", layout="wide")

RTL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600&family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
html, body, p, h1, h2, h3, h4, h5, h6, label, .stMarkdown, .stText { font-family: 'Vazirmatn', 'Tahoma', sans-serif; }
.material-symbols-rounded, .material-icons, [data-testid="stIconMaterial"], span[class*="material-symbols"] {
    font-family: 'Material Symbols Rounded' !important; direction: ltr !important; font-feature-settings: 'liga' !important;
}
textarea, .stTextArea textarea, .stTextInput input { direction: rtl; text-align: right; font-family: 'Vazirmatn', 'Tahoma', sans-serif; }
.stCodeBlock pre, .stCode pre { direction: rtl; text-align: right; font-size: 14px; line-height: 1.8; }
.stButton > button { white-space: normal; height: auto; line-height: 1.35; }
@media (max-width: 700px) {
  div[data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    flex: 1 1 48% !important;
    width: 48% !important;
    min-width: 48% !important;
  }
  .stButton > button { font-size: 0.78rem; padding: 0.4rem 0.35rem; }
}
</style>
"""
st.markdown(RTL_CSS, unsafe_allow_html=True)
st.title("🎙️ Gemini TTS Studio Pro")
st.caption("Gemini 3.8 · Interactions API · کتابخانه صدا، طراحی صدا، استریم و تلگرام")

# ----------------------------- Constants -----------------------------

SAMPLE_RATES = [24000, 16000, 8000]
INPUT_TOKEN_LIMIT = 8192
OUTPUT_TOKEN_LIMIT = 16384
HISTORY_LIMIT = 8
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 1.5
CUSTOM_TURN_LIMIT = 40

ALL_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]
VOICE_DESCRIPTIONS = {
    "Zephyr": "روشن", "Puck": "خوش‌بین", "Charon": "آموزنده", "Kore": "محکم",
    "Fenrir": "هیجان‌انگیز", "Leda": "جوان", "Orus": "محکم", "Aoede": "ملایم",
    "Callirrhoe": "آسان‌گیر", "Autonoe": "روشن", "Enceladus": "نفس‌گیر",
    "Iapetus": "شفاف", "Umbriel": "آسان‌گیر", "Algieba": "صاف", "Despina": "صاف",
    "Erinome": "پاک", "Algenib": "شنی", "Rasalgethi": "آموزنده", "Laomedeia": "خوش‌بین",
    "Achernar": "نرم", "Alnilam": "محکم", "Schedar": "یکنواخت", "Gacrux": "بالغ",
    "Pulcherrima": "پیشرو", "Achird": "دوستانه", "Zubenelgenubi": "غیررسمی",
    "Vindemiatrix": "ملایم", "Sadachbia": "سرزنده", "Sadaltager": "آگاه", "Sulafat": "گرم",
}
MODELS = ["gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts"]
MIME_TYPES = {
    "WAV (پیشنهادی)": "audio/wav",
    "PCM خطی L16": "audio/l16",
    "mu-law تلفنی": "audio/mulaw",
    "A-law تلفنی": "audio/alaw",
}
RAW_EXT = {"audio/l16": "pcm", "audio/mulaw": "mulaw", "audio/alaw": "alaw"}
PREDEFINED_STYLES = {
    "— (بدون سبک خاص / پیش‌فرض)": "",
    "گرم و مشتاق (Warm and enthusiastic)": "warm and enthusiastic, clear pacing",
    "آرام و عمیق (Calm and deep)": "calm and deep, steady pacing",
    "دوستانه و صمیمی (Friendly and gentle)": "friendly and gentle, approachable",
    "هیجان‌زده و پرانرژی (Excited and energetic)": "excited and energetic",
    "غمگین و آهسته (Sad and slow)": "sad and slow",
    "گوینده خبر رسمی (News anchor)": "professional news anchor, formal tone",
    "نجوا و مرموز (Whispering)": "whispering, mysterious",
    "طنز و کنایه (Sarcastic)": "sarcastic, playful",
    "سریع و هیجانی (Fast paced)": "speaking rapidly, excited",
    "سفارشی (Custom)": "custom",
}
QUICK_TAGS = [
    "<short pause>", "<long pause>", "<laugh>", "<sigh>",
    "<breath>", "<gasp>", "<cough>", "<whispers>",
    "|oh hmm|", "|oh really?|", "|absolutely|", "|ok|",
]

# ★ مطابق سند اکتبر ۲۰۲۶: در Interactions API از type و threshold کوچک استفاده می‌شود.
INTERACTION_SAFETY_SETTINGS = [
    {"type": "harassment", "threshold": "off"},
    {"type": "hate_speech", "threshold": "off"},
    {"type": "sexually_explicit", "threshold": "off"},
    {"type": "dangerous_content", "threshold": "off"},
]
# ★ models.generate_content هنوز ساختار قدیمی category/threshold را می‌گیرد.
TEXT_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "OFF"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "OFF"},
]

# ----------------------------- Balochi poem data -----------------------------

BALOCH_POEM_TITLE = {
    "balochi": "او مڑا داریں بلوچ",
    "transliteration": "O Mardaaren Baloch",
    "translation": "ای بلوچ با غیرت و نامدار!",
    "subtitle": "گالاں نصیرءِ گوش بدار (به سخنان نصیر گوش فراده)",
    "poet": "میر گل خان نصیر (۱۹۱۴–۱۹۸۳) — ملک‌الشعرای بلوچستان",
}

BALOCH_VERSES = [
    {"id": 1, "balochi": "او مڑا داریں بلوچ! او سرمَچنڈیں نامدار",
     "transliteration": "O mardaaren Baloch! O sarmachand-en naamdaar",
     "translation": "ای بلوچ با غیرت و دلاور! ای قهرمان نامدار و سربلند!",
     "explanation": "فراخوانی پرشور به میراث اصیل و غیرت تاریخی مردم بلوچ.", "keywords": ["مڑا داریں", "سرمَچنڈیں", "نامدار"]},
    {"id": 2, "balochi": "نشتگئے پرچے او ورنا ! تو چو بیواک و نکار",
     "transliteration": "Nishtag-e parche o warnaa! Tu chu bay-waak o nakaar",
     "translation": "چرا بیکار نشسته‌ای ای جوان! در ناتوانی و بی‌خاصیتی؟",
     "explanation": "سرزنشی تند به سکون و بی‌عملی، فراخوان نسل جوان به رهایی از انفعال.", "keywords": ["ورنا", "بیواک", "نکار"]},
    {"id": 3, "balochi": "بستگئے دستان وتی ، چماں تئی گِپتہ ھُمار",
     "transliteration": "Bastag-e dastaan wati, chammaan tayi gepta humaar",
     "translation": "دستان خودت را بسته‌ای و خواب و مستی چشمانت را فراگرفته است!",
     "explanation": "شاعر تراژدی را تشخیص می‌دهد: نه کمبود نیرو، بلکه بستن دستان خویش و به خواب رفتن.", "keywords": ["دستان", "ھُمار"]},
    {"id": 4, "balochi": "بوجی ءَ گندئے وتی بیتگ گوں توپان ءَ دچار",
     "transliteration": "Boji-a gind-e wati baytag gon toofaan-a dochaar",
     "translation": "کشتی چوبی خودت را می‌بینی که گرفتار توفان سهمگین شده است!",
     "explanation": "استعارهٔ دریایی مکران: کشتی چوبی (بوجی) در میان امواج خروشان.", "keywords": ["بوجی", "توپان", "دچار"]},
    {"id": 5, "balochi": "پاد کائنت چئول ،چو گٹیں گـَر و سبزیں تلار",
     "transliteration": "Paad kayant chawool, chu gatt-en gar o sabz-en talaar",
     "translation": "امواج سرکش مانند پرتگاه‌های ژرف و صخره‌های سبزفام به بالا می‌جهند!",
     "explanation": "تصویری زنده از امواج عظیم دریا همچون پرتگاه‌های کوه و صخره‌های لغزنده.", "keywords": ["چئول", "گٹیں گـَر", "سبزیں تلار"]},
    {"id": 6, "balochi": "بوجی ءَ نیستیں ،تئی مستیں زرءِ لاپ ءَ کرار",
     "transliteration": "Boji-a nest-en, tayi mast-en zar-e laap-a qaraar",
     "translation": "کشتی تو در دل دریای مست و خروشان هیچ آرام و قراری ندارد!",
     "explanation": "دریا «مست» و سرکش وصف شده؛ هیچ پناهگاهی برای کشتی بی‌حرکت نیست.", "keywords": ["مستیں زر", "لاپ", "کرار"]},
    {"id": 7, "balochi": "جمّراں بستہ دُهتوکی، گرئنداں گوں گوات ءَ آوار",
     "transliteration": "Jammaraan basta dohtoki, grayndaan gon gwaath-a aawaar",
     "translation": "ابرهای سنگین پرده‌های تیره بر آسمان کشیده‌اند؛ غرش رعد با زوزهٔ باد درآمیخته است!",
     "explanation": "تاریکی و خفقان جوی که در آن باد و آذرخش و رعد به هم می‌آمیزند.", "keywords": ["جمّراں", "دُهتوکی", "گرئنداں", "آوار"]},
    {"id": 8, "balochi": "دیر و بیگواہ انت تیاب و شپ سیاہ انت و تهار",
     "transliteration": "Dair o bay-gwaah ant tayaab o shap siyaah ant o tahaar",
     "translation": "ساحل دور و گم شده و شب سیاه و تاریک است!",
     "explanation": "سرگشتگی کامل؛ در تاریک‌ترین نیمه‌شب، بندر دیده نمی‌شود.", "keywords": ["بیگواہ", "تیاب", "تہار"]},
    {"id": 9, "balochi": "بد دلی زیبا نہ انت او دل مَتُرسین سَرمَچار",
     "transliteration": "Bad-dilli zaybaa na-int, o dil ma-tursen sarmachaar",
     "translation": "بزدلی زیبنده نیست! ای جنگجوی بی‌باک، دل خویش را نترسان!",
     "explanation": "چرخش از ناامیدی به ایستادگی: مردان راستین هرگز ترس را به دل راه نمی‌دهند.", "keywords": ["بد دلی", "سَرمَچار", "مَتُرسین"]},
    {"id": 10, "balochi": "یک کسانیں مُهلتے اے زندگی نئیتیں دو بار",
     "transliteration": "Yak kasaan-en mohlat-e ay zindagee nayt-en do baar",
     "translation": "زندگی مهلتی کوتاه است و هرگز دوباره داده نمی‌شود!",
     "explanation": "فوریت وجودی: این تنها فرصت برای ایستادن و شرافتمندانه زیستن است.", "keywords": ["مُهلتے", "زندگی", "دو بار"]},
    {"id": 11, "balochi": "باید انت بندئے سرینءَ نیں پہ جدّ و جُهد و کار",
     "transliteration": "Baayad ant band-e sarin-a neyn pa jadd o johd o kaar",
     "translation": "اکنون باید کمر برای تلاش و کوشش و کار ببندی!",
     "explanation": "بستن کمر (سرین) کنایهٔ سنتی بلوچی برای آماده شدن برای نبرد و کار سخت است.", "keywords": ["سرین", "جدّ و جُهد", "کار"]},
    {"id": 12, "balochi": "بئے گوں توپانءَ مُکابل، چِکّی تکدیرءِ مهار",
     "transliteration": "Baye gon toofaan-a mukaabal, chekki takdeer-e mahaar",
     "translation": "رو در روی توفان بایست و محکم افسار سرنوشت را بکش!",
     "explanation": "رد جبرگرایی: سرنوشت یوغی منفعل نیست، بلکه افساری است که باید به دست خود گرفت.", "keywords": ["مُکابل", "تکدیرءِ مهار", "چِکّی"]},
    {"id": 13, "balochi": "زندگی لئیبے بزان، پرواہ مکن، وهمءَ میار",
     "transliteration": "Zindagee layb-e bazaan, parwaah ma-kan, wahm-a ma-yaar",
     "translation": "زندگی را بازی‌ای جسورانه بدان؛ پروا مکن و وهم به دل میاور!",
     "explanation": "زندگی را با روحیهٔ بی‌پروا بازی کن، نه با اضطراب‌های فلج‌کننده.", "keywords": ["لئیب", "پرواہ", "وهم"]},
    {"id": 14, "balochi": "گوات و توپان و گِروک و گِرئندگاں ہِچّی مَچار",
     "transliteration": "Gwaath o toofaan o giroak o grayndagaan hich-ee ma-chaar",
     "translation": "باد زوزه‌کش و توفان و آذرخش و رعد را هیچ بشمار!",
     "explanation": "کاستن از هراس بیرونی با قوت درونی و یقین روانی.", "keywords": ["گِروک", "گِرئندگاں", "هِچّی"]},
    {"id": 15, "balochi": "آزمان پُرشیت، زمین جسکیت بلے، پرواہ مدار",
     "transliteration": "Aazmaan porsheet, zameen jaskeet balay, parwaah ma-daar",
     "translation": "اگر آسمان بشکافد و زمین بلرزد، باز هم پروا مکن!",
     "explanation": "بی‌باکی رواقی در برابر سخت‌ترین سختی‌ها.", "keywords": ["آزمان پُرشیت", "زمین جسکیت", "پرواہ مدار"]},
    {"id": 16, "balochi": "کل تئی وَهم و گمان ئنت ایش کہ گُرّنت چو نهار",
     "transliteration": "Kull tayi wahm o gumaan ant eysh ke gurrant chu nahaar",
     "translation": "همهٔ این هیولاهایی که چون درندگان می‌غرشند، تنها وهم و گمان خودت هستند!",
     "explanation": "بینش روان‌شناختی: اشباح بیرونی تنها تا جایی قدرت دارند که ذهن تو ترس را فرامی‌خواند.", "keywords": ["وَهم و گمان", "گُرّنت", "نهار"]},
    {"id": 17, "balochi": "هَکلش دئے دیر سِندنت شِنگ و شانگ و تار پَتار",
     "transliteration": "Hakkl-esh day dair sindant shing o shaang o taar pataar",
     "translation": "بر آنان فریاد بزن تا از هم بپاشند و تکه‌تکه و پراکنده شوند!",
     "explanation": "صدای قاطع یقین، هراس‌های موهوم را به هیچ می‌شکند.", "keywords": ["هَکلش دئے", "شِنگ و شانگ", "تار پَتار"]},
    {"id": 18, "balochi": "همت اش نیستن، تئی دیما بہ اوشتنت پِیْدْوار",
     "transliteration": "Himmat-ish nest-en, tayi daymaa ba-oshtant paydwaar",
     "translation": "آنان را یارای ایستادن در برابر پیشروی استوار تو نیست!",
     "explanation": "ستم و سختی در برابر ارادهٔ ناگسستنی آدمی پژمرده می‌شود.", "keywords": ["همت", "اوشتنت", "پِیْدْوار"]},
    {"id": 19, "balochi": "بُست او ورنا ! پہ زندءَ نیں پَتَی دستان مَچار",
     "transliteration": "Bost o warnaa! Pa zind-a neyn patay dastaan ma-chaar",
     "translation": "برخیز ای جوان! در این زندگی، با حسرت به دستان خالی منگر!",
     "explanation": "بهانهٔ تهیدستی و ناتوانی را کنار بگذار؛ ارادهٔ انسان بزرگ‌ترین سرمایه است.", "keywords": ["بُست", "ورنا", "دستان"]},
    {"id": 20, "balochi": "وت تئی دست انت بیلی بَھت و تکدیرءِ مهار",
     "transliteration": "Wat tayi dast ant bayli baht o takdeer-e mahaar",
     "translation": "ای یار، در دستان خود توست افسار اقبال و سرنوشت!",
     "explanation": "پیام فلسفی بنیادین: تو خود نویسنده و فرماندهٔ سرنوشت خویشی.", "keywords": ["بیلی", "بَھت", "تکدیرءِ مهار"]},
    {"id": 21, "balochi": "ڈڈ کَن ورنائیں دلءَ گالاں نصیرءِ گوش بدار",
     "transliteration": "Dadd kan warnaa-en dil-a gaalaan Naseer-e gosh ba-daar",
     "translation": "دل جوانت را پولادین کن و به سخنان نصیر گوش فراده:",
     "explanation": "شاعر نام خود (تخلص) را در شعر می‌نشاند و وصیت جاودان خود را به نسل‌های آینده می‌سپارد.", "keywords": ["ڈڈ کَن", "دل", "نصیر", "گوش بدار"]},
    {"id": 22, "balochi": "اے سیاهیں شپ نہ مانیت، نئے سیاهیں روزگار",
     "transliteration": "Ay siyaah-en shap na maaneet, nay siyaah-en rozgaar",
     "translation": "نه این شب تاریک خواهد ماند و نه این روزگار سیاه!",
     "explanation": "سرود جاودانهٔ امید و پیروزی: تاریک‌ترین شب و ستمگرترین دوران ناگزیر به سپیده می‌رسد.", "keywords": ["سیاهیں شپ", "نہ مانیت", "سیاهیں روزگار"]},
]

BALOCH_GLOSSARY = [
    {"word": "مڑا داریں", "transliteration": "Mardaaren", "meaning": "با غیرت، جوانمرد و صاحب همت"},
    {"word": "سرمَچنڈیں", "transliteration": "Sarmachand-en", "meaning": "سربلند، قهرمان سرکش و بی‌باک"},
    {"word": "سَرمَچار", "transliteration": "Sarmachaar", "meaning": "جان‌نثار، جنگجوی سرافراز"},
    {"word": "بوجی", "transliteration": "Boji", "meaning": "قایق چوبی سنتی سواحل مکران"},
    {"word": "چئول", "transliteration": "Chawool", "meaning": "موج کوبنده و خروشان دریا"},
    {"word": "تلار", "transliteration": "Talaar", "meaning": "صخرهٔ بلند و دیوارهٔ سنگی"},
    {"word": "مستیں زر", "transliteration": "Mast-en zar", "meaning": "دریای خروشان و سرکش (دریای عمان)"},
    {"word": "دُهتوکی", "transliteration": "Dohtoki", "meaning": "چادر تیره و پردهٔ فراگیر آسمان"},
    {"word": "تیاب", "transliteration": "Tayaab", "meaning": "ساحل و کنارهٔ دریا"},
    {"word": "بندئے سرینءَ", "transliteration": "Band-e sarin-a", "meaning": "کمر بستن؛ آماده شدن برای کار و نبرد"},
    {"word": "تکدیرءِ مهار", "transliteration": "Takdeer-e mahaar", "meaning": "افسار سرنوشت؛ به دست گرفتن تقدیر خود"},
    {"word": "گِروک", "transliteration": "Giroak", "meaning": "درخشش آذرخش که ابرها را می‌شکافد"},
    {"word": "گرئند", "transliteration": "Graynd", "meaning": "غرش رعد در کوه و دریا"},
    {"word": "نهار", "transliteration": "Nahaar", "meaning": "درندهٔ غران، شیر یا جانور وحشی"},
    {"word": "تار پَتار", "transliteration": "Taar pataar", "meaning": "تکه‌تکه و پراکنده شده"},
    {"word": "ڈڈ کَن", "transliteration": "Dadd kan", "meaning": "پولادین و استوار کردن دل"},
    {"word": "سیاهیں روزگار", "transliteration": "Siyaah-en rozgaar", "meaning": "دوران تاریک و ظلم و جور"},
]

BALOCH_VOICES = [
    {"name": "Fenrir", "label": "Fenrir (بم و حماسی مردانه)",
     "tone": "شاهری، باصلابت، طنین سینه و صدای دلاورانه",
     "style": "Deep, heroic, stirring orator with resonant chest tone, reciting classical Balochi revolutionary poetry with emotional weight and solemn pride"},
    {"name": "Charon", "label": "Charon (پیر دانا و راوی کهن)",
     "tone": "استاد کهنسال و راوی تاریخ بلوچستان با وقار و هیبت",
     "style": "Ancient epic bard declaiming against the howling storm, with deep sonorous projection and legendary gravitas"},
    {"name": "Puck", "label": "Puck (ورنا و جوان پرشور)",
     "tone": "جوان، جسور، شتابان و پرانرژی برای اشعار امید و خروش",
     "style": "Urgent, impassioned, stirring revolutionary youth reciting verses with rapid cadence, conviction, and fearless energy"},
    {"name": "Aoede", "label": "Aoede (بانوی نغمه‌خوان مکرانی)",
     "tone": "گیرا، سوزناک و شاعرانه، نغمه‌سرایی لطیف زنانه",
     "style": "Lyrical, emotive Balochi female bard reciting with soulful clarity, musical cadences, and poetic beauty"},
    {"name": "Kore", "label": "Kore (آرام، نرم و شمرده)",
     "tone": "صدای ملایم، آرام‌بخش و شمرده، مناسب آموزش و غزل‌های دلنشین",
     "style": "Lyrical, emotive, rich poetic declamation with clear enunciation, dramatic pauses, and solemn grandeur"},
    {"name": "Zephyr", "label": "Zephyr (متین و رادیویی)",
     "tone": "صدای استوار، سنجیده، گوینده رادیویی و دانا",
     "style": "Wise, steadfast, dignified poet elder reciting with rhythmic meter, calm authority, and unwavering conviction"},
]

BALOCH_STYLES = [
    {"id": "epic", "label": "دکلمه حماسی شاهری", "prompt": "Passionate, heroic Balochi master poet declaiming with majestic cadence, rolling r, and rhythmic dignity"},
    {"id": "zahirok", "label": "زهیروک و سوزناک", "prompt": "Sorrowful, deeply emotional Balochi zahirok lamentation style, melodic pauses, soulful breathing"},
    {"id": "liko", "label": "نغمگی و لِیکو", "prompt": "Rhythmic, melodious Balochi liko chanting with musical cadence and flowing prosody"},
    {"id": "clear", "label": "شمرده و آموزشی", "prompt": "Articulate, slow educational native Balochi reciter, precise vowels and retroflex consonants"},
    {"id": "gentle", "label": "نجوای آرام و شبانه", "prompt": "Gentle, lyrical nocturnal Balochi poetry recitation with warm intimate tones and smooth transitions"},
    {"id": "dialogue", "label": "مناظره و گفت‌وگو", "prompt": "Dramatic dialogue, sharp responsive theatrical delivery with dynamic emotional shifts"},
    {"id": "festive", "label": "سرود شادمانی و جشن", "prompt": "Uplifting, joyous Balochi festive chant celebrating courage, unity, and bright dawn"},
]

# ----------------------------- Utilities -----------------------------

def get_secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

def decode_b64(value):
    if not value:
        return b""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return base64.b64decode(value)

def pcm_to_wav_bytes(pcm, rate=24000, channels=1, sample_width=2):
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(int(rate))
        wf.writeframes(pcm)
    return out.getvalue()

def wav_pcm(data):
    if not data.startswith(b"RIFF"):
        return data, None
    with wave.open(io.BytesIO(data), "rb") as wf:
        return wf.readframes(wf.getnframes()), wf.getframerate()

def join_wavs(wav_list):
    frames = []
    rate = 24000
    width = 2
    channels = 1
    for blob in wav_list:
        with wave.open(io.BytesIO(blob), "rb") as wf:
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            rate = wf.getframerate()
            frames.append(wf.readframes(wf.getnframes()))
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(width)
        wf.setframerate(rate)
        wf.writeframes(b"".join(frames))
    return out.getvalue()

def mulaw_to_pcm16(data):
    out = bytearray()
    for value in data:
        u = (~value) & 0xFF
        t = (((u & 0x0F) << 3) + 0x84) << ((u & 0x70) >> 4)
        sample = 0x84 - t if (u & 0x80) else t - 0x84
        out.extend(int(max(-32768, min(32767, sample))).to_bytes(2, "little", signed=True))
    return bytes(out)

def alaw_to_pcm16(data):
    out = bytearray()
    for value in data:
        a = value ^ 0x55
        t = (a & 0x0F) << 4
        seg = (a & 0x70) >> 4
        if seg == 0:
            t += 8
        elif seg == 1:
            t += 0x108
        else:
            t += 0x108
            t <<= seg - 1
        sample = t if (a & 0x80) else -t
        out.extend(int(sample).to_bytes(2, "little", signed=True))
    return bytes(out)

def estimate_tokens(text):
    """تخمین رو به بالا (محافظه‌کارانه) برای هشدار سقف توکن ورودی."""
    s = text or ""
    if not s:
        return 1
    non_ascii = sum(1 for ch in s if ord(ch) > 127)
    ascii_len = len(s) - non_ascii
    # لاتین ≈ ۴ کاراکتر/توکن (اینجا ۳ برای احتیاط)، غیرلاتین (فارسی و…) ≈ ۱ کاراکتر/توکن
    return max(1, ascii_len // 3 + non_ascii)


def is_custom_voice(voice):
    v = (voice or "").strip()
    return v.startswith("voice_") or v.startswith("voicekey_")

def parse_speaker_line(line, spk1, spk2):
    line = line.strip()
    if not line:
        return None, None
    normalized = line.replace("：", ":").replace("﹕", ":")
    if ":" in normalized:
        prefix, txt = normalized.split(":", 1)
        prefix, txt = prefix.strip(), txt.strip()
        if prefix in (spk1, spk2):
            return prefix, txt
    return spk1, line

def clean_text(text):
    result = []
    for line in text.splitlines():
        line = re.sub(r"^[*_\s]+", "", line)
        line = re.sub(r"[*_\s]+$", "", line)
        result.append(line.strip("`\"'«»").strip())
    return "\n".join(result)

def sanitize_input_text(text):
    if not text:
        return text
    replacements = {
        "کشتار": "درگیری", "کشتن": "متوقف کردن", "مرگ": "پایان", "مرده": "بی‌حرکت",
        "خون": "مایع قرمز", "خونی": "قرمز", "مواد مخدر": "مواد", "مخدر": "ماده",
        "تجاوز": "تخطی", "اسلحه": "ابزار", "تفنگ": "ابزار", "بمب": "وسیله",
        "انفجار": "صدا", "جنگ": "درگیری", "خودکشی": "آسیب به خود",
        "قتل": "درگیری", "دزدی": "برداشتن", "فحش": "کلام نامناسب",
        "kill": "stop", "murder": "incident", "death": "end", "dead": "still",
        "blood": "red liquid", "drug": "substance", "gun": "tool", "weapon": "tool",
        "bomb": "device", "war": "conflict", "suicide": "self-harm", "hate": "dislike",
    }
    sanitized = text
    for word, replacement in replacements.items():
        if re.search(r"[A-Za-z]", word):
            sanitized = re.sub(rf"\b{re.escape(word)}\b", replacement, sanitized, flags=re.IGNORECASE)
        else:
            sanitized = sanitized.replace(word, replacement)
    return sanitized

def detect_strategy(text):
    lines = [x.strip() for x in clean_text(text).splitlines() if x.strip()]
    if not lines:
        return "line"
    dashes = sum(x.startswith(("-", "—", "–")) for x in lines)
    if len(lines) >= 4 and dashes >= len(lines) * 0.5:
        return "dash"
    if text.count("\n\n") >= 2:
        return "stanza"
    if len(lines) >= 4 and sum(map(len, lines)) / len(lines) < 70:
        return "couplet"
    return "line"

def format_multispeaker(raw, strategy, spk1, spk2, separator="---", mapping="", n_lines=2):
    if strategy == "mapping":
        pairs = {}
        for pair in mapping.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                pairs[k.strip()] = v.strip()
        out = []
        for line in clean_text(raw).splitlines():
            if not line.strip():
                continue
            normalized = line.replace("：", ":")
            if ":" in normalized:
                prefix, txt = normalized.split(":", 1)
                target = pairs.get(prefix.strip(), "1")
                out.append(f"{spk1 if target in ('1', spk1) else spk2}: {txt.strip()}")
            else:
                out.append(f"{spk1}: {line.strip()}")
        return "\n".join(out)
    if strategy == "separator":
        if not separator:
            return ""
        parts = [p.strip() for p in raw.split(separator) if p.strip()]
        out = []
        for i, part in enumerate(parts):
            who = spk1 if i % 2 == 0 else spk2
            out.extend(f"{who}: {line}" for line in clean_text(part).splitlines() if line.strip())
        return "\n".join(out)
    cleaned = clean_text(raw)
    lines = [x.strip() for x in cleaned.splitlines() if x.strip()]
    if strategy == "stanza":
        stanzas, cur = [], []
        for line in cleaned.splitlines():
            if line.strip():
                cur.append(line.strip())
            elif cur:
                stanzas.append(cur)
                cur = []
        if cur:
            stanzas.append(cur)
        return "\n".join(
            f"{spk1 if i % 2 == 0 else spk2}: {line}"
            for i, stanza in enumerate(stanzas) for line in stanza
        )
    out = []
    for i, line in enumerate(lines):
        if strategy == "dash":
            has_dash = line.startswith(("-", "—", "–"))
            spoken = line.lstrip("-—–").strip() if has_dash else line
            out.append(f"{spk1 if has_dash else spk2}: {spoken}")
        elif strategy == "couplet":
            out.append(f"{spk1 if (i // 2) % 2 == 0 else spk2}: {line}")
        elif strategy == "n_lines":
            n = max(1, int(n_lines))
            out.append(f"{spk1 if (i // n) % 2 == 0 else spk2}: {line}")
        else:
            out.append(f"{spk1 if i % 2 == 0 else spk2}: {line}")
    return "\n".join(out)

def split_text_safely(text, max_chars=3500):
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    chunks, current = [], ""
    units = re.split(r"(?<=[.!?؟。])\s+|\n", text)
    for unit in units:
        unit = unit.strip()
        if not unit:
            continue
        while len(unit) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            cut = unit.rfind(" ", 0, max_chars)
            if cut < max_chars // 2:
                cut = max_chars
            chunks.append(unit[:cut].strip())
            unit = unit[cut:].strip()
        candidate = f"{current}\n{unit}".strip() if current else unit
        if len(candidate) > max_chars and current:
            chunks.append(current.strip())
            current = unit
        else:
            current = candidate
    if current:
        chunks.append(current.strip())
    return chunks

def split_multispeaker_lines(text, max_chars=3500):
    lines = [line for line in text.splitlines() if line.strip()]
    chunks, current = [], ""
    for line in lines:
        if len(line) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line)
            continue
        candidate = f"{current}\n{line}".strip() if current else line
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text.strip()]

def build_client(api_key):
    # مدل‌های TTS و صداها فقط تحت v1beta در دسترس‌اند؛ SDK 3.0 به‌طور پیش‌فرض v1 می‌زند.
    return genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})

def is_retriable(exc):
    msg = str(exc).lower()
    tokens = ("429", "quota", "rate limit", "rate_limit", "timeout", "timed out", "temporarily", "500", "502", "503", "504")
    return any(token in msg for token in tokens)

def safety_rejected(exc):
    msg = str(exc).lower()
    if "safety_setting" in msg or "safety_settings" in msg:
        return True
    return "safety" in msg and any(k in msg for k in ("extra", "unknown", "unexpected", "forbidden", "invalid", "validation"))

def create_with_retry(client, **kwargs):
    last_exc = None
    dropped_safety = False
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return client.interactions.create(**kwargs)
        except Exception as exc:
            last_exc = exc
            if not dropped_safety and safety_rejected(exc):
                kwargs.pop("safety_settings", None)
                dropped_safety = True
                continue
            if attempt == RETRY_ATTEMPTS - 1 or not is_retriable(exc):
                raise
            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
    raise last_exc

def generate_text_with_retry(client, model, prompt):
    last_exc = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return client.models.generate_content(
                model=model,
                contents=prompt,
                config={"safety_settings": TEXT_SAFETY_SETTINGS},
            )
        except TypeError:
            return client.models.generate_content(model=model, contents=prompt)
        except Exception as exc:
            last_exc = exc
            if safety_rejected(exc):
                try:
                    return client.models.generate_content(model=model, contents=prompt)
                except Exception as inner:
                    last_exc = inner
            if attempt == RETRY_ATTEMPTS - 1 or not is_retriable(exc):
                raise last_exc
            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
    raise last_exc

def generate_balochi_json(client, system_instruction, user_prompt, primary="gemini-3.1-flash-lite", fallback="gemini-3.8-flash"):
    """تولید متن بلوچی با مدل اصلی و fallback، سپس پارس خروجی JSON."""
    last_exc = None
    for model in (primary, fallback):
        try:
            config = {"safety_settings": TEXT_SAFETY_SETTINGS}
            if system_instruction:
                config["system_instruction"] = system_instruction
            response = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=config,
            )
            text = (response.text or "").strip()
            if not text:
                raise ValueError("پاسخ مدل خالی بود.")
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                return json.loads(match.group(0))
            return json.loads(text)
        except Exception as exc:
            last_exc = exc
            continue
    raise last_exc

def build_single_input(text, voice, style):
    content_item = {"type": "text", "text": text}
    style = (style or "").strip()
    if style:
        content_item["annotations"] = [{"type": "speech_metadata", "style": style}]
    return [{"type": "user_input", "content": [content_item]}], [{"voice": voice}]

def build_multi_input(text, spk1, spk2, voice1, voice2, style1, style2):
    blocks = []
    for line in text.splitlines():
        if not line.strip():
            continue
        speaker, content = parse_speaker_line(line, spk1, spk2)
        if not content:
            continue
        style = style1 if speaker == spk1 else style2
        annotation = {"type": "speech_metadata", "speaker": speaker}
        if (style or "").strip():
            annotation["style"] = style.strip()
        blocks.append({"type": "text", "text": content, "annotations": [annotation]})
    if not blocks:
        raise ValueError("هیچ خط معتبری پیدا نشد. هر خط باید «نام: متن» باشد و نام‌ها با تنظیمات یکی باشند.")
    config = {
        "speakers": [
            {"speaker": spk1, "voice": voice1},
            {"speaker": spk2, "voice": voice2},
        ]
    }
    return [{"type": "user_input", "content": blocks}], config

def response_format_for(stream, mime_type, sample_rate):
    rate = int(sample_rate or 24000)
    if stream and rate == 24000:
        return {"type": "audio"}
    if stream:
        return {"type": "audio", "mime_type": "audio/l16", "sample_rate": rate}
    fmt = {"type": "audio", "mime_type": mime_type}
    if rate != 24000:
        fmt["sample_rate"] = rate
    return fmt

def raw_to_wav(raw, mime_type, sample_rate):
    rate = int(sample_rate or 24000)
    if raw.startswith(b"RIFF"):
        return raw
    if mime_type == "audio/mulaw":
        return pcm_to_wav_bytes(mulaw_to_pcm16(raw), rate=rate)
    if mime_type == "audio/alaw":
        return pcm_to_wav_bytes(alaw_to_pcm16(raw), rate=rate)
    return pcm_to_wav_bytes(raw, rate=rate)

def generate_audio(client, model, input_blocks, speech_config, stream, mime_type, sample_rate):
    started = time.time()
    fmt = response_format_for(stream, mime_type, sample_rate)
    rate = int(sample_rate or 24000)
    kwargs = {
        "model": model,
        "input": input_blocks,
        "response_format": fmt,
        "generation_config": {"speech_config": speech_config},
        "safety_settings": INTERACTION_SAFETY_SETTINGS,
    }
    if stream:
        kwargs["stream"] = True
        last_exc = None
        dropped_safety = False
        for attempt in range(RETRY_ATTEMPTS):
            try:
                response = client.interactions.create(**kwargs)
                chunks = []
                for event in response:
                    event_type = getattr(event, "event_type", None)
                    if event_type in ("error", "interaction.error"):
                        raise RuntimeError(f"خطای استریم: {getattr(event, 'error', event)}")
                    if event_type == "step.delta":
                        delta = getattr(event, "delta", None)
                        if getattr(delta, "type", None) == "audio" and getattr(delta, "data", None):
                            chunks.append(decode_b64(delta.data))
                raw = b"".join(chunks)
                if not raw:
                    raise RuntimeError("استریم تمام شد اما داده صوتی نیامد.")
                return raw_to_wav(raw, "audio/l16", rate), raw, time.time() - started
            except Exception as exc:
                last_exc = exc
                if not dropped_safety and safety_rejected(exc):
                    kwargs.pop("safety_settings", None)
                    dropped_safety = True
                    continue
                if attempt == RETRY_ATTEMPTS - 1 or not is_retriable(exc):
                    raise
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
        raise last_exc

    try:
        response = create_with_retry(client, **kwargs)
    except Exception as exc:
        msg = str(exc).lower()
        if "content_blocked" in msg or "policy" in msg or "prohibited" in msg:
            raise RuntimeError(
                "متن توسط فیلتر ایمنی Gemini مسدود شد. واژه‌ها را عوض کنید یا «نرم‌سازی واژه‌ها» را روشن کنید."
            ) from exc
        raise
    raw = decode_b64(getattr(getattr(response, "output_audio", None), "data", None))
    if not raw:
        raise RuntimeError("API پاسخی بدون داده صوتی برگرداند.")
    return raw_to_wav(raw, mime_type, rate), raw, time.time() - started

def explain_error(exc):
    err = str(exc)
    low = err.lower()
    if "429" in err or "rate" in low or "quota" in low:
        return "سقف درخواست پر شده است. کمی صبر کنید یا مدل lite را انتخاب کنید."
    if "404" in err or "not_found" in low:
        return "مدل یا شناسه صدا پیدا نشد. voice_ را دوباره بسازید یا نام پیش‌ساخته را چک کنید."
    if "content_blocked" in low or "policy" in low:
        return "فیلتر ایمنی پاسخ را بست."
    if "extra_forbidden" in low or "unknown field" in low:
        return "یک فیلد درخواست با این نسخه از SDK سازگار نیست."
    if "safety" in low:
        return "تنظیمات ایمنی یا متن را تغییر دهید."
    return "کلید API، مدل و شناسه صدا را بررسی کنید."

# ----------------------------- Sample / tag callbacks -----------------------------

def load_single_sample():
    st.session_state.single_text_value = (
        "سلام! به Gemini TTS Studio Pro خوش آمدید. <short pause> امیدوارم روز فوق‌العاده‌ای داشته باشید."
    )

def load_multi_sample():
    spk1 = st.session_state.get("speaker_name_1", "مرد")
    spk2 = st.session_state.get("speaker_name_2", "زن")
    st.session_state.multi_text_value = (
        f"{spk1}: سلام! امروز چطوری؟\n"
        f"{spk2}: خوبم، ممنون. تو چطور؟\n"
        f"{spk1}: عالی‌ام! <laugh> آماده‌ای شروع کنیم؟\n"
        f"{spk2}: همیشه آماده‌ام!"
    )

def load_poem_sample():
    spk1 = st.session_state.get("speaker_name_1", "مرد")
    spk2 = st.session_state.get("speaker_name_2", "زن")
    st.session_state.multi_text_value = (
        f"{spk1}: منی دل، منی نوجوانی توئے\n"
        f"{spk1}: منی زینت و زندگانی توئے\n"
        f"{spk2}: گمانی، سیائے دَنز و مُجاں\n"
        f"{spk2}: من شاداں، منی شادمانی توئے"
    )

def load_backchannel_sample():
    spk1 = st.session_state.get("speaker_name_1", "مرد")
    spk2 = st.session_state.get("speaker_name_2", "زن")
    st.session_state.multi_text_value = (
        f"{spk1}: پس انتشار چهارشنبه است |جدی؟| واقعاً آماده‌ایم؟\n"
        f"{spk2}: |آها| فکر کنم بله. <short pause> یک بار دیگر متن را بخوانیم."
    )

def append_tag(key, tag):
    current = st.session_state.get(key, "") or ""
    st.session_state[key] = (current.rstrip() + " " + tag).strip()

def remember_voice(voice_id):
    st.session_state.pending_voice_id = voice_id

# ----------------------------- Telegram -----------------------------

def send_to_telegram(file_bytes, filename, caption="", as_document=False):
    token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "توکن یا شناسه چت تلگرام در Secrets تنظیم نشده است."
    method = "sendDocument" if as_document else "sendAudio"
    field = "document" if as_document else "audio"
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        response = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption[:1024], "title": "Gemini TTS"},
            files={field: (filename, io.BytesIO(file_bytes))},
            timeout=(10, 90),
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.ok and payload.get("ok"):
            return True, "فایل به تلگرام ارسال شد."
        description = payload.get("description", response.text[:500])
        return False, f"تلگرام خطا داد ({response.status_code}): {description}"
    except requests.RequestException as exc:
        return False, f"خطای اتصال به تلگرام: {exc}"

# ----------------------------- Sidebar -----------------------------

with st.sidebar:
    st.header("راهنما")
    st.markdown(
        "**مدل‌ها**\n"
        "- `gemini-3.8-flash-lite-tts` پیش‌فرض\n"
        "- `gemini-3.8-flash-tts` کیفیت بالاتر"
    )
    st.info(
        "تک‌بلندگو: `speech_config` آرایه است.\n\n"
        "چندبلندگو با صدای پیش‌ساخته: شیء `speakers`.\n\n"
        "استریم پیش‌فرض PCM خام ۲۴ کیلوهرتز است و اینجا به WAV تبدیل می‌شود."
    )
    st.markdown(
        "**برچسب داخل متن** (خوانده نمی‌شود، اجرا می‌شود)\n\n"
        "`<short pause>` `<laugh>` `<sigh>` `<breath>` `<gasp>` `<cough>`\n\n"
        "برای متن غیرانگلیسی هم خودِ برچسب را انگلیسی بگذارید.\n\n"
        "**واکنش شنونده** با خط عمودی، داخل همان نوبت (بهتر با مدل flash):\n\n"
        "`|oh hmm|` `|oh really?|` `|absolutely|`"
    )
    st.warning(
        "صدای `voice_` و `voicekey_` را نمی‌توان در یک درخواست چندبلندگو گذاشت. "
        "هر نوبت جدا ساخته و بعد به هم وصل می‌شود. سقف ۲۰۰ صدای ذخیره‌شده، ماندگاری یک سال.\n\n"
        f"سقف ورودی هر درخواست **{INPUT_TOKEN_LIMIT:,}** توکن و سقف خروجی صوتی **{OUTPUT_TOKEN_LIMIT:,}** توکن است. "
        "مدل lite برای حجم بالا و تک‌گویی روزمره است؛ برای دیالوگ پیچیده و لهجه، flash را انتخاب کنید. "
        "مدل‌های پیش‌نمایش ۲.۵ و ۳.۱ این طرح `speech_metadata` را ندارند."
    )
    if get_secret("TELEGRAM_BOT_TOKEN") and get_secret("TELEGRAM_CHAT_ID"):
        st.success("تلگرام پیکربندی شده")
    else:
        st.caption("تلگرام: TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID را در Secrets بگذارید.")

# ----------------------------- API key -----------------------------

secret_api_key = get_secret("GEMINI_API_KEY")
with st.expander("🔑 دسترسی API", expanded=not bool(secret_api_key)):
    if secret_api_key:
        st.success("کلید از Secrets خوانده می‌شود.")
        api_key = secret_api_key
    else:
        api_key = st.text_input("کلید API Gemini", type="password", key="api_key_input")
        st.caption("در میزبانی، GEMINI_API_KEY را در Secrets بگذارید. کلید از https://aistudio.google.com/apikey")
if not api_key:
    st.info("برای شروع، کلید API را وارد کنید.")
    st.stop()
try:
    client = build_client(api_key)
except Exception as exc:
    st.error(f"ساخت کلاینت ناموفق بود: {exc}")
    st.stop()

# ----------------------------- Session -----------------------------

for key, value in {
    "generated_transcript": "",
    "history": [],
    "single_text_value": "",
    "multi_text_value": "",
    "formatted_preview": "",
    "last_created_voice": None,
    "created_voices": [],
    "library_rows": [],
    "library_page_token": "",
    "pending_voice_id": "",
    "last_result": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ----------------------------- Balochi section -----------------------------

st.header("📜 بلوچی — شعر و دکلمه")
st.caption("شعر «او مردارین بلوچ» از میر گل خان نصیر + سرودن، تحلیل و تقسیم چندصدایی متن بلوچی.")

def _balochi_tts(text, voice_name, style_prompt, label):
    """دکلمهٔ متن بلوچی با مدل TTS و نمایش نتیجه."""
    try:
        blocks, config = build_single_input(text.strip(), voice_name, style_prompt or "")
        with st.spinner("در حال دکلمه..."):
            wav, raw, took = generate_audio(
                client, "gemini-3.8-flash-tts", blocks, config, False, "audio/wav", 24000
            )
        st.session_state.baloch_audio = {"wav": wav, "label": label}
    except Exception as exc:
        st.error(f"{exc}")
        st.info(explain_error(exc))

tab_read, tab_compose, tab_analyze, tab_tag = st.tabs(
    ["خواندن شعر", "سرودن شعر", "تحلیل متن", "چندصدایی"]
)

# ---- خواندن شعر ----
with tab_read:
    st.markdown(
        f"**{BALOCH_POEM_TITLE['balochi']}** — {BALOCH_POEM_TITLE['translation']}\n\n"
        f"{BALOCH_POEM_TITLE['subtitle']} · {BALOCH_POEM_TITLE['poet']}"
    )
    c1, c2 = st.columns(2)
    with c1:
        voice_label = st.selectbox("صدا", [v["label"] for v in BALOCH_VOICES], key="baloch_voice")
        sel_voice = next(v for v in BALOCH_VOICES if v["label"] == voice_label)
    with c2:
        style_label = st.selectbox("سبک دکلمه", [s["label"] for s in BALOCH_STYLES], key="baloch_style")
        sel_style = next(s for s in BALOCH_STYLES if s["label"] == style_label)
    st.caption("صدای انتخابی: " + sel_voice["tone"])

    full_text = "\n".join(v["balochi"] for v in BALOCH_VERSES)
    if st.button("🎧 خواندن کل شعر", type="primary", use_container_width=True, key="baloch_full"):
        _balochi_tts(full_text, sel_voice["name"], sel_style["prompt"], "او مردارین بلوچ — دکلمه کامل")

    verse_no = st.selectbox(
        "بیت", range(1, len(BALOCH_VERSES) + 1),
        format_func=lambda i: f"بیت {i}", key="baloch_verse_no",
    )
    verse = BALOCH_VERSES[verse_no - 1]
    st.markdown(f"**{verse['balochi']}**")
    st.caption(verse["transliteration"])
    st.caption(verse["translation"])
    if st.button("خواندن این بیت", use_container_width=True, key="baloch_verse_btn"):
        _balochi_tts(verse["balochi"], sel_voice["name"], sel_style["prompt"], f"بیت {verse_no}")

    with st.expander("متن کامل شعر (۲۲ بیت)"):
        for v in BALOCH_VERSES:
            st.markdown(f"**{v['id']}. {v['balochi']}**")
            st.caption(v["transliteration"] + " — " + v["translation"])

    with st.expander("واژه‌نامه بلوچی"):
        for g in BALOCH_GLOSSARY:
            st.markdown(f"**{g['word']}** ({g['transliteration']}) — {g['meaning']}")

# ---- سرودن شعر ----
with tab_compose:
    st.caption("سرودن شعر اصیل بلوچی با Gemini (همراه آوانویسی و ترجمه فارسی).")
    c1, c2 = st.columns(2)
    with c1:
        theme = st.text_input("موضوع", "دلیری و غیرت بلوچ", key="baloch_theme")
        form = st.selectbox("قالب", ["غزل و دوبیتی حماسی", "دوبیتی", "رباعی", "غزل", "شعر آزاد"], key="baloch_form")
    with c2:
        dialect = st.selectbox("گویش", ["مکرانی", "رخشانی", "سرحدی", "لاشاری"], key="baloch_dialect")
        mood = st.selectbox("حال‌وهوا", ["حماسی و انگیزشی", "سوزناک و عاشقانه", "امیدبخش", "حکیمانه"], key="baloch_mood")
    verse_count = st.slider("تعداد بیت", 2, 12, 4, key="baloch_vcount")

    if st.button("سرودن شعر", type="primary", use_container_width=True, key="baloch_compose_btn"):
        system_instruction = (
            "You are a renowned master Balochi poet and literary scholar. "
            "Compose authentic, linguistically accurate Balochi poetry (not Persian/Urdu disguised as Balochi). "
            "Follow traditional Balochi meter and rhyme; use traditional Arabic-Balochi script "
            "(letters ݔ، ۏ، ئے، ء، ڈ، ٹ، ڑ). Provide precise Romanized phonetic transliteration for every verse, "
            "a faithful Persian translation for each verse, and a literary explanation and vocabulary breakdown. "
            "Output must be strictly valid JSON."
        )
        user_prompt = (
            f"Compose an original Balochi poem:\n- Theme: {theme}\n- Form: {form}\n"
            f"- Dialect: {dialect}\n- Mood: {mood}\n- Couplets: {verse_count}\n\n"
            'Return JSON with schema: {"title": "...", "dialect": "...", '
            '"verses": [{"balochi": "...", "transliteration": "...", "translation": "..."}], '
            '"fullBalochiText": "...", "explanation": "...", '
            '"vocabulary": [{"word": "...", "meaning": "..."}]}'
        )
        try:
            with st.spinner("در حال سرودن..."):
                st.session_state.baloch_poem = generate_balochi_json(client, system_instruction, user_prompt)
        except Exception as exc:
            st.error(f"سرودن ناموفق بود: {exc}")

    poem = st.session_state.get("baloch_poem")
    if poem:
        st.subheader(poem.get("title", "شعر بلوچی"))
        if poem.get("dialect"):
            st.caption("گویش: " + str(poem["dialect"]))
        verses = poem.get("verses") or []
        for v in verses:
            st.markdown(f"**{v.get('balochi', '')}**")
            st.caption(v.get("transliteration", ""))
            st.caption(v.get("translation", ""))
        if poem.get("explanation"):
            with st.expander("شرح ادبی"):
                st.write(poem["explanation"])
        vocab = poem.get("vocabulary") or []
        if vocab:
            with st.expander("واژه‌نامه"):
                for item in vocab:
                    st.markdown(f"**{item.get('word', '')}** — {item.get('meaning', '')}")
        full = poem.get("fullBalochiText") or "\n".join(v.get("balochi", "") for v in verses)
        if full and st.button("خواندن شعر سروده‌شده", use_container_width=True, key="baloch_compose_read"):
            _balochi_tts(full, sel_voice["name"], sel_style["prompt"], "شعر سروده‌شده")

# ---- تحلیل متن ----
with tab_analyze:
    st.caption("تحلیل متن بلوچی: آوانویسی، ترجمه فارسی، آماده‌سازی دکلمه و واژه‌نامه.")
    analyze_text = st.text_area(
        "متن بلوچی", height=160, key="baloch_analyze_text",
        placeholder="متن یا شعر بلوچی را اینجا بچسبانید...",
    )
    if st.button("تحلیل متن", type="primary", use_container_width=True, key="baloch_analyze_btn"):
        if not analyze_text.strip():
            st.error("متن بلوچی را وارد کنید.")
        else:
            system_instruction = (
                "You are a native Balochi literary scholar and phoneticist. "
                "Analyze the provided Balochi text/poetry: parse it verse by verse; provide exact Romanized "
                "phonetic transcription (long vowels, retroflex consonants); provide a Persian translation for "
                "each verse; prepare an optimized recitation script; extract key vocabulary with Persian meanings. "
                "Output strictly valid JSON."
            )
            user_prompt = (
                "Analyze this Balochi poetry:\n\"\"\"\n" + analyze_text.strip() + "\n\"\"\"\n\n"
                'Return JSON with schema: {"verses": [{"balochi": "...", "transliteration": "...", "translation": "..."}], '
                '"optimizedRecitationText": "...", "phoneticGuide": "...", '
                '"vocabulary": [{"word": "...", "meaning": "..."}]}'
            )
            try:
                with st.spinner("در حال تحلیل..."):
                    st.session_state.baloch_analysis = generate_balochi_json(client, system_instruction, user_prompt)
            except Exception as exc:
                st.error(f"تحلیل ناموفق بود: {exc}")

    analysis = st.session_state.get("baloch_analysis")
    if analysis:
        verses = analysis.get("verses") or []
        for v in verses:
            st.markdown(f"**{v.get('balochi', '')}**")
            st.caption(v.get("transliteration", ""))
            st.caption(v.get("translation", ""))
        if analysis.get("phoneticGuide"):
            with st.expander("راهنمای تلفظ"):
                st.write(analysis["phoneticGuide"])
        vocab = analysis.get("vocabulary") or []
        if vocab:
            with st.expander("واژه‌نامه"):
                for item in vocab:
                    st.markdown(f"**{item.get('word', '')}** — {item.get('meaning', '')}")
        recit = analysis.get("optimizedRecitationText") or analyze_text
        if recit and st.button("خواندن متن تحلیل‌شده", use_container_width=True, key="baloch_analyze_read"):
            _balochi_tts(recit, sel_voice["name"], sel_style["prompt"], "متن تحلیل‌شده")

# ---- تقسیم چندصدایی ----
with tab_tag:
    st.caption("تقسیم خودکار شعر/متن بلوچی برای دکلمهٔ دو صدایی (راوی + جوان).")
    tag_text = st.text_area(
        "متن بلوچی", height=160, key="baloch_tag_text",
        placeholder="شعر یا متن بلوچی را بچسبانید...",
    )
    if st.button("تقسیم چندصدایی", type="primary", use_container_width=True, key="baloch_tag_btn"):
        if not tag_text.strip():
            st.error("متن بلوچی را وارد کنید.")
        else:
            system_instruction = (
                "You are an expert native Balochi theatrical director. Segment and tag the poem for 2 distinct "
                "speakers for dramatic multi-speaker recitation. Assign each segment to spk1 (پیر/راوی, voice "
                "Charon or Fenrir) or spk2 (جوان/ورنا, voice Puck or Aoede). For each segment provide id, speakerId, "
                "speakerName, assignedVoice (one of Fenrir, Puck, Charon, Aoede, Kore, Zephyr), balochiText, "
                "transliteration, translation, deliveryHint. Output strictly valid JSON."
            )
            user_prompt = (
                "Partition and tag this Balochi poetry for 2 speakers:\n\"\"\"\n" + tag_text.strip() + "\n\"\"\"\n\n"
                'Return JSON: {"speakers": [{"id": "spk1", "name": "...", "voice": "Charon"}, '
                '{"id": "spk2", "name": "...", "voice": "Puck"}], '
                '"segments": [{"id": "seg-1", "speakerId": "spk1", "assignedVoice": "Charon", '
                '"balochiText": "...", "transliteration": "...", "translation": "...", "deliveryHint": "..."}]}'
            )
            try:
                with st.spinner("در حال تقسیم..."):
                    st.session_state.baloch_tag = generate_balochi_json(client, system_instruction, user_prompt)
            except Exception as exc:
                st.error(f"تقسیم ناموفق بود: {exc}")

    tagged = st.session_state.get("baloch_tag")
    if tagged:
        speakers = tagged.get("speakers") or []
        segs = tagged.get("segments") or []
        if speakers:
            st.markdown("**گوینده‌ها:** " + " · ".join(
                f"{s.get('name', '')} ({s.get('voice', '')})" for s in speakers
            ))
        for seg in segs:
            spk = seg.get("speakerName") or seg.get("speakerId") or "?"
            st.markdown(f"**{spk}** — {seg.get('balochiText', '')}")
            cap = seg.get("transliteration", "")
            if seg.get("deliveryHint"):
                cap += " — " + seg.get("deliveryHint", "")
            st.caption(cap)
        if segs and st.button("خواندن با دو گوینده", type="primary", use_container_width=True, key="baloch_tag_read"):
            spk1_name = next((s.get("name") for s in speakers if s.get("id") == "spk1"), "راوی")
            spk2_name = next((s.get("name") for s in speakers if s.get("id") == "spk2"), "جوان")
            voice1 = next((s.get("voice") for s in speakers if s.get("id") == "spk1"), "Charon")
            voice2 = next((s.get("voice") for s in speakers if s.get("id") == "spk2"), "Puck")
            if spk1_name == spk2_name:
                spk2_name = "جوان"
            lines = []
            for seg in segs:
                sid = seg.get("speakerId") or "spk1"
                who = spk1_name if sid == "spk1" else spk2_name
                txt = seg.get("balochiText") or ""
                if txt:
                    lines.append(f"{who}: {txt}")
            if not lines:
                st.error("بخش‌بندی خالی بود.")
            else:
                try:
                    blocks, config = build_multi_input(
                        "\n".join(lines), spk1_name, spk2_name, voice1, voice2, "", ""
                    )
                    with st.spinner("در حال دکلمه..."):
                        wav, raw, took = generate_audio(
                            client, "gemini-3.8-flash-tts", blocks, config, False, "audio/wav", 24000
                        )
                    st.session_state.baloch_audio = {"wav": wav, "label": "دکلمه دو صدایی"}
                except Exception as exc:
                    st.error(f"{exc}")
                    st.info(explain_error(exc))

# نمایش خروجی صوتی بخش بلوچی (مشترک بین تب‌ها)
if st.session_state.get("baloch_audio"):
    st.audio(st.session_state.baloch_audio["wav"], format="audio/wav")
    st.caption(st.session_state.baloch_audio.get("label", ""))
    st.download_button(
        "دانلود WAV", data=st.session_state.baloch_audio["wav"],
        file_name="baloch.wav", mime="audio/wav", key="baloch_dl",
    )

# ----------------------------- Voice design -----------------------------

def sanitize_voice_prompt(prompt_text):
    if not prompt_text:
        return ""
    forbidden = [
        "کودک", "نوجوان", "بچه", "نابالغ", "دختر بچه", "پسر بچه",
        "teen", "teenager", "child", "kid", "minor", "young girl", "young boy",
    ]
    sanitized = prompt_text
    for word in forbidden:
        sanitized = re.sub(re.escape(word), "", sanitized, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", sanitized).strip()

def create_prompted_voice(client, model_name, display_name, prompt_text, gender="", language_code=""):
    safe_prompt = sanitize_voice_prompt(prompt_text)
    if not safe_prompt:
        raise ValueError("بعد از پاک‌سازی، توضیح صدا خالی شد.")
    voice_payload = {
        "model": model_name,
        "type": "prompted",
        "display_name": (display_name or "Custom Voice").strip()[:80] or "Custom Voice",
        "prompted": {"input": safe_prompt[:2000]},
    }
    if gender and gender != "—":
        voice_payload["gender"] = gender
    if language_code and language_code.strip():
        voice_payload["language_code"] = language_code.strip()
    try:
        return client.voices.create(store=True, voice=voice_payload)
    except Exception as exc:
        if "safety" in str(exc).lower():
            raise ValueError(
                "توضیح صدا توسط فیلتر ایمنی بسته شد. سن و توصیف ظاهری حساس را حذف کنید."
            ) from exc
        raise

def voice_sample_wav(created):
    sample = getattr(created, "sample_audio", None)
    if sample is None:
        return None
    raw = decode_b64(getattr(sample, "data", None))
    if not raw:
        return None
    mime = (getattr(sample, "mime_type", "") or "").lower()
    if raw.startswith(b"RIFF"):
        return raw
    if "mulaw" in mime:
        return pcm_to_wav_bytes(mulaw_to_pcm16(raw))
    if "alaw" in mime:
        return pcm_to_wav_bytes(alaw_to_pcm16(raw))
    return pcm_to_wav_bytes(raw)

def voice_identifier(created, store=True):
    if not store:
        return getattr(created, "key", None) or getattr(created, "id", "") or ""
    return getattr(created, "id", None) or getattr(created, "key", "") or ""

def register_voice(created, display_name, store=True):
    ident = voice_identifier(created, store)
    entry = {
        "id": ident,
        "display_name": display_name or ident,
        "sample": voice_sample_wav(created),
    }
    st.session_state.last_created_voice = entry
    st.session_state.created_voices = [v for v in st.session_state.created_voices if v.get("id") != ident]
    st.session_state.created_voices.insert(0, entry)
    st.session_state.created_voices = st.session_state.created_voices[:20]
    if ident:
        st.session_state.pending_voice_id = ident
    return ident

CONSENT_EN = (
    "I am the owner of this voice and I consent to Google using this voice "
    "to create a synthetic voice model."
)

with st.expander("🎨 طراحی صدای سفارشی", expanded=False):
    st.caption("POST voices با type=prompted و store=true. شناسه voice_ را بعداً در منبع صدای سفارشی بگذارید. سقف ۲۰۰ صدا.")
    vd1, vd2 = st.columns(2)
    with vd1:
        vd_display_name = st.text_input("نام نمایشی", value="راوی گرم فارسی", key="vd_name")
        vd_gender = st.selectbox("جنسیت", ["—", "female", "male", "neutral"], key="vd_gender")
        vd_lang = st.text_input("کد زبان", value="fa-IR", key="vd_lang")
    with vd2:
        vd_model = st.selectbox("مدل ساخت", MODELS, index=0, key="vd_model")
        st.caption("شخصیت را یک‌بار اینجا بسازید. در style گفتار، سن و لهجه را تکرار نکنید.")
    vd_prompt = st.text_area(
        "توضیح شخصیت",
        height=90,
        key="vd_prompt",
        value="یک راوی بزرگسال با صدای گرم، آرام و واضح، مناسب پادکست.",
    )
    b1, b2 = st.columns(2)
    if b1.button("ساخت صدا", type="primary", use_container_width=True, key="vd_create_btn"):
        try:
            with st.spinner("در حال طراحی صدا..."):
                created = create_prompted_voice(client, vd_model, vd_display_name, vd_prompt, vd_gender, vd_lang)
            voice_id = register_voice(created, vd_display_name, store=True)
            st.success(f"ساخته شد: {voice_id}")
        except Exception as exc:
            st.error(f"ساخت صدا ناموفق بود: {exc}")
            with st.expander("جزئیات"):
                st.code(traceback.format_exc(), language="text")
    if b2.button("صداهای ذخیره‌شده پروژه", use_container_width=True, key="vd_list_btn"):
        try:
            with st.spinner("دریافت لیست..."):
                response = client.voices.list(type_=["prompted", "replicated"], page_size=20)
            remote = list(response.voices or [])
            if not remote:
                st.info("صدای سفارشی ذخیره‌شده‌ای نیست.")
            else:
                for voice in remote:
                    vid = getattr(voice, "id", "")
                    prompted = getattr(voice, "prompted", None)
                    base = getattr(prompted, "base_voice", "") if prompted else ""
                    if vid and not any(x.get("id") == vid for x in st.session_state.created_voices):
                        st.session_state.created_voices.append({
                            "id": vid,
                            "display_name": getattr(voice, "display_name", "") or vid,
                            "sample": None,
                            "base": base or "",
                            "kind": getattr(voice, "type", "") or "",
                        })
                st.success(f"{len(remote)} صدا بارگذاری شد.")
        except Exception as exc:
            st.error(f"لیست صداها ناموفق بود. google-genai>=2.25.0 لازم است. {exc}")
    if st.session_state.last_created_voice:
        lv = st.session_state.last_created_voice
        st.markdown(f"آخرین شناسه: `{lv['id']}`")
        if lv.get("sample"):
            st.audio(lv["sample"], format="audio/wav")
        if st.button("استفاده از این شناسه در گفتار", key="use_last_voice"):
            remember_voice(lv["id"])
            st.rerun()

with st.expander("بازترکیب صدا", expanded=False):
    st.caption(
        "همان POST voices با type=prompted، به‌اضافه prompted.base_voice. "
        "صدای پایه عوض نمی‌شود؛ یک voice_ تازه ذخیره می‌شود. ساخت با flash است و شناسه روی هر دو مدل کار می‌کند. طرح پولی لازم است."
    )
    r1, r2 = st.columns(2)
    with r1:
        remix_base_pick = st.selectbox("صدای پایه پیش‌ساخته", ALL_VOICES, index=ALL_VOICES.index("Puck"), key="remix_base_pick")
        remix_base_custom = st.text_input("یا شناسه پایهٔ دیگر", placeholder="voice_... یا نام کتابخانه", key="remix_base_custom")
    with r2:
        remix_name = st.text_input("نام نمایشی", value="نسخه بازترکیب‌شده", key="remix_name")
        st.caption("یک یا دو ویژگی را عوض کنید: سن، زیروبم، انرژی، لهجه یا سرعت.")
    remix_prompt = st.text_area(
        "تغییر نسبت به صدای پایه",
        height=80,
        key="remix_prompt",
        value="Make the voice slightly older, warmer, and a little lower in pitch.",
    )
    if st.button("ساخت نسخه تازه", type="primary", key="remix_btn"):
        base = (remix_base_custom or "").strip() or remix_base_pick
        instruction = sanitize_voice_prompt(remix_prompt)
        if not instruction:
            st.error("توضیح تغییر را بنویسید.")
        else:
            try:
                with st.spinner("در حال بازترکیب..."):
                    created = client.voices.create(
                        store=True,
                        voice={
                            "model": "gemini-3.8-flash-tts",
                            "type": "prompted",
                            "display_name": (remix_name or "Remixed").strip()[:80],
                            "prompted": {"base_voice": base, "input": instruction[:2000]},
                        },
                    )
                ident = register_voice(created, remix_name, store=True)
                st.success(f"نسخه تازه: {ident}")
            except Exception as exc:
                st.error(f"بازترکیب ناموفق بود: {exc}")

with st.expander("تکثیر صدا", expanded=False):
    st.caption(
        "دو فایل WAV از یک گویندهٔ بزرگسال: ۱۰ تا ۳۰ ثانیه گفتار، و خواندن دقیق جملهٔ رضایت. "
        "۲۴ کیلوهرتز، مونو، ۱۶ بیت بهتر است. طرح پولی لازم است. واترمارک SynthID روی خروجی می‌ماند."
    )
    st.code(CONSENT_EN, language=None)
    st.caption("فارسی در فهرست ۳۰ زبان جملهٔ رضایت نیست. جمله باید همان متن یکی از زبان‌های سند، مثلاً انگلیسی، باشد.")
    rep1, rep2 = st.columns(2)
    with rep1:
        source_file = st.file_uploader("گفتار مرجع", type=["wav"], key="rep_source")
        consent_file = st.file_uploader("فایل رضایت", type=["wav"], key="rep_consent")
    with rep2:
        rep_name = st.text_input("نام نمایشی", value="گوینده تکثیرشده", key="rep_name")
        rep_store = st.checkbox("ذخیره در پروژه (voice_)", value=True, key="rep_store", help="خاموش یعنی کلید بی‌حالت voicekey_ با عمر ۷ روز.")
        rep_model = st.selectbox("مدل ساخت", MODELS, index=1 if len(MODELS) > 1 else 0, key="rep_model")
    if st.button("تکثیر", type="primary", key="rep_btn"):
        if source_file is None or consent_file is None:
            st.error("هر دو فایل WAV لازم است.")
        else:
            try:
                source_b64 = base64.b64encode(source_file.getvalue()).decode("utf-8")
                consent_b64 = base64.b64encode(consent_file.getvalue()).decode("utf-8")
                voice_body = {
                    "model": rep_model,
                    "type": "replicated",
                    "replicated": {
                        "source_audio": {"mime_type": "audio/wav", "data": source_b64},
                        "consent_audio": {"mime_type": "audio/wav", "data": consent_b64},
                    },
                }
                if rep_store:
                    voice_body["display_name"] = (rep_name or "Replicated").strip()[:80]
                with st.spinner("در حال تأیید و تکثیر..."):
                    created = client.voices.create(store=rep_store, voice=voice_body)
                ident = register_voice(created, rep_name, store=rep_store)
                st.success(f"ساخته شد: {ident}")
                if not rep_store:
                    st.caption("این کلید ۷ روز اعتبار دارد. برای تمدید، همان دو فایل را دوباره بفرستید.")
            except Exception as exc:
                st.error(f"تکثیر ناموفق بود: {exc}")

with st.expander("مدیریت صداهای ذخیره‌شده", expanded=False):
    st.caption("لیست، sample_audio را برنمی‌گرداند. پیش‌نمایش با voices.get و حذف با voices.delete است.")
    manage_id = st.text_input("شناسه voice_", key="manage_voice_id", placeholder="voice_...")
    g1, g2, g3 = st.columns(3)
    if g1.button("پیش‌نمایش", key="manage_get", use_container_width=True):
        if not manage_id.strip():
            st.error("شناسه را وارد کنید.")
        else:
            try:
                info = client.voices.get(id=manage_id.strip())
                sample = voice_sample_wav(info)
                name = getattr(info, "display_name", "") or manage_id.strip()
                st.session_state.managed_preview = {"id": manage_id.strip(), "name": name, "sample": sample}
            except Exception as exc:
                st.error(f"دریافت صدا ناموفق بود: {exc}")
    if g2.button("استفاده در گفتار", key="manage_use", use_container_width=True):
        if manage_id.strip():
            remember_voice(manage_id.strip())
            st.rerun()
    confirm_delete = g3.checkbox("حذف", key="manage_confirm_delete")
    if confirm_delete and st.button("حذف دائمی این صدا", key="manage_delete"):
        if not manage_id.strip():
            st.error("شناسه را وارد کنید.")
        else:
            try:
                client.voices.delete(id=manage_id.strip())
                st.session_state.created_voices = [
                    v for v in st.session_state.created_voices if v.get("id") != manage_id.strip()
                ]
                st.success("حذف شد.")
            except Exception as exc:
                st.error(f"حذف ناموفق بود: {exc}")
    preview = st.session_state.get("managed_preview")
    if preview and preview.get("sample"):
        st.caption(preview.get("name") or preview.get("id"))
        st.audio(preview["sample"], format="audio/wav")

with st.expander("📚 کتابخانه صدای گسترده", expanded=False):
    st.caption("client.voices.list — فیلترها با AND و مقدارهای هر فیلتر با OR ترکیب می‌شوند.")
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        lib_search = st.text_input("جستجو", key="lib_search")
    with f2:
        lib_lang = st.text_input("زبان", value="fa-IR", key="lib_lang")
    with f3:
        lib_gender = st.selectbox("جنسیت", ["—", "female", "male", "neutral"], key="lib_gender")
    with f4:
        lib_type = st.selectbox("نوع", ["prebuilt", "prompted", "replicated"], key="lib_type")
    f5, f6 = st.columns(2)
    with f5:
        lib_pitch = st.selectbox("زیروبم", ["—", "low", "medium", "high"], key="lib_pitch")
    with f6:
        lib_context = st.selectbox(
            "کاربرد",
            ["—", "Conversational", "Audiobook", "News"],
            key="lib_context",
        )
    if st.button("جستجو", key="lib_search_btn"):
        try:
            kwargs = {"page_size": 30, "type_": [lib_type]}
            if lib_search.strip():
                kwargs["search"] = lib_search.strip()
            if lib_lang.strip():
                kwargs["language_code"] = [lib_lang.strip()]
            if lib_gender != "—":
                kwargs["gender"] = [lib_gender]
            if lib_pitch != "—":
                kwargs["pitch"] = [lib_pitch]
            if lib_context != "—":
                kwargs["contexts"] = [lib_context]
            page = client.voices.list(**kwargs)
            rows = []
            for voice in page.voices or []:
                rows.append({
                    "id": getattr(voice, "id", "") or "",
                    "name": getattr(voice, "display_name", "") or "",
                    "language": getattr(voice, "language_code", "") or "",
                    "accent": getattr(voice, "accent", "") or "",
                    "gender": getattr(voice, "gender", "") or "",
                    "pitch": getattr(voice, "pitch", "") or "",
                })
            st.session_state.library_rows = rows
            st.session_state.library_page_token = getattr(page, "next_page_token", "") or ""
        except Exception as exc:
            st.error(f"جستجو ناموفق بود: {exc}")
    rows = st.session_state.library_rows
    if rows:
        labels = [f"{r['id']} — {r['name']} ({r['language']}, {r['gender']})" for r in rows]
        pick = st.selectbox("نتیجه", labels, key="lib_pick")
        picked_id = rows[labels.index(pick)]["id"]
        st.caption(picked_id)
        if st.button("گذاشتن این شناسه در فیلد صدای سفارشی", key="use_library_voice"):
            remember_voice(picked_id)
            st.rerun()
        if st.session_state.library_page_token:
            st.caption("نتیجه بیشتر از یک صفحه است. page_size روی ۳۰ صدا است؛ جستجو را دقیق‌تر کنید.")

if st.session_state.pending_voice_id:
    vid = st.session_state.pending_voice_id
    st.session_state.single_voice_source = "سفارشی (voice_... / voicekey_...)"
    st.session_state.single_custom_voice = vid
    st.session_state.voice1_source = "سفارشی"
    st.session_state.custom_voice_1 = vid
    st.session_state.pending_voice_id = ""

# ----------------------------- Generation config -----------------------------

st.header("تنظیمات تولید")
c1, c2, c3 = st.columns(3)
with c1:
    mode = st.radio("حالت", ["تک‌بلندگو", "چندبلندگو"], horizontal=True)
with c2:
    model = st.selectbox(
        "مدل",
        MODELS,
        index=0,
        help="lite: حجم بالا و تأخیر کم. flash: وفاداری استودیویی، دیالوگ چندگوینده و لهجه. طرح درخواست هر دو یکی است.",
    )
    if model.endswith("lite-tts"):
        st.caption("lite برای تولید روزمره و تک‌گویی است. دیالوگ سنگین را با flash امتحان کنید.")
with c3:
    streaming = st.checkbox("استریمینگ", value=False, help="تکه‌های PCM خام تا پایان جمع می‌شوند و یک WAV ساخته می‌شود.")

mime_label = st.selectbox("فرمت API در حالت غیر استریم", list(MIME_TYPES), disabled=streaming)
mime_type = MIME_TYPES[mime_label]
sample_rate = st.selectbox(
    "نرخ نمونه",
    SAMPLE_RATES,
    index=0,
    format_func=lambda r: f"{r:,} Hz",
    help="۲۴۰۰۰ پیش‌فرض سند است. در استریم، نرخ غیر از ۲۴۰۰۰ با mime_type برابر audio/l16 فرستاده می‌شود.",
)
if mime_type in ("audio/mulaw", "audio/alaw") and sample_rate != 8000:
    st.caption("برای تلفن، mu-law و A-law معمولاً ۸۰۰۰ هرتز هستند.")

# ----------------------------- Transcript -----------------------------

with st.expander("تولید خودکار متن", expanded=False):
    g1, g2, g3 = st.columns(3)
    with g1:
        topic = st.text_input("موضوع", "تکنولوژی و هوش مصنوعی")
    with g2:
        transcript_style = st.selectbox("سبک متن", ["پادکست", "مصاحبه", "گفت‌وگوی دوستانه", "بحث علمی", "داستان"])
    with g3:
        language = st.selectbox("زبان", ["فارسی", "بلوچی", "تشخیص خودکار"])
    word_count = st.slider("حدود کلمه", 50, 500, 150, step=25)
    if st.button("نوشتن با Gemini", use_container_width=True):
        try:
            with st.spinner("در حال نوشتن..."):
                spk1_name = st.session_state.get("speaker_name_1", "مرد")
                spk2_name = st.session_state.get("speaker_name_2", "زن")
                if language == "تشخیص خودکار":
                    lang_instruction = "اگر موضوع بلوچی است بلوچی بنویس، وگرنه فارسی روان."
                else:
                    lang_instruction = f"متن دقیقاً به زبان {language} باشد."
                if mode == "تک‌بلندگو":
                    prompt = (
                        f"یک متن گفتاری حدود {word_count} کلمه بنویس. {lang_instruction} "
                        f"سبک {transcript_style}، درباره «{topic}». "
                        "فقط خود گفتار را برگردان. نام گوینده، عنوان و توضیح صحنه ننویس."
                    )
                else:
                    prompt = (
                        f"یک گفت‌وگو حدود {word_count} کلمه بنویس. {lang_instruction} "
                        f"سبک {transcript_style}، درباره «{topic}». "
                        f"فقط خطوط «{spk1_name}: متن» و «{spk2_name}: متن». توضیح اضافه ننویس."
                    )
                response = generate_text_with_retry(client, model="gemini-2.5-flash", prompt=prompt)
                st.session_state.generated_transcript = response.text or ""
                st.session_state.generated_preview = st.session_state.generated_transcript
            st.success("متن آماده شد.")
        except Exception as exc:
            st.error(f"تولید متن ناموفق بود: {exc}")
    if st.session_state.generated_transcript:
        st.text_area("متن تولیدشده", key="generated_preview", height=120)
        if st.button("بردن به ویرایشگر"):
            target = "single_text_value" if mode == "تک‌بلندگو" else "multi_text_value"
            st.session_state[target] = st.session_state.generated_transcript
            st.rerun()

# ----------------------------- Speakers and text -----------------------------

speaker1, speaker2 = "مرد", "زن"
voice1, voice2, style1, style2 = "Kore", "Aoede", "", ""
selected_voice, style_single = "Kore", ""

def style_picker(label, key_prefix):
    choice = st.selectbox(label, list(PREDEFINED_STYLES.keys()), key=f"{key_prefix}_choice")
    if choice == "سفارشی (Custom)":
        return st.text_input("سبک انگلیسی", placeholder="warm and enthusiastic", key=f"{key_prefix}_custom")
    return PREDEFINED_STYLES[choice]

if mode == "تک‌بلندگو":
    voice_source = st.radio(
        "منبع صدا",
        ["پیش‌ساخته", "سفارشی (voice_... / voicekey_...)"],
        horizontal=True,
        key="single_voice_source",
    )
    v1, v2 = st.columns(2)
    with v1:
        if voice_source == "پیش‌ساخته":
            selected_voice = st.selectbox(
                "صدا",
                ALL_VOICES,
                index=ALL_VOICES.index("Kore"),
                format_func=lambda v: f"{v} — {VOICE_DESCRIPTIONS.get(v, '')}",
                key="single_prebuilt_voice",
            )
        else:
            selected_voice = st.text_input(
                "شناسه صدا",
                placeholder="voice_... یا voicekey_... یا نام کتابخانه",
                key="single_custom_voice",
            ).strip()
    with v2:
        style_single = style_picker("سبک بیان", "single_style")
    text_input = st.text_area("متن", key="single_text_value", height=220, placeholder="متن را اینجا بنویسید. نام گوینده نگذارید.")
else:
    v1, v2 = st.columns(2)
    with v1:
        speaker1 = st.text_input("نام گوینده ۱", "مرد", key="speaker_name_1")
        voice1_source = st.radio("منبع صدای ۱", ["پیش‌ساخته", "سفارشی"], horizontal=True, key="voice1_source")
        if voice1_source == "پیش‌ساخته":
            voice1 = st.selectbox(
                "صدای ۱", ALL_VOICES, index=ALL_VOICES.index("Kore"),
                format_func=lambda v: f"{v} — {VOICE_DESCRIPTIONS.get(v, '')}", key="voice_1",
            )
        else:
            voice1 = st.text_input("شناسه صدای ۱", placeholder="voice_...", key="custom_voice_1").strip()
        style1 = style_picker("سبک ۱", "style_1")
    with v2:
        speaker2 = st.text_input("نام گوینده ۲", "زن", key="speaker_name_2")
        voice2_source = st.radio("منبع صدای ۲", ["پیش‌ساخته", "سفارشی"], horizontal=True, key="voice2_source")
        if voice2_source == "پیش‌ساخته":
            voice2 = st.selectbox(
                "صدای ۲", ALL_VOICES, index=ALL_VOICES.index("Aoede"),
                format_func=lambda v: f"{v} — {VOICE_DESCRIPTIONS.get(v, '')}", key="voice_2",
            )
        else:
            voice2 = st.text_input("شناسه صدای ۲", placeholder="voice_...", key="custom_voice_2").strip()
        style2 = style_picker("سبک ۲", "style_2")
    if not speaker1.strip() or not speaker2.strip() or speaker1.strip() == speaker2.strip():
        st.warning("نام دو گوینده باید پر و متفاوت باشد. نام‌ها خوانده نمی‌شوند.")
    split_needed = is_custom_voice(voice1) or is_custom_voice(voice2)
    if split_needed:
        st.info("حداقل یک صدا سفارشی است. نوبت‌ها جدا با audio/l16 ساخته و به یک WAV وصل می‌شوند.")
    with st.expander("قالب‌بندی شعر و دیالوگ", expanded=False):
        raw = st.text_area("متن خام", height=140, key="raw_multi")
        strategy_label = st.selectbox(
            "روش",
            ["تشخیص خودکار", "خط به خط", "بیت به بیت (هر دو خط)", "بند به بند", "خط تیره", "تعداد خط در هر نوبت", "نگاشت نام گوینده", "جداکننده سفارشی"],
        )
        sep, mapping, n_lines = "---", f"{speaker1}=1, {speaker2}=2", 2
        if strategy_label == "جداکننده سفارشی":
            sep = st.text_input("جداکننده", "---")
        if strategy_label == "نگاشت نام گوینده":
            mapping = st.text_input("نگاشت", mapping)
        if strategy_label == "تعداد خط در هر نوبت":
            n_lines = st.number_input("تعداد خط", min_value=1, max_value=20, value=2)
        if st.button("پیش‌نمایش", use_container_width=True):
            strategies = {
                "تشخیص خودکار": detect_strategy(raw),
                "خط به خط": "line",
                "بیت به بیت (هر دو خط)": "couplet",
                "بند به بند": "stanza",
                "خط تیره": "dash",
                "تعداد خط در هر نوبت": "n_lines",
                "نگاشت نام گوینده": "mapping",
                "جداکننده سفارشی": "separator",
            }
            st.session_state.formatted_preview = format_multispeaker(
                raw, strategies[strategy_label], speaker1, speaker2, sep, mapping, n_lines
            )
        if st.session_state.formatted_preview:
            st.code(st.session_state.formatted_preview, language=None)
            if st.button("اعمال در متن نهایی", type="primary"):
                st.session_state.multi_text_value = st.session_state.formatted_preview
                st.rerun()
    text_input = st.text_area(
        "متن نهایی",
        key="multi_text_value",
        height=260,
        placeholder=f"{speaker1}: سلام\n{speaker2}: سلام",
        help="نام قبل از دونقطه فقط برچسب است و داخل text API نمی‌رود.",
    )

text_key = "single_text_value" if mode == "تک‌بلندگو" else "multi_text_value"
st.caption("افزودن برچسب به انتهای متن. در موبایل دکمه‌ها دو ستونه می‌شکنند.")
tag_cols = st.columns(4)
for i, tag in enumerate(QUICK_TAGS):
    tag_cols[i % 4].button(tag, key=f"tagbtn_{mode}_{i}", on_click=append_tag, args=(text_key, tag), use_container_width=True)

st.subheader("نمونه")
s1, s2, s3, s4 = st.columns(4)
s1.button("تک‌گوینده", use_container_width=True, on_click=load_single_sample)
s2.button("گفت‌وگو", use_container_width=True, on_click=load_multi_sample)
s3.button("شعر", use_container_width=True, on_click=load_poem_sample)
s4.button("واکنش شنونده", use_container_width=True, on_click=load_backchannel_sample)

# ----------------------------- Validate -----------------------------

with st.expander("متن طولانی و نرم‌سازی", expanded=False):
    soften = st.checkbox("جایگزینی واژه‌های حساس قبل از ارسال", value=False, help="اگر روشن باشد، متنِ خوانده‌شده با نسخه سندِ کلمه‌به‌کلمه فرق می‌کند.")
    chunk_long_text = st.checkbox("تقسیم متن طولانی به چند درخواست", value=False)
    chunk_size = st.slider("سقف کاراکتر هر بخش", 1000, 6000, 3500, 250, disabled=not chunk_long_text)
text_input = text_input or ""
token_est = estimate_tokens(text_input)
st.caption(f"{len(text_input):,} کاراکتر · تخمین محافظه‌کارانه {token_est:,} از {INPUT_TOKEN_LIMIT:,} توکن ورودی")
if not text_input.strip():
    st.info("متن را وارد کنید.")
elif token_est > INPUT_TOKEN_LIMIT and not chunk_long_text:
    st.warning("احتمالاً از سقف ۸۱۹۲ توکن ورودی رد می‌شود. تقسیم متن را روشن کنید یا متن را کوتاه کنید.")
elif len(text_input) > 18000 and not chunk_long_text:
    st.warning("متن خیلی بلند است. تقسیم را روشن کنید یا کوتاه‌ترش کنید.")

multi_valid = bool(speaker1.strip() and speaker2.strip() and speaker1.strip() != speaker2.strip())
voice_valid = bool(str(selected_voice).strip()) if mode == "تک‌بلندگو" else bool(str(voice1).strip() and str(voice2).strip())
can_generate = (
    bool(text_input.strip())
    and voice_valid
    and (mode != "چندبلندگو" or multi_valid)
    and (token_est <= INPUT_TOKEN_LIMIT or chunk_long_text)
)
if text_input.strip() and not voice_valid:
    st.warning("صدا را انتخاب یا شناسه را وارد کنید.")

split_custom = mode == "چندبلندگو" and (is_custom_voice(voice1) or is_custom_voice(voice2))
preview_blocks, preview_config = None, None
preview_error = ""
try:
    if text_input.strip() and voice_valid and mode == "تک‌بلندگو":
        preview_blocks, preview_config = build_single_input(text_input.strip()[:500], selected_voice, style_single)
    elif text_input.strip() and voice_valid and multi_valid and not split_custom:
        preview_blocks, preview_config = build_multi_input(
            "\n".join(text_input.splitlines()[:4]), speaker1, speaker2, voice1, voice2, style1, style2
        )
except ValueError as exc:
    preview_error = str(exc)

with st.expander("شکل درخواست، مطابق سند", expanded=False):
    if split_custom:
        st.write("هر خط یک درخواست تک‌بلندگو با `audio/l16` است و PCMها به هم وصل می‌شوند.")
    elif preview_error:
        st.warning(preview_error)
    elif preview_blocks is not None:
        st.json({
            "model": model,
            "input": preview_blocks,
            "response_format": response_format_for(streaming, mime_type, sample_rate),
            "generation_config": {"speech_config": preview_config},
            "stream": streaming,
        })
    else:
        st.caption("بعد از وارد کردن متن، بدنه درخواست اینجا دیده می‌شود.")

telegram_ready = bool(get_secret("TELEGRAM_BOT_TOKEN") and get_secret("TELEGRAM_CHAT_ID"))
send_telegram = st.checkbox("بعد از تولید به تلگرام بفرست", value=False, disabled=not telegram_ready)

# ----------------------------- Generate -----------------------------

if st.button("🎧 تولید صدا", type="primary", use_container_width=True, disabled=not can_generate):
    try:
        sent = sanitize_input_text(text_input) if soften else text_input
        if sent != text_input:
            st.warning("برخی واژه‌ها قبل از ارسال جایگزین شدند.")
            with st.expander("متن ارسال‌شده"):
                st.text(sent)

        jobs = []
        if split_custom:
            for line in sent.splitlines():
                if not line.strip():
                    continue
                spk, content = parse_speaker_line(line, speaker1, speaker2)
                if not content:
                    continue
                voice = voice1 if spk == speaker1 else voice2
                style = style1 if spk == speaker1 else style2
                blocks, config = build_single_input(content, voice, style)
                jobs.append((blocks, config, False, "audio/l16"))
            if not jobs:
                raise ValueError("نوبت معتبری برای چسباندن پیدا نشد.")
            if len(jobs) > CUSTOM_TURN_LIMIT:
                raise ValueError(f"برای صدای سفارشی حداکثر {CUSTOM_TURN_LIMIT} نوبت در هر بار. متن را کوتاه کنید.")
        else:
            if chunk_long_text:
                chunks = split_multispeaker_lines(sent, int(chunk_size)) if mode == "چندبلندگو" else split_text_safely(sent, int(chunk_size))
            else:
                chunks = [sent.strip()]
            for chunk in chunks:
                if mode == "تک‌بلندگو":
                    blocks, config = build_single_input(chunk, selected_voice, style_single)
                else:
                    blocks, config = build_multi_input(
                        chunk, speaker1, speaker2, voice1, voice2, style1, style2
                    )
                jobs.append((blocks, config, streaming, mime_type))

        progress = st.progress(0, text="شروع")
        wav_parts = []
        raw_parts = []
        elapsed = 0.0
        for i, (blocks, config, stream_flag, job_mime) in enumerate(jobs):
            progress.progress(i / len(jobs), text=f"بخش {i + 1} از {len(jobs)}")
            wav_data, raw, took = generate_audio(
                client, model, blocks, config, stream_flag, job_mime, sample_rate
            )
            wav_parts.append(wav_data)
            raw_parts.append(raw)
            elapsed += took
        progress.progress(1.0, text="آماده")
        merged = wav_parts[0] if len(wav_parts) == 1 else join_wavs(wav_parts)
        label = f"{mode} · {model} · {sample_rate} Hz · {len(sent)} کاراکتر · {elapsed:.1f}s"
        st.session_state.last_result = {
            "wav": merged,
            "raw": b"".join(raw_parts) if len(raw_parts) == 1 else None,
            "raw_mime": jobs[0][3] if len(jobs) == 1 and not streaming else None,
            "label": label,
            "sent": sent,
        }
        st.session_state.history.insert(0, {"wav": merged, "label": label})
        st.session_state.history = st.session_state.history[:HISTORY_LIMIT]
        if send_telegram:
            ok, msg = send_to_telegram(merged, "gemini-tts.wav", label)
            (st.success if ok else st.error)(msg)
    except Exception as exc:
        st.error(f"{exc}")
        st.info(explain_error(exc))
        with st.expander("جزئیات فنی"):
            st.code(traceback.format_exc(), language="text")

result = st.session_state.last_result
if result and result.get("wav"):
    st.success("صدا آماده است.")
    st.audio(result["wav"], format="audio/wav")
    d1, d2 = st.columns(2)
    d1.download_button("دانلود WAV", data=result["wav"], file_name="gemini-tts.wav", mime="audio/wav", use_container_width=True)
    raw_mime = result.get("raw_mime")
    if result.get("raw") and raw_mime in RAW_EXT:
        d2.download_button(
            f"دانلود {RAW_EXT[raw_mime]}",
            data=result["raw"],
            file_name=f"gemini-tts.{RAW_EXT[raw_mime]}",
            mime="application/octet-stream",
            use_container_width=True,
        )
    st.caption(result["label"])
    if telegram_ready and st.button("ارسال همین فایل به تلگرام"):
        ok, msg = send_to_telegram(result["wav"], "gemini-tts.wav", result["label"])
        (st.success if ok else st.error)(msg)

if st.session_state.history:
    st.subheader("تاریخچه این نشست")
    for i, item in enumerate(st.session_state.history):
        st.caption(item["label"])
        st.audio(item["wav"], format="audio/wav")
        st.download_button(
            "دانلود",
            data=item["wav"],
            file_name=f"gemini-tts-{i + 1}.wav",
            mime="audio/wav",
            key=f"hist_dl_{i}",
        )
