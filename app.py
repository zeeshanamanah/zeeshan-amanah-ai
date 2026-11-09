import os
import json
import asyncio
import tempfile
import threading
import socket

import speech_recognition as sr
import edge_tts

from dotenv import load_dotenv
from google import genai
from google.genai import types
from flask import Flask, request, jsonify, render_template_string


# =========================================================
# ZEESHAN AMANAH AI
# Creator: Mohd Zeeshan Raza
# =========================================================

APP_NAME = "Zeeshan Amanah AI"
CREATOR = "Mohd Zeeshan Raza"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(BASE_DIR, "memory.json")
ENV_FILE = os.path.join(BASE_DIR, ".env")

load_dotenv(ENV_FILE)
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Fast, lightweight model first. The second model is only a backup.
MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
]

SYSTEM_PROMPT = """
Tumhara naam Zeeshan Amanah AI hai.
Tumhare creator Mohd Zeeshan Raza hain.
Tum ek helpful personal assistant ho.
Aasaan Hindi aur Roman Urdu mein seedhe aur chhote jawab do.
Zarurat par Urdu bhi use karo.
Islamic sawalon mein ehtiyat rakho:
- Quran aur authentic Hadith ka hawala tabhi do jab yaqeen ho.
- Galat ya banawati Islamic baat mat batao.
- Yaqeen na ho to saaf batao.
- Mufti ya aalim hone ka daawa mat karo.
User ke sawal ka seedha jawab do.
"""

VOICE_OPTIONS = {
    "male": "hi-IN-MadhurNeural",
    "female": "hi-IN-SwaraNeural",
}

voice_gender = "female"
voice_enabled = True

# =========================================================
# MEMORY
# =========================================================

memory_lock = threading.Lock()


def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, dict):
                data.setdefault("chat_history", [])
                return data
        except Exception as error:
            print("Memory load error:", error)
    return {"chat_history": []}


memory = load_memory()


def save_memory():
    try:
        with memory_lock:
            with open(MEMORY_FILE, "w", encoding="utf-8") as file:
                json.dump(memory, file, ensure_ascii=False, indent=2)
    except Exception as error:
        print("Memory save error:", error)


# =========================================================
# GEMINI
# =========================================================

client = None
if API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
    except Exception as error:
        print("Gemini client error:", error)


def local_answer(question):
    q = question.lower().strip()
    q = q.replace("?", "").replace("!", "").replace(".", "")

    if any(x in q for x in [
        "aap ka name", "aapka name", "aap ka naam", "aapka naam",
        "name batao", "naam batao", "tumhara naam", "your name"
    ]):
        return "Mera naam Zeeshan Amanah AI hai."

    if any(x in q for x in [
        "kisne banaya", "kis ne banaya", "creator kaun",
        "who created you", "banane wala kaun"
    ]):
        return "Mujhe Mohd Zeeshan Raza ne banaya hai."

    if q in [
        "hello", "hi", "salam", "assalamu alaikum",
        "assalamualaikum", "السلام علیکم"
    ]:
        return "Wa Alaikum Assalam! Umeed hai aap khairiyat se hain."

    return None


def ask_ai(question, remember=True):
    local = local_answer(question)
    if local:
        return local

    if client is None:
        return "Gemini API key nahi mili. App folder ki .env file check karein."

    # Mobile visitors do not share or persist chat history with other visitors.
    # Keep PC conversation memory only when remember=True.
    history = []
    if remember:
        with memory_lock:
            history = list(memory.get("chat_history", []))[-6:]

    contents = []
    for item in history:
        role = item.get("role")
        message = item.get("text")
        if role in ("user", "model") and message:
            contents.append({
                "role": role,
                "parts": [{"text": str(message)}]
            })

    contents.append({
        "role": "user",
        "parts": [{"text": question}]
    })

    last_error = None

    for model_name in MODELS:
        try:
            print("\nAI model:", model_name)

            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.5,
                    max_output_tokens=600,
                    candidate_count=1,
                ),
            )

            answer = (response.text or "").strip()
            if not answer:
                answer = "Maaf kijiye, is baar jawab nahi mila."

            if remember:
                with memory_lock:
                    memory["chat_history"].extend([
                        {"role": "user", "text": question},
                        {"role": "model", "text": answer},
                    ])
                    memory["chat_history"] = memory["chat_history"][-20:]
                save_memory()
            return answer

        except Exception as error:
            last_error = error
            error_text = str(error).lower()
            print("Gemini error:", error)

            # Try backup only for temporary overload/server errors.
            temporary = any(code in error_text for code in [
                "503", "429", "500", "502", "504",
                "unavailable", "resource_exhausted",
                "overloaded", "deadline"
            ])
            if not temporary:
                break

            # Intentionally no time.sleep(): don't add an artificial delay.

    print("Final Gemini error:", last_error)
    return (
        "Maaf kijiye, AI server abhi busy hai ya connection mein dikkat hai. "
        "Thodi der baad dobara koshish karein."
    )


