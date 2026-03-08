import base64
import os

import chainlit as cl
from openai import OpenAI


client = OpenAI()

MODEL = os.getenv("OPENAI_MODEL")
if not MODEL:
    raise RuntimeError("OPENAI_MODEL environment variable is not set")

SYSTEM_PROMPT = "Your name is McChattie. You are a helpful assistant."


def build_user_content(message: cl.Message):
    image_elements = [e for e in message.elements if e.mime and e.mime.startswith("image/")]
    if not image_elements:
        return message.content
    content = [{"type": "text", "text": message.content}]
    for el in image_elements:
        with open(el.path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{el.mime};base64,{b64}"}
        })
    return content


async def start():
    cl.user_session.set("message_history", [{"role": "system", "content": SYSTEM_PROMPT}])
    await cl.Message(content="Hi! How can I help you today?").send()


async def on_chat_resume(thread):
    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    for step in thread.get("steps", []):
        if step["type"] == "user_message":
            history.append({"role": "user", "content": step["output"]})
        elif step["type"] == "assistant_message":
            history.append({"role": "assistant", "content": step["output"]})
    cl.user_session.set("message_history", history)


async def handle_message(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])
    message_history.append({"role": "user", "content": build_user_content(message)})

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


def register():
    cl.on_chat_start(start)
    cl.on_chat_resume(on_chat_resume)
    cl.on_message(handle_message)
