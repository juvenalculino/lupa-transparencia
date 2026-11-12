import json
import sqlite3
import unittest

import coleta


class BpcRepresentativeTests(unittest.TestCase):
    def test_extracts_legal_representative_fields(self):
        item = {
            "menor16anos": True,
            "beneficiario": {
                "nis": "",
                "nome": "*** TITULAR MENOR DE 16 ANOS ***",
                "cpfFormatado": "***.000.000-**",
                "nomeRepresentanteLegal": "RESPONSAVEL TESTE",
                "nisRepresentanteLegal": "98765432100",
                "cpfRepresentanteLegalFormatado": "***.123.456-**",
            },
            "valor": 1518.0,
        }

        self.assertEqual(
            coleta._representante_legal(item),
            {
                "nome": "RESPONSAVEL TESTE",
                "nis": "98765432100",
                "cpf_mascarado": "***.123.456-**",
            },
        )

    def test_collection_persists_minor_status_and_representative(self):
        con = sqlite3.connect(":memory:")
        con.executescript(coleta.SCHEMA)
        item = {
            "id": 42,
            "menor16anos": True,
            "beneficiario": {
                "nis": "",
                "nome": "*** TITULAR MENOR DE 16 ANOS ***",
                "cpfFormatado": "***.000.000-**",
                "nomeRepresentanteLegal": "RESPONSAVEL TESTE",
                "nisRepresentanteLegal": "98765432100",
                "cpfRepresentanteLegalFormatado": "***.123.456-**",
            },
            "valor": 1518.0,
        }

        class Client:
            total_requisicoes = 0
            tempo_total_ms = 0.0

            def get(self, endpoint, params):
                self.total_requisicoes += 1
                return ([item] if params["pagina"] == 1 else [], 1.0)

        coleta.coletar_beneficiarios(
            Client(), con, "BPC", "202501", "2910750", "Fatima", "BA")
        nis, nome, valor, extras = con.execute(
            """
            SELECT nis, nome, valor, extras FROM beneficiario
            WHERE beneficio='BPC'
            """
        ).fetchone()
        dados_extras = json.loads(extras)

        self.assertEqual(nis, "sem-nis-42")
        self.assertEqual(nome, "*** TITULAR MENOR DE 16 ANOS ***")
        self.assertEqual(valor, 1518.0)
        self.assertTrue(dados_extras["menor16anos"])
        self.assertEqual(
            dados_extras["representanteLegal"]["nome"], "RESPONSAVEL TESTE")


if __name__ == "__main__":
    unittest.main()
