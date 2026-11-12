import json
import tempfile
import unittest
from pathlib import Path

import coleta


class NewBolsaFamiliaTests(unittest.TestCase):
    def test_extracts_new_program_dto_fields(self):
        item = {
            "beneficiarioNovoBolsaFamilia": {
                "nis": "12345678901",
                "nome": "Pessoa Beneficiaria",
                "cpfFormatado": "***.123.456-**",
            },
            "valorSaque": 600.0,
        }

        self.assertEqual(
            coleta._beneficiario_campos(item),
            ("12345678901", "Pessoa Beneficiaria", "***.123.456-**", 600.0),
        )

    def test_init_db_migrates_previously_collected_records(self):
        with tempfile.TemporaryDirectory() as directory:
            caminho = Path(directory) / "beneficios.db"
            con = coleta.init_db(str(caminho))
            extras = {
                "beneficiarioNovoBolsaFamilia": {
                    "nis": "12345678901",
                    "nome": "Pessoa Beneficiaria",
                    "cpfFormatado": "***.123.456-**",
                },
                "valorSaque": 600.0,
            }
            con.execute(
                """
                INSERT INTO beneficiario
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Novo Bolsa Familia (sacado)", "202601", "2910750",
                    "sem-nis-123", "", "", None,
                    json.dumps(extras, ensure_ascii=False),
                ),
            )
            con.commit()
            con.close()

            migrated = coleta.init_db(str(caminho))
            row = migrated.execute(
                """
                SELECT nis, nome, cpf_mascarado, valor
                FROM beneficiario
                WHERE beneficio='Novo Bolsa Familia (sacado)'
                """
            ).fetchone()
            migrated.close()

        self.assertEqual(
            row,
            ("12345678901", "Pessoa Beneficiaria", "***.123.456-**", 600.0),
        )

    def test_migration_is_idempotent(self):
        con = coleta.init_db(":memory:")
        extras = {
            "beneficiarioNovoBolsaFamilia": {
                "nis": "12345678901",
                "nome": "Pessoa Beneficiaria",
                "cpfFormatado": "***.123.456-**",
            },
            "valorSaque": 600.0,
        }
        con.execute(
            "INSERT INTO beneficiario VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "Novo Bolsa Familia (sacado)", "202601", "2910750",
                "sem-nis-123", "", "", None,
                json.dumps(extras, ensure_ascii=False),
            ),
        )

        coleta.migrar_beneficiarios_novo_bolsa_familia(con)
        coleta.migrar_beneficiarios_novo_bolsa_familia(con)
        result = con.execute(
            "SELECT nis, COUNT(*) FROM beneficiario GROUP BY nis"
        ).fetchall()

        self.assertEqual(result, [("12345678901", 1)])


if __name__ == "__main__":
    unittest.main()
