# SahuCodeX API (FastAPI). Build context is the repository root:
#   docker build -f infrastructure/docker/api.Dockerfile -t sahucodex-api .
#
# The image mirrors the repo layout (/srv/apps/api + /srv/database) so Alembic's relative
# script_location and the seed script's path logic work identically in and out of Docker.

FROM python:3.12-slim AS deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY apps/api/requirements.txt .
# All dependencies ship manylinux wheels, so no compiler is needed in the image.
RUN pip install --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /srv/apps/api

COPY --from=deps /install /usr/local
COPY apps/api/app ./app
COPY apps/api/alembic.ini ./alembic.ini
COPY database /srv/database
COPY infrastructure/docker/api-entrypoint.sh /usr/local/bin/api-entrypoint
# Guard against CRLF endings from a Windows checkout, which would break the shebang.
RUN sed -i 's/\r$//' /usr/local/bin/api-entrypoint && chmod 0755 /usr/local/bin/api-entrypoint

USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=4s --start-period=30s --retries=5 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

ENTRYPOINT ["api-entrypoint"]
CMD ["uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
