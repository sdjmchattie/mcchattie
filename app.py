import json
import os
import chainlit as cl
from openai import OpenAI


# Initialise your OpenAI client
client = OpenAI()

# Get environment variables
MODEL = os.getenv("OPENAI_MODEL")
USERS_FILE = os.getenv("USERS_FILE")
with open(USERS_FILE) as f:
    USERS = json.load(f)

# System prompt controlling the assistant's role/behaviour
SYSTEM_PROMPT = "You are a helpful assistant."

# Simple auth flow
@cl.password_auth_callback
async def login(email: str, password: str) -> bool:
    if (metadata := USERS.get(email)) and metadata["password"] == password:
        return cl.User(
            identifier=metadata["user_name"], metadata={"role": "admin", "provider": "credentials"}
        )

    return None


@cl.on_chat_start
async def start():
    cl.user_session.set("message_history", [{"role": "system", "content": SYSTEM_PROMPT}])   # In-memory chat history
    await cl.Message(
        content="Hi! How can I help you today?"
    ).send()


@cl.on_chat_resume
async def on_chat_resume(thread):
    pass


@cl.on_message
async def handle_message(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])
    message_history.append({"role": "user", "content": message.content})

    msg = await cl.Message(content="").send()

    stream = client.chat.completions.create(
        model=MODEL,
        messages=message_history,
        stream=True,
    )

    for part in stream:
        if token := part.choices[0].delta.content or "":
            await msg.stream_token(token)

    message_history.append({"role": "assistant", "content": msg.content})
    cl.user_session.set("message_history", message_history)

    await msg.update()
