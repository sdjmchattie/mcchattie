import json
import os

import chainlit as cl


def _load_users():
    users_file = os.getenv("USERS_FILE")
    if not users_file:
        raise RuntimeError("USERS_FILE environment variable is not set")
    try:
        with open(users_file) as f:
            return json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"Users file not found: {users_file}")


USERS = _load_users()


async def login(email: str, password: str) -> bool:
    if (metadata := USERS.get(email)) and metadata["password"] == password:
        return cl.User(
            identifier=metadata["user_name"], metadata={"role": "admin", "provider": "credentials"}
        )

    return None


def register():
    cl.password_auth_callback(login)
