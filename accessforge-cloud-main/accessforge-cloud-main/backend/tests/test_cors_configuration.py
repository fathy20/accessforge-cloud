"""CORS origin resolution: trimmed, wildcard-free, environment-aware."""

import unittest

from backend.config import (
    ConfigurationError,
    DEFAULT_CORS_ORIGINS,
    resolve_cors_origins,
)


class TestResolveCorsOrigins(unittest.TestCase):
    def test_unset_or_blank_falls_back_to_development_defaults(self):
        self.assertEqual(resolve_cors_origins("development", {}), list(DEFAULT_CORS_ORIGINS))
        self.assertEqual(
            resolve_cors_origins("production", {"CORS_ORIGINS": "  "}),
            list(DEFAULT_CORS_ORIGINS),
        )

    def test_entries_are_trimmed_and_trailing_slashes_removed(self):
        resolved = resolve_cors_origins(
            "production",
            {"CORS_ORIGINS": " https://ops.redsea.example/ , https://admin.redsea.example ,,"},
        )
        self.assertEqual(
            resolved,
            ["https://ops.redsea.example", "https://admin.redsea.example"],
        )

    def test_wildcard_is_fatal_in_production(self):
        with self.assertRaises(ConfigurationError):
            resolve_cors_origins("production", {"CORS_ORIGINS": "https://a.example,*"})

    def test_wildcard_is_dropped_with_a_warning_in_development(self):
        resolved = resolve_cors_origins("development", {"CORS_ORIGINS": "*,https://a.example"})
        self.assertEqual(resolved, ["https://a.example"])

    def test_wildcard_only_in_development_falls_back_to_defaults(self):
        resolved = resolve_cors_origins("development", {"CORS_ORIGINS": "*"})
        self.assertEqual(resolved, list(DEFAULT_CORS_ORIGINS))


if __name__ == "__main__":
    unittest.main()
