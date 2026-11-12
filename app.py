#!/usr/bin/env python3
"""
Painel de beneficios do Portal da Transparencia — busca inteligente.

Rode com:  streamlit run app.py

Fluxo: escolhe programa + municipio + periodo, clica em Buscar.
O app valida a vigencia do programa, usa o banco se os dados ja existirem
e so acessa a API quando preciso. Resultado aparece na mesma tela.
"""
import os
from datetime import date

import pandas as pd
import streamlit as st
from streamlit_agraph import agraph, Config

from coleta import (
    PROGRAMAS_AGREGADO, PROGRAMAS_BENEFICIARIO,
    PortalClient, carregar_municipios,
    coletar_agregado_ano, coletar_beneficiarios, fmt_mes, init_db,
    meses_agregado_faltantes, meses_beneficiarios_faltantes,
    meses_validos_ano, vigencia_programa,
    rotulo_programa,
)

from rede import (
    buscar_pessoas, calcular_metricas_grafo, criar_grafo_pessoa,
    criar_grafo_programas, mascarar_nis, nx_to_agraph, programas_da_pessoa,
)

st.set_page_config(page_title="Beneficios por Municipio", layout="wide")
st.title("Beneficios por Municipio")

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PADRAO = os.path.join(BASE, "beneficios.db")

MUNICIPIOS, UFS = carregar_municipios(os.path.join(BASE, "dados"))

# ------------------------------------------------------------ Funções auxiliares de carregamento do banco ----

def _mes_ano(ano, mes):
    return f"{int(ano)}{int(mes):02d}"


def carregar_agregado(con, beneficio, ano, codigo_ibge, mes):
    """Carrega dados agregados de um mês específico do banco de dados."""
    rows = con.execute(
        """
        SELECT valor, qtd_beneficiados
        FROM beneficio_mensal
        WHERE mes_ano=? AND beneficio=? AND codigo_ibge=?
        """,
        (_mes_ano(ano, mes), beneficio, codigo_ibge),
    ).fetchall()
    return pd.DataFrame(
        [
            {"mes": int(mes), "valor": valor, "beneficiados": quantidade}
            for valor, quantidade in rows
        ],
        columns=["mes", "valor", "beneficiados"],
    )


def carregar_agregados(con, beneficio, ano, codigo_ibge, meses):
    dados = [
        df for mes in meses
        if not (df := carregar_agregado(
            con, beneficio, ano, codigo_ibge, mes
        )).empty
    ]
    return (
        pd.concat(dados, ignore_index=True)
        if dados
        else pd.DataFrame(columns=["mes", "valor", "beneficiados"])
    )


def carregar_beneficiarios(con, beneficio, ano, codigo_ibge, mes):
    """Carrega dados de beneficiários de um mês específico do banco de dados."""
    rows = con.execute(
        """
        SELECT nis, nome, cpf_mascarado, valor
        FROM beneficiario
        WHERE mes_ano=? AND beneficio=? AND codigo_ibge=?
        """,
        (_mes_ano(ano, mes), beneficio, codigo_ibge),
    ).fetchall()
    return pd.DataFrame(
        [
            {
                "nis": nis,
                "nome": nome,
                "cpf": cpf,
                "valor_saque": valor,
                "mes": int(mes),
                "ano": int(ano),
            }
            for nis, nome, cpf, valor in rows
        ],
        columns=["nis", "nome", "cpf", "valor_saque", "mes", "ano"],
    )


def periodos_disponiveis(con, beneficio, codigo_ibge, tipo):
    tabela = (
        "beneficio_mensal"
        if tipo == "Agregado mensal do ano" else "beneficiario"
    )
    periodos = {}
    if not codigo_ibge:
        return periodos
    for ano_registro, mes in con.execute(
        f"""
        SELECT DISTINCT substr(mes_ano,1,4), substr(mes_ano,5,2)
        FROM {tabela}
        WHERE codigo_ibge=? AND beneficio=?
        ORDER BY 1 DESC, 2
        """,
        (codigo_ibge, beneficio),
    ):
        periodos.setdefault(ano_registro, []).append(mes)
    return periodos


def _anos_validos_programa(beneficio):
    inicio, fim = vigencia_programa(beneficio)
    ano_inicio = int(inicio[:4])
    ano_fim = min(
        int(fim[:4]) if fim else date.today().year,
        date.today().year,
    )
    return [str(ano) for ano in range(ano_fim, ano_inicio - 1, -1)]


