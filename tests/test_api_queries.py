import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import api
from coleta import init_db, meses_validos_ano


class ApiQueryTests(unittest.TestCase):
    def setUp(self):
        self.con = init_db(":memory:")
        for index in range(110):
            self.con.execute(
                """
                INSERT INTO beneficiario
                    (beneficio, mes_ano, codigo_ibge, nis, nome, valor)
                VALUES (?, '202501', '2910750', ?, ?, 100)
                """,
                (
                    "Novo Bolsa Familia (sacado)",
                    f"{index:011d}",
                    f"BENEFICIARIO {index:03d}",
                ),
            )
        self.con.execute(
            """
            INSERT INTO beneficiario
                (beneficio, mes_ano, codigo_ibge, nis, nome, valor)
            VALUES ('Novo Bolsa Familia (sacado)', '202501', '2910751',
                    '99999999999', 'OUTRO MUNICIPIO', 100)
            """
        )

    def tearDown(self):
        self.con.close()

    def test_beneficiary_pages_filter_by_exact_municipality_and_program_alias(self):
        page, total = api.carregar_dados_beneficiarios(
            self.con,
            "Novo Bolsa Familia",
            "2025",
            "2910750",
            "Todos",
            pagina=2,
            por_pagina=25,
        )

        self.assertEqual(total, 110)
        self.assertEqual(len(page), 25)
        self.assertTrue(page["programa"].eq("Novo Bolsa Familia (sacado)").all())
        self.assertNotIn("OUTRO MUNICIPIO", page["nome"].tolist())

    def test_search_and_period_filters_are_applied_before_pagination(self):
        self.con.execute(
            """
            INSERT INTO beneficiario
                (beneficio, mes_ano, codigo_ibge, nis, nome, valor)
            VALUES ('Novo Bolsa Familia (sacado)', '202401', '2910750',
                    '12345678900', 'MARIA DA SILVA', 100)
            """
        )

        page, total = api.carregar_dados_beneficiarios(
            self.con,
            "Novo Bolsa Familia",
            "2024",
            "2910750",
            "01",
            pagina=1,
            por_pagina=25,
            busca="MARIA",
        )

        self.assertEqual(total, 1)
        self.assertEqual(page.iloc[0]["nome"], "MARIA DA SILVA")

        page, total = api.carregar_dados_beneficiarios(
            self.con,
            "Todos",
            "2025",
            "2910750",
            "Todos",
            pagina=1,
            por_pagina=25,
            busca="Bolsa Familia",
        )

        self.assertEqual(total, 110)
        self.assertEqual(len(page), 25)

    def test_beneficiary_dashboard_summary_aggregates_without_returning_rows(self):
        self.con.execute(
            """
            INSERT INTO beneficiario
                (beneficio, mes_ano, codigo_ibge, nis, nome, valor)
            VALUES
                ('Novo Bolsa Familia (sacado)', '202502', '2910750',
                 '00000000001', 'BENEFICIARIO 001', 300),
                ('Novo Bolsa Familia (sacado)', '202502', '2910750',
                 '00000000002', 'BENEFICIARIO 002', 400)
            """
        )

        dados, resumo = api.carregar_resumo_beneficiarios(
            self.con, "Novo Bolsa Familia", "2025", "2910750", "Todos")

        self.assertEqual(len(dados), 2)
        self.assertEqual(resumo, {
            "registros": 112,
            "total_valor": 11_700,
            "total_beneficiados": 110,
            "meses": 2,
        })
        self.assertEqual(dados[0]["valor"], 11_000)
        self.assertEqual(dados[1]["valor"], 700)
        self.assertTrue(all(
            item["programa"] == "Novo Bolsa Familia (sacado)"
            for item in dados
        ))

    def test_beneficiary_summary_keeps_program_series_separate(self):
        self.con.execute(
            """
            INSERT INTO beneficiario (
                beneficio, mes_ano, codigo_ibge, nis, nome, valor
            ) VALUES (
                'BPC', '202501', '2910750', '00000000001',
                'BENEFICIARIO 001', 200
            )
            """
        )

        dados, resumo = api.carregar_resumo_beneficiarios(
            self.con, "Todos", "2025", "2910750", "Todos")

        self.assertEqual(
            [(item["programa"], item["valor"]) for item in dados],
            [
                ("BPC", 200),
                ("Novo Bolsa Familia (sacado)", 11_000),
            ],
        )
        self.assertEqual(resumo["total_valor"], 11_200)
        self.assertEqual(resumo["total_beneficiados"], 110)

    def test_program_year_months_follow_the_supplied_vigence_ranges(self):
        self.assertEqual(meses_validos_ano("Novo Bolsa Familia", 2022), [])
        self.assertEqual(
            meses_validos_ano("Novo Bolsa Familia", 2023),
            [f"{mes:02d}" for mes in range(3, 13)],
        )
        self.assertEqual(
            meses_validos_ano("Auxilio Brasil", 2023), ["01", "02"])
        self.assertEqual(
            meses_validos_ano("Bolsa Familia", 2021),
            [f"{mes:02d}" for mes in range(1, 11)],
        )
        self.assertEqual(
            meses_validos_ano("Auxilio Emergencial", 2021),
            [f"{mes:02d}" for mes in range(1, 11)],
        )
        self.assertEqual(meses_validos_ano("PETI", 2006), [])
        self.assertEqual(
            meses_validos_ano("Seguro Defeso", 1991),
            [f"{mes:02d}" for mes in range(1, 13)],
        )
        self.assertEqual(meses_validos_ano("Garantia Safra", 2001), [])
        self.assertNotIn(
            "Bolsa Familia",
            {item["nome"] for item in api.get_programas_vigentes("2021", "11")},
        )
        self.assertIn(
            "Auxilio Brasil",
            {item["nome"] for item in api.get_programas_vigentes("2023", "02")},
        )
        self.assertNotIn(
            "Auxilio Brasil",
            {item["nome"] for item in api.get_programas_vigentes("2023", "03")},
        )

    def test_download_rejects_program_month_outside_its_vigence(self):
        request = api.ConsultaRequest(
            tipo="Adicionar beneficiários",
            programa="Novo Bolsa Familia",
            uf="BA",
            codigo_ibge="2910750",
            nome_mun="Fátima",
            ano="2022",
            mes="04",
            permitir_novos=True,
        )

        with self.assertRaises(api.HTTPException) as raised:
            api.consultar_dados(request)

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("não estava vigente em 2022", raised.exception.detail)

    def test_downloading_a_full_year_uses_only_valid_program_months(self):
        request = api.ConsultaRequest(
            tipo="Adicionar beneficiários",
            programa="Novo Bolsa Familia",
            uf="BA",
            codigo_ibge="2910750",
            nome_mun="Fátima",
            ano="2023",
            mes="Todos",
            permitir_novos=True,
            api_key="test-key",
        )
        previous_status = api._status_coleta
        try:
            with (
                patch.object(api, "init_db", return_value=self.con),
                patch.object(
                    api, "meses_beneficiarios_faltantes",
                    return_value=[]) as pendentes,
            ):
                api.consultar_dados(request)
        finally:
            api._status_coleta = previous_status

        self.assertEqual(
            pendentes.call_args.args[4],
            [f"{mes:02d}" for mes in range(3, 13)],
        )

    def test_exact_municipality_filter_uses_existing_composite_index(self):
        where, values = api._filtros_consulta(
            "Novo Bolsa Familia", "2025", "2910750", "Todos")
        query = (
            "SELECT * FROM beneficiario WHERE "
            f"{where} ORDER BY beneficio, mes_ano, nis LIMIT ? OFFSET ?"
        )
        plan = self.con.execute(
            f"EXPLAIN QUERY PLAN {query}",
            (*values, 100, 0),
        ).fetchall()

        self.assertTrue(any(
            "idx_beneficiario_municipio_programa_mes_nis" in row[3]
            for row in plan
        ))

    def test_collection_status_is_available_without_internal_timer(self):
        previous = api._status_coleta
        api._status_coleta = {
            "mensagem": "Coletando",
            "registros_lidos": 12,
            "paginas_lidas": 2,
            "tempo_decorrido": 1,
            "inicio": 0,
            "concluido": False,
            "erro": None,
        }
        try:
            response = api.status_coleta()
        finally:
            api._status_coleta = previous

        self.assertEqual(response["status"]["registros_lidos"], 12)
        self.assertNotIn("inicio", response["status"])

    def test_cnpj_status_reports_stage_elapsed_without_exposing_timers(self):
        previous = api._status_cnpj
        api._status_cnpj = {
            "codigo_ibge": "2805505",
            "etapa": "enriquecendo",
            "inicio": 10,
            "inicio_etapa": 12,
            "concluido": False,
        }
        try:
            with patch("api.time.monotonic", return_value=15):
                response = api.status_coleta_cnpj("2805505")
        finally:
            api._status_cnpj = previous

        self.assertEqual(response["status"]["tempo_decorrido"], 5)
        self.assertEqual(response["status"]["tempo_etapa"], 3)
        self.assertNotIn("inicio", response["status"])
        self.assertNotIn("inicio_etapa", response["status"])

    def test_active_municipalities_include_saved_data_and_completed_collections(self):
        self.con.execute(
            """
            INSERT INTO beneficio_mensal
                (beneficio, mes_ano, codigo_ibge, valor, qtd_beneficiados,
                 coletado_em)
            VALUES ('BPC', '202501', '2910752', 100, 1, '2025-01-01')
            """
        )
        self.con.execute(
            """
            INSERT INTO coleta_log
                (quando, tipo, beneficio, mes_ano, codigo_ibge)
            VALUES
                ('2025-01-01', 'beneficiario', 'BPC', '202501', '2805505'),
                ('2025-01-01', 'cnpj', 'CNPJ', '2025', '2805501')
            """
        )

        self.assertEqual(
            api._codigos_municipios_com_beneficios(self.con),
            {"2910750", "2910751", "2910752", "2805505"},
        )

    def test_municipalities_endpoint_returns_only_municipalities_with_benefit_data(self):
        with tempfile.TemporaryDirectory() as directory:
            caminho_db = str(Path(directory) / "beneficios.db")
            con = init_db(caminho_db)
            con.execute(
                """
                INSERT INTO beneficiario
                    (beneficio, mes_ano, codigo_ibge, nis)
                VALUES ('BPC', '202501', '2910750', '00000000001')
                """
            )
            con.commit()
            con.close()

            municipios = [
                {"codigo_ibge": "2910750", "nome": "Fátima", "uf": "BA"},
                {"codigo_ibge": "2805505", "nome": "Poço Verde", "uf": "SE"},
            ]
            with patch.object(api, "DB_PADRAO", caminho_db), patch.object(
                api, "carregar_municipios", return_value=(municipios, ["BA", "SE"])
            ):
                response = api.listar_municipios()

        self.assertEqual(response["municipios"], municipios)
        self.assertEqual(response["ufs"], ["BA", "SE"])
        self.assertEqual(
            response["codigos_municipios_com_dados"],
            [municipios[0]["codigo_ibge"]],
        )
        self.assertEqual(
            response["codigos_municipios_com_beneficiarios"],
            [municipios[0]["codigo_ibge"]],
        )
        self.assertEqual(response["codigos_municipios_com_agregados"], [])


if __name__ == "__main__":
    unittest.main()
