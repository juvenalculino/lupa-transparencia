import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import api
from cnpj_dados import (
    criar_grafo_cnpj,
    cruzar_beneficiarios_cnpj,
    importar_csv_cnpj,
    listar_empresas_cnpj,
    obter_cruzamento_beneficiarios_cnpj,
    salvar_registros_cnpj,
    resumir_beneficios_cnpj,
)
from coleta import init_db
from utils.cnpj_municipio import buscar_cnpjs, coletar_dados_municipio


class CnpjDataTests(unittest.TestCase):
    def setUp(self):
        self.con = init_db(":memory:")
        self.con.execute(
            """
            INSERT INTO beneficiario (
                beneficio, mes_ano, codigo_ibge, nis, nome,
                cpf_mascarado, valor
            ) VALUES
                ('Novo Bolsa Familia', '202501', '2910750', '11111111111',
                 'JOAO DA SILVA', '***.123.456-**', 600),
                ('BPC', '202502', '2910750', '11111111111',
                 'João da Silva', '***.123.456-**', 800),
                ('PETI', '202503', '2910750', '11111111111',
                 'João da Silva', NULL, 0),
                ('Novo Bolsa Familia', '202501', '2910750', '22222222222',
                 'JOAO DA SILVA', '***.654.321-**', 500),
                ('Novo Bolsa Familia', '202501', '2910750', '33333333333',
                 'MARIA DE SOUZA', '***.123.456-**', 500)
            """
        )

    def tearDown(self):
        self.con.close()

    def test_match_requires_normalized_name_and_visible_cpf_digits(self):
        records = [
            self._record(
                "11111111000111", "João da Silva", "***123456**", "PF"),
            self._record(
                "22222222000122", "JOAO DA SILVA", "***999999**", "PF"),
            self._record(
                "33333333000133", "MARIA DE SOUZA", "12345678", "PJ"),
        ]
        records[0]["capital_social"] = 123456.78
        salvar_registros_cnpj(
            self.con, records, "2910750", "Fátima", "BA", "teste")

        resultado = obter_cruzamento_beneficiarios_cnpj(
            self.con, "2910750", detalhado=True)

        self.assertEqual(resultado["empresas"], 3)
        self.assertEqual(resultado["socios"], 3)
        self.assertEqual(resultado["beneficiarios_com_cnpj"], 1)
        pessoa = resultado["resultados"][0]
        self.assertEqual(pessoa["nome"], "JOAO DA SILVA")
        self.assertEqual(
            pessoa["programas"], ["BPC", "Novo Bolsa Familia", "PETI"])
        self.assertEqual(
            pessoa["beneficios"],
            [
                {"programa": "BPC", "competencia": "202502", "valor": 800.0},
                {
                    "programa": "Novo Bolsa Familia",
                    "competencia": "202501",
                    "valor": 600.0,
                },
                {"programa": "PETI", "competencia": "202503", "valor": 0.0},
            ],
        )
        self.assertEqual(pessoa["empresas"][0]["cnpj"], "11111111000111")
        self.assertEqual(
            pessoa["empresas"][0]["capital_social"], 123456.78)
        self.assertEqual(
            pessoa["empresas"][0]["socio_cpf_cnpj_mascarado"],
            "***123456**",
        )
        self.assertEqual(pessoa["empresas"][0]["socio_tipo"], "PF")
        self.assertNotIn("nis", pessoa)

    def test_company_status_filter_limits_list_and_detailed_matches(self):
        records = [
            self._record(
                "11111111000111", "João da Silva", "***123456**", "PF"),
            self._record(
                "22222222000122", "João da Silva", "***123456**", "PF"),
            self._record(
                "33333333000133", "João da Silva", "***123456**", "PF"),
        ]
        records[0]["situacao_cadastral"] = "ATIVA"
        records[1]["situacao_cadastral"] = "BAIXADA"
        records[2]["situacao_cadastral"] = "INAPTA"
        salvar_registros_cnpj(
            self.con, records, "2910750", "Fátima", "BA", "teste")

        lista = listar_empresas_cnpj(
            self.con,
            "2910750",
            pagina=1,
            por_pagina=10,
            situacoes_cadastrais=["BAIXADA", "INAPTA"],
        )
        relatorio = obter_cruzamento_beneficiarios_cnpj(
            self.con,
            "2910750",
            detalhado=True,
            situacoes_cadastrais=["BAIXADA"],
        )

        self.assertEqual(lista["total"], 2)
        self.assertEqual(
            {empresa["situacao_cadastral"] for empresa in lista["resultados"]},
            {"BAIXADA", "INAPTA"},
        )
        self.assertEqual(
            lista["situacoes_cadastrais"], ["ATIVA", "BAIXADA", "INAPTA"])
        self.assertEqual(relatorio["empresas"], 1)
        self.assertEqual(relatorio["socios"], 1)
        self.assertEqual(
            [empresa["cnpj"] for pessoa in relatorio["resultados"]
             for empresa in pessoa["empresas"]],
            ["22222222000122"],
        )

    def test_company_filters_and_benefit_program_filter_the_match_section(self):
        records = [
            self._record(
                "11111111000111", "João da Silva", "***123456**", "PF"),
            self._record(
                "22222222000122", "João da Silva", "***123456**", "PF"),
        ]
        records[0]["razao_social"] = "Empresa Ativa"
        records[0]["situacao_cadastral"] = "ATIVA"
        records[0]["capital_social"] = 100
        records[1]["razao_social"] = "Empresa Baixada"
        records[1]["situacao_cadastral"] = "BAIXADA"
        records[1]["capital_social"] = 1000
        salvar_registros_cnpj(
            self.con, records, "2910750", "Fátima", "BA", "teste")
        self.con.execute(
            """
            INSERT INTO beneficiario (
                beneficio, mes_ano, codigo_ibge, nis, nome,
                cpf_mascarado, valor
            ) VALUES (
                'Auxilio Emergencial', '202004', '2910750',
                '11111111111', 'JOAO DA SILVA', '***.123.456-**', 1200
            )
            """
        )

        resultado = obter_cruzamento_beneficiarios_cnpj(
            self.con,
            "2910750",
            detalhado=True,
            busca="baixada",
            capital_min=500,
            capital_max=1500,
            situacoes_cadastrais=["BAIXADA"],
            programa="BPC",
        )

        self.assertEqual(resultado["empresas"], 1)
        self.assertEqual(resultado["beneficiarios_com_cnpj"], 1)
        self.assertEqual(
            resultado["programas_disponiveis"],
            [
                "Auxilio Emergencial",
                "BPC",
                "Novo Bolsa Familia",
                "PETI",
            ],
        )
        pessoa = resultado["resultados"][0]
        self.assertEqual(pessoa["programas"], ["BPC"])
        self.assertEqual(pessoa["periodos"], ["202502"])
        self.assertEqual(
            pessoa["beneficios"],
            [{"programa": "BPC", "competencia": "202502", "valor": 800.0}],
        )
        self.assertEqual(
            [empresa["cnpj"] for empresa in pessoa["empresas"]],
            ["22222222000122"],
        )

    def test_filter_lists_local_programs_and_matches_sacado_alias(self):
        salvar_registros_cnpj(
            self.con,
            [self._record(
                "11111111000111", "João da Silva", "***123456**", "PF")],
            "2910750",
            "Fátima",
            "BA",
            "teste",
        )
        self.con.execute(
            """
            INSERT INTO beneficiario (
                beneficio, mes_ano, codigo_ibge, nis, nome,
                cpf_mascarado, valor
            ) VALUES
                ('Auxilio Brasil (sacado)', '202302', '2910750',
                 '11111111111', 'JOAO DA SILVA', '***.123.456-**', 600),
                ('Garantia Safra', '202302', '2910750',
                 '44444444444', 'ANA COSTA', '***.987.654-**', 500)
            """
        )

        resultado_auxilio = obter_cruzamento_beneficiarios_cnpj(
            self.con, "2910750", programa="Auxilio Brasil")
        resultado_garantia = obter_cruzamento_beneficiarios_cnpj(
            self.con, "2910750", programa="Garantia Safra")

        self.assertIn(
            "Auxilio Brasil (sacado)",
            resultado_auxilio["programas_cadastrados"],
        )
        self.assertIn(
            "Garantia Safra",
            resultado_garantia["programas_cadastrados"],
        )
        self.assertEqual(resultado_auxilio["beneficiarios_com_cnpj"], 1)
        self.assertEqual(
            resultado_auxilio["resultados"][0]["programas"],
            ["Auxilio Brasil (sacado)"],
        )
        self.assertEqual(resultado_garantia["beneficiarios_com_cnpj"], 0)

    def test_pdf_endpoint_forwards_company_and_program_filters(self):
        records = [
            self._record(
                "11111111000111", "João da Silva", "***123456**", "PF"),
            self._record(
                "22222222000122", "João da Silva", "***123456**", "PF"),
        ]
        records[0]["situacao_cadastral"] = "ATIVA"
        records[1]["situacao_cadastral"] = "BAIXADA"
        records[1]["capital_social"] = 200
        salvar_registros_cnpj(
            self.con, records, "2910750", "Fátima", "BA", "teste")
        municipios = [
            {"codigo_ibge": "2910750", "nome": "Fátima", "uf": "BA"},
        ]
        with (
            patch.object(api, "init_db", return_value=self.con),
            patch.object(
                api,
                "carregar_municipios",
                return_value=(municipios, ["BA"]),
            ),
            patch.object(
                api, "gerar_relatorio_cruzamento_pdf", return_value=b"%PDF"
            ) as gerar_pdf,
        ):
            response = api.exportar_relatorio_cruzamento_pdf(
                "2910750",
                "BAIXADA",
                busca="22222222000122",
                capital_min=100,
                capital_max=300,
                programa="BPC",
            )

        dados_pdf = gerar_pdf.call_args.args[3]
        self.assertEqual(response.body, b"%PDF")
        self.assertEqual(gerar_pdf.call_args.args[4], ["BAIXADA"])
        self.assertEqual(
            gerar_pdf.call_args.args[5],
            {
                "busca": "22222222000122",
                "capital_min": 100,
                "capital_max": 300,
                "programa": "BPC",
            },
        )
        self.assertEqual(dados_pdf["empresas"], 1)
        self.assertEqual(
            [empresa["cnpj"] for pessoa in dados_pdf["resultados"]
             for empresa in pessoa["empresas"]],
            ["22222222000122"],
        )

    def test_detailed_pdf_report_contains_all_local_beneficiary_matches(self):
        salvar_registros_cnpj(
            self.con,
            [self._record(
                "11111111000111", "João da Silva", "***123456**", "PF")],
            "2910750",
            "Fátima",
            "BA",
            "teste",
        )
        municipios = [
            {"codigo_ibge": "2910750", "nome": "Fátima", "uf": "BA"},
        ]
        with (
            patch.object(api, "init_db", return_value=self.con),
            patch.object(
                api,
                "carregar_municipios",
                return_value=(municipios, ["BA"]),
            ),
        ):
            response = api.exportar_relatorio_cruzamento_pdf("2910750")

        self.assertEqual(response.media_type, "application/pdf")
        self.assertTrue(response.body.startswith(b"%PDF-"))
        self.assertTrue(response.body.rstrip().endswith(b"%%EOF"))
        self.assertIn(
            "relatorio_beneficiarios_socios_F_tima.pdf",
            response.headers["content-disposition"],
        )

    def test_company_graph_excludes_partners_outside_the_company_limit(self):
        records = [
            self._record(
                "11111111000111", "Sócio Selecionado", "***123456**", "PF"),
            self._record(
                "22222222000122", "Sócio Compartilhado", "***654321**", "PF"),
            self._record(
                "33333333000133", "Sócio Compartilhado", "***654321**", "PF"),
        ]
        records[0]["capital_social"] = 1000
        records[1]["capital_social"] = 200
        records[2]["capital_social"] = 100
        salvar_registros_cnpj(
            self.con, records, "2910750", "Fátima", "BA", "teste")

        grafo = criar_grafo_cnpj(self.con, "2910750", limite=1)

        empresas_no_grafo = {
            node
            for node, atributos in grafo.nodes(data=True)
            if atributos.get("tipo") == "empresa"
        }
        self.assertEqual(empresas_no_grafo, {"11111111000111"})
        self.assertNotIn("22222222000122", grafo)
        self.assertNotIn("33333333000133", grafo)

    def test_pagination_applies_after_distinct_beneficiary_matching(self):
        records = [
            self._record(
                "11111111000111", "João da Silva", "***123456**", "PF"),
            self._record(
                "22222222000122", "JOAO DA SILVA", "***654321**", "PF"),
        ]
        salvar_registros_cnpj(
            self.con, records, "2910750", "Fátima", "BA", "teste")

        first_page = cruzar_beneficiarios_cnpj(
            self.con, "2910750", pagina=1, por_pagina=1)
        second_page = cruzar_beneficiarios_cnpj(
            self.con, "2910750", pagina=2, por_pagina=1)

        self.assertEqual(first_page["beneficiarios_com_cnpj"], 2)
        self.assertEqual(first_page["total_paginas"], 2)
        self.assertEqual(len(first_page["resultados"]), 1)
        self.assertEqual(len(second_page["resultados"]), 1)

    def test_intermunicipal_summary_counts_distinct_people_by_program(self):
        salvar_registros_cnpj(
            self.con,
            [self._record(
                "11111111000111", "João da Silva", "***123456**", "PF")],
            "2910750", "Fátima", "BA", "teste",
        )
        nises = ["11111111111"] + [
            f"444444444{indice:02d}" for indice in range(1, 5)
        ]
        self.con.executemany(
            """
            INSERT INTO beneficiario (
                beneficio, mes_ano, codigo_ibge, nis, nome,
                cpf_mascarado, valor
            ) VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            [
                (
                    "Novo Bolsa Familia", "202504", "2910750",
                    nis, "JOAO DA SILVA", "***.123.456-**",
                )
                for nis in nises[1:]
            ] + [
                (
                    "Novo Bolsa Familia", "202505", "2910751",
                    nis, "JOAO DA SILVA", "***.123.456-**",
                )
                for nis in nises
            ] + [
                (
                    "BPC", "202501", "2910751", "11111111111",
                    "João da Silva", "***123456**",
                ),
            ],
        )

        resumo = resumir_beneficios_cnpj(self.con, "2910750")

        intermunicipais = [
            grupo for grupo in resumo if grupo["codigo_ibge"] == "2910751"
        ]
        self.assertEqual(
            intermunicipais,
            [{
                "codigo_ibge": "2910751",
                "beneficio": "BPC",
                "beneficiarios": 1,
                "periodo_inicial": "202501",
                "periodo_final": "202501",
            }, {
                "codigo_ibge": "2910751",
                "beneficio": "Novo Bolsa Familia",
                "beneficiarios": 5,
                "periodo_inicial": "202505",
                "periodo_final": "202505",
            }],
        )

    def test_imports_the_local_municipality_csv(self):
        caminho = (
            Path(__file__).resolve().parent.parent
            / "utils" / "cnpj_FATIMA_BA.csv"
        )
        resumo = importar_csv_cnpj(
            self.con, caminho, "2910750", "Fátima", "BA")
        repetido = importar_csv_cnpj(
            self.con, caminho, "2910750", "Fátima", "BA")

        self.assertEqual(resumo, {"empresas": 1872, "socios": 598})
        self.assertEqual(repetido, resumo)
        contagem = self.con.execute(
            "SELECT COUNT(*) FROM cnpj_empresa WHERE codigo_ibge='2910750'"
        ).fetchone()[0]
        self.assertEqual(contagem, 1872)

    def test_refuses_csv_rows_from_another_municipality_without_partial_write(self):
        registro = self._record(
            "11111111000111", "João da Silva", "***123456**", "PF")
        registro["municipio"] = "Outro Município"

        with self.assertRaisesRegex(ValueError, "outro município"):
            salvar_registros_cnpj(
                self.con, [registro], "2910750", "Fátima", "BA", "teste")

        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM cnpj_empresa").fetchone()[0],
            0,
        )

    def test_empty_refresh_does_not_delete_saved_municipal_cnpjs(self):
        registro = self._record(
            "11111111000111", "João da Silva", "***123456**", "PF")
        salvar_registros_cnpj(
            self.con, [registro], "2910750", "Fátima", "BA", "teste")

        with self.assertRaisesRegex(ValueError, "lista de CNPJs está vazia"):
            salvar_registros_cnpj(
                self.con, [], "2910750", "Fátima", "BA", "teste",
                substituir_municipio=True,
            )

        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM cnpj_empresa").fetchone()[0],
            1,
        )

    def test_api_import_endpoint_uses_the_bundled_municipal_csv(self):
        request = api.CnpjColetaRequest(codigo_ibge="2910750")
        with (
            patch.object(
                api, "carregar_municipios",
                return_value=([{
                    "codigo_ibge": "2910750",
                    "nome": "Fátima",
                    "uf": "BA",
                }], ["BA"]),
            ),
            patch.object(api, "init_db", side_effect=lambda _: init_db(":memory:")),
        ):
            response = api.importar_csv_municipio_cnpj(request, "admin-token")

        self.assertEqual(response["empresas"], 1872)
        self.assertEqual(response["socios"], 598)
        self.assertEqual(response["origem"], "cnpj_FATIMA_BA.csv")

    def test_intermunicipal_report_suppresses_small_groups_and_personal_data(self):
        grupos = [
            {
                "codigo_ibge": "2805505",
                "beneficio": "Novo Bolsa Familia",
                "beneficiarios": 5,
                "periodo_inicial": "202501",
                "periodo_final": "202505",
            },
            {
                "codigo_ibge": "2805505",
                "beneficio": "BPC",
                "beneficiarios": 4,
                "periodo_inicial": "202501",
                "periodo_final": "202501",
            },
        ]
        municipios = [
            {"codigo_ibge": "2910750", "nome": "Fátima", "uf": "BA"},
            {"codigo_ibge": "2805505", "nome": "Aracaju", "uf": "SE"},
        ]
        with (
            patch.object(api, "init_db", side_effect=lambda _: init_db(":memory:")),
            patch.object(api, "carregar_municipios", return_value=(municipios, ["BA", "SE"])),
            patch.object(api, "resumir_beneficios_cnpj", return_value=grupos),
        ):
            resumo = api.consultar_beneficios_cnpj("2910750")
            response = api.exportar_relatorio_cnpj("2910750")

        self.assertEqual(resumo, [{
            **grupos[0],
            "municipio": "Aracaju",
            "uf": "SE",
        }])
        conteudo = response.body.decode("utf-8-sig")
        self.assertIn("Novo Bolsa Familia", conteudo)
        self.assertNotIn("BPC", conteudo)
        self.assertNotIn("JOAO DA SILVA", conteudo)
        self.assertNotIn("11111111111", conteudo)

    def test_cnpj_progress_callback_updates_status_and_completes(self):
        previous_status = api._status_cnpj
        api._status_cnpj = {
            "codigo_ibge": "2805505",
            "inicio": time.monotonic(),
            "concluido": False,
        }
        con = init_db(":memory:")
        status_final = None

        def fake_coletar(uf, municipio, cache_dir, on_progress):
            on_progress({
                "etapa": "listando",
                "empresas": 1,
                "total": 1,
                "mensagem": "Lista municipal: 1 empresa encontrada",
            })
            return [{"cnpj": "12345678000199", "brasilapi_status": 200}]

        try:
            with (
                patch.object(
                    api, "coletar_dados_municipio",
                    side_effect=fake_coletar,
                ),
                patch.object(api, "init_db", return_value=con),
                patch.object(
                    api, "salvar_registros_cnpj",
                    return_value={"empresas": 1, "socios": 0},
                ),
            ):
                api._executar_coleta_cnpj("2805505", "Poço Verde", "SE")
                status_final = api._status_cnpj.copy()
        finally:
            api._status_cnpj = previous_status

        self.assertEqual(status_final["etapa"], "concluida")
        self.assertEqual(status_final["empresas"], 1)
        self.assertEqual(status_final["total"], 1)

    def test_downloader_reuses_ascii_cache_name_and_returns_database_rows(self):
        empresa = {
            "cnpj": "11111111000111",
            "razao_social": "EMPRESA TESTE",
            "situacao_cadastral": {"situacao_atual": "ATIVA"},
        }
        brasilapi = {
            "brasilapi_status": 200,
            "qsa": [{
                "nome": "JOAO DA SILVA",
                "cpf_cnpj_mascarado": "***123456**",
                "qualificacao": "Sócio",
                "tipo": "PF",
                "data_entrada": "2020-01-01",
                "faixa_etaria": "41 a 50 anos",
            }],
        }
        with TemporaryDirectory() as cache_dir:
            with (
                patch(
                    "utils.cnpj_municipio.buscar_cnpjs",
                    return_value=[empresa],
                ) as buscar,
                patch(
                    "utils.cnpj_municipio.enriquecer",
                    return_value=brasilapi,
                ),
            ):
                registros = coletar_dados_municipio(
                    "ba", "Fátima", cache_dir)

            self.assertEqual(
                buscar.call_args.args,
                ("BA", "FATIMA", str(Path(cache_dir) / "cnpj_FATIMA_BA.checkpoint.json")),
            )
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["socio_nome"], "JOAO DA SILVA")
        self.assertEqual(registros[0]["socio_tipo"], "PF")
        self.assertEqual(registros[0]["municipio"], "FATIMA")

    def test_downloader_reports_estimated_total_across_pages(self):
        respostas = [
            {"total": 3, "cnpjs": [{"cnpj": "00000000000001"}, {"cnpj": "00000000000002"}]},
            {"total": 1, "cnpjs": [{"cnpj": "00000000000003"}]},
            {"total": 0, "cnpjs": []},
        ]
        progressos = []
        with TemporaryDirectory() as cache_dir:
            checkpoint = Path(cache_dir) / "cnpj_POCO VERDE_SE.checkpoint.json"
            with (
                patch("utils.cnpj_municipio.post_casa", side_effect=respostas),
                patch("utils.cnpj_municipio.time.sleep"),
            ):
                empresas = buscar_cnpjs(
                    "SE", "POCO VERDE", str(checkpoint),
                    on_progress=progressos.append,
                )

        self.assertEqual(len(empresas), 3)
        self.assertEqual(
            [progresso["total"] for progresso in progressos],
            [3, 3, 3],
        )

    @staticmethod
    def _record(cnpj, socio_nome, cpf_mascarado, tipo):
        return {
            "cnpj": cnpj,
            "razao_social": f"Empresa {cnpj}",
            "situacao_cadastral": "ATIVA",
            "municipio": "FATIMA",
            "uf": "BA",
            "socio_nome": socio_nome,
            "socio_cpf_cnpj_mascarado": cpf_mascarado,
            "socio_qualificacao": "Sócio",
            "socio_tipo": tipo,
        }


if __name__ == "__main__":
    unittest.main()
