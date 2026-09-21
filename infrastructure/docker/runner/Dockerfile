# SahuJudge runner image: the toolchains a sandbox container needs, and nothing else.
#
# Built INTO the sandbox daemon (never the host's): the judge worker does it on start (SANDBOX_AUTO_BUILD) from the
# context the worker image ships, or by hand with ./build.sh. `supervisor.py` is copied in from
# apps/judge/sahujudge/supervisor.py at that point, so there is a single source of truth for it.
#
# Adding a language: install its toolchain here, add a LanguageSpec in apps/judge/sahujudge/languages.py, enable its row in
# `programming_languages`. No judge logic changes.

FROM python:3.12-slim-bookworm

# Node.js: the official binary, copied from the official image (no third-party install scripts).
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node

RUN apt-get update \
 && apt-get install -y --no-install-recommends g++ libc6-dev \
 && rm -rf /var/lib/apt/lists/* \
 # Two unprivileged accounts: 10001 runs submitted code and owns /work; 10002 is the container's main process, so
 # submitted code cannot signal, ptrace or read the memory of it.
 && groupadd --gid 10001 sandbox && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin sandbox \
 && groupadd --gid 10002 sandbox-init && useradd --uid 10002 --gid 10002 --no-create-home --shell /usr/sbin/nologin sandbox-init \
 && mkdir -p /opt/sjx /work \
 # No setuid/setgid binary survives: nothing in a sandbox may escalate.
 && find / -xdev -perm /6000 -type f -exec chmod a-s {} + 2>/dev/null || true

# Root-owned and read-only at run time: submitted code cannot alter the supervisor.
COPY supervisor.py /opt/sjx/supervisor.py
RUN chmod 0644 /opt/sjx/supervisor.py && chmod 0755 /opt/sjx

ENV PYTHONDONTWRITEBYTECODE=1 \
    SJX_SANDBOX=1 \
    LANG=C.UTF-8
USER 10002:10002
WORKDIR /work
