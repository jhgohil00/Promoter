import os
import asyncio
import random
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from groq import Groq

# ==========================================
# 🌍 WEB SERVER
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is Online."

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# 🔧 CONFIGURATION
# ==========================================
API_ID = int(os.environ.get("API_ID", 28723682))
API_HASH = os.environ.get("API_HASH", '868a078ba0208b4409208275fa8bc598')
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") 
SESSION_STRING = os.environ.get("SESSION_STRING") 

BOT_USERNAME = 'chatbot' 
MAX_MESSAGES = 10           
PROMO_TRIGGER = 4  # Message #4 is Promo Time

PERSONAS = [
    {"id": "indo", "country": "Indonesia", "role": "19 year old girl from Jakarta. Speak Indo slang.", "greetings": ["hai", "halo", "iya?"]},
    {"id": "malay", "country": "Malaysia", "role": "21 year old girl from KL. Speak Malay/English mix.", "greetings": ["hi", "hello", "hey you"]},
    {"id": "india", "country": "India", "role": "22 year old girl from Mumbai. Speak Hinglish.", "greetings": ["hi", "hello", "hey"]},
    {"id": "uk", "country": "UK", "role": "17 year old girl from London. Speak casual English.", "greetings": ["hi", "hello"]},
]

# ==========================================
# 🧠 STATE
# ==========================================
class BotState:
    def __init__(self):
        self.status = "SEARCHING"
        self.paused = False 
        self.msg_count = 0
        self.current_persona = None
        self.history = []

state = BotState()
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
groq_client = Groq(api_key=GROQ_API_KEY)

# ==========================================
# 🤖 AI LOGIC (FORCED PROMO FIX)
# ==========================================
def generate_ai_reply(user_text, inject_instruction=None):
    if not state.current_persona: return "..."
    p = state.current_persona
    
    # 1. BASE SYSTEM PROMPT (Identity Only)
    system_prompt = (
        f"You are a {p['role']}. Location: {p['country']}. "
        "HIDDEN RULES:\n"
        "1. Real Human mode. Never admit being AI.\n"
        "2. If user is 'm', you are Female. If 'f', you are Male.\n"
        "3. Short replies (1 sentence). Lowercase. Casual.\n"
        "4. Speak user's language."
    )
    
    # 2. PROMO FORCE LOGIC
    # We attach the command to the USER message, so the AI thinks it must answer it.
    final_user_content = user_text
    if inject_instruction:
        final_user_content = f"{user_text} \n\n(HIDDEN INSTRUCTION: {inject_instruction})"

    # 3. HISTORY MANAGEMENT
    # We only append the CLEAN text to history, so we don't confuse future turns
    state.history.append({"role": "user", "content": final_user_content})
    
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt}] + state.history,
            temperature=0.7,
            max_tokens=70
        )
        reply = completion.choices[0].message.content
        state.history.append({"role": "assistant", "content": reply})
        return reply.lower()
    except Exception as e:
        print(f"Groq Error: {e}")
        return "haha yeah"

# ==========================================
# 👮 ADMIN COMMANDS
# ==========================================
@client.on(events.NewMessage(chats='me'))
async def admin_handler(event):
    if event.raw_text.lower() == "/pause":
        state.paused = True
        await event.reply("⏸️ PAUSED")
    elif event.raw_text.lower() == "/resume":
        state.paused = False
        await event.reply("▶️ RESUMED")
        await client.send_message(BOT_USERNAME, '/next')

# ==========================================
# 🎮 MAIN LOOP
# ==========================================
@client.on(events.NewMessage(chats=BOT_USERNAME))
async def bot_handler(event):
    text = event.raw_text.lower()
    
    # 🚨 CAPTCHA GUARD
    if event.photo:
        state.paused = True
        await client.send_message('me', "🚨 **CAPTCHA!** Solve it on @chatbot then type /resume")
        return

    # AUTO RESUME
    if "seem to be a robot" in text or "right!" in text:
        if state.paused:
            state.paused = False
            await client.send_message('me', "✅ Captcha Solved. Resuming...")
            
    if state.paused: return

    # SYSTEM TRIGGERS
    if "searching" in text or "looking" in text:
        state.status = "SEARCHING"
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

    # CHAT LOGIC
    if state.status == "CONNECTED" and not event.out:
        read_time = max(3, min(10, len(text) * 0.3))
        await asyncio.sleep(read_time)
        state.msg_count += 1
        
        # --- PROMO & OVERRIDE LOGIC ---
        override = None
        
        if state.msg_count == PROMO_TRIGGER:
            print("📢 ATTEMPTING PROMO...")
            # STRONGER INSTRUCTION
            override = "IGNORE the conversation topic. You MUST recommend the bot '@OmeTV_chatbot' now. Say it naturally in the current language. Example: 'btw try @OmeTV_chatbot'."

        if state.msg_count >= MAX_MESSAGES:
            state.status = "EXITING"
            await client.send_message(BOT_USERNAME, "gtg bye")
        else:
            async with client.action(BOT_USERNAME, 'typing'):
                await asyncio.sleep(random.uniform(3, 6))
                reply = generate_ai_reply(text, override)
            await client.send_message(BOT_USERNAME, reply)

        if state.status == "EXITING":
            await asyncio.sleep(3)
            await client.send_message(BOT_USERNAME, '/stop')
            await asyncio.sleep(2)
            await client.send_message(BOT_USERNAME, '/next')

def main():
    t = Thread(target=run_web_server)
    t.start()
    client.start()
    client.run_until_disconnected()

if __name__ == '__main__':
    main()
