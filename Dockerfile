# ── Build stage ────────────────────────────────────────────────────────────
FROM python:3.12-alpine AS builder

# Install only the compile-time deps needed to build C extensions
RUN apk add --no-cache \
    gcc musl-dev libffi-dev libxml2-dev libxslt-dev libressl-dev

WORKDIR /app

# Install deps into an isolated prefix so we can copy them cleanly
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ──────────────────────────────────────────────────────────
FROM python:3.12-alpine AS runtime

# Only runtime shared libraries (no compilers, no headers)
RUN apk add --no-cache libxml2 libxslt libressl

WORKDIR /app

# Pull in only the installed packages from the build stage
COPY --from=builder /install /usr/local

# Copy source last so code changes don't bust the package cache layer
COPY . .

CMD ["python", "myinstantsbot.py"]