# ------------------------------------------------------------ sidebar ----
st.sidebar.title("Configuracao")
chave = st.sidebar.text_input("Chave da API do Portal", type="password",
                              help="Nao fica salva em arquivo.")
db_path = st.sidebar.text_input("Banco SQLite", DB_PADRAO)
con = init_db(db_path)
st.sidebar.caption("Limites da API: 700 req/min (00h-05h59), "
                   "400 req/min (06h-23h59), 180 req/min em endpoints "
                   "restritos. O app usa 95% do limite em horário de Brasília.")

# ------------------------------------------------------------ filtros ----
st.subheader("O que buscar")
tipo = st.radio("Tipo de consulta",
                ["Agregado mensal do ano", "Adicionar beneficiários"],
                horizontal=True, key="tipo", label_visibility="collapsed")

programas = (PROGRAMAS_AGREGADO if tipo == "Agregado mensal do ano"
             else PROGRAMAS_BENEFICIARIO)
rotulos = {rotulo_programa(p): p for p in programas}
rotulo = st.selectbox("Programa", list(rotulos))
beneficio = rotulos[rotulo]
ini, fim = vigencia_programa(beneficio)
st.caption(f"Vigencia do programa: {fmt_mes(ini)} a "
           f"{fmt_mes(fim) if fim else 'atual'}")

c1, c2 = st.columns(2)
with c1:
    uf = st.selectbox("Estado", UFS, key="uf")
    municipios_estado = [m for m in MUNICIPIOS if m["uf"] == uf]
    municipios_por_codigo = {m["codigo_ibge"]: m for m in municipios_estado}
    codigo_municipio = st.selectbox(
        "Buscar município",
        options=list(municipios_por_codigo),
        index=None,
        placeholder="Digite o nome ou código IBGE...",
        format_func=lambda codigo: (
            f'{municipios_por_codigo[codigo]["nome"]} ({codigo})'),
        key=f"municipio_{uf}",
    )
    mun = municipios_por_codigo.get(codigo_municipio)
    st.caption(f"{len(municipios_estado)} municípios disponíveis em {uf}.")

periodos_db = periodos_disponiveis(
    con, beneficio, mun["codigo_ibge"] if mun else None, tipo
)
permitir_novos_periodos = st.checkbox(
    "Incluir competências ainda não salvas (consultar API)",
    value=False,
    key=f"incluir_novos_{tipo}_{beneficio}_{codigo_municipio or 'sem-municipio'}",
    help=(
        "Desmarcado: os filtros mostram somente anos e meses já registrados "
        "para o programa e município. Marque para incluir períodos ainda "
        "não coletados na consulta à API."
    ),
    disabled=not mun,
)

with c2:
    anos_disponiveis = list(periodos_db)
    if permitir_novos_periodos:
        anos_disponiveis = sorted(
            set(anos_disponiveis) | set(_anos_validos_programa(beneficio)),
            reverse=True,
        )
    if anos_disponiveis:
        ano = st.selectbox(
            "Ano disponível",
            options=anos_disponiveis,
            index=0,
            key=(
                f"ano_{tipo}_{beneficio}_"
                f"{codigo_municipio or 'sem-municipio'}_"
                f"{int(permitir_novos_periodos)}"
            ),
        )
        ano = int(ano)
        meses_banco = periodos_db.get(str(ano), [])
        meses_validos = (
            meses_validos_ano(beneficio, ano)
            if permitir_novos_periodos else meses_banco
        )
    else:
        ano = None
        meses_banco = []
        meses_validos = []
        if mun:
            st.info(
                "Ainda não há anos com dados deste programa neste município. "
                "Marque a opção para incluir períodos novos pela API."
            )
    mes = None
    reconsultar_beneficiarios = False
    if tipo == "Agregado mensal do ano":
        modo_meses = st.radio(
            "Meses do ano",
            ["Todos os meses", "Selecionar meses"],
            horizontal=True,
            key="modo_meses_agregado",
        )
        if modo_meses == "Todos os meses":
            meses_consulta = meses_validos
        elif ano is not None:
            meses_consulta = st.multiselect(
                "Escolha um ou mais meses",
                options=meses_validos,
                format_func=lambda valor: f"{valor}/{ano}",
                key=f"meses_agregado_{beneficio}_{ano}",
            )
        else:
            meses_consulta = []
        periodo = modo_meses
    elif ano is not None:
        periodo = st.radio(
            "Período a adicionar",
            ["Um mês", "Ano inteiro"],
            horizontal=True,
            key="periodo_adicionar_beneficiarios",
        )
        if periodo == "Um mês":
            if meses_validos:
                mes = st.selectbox(
                    "Mês",
                    options=meses_validos,
                    format_func=lambda valor: f"{valor}/{ano}",
                    key=f"mes_beneficiario_{beneficio}_{ano}",
                )
                meses_consulta = [mes]
            else:
                meses_consulta = []
        else:
            meses_consulta = meses_validos
        reconsultar_beneficiarios = st.checkbox(
            "Reconsultar meses já coletados",
            key=f"reconsultar_{beneficio}_{ano}",
            help=(
                "Atualiza os registros locais com a resposta atual da API. "
                "Use para preencher os dados do representante legal do BPC "
                "em meses que foram coletados antes desta melhoria."
            ),
        )
    else:
        periodo = "Sem períodos disponíveis"
        meses_consulta = []

