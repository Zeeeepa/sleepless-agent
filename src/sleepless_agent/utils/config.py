"""Configuration management backed by YAML."""

from __future__ import annotations

import os
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Iterable

import yaml
from dotenv import load_dotenv

load_dotenv()

CONFIG_ENV_VAR = "SLEEPLESS_AGENT_CONFIG_FILE"
DEFAULT_CONFIG_NAME = "config.yaml"
ENV_PREFIX = "SLEEPLESS_AGENT__"
PACKAGE_ROOT = "sleepless_agent"

# Mapping for environment variables that previously relied on Pydantic aliases.
ENVIRONMENT_ALIASES: dict[str, tuple[str, ...]] = {
    "SLACK_BOT_TOKEN": ("slack", "bot_token"),
    "SLACK_APP_TOKEN": ("slack", "app_token"),
}

PATH_FIELD_KEYS: set[tuple[str, ...]] = {
    ("agent", "workspace_root"),
    ("agent", "shared_workspace"),
    ("agent", "db_path"),
    ("agent", "results_path"),
}


class ConfigNode(dict):
    """Dictionary with attribute-style access that keeps nested nodes wrapped."""

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__()
        for key, value in data.items():
            super().__setitem__(key, self._wrap(value))

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:  # pragma: no cover - mirrors attr behaviour
            raise AttributeError(name) from exc

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, self._wrap(value))

    def update(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        for key, value in dict(*args, **kwargs).items():
            self[key] = value

    @staticmethod
    def _wrap(value: Any) -> Any:
        if isinstance(value, dict) and not isinstance(value, ConfigNode):
            return ConfigNode(value)
        if isinstance(value, list):
            return [ConfigNode._wrap(item) for item in value]
        return value


class Config(ConfigNode):
    """Concrete configuration object for backward compatibility."""

    pass


def _default_config_source(path_override: str | Path | None = None) -> dict[str, Any]:
    if path_override:
        config_path = Path(path_override).expanduser().resolve()
        with config_path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    config_resource = resources.files(PACKAGE_ROOT).joinpath(DEFAULT_CONFIG_NAME)
    with config_resource.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _coerce_env_value(raw_value: str) -> Any:
    try:
        parsed_value = yaml.safe_load(raw_value)
    except yaml.YAMLError:
        return raw_value
    return parsed_value


def _apply_override(tree: dict[str, Any], path: Iterable[str], value: Any) -> None:
    current = tree
    segments = list(path)
    for segment in segments[:-1]:
        current = current.setdefault(segment, {})  # type: ignore[assignment]
    current[segments[-1]] = value


def _normalise_env_key(key: str) -> tuple[str, ...] | None:
    if key in ENVIRONMENT_ALIASES:
        return ENVIRONMENT_ALIASES[key]

    candidate = key
    if key.startswith(ENV_PREFIX):
        candidate = key[len(ENV_PREFIX) :]
    elif "__" not in key:
        return None

    parts = [segment for segment in candidate.split("__") if segment]
    if not parts:
        return None
    return tuple(part.lower() for part in parts)


def _load_env_overrides() -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for env_key, raw_value in os.environ.items():
        path = _normalise_env_key(env_key)
        if not path:
            continue
        _apply_override(overrides, path, _coerce_env_value(raw_value))
    return overrides


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _coerce_special_types(data: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(data, dict):
        return {
            key: _coerce_special_types(value, path + (key,))
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [_coerce_special_types(item, path) for item in data]
    if isinstance(data, str) and path in PATH_FIELD_KEYS:
        return Path(data).expanduser()
    return data


def _resolve_config_data(config_path: str | Path | None = None) -> Config:
    path_override = config_path or os.environ.get(CONFIG_ENV_VAR)
    base_config = _default_config_source(path_override)
    env_overrides = _load_env_overrides()
    merged_config = _deep_merge(base_config, env_overrides)
    typed_config = _coerce_special_types(merged_config)
    return Config(typed_config)


@lru_cache(maxsize=4)
def get_config(config_path: str | Path | None = None) -> Config:
    """Load configuration, applying environment overrides."""
    return _resolve_config_data(config_path)


__all__ = ["Config", "ConfigNode", "get_config"]
