"""Unit tests for ohrouting.config: no network, no real keys."""

import copy
import json
import pickle
import tempfile
import unittest
from pathlib import Path

from ohrouting import config as cfgmod
from ohrouting.config import (
    ApiKey,
    Config,
    ConfigError,
    MissingApiKeyError,
    get_api_key,
    load_config,
)

FAKE_KEY = "not-a-real-key-0123456789"


def write_toml(text: str) -> str:
    fh = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
    fh.write(text)
    fh.close()
    path = Path(fh.name)
    return str(path)


class DefaultsTest(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config(environ={})

    def test_model_pair(self):
        self.assertEqual(self.cfg.frontier.model_id, "anthropic/claude-sonnet-5.5")
        self.assertEqual(self.cfg.cheap.model_id, "anthropic/claude-haiku-5.5")
        self.assertEqual(self.cfg.frontier.litellm_name, "openrouter/anthropic/claude-sonnet-5.5")
        self.assertEqual(self.cfg.cheap.litellm_name, "openrouter/anthropic/claude-haiku-5.5")
        self.assertEqual(self.cfg.frontier.base_url, "https://openrouter.ai/api/v1")

    def test_prices(self):
        self.assertEqual(self.cfg.frontier.prices.prompt, 0.000002)
        self.assertEqual(self.cfg.cheap.prices.cache_read, 0.00000001)

    def test_provider_pin(self):
        self.assertEqual(
            self.cfg.provider.extra_body(),
            {
                "provider": {"order": ["anthropic"], "allow_fallbacks": False},
                "usage": {"include": True},
            },
        )

    def test_reasoning_effort_default_is_explicit(self):
        self.assertEqual(self.cfg.reasoning_effort, "none")

    def test_unmeasured_values_unset(self):
        self.assertIsNone(self.cfg.repeats)
        self.assertIsNone(self.cfg.per_run_cap_usd)
        self.assertIsNone(self.cfg.per_sweep_cap_usd)
        self.assertEqual(
            self.cfg.unset_run_settings(), ["repeats", "per_run_cap_usd", "per_sweep_cap_usd"]
        )
        with self.assertRaises(ConfigError) as ctx:
            self.cfg.require_ready_for_sweep()
        self.assertIn("per_run_cap_usd", str(ctx.exception))

    def test_switch_points_otel_results(self):
        self.assertEqual(self.cfg.switch_points, (5, 10, 15))
        self.assertEqual(self.cfg.otel.endpoint, "http://localhost:4318")
        self.assertEqual(self.cfg.otel.protocol, "http/protobuf")
        self.assertEqual(self.cfg.results_dir, "results")

    def test_defaults_do_not_need_a_key(self):
        load_config(environ={})  # must not raise without OPENROUTER_API_KEY


class EnvOverrideTest(unittest.TestCase):
    def test_scalars(self):
        cfg = load_config(
            environ={
                "OHROUTING_REPEATS": "2",
                "OHROUTING_PER_RUN_CAP_USD": "0.5",
                "OHROUTING_PER_SWEEP_CAP_USD": "3",
                "OHROUTING_REASONING_EFFORT": "LOW",
                "OHROUTING_SWITCH_POINTS": "3, 7",
                "OHROUTING_RESULTS_DIR": "out",
            }
        )
        self.assertEqual(cfg.repeats, 2)
        self.assertEqual(cfg.per_run_cap_usd, 0.5)
        self.assertEqual(cfg.per_sweep_cap_usd, 3.0)
        self.assertEqual(cfg.reasoning_effort, "low")
        self.assertEqual(cfg.switch_points, (3, 7))
        self.assertEqual(cfg.results_dir, "out")
        cfg.require_ready_for_sweep()

    def test_otlp_env(self):
        cfg = load_config(
            environ={
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://jaeger:4318/v1/traces",
                "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http/protobuf",
            }
        )
        self.assertEqual(cfg.otel.endpoint, "http://jaeger:4318/v1/traces")

    def test_otlp_generic_endpoint_and_traces_precedence(self):
        cfg = load_config(environ={"OTEL_EXPORTER_OTLP_ENDPOINT": "http://a:4318"})
        self.assertEqual(cfg.otel.endpoint, "http://a:4318")
        cfg = load_config(
            environ={
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://a:4318",
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://b:4318",
            }
        )
        self.assertEqual(cfg.otel.endpoint, "http://b:4318")

    def test_blank_env_ignored(self):
        cfg = load_config(environ={"OHROUTING_REPEATS": "  "})
        self.assertIsNone(cfg.repeats)


class TomlOverrideTest(unittest.TestCase):
    def test_toml_values(self):
        path = write_toml(
            """
repeats = 4
per_run_cap_usd = 1.5
per_sweep_cap_usd = 20
reasoning_effort = "low"
switch_points = [4, 8]
results_dir = "r"

[models.cheap]
id = "anthropic/claude-haiku-4.5"

[models.frontier.prices]
prompt = 0.000003

[provider]
order = ["anthropic", "google-vertex"]
allow_fallbacks = true

[otel]
endpoint = "http://collector:4318"
"""
        )
        self.addCleanup(Path(path).unlink)
        cfg = load_config(path, environ={})
        self.assertEqual(cfg.repeats, 4)
        self.assertEqual(cfg.per_sweep_cap_usd, 20.0)
        self.assertEqual(cfg.switch_points, (4, 8))
        self.assertEqual(cfg.cheap.model_id, "anthropic/claude-haiku-4.5")
        self.assertEqual(cfg.frontier.prices.prompt, 0.000003)
        self.assertEqual(cfg.frontier.prices.completion, 0.00001)  # untouched default
        self.assertEqual(cfg.provider.order, ("anthropic", "google-vertex"))
        self.assertTrue(cfg.provider.allow_fallbacks)
        self.assertEqual(cfg.otel.endpoint, "http://collector:4318")

    def test_env_beats_toml(self):
        path = write_toml("repeats = 4\n")
        self.addCleanup(Path(path).unlink)
        cfg = load_config(path, environ={"OHROUTING_REPEATS": "6"})
        self.assertEqual(cfg.repeats, 6)

    def test_path_from_env(self):
        path = write_toml("repeats = 5\n")
        self.addCleanup(Path(path).unlink)
        self.assertEqual(load_config(environ={"OHROUTING_CONFIG": path}).repeats, 5)


class ValidationTest(unittest.TestCase):
    def assert_toml_error(self, text: str, fragment: str):
        path = write_toml(text)
        self.addCleanup(Path(path).unlink)
        with self.assertRaises(ConfigError) as ctx:
            load_config(path, environ={})
        self.assertIn(fragment, str(ctx.exception))

    def assert_env_error(self, env: dict, fragment: str):
        with self.assertRaises(ConfigError) as ctx:
            load_config(environ=env)
        self.assertIn(fragment, str(ctx.exception))

    def test_bad_toml_values(self):
        self.assert_toml_error("repeats = 0\n", "repeats: must be >= 1")
        self.assert_toml_error("repeats = true\n", "repeats: expected an integer")
        self.assert_toml_error("per_run_cap_usd = -1\n", "per_run_cap_usd: must be a positive")
        self.assert_toml_error('per_run_cap_usd = "x"\n', "expected a number")
        self.assert_toml_error('reasoning_effort = "turbo"\n', "reasoning_effort: must be one of")
        self.assert_toml_error("switch_points = []\n", "switch_points")
        self.assert_toml_error("switch_points = [5, 5]\n", "duplicate")
        self.assert_toml_error('[models.cheap]\nid = "haiku"\n', "models.cheap.id")
        self.assert_toml_error('[otel]\nprotocol = "grpc"\n', "otel.protocol")
        self.assert_toml_error('[otel]\nendpoint = "localhost:4318"\n', "otel.endpoint")
        self.assert_toml_error("[provider]\norder = []\n", "provider.order")
        self.assert_toml_error('[provider]\nallow_fallbacks = "no"\n', "allow_fallbacks")
        self.assert_toml_error("[models.cheap.prices]\nprompt = -1\n", "models.cheap.prices.prompt")

    def test_unknown_keys(self):
        self.assert_toml_error("api_key = 'x'\n", "unknown key(s) ['api_key']")
        self.assert_toml_error("[provider]\nfoo = 1\n", "provider: unknown key")

    def test_invalid_toml_and_missing_file(self):
        self.assert_toml_error("repeats = = 1\n", "not valid TOML")
        with self.assertRaises(ConfigError) as ctx:
            load_config("/nonexistent/ohrouting.toml", environ={})
        self.assertIn("not found", str(ctx.exception))

    def test_cross_field(self):
        self.assert_toml_error("per_run_cap_usd = 5\nper_sweep_cap_usd = 1\n", "exceeds")
        self.assert_toml_error(
            '[models.cheap]\nid = "anthropic/claude-sonnet-5.5"\n', "must differ"
        )

    def test_bad_env(self):
        self.assert_env_error({"OHROUTING_REPEATS": "many"}, "OHROUTING_REPEATS")
        self.assert_env_error({"OHROUTING_PER_RUN_CAP_USD": "nan"}, "OHROUTING_PER_RUN_CAP_USD")
        self.assert_env_error({"OHROUTING_SWITCH_POINTS": "5,x"}, "OHROUTING_SWITCH_POINTS")
        self.assert_env_error(
            {"OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "grpc"}, "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"
        )


class ApiKeyTest(unittest.TestCase):
    def test_missing_key_only_raises_when_requested(self):
        cfg = load_config(environ={})  # no raise
        self.assertIsInstance(cfg, Config)
        with self.assertRaises(MissingApiKeyError) as ctx:
            get_api_key({})
        self.assertIn("OPENROUTER_API_KEY", str(ctx.exception))
        with self.assertRaises(MissingApiKeyError):
            get_api_key({"OPENROUTER_API_KEY": "   "})

    def test_key_read_from_env(self):
        key = get_api_key({"OPENROUTER_API_KEY": FAKE_KEY})
        self.assertEqual(key.reveal(), FAKE_KEY)

    def test_redaction_in_repr_and_str(self):
        key = get_api_key({"OPENROUTER_API_KEY": FAKE_KEY})
        for text in (repr(key), str(key), f"{key}", f"{key!r}", repr([key]), repr({"k": key})):
            self.assertNotIn(FAKE_KEY, text)
        self.assertIn("redacted", repr(key))

    def test_key_not_in_config_dump_or_repr(self):
        env = {"OPENROUTER_API_KEY": FAKE_KEY}
        cfg = load_config(environ=env)
        get_api_key(env)
        self.assertNotIn(FAKE_KEY, repr(cfg))
        self.assertNotIn(FAKE_KEY, str(cfg))
        self.assertNotIn(FAKE_KEY, json.dumps(cfg.to_dict()))
        self.assertFalse(hasattr(cfg, "api_key"))
        self.assertNotIn("key", " ".join(cfg.to_dict()).lower())

    def test_key_not_serializable_or_copyable(self):
        key = ApiKey(FAKE_KEY)
        with self.assertRaises(TypeError):
            json.dumps({"k": key})
        with self.assertRaises(TypeError):
            pickle.dumps(key)
        with self.assertRaises(TypeError):
            copy.deepcopy(key)

    def test_config_has_no_secret_fields(self):
        names = {f.name for f in cfgmod.dataclasses.fields(Config)}
        self.assertFalse({n for n in names if "key" in n or "secret" in n or "token" in n})


class DumpTest(unittest.TestCase):
    def test_to_dict_is_json_serialisable_and_has_prices(self):
        d = load_config(environ={}).to_dict()
        text = json.dumps(d)
        self.assertIn("claude-haiku-5.5", text)
        self.assertEqual(d["frontier"]["prices"]["cache_write"], 0.0000025)


if __name__ == "__main__":
    unittest.main()
