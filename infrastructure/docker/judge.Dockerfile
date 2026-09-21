# SahuJudge worker (Celery). Build context is the repository root:
#   docker build -f infrastructure/docker/judge.Dockerfile -t sahucodex-judge .
#
# The worker holds the Docker *CLI* only (a static binary, no daemon) and talks to a DEDICATED sandbox daemon named by
# SANDBOX_DOCKER_HOST. It never mounts the host's Docker socket. User code runs in the sandbox containers that daemon
# creates, never in this container. See docs/judge.md.

FROM docker:27-cli AS docker-cli

FROM python:3.12-slim AS deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
# The worker shares the API's dependencies (it imports its models and settings) and adds none of its own.
COPY apps/api/requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PYTHONPATH=/srv/apps/api:/srv/apps/judge
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin judge
WORKDIR /srv/apps/judge

COPY --from=deps /install /usr/local
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY apps/api/app /srv/apps/api/app
COPY apps/judge/sahujudge ./sahujudge
# The build context for the runner image the worker builds into the sandbox daemon on start.
COPY infrastructure/docker/runner/Dockerfile /srv/infrastructure/docker/runner/Dockerfile
COPY apps/judge/sahujudge/supervisor.py /srv/infrastructure/docker/runner/supervisor.py

USER judge
ENV SANDBOX_BUILD_CONTEXT=/srv/infrastructure/docker/runner
# `-B` runs the periodic reaper; start exactly one worker container with it.
CMD ["celery", "-A", "sahujudge.celery_app", "worker", "-Q", "judge", "--concurrency", "2", "-B", \
     "--schedule", "/tmp/celerybeat-schedule", "--loglevel", "INFO"]
