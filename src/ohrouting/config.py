"""Typed configuration for the routing experiment (T2).

Everything tunable lives here as frozen dataclasses: model profiles, the provider pin, reasoning
effort, repeats, cost caps, switch points, OTLP export and the results directory.

Sources, lowest to highest precedence: built-in defaults, an optional TOML file, environment.
Repeats and both cost caps default to ``None`` on purpose (ADR 0007: no unmeasured number is
treated as fact); ``Config.require_ready_for_sweep()`` refuses to proceed until they are set.

The OpenRouter key is never part of ``Config``. It is read from ``OPENROUTER_API_KEY`` only when
explicitly requested through ``get_api_key`` and is wrapped in ``ApiKey``, which redacts itself
in ``repr``/``str`` and refuses to be copied or pickled.
"""

from __future__ import annotations

import dataclasses
import math
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

API_KEY_ENV = "OPENROUTER_API_KEY"
CONFIG_FILE_ENV = "OHROUTING_CONFIG"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OTLP_ENDPOINT = "http://localhost:4318"
OTLP_PROTOCOL = "http/protobuf"
REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
DEFAULT_REASONING_EFFORT = "none"  # lowest value; see ADR 0009 and the spike findings addendum.


class ConfigError(ValueError):
    """Invalid or incomplete configuration."""


class MissingApiKeyError(ConfigError):
    """OPENROUTER_API_KEY was requested but is not set."""


class ApiKey:
    """Holds a secret; never reveals it through repr, str, copy, pickle or serialization."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        """Return the raw key. Call only where the key is handed to the LLM builder."""
        return self._value

    def __repr__(self) -> str:
        return "ApiKey(<redacted>)"

    __str__ = __repr__

    def __bool__(self) -> bool:
        return bool(self._value)

    def __reduce__(self) -> Any:
        raise TypeError("ApiKey cannot be pickled or copied")


@dataclass(frozen=True)
class Prices:
    """USD per token, from the OpenRouter models API (anthropic endpoint), stored with results."""

    prompt: float
    completion: float
    cache_read: float
    cache_write: float
    cache_write_1h: float


@dataclass(frozen=True)
class ModelProfile:
    role: str
    model_id: str
    prices: Prices
    base_url: str = OPENROUTER_BASE_URL

    @property
    def litellm_name(self) -> str:
        return f"openrouter/{self.model_id}"


@dataclass(frozen=True)
class ProviderPin:
    """OpenRouter provider routing (ADR 0004) plus usage accounting."""

    order: tuple[str, ...] = ("anthropic",)
    allow_fallbacks: bool = False
    usage_include: bool = True

    def extra_body(self) -> dict[str, Any]:
        return {
            "provider": {"order": list(self.order), "allow_fallbacks": self.allow_fallbacks},
            "usage": {"include": self.usage_include},
        }


@dataclass(frozen=True)
class OtelConfig:
    endpoint: str = DEFAULT_OTLP_ENDPOINT
    protocol: str = OTLP_PROTOCOL


def _default_frontier() -> ModelProfile:
    return ModelProfile(
        role="frontier",
        model_id="anthropic/claude-sonnet-5.5",
        prices=Prices(0.000002, 0.00001, 0.0000001, 0.0000025, 0.000004),
    )


def _default_cheap() -> ModelProfile:
    return ModelProfile(
        role="cheap",
        model_id="anthropic/claude-haiku-5.5",
        prices=Prices(0.0000001, 0.0000005, 0.00000001, 0.000000125, 0.0000002),
    )


@dataclass(frozen=True)
class Config:
    frontier: ModelProfile = field(default_factory=_default_frontier)
    cheap: ModelProfile = field(default_factory=_default_cheap)
    provider: ProviderPin = field(default_factory=ProviderPin)
    reasoning_effort: str = DEFAULT_REASONING_EFFORT
    repeats: int | None = None
    per_run_cap_usd: float | None = None
    per_sweep_cap_usd: float | None = None
    switch_points: tuple[int, ...] = (5, 10, 15)
    otel: OtelConfig = field(default_factory=OtelConfig)
    results_dir: str = "results"

    def models(self) -> dict[str, ModelProfile]:
        return {"frontier": self.frontier, "cheap": self.cheap}

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable dump (contains no secrets: the key is not part of Config)."""
        return dataclasses.asdict(self)

    def unset_run_settings(self) -> list[str]:
        """Names of the ADR 0007 values still unset (None)."""
        names = ("repeats", "per_run_cap_usd", "per_sweep_cap_usd")
        return [n for n in names if getattr(self, n) is None]

    def require_ready_for_sweep(self) -> None:
        missing = self.unset_run_settings()
        if missing:
            raise ConfigError(
                f"unset before a live run/sweep: {', '.join(missing)} "
                "(ADR 0007: set explicitly in the config file or OHROUTING_* env vars)"
            )


# ---------------------------------------------------------------- validation helpers


def _fail(where: str, msg: str) -> ConfigError:
    return ConfigError(f"{where}: {msg}")


