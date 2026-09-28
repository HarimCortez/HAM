"""FIX-E N2 regression: `render.yaml`'s `ham-worker` service used to be missing several env
vars `config.settings.prod` fails fast on at boot (`HAM_TOKEN_HMAC_KEYS`,
`HAM_OBJECT_STORE_BACKEND`, the `HAM_S3_*` keys, `DJANGO_ALLOWED_HOSTS`) -- the worker would
never have booted in production. This is an independent oracle, not a hand-maintained copy of
"the list": it actually imports `config.settings.prod` in a subprocess with *only* the env
vars `render.yaml` declares for one service (resolving `fromDatabase`/`fromService`
references, since those don't carry a literal value in the blueprint itself), with dummy
values that satisfy every format constraint (valid Fernet key, non-localhost URL, etc.) --
if a future `prod.py` check needs an env var no service actually sets, this fails without
anyone having to update a parallel list here. New file per wave brief.

No PyYAML dependency: `render.yaml`'s structure is simple and stable enough for a small,
purpose-built line parser (`_parse_services`) rather than adding a new project dependency for
one test file (CLAUDE.md: new deps need a pyproject.toml entry + CI install).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RENDER_YAML = REPO_ROOT / "render.yaml"

_SERVICE_START = re.compile(r"^  - type: \w+$")
_SERVICE_NAME = re.compile(r"^    name: (\S+)$")
_TOP_LEVEL_FIELD = re.compile(r"^    \S")  # 4-space indent: a field of the service itself
_ENVVAR_KEY = re.compile(r"^      - key: (\S+)$")
_ENVVAR_FROM_SERVICE_START = re.compile(r"^      - fromService:$")
_FROM_SERVICE_ENVVARKEY = re.compile(r"^          envVarKey: (\S+)$")


def _parse_services(text: str) -> dict[str, set[str]]:
    """``{service_name: {every env var key the running container will have}}`` -- resolves a
    bare ``fromService:`` entry (no sibling ``key:``) to its own ``envVarKey`` name, same as
    Render does at deploy time."""
    lines = text.splitlines()
    services: dict[str, set[str]] = {}
    current_name: str | None = None
    in_env_vars = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if _SERVICE_START.match(line):
            current_name = None
            in_env_vars = False
            services_started = True  # noqa: F841 - readability marker only
        elif current_name is None and (m := _SERVICE_NAME.match(line)):
            current_name = m.group(1)
            services[current_name] = set()
        elif current_name is not None:
            if line.strip() == "envVars:":
                in_env_vars = True
            elif in_env_vars and (m := _ENVVAR_KEY.match(line)):
                services[current_name].add(m.group(1))
            elif in_env_vars and _ENVVAR_FROM_SERVICE_START.match(line):
                # Look ahead a few lines for this block's own envVarKey.
                for j in range(i + 1, min(i + 5, len(lines))):
                    if m2 := _FROM_SERVICE_ENVVARKEY.match(lines[j]):
                        services[current_name].add(m2.group(1))
                        break
            elif in_env_vars and _TOP_LEVEL_FIELD.match(line) and not line.startswith("      "):
                # Back out to a 4-space field (e.g. "    buildCommand:") -- envVars ended.
                in_env_vars = False
        i += 1
    return services


def test_parser_finds_both_prod_services():
    services = _parse_services(RENDER_YAML.read_text())
    assert services["ham-web"], "expected at least one env var on ham-web"
    assert services["ham-worker"], "expected at least one env var on ham-worker"


def _dummy_env_for(keys: set[str]) -> dict[str, str]:
    """One valid dummy value per key -- valid enough to satisfy every format constraint
    `config.settings.prod` checks (a Fernet key, a non-localhost URL, etc.), since the point
    of this test is "is the var present at all", not "does this exact secret work"."""
    fixed = {
        "HAM_FIELD_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "HAM_BASE_URL": "https://ham.example.org",
        "DJANGO_ALLOWED_HOSTS": "ham.example.org",
        "HAM_TRUSTED_PROXY_COUNT": "1",
        "HAM_OBJECT_STORE_BACKEND": "ham.integrations.storage.s3.R2ObjectStore",
        "DATABASE_URL": "postgres://u:p@localhost:5432/db",
        "DJANGO_EMAIL_BACKEND": "anymail.backends.resend.EmailBackend",
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        "HAM_ENV": "production",
        "HAM_BRAND": "miami-temple",
    }
    return {key: fixed.get(key, "dummy-value") for key in keys}


def _boot_prod_settings(env_vars: dict[str, str]) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": ".", **env_vars}
    return subprocess.run(
        [sys.executable, "-c", "import config.settings.prod"],
        env=env,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=60,
    )


@pytest.mark.parametrize("service_name", ["ham-web", "ham-worker"])
def test_every_service_running_prod_settings_has_every_var_prod_py_needs(service_name):
    """N2: boots `config.settings.prod` in a subprocess using *only* the env vars
    `render.yaml` actually declares for this service -- a missing required var makes
    `prod.py`'s own fail-fast checks raise, and the subprocess exits non-zero."""
    services = _parse_services(RENDER_YAML.read_text())
    keys = services[service_name]
    assert "DJANGO_SETTINGS_MODULE" in keys, f"{service_name} must run config.settings.prod"

    result = _boot_prod_settings(_dummy_env_for(keys))
    assert result.returncode == 0, (
        f"{service_name}'s render.yaml env vars are not enough to boot config.settings.prod "
        f"(missing at least one var prod.py requires):\n{result.stderr}"
    )
