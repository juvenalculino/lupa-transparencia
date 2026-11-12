"""Consultas e modelos de grafos para exploração dos dados locais."""

import hashlib
from itertools import combinations
import json

import networkx as nx

NOME_MENOR_BPC = "*** TITULAR MENOR DE 16 ANOS ***"


def _ano_sql(ano):
    return str(ano) if ano is not None else None


def mascarar_nis(nis):
    if not nis or nis.startswith("sem-nis-"):
        return "NIS não informado"
    return f"NIS ***{nis[-4:]}"


def _id_no(tipo, identificador):
    digest = hashlib.sha256(identificador.encode("utf-8")).hexdigest()[:16]
    return f"{tipo}_{digest}"


def anos_beneficiarios(con, codigo_ibge):
    return [
        row[0]
        for row in con.execute(
            """
            SELECT DISTINCT substr(mes_ano,1,4)
            FROM beneficiario
            WHERE codigo_ibge=?
            ORDER BY substr(mes_ano,1,4) DESC
            """,
            (codigo_ibge,),
        )
    ]


def _filtro_periodo(meses=None):
    if not meses:
        return "", ()
    placeholders = ",".join("?" for _ in meses)
    return f" AND substr(mes_ano,5,2) IN ({placeholders})", tuple(meses)


def buscar_pessoas(con, codigo_ibge, termo, ano=None, meses=None, limite=100):
    """Busca titulares pelo nome/NIS e preserva homônimos com NIS distinto."""
    termo = termo.strip()
    if len(termo) < 2:
        return []
    filtro_mes, parametros_mes = _filtro_periodo(meses)
    return con.execute(
        f"""
        SELECT nis,
               MAX(CASE WHEN nome != ? THEN NULLIF(nome, '') END) AS nome,
               MAX(CASE WHEN json_extract(extras, '$.menor16anos') = 1
                          OR nome = ? THEN 1 ELSE 0 END) AS menor,
               COUNT(DISTINCT beneficio) AS quantidade_programas
        FROM beneficiario
        WHERE codigo_ibge=?
          AND (? IS NULL OR substr(mes_ano,1,4)=?)
          {filtro_mes}
          AND (
              instr(lower(COALESCE(nome, '')), lower(?)) > 0
              OR instr(nis, ?) > 0
              OR instr(lower(COALESCE(json_extract(
                  extras, '$.representanteLegal.nome'), '')), lower(?)) > 0
              OR instr(COALESCE(json_extract(
                  extras, '$.representanteLegal.nis'), ''), ?) > 0
          )
        GROUP BY nis
        ORDER BY nome, nis
        LIMIT ?
        """,
        (
            NOME_MENOR_BPC, NOME_MENOR_BPC, codigo_ibge,
            _ano_sql(ano), _ano_sql(ano),
            *parametros_mes, termo, termo, termo, termo, limite,
        ),
    ).fetchall()


def programas_da_pessoa(con, codigo_ibge, nis, ano=None, meses=None):
    """Resume competências, valores e representante por programa."""
    filtro_mes, parametros_mes = _filtro_periodo(meses)
    return con.execute(
        f"""
        SELECT beneficio,
               COUNT(DISTINCT mes_ano) AS quantidade_meses,
               COUNT(DISTINCT substr(mes_ano,1,4)) AS quantidade_anos,
               SUM(valor) AS valor_total,
               MAX(CASE WHEN json_extract(extras, '$.menor16anos') = 1
                          OR nome = ? THEN 1 ELSE 0 END) AS menor,
               MAX(json_extract(
                   extras, '$.representanteLegal.nome')) AS representante_nome,
               MAX(json_extract(
                   extras, '$.representanteLegal.nis')) AS representante_nis,
               MAX(json_extract(
                   extras, '$.representanteLegal.cpf_mascarado'))
                   AS representante_cpf
        FROM beneficiario
        WHERE codigo_ibge=? AND nis=?
          AND (? IS NULL OR substr(mes_ano,1,4)=?)
          {filtro_mes}
        GROUP BY beneficio
        ORDER BY beneficio
        """,
        (
            NOME_MENOR_BPC, codigo_ibge, nis, _ano_sql(ano), _ano_sql(ano),
            *parametros_mes,
        ),
    ).fetchall()