# ------------------------------------------------------------ Lógica principal ----
resultado = {}

# Determina se precisamos buscar na API ou se podemos usar o banco
precisa_api = False
motivo_api = ""

if tipo == "Agregado mensal do ano":
    meses_faltantes = meses_agregado_faltantes(
        con, beneficio, ano, mun["codigo_ibge"] if mun else None,
        meses_consulta,
    )
    if meses_faltantes:
        precisa_api = True
        motivo_api = (
            f"Dados do mês {meses_faltantes[0]}/{ano} "
            "não encontrados no banco"
        )
else:  # Adicionar beneficiários
    meses_faltantes = meses_beneficiarios_faltantes(
        con, beneficio, ano, mun["codigo_ibge"] if mun else None,
        meses_consulta,
    )
    if reconsultar_beneficiarios:
        precisa_api = True
        motivo_api = "Reconsultando meses já coletados"
    elif meses_faltantes:
        precisa_api = True
        motivo_api = (
            f"Dados do mês {meses_faltantes[0]}/{ano} "
            "não encontrados no banco"
        )

# Mostra aviso sobre API apenas se realmente precisarmos
if precisa_api and not chave:
    st.warning("⚠️ Insira a chave da API para buscar dados que não estão no banco de dados.")

# Botão de busca
rotulo_botao = ("Buscar agregado" if tipo == "Agregado mensal do ano" else "Adicionar dados do programa")
if st.button(
    rotulo_botao,
    type="primary",
    key="buscar",
    disabled=not mun or not meses_consulta,
):
    if not mun:
        st.warning("Selecione um município para realizar a busca.")
    else:
        if tipo == "Agregado mensal do ano":
            if precisa_api and chave:
                client = PortalClient(chave)
                try:
                    stats = coletar_agregado_ano(
                        client, con, beneficio, ano, mun["codigo_ibge"],
                        mun["nome"], mun["uf"], meses_faltantes,
                    )
                    resultado = {
                        "df": carregar_agregados(
                            con, beneficio, ano, mun["codigo_ibge"],
                            meses_consulta,
                        ),
                        "origem": "api",
                        "meses_existentes": stats["meses_ok"],
                        "meses_atualizados": 0,
                        "registros": stats["meses_ok"],
                    }
                except RuntimeError as error:
                    resultado = {
                        "df": carregar_agregados(
                            con, beneficio, ano, mun["codigo_ibge"],
                            meses_consulta,
                        ),
                        "origem": "banco",
                        "erro": f"Falha ao consultar a API: {error}",
                    }
            elif not precisa_api:
                # Usa apenas o banco de dados
                dfs = []
                for m in meses_consulta:
                    df = carregar_agregado(con, beneficio, ano, mun["codigo_ibge"], m)
                    if not df.empty:
                        dfs.append(df)
                df_result = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
                resultado = {
                    "df": df_result,
                    "origem": "banco",
                    "meses_existentes": len(meses_consulta),
                    "meses_atualizados": 0,
                    "registros": len(df_result)
                }
            else:
                # Precisa da API mas não temos a chave
                resultado = {
                    "erro": "Insira a chave da API para realizar a busca.",
                    "origem": "banco",
                    "df": carregar_agregados(
                        con, beneficio, ano, mun["codigo_ibge"],
                        meses_consulta,
                    ),
                }
        else:  # Adicionar beneficiários
            if precisa_api and chave:
                client = PortalClient(chave)
                total_registros = 0
                meses_atualizados = 0
                meses_adicionados = 0
                meses_para_coletar = (
                    meses_consulta if reconsultar_beneficiarios
                    else meses_faltantes
                )
                try:
                    for m in meses_para_coletar:
                        reg = coletar_beneficiarios(
                            client, con, beneficio, _mes_ano(ano, m),
                            mun["codigo_ibge"], mun["nome"], mun["uf"],
                        )
                        total_registros += reg["registros"]
                        if reconsultar_beneficiarios:
                            meses_atualizados += 1
                        else:
                            meses_adicionados += 1
                    erro_coleta = None
                except RuntimeError as error:
                    erro_coleta = f"Falha ao consultar a API: {error}"

                dfs = [
                    df for m in meses_consulta
                    if not (df := carregar_beneficiarios(
                        con, beneficio, ano, mun["codigo_ibge"], m
                    )).empty
                ]
                resultado = {
                    "origem": "api" if erro_coleta is None else "banco",
                    "registros": total_registros,
                    "meses_atualizados": meses_atualizados,
                    "meses_adicionados": meses_adicionados,
                    "meses_existentes": (
                        len(meses_consulta) - len(meses_faltantes)
                        if not reconsultar_beneficiarios else 0
                    ),
                    "df": pd.concat(dfs, ignore_index=True)
                    if dfs else pd.DataFrame(),
                }
                if erro_coleta:
                    resultado["erro"] = erro_coleta
            elif not precisa_api:
                # Usa apenas o banco de dados
                dfs = []
                for m in meses_consulta:
                    df = carregar_beneficiarios(con, beneficio, ano, mun["codigo_ibge"], m)
                    if not df.empty:
                        dfs.append(df)
                df_result = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
                resultado = {
                    "df": df_result,
                    "origem": "banco",
                    "meses_existentes": len(meses_consulta),
                    "meses_atualizados": 0,
                    "meses_adicionados": 0,
                    "registros": len(df_result)
                }
            else:
                # Precisa da API mas não temos a chave
                dfs = [
                    df for m in meses_consulta
                    if not (df := carregar_beneficiarios(
                        con, beneficio, ano, mun["codigo_ibge"], m
                    )).empty
                ]
                resultado = {
                    "erro": "Insira a chave da API para realizar a busca.",
                    "origem": "banco",
                    "df": pd.concat(dfs, ignore_index=True)
                    if dfs else pd.DataFrame(),
                }

        resultado.update({
            "codigo_ibge": mun["codigo_ibge"],
            "beneficio": beneficio,
            "tipo": tipo,
            "ano": int(ano),
            "periodo": periodo,
            "meses_consulta": tuple(meses_consulta),
            "reconsultar_beneficiarios": reconsultar_beneficiarios,
        })
        st.session_state.resultado = resultado

