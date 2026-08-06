import unittest

from gateway_security import (
    AuthenticationError,
    extract_mcp_api_key,
    require_runtime_secrets,
)


class GatewaySecurityTests(unittest.TestCase):
    def test_accepts_x_api_key(self):
        self.assertEqual(extract_mcp_api_key({"x-api-key": "hub-key"}), "hub-key")

    def test_accepts_bearer_api_key(self):
        self.assertEqual(
            extract_mcp_api_key({"authorization": "Bearer hub-key"}), "hub-key"
        )

    def test_rejects_basic_as_mcp_api_key(self):
        with self.assertRaises(AuthenticationError):
            extract_mcp_api_key({"authorization": "Basic c2VjcmV0"})

    def test_requires_all_runtime_secrets(self):
        with self.assertRaisesRegex(ValueError, "TRINO_SERVICE_PASSWORD"):
            require_runtime_secrets(
                {
                    "DATABASE_URL": "postgresql://example",
                    "TRINO_CATALOG_ENCRYPTION_KEY": "key",
                    "TRINO_SERVICE_USER": "trino_gateway",
                }
            )


if __name__ == "__main__":
    unittest.main()
