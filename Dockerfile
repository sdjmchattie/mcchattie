FROM python:3.12-slim

# Install UV
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy only pyproject.toml and lock file for faster rebuilds
COPY pyproject.toml .
COPY uv.lock .

# Install dependencies using UV
RUN uv sync

# Copy the Chainlit app
COPY .chainlit ./.chainlit
COPY chainlit.md .
COPY app.py .

# Expose Chainlit port
EXPOSE 8000

# Default command
CMD ["uv", "run", "chainlit", "run", "app.py", "--headless", "--host", "0.0.0.0", "--port", "8000"]