# ---------------------------------------------------------- resultados ----
r = st.session_state.get("resultado")
resultado_valido = bool(
    r and mun and ano is not None and all((
        r.get("codigo_ibge") == mun["codigo_ibge"],
        r.get("beneficio") == beneficio,
        r.get("tipo") == tipo,
        r.get("ano") == int(ano),
        r.get("periodo") == periodo,
        r.get("meses_consulta") == tuple(meses_consulta),
        r.get("reconsultar_beneficiarios", False)
        == reconsultar_beneficiarios,
    ))
)

if not resultado_valido:
    st.info("Selecione filtros com dados disponíveis e clique em Buscar.")
elif tipo == "Agregado mensal do ano":
    if r.get("erro"):
        st.error(r["erro"])
    st.caption(
        f"{beneficio} — {mun['nome']}/{mun['uf']} — {ano} "
        f"({len(meses_consulta)} competência(s))"
    )
    df = r.get("df")
    if df is None:
        df = carregar_agregados(
            con, beneficio, ano, mun["codigo_ibge"], meses_consulta
        )
    if r.get("origem") == "banco" and st.button(
        "Atualizar dados da API",
        key=f"atualizar_agregado_{mun['codigo_ibge']}_{beneficio}_{ano}",
    ):
        if not chave:
            st.error("Informe a chave da API para atualizar os dados.")
        else:
            try:
                coletar_agregado_ano(
                    PortalClient(chave), con, beneficio, ano,
                    mun["codigo_ibge"], mun["nome"], mun["uf"],
                    meses_consulta, sobrescrever=True,
                )
            except RuntimeError as error:
                st.error(f"Falha ao consultar a API: {error}")
            else:
                r["df"] = carregar_agregados(
                    con, beneficio, ano, mun["codigo_ibge"], meses_consulta
                )
                r["origem"] = "api"
                st.session_state.resultado = r
                st.rerun()
    if df.empty:
        st.info("Não há dados agregados para as competências selecionadas.")
    else:
        k1, k2, k3 = st.columns(3)
        k1.metric("Meses com dados", len(df))
        k2.metric("Valor total", f"R$ {df['valor'].sum():,.2f}")
        k3.metric(
            "Beneficiados (soma mensal)",
            f"{int(df['beneficiados'].sum()):,}",
        )
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Valor por mês (R$)")
            st.line_chart(df.set_index("mes")["valor"])
        with c2:
            st.subheader("Beneficiados por mês")
            st.bar_chart(df.set_index("mes")["beneficiados"])
        st.dataframe(df, width="stretch", hide_index=True)
        st.download_button(
            "Baixar CSV",
            df.to_csv(index=False).encode("utf-8"),
            f"{beneficio}_{ano}_{mun['codigo_ibge']}.csv",
            "text/csv",
        )
