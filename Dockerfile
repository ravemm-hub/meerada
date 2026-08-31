# Meerada LLManager — hosted cockpit (FastAPI). Free-tier friendly.
FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
# [hosted] pulls in cryptography so the per-user key vault is encrypted at rest.
RUN pip install --no-cache-dir ".[hosted]"

ENV PORT=8000
EXPOSE 8000

# build_app() reads OAuth config from the environment; with it set, Google
# sign-in is enforced and every user brings their own model keys.
CMD ["sh", "-c", "python -m uvicorn --factory handover.copilot.serve:build_app --host 0.0.0.0 --port ${PORT}"]
