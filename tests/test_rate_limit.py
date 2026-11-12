import unittest
from collections import deque
from email.message import Message
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import coleta


class RateLimiterTests(unittest.TestCase):
    def setUp(self):
        """Isola a janela móvel de cada teste."""
        self.client = coleta.PortalClient("test-key-rate-limiter", margem=1)
        coleta.PortalClient._requests_by_key.pop(
            self.client._identificador_chave, None)

    def test_spaces_general_requests_by_the_active_limit(self):
        """A próxima chamada aguarda o intervalo mínimo da cota geral."""
        coleta.PortalClient._requests_by_key[
            self.client._identificador_chave] = deque([(0.0, False)])
        clock = [0.1]
        with patch.object(coleta, "_limite_por_minuto", return_value=400), \
                patch.object(coleta.time, "monotonic",
                             side_effect=lambda: clock[0]), \
                patch.object(
                    coleta.time, "sleep",
                    side_effect=lambda seconds: clock.__setitem__(
                        0, clock[0] + seconds)):
            self.client._esperar_ritmo("endpoint")

        self.assertGreaterEqual(clock[0], 60 / 400)

    def test_restricted_endpoint_obeys_its_lower_rolling_cap(self):
        """Um endpoint restrito respeita sua cota reduzida de 60 segundos."""
        coleta.PortalClient._requests_by_key[
            self.client._identificador_chave] = deque(
                (0.0, True) for _ in range(180))
        clock = [59.9]
        with patch.object(coleta, "_limite_por_minuto", return_value=400), \
                    patch.object(coleta.time, "monotonic",
                                 side_effect=lambda: clock[0]), \
                    patch.object(
                        coleta.time, "sleep",
                        side_effect=lambda seconds: clock.__setitem__(
                            0, clock[0] + seconds)):
            self.client._esperar_ritmo(
                "bolsa-familia-disponivel-por-cpf-ou-nis")

        self.assertGreaterEqual(clock[0], 60)
        self.assertEqual(
            len(coleta.PortalClient._requests_by_key[
                self.client._identificador_chave]), 1)

    def test_retry_after_retries_and_counts_failed_http_requests(self):
        """429 respeita Retry-After e conta as tentativas feitas à API."""
        url = f"{coleta.BASE_URL}/endpoint?pagina=1"
        headers = Message()
        headers["Retry-After"] = "0"
        erro_429 = coleta.urllib.error.HTTPError(
            url, 429, "Too Many Requests", headers, BytesIO())

        class Response:
            def __enter__(self):
                """Disponibiliza a resposta falsa no bloco with."""
                return self

            def __exit__(self, *args):
                """Simula o fechamento normal da resposta HTTP."""
                return None

            def read(self):
                """Devolve uma resposta JSON vazia."""
                return b"[]"

        with patch.object(
                coleta.urllib.request, "urlopen",
                side_effect=[erro_429, Response()]) as urlopen, \
                patch.object(coleta.time, "sleep"):
            dados, _ = self.client.get(
                "endpoint", {"pagina": 1}, tentativas=2)

        self.assertEqual(dados, [])
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(self.client.total_requisicoes, 2)

    def test_rate_limit_switches_to_the_next_saved_api_key(self):
        headers = Message()
        headers["Retry-After"] = "120"
        erro_429 = coleta.urllib.error.HTTPError(
            "https://example.test", 429, "Too Many Requests", headers,
            BytesIO())
        client = coleta.PortalClient(["first-key", "second-key"])

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return b"[]"

        with patch.object(
                coleta.urllib.request, "urlopen",
                side_effect=[erro_429, Response()]) as urlopen, \
                patch.object(coleta.time, "sleep") as sleep:
            dados, _ = client.get("endpoint", {"pagina": 1})

        self.assertEqual(dados, [])
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(
            [call.args[0].get_header("Chave-api-dados")
             for call in urlopen.call_args_list],
            ["first-key", "second-key"],
        )
        sleep.assert_not_called()
        self.assertEqual(client.chave, "second-key")

    def test_json_response_with_utf8_bom_is_decoded(self):
        class Response:
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return bytes.fromhex("efbbbf5b5d")

        with patch.object(
                coleta.urllib.request, "urlopen", return_value=Response()):
            dados, _ = self.client.get("endpoint", {"pagina": 1})

        self.assertEqual(dados, [])

    def test_invalid_json_error_includes_response_metadata(self):
        class Response:
            headers = {"Content-Type": "text/html"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return b"<html>"

        with patch.object(
                coleta.urllib.request, "urlopen", return_value=Response()):
            with self.assertRaisesRegex(
                    RuntimeError,
                    r"JSONDecodeError \(Content-Type: text/html; 6 bytes; "
                    r"linha 1, coluna 1\)"):
                self.client.get("endpoint", {"pagina": 290}, tentativas=1)

    def test_only_explicit_restricted_routes_use_the_special_limit(self):
        """Somente os caminhos explicitamente classificados usam a cota."""
        self.assertTrue(coleta._endpoint_restrito(
            "/api-de-dados/bolsa-familia-disponivel-por-cpf-ou-nis"))
        self.assertTrue(coleta._endpoint_restrito(
            "despesas/documentos-por-favorecido"))
        self.assertFalse(coleta._endpoint_restrito(
            "bolsa-familia-disponivel-beneficiario-por-municipio"))

    def test_general_limit_uses_brasilia_hour(self):
        """Aplica a cota noturna e diurna com base no horário de Brasília."""
        for hora, limite in ((5, 700), (6, 400), (23, 400), (0, 700)):
            with self.subTest(hora=hora):
                class Clock:
                    @staticmethod
                    def now(tz=None):
                        """Retorna a hora simulada para o caso em teste."""
                        return SimpleNamespace(hour=hora)

                with patch.object(coleta, "datetime", Clock):
                    self.assertEqual(coleta._limite_por_minuto(), limite)


if __name__ == "__main__":
    unittest.main()