else:
    if r.get("erro"):
        st.error(r["erro"])
    st.caption(
        f"{beneficio} — {mun['nome']}/{mun['uf']} — {ano} "
        f"({len(meses_consulta)} competência(s))"
    )
    if not r.get("erro") and r.get("origem") == "banco":
        st.info(
            f"Dados carregados do banco: {r.get('registros', 0):,} registro(s)."
        )
    elif not r.get("erro"):
        st.success(
            f"Consulta concluída: {r.get('registros', 0):,} registro(s) "
            f"em {len(meses_consulta)} competência(s)."
        )
    df = r.get("df", pd.DataFrame())
    if df.empty:
        st.info("Não há beneficiários para as competências selecionadas.")
    else:
        st.subheader(f"Beneficiários de {beneficio}")
        st.dataframe(df, width="stretch", hide_index=True)
        st.download_button(
            "Baixar CSV",
            df.to_csv(index=False).encode("utf-8"),
            f"{beneficio}_{ano}_{mun['codigo_ibge']}.csv",
            "text/csv",
        )

        aba_programas, aba_pessoa = st.tabs([
            "Programas com beneficiários em comum",
            "Grafo de uma pessoa",
        ])
        with aba_programas:
            grafo_programas = criar_grafo_programas(
                con, mun["codigo_ibge"], ano, meses_consulta
            )
            if grafo_programas.number_of_nodes() == 0:
                st.info(
                    "Não há NIS identificados nos programas deste município "
                    "e período para montar o grafo."
                )
            else:
                nodes, edges = nx_to_agraph(grafo_programas)
                agraph(
                    nodes=nodes,
                    edges=edges,
                    config=Config(
                        width=900,
                        height=650,
                        directed=False,
                        physics=True,
                        hierarchical=False,
                    ),
                )
                metricas = calcular_metricas_grafo(grafo_programas)
                m1, m2, m3 = st.columns(3)
                m1.metric("Programas", metricas["nos"])
                m2.metric("Ligações", metricas["arestas"])
                m3.metric("Densidade", f"{metricas['densidade']:.3f}")
                if metricas["arestas"] == 0:
                    st.caption(
                        "Os programas aparecem sem ligações quando não há "
                        "NIS em comum nos registros desse período."
                    )

        with aba_pessoa:
            termo = st.text_input(
                "Buscar beneficiário por nome ou NIS",
                key=(
                    f"busca_grafo_{mun['codigo_ibge']}_{beneficio}_"
                    f"{ano}_{'-'.join(meses_consulta)}"
                ),
                placeholder="Digite pelo menos dois caracteres...",
            )
            candidatos = buscar_pessoas(
                con, mun["codigo_ibge"], termo, ano, meses_consulta
            ) if len(termo.strip()) >= 2 else []
            if len(termo.strip()) < 2:
                st.info("Digite pelo menos dois caracteres para buscar.")
            elif not candidatos:
                st.info("Nenhum beneficiário corresponde a essa busca.")
            else:
                opcoes = {
                    pessoa[0]: (
                        f'{pessoa[1] or ("Titular menor de 16 anos" if pessoa[2] else "Titular sem nome informado")} '
                        f'({mascarar_nis(pessoa[0])}; '
                        f'{pessoa[3]} programa(s))'
                    )
                    for pessoa in candidatos
                }
                nis = st.selectbox(
                    "Pessoa encontrada",
                    list(opcoes),
                    format_func=lambda item: opcoes[item],
                    key=(
                        f"pessoa_grafo_{mun['codigo_ibge']}_{beneficio}_"
                        f"{ano}_{'-'.join(meses_consulta)}"
                    ),
                )
                dados_pessoa = programas_da_pessoa(
                    con, mun["codigo_ibge"], nis, ano, meses_consulta
                )
                nome = next(
                    (pessoa[1] for pessoa in candidatos if pessoa[0] == nis),
                    None,
                )
                grafo_pessoa = criar_grafo_pessoa(
                    nis, dados_pessoa, nome_pessoa=nome
                )
                nodes, edges = nx_to_agraph(grafo_pessoa)
                if nodes:
                    agraph(
                        nodes=nodes,
                        edges=edges,
                        config=Config(
                            width=900,
                            height=650,
                            directed=False,
                            physics=True,
                            hierarchical=False,
                        ),
                    )
                    st.caption(
                        "Os vínculos refletem apenas registros encontrados; "
                        "não comprovam parentesco ou residência conjunta."
                    )
                else:
                    st.info("Não há relações registradas para essa pessoa.")

