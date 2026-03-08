# McChattie

A Chainlit-based chat interface for the OpenAI API, with password authentication, PostgreSQL thread persistence, and S3 file storage.

## Tech Stack

- **Python 3.12** managed with **uv**
- **Chainlit** – UI framework and session/thread management
- **OpenAI** – LLM backend (configurable model via `OPENAI_MODEL`)
- **PostgreSQL** – thread/chat history persistence
- **S3 (LocalStack locally)** – file storage

## Project Structure

- `app.py` – main application (auth, chat start/resume, message handling, startup DB migration)
- `public/` – static files served by Chainlit; `logo_light.png` and `logo_dark.png` are auto-detected as the app logo
- `pyproject.toml` / `uv.lock` – dependency management
- `.chainlit/config.toml` – Chainlit UI and feature configuration
- `chainlit.md` – welcome screen content
- `docker-compose.yaml` – local dev environment (postgres, localstack, app)
- `localstack-script.sh` – creates and configures the S3 bucket on localstack startup
- `Dockerfile` – production container image
- `.env.example` – template for required environment variables
- `users.json.example` – template for user credentials file

## Setup

### Local development (without Docker)

```bash
cp .env.example .env          # fill in OPENAI_API_KEY and other vars
cp users.json.example users.json   # add user credentials
uv sync
uv run chainlit run app.py
```

Requires a running PostgreSQL and (optionally) S3-compatible service — use Docker Compose for these:

```bash
docker compose up db localstack
```

### Full Docker deployment

```bash
cp .env.example .env
cp users.json.example users.json
docker compose up
```

App runs on port **8000**.

## Environment Variables

See `.env.example` for all variables. Key ones:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | Model name (e.g. `gpt-4.1-mini`) |
| `CHAINLIT_AUTH_SECRET` | Secret for signing auth tokens |
| `USERS_FILE` | Path to the users JSON file (default: `users.json`) |
| `DATABASE_URL` | PostgreSQL connection string |
| `BUCKET_NAME` | S3 bucket name |
| `APP_AWS_ACCESS_KEY` / `APP_AWS_SECRET_KEY` / `APP_AWS_REGION` | AWS/LocalStack credentials |
| `DEV_AWS_ENDPOINT` | Override S3 endpoint (e.g. `http://localhost:4566` for LocalStack) |

## Authentication

Users are defined in `users.json` (gitignored). Copy `users.json.example` and add entries:

```json
{
  "user@example.com": {
    "user_name": "Display Name",
    "password": "plaintext-password"
  }
}
```

## Dependencies

Managed with `uv`. To add a package:

```bash
uv add <package>
```

To upgrade all packages to the latest versions satisfying `pyproject.toml` constraints:

```bash
uv lock --upgrade
uv sync
```

To upgrade a single package:

```bash
uv lock --upgrade-package <package>
uv sync
```

After upgrading, update the minimum version floors in `pyproject.toml` to match the new resolved versions, then commit both files.

## Database Migrations

`app.py` runs a lightweight startup migration on every launch (currently: setting a default on `Thread.metadata` to fix a Chainlit 2.6.5 → 2.10.0 schema incompatibility). This pattern is only safe for catalogue-only changes (e.g. `SET DEFAULT`) that complete instantly regardless of table size. Migrations that scan or rewrite the table must be run manually as a separate step before deploying.
