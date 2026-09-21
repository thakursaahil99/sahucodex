from __future__ import annotations

import os
import shutil
import sys

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    docker_ready = os.environ.get("SJX_DOCKER_TESTS") == "1" and shutil.which("docker") is not None
    for item in items:
        if "docker" in item.keywords and not docker_ready:
            item.add_marker(
                pytest.mark.skip(reason="needs a Docker daemon: set SJX_DOCKER_TESTS=1 (see docs/judge.md#testing)")
            )
        if "linux" in item.keywords and not sys.platform.startswith("linux"):
            item.add_marker(pytest.mark.skip(reason="the in-container supervisor is Linux-only (/proc, wait4)"))