if mun:
    st.divider()
    st.subheader("Buscar beneficiário em qualquer programa")
    st.caption(
        f"A busca considera todos os programas e anos já salvos para "
        f"{mun['nome']}/{mun['uf']}, independentemente dos filtros acima."
    )
    termo_global = st.text_input(
        "Nome ou NIS do beneficiário",
        key=f"busca_global_beneficiario_{mun['codigo_ibge']}",
        placeholder="Digite pelo menos dois caracteres...",
    )
    if len(termo_global.strip()) < 2:
        st.info("Digite pelo menos dois caracteres para pesquisar.")
    else:
        candidatos_globais = buscar_pessoas(
            con, mun["codigo_ibge"], termo_global
        )
        if not candidatos_globais:
            st.info(
                "Nenhum beneficiário encontrado nos programas já salvos "
                "para este município."
            )
        else:
            opcoes_globais = {
                pessoa[0]: (
                    f'{pessoa[1] or ("Titular menor de 16 anos" if pessoa[2] else "Titular sem nome informado")} '
                    f'({mascarar_nis(pessoa[0])}; '
                    f'{pessoa[3]} programa(s))'
                )
                for pessoa in candidatos_globais
            }
            nis_global = st.selectbox(
                "Beneficiário encontrado",
                list(opcoes_globais),
                format_func=lambda item: opcoes_globais[item],
                key=f"beneficiario_global_{mun['codigo_ibge']}",
            )
            if len(candidatos_globais) == 100:
                st.caption(
                    "Exibindo até 100 resultados. Refine pelo nome completo "
                    "ou NIS para localizar outras correspondências."
                )

            programas_globais = programas_da_pessoa(
                con, mun["codigo_ibge"], nis_global
            )
            nome_global = next(
                (
                    pessoa[1] for pessoa in candidatos_globais
                    if pessoa[0] == nis_global
                ),
                None,
            )
            candidato_selecionado = next(
                pessoa for pessoa in candidatos_globais
                if pessoa[0] == nis_global
            )
            tabela_programas = pd.DataFrame(
                [
                    {
                        "Programa": linha[0],
                        "Competências encontradas": linha[1],
                        "Anos encontrados": linha[2],
                        "Total registrado (R$)": linha[3] or 0,
                    }
                    for linha in programas_globais
                ],
                columns=[
                    "Programa", "Competências encontradas",
                    "Anos encontrados", "Total registrado (R$)",
                ],
            )
            st.markdown(
                f"**{nome_global or ('Titular menor de 16 anos' if candidato_selecionado[2] else 'Titular sem nome informado')}** — "
                f"{len(programas_globais)} programa(s) encontrado(s)"
            )
            st.dataframe(
                tabela_programas,
                width="stretch",
                hide_index=True,
            )
            grafo_global = criar_grafo_pessoa(
                nis_global, programas_globais, nome_pessoa=nome_global
            )
            nos_globais, arestas_globais = nx_to_agraph(grafo_global)
            if nos_globais:
                agraph(
                    nodes=nos_globais,
                    edges=arestas_globais,
                    config=Config(
                        width=900,
                        height=650,
                        directed=False,
                        physics=True,
                        hierarchical=False,
                    ),
                )
            st.caption(
                "O grafo reúne registros vinculados pelo mesmo NIS. "
                "A presença em programas não comprova parentesco ou "
                "residência conjunta."
            )
