# Runner Prosimos di DeliR. Build dalla cartella ops/prosimos:
#   docker build -f runner/Dockerfile -t delir-prosimos-runner .
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RUNNER_DATA_DIR=/data \
    GUNICORN_WORKERS=6 \
    GUNICORN_TIMEOUT=1800

WORKDIR /app
COPY runner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY runner/runner.py .
RUN useradd --system --uid 10001 runner && mkdir -p /data && chown runner /data
USER runner

EXPOSE 5000
# Worker sync: un run per processo, cosi' il seed globale non si mescola fra run.
# `exec`: gunicorn diventa il PID 1 e riceve SIGTERM, cosi' `docker stop` non aspetta il kill.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:5000 --workers \"$GUNICORN_WORKERS\" --timeout \"$GUNICORN_TIMEOUT\" --access-logfile - runner:app"]
