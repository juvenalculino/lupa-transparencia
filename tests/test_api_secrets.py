import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi import HTTPException
from starlette.requests import Request

import api_secrets
import api
from api_secrets import (
    SecretStoreError, create_server_secrets, delete_api_key, list_api_keys,
    load_api_key, load_api_keys, load_server_secrets, save_api_key,
)


def local_request(host="127.0.0.1", origin=None):
    headers = []
    if origin:
        headers.append((b"origin", origin.encode("ascii")))
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (host, 1234),
        "server": ("127.0.0.1", 8000),
    })


class ApiSecretStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.secret_path = Path(self.temp_dir.name) / "portal-key.enc"
        self.environment = patch.dict(os.environ, {
            "PORTAL_API_KEY_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "PORTAL_API_ADMIN_TOKEN": "admin-token-test",
            "PORTAL_API_KEY_FILE": str(self.secret_path),
        })
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_api_key_is_encrypted_and_can_be_loaded_and_deleted(self):
        api_key = "private-portal-api-key"

        save_api_key(api_key)

        encrypted_file = self.secret_path.read_bytes()
        self.assertNotIn(api_key.encode(), encrypted_file)
        if os.name == "posix":
            self.assertEqual(self.secret_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(load_api_key(), api_key)
        self.assertTrue(delete_api_key())
        self.assertFalse(self.secret_path.exists())
        self.assertIsNone(load_api_key())

    def test_invalid_encryption_key_fails_explicitly(self):
        save_api_key("private-portal-api-key")
        os.environ["PORTAL_API_KEY_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

        with self.assertRaisesRegex(SecretStoreError, "não pode ser descriptografada"):
            load_api_key()

    def test_saving_api_key_works_without_os_fchmod(self):
        with patch.object(api_secrets.os, "fchmod", None):
            save_api_key("private-portal-api-key")

        self.assertEqual(load_api_key(), "private-portal-api-key")

    def test_server_secret_setup_is_private_and_does_not_overwrite_existing_file(self):
        config_path = Path(self.temp_dir.name) / "server.env"

        self.assertTrue(create_server_secrets(config_path))
        original_config = config_path.read_text(encoding="utf-8")
        if os.name == "posix":
            self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(create_server_secrets(config_path))
        self.assertEqual(config_path.read_text(encoding="utf-8"), original_config)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PORTAL_API_ADMIN_TOKEN", None)
            os.environ.pop("PORTAL_API_KEY_ENCRYPTION_KEY", None)
            load_server_secrets(config_path)
            self.assertTrue(os.environ["PORTAL_API_KEY_ENCRYPTION_KEY"])
            self.assertNotIn("PORTAL_API_ADMIN_TOKEN", os.environ)

    def test_key_management_is_local_and_does_not_require_admin_token(self):
        request = api.ApiKeyRequest(api_key="private-portal-api-key")

        with self.assertRaises(HTTPException) as non_local:
            api.api_key_save(request, local_request("192.0.2.10"))
        self.assertEqual(non_local.exception.status_code, 403)
        with self.assertRaises(HTTPException) as remote_origin:
            api.api_key_status(local_request(origin="https://example.com"))
        self.assertEqual(remote_origin.exception.status_code, 403)
        self.assertFalse(self.secret_path.exists())

    def test_key_management_lists_masked_keys_and_removes_one_at_a_time(self):
        save_api_key("private-portal-api-key")
        save_api_key("second-private-key")

        status = api.api_key_status(local_request())

        self.assertEqual(status["configured"], True)
        self.assertEqual(len(status["keys"]), 2)
        self.assertEqual(status["keys"][0]["label"], "••••-key")
        self.assertNotIn("api_key", status)
        self.assertNotIn("private-portal-api-key", str(status))

        key_to_remove = status["keys"][0]["id"]
        response = api.api_key_delete(key_to_remove, local_request())
        self.assertEqual(response["configured"], True)
        self.assertEqual(load_api_keys(), ["second-private-key"])

    def test_saving_keys_preserves_existing_key_and_legacy_single_key_file(self):
        save_api_key("first-private-key")
        save_api_key("second-private-key")
        save_api_key("first-private-key")

        self.assertEqual(
            load_api_keys(), ["first-private-key", "second-private-key"])
        self.assertEqual(load_api_key(), "first-private-key")
        self.assertEqual(len(list_api_keys()), 2)

        self.secret_path.write_bytes(
            Fernet(os.environ["PORTAL_API_KEY_ENCRYPTION_KEY"].encode())
            .encrypt(b"legacy-private-key")
        )
        self.assertEqual(load_api_keys(), ["legacy-private-key"])

    def test_key_status_never_returns_the_secret(self):
        save_api_key("private-portal-api-key")

        status = api.api_key_status(local_request())

        self.assertEqual(status["enabled"], True)
        self.assertEqual(status["configured"], True)
        self.assertNotIn("api_key", status)

    def test_collection_requires_portal_api_key_before_database_access(self):
        request = api.ConsultaRequest(
            tipo="Adicionar beneficiários",
            programa="Novo Bolsa Familia",
            uf="BA",
            codigo_ibge="2910750",
            nome_mun="Fátima",
            ano="2025",
            mes="01",
            permitir_novos=True,
        )

        with (
            patch.dict(os.environ, {"PORTAL_API_KEY": ""}),
            patch.object(api, "init_db") as init_db,
        ):
            with self.assertRaises(HTTPException) as response:
                api.consultar_dados(request)

        self.assertEqual(response.exception.status_code, 409)
        init_db.assert_not_called()

    def test_collection_can_use_the_provided_portal_key_without_admin_token(self):
        con = api.init_db(":memory:")
        previous_status = api._status_coleta
        request = api.ConsultaRequest(
            tipo="Adicionar beneficiários",
            programa="Novo Bolsa Familia",
            uf="BA",
            codigo_ibge="2910750",
            nome_mun="Fátima",
            ano="2025",
            mes="01",
            permitir_novos=True,
            api_key="private-portal-api-key",
        )
        try:
            with (
                patch.dict(os.environ, {"PORTAL_API_KEY": ""}),
                patch.object(api, "init_db", return_value=con),
                patch.object(api, "meses_validos_ano", return_value=["01"]),
                patch.object(api, "meses_beneficiarios_faltantes", return_value=[]),
            ):
                response = api.consultar_dados(request)
        finally:
            api._status_coleta = previous_status
            con.close()

        self.assertEqual(response["registros"], 0)
        self.assertEqual(response["dados"], [])

    def test_collection_can_use_the_stored_key_without_admin_token(self):
        con = api.init_db(":memory:")
        previous_status = api._status_coleta
        request = api.ConsultaRequest(
            tipo="Adicionar beneficiários",
            programa="Novo Bolsa Familia",
            uf="BA",
            codigo_ibge="2910750",
            nome_mun="Fátima",
            ano="2025",
            mes="01",
            permitir_novos=True,
        )
        try:
            with (
                patch.dict(os.environ, {"PORTAL_API_KEY": ""}),
                patch.object(
                    api, "_load_stored_api_keys",
                    return_value=["private-portal-api-key"],
                ),
                patch.object(api, "init_db", return_value=con),
                patch.object(api, "meses_validos_ano", return_value=["01"]),
                patch.object(api, "meses_beneficiarios_faltantes", return_value=[]),
            ):
                response = api.consultar_dados(request)
        finally:
            api._status_coleta = previous_status
            con.close()

        self.assertEqual(response["registros"], 0)
        self.assertEqual(response["dados"], [])


if __name__ == "__main__":
    unittest.main()
