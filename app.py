from db import run_migrations
from auth import register as register_auth
from chat import register as register_chat

run_migrations()
register_auth()
register_chat()
