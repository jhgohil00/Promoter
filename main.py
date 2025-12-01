import asyncio
import random
import os
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from groq import Groq
from aiohttp import web 

# ==========================================
# 🔧 CONFIGURATION SECTION
# ==========================================
API_ID = int(os.environ.get("API_ID", 28723682))
API_HASH = os.environ.get("API_HASH", "868a078ba0208b4409208275fa8bc598")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
STRING_SESSION = os.environ.get("STRING_SESSION", "") 

BOT_USERNAME = 'chatbot' 
MAX_MESSAGES = 10           
PROMO_TRIGGER = 6           

# ==========================================
# 🎭 PERSONA DATABASE
# ==========================================
PERSONAS = [
    {
        "id": "indo_girl",
        "country": "Indonesia",
        "role": "Female, 19, Jakarta slang style. Shy but curious.",
        "greetings": ["hai", "halo", "iya?"],
    },
    {
        "id": "malay_girl",
        "country": "Malaysia",
        "role": "Female, 21, KL style. Mix Malay/English. Polite.",
        "greetings": ["hi", "hello", "hey you"],
    },
    {
        "id": "indian_girl",
        "country": "India",
        "role": "Female, 22, Mumbai. Hinglish + English. Practical.",
        "greetings": ["hi", "hello", "hey"],
    },
    {
        "id": "uk_girl",
        "country": "UK",
        "role": "Female, 17, London. Student. Bored/Tired.",
        "greetings": ["hi", "hello"],
    }
]

# ==========================================
# 🧠 STATE MANAGEMENT
# ==========================================
class BotState:
    def __init__(self):
        self.status = "SEARCHING"
        self.msg_count = 0
        self.current_persona = None
        self.history = []
        self.is_paused = False

state = BotState()

# Initialize Client
if not STRING_SESSION:
    print("❌ ERROR: String Session is missing in Environment Variables!")
else:
    client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

groq_client = Groq(api_key=GROQ_API_KEY)

# ==========================================
# 🤖 AI GENERATION LOGIC
# ==========================================
def generate_ai_reply(user_text, inject_instruction=None):
    p = state.current_persona
    system_prompt = (
        f"You are a {p['role']}. You are chatting on an anonymous app. "
        f"Your location is {p['country']}. "
        "IMPORTANT RULES:\n"
        "- If user is Male, act Female. If User is Female, act Male.\n"
        "- Keep replies SHORT (1 sentence max).\n"
        "- Use lowercase mostly. Minimal emojis.\n"
        "- Do NOT be overly enthusiastic. Be 'Real'.\n"
        "- If asked where you are from FIRST, say 'UK'. Otherwise use your real country.\n"
        "- If user speaks Indo/Malay, speak that language. If English, speak English."
    )

    if inject_instruction:
        # We emphasize the instruction to ensure it doesn't accidentally add an '@'
        system_prompt += f"\n\n[URGENT INSTRUCTION]: {inject_instruction}"

    state.history.append({"role": "user", "content": user_text})

    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt}] + state.history,
            temperature=0.7,
            max_tokens=80 # Increased slightly for the specific promo text
        )
        reply = completion.choices[0].message.content
        state.history.append({"role": "assistant", "content": reply})
        return reply.lower() 
    except Exception as e:
        print(f"❌ Groq Error: {e}")
        return "haha yeah" 

