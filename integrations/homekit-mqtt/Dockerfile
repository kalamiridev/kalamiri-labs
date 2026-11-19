FROM python:3.14-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOMEKIT_DATA_DIR=/data

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY homekit_mqtt ./homekit_mqtt

RUN useradd --system --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

USER appuser

VOLUME ["/data"]

CMD ["python", "-m", "homekit_mqtt"]