# =========================================================
# VOICE (PC)
# =========================================================

async def make_speech_file(text, file_path):
    voice = VOICE_OPTIONS.get(voice_gender, VOICE_OPTIONS["female"])
    communicate = edge_tts.Communicate(
        text=str(text),
        voice=voice,
        rate="+0%",
    )
    await communicate.save(file_path)


def speak(text):
    if not voice_enabled:
        return
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp:
            file_path = temp.name
        asyncio.run(make_speech_file(text, file_path))
        os.startfile(file_path)
    except Exception as error:
        print("Voice error:", error)


# =========================================================
# MICROPHONE (PC)
# =========================================================

def listen_once():
    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            print("\nBolna shuru karein...")
            recognizer.adjust_for_ambient_noise(source, duration=0.4)
            audio = recognizer.listen(source, timeout=8, phrase_time_limit=12)

        print("Awaaz samajh raha hoon...")
        text = recognizer.recognize_google(audio, language="hi-IN")
        print("Aapne kaha:", text)
        return text

    except sr.WaitTimeoutError:
        print("Awaaz nahi mili.")
    except sr.UnknownValueError:
        print("Awaaz samajh nahi aayi.")
    except Exception as error:
        print("Microphone error:", error)

    return None


# =========================================================
# COMMANDS (PC CMD)
# =========================================================

def handle_command(command):
    global voice_gender, voice_enabled

    cmd = command.lower().strip()

    if cmd in ("voice female", "female voice"):
        voice_gender = "female"
        print("Female voice select ho gayi.")
        speak("Female voice select ho gayi.")
        return True

    if cmd in ("voice male", "male voice"):
        voice_gender = "male"
        print("Male voice select ho gayi.")
        speak("Male voice select ho gayi.")
        return True

    if cmd in ("voice off", "awaaz band"):
        voice_enabled = False
        print("Voice band ho gayi.")
        return True

    if cmd in ("voice on", "awaaz chalu"):
        voice_enabled = True
        print("Voice chalu ho gayi.")
        speak("Voice chalu ho gayi.")
        return True

    if cmd in ("mic", "listen", "suno"):
        question = listen_once()
        if question:
            answer = ask_ai(question)
            print("\nZeeshan Amanah AI:", answer)
            speak(answer)
        return True

    if cmd in ("clear memory", "memory clear"):
        with memory_lock:
            memory["chat_history"] = []
        save_memory()
        print("Chat memory clear ho gayi.")
        return True

    if cmd in ("exit", "quit", "bye", "band"):
        print("Allah Hafiz!")
        speak("Allah Hafiz! Apna khayal rakhiye.")
        return False

    return None


# =========================================================
# MOBILE WEBSITE
# =========================================================

web_app = Flask(__name__)

HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#075b45">
<title>Zeeshan Amanah AI</title>
<style>
* { box-sizing: border-box; }
body {
    margin: 0; font-family: Arial, sans-serif;
    background: #101b19; color: #fff;
}
header {
    background: #075b45; padding: 15px 10px;
    text-align: center; position: sticky; top: 0;
}
header h2 { margin: 4px; font-size: 20px; }
header p { margin: 4px; font-size: 12px; opacity: .9; }
#chat {
    padding: 14px; height: calc(100dvh - 145px);
    overflow-y: auto; scroll-behavior: smooth;
}
.msg {
    padding: 12px 14px; margin: 10px 0;
    border-radius: 14px; max-width: 88%;
    white-space: pre-wrap; overflow-wrap: anywhere;
    line-height: 1.5; font-size: 15px;
}
.user { background: #176b52; margin-left: auto; }
.ai { background: #293b36; margin-right: auto; }
footer {
    position: fixed; bottom: 0; left: 0; width: 100%;
    background: #172521; padding: 10px;
    padding-bottom: max(10px, env(safe-area-inset-bottom));
    display: flex; gap: 8px;
}
input {
    flex: 1; min-width: 0; padding: 13px;
    border-radius: 10px; border: none; outline: none;
    font-size: 16px;
}
button {
    background: #0b9b70; color: white; border: 0;
    border-radius: 10px; padding: 0 17px;
    font-size: 15px; font-weight: bold;
}
button:disabled { opacity: .55; }
.small { font-size: 12px; opacity: .7; text-align: center; padding: 4px; }
</style>
</head>
<body>
<header>
    <h2>ZEESHAN AMANAH AI</h2>
    <p>Created by Mohd Zeeshan Raza</p>
    <p>Personal AI Assistant</p>
</header>

<div id="chat">
    <div class="msg ai">Assalamu Alaikum!<br>Umeed hai aap khairiyat se hain.<br><br>Main Zeeshan Amanah AI hoon.</div>
    <div class="small">Apna sawal neeche likhein</div>
</div>

<footer>
    <input id="question" autocomplete="off" placeholder="Apna sawal likhein..."
      onkeydown="if(event.key==='Enter') sendMessage()">
    <button id="sendButton" onclick="sendMessage()">Send</button>
</footer>

<script>
let waiting = false;

async function sendMessage() {
    if (waiting) return;

    const input = document.getElementById("question");
    const chat = document.getElementById("chat");
    const button = document.getElementById("sendButton");
    const question = input.value.trim();

    if (!question) return;

    waiting = true;
    input.value = "";
    button.disabled = true;
    button.textContent = "...";

    const user = document.createElement("div");
    user.className = "msg user";
    user.textContent = question;
    chat.appendChild(user);

    const loading = document.createElement("div");
    loading.className = "msg ai";
    loading.textContent = "Jawab taiyar ho raha hai...";
    chat.appendChild(loading);
    chat.scrollTop = chat.scrollHeight;

    try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 60000);

        const response = await fetch("/chat", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({message: question}),
            signal: controller.signal
        });

        clearTimeout(timer);

        const data = await response.json();
        loading.textContent = data.answer || "Jawab nahi mila.";

    } catch (error) {
        loading.textContent = error.name === "AbortError"
            ? "Jawab aane mein zyada waqt lag raha hai. Dobara koshish karein."
            : "Connection error. PC aur phone ka Wi-Fi check karein.";
    } finally {
        waiting = false;
        button.disabled = false;
        button.textContent = "Send";
        chat.scrollTop = chat.scrollHeight;
        input.focus();
    }
}
</script>
</body>
</html>
"""


@web_app.route("/", methods=["GET"])
def home():
    return render_template_string(HTML_PAGE)


@web_app.route("/chat", methods=["POST"])
def mobile_chat():
    data = request.get_json(silent=True) or {}
    question = str(data.get("message", "")).strip()

    if not question:
        return jsonify({"answer": "Apna sawal likhiye."}), 400

    try:
        # Public mobile requests are stateless: one visitor cannot inherit another visitor's chat.
        answer = ask_ai(question, remember=False)
        return jsonify({"answer": answer})
    except Exception as error:
        print("Mobile chat error:", error)
        return jsonify({"answer": "Maaf kijiye, kuch problem hui."}), 500


def get_lan_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "PC ka IPv4 address ipconfig se dekhein"


def start_web_server():
    def run_server():
        web_app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,
            use_reloader=False,
            threaded=True,
        )

    threading.Thread(target=run_server, daemon=True).start()


# =========================================================
# START
# =========================================================

def main():
    start_web_server()

    print("\n" + "=" * 45)
    print("       ZEESHAN AMANAH AI")
    print("=" * 45)
    print("Creator:", CREATOR)
    print("\nAssalamu Alaikum!")
    print("Umeed hai aap khairiyat se hain.")
    print("\nPhone URL:")
    print("http://" + get_lan_ip() + ":5000")
    print("\nPC commands:")
    print("voice female | voice male | voice on | voice off")
    print("mic | clear memory | exit")
    print("\nAI taiyar hai!")

    if not API_KEY:
        print("\nWARNING: GEMINI_API_KEY nahi mili. .env file check karein.")

    # Don't generate/play a greeting MP3 at startup; it delays startup.
    while True:
        try:
            question = input("\nAap: ").strip()
            if not question:
                continue

            result = handle_command(question)
            if result is False:
                break
            if result is True:
                continue

            answer = ask_ai(question)
            print("\nZeeshan Amanah AI:", answer)
            speak(answer)

        except KeyboardInterrupt:
            print("\nAllah Hafiz!")
            break
        except Exception as error:
            print("App error:", error)


if __name__ == "__main__":
    main()