# ==========================================
# 👂 THE LISTENER (EVENT HANDLER)
# ==========================================
@client.on(events.NewMessage)
async def handler(event):
    text = event.raw_text.lower()
    sender_id = event.sender_id
    me = await client.get_me()

    # 🛡️ SUPERVISOR LAYER: ADMIN COMMANDS
    if event.is_private and sender_id == me.id:
        if text == "/pause":
            state.is_paused = True
            await event.reply("⏸️ PAUSED. I will stop replying to strangers.")
            print("--- PAUSED BY ADMIN ---")
            return
        elif text == "/resume":
            state.is_paused = False
            await event.reply("▶️ RESUMED. Back to work.")
            print("--- RESUMED BY ADMIN ---")
            return
        elif text == "/status":
            status_msg = f"Status: {state.status}\nPaused: {state.is_paused}\nMsgs: {state.msg_count}"
            await event.reply(status_msg)
            return

    if event.chat and getattr(event.chat, 'username', '') != BOT_USERNAME:
        return

    # 🛡️ SUPERVISOR LAYER: CAPTCHA DETECTION
    if event.photo and not event.out:
        state.is_paused = True
        print("🚨 CAPTCHA DETECTED! Pausing...")
        await client.send_message('me', "⚠️ CAPTCHA DETECTED! \n1. Go to @chatbot\n2. Solve the puzzle manually.\n3. I will auto-resume when I see 'Partner found'.")
        return

    # --- SYSTEM MESSAGES ---
    if "searching" in text or "looking" in text:
        state.status = "SEARCHING"
        return

    if "partner found" in text or "connected" in text:
        if state.is_paused:
            state.is_paused = False
            await client.send_message('me', "✅ Captcha Solved / Partner Found. Auto-Resuming!")
        
        state.status = "CONNECTED"
        state.msg_count = 0
        state.history = []
        state.current_persona = random.choice(PERSONAS)
        
        print(f"✅ Connected! Selected: {state.current_persona['id']}")
        await asyncio.sleep(5) 
        
        if not state.is_paused:
            greeting = random.choice(state.current_persona['greetings'])
            await client.send_message(BOT_USERNAME, greeting)
            state.msg_count += 1
        return

    if "partner disconnected" in text or "stopped" in text:
        state.status = "SEARCHING"
        await asyncio.sleep(2)
        if not state.is_paused:
            await client.send_message(BOT_USERNAME, '/next')
        return

    if state.is_paused:
        return

    # --- STRANGER MESSAGES ---
    if state.status == "CONNECTED" and not event.out:
        read_time = len(text) * 0.3
        if read_time < 3: read_time = 3
        if read_time > 10: read_time = 10 
        await asyncio.sleep(read_time)

        state.msg_count += 1
        
        # --- PROMO LOGIC (STEALTH MODE) ---
        override_instruction = None
        if state.msg_count == PROMO_TRIGGER:
            
            # 🎲 1. Randomize the "Obfuscated Name"
            # We break the words so the system doesn't see "chatbot" or "ometv"
            stealth_names = [
                "OmeTV chatb o t", 
                "Ome TV cha t bo t", 
                "Ome-TV b o t",
                "Ometv:chat with strangers", 
                "Ome_TV b0t",
                "Ome TV new b ot"
            ]
            chosen_name = random.choice(stealth_names)
            
            # 📝 2. Randomize the "Instruction Style"
            prompts = [
                f"Tell them to search for '{chosen_name}' on telegram (with spaces).",
                f"Say u found a better bot called '{chosen_name}'.",
                f"Ask if they have tried '{chosen_name}' yet.",
                f"Tell them this bot is dead and to go to '{chosen_name}'."
            ]
            selected_prompt = random.choice(prompts)
            
            override_instruction = (
                f"IGNORE previous topic. {selected_prompt} "
                "IMPORTANT: Do NOT use the '@' symbol. "
                "Write the bot name EXACTLY as I showed you with the spaces. "
                "Keep it short and lowercase."
            )
            print(f"📢 Triggering Safe Promo: {chosen_name}")

        if state.msg_count >= MAX_MESSAGES:
            reply = "gtg bye" 
            state.status = "EXITING"
            await client.send_message(BOT_USERNAME, reply)
        else:
            async with client.action(BOT_USERNAME, 'typing'):
                typing_delay = random.uniform(3, 6)
                await asyncio.sleep(typing_delay)
                reply = generate_ai_reply(text, inject_instruction=override_instruction)
            await client.send_message(BOT_USERNAME, reply)

        if state.status == "EXITING":
            await asyncio.sleep(3)
            await client.send_message(BOT_USERNAME, '/stop')
            await asyncio.sleep(2)
            await client.send_message(BOT_USERNAME, '/next')

# ==========================================
# 🌐 DUMMY WEB SERVER (Keep-Alive)
# ==========================================
async def web_handler(request):
    return web.Response(text="I am alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', web_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    print("🌍 Web Server running on port 10000")

# ==========================================
# 🚀 MAIN STARTER
# ==========================================
async def main():
    print("--- 🟢 Smart Agent v4 (Stealth Edition) Started ---")
    await start_web_server()
    await client.start()
    await client.send_message('me', "🚀 Bot v4 (Stealth Mode) is Online!")
    await client.send_message(BOT_USERNAME, '/start')
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
