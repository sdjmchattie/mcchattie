import base64
import json
import mimetypes
import os
import uuid

import boto3
import chainlit as cl
from openai import OpenAI


client = OpenAI()

MODEL = os.getenv("OPENAI_MODEL")
if not MODEL:
    raise RuntimeError("OPENAI_MODEL environment variable is not set")

SYSTEM_PROMPT = "Your name is McChattie. You are a helpful assistant."

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a file and attach it to the chat for the user to download",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "The filename including extension"
                    },
                    "content": {
                        "type": "string",
                        "description": "The file content"
                    }
                },
                "required": ["filename", "content"]
            }
        }
    }
]


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


def _s3_client():
    kwargs = {
        "aws_access_key_id": os.getenv("APP_AWS_ACCESS_KEY"),
        "aws_secret_access_key": os.getenv("APP_AWS_SECRET_KEY"),
        "region_name": os.getenv("APP_AWS_REGION"),
    }
    endpoint = os.getenv("DEV_AWS_ENDPOINT")
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("s3", **kwargs)


def _s3_public_url(key: str) -> str:
    bucket = os.getenv("BUCKET_NAME", "")
    base = os.getenv("PUBLIC_S3_ENDPOINT") or os.getenv("DEV_AWS_ENDPOINT")
    if base:
        return f"{base}/{bucket}/{key}"
    region = os.getenv("APP_AWS_REGION", "us-east-1")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"


def _upload_user_elements(elements) -> None:
    """Upload user-uploaded files to S3 and set el.url so Chainlit persists the URL."""
    if not elements:
        return
    s3 = _s3_client()
    bucket = os.getenv("BUCKET_NAME", "")
    for el in elements:
        path = getattr(el, "path", None)
        if not path:
            continue
        filename = el.name or os.path.basename(path)
        mime = el.mime or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        key = f"uploads/{uuid.uuid4()}/{filename}"
        with open(path, "rb") as f:
            s3.put_object(Bucket=bucket, Key=key, Body=f.read(), ContentType=mime)
        el.url = _s3_public_url(key)


def _execute_tool(name: str, arguments_json: str, file_elements: list) -> str:
    try:
        args = json.loads(arguments_json)
    except json.JSONDecodeError:
        return "Error: invalid arguments"

    if name == "create_file":
        filename = args.get("filename", "file.txt")
        content = args.get("content", "")
        key = f"attachments/{uuid.uuid4()}/{filename}"
        mime, _ = mimetypes.guess_type(filename)
        _s3_client().put_object(
            Bucket=os.getenv("BUCKET_NAME", ""),
            Key=key,
            Body=content.encode("utf-8"),
            ContentType=mime or "application/octet-stream",
        )
        url = _s3_public_url(key)
        file_elements.append(cl.File(name=filename, url=url, mime=mime or "application/octet-stream"))
        return f"File '{filename}' created and attached to the chat."

    return f"Unknown tool: {name}"


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
    _upload_user_elements(message.elements)
    message_history = cl.user_session.get("message_history", [])
    message_history.append({"role": "user", "content": build_user_content(message)})

    msg = await cl.Message(content="").send()
    file_elements = []

    try:
        while True:
            stream = client.chat.completions.create(
                model=MODEL,
                messages=message_history,
                tools=TOOLS,
                stream=True,
            )

            # Accumulate streamed response
            tool_calls_acc = {}  # index -> {id, name, arguments}
            text_content = ""
            finish_reason = None

            for part in stream:
                choice = part.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta

                if delta.content:
                    text_content += delta.content
                    await msg.stream_token(delta.content)

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            tool_calls_acc[idx]["name"] += tc.function.name
                        if tc.function and tc.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc.function.arguments

            # Record assistant turn
            assistant_turn = {"role": "assistant", "content": text_content or None}
            if tool_calls_acc:
                assistant_turn["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]}
                    }
                    for tc in tool_calls_acc.values()
                ]
            message_history.append(assistant_turn)

            if finish_reason != "tool_calls":
                break

            # Execute tool calls and append results
            for tc in tool_calls_acc.values():
                result = _execute_tool(tc["name"], tc["arguments"], file_elements)
                message_history.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

    except Exception as e:
        await msg.update(content=f"Sorry, something went wrong: {e}")
        return

    if file_elements:
        msg.elements = file_elements

    cl.user_session.set("message_history", message_history)
    await msg.update()


def register():
    cl.on_chat_start(start)
    cl.on_chat_resume(on_chat_resume)
    cl.on_message(handle_message)
