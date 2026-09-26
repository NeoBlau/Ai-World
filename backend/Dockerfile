# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=true
# Optional build secret "extra_ca": a CA bundle for builds behind a TLS-inspecting proxy.
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install -r requirements.txt && if [ "$INSTALL_DEV" = "true" ]; then pip install -r requirements-dev.txt; fi

COPY . .

# Agents and the API never run as root.
RUN useradd --create-home --uid 10001 aiworld && chown -R aiworld /app
USER aiworld

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