def vizinhos_por_programas(con, codigo_ibge, nis, programas, ano=None,
                           meses=None, limite=12):
    if not programas:
        return []
    filtro_mes, parametros_mes = _filtro_periodo(meses)
    marcadores = ",".join("?" for _ in programas)
    return con.execute(
        f"""
        WITH base AS (
            SELECT nis, beneficio,
                   MAX(CASE WHEN nome != ?
                            THEN NULLIF(nome, '') END) AS nome,
                   MAX(CASE WHEN json_extract(extras, '$.menor16anos') = 1
                              OR nome = ? THEN 1 ELSE 0 END) AS menor
            FROM beneficiario
            WHERE codigo_ibge=?
              AND (? IS NULL OR substr(mes_ano,1,4)=?)
              {filtro_mes}
              AND nis NOT LIKE 'sem-nis-%'
            GROUP BY nis, beneficio
        ),
        vizinhos AS (
            SELECT nis, COUNT(DISTINCT beneficio) AS compartilhados
            FROM base
            WHERE beneficio IN ({marcadores}) AND nis != ?
            GROUP BY nis
            ORDER BY compartilhados DESC, nis
            LIMIT ?
        )
        SELECT base.nis, base.nome, base.menor, base.beneficio,
               vizinhos.compartilhados
        FROM base
        JOIN vizinhos ON vizinhos.nis=base.nis
        ORDER BY vizinhos.compartilhados DESC, base.nome, base.beneficio
        """,
        (
            NOME_MENOR_BPC, NOME_MENOR_BPC, codigo_ibge,
            _ano_sql(ano), _ano_sql(ano),
            *parametros_mes, *programas, nis, limite,
        ),
    ).fetchall()


def criar_grafo_pessoa(nis, dados_programas, vizinhos=(), nome_pessoa=None):
    grafo = nx.Graph()
    if not dados_programas:
        return grafo
    menor = any(row[4] for row in dados_programas)
    nome_pessoa = nome_pessoa or (
        "Titular menor de 16 anos"
        if menor else "Titular sem nome informado"
    )
    id_pessoa = _id_no("pessoa", nis)
    grafo.add_node(
        id_pessoa,
        tipo="pessoa",
        label=f"{nome_pessoa}\n{mascarar_nis(nis)}",
        tooltip=f"{nome_pessoa} — {mascarar_nis(nis)}",
    )

    representantes = set()
    for (
        beneficio, meses, anos, valor, _, rep_nome, rep_nis, rep_cpf
    ) in dados_programas:
        id_programa = _id_no("programa", beneficio)
        grafo.add_node(
            id_programa,
            tipo="programa",
            label=beneficio,
            tooltip=f"{beneficio}: {meses} competência(s), {anos} ano(s)",
        )
        detalhes = f"{meses} mês(es) · {anos} ano(s)"
        if valor is not None:
            detalhes += f" · R$ {valor:,.2f}"
        grafo.add_edge(
            id_pessoa, id_programa, relacao="recebe", label=detalhes
        )
        if rep_nome or rep_nis or rep_cpf:
            identidade = rep_nis or rep_cpf or rep_nome
            id_representante = _id_no("representante", identidade)
            if id_representante not in representantes:
                nome_representante = rep_nome or "Representante legal"
                grafo.add_node(
                    id_representante,
                    tipo="representante",
                    label=(
                        f"{nome_representante}\n"
                        f"{mascarar_nis(rep_nis or '')}"
                    ),
                    tooltip=(
                        f"{nome_representante}; NIS: "
                        f"{mascarar_nis(rep_nis or '')}; "
                        f"CPF: {rep_cpf or 'não informado'}"
                    ),
                )
                representantes.add(id_representante)
            grafo.add_edge(
                id_pessoa, id_representante,
                relacao="representante legal", label="representa",
            )

    for nis_vizinho, nome, vizinho_menor, beneficio, compartilhados in vizinhos:
        id_vizinho = _id_no("pessoa", nis_vizinho)
        nome_vizinho = nome or (
            "Titular menor de 16 anos" if vizinho_menor
            else "Titular sem nome informado"
        )
        grafo.add_node(
            id_vizinho,
            tipo="pessoa_relacionada",
            label=f"{nome_vizinho}\n{mascarar_nis(nis_vizinho)}",
            tooltip=(
                f"{nome_vizinho} — {mascarar_nis(nis_vizinho)}; "
                f"compartilha {compartilhados} programa(s)"
            ),
        )
        id_programa = _id_no("programa", beneficio)
        if id_programa in grafo:
            grafo.add_edge(
                id_vizinho, id_programa,
                relacao="programa em comum", label="mesmo programa",
            )
    return grafo


