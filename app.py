import asyncio
import json
import os
import asyncpg
import chainlit as cl
from openai import OpenAI


# Initialise your OpenAI client
client = OpenAI()

# One-off migration: fix Thread.metadata NOT NULL constraint after Chainlit 2.6.5 -> 2.10.0 upgrade.
# NOTE: This approach (idempotent ALTER TABLE at startup) is only suitable for catalogue-only
# changes that complete instantly regardless of table size (e.g. SET DEFAULT, SET/DROP NOT NULL
# via a pre-validated constraint). Any migration that scans or rewrites the table should be run
# manually as a separate step, not at app startup.
async def _migrate():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return
    try:
        conn = await asyncpg.connect(database_url)
        try:
            await conn.execute(
                'ALTER TABLE "Thread" ALTER COLUMN metadata SET DEFAULT \'{}\'::jsonb'
            )
            await conn.execute(
                'UPDATE "Thread" SET metadata = \'{}\' WHERE metadata IS NULL'
            )
        finally:
            await conn.close()
    except Exception as e:
        print(f"Warning: DB migration failed: {e}")

asyncio.run(_migrate())

# Get environment variables
MODEL = os.getenv("OPENAI_MODEL")
USERS_FILE = os.getenv("USERS_FILE")

if not MODEL:
    raise RuntimeError("OPENAI_MODEL environment variable is not set")
if not USERS_FILE:
    raise RuntimeError("USERS_FILE environment variable is not set")

try:
    with open(USERS_FILE) as f:
        USERS = json.load(f)
except FileNotFoundError:
    raise RuntimeError(f"Users file not found: {USERS_FILE}")

# System prompt controlling the assistant's role/behaviour
SYSTEM_PROMPT = "Your name is McChattie. You are a helpful assistant."

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
    cl.user_session.set("message_history", [{"role": "system", "content": SYSTEM_PROMPT}])
    await cl.Message(content="Hi! How can I help you today?").send()


@cl.on_chat_resume
async def on_chat_resume(thread):
    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    for step in thread.get("steps", []):
        if step["type"] == "user_message":
            history.append({"role": "user", "content": step["output"]})
        elif step["type"] == "assistant_message":
            history.append({"role": "assistant", "content": step["output"]})
    cl.user_session.set("message_history", history)


@cl.on_message
async def handle_message(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])
    message_history.append({"role": "user", "content": message.content})

    msg = await cl.Message(content="").send()

    try:
        stream = client.chat.completions.create(
            model=MODEL,
            messages=message_history,
            stream=True,
        )

        for part in stream:
            if token := part.choices[0].delta.content or "":
                await msg.stream_token(token)

    except Exception as e:
        await msg.update(content=f"Sorry, something went wrong: {e}")
        return

    message_history.append({"role": "assistant", "content": msg.content})
    cl.user_session.set("message_history", message_history)

    await msg.update()
