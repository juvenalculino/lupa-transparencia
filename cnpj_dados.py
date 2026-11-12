import csv
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations

import networkx as nx


_CAMPOS_CSV = {
    "cnpj", "razao_social", "nome_fantasia", "situacao_cadastral",
    "capital_social", "cnae_fiscal", "cnae_descricao", "porte",
    "endereco", "logradouro", "numero", "complemento", "bairro", "cep",
    "telefone", "municipio", "uf", "socio_nome",
    "socio_cpf_cnpj_mascarado", "socio_qualificacao", "socio_tipo",
    "socio_data_entrada", "socio_faixa_etaria",
}


def _digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


def _normalizar_nome(nome):
    decomposicao = unicodedata.normalize("NFKD", str(nome or ""))
    sem_acentos = "".join(
        caractere for caractere in decomposicao
        if not unicodedata.combining(caractere)
    )
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", sem_acentos.upper()).split())


def _cpf_visivel(valor):
    digitos = _digitos(valor)
    if len(digitos) == 6:
        return digitos
    if len(digitos) == 11:
        return digitos[3:9]
    return ""


def _programa_filtro_key(programa):
    programa = str(programa or "").strip()
    sufixo = " (sacado)"
    if programa.casefold().endswith(sufixo):
        programa = programa[:-len(sufixo)].rstrip()
    return programa.casefold()


def _float_ou_nulo(valor):
    if valor is None or str(valor).strip() == "":
        return None
    return float(str(valor).replace(",", "."))