def calcular_metricas_grafo(grafo):
    return {
        "nos": grafo.number_of_nodes(),
        "arestas": grafo.number_of_edges(),
        "densidade": nx.density(grafo) if grafo.number_of_nodes() > 1 else 0.0,
    }


def format_metricas_para_exibicao(metricas):
    return {
        "Nós": metricas.get("nos", 0),
        "Arestas": metricas.get("arestas", 0),
        "Densidade": f"{metricas.get('densidade', 0):.3f}",
    }


def criar_grafo_programas(con, codigo_ibge, ano=None, meses=None,
                          minimo_compartilhados=1):
    """Liga programas quando um NIS válido aparece nos dois registros."""
    filtro_mes, parametros_mes = _filtro_periodo(meses)
    associacoes = con.execute(
        f"""
        SELECT DISTINCT beneficio, nis
        FROM beneficiario
        WHERE codigo_ibge=?
          AND nis NOT LIKE 'sem-nis-%'
          AND (? IS NULL OR substr(mes_ano,1,4)=?)
          {filtro_mes}
        """,
        (codigo_ibge, _ano_sql(ano), _ano_sql(ano), *parametros_mes),
    ).fetchall()
    pessoas_por_programa = {}
    programas_por_pessoa = {}
    for beneficio, nis in associacoes:
        pessoas_por_programa[beneficio] = (
            pessoas_por_programa.get(beneficio, 0) + 1
        )
        programas_por_pessoa.setdefault(nis, set()).add(beneficio)

    compartilhados = {}
    for programas in programas_por_pessoa.values():
        for a, b in combinations(sorted(programas), 2):
            compartilhados[(a, b)] = compartilhados.get((a, b), 0) + 1

    grafo = nx.Graph()
    for beneficio, pessoas in sorted(pessoas_por_programa.items()):
        grafo.add_node(
            _id_no("programa", beneficio),
            tipo="programa",
            label=f"{beneficio}\n{pessoas:,} NIS identificados",
            tooltip=f"{beneficio}: {pessoas:,} NIS distintos",
            pessoas=pessoas,
        )
    for (a, b), quantidade in sorted(
        compartilhados.items(), key=lambda item: (-item[1], item[0])
    ):
        if quantidade < minimo_compartilhados:
            continue
        grafo.add_edge(
            _id_no("programa", a),
            _id_no("programa", b),
            peso=quantidade,
            label=f"{quantidade:,} NIS em comum",
            tooltip=f"{quantidade:,} NIS em ambos os programas",
        )
    return grafo


def para_dot(grafo):
    """Serializa um grafo em DOT, sem expor identificadores originais."""
    linhas = [
        "graph rede {",
        '  graph [layout="sfdp", overlap="false", splines="true", '
        'bgcolor="transparent"];',
        '  node [style="filled", fontname="sans-serif", fontsize="10"];',
        '  edge [fontname="sans-serif", fontsize="8", color="#64748b"];',
    ]
    cores = {
        "pessoa": "#bfdbfe",
        "pessoa_relacionada": "#e0f2fe",
        "programa": "#bbf7d0",
        "representante": "#fef3c7",
    }
    formas = {
        "pessoa": "ellipse",
        "pessoa_relacionada": "ellipse",
        "programa": "box",
        "representante": "diamond",
    }
    for no, dados in grafo.nodes(data=True):
        tipo = dados.get("tipo", "pessoa")
        linhas.append(
            f"  {json.dumps(no)} ["
            f"label={json.dumps(dados.get('label', str(no)), ensure_ascii=False)}, "
            f"tooltip={json.dumps(dados.get('tooltip', ''), ensure_ascii=False)}, "
            f"fillcolor={json.dumps(cores.get(tipo, '#e2e8f0'))}, "
            f"shape={json.dumps(formas.get(tipo, 'ellipse'))}];"
        )
    for origem, destino, dados in grafo.edges(data=True):
        linhas.append(
            f"  {json.dumps(origem)} -- {json.dumps(destino)} "
            f"[label={json.dumps(dados.get('label', ''), ensure_ascii=False)}, "
            f"tooltip={json.dumps(dados.get('tooltip', ''), ensure_ascii=False)}];"
        )
    linhas.append("}")
    return "\n".join(linhas)
