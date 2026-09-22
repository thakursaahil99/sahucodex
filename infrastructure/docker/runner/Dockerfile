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
# Go: the official toolchain, copied from the official image.
COPY --from=golang:1.23-bookworm /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:${PATH}"
# .NET SDK: the official image's install, copied in (its own base is not Debian-slim-compatible to install from apt).
COPY --from=mcr.microsoft.com/dotnet/sdk:10.0-bookworm-slim /usr/share/dotnet /usr/share/dotnet
ENV PATH="/usr/share/dotnet:${PATH}" DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends g++ gcc libc6-dev default-jdk-headless php-cli curl ca-certificates \
 # Rust: rustup's installer script, run non-interactively, pinned to stable; removed once installed.
 && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal \
 && mv /root/.cargo/bin/rustc /usr/local/bin/rustc && mv /root/.cargo/bin/* /usr/local/bin/ 2>/dev/null || true \
 && rm -rf /root/.cargo /root/.rustup /var/lib/apt/lists/* \
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

# TypeScript needs no separate toolchain: Node's own `--experimental-strip-types` (stable since Node 22, see the
# `typescript` LanguageSpec) erases type syntax and runs the result directly.

# An empty console project for C#: `dotnet build` needs a .csproj; this lets it build a lone Program.cs offline
# (`--no-restore`, so no network call in the sandbox). Warmed once so the first real submission doesn't pay for it.
RUN mkdir -p /work \
 && printf '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n    <OutputType>Exe</OutputType>\n    <TargetFramework>net10.0</TargetFramework>\n    <AssemblyName>sjx</AssemblyName>\n    <Nullable>enable</Nullable>\n    <InvariantGlobalization>true</InvariantGlobalization>\n  </PropertyGroup>\n</Project>\n' > /work/sjx.csproj \
 && echo 'class Program { static void Main() {} }' > /work/Program.cs \
 && dotnet build -c Release /work/sjx.csproj -o /tmp/sjx-warm \
 && rm -rf /work/Program.cs /work/obj /work/bin /tmp/sjx-warm \
 && chown -R 10001:10001 /work && chmod 0755 /work/sjx.csproj

ENV PYTHONDONTWRITEBYTECODE=1 \
    SJX_SANDBOX=1 \
    LANG=C.UTF-8
USER 10002:10002
WORKDIR /work
