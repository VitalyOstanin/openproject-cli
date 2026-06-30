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
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from openproject_cli import secrets
from openproject_cli.errors import AuthError, ConfigError

DEFAULT_TIMEOUT = 30.0

ENV_URL = "OPENPROJECT_URL"
ENV_TOKEN = "OPENPROJECT_TOKEN"
ENV_TIMEOUT = "OPENPROJECT_TIMEOUT"
ENV_INSECURE = "OPENPROJECT_INSECURE"
ENV_CONFIG = "OPENPROJECT_CONFIG"


@dataclass(slots=True)
class Config:
    """Effective configuration used to build an API client."""

    base_url: str
    token: str
    timeout: float = DEFAULT_TIMEOUT
    verify_ssl: bool = True

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
    base_url = str(base_url).rstrip("/")

    # Token resolution order (highest first): flag, env, keyring, config file.
    keyring_token = secrets.get_token(base_url) if base_url else None
    api_token = token or env.get(ENV_TOKEN) or keyring_token or file_data.get("token") or ""

    if timeout is not None:
        eff_timeout = timeout
    elif env.get(ENV_TIMEOUT):
        try:
            eff_timeout = float(env[ENV_TIMEOUT])
        except ValueError as exc:
            raise ConfigError(f"{ENV_TIMEOUT} must be a number, got {env[ENV_TIMEOUT]!r}.") from exc
    else:
        eff_timeout = float(file_data.get("timeout", DEFAULT_TIMEOUT))

    if insecure is not None:
        verify_ssl = not insecure
    else:
        env_insecure = _coerce_bool(env.get(ENV_INSECURE))
        if env_insecure is not None:
            verify_ssl = not env_insecure
        else:
            file_verify = _coerce_bool(file_data.get("verify_ssl"))
            verify_ssl = True if file_verify is None else file_verify

    return Config(base_url=base_url, token=str(api_token), timeout=eff_timeout, verify_ssl=verify_ssl)