def salvar_registros_cnpj(
        con, registros, codigo_ibge, municipio, uf, origem,
        substituir_municipio=False):
    empresas = {}
    socios = defaultdict(dict)
    municipio_normalizado = _normalizar_nome(municipio)

    for numero_linha, registro in enumerate(registros, start=1):
        cnpj = _digitos(registro.get("cnpj"))
        if len(cnpj) != 14:
            raise ValueError(f"CNPJ inválido no registro {numero_linha}.")
        if _normalizar_nome(registro.get("municipio")) != municipio_normalizado:
            raise ValueError(
                f"O registro {numero_linha} pertence a outro município.")
        if str(registro.get("uf", "")).upper() != uf.upper():
            raise ValueError(f"O registro {numero_linha} pertence a outra UF.")

        empresas[cnpj] = {
            "cnpj": cnpj,
            "codigo_ibge": str(codigo_ibge),
            "razao_social": registro.get("razao_social") or None,
            "nome_fantasia": registro.get("nome_fantasia") or None,
            "situacao_cadastral": registro.get("situacao_cadastral") or None,
            "capital_social": _float_ou_nulo(registro.get("capital_social")),
            "cnae_fiscal": str(registro.get("cnae_fiscal") or ""),
            "cnae_descricao": registro.get("cnae_descricao") or None,
            "porte": registro.get("porte") or None,
            "endereco": registro.get("endereco") or None,
            "logradouro": registro.get("logradouro") or None,
            "numero": registro.get("numero") or None,
            "complemento": registro.get("complemento") or None,
            "bairro": registro.get("bairro") or None,
            "cep": _digitos(registro.get("cep")) or None,
            "telefone": registro.get("telefone") or None,
        }

        nome_socio = str(registro.get("socio_nome") or "").strip()
        cpf_socio = str(
            registro.get("socio_cpf_cnpj_mascarado") or "").strip()
        qualificacao = str(
            registro.get("socio_qualificacao") or "").strip()
        if nome_socio or cpf_socio or qualificacao:
            chave_socio = (nome_socio, cpf_socio, qualificacao)
            socios[cnpj][chave_socio] = (
                nome_socio or None,
                cpf_socio or None,
                qualificacao or None,
                str(registro.get("socio_tipo") or "").strip() or None,
                str(registro.get("socio_data_entrada") or "").strip() or None,
                str(registro.get("socio_faixa_etaria") or "").strip() or None,
            )

    if substituir_municipio and not empresas:
        raise ValueError(
            "A lista de CNPJs está vazia; os dados municipais existentes foram mantidos."
        )

    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with con:
        if substituir_municipio:
            cnpjs_antigos = con.execute(
                "SELECT cnpj FROM cnpj_empresa WHERE codigo_ibge=?",
                (str(codigo_ibge),),
            ).fetchall()
            con.executemany(
                "DELETE FROM cnpj_socio WHERE cnpj=?",
                cnpjs_antigos,
            )
            con.execute(
                "DELETE FROM cnpj_empresa WHERE codigo_ibge=?",
                (str(codigo_ibge),),
            )

        for empresa in empresas.values():
            con.execute(
                """
                INSERT INTO cnpj_empresa (
                    cnpj, codigo_ibge, razao_social, nome_fantasia,
                    situacao_cadastral, capital_social, cnae_fiscal,
                    cnae_descricao, porte, endereco, logradouro, numero,
                    complemento, bairro, cep, telefone, atualizado_em
                ) VALUES (
                    :cnpj, :codigo_ibge, :razao_social, :nome_fantasia,
                    :situacao_cadastral, :capital_social, :cnae_fiscal,
                    :cnae_descricao, :porte, :endereco, :logradouro, :numero,
                    :complemento, :bairro, :cep, :telefone, :atualizado_em
                )
                ON CONFLICT(cnpj) DO UPDATE SET
                    codigo_ibge=excluded.codigo_ibge,
                    razao_social=excluded.razao_social,
                    nome_fantasia=excluded.nome_fantasia,
                    situacao_cadastral=excluded.situacao_cadastral,
                    capital_social=excluded.capital_social,
                    cnae_fiscal=excluded.cnae_fiscal,
                    cnae_descricao=excluded.cnae_descricao,
                    porte=excluded.porte,
                    endereco=excluded.endereco,
                    logradouro=excluded.logradouro,
                    numero=excluded.numero,
                    complemento=excluded.complemento,
                    bairro=excluded.bairro,
                    cep=excluded.cep,
                    telefone=excluded.telefone,
                    atualizado_em=excluded.atualizado_em
                """,
                {**empresa, "atualizado_em": agora},
            )
            con.execute("DELETE FROM cnpj_socio WHERE cnpj=?", (empresa["cnpj"],))
            con.executemany(
                """
                INSERT INTO cnpj_socio (
                    cnpj, socio_nome, socio_cpf_cnpj_mascarado,
                    socio_qualificacao, socio_tipo, socio_data_entrada,
                    socio_faixa_etaria
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (empresa["cnpj"], *socio)
                    for socio in socios.get(empresa["cnpj"], {}).values()
                ],
            )

        total_socios = sum(len(itens) for itens in socios.values())
        con.execute(
            """
            INSERT INTO cnpj_coleta (
                codigo_ibge, coletado_em, origem, empresas, socios
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(codigo_ibge) DO UPDATE SET
                coletado_em=excluded.coletado_em,
                origem=excluded.origem,
                empresas=excluded.empresas,
                socios=excluded.socios
            """,
            (str(codigo_ibge), agora, origem, len(empresas), total_socios),
        )

    return {"empresas": len(empresas), "socios": total_socios}


def importar_csv_cnpj(con, caminho, codigo_ibge, municipio, uf):
    with open(caminho, encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=";")
        faltantes = _CAMPOS_CSV.difference(leitor.fieldnames or [])
        if faltantes:
            raise ValueError(
                "CSV de CNPJ sem as colunas obrigatórias: "
                + ", ".join(sorted(faltantes))
            )
        return salvar_registros_cnpj(
            con, leitor, codigo_ibge, municipio, uf, "csv",
        )


def obter_cruzamento_beneficiarios_cnpj(
        con, codigo_ibge, detalhado=False, situacoes_cadastrais=None,
        busca="", capital_min=None, capital_max=None, programa=None):
    codigo_ibge = str(codigo_ibge)
    filtro_empresas, parametros_empresas = _filtros_empresas_sql(
        busca,
        capital_min,
        capital_max,
        situacoes_cadastrais,
        prefixo="e.",
    )
    if filtro_empresas:
        filtro_empresas = f" AND {filtro_empresas}"
    programa = (programa or "").strip()
    if programa.casefold() == "todos":
        programa = ""
    programa_filtro = _programa_filtro_key(programa)
    programas_cadastrados = [
        row[0]
        for row in con.execute(
            """
            SELECT DISTINCT beneficio
            FROM beneficiario
            WHERE codigo_ibge=? AND beneficio IS NOT NULL
              AND trim(beneficio) != ''
            ORDER BY beneficio COLLATE NOCASE
            """,
            (codigo_ibge,),
        )
    ]

    linhas_beneficiarios = con.execute(
        """
        SELECT beneficio, mes_ano, nis, nome, cpf_mascarado, valor
        FROM beneficiario
        WHERE codigo_ibge=? AND nome IS NOT NULL AND trim(nome) != ''
        """,
        (codigo_ibge,),
    ).fetchall()
    pessoas = {}
    chaves_por_pessoa = defaultdict(set)
    for beneficio, mes_ano, nis, nome, cpf, valor in linhas_beneficiarios:
        nome_normalizado = _normalizar_nome(nome)
        cpf_visivel = _cpf_visivel(cpf)
        if not nis or not nome_normalizado:
            continue
        pessoa = pessoas.setdefault(nis, {
            "nome": nome,
            "cpf_mascarado": cpf,
            "beneficios": set(),
        })
        if not pessoa["cpf_mascarado"] and cpf:
            pessoa["cpf_mascarado"] = cpf
        pessoa["beneficios"].add((beneficio, str(mes_ano), valor))
        if cpf_visivel:
            chaves_por_pessoa[nis].add((nome_normalizado, cpf_visivel))

    pessoas_por_chave = defaultdict(set)
    for nis, chaves in chaves_por_pessoa.items():
        for chave in chaves:
            pessoas_por_chave[chave].add(nis)

    if detalhado:
        socios = con.execute(
            f"""
            SELECT e.cnpj, e.razao_social, e.nome_fantasia,
                   e.situacao_cadastral, e.capital_social, e.cnae_fiscal,
                   e.cnae_descricao, e.porte, e.endereco, e.logradouro,
                   e.numero, e.complemento, e.bairro, e.cep, e.telefone,
                   e.atualizado_em, s.socio_nome,
                   s.socio_cpf_cnpj_mascarado, s.socio_qualificacao,
                   s.socio_tipo, s.socio_data_entrada, s.socio_faixa_etaria
            FROM cnpj_empresa e
            JOIN cnpj_socio s ON s.cnpj=e.cnpj
            WHERE e.codigo_ibge=?
              AND upper(coalesce(s.socio_tipo, 'PF'))='PF'
              {filtro_empresas}
            """,
            (codigo_ibge, *parametros_empresas),
        ).fetchall()
    else:
        socios = con.execute(
            f"""
            SELECT e.cnpj, e.razao_social, e.nome_fantasia,
                   e.situacao_cadastral, e.capital_social, s.socio_nome,
                   s.socio_cpf_cnpj_mascarado, s.socio_qualificacao
            FROM cnpj_empresa e
            JOIN cnpj_socio s ON s.cnpj=e.cnpj
            WHERE e.codigo_ibge=?
              AND upper(coalesce(s.socio_tipo, 'PF'))='PF'
              {filtro_empresas}
            """,
            (codigo_ibge, *parametros_empresas),
        ).fetchall()
    resultados_por_pessoa = {}
    for socio in socios:
        if detalhado:
            (
                cnpj, razao_social, nome_fantasia, situacao, capital_social,
                cnae_fiscal, cnae_descricao, porte, endereco, logradouro,
                numero, complemento, bairro, cep, telefone, atualizado_em,
                socio_nome, cpf_socio, qualificacao, socio_tipo,
                socio_data_entrada, socio_faixa_etaria,
            ) = socio
        else:
            (
                cnpj, razao_social, nome_fantasia, situacao, capital_social,
                socio_nome, cpf_socio, qualificacao,
            ) = socio
        chave = (_normalizar_nome(socio_nome), _cpf_visivel(cpf_socio))
        if not chave[0] or not chave[1]:
            continue
        for nis in pessoas_por_chave.get(chave, ()):
            resultado = resultados_por_pessoa.setdefault(nis, {
                "nome": pessoas[nis]["nome"],
                "cpf_mascarado": pessoas[nis]["cpf_mascarado"],
                "beneficios": pessoas[nis]["beneficios"],
                "empresas": {},
            })
            resultado["empresas"][cnpj] = {
                "cnpj": cnpj,
                "razao_social": razao_social,
                "nome_fantasia": nome_fantasia,
                "situacao_cadastral": situacao,
                "capital_social": capital_social,
                "socio_nome": socio_nome,
                "socio_qualificacao": qualificacao,
            }
            if detalhado:
                resultado["empresas"][cnpj].update({
                    "cnae_fiscal": cnae_fiscal,
                    "cnae_descricao": cnae_descricao,
                    "porte": porte,
                    "endereco": endereco,
                    "logradouro": logradouro,
                    "numero": numero,
                    "complemento": complemento,
                    "bairro": bairro,
                    "cep": cep,
                    "telefone": telefone,
                    "atualizado_em": atualizado_em,
                    "socio_cpf_cnpj_mascarado": cpf_socio,
                    "socio_tipo": socio_tipo,
                    "socio_data_entrada": socio_data_entrada,
                    "socio_faixa_etaria": socio_faixa_etaria,
                })

    resultados = []
    programas_disponiveis = set()
    for resultado in resultados_por_pessoa.values():
        beneficios = resultado["beneficios"]
        programas_disponiveis.update(
            beneficio for beneficio, _, _ in beneficios)
        if programa_filtro:
            beneficios = {
                beneficio for beneficio in beneficios
                if _programa_filtro_key(beneficio[0]) == programa_filtro
            }
            if not beneficios:
                continue
        pessoa = {
            "nome": resultado["nome"],
            "cpf_mascarado": resultado["cpf_mascarado"],
            "programas": sorted({item[0] for item in beneficios}),
            "periodos": sorted({item[1] for item in beneficios}),
            "empresas": sorted(
                resultado["empresas"].values(),
                key=lambda empresa: empresa["cnpj"],
            ),
        }
        if detalhado:
            pessoa["beneficios"] = [
                {
                    "programa": beneficio,
                    "competencia": periodo,
                    "valor": valor,
                }
                for beneficio, periodo, valor in sorted(
                    beneficios,
                    key=lambda item: (
                        item[0], item[1], item[2] is None, item[2] or 0
                    ),
                )
            ]
        resultados.append(pessoa)
    resultados.sort(key=lambda resultado: (
        _normalizar_nome(resultado["nome"]),
        resultado["cpf_mascarado"] or "",
    ))

    total = len(resultados)
    resumo = con.execute(
        f"""
        SELECT COUNT(DISTINCT e.cnpj), COUNT(DISTINCT s.id)
        FROM cnpj_empresa e
        LEFT JOIN cnpj_socio s ON s.cnpj=e.cnpj
        WHERE e.codigo_ibge=? {filtro_empresas}
        """,
        (codigo_ibge, *parametros_empresas),
    ).fetchone()
    coleta = con.execute(
        """
        SELECT coletado_em, origem FROM cnpj_coleta WHERE codigo_ibge=?
        """,
        (codigo_ibge,),
    ).fetchone()
    return {
        "empresas": resumo[0],
        "socios": resumo[1],
        "beneficiarios_com_cnpj": total,
        "programas_disponiveis": sorted(programas_disponiveis),
        "programas_cadastrados": programas_cadastrados,
        "coletado_em": coleta[0] if coleta else None,
        "origem": coleta[1] if coleta else None,
        "resultados": resultados,
    }


def cruzar_beneficiarios_cnpj(
        con, codigo_ibge, pagina=1, por_pagina=50, busca="",
        capital_min=None, capital_max=None, situacoes_cadastrais=None,
        programa=None):
    """Retorna uma página dos beneficiários com correspondência empresarial."""
    cruzamento = obter_cruzamento_beneficiarios_cnpj(
        con,
        codigo_ibge,
        busca=busca,
        capital_min=capital_min,
        capital_max=capital_max,
        situacoes_cadastrais=situacoes_cadastrais,
        programa=programa,
    )
    total = cruzamento["beneficiarios_com_cnpj"]
    inicio = (pagina - 1) * por_pagina
    return {
        **cruzamento,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total_paginas": (total + por_pagina - 1) // por_pagina,
        "resultados": cruzamento["resultados"][inicio:inicio + por_pagina],
    }


def resumir_beneficios_cnpj(con, codigo_ibge):
    """Conta vínculos por município/programa sem retornar dados pessoais."""
    socios = con.execute(
        """
        SELECT s.socio_nome, s.socio_cpf_cnpj_mascarado
        FROM cnpj_empresa e
        JOIN cnpj_socio s ON s.cnpj=e.cnpj
        WHERE e.codigo_ibge=? AND upper(coalesce(s.socio_tipo, 'PF'))='PF'
        """,
        (str(codigo_ibge),),
    ).fetchall()
    chaves = {
        (_normalizar_nome(nome), _cpf_visivel(cpf))
        for nome, cpf in socios
        if _normalizar_nome(nome) and _cpf_visivel(cpf)
    }
    if not chaves:
        return []

    cpfs = sorted({cpf for _, cpf in chaves})
    nises = set()
    cpf_sql = """
        CASE
            WHEN length(cpf_digitos) = 6 THEN cpf_digitos
            WHEN length(cpf_digitos) = 11 THEN substr(cpf_digitos, 4, 6)
            ELSE ''
        END
    """
    for inicio in range(0, len(cpfs), 500):
        lote = cpfs[inicio:inicio + 500]
        placeholders = ",".join("?" for _ in lote)
        linhas = con.execute(
            f"""
            SELECT nis, nome,
                   CASE
                       WHEN length(cpf_digitos) = 6 THEN cpf_digitos
                       WHEN length(cpf_digitos) = 11
                           THEN substr(cpf_digitos, 4, 6)
                       ELSE ''
                   END AS cpf_visivel
            FROM (
                SELECT beneficio, codigo_ibge, nis, nome,
                       replace(replace(replace(replace(replace(replace(
                           coalesce(cpf_mascarado, ''), '.', ''), '-', ''),
                           '*', ''), ' ', ''), '/', ''), '\\', '')
                           AS cpf_digitos
                FROM beneficiario
                WHERE codigo_ibge=? AND cpf_mascarado IS NOT NULL
            )
            WHERE {cpf_sql} IN ({placeholders})
            """,
            (str(codigo_ibge), *lote),
        ).fetchall()
        for nis, nome, cpf in linhas:
            chave = (_normalizar_nome(nome), cpf)
            if chave in chaves:
                nises.add(nis)

    if not nises:
        return []

    grupos = defaultdict(lambda: {"nises": set(), "periodos": set()})
    nises = sorted(nises)
    for inicio in range(0, len(nises), 500):
        lote = nises[inicio:inicio + 500]
        placeholders = ",".join("?" for _ in lote)
        linhas = con.execute(
            f"""
            SELECT beneficio, codigo_ibge, nis, mes_ano
            FROM beneficiario
            WHERE nis IN ({placeholders})
            """,
            lote,
        ).fetchall()
        for beneficio, municipio, nis, mes_ano in linhas:
            grupo = grupos[(str(municipio), beneficio)]
            grupo["nises"].add(nis)
            grupo["periodos"].add(str(mes_ano))

    return [
        {
            "codigo_ibge": municipio,
            "beneficio": beneficio,
            "beneficiarios": len(beneficiarios["nises"]),
            "periodo_inicial": min(beneficiarios["periodos"]),
            "periodo_final": max(beneficiarios["periodos"]),
        }
        for (municipio, beneficio), beneficiarios in sorted(grupos.items())
    ]


def _filtro_situacoes(situacoes, campo):
    if isinstance(situacoes, str):
        situacoes = situacoes.split(",")
    valores = list(dict.fromkeys(
        str(situacao).strip()
        for situacao in (situacoes or [])
        if str(situacao).strip()
    ))
    if not valores:
        return "", []

    condicoes = []
    parametros = []
    for situacao in valores:
        if situacao == "__SEM_SITUACAO__":
            condicoes.append(f"({campo} IS NULL OR TRIM({campo}) = '')")
        else:
            condicoes.append(f"UPPER(TRIM({campo})) = UPPER(?)")
            parametros.append(situacao)
    return f"({' OR '.join(condicoes)})", parametros


def _filtros_empresas_sql(
        busca="", capital_min=None, capital_max=None,
        situacoes_cadastrais=None, prefixo=""):
    clausulas = []
    parametros = []
    termo = (busca or "").strip()
    if termo:
        termo_lower = f"%{termo.lower()}%"
        clausulas.append(
            f"(LOWER(COALESCE({prefixo}razao_social, '')) LIKE ? "
            f"OR LOWER(COALESCE({prefixo}nome_fantasia, '')) LIKE ? "
            f"OR {prefixo}cnpj LIKE ?)"
        )
        parametros.extend([termo_lower, termo_lower, f"%{termo}%"])
    if capital_min is not None:
        clausulas.append(f"COALESCE({prefixo}capital_social, 0) >= ?")
        parametros.append(float(capital_min))
    if capital_max is not None:
        clausulas.append(f"COALESCE({prefixo}capital_social, 0) <= ?")
        parametros.append(float(capital_max))
    filtro_situacoes, parametros_situacoes = _filtro_situacoes(
        situacoes_cadastrais, f"{prefixo}situacao_cadastral")
    if filtro_situacoes:
        clausulas.append(filtro_situacoes)
        parametros.extend(parametros_situacoes)
    return " AND ".join(clausulas), parametros


def listar_empresas_cnpj(con, codigo_ibge, busca="", capital_min=None,
                        capital_max=None, pagina=1, por_pagina=50,
                        situacoes_cadastrais=None):
    if pagina < 1:
        raise ValueError("A página deve ser positiva.")
    if por_pagina < 1:
        raise ValueError("O tamanho da página deve ser positivo.")

    clausulas = ["codigo_ibge = ?"]
    parametros = [str(codigo_ibge)]
    filtro_empresas, parametros_empresas = _filtros_empresas_sql(
        busca,
        capital_min,
        capital_max,
        situacoes_cadastrais,
    )
    if filtro_empresas:
        clausulas.append(filtro_empresas)
        parametros.extend(parametros_empresas)

    where = " AND ".join(clausulas)
    total = con.execute(
        f"SELECT COUNT(*) FROM cnpj_empresa WHERE {where}",
        parametros,
    ).fetchone()[0]

    offset = (pagina - 1) * por_pagina
    rows = con.execute(
        f"""
        SELECT cnpj, razao_social, nome_fantasia, situacao_cadastral,
               capital_social, cnae_fiscal, cnae_descricao, porte,
               endereco, logradouro, numero, complemento, bairro, cep,
               telefone, atualizado_em
        FROM cnpj_empresa
        WHERE {where}
        ORDER BY razao_social COLLATE NOCASE, cnpj
        LIMIT ? OFFSET ?
        """,
        (*parametros, por_pagina, offset),
    ).fetchall()
    situacoes_disponiveis = con.execute(
        """
        SELECT DISTINCT CASE
            WHEN situacao_cadastral IS NULL OR trim(situacao_cadastral) = ''
                THEN '__SEM_SITUACAO__'
            ELSE trim(situacao_cadastral)
        END
        FROM cnpj_empresa
        WHERE codigo_ibge=?
        ORDER BY 1 COLLATE NOCASE
        """,
        (str(codigo_ibge),),
    ).fetchall()

    empresas = []
    for row in rows:
        (
            cnpj, razao_social, nome_fantasia, situacao_cadastral,
            capital_social, cnae_fiscal, cnae_descricao, porte,
            endereco, logradouro, numero, complemento, bairro, cep,
            telefone, atualizado_em,
        ) = row
        empresas.append({
            "cnpj": cnpj,
            "razao_social": razao_social,
            "nome_fantasia": nome_fantasia,
            "situacao_cadastral": situacao_cadastral,
            "capital_social": capital_social,
            "cnae_fiscal": cnae_fiscal,
            "cnae_descricao": cnae_descricao,
            "porte": porte,
            "endereco": endereco,
            "logradouro": logradouro,
            "numero": numero,
            "complemento": complemento,
            "bairro": bairro,
            "cep": cep,
            "telefone": telefone,
            "atualizado_em": atualizado_em,
        })

    return {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total_paginas": (total + por_pagina - 1) // por_pagina,
        "capital_total": round(sum(float(item["capital_social"] or 0) for item in empresas), 2),
        "situacoes_cadastrais": [row[0] for row in situacoes_disponiveis],
        "resultados": empresas,
    }


def criar_grafo_cnpj(con, codigo_ibge, limite=200):
    """Cria um grafo de empresas e sócios para um município."""
    grafo = nx.Graph()
    empresas = con.execute(
        """
        SELECT cnpj, razao_social, nome_fantasia, capital_social, situacao_cadastral
        FROM cnpj_empresa
        WHERE codigo_ibge=?
        ORDER BY COALESCE(capital_social, 0) DESC, razao_social COLLATE NOCASE
        LIMIT ?
        """,
        (str(codigo_ibge), limite),
    ).fetchall()

    cnpjs_selecionados = [empresa[0] for empresa in empresas]
    if not cnpjs_selecionados:
        return grafo

    socios_por_empresa = defaultdict(list)
    placeholders = ",".join("?" for _ in cnpjs_selecionados)
    socios = con.execute(
        f"""
        SELECT s.cnpj, s.socio_nome, s.socio_qualificacao, s.socio_tipo,
               s.socio_cpf_cnpj_mascarado
        FROM cnpj_socio s
        WHERE s.cnpj IN ({placeholders})
        ORDER BY s.socio_nome COLLATE NOCASE
        """,
        cnpjs_selecionados,
    ).fetchall()

    for cnpj, nome, _, _, _ in socios:
        if nome:
            socios_por_empresa[cnpj].append(nome)

    for cnpj, razao_social, nome_fantasia, capital_social, situacao in empresas:
        label = razao_social or nome_fantasia or cnpj
        grafo.add_node(
            cnpj,
            tipo="empresa",
            label=f"{label}\n{cnpj}",
            tooltip=f"{label} · {situacao or 'Sem situação'} · Capital: R$ {float(capital_social or 0):,.2f}",
            tamanho=22,
        )
        for socio_nome in socios_por_empresa.get(cnpj, []):
            socio_key = f"socio::{_normalizar_nome(socio_nome)}"
            if not grafo.has_node(socio_key):
                grafo.add_node(
                    socio_key,
                    tipo="socio",
                    label=socio_nome,
                    tooltip=f"Sócio: {socio_nome}",
                    tamanho=18,
                )
            grafo.add_edge(cnpj, socio_key, relacao="socio", label="sócio")

    socios_para_empresas = defaultdict(set)
    for cnpj, nome, _, _, _ in socios:
        if nome:
            socios_para_empresas[_normalizar_nome(nome)].add(cnpj)
    for _, empresas_compartilhadas in socios_para_empresas.items():
        empresas_compartilhadas = sorted(empresas_compartilhadas)
        for empresa_a, empresa_b in combinations(empresas_compartilhadas, 2):
            if not grafo.has_edge(empresa_a, empresa_b):
                grafo.add_edge(empresa_a, empresa_b, relacao="mesmo_socio", label="mesmo sócio")

    return grafo