def _as_int(value: Any, where: str, minimum: int = 1) -> int:
    if isinstance(value, bool):
        raise _fail(where, f"expected an integer, got {value!r}")
    if isinstance(value, str):
        try:
            value = int(value.strip())
        except ValueError:
            raise _fail(where, f"expected an integer, got {value!r}") from None
    if not isinstance(value, int):
        raise _fail(where, f"expected an integer, got {value!r}")
    if value < minimum:
        raise _fail(where, f"must be >= {minimum}, got {value}")
    return value


def _as_cap(value: Any, where: str) -> float:
    if isinstance(value, bool):
        raise _fail(where, f"expected a number, got {value!r}")
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            raise _fail(where, f"expected a number, got {value!r}") from None
    if not isinstance(value, int | float):
        raise _fail(where, f"expected a number, got {value!r}")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise _fail(where, f"must be a positive finite number, got {value}")
    return value


def _as_str(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(where, f"expected a non-empty string, got {value!r}")
    return value.strip()


def _as_bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise _fail(where, f"expected true/false, got {value!r}")
    return value


def _as_switch_points(value: Any, where: str) -> tuple[int, ...]:
    if isinstance(value, str):
        value = [part for part in value.replace(",", " ").split() if part]
    if not isinstance(value, list | tuple) or not value:
        raise _fail(where, f"expected a non-empty list of integers, got {value!r}")
    points = tuple(_as_int(v, where) for v in value)
    if len(set(points)) != len(points):
        raise _fail(where, f"duplicate values in {points}")
    return tuple(sorted(points))


def _check_keys(table: Mapping[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise _fail(where, f"unknown key(s) {unknown}; allowed: {sorted(allowed)}")


def _table(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _fail(where, "expected a table")
    return value


# ---------------------------------------------------------------- building from sources


def _build_prices(base: Prices, raw: Any, where: str) -> Prices:
    table = _table(raw, where)
    names = {f.name for f in dataclasses.fields(Prices)}
    _check_keys(table, names, where)
    updates = {}
    for name, value in table.items():
        if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
            raise _fail(f"{where}.{name}", f"expected a number >= 0, got {value!r}")
        updates[name] = float(value)
    return dataclasses.replace(base, **updates)


def _build_model(base: ModelProfile, raw: Any, where: str) -> ModelProfile:
    table = _table(raw, where)
    _check_keys(table, {"id", "base_url", "prices"}, where)
    updates: dict[str, Any] = {}
    if "id" in table:
        model_id = _as_str(table["id"], f"{where}.id")
        if "/" not in model_id or model_id.startswith("openrouter/"):
            raise _fail(
                f"{where}.id", f"expected an OpenRouter id like 'anthropic/x', got {model_id!r}"
            )
        updates["model_id"] = model_id
    if "base_url" in table:
        url = _as_str(table["base_url"], f"{where}.base_url")
        if not url.startswith(("http://", "https://")):
            raise _fail(f"{where}.base_url", f"must start with http:// or https://, got {url!r}")
        updates["base_url"] = url
    if "prices" in table:
        updates["prices"] = _build_prices(base.prices, table["prices"], f"{where}.prices")
    return dataclasses.replace(base, **updates)


def _build_provider(base: ProviderPin, raw: Any) -> ProviderPin:
    where = "provider"
    table = _table(raw, where)
    _check_keys(table, {"order", "allow_fallbacks", "usage_include"}, where)
    updates: dict[str, Any] = {}
    if "order" in table:
        order = table["order"]
        if not isinstance(order, list | tuple) or not order:
            raise _fail("provider.order", f"expected a non-empty list of strings, got {order!r}")
        updates["order"] = tuple(_as_str(o, "provider.order") for o in order)
    for name in ("allow_fallbacks", "usage_include"):
        if name in table:
            updates[name] = _as_bool(table[name], f"provider.{name}")
    return dataclasses.replace(base, **updates)


def _build_otel(base: OtelConfig, raw: Any) -> OtelConfig:
    where = "otel"
    table = _table(raw, where)
    _check_keys(table, {"endpoint", "protocol"}, where)
    updates: dict[str, Any] = {}
    if "endpoint" in table:
        updates["endpoint"] = _check_endpoint(table["endpoint"], "otel.endpoint")
    if "protocol" in table:
        updates["protocol"] = _check_protocol(table["protocol"], "otel.protocol")
    return dataclasses.replace(base, **updates)


def _check_endpoint(value: Any, where: str) -> str:
    url = _as_str(value, where)
    if not url.startswith(("http://", "https://")):
        raise _fail(where, f"must start with http:// or https://, got {url!r}")
    return url


def _check_protocol(value: Any, where: str) -> str:
    proto = _as_str(value, where)
    if proto != OTLP_PROTOCOL:
        raise _fail(where, f"only {OTLP_PROTOCOL!r} is supported, got {proto!r}")
    return proto


def _check_reasoning(value: Any, where: str) -> str:
    effort = _as_str(value, where).lower()
    if effort not in REASONING_EFFORTS:
        raise _fail(where, f"must be one of {list(REASONING_EFFORTS)}, got {effort!r}")
    return effort


_TOP_LEVEL_KEYS = {
    "reasoning_effort",
    "repeats",
    "per_run_cap_usd",
    "per_sweep_cap_usd",
    "switch_points",
    "results_dir",
    "models",
    "provider",
    "otel",
}


def _apply_mapping(cfg: Config, data: Mapping[str, Any]) -> Config:
    _check_keys(data, _TOP_LEVEL_KEYS, "config")
    updates: dict[str, Any] = {}
    if "reasoning_effort" in data:
        updates["reasoning_effort"] = _check_reasoning(data["reasoning_effort"], "reasoning_effort")
    if "repeats" in data:
        updates["repeats"] = _as_int(data["repeats"], "repeats")
    for name in ("per_run_cap_usd", "per_sweep_cap_usd"):
        if name in data:
            updates[name] = _as_cap(data[name], name)
    if "switch_points" in data:
        updates["switch_points"] = _as_switch_points(data["switch_points"], "switch_points")
    if "results_dir" in data:
        updates["results_dir"] = _as_str(data["results_dir"], "results_dir")
    if "models" in data:
        models = _table(data["models"], "models")
        _check_keys(models, {"frontier", "cheap"}, "models")
        for role in ("frontier", "cheap"):
            if role in models:
                updates[role] = _build_model(getattr(cfg, role), models[role], f"models.{role}")
    if "provider" in data:
        updates["provider"] = _build_provider(cfg.provider, data["provider"])
    if "otel" in data:
        updates["otel"] = _build_otel(cfg.otel, data["otel"])
    return dataclasses.replace(cfg, **updates)


def _apply_env(cfg: Config, env: Mapping[str, str]) -> Config:
    updates: dict[str, Any] = {}
    simple: dict[str, tuple[str, Any]] = {
        "OHROUTING_REASONING_EFFORT": ("reasoning_effort", _check_reasoning),
        "OHROUTING_REPEATS": ("repeats", _as_int),
        "OHROUTING_PER_RUN_CAP_USD": ("per_run_cap_usd", _as_cap),
        "OHROUTING_PER_SWEEP_CAP_USD": ("per_sweep_cap_usd", _as_cap),
        "OHROUTING_SWITCH_POINTS": ("switch_points", _as_switch_points),
        "OHROUTING_RESULTS_DIR": ("results_dir", _as_str),
    }
    for var, (name, parse) in simple.items():
        if env.get(var, "").strip():
            updates[name] = parse(env[var], var)

    otel: dict[str, Any] = {}
    endpoint_var = next(
        (
            v
            for v in ("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT")
            if env.get(v, "").strip()
        ),
        None,
    )
    if endpoint_var:
        otel["endpoint"] = _check_endpoint(env[endpoint_var], endpoint_var)
    protocol_var = next(
        (
            v
            for v in ("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "OTEL_EXPORTER_OTLP_PROTOCOL")
            if env.get(v, "").strip()
        ),
        None,
    )
    if protocol_var:
        otel["protocol"] = _check_protocol(env[protocol_var], protocol_var)
    if otel:
        updates["otel"] = dataclasses.replace(cfg.otel, **otel)
    return dataclasses.replace(cfg, **updates)


def _validate(cfg: Config) -> None:
    if cfg.per_run_cap_usd is not None and cfg.per_sweep_cap_usd is not None:
        if cfg.per_run_cap_usd > cfg.per_sweep_cap_usd:
            raise ConfigError(
                f"per_run_cap_usd ({cfg.per_run_cap_usd}) exceeds "
                f"per_sweep_cap_usd ({cfg.per_sweep_cap_usd})"
            )
    if cfg.frontier.model_id == cfg.cheap.model_id:
        raise ConfigError("frontier and cheap model ids must differ")


def load_config(
    path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Config:
    """Build a Config: defaults, then the TOML file (``path`` or $OHROUTING_CONFIG), then env."""

    env = os.environ if environ is None else environ
    cfg = Config()
    file_path = path if path is not None else (env.get(CONFIG_FILE_ENV) or None)
    if file_path is not None:
        p = Path(file_path)
        try:
            with p.open("rb") as fh:
                data = tomllib.load(fh)
        except FileNotFoundError:
            raise ConfigError(f"config file not found: {p}") from None
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"config file {p} is not valid TOML: {exc}") from None
        cfg = _apply_mapping(cfg, data)
    cfg = _apply_env(cfg, env)
    _validate(cfg)
    return cfg


def get_api_key(environ: Mapping[str, str] | None = None) -> ApiKey:
    """Read OPENROUTER_API_KEY from the environment. Raises only when called without a key."""

    env = os.environ if environ is None else environ
    value = env.get(API_KEY_ENV, "").strip()
    if not value:
        raise MissingApiKeyError(
            f"{API_KEY_ENV} is not set; supply it via `op run --env-file=... --` "
            "(the harness never reads it from files or arguments)"
        )
    return ApiKey(value)
