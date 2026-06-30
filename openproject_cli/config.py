"""Configuration loading and credential resolution.

Credentials are resolved like ``gh``: a YAML config file under the user's
config directory holds the default host URL and API token, and environment
variables / explicit CLI flags override the file for one-off use.

Resolution order (highest priority first) for every field:

1. explicit value passed on the command line (``--url`` / ``--token`` / ...);
2. environment variable (``OPENPROJECT_URL`` / ``OPENPROJECT_TOKEN`` / ...);
3. the config file (``~/.config/openproject-cli/config.yaml``).
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from openproject_cli import secrets
from openproject_cli.errors import AuthError, ConfigError

DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3
RETRY_BACKOFF = 0.5

ENV_URL = "OPENPROJECT_URL"
ENV_TOKEN = "OPENPROJECT_TOKEN"
ENV_TIMEOUT = "OPENPROJECT_TIMEOUT"
ENV_RETRIES = "OPENPROJECT_RETRIES"
ENV_INSECURE = "OPENPROJECT_INSECURE"
ENV_CONFIG = "OPENPROJECT_CONFIG"


@dataclass(slots=True)
class Config:
    """Effective configuration used to build an API client."""

    base_url: str
    token: str
    timeout: float = DEFAULT_TIMEOUT
    verify_ssl: bool = True
    max_retries: int = DEFAULT_RETRIES
    retry_backoff: float = RETRY_BACKOFF

    def require_credentials(self) -> None:
        """Raise AuthError if the URL or token is missing."""
        if not self.base_url:
            raise AuthError(
                "No OpenProject URL configured. Run 'openproject-cli auth login "
                "--url <url> --token <token>' or set OPENPROJECT_URL."
            )
        if not self.token:
            raise AuthError(
                "No API token configured. Run 'openproject-cli auth login "
                "--url <url> --token <token>' or set OPENPROJECT_TOKEN."
            )


def default_config_path() -> Path:
    """Return the config file path, honouring OPENPROJECT_CONFIG / XDG_CONFIG_HOME."""
    override = os.environ.get(ENV_CONFIG)
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "openproject-cli" / "config.yaml"


def _normalize_base_url(url: str) -> str:
    """Strip a trailing slash and default a scheme-less URL to ``https://``.

    A scheme is required so the client can compare the configured host against
    the host of any absolute URL it is later asked to call (the token must not
    be sent elsewhere). Without a scheme ``urlsplit`` puts everything in the
    path and the host comparison would be disabled (fail-open).
    """
    url = url.strip().rstrip("/")
    if url and "://" not in url:
        url = "https://" + url
    return url


def _resolve_numeric(
    flag: float | int | None,
    env: Mapping[str, str],
    env_name: str,
    file_data: dict,
    file_key: str,
    default: float | int,
    caster: Callable[[Any], float | int],
    kind: str,
) -> float | int:
    """Resolve a numeric setting from flag, env or file (in that order).

    Mirrors the credential precedence and raises a clear ``ConfigError`` (rather
    than an unhandled traceback) for a non-numeric env var or config-file value.
    """
    if flag is not None:
        return flag
    raw_env = env.get(env_name)
    if raw_env:
        try:
            return caster(raw_env)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{env_name} must be {kind}, got {raw_env!r}.") from exc
    raw_file = file_data.get(file_key, default)
    try:
        return caster(raw_file)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{file_key} in the config file must be {kind}, got {raw_file!r}.") from exc


def _coerce_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return None


def load_config_file(path: Path | None = None) -> dict:
    """Read and validate the YAML config file. Missing file yields an empty dict."""
    path = path or default_config_path()
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Cannot parse config file {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config file {path} must contain a YAML mapping, got {type(data).__name__}.")
    return data


def save_config_file(config: Config, path: Path | None = None) -> Path:
    """Write credentials to the config file with 0700 dir / 0600 file permissions."""
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(path.parent, 0o700)
    data = {
        "url": config.base_url,
        "timeout": config.timeout,
        "verify_ssl": config.verify_ssl,
    }
    # Only persist the token in the file when it is stored insecurely; with
    # keyring storage the file holds no secret.
    if config.token:
        data["token"] = config.token
    path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=True), encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)
    return path


def resolve_config(
    *,
    url: str | None = None,
    token: str | None = None,
    timeout: float | None = None,
    retries: int | None = None,
    insecure: bool | None = None,
    config_path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Config:
    """Merge CLI flags, environment and the config file into a single Config.

    The returned Config is not validated for completeness; call
    ``require_credentials()`` before making authenticated requests so that
    read-only/offline commands (such as ``--help``) never need a token.
    """
    env = os.environ if env is None else env
    file_data = load_config_file(config_path)

    base_url = url or env.get(ENV_URL) or file_data.get("url") or ""
    base_url = _normalize_base_url(str(base_url))

    # Token resolution order (highest first): flag, env, keyring, config file.
    keyring_token = secrets.get_token(base_url) if base_url else None
    api_token = token or env.get(ENV_TOKEN) or keyring_token or file_data.get("token") or ""

    eff_timeout = float(
        _resolve_numeric(timeout, env, ENV_TIMEOUT, file_data, "timeout", DEFAULT_TIMEOUT, float, "a number")
    )
    eff_retries = max(
        0,
        int(
            _resolve_numeric(
                retries, env, ENV_RETRIES, file_data, "retries", DEFAULT_RETRIES, int, "an integer"
            )
        ),
    )

    if insecure is not None:
        verify_ssl = not insecure
    else:
        env_insecure = _coerce_bool(env.get(ENV_INSECURE))
        if env_insecure is not None:
            verify_ssl = not env_insecure
        else:
            file_verify = _coerce_bool(file_data.get("verify_ssl"))
            verify_ssl = True if file_verify is None else file_verify

    return Config(
        base_url=base_url,
        token=str(api_token),
        timeout=eff_timeout,
        verify_ssl=verify_ssl,
        max_retries=eff_retries,
    )
