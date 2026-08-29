from app.config import ScriptConfig
from app.conversation import ConversationEngine

script = ScriptConfig(
    greeting="Hi, this is Alex calling on a recorded line. How are you today?",
    pitch=(
        "I'm calling because you qualify for some free Medicare benefits "
        "with your current Medicare plan."
    ),
    qualifying_questions=[
        "Do you have Medicare Part A and Part B?",
        "How old are you?",
        "Do you make your own decisions?",
    ],
    transfer_line=(
        "Perfect — let me connect you with a licensed specialist right now, one moment."
    ),
)
e = ConversationEngine(script=script)
steps = [
    "I am fine.",
    "Yes. Yes, I have.",
    "I am 62.",
    "Yes, I make.",
    "Yes, I make.",
    "Yes, I make my own decisions.",
    "Are you there?",
    "Yes, I do.",
]
t = e.open()
print(f"BOT[{e.state}]: {t.reply}")
for text in steps:
    print(f"CALLER: {text}")
    t = e.handle(text)
    fu = e.take_pending_followup()
    print(f"BOT[{e.state}/{t.action}]: {t.reply}")
    if fu:
        print(f"  followup: {fu}")
