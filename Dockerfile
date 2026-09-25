FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY blizzbot ./blizzbot
COPY verify_namespace.py .

CMD ["python3", "-m", "blizzbot.run_bot"]
