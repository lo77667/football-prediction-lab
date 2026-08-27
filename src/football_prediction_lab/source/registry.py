"""Build enabled football source adapters from a local, non-secret config."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .openligadb import OpenLigaDBClient
from .providers import FootballDataClient, SportScoreClient, TheSportsDBClient

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "configs" / "external_sources.yaml"


class ProviderConfigError(ValueError):
    """Raised when provider activation config violates the safety contract."""


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ProviderConfigError(f"{field} must be boolean")
    return value


def _provider_config(data: dict[str, Any], name: str) -> dict[str, Any]:
    providers = data.get("providers")
    if not isinstance(providers, dict) or not isinstance(providers.get(name), dict):
        raise ProviderConfigError(f"missing provider config: {name}")
    return providers[name]


def build_enabled_clients(config_path: Path = DEFAULT_CONFIG) -> dict[str, object]:
    """Build all enabled adapters; real network calls still require explicit opt-in."""

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ProviderConfigError("config must be an object")
    if data.get("mode") != "shadow_only":
        raise ProviderConfigError("provider mode must be shadow_only")
    if data.get("commercial_release") is not False:
        raise ProviderConfigError("commercial_release must remain false")
    allow_network_default = _bool(data.get("allow_network_default"), "allow_network_default")

    openligadb = _provider_config(data, "openligadb")
    sportscore = _provider_config(data, "sportscore")
    football_data = _provider_config(data, "football_data")
    thesportsdb = _provider_config(data, "thesportsdb")
    configs = {
        "openligadb": openligadb,
        "sportscore": sportscore,
        "football_data": football_data,
        "thesportsdb": thesportsdb,
    }
    clients: dict[str, object] = {}
    for name, provider in configs.items():
        enabled = _bool(provider.get("enabled"), f"providers.{name}.enabled")
        if not enabled:
            continue
        allow_network = _bool(
            provider.get("allow_network", allow_network_default),
            f"providers.{name}.allow_network",
        )
        kwargs: dict[str, Any] = {"allow_network": allow_network}
        if name == "openligadb":
            clients[name] = OpenLigaDBClient(**kwargs)
        elif name == "sportscore":
            clients[name] = SportScoreClient(**kwargs)
        elif name == "football_data":
            token_env = provider.get("token_env")
            if not isinstance(token_env, str) or not token_env:
                raise ProviderConfigError("football_data.token_env must be non-empty")
            clients[name] = FootballDataClient(token=os.getenv(token_env), **kwargs)
        elif name == "thesportsdb":
            token_env = provider.get("token_env")
            if not isinstance(token_env, str) or not token_env:
                raise ProviderConfigError("thesportsdb.token_env must be non-empty")
            clients[name] = TheSportsDBClient(token=os.getenv(token_env), **kwargs)
    return clients


__all__ = ["DEFAULT_CONFIG", "ProviderConfigError", "build_enabled_clients"]
