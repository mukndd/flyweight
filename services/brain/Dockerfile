# Flyweight brain service (services/brain).
#
# Build context must be the repository root. Build with:
#   docker build -f services/brain/Dockerfile -t flyweight-brain .
#
# Runtime env (validated at startup by services/brain/config.py; invalid or
# missing production values fail closed rather than defaulting permissively):
#   FLYWEIGHT_ENV              "development" (default) or "production"
#   PORT                       listen port (default 8000)
#   FLYWEIGHT_BIND_HOST        127.0.0.1 (default); production may use 0.0.0.0
#   FLYWEIGHT_PUBLIC_ORIGINS   comma-separated exact allowed origins
#                               (must be HTTPS in production)
#   FLYWEIGHT_ALLOWED_HOSTS    comma-separated exact allowed Host headers
#   FLYWEIGHT_DATA_DIR         processed-connectome directory; must resolve
#                               inside the image or under a mounted /data
#                               volume — mount your prepared processed graph
#                               there for production, the image does not
#                               bundle the connectome dataset
#
# In production mode, the service refuses to start without a prepared and
# validated processed graph already present at FLYWEIGHT_DATA_DIR (no
# silent synthetic fallback in production) — mount it as a read-only volume.

FROM python:3.12-slim AS build
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --prefix=/install --require-hashes -r requirements.lock

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN useradd --create-home --uid 10001 flyweight
ENV PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    PATH=/install/bin:$PATH \
    PYTHONPATH=/install/lib/python3.12/site-packages
COPY --from=build /install /install
COPY services ./services
COPY scripts/serve_brain.py ./scripts/serve_brain.py
COPY scripts/__init__.py ./scripts/__init__.py
RUN mkdir -p data/processed checkpoints logs .runtime \
    && chown -R flyweight:flyweight /app
USER flyweight
EXPOSE 8000
CMD ["python", "-m", "scripts.serve_brain"]
