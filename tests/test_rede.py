import json
import sqlite3
import unittest

from rede import (
    NOME_MENOR_BPC,
    buscar_pessoas,
    criar_grafo_pessoa,
    criar_grafo_programas,
    para_dot,
    programas_da_pessoa,
)


class RedeTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute(
            """
            CREATE TABLE beneficiario (
                beneficio TEXT NOT NULL,
                mes_ano TEXT NOT NULL,
                codigo_ibge TEXT NOT NULL,
                nis TEXT NOT NULL,
                nome TEXT,
                valor REAL,
                extras TEXT
            )
            """
        )

    def tearDown(self):
        self.con.close()

    def adicionar(self, beneficio, mes, nis, nome, extras=None, valor=0):
        self.con.execute(
            """
            INSERT INTO beneficiario
                (beneficio, mes_ano, codigo_ibge, nis, nome, valor, extras)
            VALUES (?, ?, '2910750', ?, ?, ?, ?)
            """,
            (beneficio, mes, nis, nome, valor, json.dumps(extras or {})),
        )

    def test_program_graph_counts_distinct_shared_nis_and_excludes_synthetic(self):
        self.adicionar("BPC", "202501", "11111111111", "PESSOA A")
        self.adicionar("BPC", "202502", "11111111111", "PESSOA A")
        self.adicionar("BPC", "202501", "22222222222", "PESSOA B")
        self.adicionar("Programa X", "202501", "11111111111", "PESSOA A")
        self.adicionar("Programa X", "202502", "22222222222", "PESSOA B")
        self.adicionar("Programa X", "202501", "sem-nis-3", "PESSOA C")

        graph = criar_grafo_programas(self.con, "2910750")
        bpc = next(data for _, data in graph.nodes(data=True)
                   if data["label"].startswith("BPC\n"))
        shared = next(iter(graph.edges(data=True)))[2]["peso"]

        self.assertEqual(bpc["pessoas"], 2)
        self.assertEqual(shared, 2)
        self.assertEqual(graph.number_of_edges(), 1)

    def test_year_filter_and_minimum_shared_count(self):
        self.adicionar("BPC", "202501", "11111111111", "PESSOA A")
        self.adicionar("Programa X", "202501", "11111111111", "PESSOA A")
        self.adicionar("BPC", "202401", "22222222222", "PESSOA B")
        self.adicionar("Programa X", "202401", "22222222222", "PESSOA B")

        graph = criar_grafo_programas(
            self.con, "2910750", ano=2025, minimo_compartilhados=2)

        self.assertEqual(graph.number_of_nodes(), 2)
        self.assertEqual(graph.number_of_edges(), 0)

    def test_month_filter_uses_only_selected_months(self):
        self.adicionar("BPC", "202501", "11111111111", "PESSOA A")
        self.adicionar("Programa X", "202502", "11111111111", "PESSOA A")

        graph = criar_grafo_programas(
            self.con, "2910750", ano=2025, meses=["01"])

        self.assertEqual(graph.number_of_nodes(), 1)
        self.assertEqual(graph.number_of_edges(), 0)

    def test_same_name_with_different_nis_remains_two_candidates(self):
        self.adicionar("BPC", "202501", "11111111111", "JOSE SILVA")
        self.adicionar("BPC", "202501", "22222222222", "JOSE SILVA")

        candidates = buscar_pessoas(self.con, "2910750", "JOSE SILVA")

        self.assertEqual({row[0] for row in candidates},
                         {"11111111111", "22222222222"})

    def test_global_search_finds_person_across_programs_and_years(self):
        self.adicionar("BPC", "202401", "11111111111", "MARIA TESTE")
        self.adicionar("Novo Bolsa Familia (sacado)", "202501",
                       "11111111111", "MARIA TESTE", valor=600)
        self.adicionar("BPC", "202501", "99999999999", "OUTRO MUNICIPIO")
        self.con.execute(
            """
            INSERT INTO beneficiario
                (beneficio, mes_ano, codigo_ibge, nis, nome, valor, extras)
            VALUES ('Garantia Safra', '202502', '9999999',
                    '11111111111', 'MARIA TESTE', 1000, '{}')
            """
        )

        people = buscar_pessoas(self.con, "2910750", "MARIA TESTE")
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0][3], 2)

        programs = programas_da_pessoa(
            self.con, "2910750", "11111111111")
        self.assertEqual(
            {row[0] for row in programs},
            {"BPC", "Novo Bolsa Familia (sacado)"},
        )
        self.assertEqual(
            {row[2] for row in programs},
            {1},
        )

    def test_minor_graph_includes_legal_representative_and_masks_nis(self):
        extras = {
            "menor16anos": True,
            "representanteLegal": {
                "nome": "RESPONSAVEL TESTE",
                "nis": "98765432100",
                "cpf_mascarado": "***.123.456-**",
            },
        }
        self.adicionar("BPC", "202501", "sem-nis-42", NOME_MENOR_BPC,
                       extras, valor=1518)

        candidates = buscar_pessoas(
            self.con, "2910750", "RESPONSAVEL TESTE", ano=2025)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][0], "sem-nis-42")
        self.assertEqual(candidates[0][2], 1)

        rows = programas_da_pessoa(self.con, "2910750", "sem-nis-42")
        graph = criar_grafo_pessoa("sem-nis-42", rows)
        dot = para_dot(graph)

        self.assertTrue(any(
            data["tipo"] == "representante"
            for _, data in graph.nodes(data=True)
        ))
        self.assertIn("Titular menor de 16 anos", dot)
        self.assertIn("RESPONSAVEL TESTE", dot)
        self.assertNotIn("98765432100", dot)
        self.assertNotIn("sem-nis-42", dot)


if __name__ == "__main__":
    unittest.main()
