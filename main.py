import os
import asyncio
import random
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from groq import Groq

# ==========================================
# 🌍 1. FAKE WEB SERVER (Keeps Render Awake)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is running! Check Telegram Saved Messages."

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# 🔧 CONFIGURATION
# ==========================================
# On Render, these come from "Environment Variables"
# On PC, you can replace os.environ.get(...) with actual values for testing
API_ID = int(os.environ.get("API_ID", 28723682))
API_HASH = os.environ.get("API_HASH", '868a078ba0208b4409208275fa8bc598')
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") # Paste key in Render
SESSION_STRING = os.environ.get("SESSION_STRING") # Paste long string in Render

BOT_USERNAME = 'chatbot' 
MAX_MESSAGES = 10           
PROMO_TRIGGER = 6           

PERSONAS = [
    {"id": "indo", "country": "Indonesia", "role": "Female, 19, Jakarta slang. Shy.", "greetings": ["hai", "halo", "iya?"]},
    {"id": "malay", "country": "Malaysia", "role": "Female, 21, KL style. Polite.", "greetings": ["hi", "hello", "hey you"]},
    {"id": "india", "country": "India", "role": "Female, 22, Mumbai. Hinglish.", "greetings": ["hi", "hello", "hey"]},
    {"id": "uk", "country": "UK", "role": "Female, 17, London. Bored.", "greetings": ["hi", "hello"]},
]

# ==========================================
# 🧠 STATE & LOGIC
# ==========================================
class BotState:
    def __init__(self):
        self.status = "SEARCHING"
        self.paused = False  # <--- The Supervisor Switch
        self.msg_count = 0
        self.current_persona = None
        self.history = []

state = BotState()
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
groq_client = Groq(api_key=GROQ_API_KEY)

# --- AI GENERATOR ---
def generate_ai_reply(user_text, inject_instruction=None):
    if not state.current_persona: return "..."
    p = state.current_persona
    
    system_prompt = (
        f"You are a {p['role']}. Location: {p['country']}. "
        "Rules: Male->act Female. Female->act Male. Short replies (1 sentence). Lowercase. "
        "No excitement. If asked origin first -> 'UK'. "
        "Speak user's language (Indo/Malay/Eng)."
    )
    if inject_instruction:
        system_prompt += f"\n\n[INSTRUCTION]: {inject_instruction}"

    state.history.append({"role": "user", "content": user_text})
    
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt}] + state.history,
            temperature=0.7,
            max_tokens=60
        )
        reply = completion.choices[0].message.content
        state.history.append({"role": "assistant", "content": reply})
        return reply.lower()
    except Exception as e:
        print(f"Groq Error: {e}")
        return "haha yeah"

# ==========================================
# 👮 THE SUPERVISOR (ADMIN COMMANDS)
# ==========================================
# Listens to "Saved Messages" (Me)
@client.on(events.NewMessage(chats='me'))
async def admin_handler(event):
    text = event.raw_text.lower()
    
    if text == "/pause":
        state.paused = True
        await event.reply("⏸️ **SYSTEM PAUSED.**\nI will stop replying to strangers.\nType `/resume` to start.")
        print("--- PAUSED BY ADMIN ---")
    
    elif text == "/resume":
        state.paused = False
        await event.reply("▶️ **SYSTEM RESUMED.**\nBack to work!")
        print("--- RESUMED BY ADMIN ---")
        await client.send_message(BOT_USERNAME, '/next')

    elif text == "/status":
        await event.reply(f"📊 **STATUS REPORT**\nPaused: {state.paused}\nState: {state.status}\nMsgs: {state.msg_count}")

# ==========================================
# 🤖 THE MAIN LISTENER (CHATBOT)
# ==========================================
@client.on(events.NewMessage(chats=BOT_USERNAME))
async def bot_handler(event):
    text = event.raw_text.lower()
    
    # ---------------------------------------
    # 🚨 CAPTCHA GUARD (High Priority)
    # ---------------------------------------
    # If bot sends a PHOTO, it's a captcha (or ad). FREEZE immediately.
    if event.photo:
        state.paused = True
        print("⚠️ CAPTCHA DETECTED (Photo)!")
        await client.send_message('me', "🚨 **CAPTCHA DETECTED!** 🚨\n\nThe bot sent a photo (likely a puzzle).\n1. Go to @chatbot\n2. Solve the puzzle manually.\n3. Wait for 'Partner found' or type `/resume` here.")
        return

    # If bot says "You don't seem to be a robot", AUTO-RESUME
    if "seem to be a robot" in text or "right!" in text:
        if state.paused:
            state.paused = False
            print("✅ Captcha Solved! Auto-Resuming...")
            await client.send_message('me', "✅ **Captcha Solved!** Auto-resuming...")
            # We don't return; we let the logic below handle the "Partner found" that usually follows
            
    # ---------------------------------------
    # 🛑 PAUSE CHECK
    # ---------------------------------------
    if state.paused:
        return  # Stop here. Do not reply. Do not read.

    # ---------------------------------------
    # 🔄 STANDARD LOGIC
    # ---------------------------------------
    if "searching" in text or "looking" in text:
        state.status = "SEARCHING"
        print("🔍 Searching...")
        return

    if "partner found" in text or "connected" in text:
        state.status = "CONNECTED"
        state.msg_count = 0
        state.history = []
        state.current_persona = random.choice(PERSONAS)
        print(f"✅ Connected: {state.current_persona['id']}")
        
        await asyncio.sleep(5)
        await client.send_message(BOT_USERNAME, random.choice(state.current_persona['greetings']))
        return

    if "partner disconnected" in text or "stopped" in text:
        state.status = "SEARCHING"
        await asyncio.sleep(2)
        await client.send_message(BOT_USERNAME, '/next')
        return

    # --- STRANGER CHAT ---
    if state.status == "CONNECTED" and not event.out:
        
        # Slower Reading
        read_time = max(3, min(10, len(text) * 0.3))
        await asyncio.sleep(read_time)
        state.msg_count += 1
        
        override = None
        if state.msg_count == PROMO_TRIGGER:
            override = "IGNORE topic. Suggest @OmeTV_chatbot naturally in CURRENT LANGUAGE."

        if state.msg_count >= MAX_MESSAGES:
            state.status = "EXITING"
            await client.send_message(BOT_USERNAME, "gtg bye")
        else:
            async with client.action(BOT_USERNAME, 'typing'):
                await asyncio.sleep(random.uniform(3, 6))
                reply = generate_ai_reply(text, override)
            await client.send_message(BOT_USERNAME, reply)
            print(f"🤖 AI: {reply}")

        if state.status == "EXITING":
            await asyncio.sleep(3)
            await client.send_message(BOT_USERNAME, '/stop')
            await asyncio.sleep(2)
            await client.send_message(BOT_USERNAME, '/next')

# ==========================================
# 🚀 LAUNCHER
# ==========================================
def main():
    # Start Fake Server (For Render)
    t = Thread(target=run_web_server)
    t.start()
    
    print("--- Cloud Bot Online ---")
    client.start()
    client.run_until_disconnected()

if __name__ == '__main__':

    main()
