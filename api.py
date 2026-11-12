import csv
import io
import ipaddress
import os
import re
import threading
import time
import sqlite3
import unicodedata
import pandas as pd
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional

from api_secrets import (
    SecretStoreError, delete_api_key, encryption_key_is_valid,
    list_api_keys, load_api_keys, load_server_secrets, save_api_key,
)
from coleta import (
    init_db, PortalClient, carregar_municipios,
    coletar_agregado_ano, coletar_beneficiarios,
    meses_agregado_faltantes, meses_beneficiarios_faltantes,
    meses_validos_ano, PROGRAMAS_VIGENCIA,
)
from cnpj_dados import (
    criar_grafo_cnpj, cruzar_beneficiarios_cnpj, importar_csv_cnpj,
    listar_empresas_cnpj, obter_cruzamento_beneficiarios_cnpj,
    resumir_beneficios_cnpj, salvar_registros_cnpj,
)
from relatorio_cnpj_pdf import gerar_relatorio_cruzamento_pdf
from utils.cnpj_municipio import coletar_dados_municipio
from rede import (
    criar_grafo_programas, buscar_pessoas,
    programas_da_pessoa, criar_grafo_pessoa
)

load_server_secrets()

app = FastAPI(title="API Benefícios - Portal da Transparência")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PADRAO = os.path.join(BASE, "beneficios.db")
PASTA_DADOS = os.path.join(BASE, "dados")
PASTA_FRONTEND = os.path.join(BASE, "dist")
_status_coleta_lock = threading.Lock()
_status_coleta = None
_status_cnpj_lock = threading.Lock()
_status_cnpj = None

# --- SITUAÇÃO DOS PROGRAMAS ---
STATUS_PROGRAMAS = {
    "Bolsa Familia": "Extinto (substituído pelo Auxílio Brasil)",
    "Auxilio Emergencial": "Extinto (criado para a pandemia)",
    "Auxilio Brasil": "Extinto (reconvertido em Bolsa Família)",
    "Novo Bolsa Familia": "Ativo",
    "BPC": "Ativo",
    "PETI": "Extinto",
    "Seguro Defeso": "Ativo",
    "Garantia Safra": "Ativo",
}

def get_programas_vigentes(ano: str, mes: str):
    """Calcula quais programas estavam ativos no ano e mês solicitados."""
    if ano == "Todos":
        # Se pedir todos os anos, retorna todos os programas mapeados
        return [
            {"nome": nome, "status": STATUS_PROGRAMAS[nome]}
            for nome in PROGRAMAS_VIGENCIA
        ]
    
    mes_inicio = "01" if mes == "Todos" else f"{int(mes):02d}"
    mes_fim = "12" if mes == "Todos" else f"{int(mes):02d}"
    
    periodo_inicio = f"{ano}{mes_inicio}"
    periodo_fim = f"{ano}{mes_fim}"
    
    vigentes = []
    for prog, (ini, fim) in PROGRAMAS_VIGENCIA.items():
        # Verifica interseção de datas
        fim_vigencia = fim or "999912"
        if not (periodo_fim < ini or periodo_inicio > fim_vigencia):
            vigentes.append({
                "nome": prog,
                "status": STATUS_PROGRAMAS[prog],
            })
            
    return sorted(vigentes, key=lambda x: x["nome"])


def _mes_ano(ano, mes):
    return f"{int(ano)}{int(mes):02d}"

# --- FUNÇÕES DE CONSULTA SQL OTIMIZADAS ---

def _filtros_consulta(beneficio, ano_str, codigo_ibge, mes_str):
    codigo_ibge = str(codigo_ibge)
    if len(codigo_ibge) == 7:
        filtros = ["codigo_ibge = ?"]
        parametros = [codigo_ibge]
    else:
        prefixo = codigo_ibge[:6]
        filtros = ["codigo_ibge >= ? AND codigo_ibge < ?"]
        parametros = [prefixo, f"{prefixo}\x7f"]

    if beneficio != "Todos":
        nome = beneficio.strip()
        filtros.append("beneficio IN (?, ?)")
        parametros.extend((nome, f"{nome} (sacado)"))

    if ano_str != "Todos":
        if mes_str == "Todos":
            filtros.append("mes_ano >= ? AND mes_ano <= ?")
            parametros.extend((f"{int(ano_str):04d}01", f"{int(ano_str):04d}12"))
        else:
            filtros.append("mes_ano = ?")
            parametros.append(f"{int(ano_str):04d}{int(mes_str):02d}")
    elif mes_str != "Todos":
        filtros.append("substr(mes_ano, 5, 2) = ?")
        parametros.append(f"{int(mes_str):02d}")

    return " AND ".join(filtros), parametros


def carregar_dados_agregados(con, beneficio, ano_str, codigo_ibge, mes_str):
    where, parametros = _filtros_consulta(
        beneficio, ano_str, codigo_ibge, mes_str)
    query = f"""
        SELECT beneficio, mes_ano, valor, qtd_beneficiados
        FROM beneficio_mensal
        WHERE {where}
        ORDER BY mes_ano, beneficio
    """
    rows = con.execute(query, parametros).fetchall()
    
    meses_nomes = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    
    resultados = []
    for prog, ma, valor, qtd in rows:
        ma_str = str(ma)
        if len(ma_str) == 6:  # Formato YYYYMM
            y, m = int(ma_str[:4]), int(ma_str[4:])
            nome_mes = meses_nomes[m-1] if 1 <= m <= 12 else str(m)
        else:
            y, m = 0, 0
            nome_mes = ma_str
            
        resultados.append({
            "programa": prog, "mes": nome_mes, "mes_num": m, 
            "ano": y, "valor": valor, "beneficiados": qtd
        })
    
    return pd.DataFrame(resultados, columns=["programa", "mes", "mes_num", "ano", "valor", "beneficiados"])


def carregar_dados_beneficiarios(
        con, beneficio, ano_str, codigo_ibge, mes_str, pagina=None,
        por_pagina=100, busca=""):
    where, parametros = _filtros_consulta(
        beneficio, ano_str, codigo_ibge, mes_str)
    if busca:
        where += " AND (nome LIKE ? OR nis LIKE ? OR beneficio LIKE ?)"
        termo = f"%{busca.strip()}%"
        parametros.extend((termo, termo, termo))

    total = con.execute(
        f"SELECT COUNT(*) FROM beneficiario WHERE {where}", parametros
    ).fetchone()[0]
    if pagina is None:
        limite, offset = 20000, 0
    else:
        limite = por_pagina
        offset = (pagina - 1) * por_pagina

    query = f"""
        SELECT beneficio, mes_ano, nis, nome, cpf_mascarado, valor 
        FROM beneficiario 
        WHERE {where}
        ORDER BY beneficio, mes_ano, nis
        LIMIT ? OFFSET ?
    """
    rows = con.execute(query, (*parametros, limite, offset)).fetchall()
    
    resultados = []
    for prog, ma, n, nm, c, v in rows:
        ma_str = str(ma)
        if len(ma_str) == 6:
            y, m = int(ma_str[:4]), int(ma_str[4:])
        else:
            y, m = 0, 0
        resultados.append({
            "programa": prog, "nis": n, "nome": nm, "cpf": c, 
            "valor_saque": v, "mes": m, "ano": y
        })
        
    dataframe = pd.DataFrame(
        resultados,
        columns=["programa", "nis", "nome", "cpf", "valor_saque", "mes", "ano"],
    )
    return dataframe, total


def carregar_resumo_beneficiarios(
        con, beneficio, ano_str, codigo_ibge, mes_str):
    where, parametros = _filtros_consulta(
        beneficio, ano_str, codigo_ibge, mes_str)
    totais = con.execute(
        f"""
        SELECT COUNT(*), COALESCE(SUM(valor), 0),
               COUNT(DISTINCT nis),
               COUNT(DISTINCT substr(mes_ano, 5, 2))
        FROM beneficiario
        WHERE {where}
        """,
        parametros,
    ).fetchone()
    rows = con.execute(
        f"""
        SELECT mes_ano, COALESCE(SUM(valor), 0), COUNT(DISTINCT nis)
        FROM beneficiario
        WHERE {where}
        GROUP BY mes_ano
        ORDER BY mes_ano
        """,
        parametros,
    ).fetchall()

    resultados = []
    for mes_ano, valor, beneficiados in rows:
        mes_ano = str(mes_ano)
        ano, mes = int(mes_ano[:4]), int(mes_ano[4:6])
        resultados.append({
            "mes": mes,
            "mes_num": mes,
            "ano": ano,
            "valor": valor,
            "beneficiados": beneficiados,
        })

    total_registros, total_valor, total_beneficiados, meses = totais
    resumo = {
        "registros": total_registros,
        "total_valor": total_valor,
        "total_beneficiados": total_beneficiados,
        "meses": meses,
    }
    return resultados, resumo


def parse_graph_to_vis(grafo):
    nodes = []
    for node_id, node_data in grafo.nodes(data=True):
        node_type = node_data.get("tipo", "desconhecido")
        color = "#bfdbfe" if node_type == "pessoa" else "#bbf7d0" if node_type == "programa" else "#fef3c7" if node_type == "representante" else "#e2e8f0"
        border = "#3b82f6" if node_type == "pessoa" else "#22c55e" if node_type == "programa" else "#f59e0b"
        
        degree = grafo.degree(node_id)
        nodes.append({
            "id": str(node_id),
            "label": node_data.get("label", str(node_id)),
            "shape": "ellipse" if node_type == "pessoa" else "box",
            "color": {"background": color, "border": border},
            "size": 15 + degree * 3,
            "font": {"size": 12, "color": "#0f172a", "face": "Inter"}
        })
        
    edges = []
    for source, target, edge_data in grafo.edges(data=True):
        weight = edge_data.get("peso", 1)
        edges.append({
            "from": str(source),
            "to": str(target),
            "label": edge_data.get("label", ""),
            "width": 1 + weight * 0.5,
            "color": {"color": "#64748b"}
        })
    return {"nodes": nodes, "edges": edges}


# --- ENDPOINTS REST DA API ---

class ConsultaRequest(BaseModel):
    tipo: str
    programa: str
    uf: str
    codigo_ibge: str
    nome_mun: str
    ano: str  # Convertido para STR para suportar "Todos"
    mes: str = "Todos"
    permitir_novos: bool
    api_key: Optional[str] = None
    pagina: Optional[int] = None
    por_pagina: int = 100
    busca: str = ""
    resumo: bool = False


class ApiKeyRequest(BaseModel):
    api_key: str = Field(min_length=1)

class InserirDadosRequest(BaseModel):
    nis: str
    nome: str
    cpf: str
    valor: float
    programa: str
    codigo_ibge: str
    nome_mun: str
    uf: str
    mes: str 
    ano: str 


class CnpjColetaRequest(BaseModel):
    codigo_ibge: str = Field(pattern=r"^\d{7}$")

@app.get("/api/filtros")
def obter_filtros_disponiveis(codigo_ibge: str, ano: str, mes: str = "Todos"):
    con = init_db(DB_PADRAO)
    where, parametros = _filtros_consulta(
        "Todos", ano, codigo_ibge, mes)
    try:
        agregados = con.execute(
            f"SELECT DISTINCT beneficio FROM beneficio_mensal WHERE {where}",
            parametros,
        ).fetchall()
        beneficiarios = con.execute(
            f"SELECT DISTINCT beneficio FROM beneficiario WHERE {where}",
            parametros,
        ).fetchall()
        
        programas_unicos = set([r[0] for r in agregados] + [r[0] for r in beneficiarios])
        programas_limpos = list(set([p.replace(" (sacado)", "").strip() for p in programas_unicos if p]))
        
        # Mapeia programas ativos baseados na Vigência Oficial
        programas_api = get_programas_vigentes(ano, mes)

        return {
            "programas": sorted(programas_limpos),
            "programas_api": programas_api
        }
    except Exception as e:
        return {"erro": str(e), "programas": [], "programas_api": []}
    finally:
        con.close()


def _require_local_api_management(request: Request) -> None:
    client = request.client
    try:
        client_is_local = bool(
            client and ipaddress.ip_address(client.host).is_loopback
        )
    except ValueError:
        client_is_local = False
    if not client_is_local:
        raise HTTPException(
            status_code=403,
            detail="O gerenciamento das chaves só está disponível localmente.",
        )

    origin = request.headers.get("origin")
    if origin:
        from urllib.parse import urlsplit

        hostname = urlsplit(origin).hostname
        try:
            origin_is_local = hostname == "localhost" or bool(
                hostname and ipaddress.ip_address(hostname).is_loopback
            )
        except ValueError:
            origin_is_local = False
        if not origin_is_local:
            raise HTTPException(
                status_code=403,
                detail="O gerenciamento das chaves só está disponível localmente.",
            )


def _load_stored_api_keys() -> list[str]:
    try:
        return load_api_keys()
    except SecretStoreError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/config/api-key")
def api_key_status(request: Request):
    _require_local_api_management(request)
    try:
        load_server_secrets()
    except SecretStoreError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    keys = list_api_keys()
    return {
        "enabled": encryption_key_is_valid(),
        "configured": bool(keys),
        "keys": keys,
    }


@app.put("/api/config/api-key")
def api_key_save(req: ApiKeyRequest, request: Request):
    _require_local_api_management(request)
    try:
        save_api_key(req.api_key)
        keys = list_api_keys()
    except SecretStoreError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "configured": True,
        "keys": keys,
        "message": "Chave da API salva com segurança.",
    }


@app.delete("/api/config/api-key/{key_id}")
def api_key_delete(key_id: str, request: Request):
    _require_local_api_management(request)
    try:
        removed = delete_api_key(key_id)
        keys = list_api_keys()
    except SecretStoreError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not removed:
        raise HTTPException(status_code=404, detail="Chave da API não encontrada.")
    return {
        "configured": bool(keys),
        "keys": keys,
        "message": "Chave da API removida.",
    }


def _api_keys_for_collection(request_key: Optional[str]) -> list[str]:
    api_keys = ([request_key] if request_key else []) + _load_stored_api_keys()
    configured_key = os.environ.get("PORTAL_API_KEY")
    if configured_key:
        api_keys.append(configured_key)
    return list(dict.fromkeys(api_keys))


def _atualizar_status_coleta(**valores):
    with _status_coleta_lock:
        if _status_coleta is not None:
            _status_coleta.update(valores)
            _status_coleta["tempo_decorrido"] = round(
                time.monotonic() - _status_coleta["inicio"], 1)


def _registrar_pagina_coleta(pagina, registros, tempo_ms):
    with _status_coleta_lock:
        if _status_coleta is not None:
            _status_coleta["paginas_lidas"] += 1
            _status_coleta["registros_lidos"] += registros
            _status_coleta["mensagem"] = f"Página {pagina} processada"
            _status_coleta["tempo_ultima_pagina"] = round(
                tempo_ms / 1000, 1)
            _status_coleta["tempo_decorrido"] = round(
                time.monotonic() - _status_coleta["inicio"], 1)


@app.post("/api/consultar")
def consultar_dados(req: ConsultaRequest):
    global _status_coleta
    if req.programa != "Todos" and req.ano != "Todos":
        try:
            meses_permitidos = meses_validos_ano(
                req.programa, int(req.ano))
        except (KeyError, ValueError) as error:
            raise HTTPException(
                status_code=422,
                detail="Programa ou ano inválido para consulta.",
            ) from error
        if not meses_permitidos:
            raise HTTPException(
                status_code=422,
                detail=f"{req.programa} não estava vigente em {req.ano}.",
            )
        if req.mes != "Todos" and req.mes not in meses_permitidos:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{req.mes}/{req.ano} está fora da vigência de "
                    f"{req.programa}. Meses válidos: "
                    f"{', '.join(meses_permitidos)}."
                ),
            )

    api_keys = []
    if req.permitir_novos:
        api_keys = _api_keys_for_collection(req.api_key)
        if not api_keys:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Informe uma chave da API do Portal da Transparência ou "
                    "salve uma chave no servidor antes de iniciar a coleta."
                ),
            )

    con = init_db(DB_PADRAO)
    try:
        if req.programa != "Todos" and req.ano != "Todos":
            meses_busca = (
                meses_permitidos if req.mes == "Todos"
                else [f"{int(req.mes):02d}"]
            )
        elif req.mes != "Todos":
            meses_busca = [f"{int(req.mes):02d}"]
        elif req.ano == "Todos" or req.programa == "Todos":
            meses_busca = [f"{m:02d}" for m in range(1, 13)]
        else:
            meses_busca = meses_validos_ano(req.programa, int(req.ano))

        if req.tipo == "Agregado mensal do ano":
            if req.permitir_novos and req.programa != "Todos" and req.ano != "Todos":
                meses_faltantes = meses_agregado_faltantes(
                    con, req.programa, int(req.ano), req.codigo_ibge,
                    meses_busca)
                if meses_faltantes:
                    try:
                        client = PortalClient(api_keys)
                        coletar_agregado_ano(
                            client, con, req.programa, int(req.ano),
                            req.codigo_ibge, req.nome_mun, req.uf,
                            meses_faltantes)
                    except Exception as e:
                        return {"erro": f"Erro com GovAPI: {str(e)}"}

            df = carregar_dados_agregados(
                con, req.programa, req.ano, req.codigo_ibge, req.mes)
            return {"dados": df.to_dict(orient="records"), "registros": len(df)}

        if req.tipo != "Adicionar beneficiários":
            return {"erro": "Tipo de consulta inválido"}

        if req.pagina is not None and req.pagina < 1:
            raise HTTPException(
                status_code=422,
                detail="A página deve ser maior que zero.",
            )
        if req.por_pagina < 1 or req.por_pagina > 200:
            raise HTTPException(
                status_code=422,
                detail="O tamanho da página deve estar entre 1 e 200.",
            )

        if req.resumo:
            dados, resumo = carregar_resumo_beneficiarios(
                con, req.programa, req.ano, req.codigo_ibge, req.mes)
            return {"dados": dados, "registros": resumo["registros"], "resumo": resumo}

        if req.permitir_novos and req.programa != "Todos" and req.ano != "Todos":
            prog_api = req.programa
            if prog_api in ["Novo Bolsa Familia", "Bolsa Familia", "Auxilio Brasil"]:
                prog_api = f"{prog_api} (sacado)"

            with _status_coleta_lock:
                _status_coleta = {
                    "mensagem": "Verificando competências pendentes",
                    "registros_lidos": 0,
                    "paginas_lidas": 0,
                    "tempo_decorrido": 0,
                    "inicio": time.monotonic(),
                    "concluido": False,
                    "erro": None,
                }

            meses_faltantes = meses_beneficiarios_faltantes(
                con, prog_api, int(req.ano), req.codigo_ibge, meses_busca)
            if meses_faltantes:
                try:
                    client = PortalClient(api_keys)
                    for mes in meses_faltantes:
                        _atualizar_status_coleta(
                            mensagem=f"Coletando competência {mes}/{req.ano}")
                        coletar_beneficiarios(
                            client, con, prog_api, f"{req.ano}{mes}",
                            req.codigo_ibge, req.nome_mun, req.uf,
                            on_pagina=_registrar_pagina_coleta)
                except Exception as e:
                    _atualizar_status_coleta(
                        mensagem="Coleta interrompida",
                        concluido=True,
                        erro=str(e))
                    return {"erro": f"Erro com GovAPI: {str(e)}"}
                _atualizar_status_coleta(
                    mensagem="Coleta concluída",
                    concluido=True,
                    erro=None)
            else:
                _atualizar_status_coleta(
                    mensagem="Nenhuma competência pendente",
                    concluido=True)

        df, total = carregar_dados_beneficiarios(
            con, req.programa, req.ano, req.codigo_ibge, req.mes,
            pagina=req.pagina, por_pagina=req.por_pagina, busca=req.busca)
        return {
            "dados": df.to_dict(orient="records"),
            "registros": total,
            "pagina": req.pagina,
            "por_pagina": req.por_pagina,
            "total_paginas": (
                (total + req.por_pagina - 1) // req.por_pagina
                if req.pagina is not None else 1
            ),
        }
    finally:
        con.close()


@app.get("/api/status")
def status_coleta():
    with _status_coleta_lock:
        if _status_coleta is None:
            return {"status": None}
        status = {
            chave: valor for chave, valor in _status_coleta.items()
            if chave != "inicio"
        }
        status["tempo_decorrido"] = round(
            time.monotonic() - _status_coleta["inicio"], 1)
        return {"status": status}


@app.get("/api/grafo/programas")
def grafo_programas(codigo_ibge: str, ano: str):
    con = init_db(DB_PADRAO)
    meses = [f"{m:02d}" for m in range(1, 13)]
    
    # Adaptado para a lógica do rede_2.py: "Todos" passa a ser None
    ano_arg = None if ano == "Todos" else int(ano) 
    grafo = criar_grafo_programas(con, codigo_ibge, ano_arg, meses)
    
    return parse_graph_to_vis(grafo)


@app.get("/api/grafo/pessoa/{nis}")
def grafo_pessoa(nis: str, codigo_ibge: str, ano: str): 
    con = init_db(DB_PADRAO)
    meses = [f"{m:02d}" for m in range(1, 13)]
    
    # Adaptado para a lógica do rede_2.py: "Todos" passa a ser None
    ano_arg = None if ano == "Todos" else int(ano) 
    
    dados_pessoa = programas_da_pessoa(con, codigo_ibge, nis, ano_arg, meses)
    candidatos = buscar_pessoas(con, codigo_ibge, nis, ano_arg, meses, limite=1)
    nome = candidatos[0][1] if candidatos else None
    
    grafo = criar_grafo_pessoa(nis, dados_pessoa, nome_pessoa=nome)
    return parse_graph_to_vis(grafo)


@app.get("/api/busca_global")
def busca_global(codigo_ibge: str, termo: str):
    con = init_db(DB_PADRAO)
    candidatos = buscar_pessoas(con, codigo_ibge, termo, limite=50)
    resultados = [{"nis": c[0], "nome": c[1], "programas": c[3]} for c in candidatos]
    return {"resultados": resultados}


def _codigos_municipios_com_beneficios(con):
    tabelas = {
        row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    consultas = []
    if "beneficio_mensal" in tabelas:
        consultas.append(
            "SELECT DISTINCT codigo_ibge FROM beneficio_mensal"
        )
    if "beneficiario" in tabelas:
        consultas.append(
            "SELECT DISTINCT codigo_ibge FROM beneficiario"
        )
    if "coleta_log" in tabelas:
        consultas.append(
            "SELECT DISTINCT codigo_ibge FROM coleta_log "
            "WHERE tipo IN ('agregado', 'beneficiario')"
        )
    if not consultas:
        return set()
    return {
        str(row[0])
        for row in con.execute(" UNION ".join(consultas))
        if row[0] is not None
    }


def _codigos_municipios_por_tabela(con, tabela):
    if tabela not in {"beneficio_mensal", "beneficiario"}:
        raise ValueError(f"Tabela municipal inválida: {tabela}")
    tabelas = {
        row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if tabela not in tabelas:
        return set()
    return {
        str(row[0])
        for row in con.execute(
            f"SELECT DISTINCT codigo_ibge FROM {tabela}"
        )
        if row[0] is not None
    }


@app.get("/api/municipios")
def listar_municipios():
    municipios, ufs = carregar_municipios(PASTA_DADOS)
    codigos_com_dados = set()
    codigos_com_agregados = set()
    codigos_com_beneficiarios = set()
    if os.path.isfile(DB_PADRAO):
        con = sqlite3.connect(DB_PADRAO)
        try:
            codigos_com_dados = _codigos_municipios_com_beneficios(con)
            codigos_com_agregados = _codigos_municipios_por_tabela(
                con, "beneficio_mensal")
            codigos_com_beneficiarios = _codigos_municipios_por_tabela(
                con, "beneficiario")
        finally:
            con.close()
    municipios_com_dados = [
        municipio for municipio in municipios
        if municipio["codigo_ibge"] in codigos_com_dados
    ]
    return {
        "municipios": municipios,
        "ufs": ufs,
        "codigos_municipios_com_dados": [
            municipio["codigo_ibge"] for municipio in municipios_com_dados
        ],
        "codigos_municipios_com_agregados": [
            municipio["codigo_ibge"] for municipio in municipios
            if municipio["codigo_ibge"] in codigos_com_agregados
        ],
        "codigos_municipios_com_beneficiarios": [
            municipio["codigo_ibge"] for municipio in municipios
            if municipio["codigo_ibge"] in codigos_com_beneficiarios
        ],
    }


def _atualizar_status_cnpj(**valores):
    with _status_cnpj_lock:
        if _status_cnpj is not None:
            etapa = valores.get("etapa")
            if etapa and etapa != _status_cnpj.get("etapa"):
                _status_cnpj["inicio_etapa"] = time.monotonic()
            _status_cnpj.update(valores)
            _status_cnpj["tempo_decorrido"] = round(
                time.monotonic() - _status_cnpj["inicio"], 1)


def _executar_coleta_cnpj(codigo_ibge, municipio, uf):
    try:
        registros = coletar_dados_municipio(
            uf,
            municipio,
            os.path.join(BASE, "utils"),
            on_progress=lambda progresso: _atualizar_status_cnpj(**progresso),
        )
        falhas = sum(
            registro.get("brasilapi_status") == 0 for registro in registros)
        if falhas:
            raise RuntimeError(
                f"{falhas} empresas não foram enriquecidas por falha na fonte."
            )

        con = init_db(DB_PADRAO)
        try:
            resumo = salvar_registros_cnpj(
                con, registros, codigo_ibge, municipio, uf,
                "Casa dos Dados + BrasilAPI",
                substituir_municipio=True,
            )
        finally:
            con.close()
        _atualizar_status_cnpj(
            mensagem="Coleta de CNPJs concluída",
            etapa="concluida",
            concluido=True,
            erro=None,
            **resumo,
        )
    except Exception as erro:
        _atualizar_status_cnpj(
            mensagem="Falha ao coletar CNPJs",
            etapa="erro",
            concluido=True,
            erro=str(erro),
        )


@app.post("/api/cnpj/coletar", status_code=202)
def iniciar_coleta_cnpj(
        req: CnpjColetaRequest,
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token")):
    global _status_cnpj
    _ = x_admin_token
    municipios, _ = carregar_municipios(PASTA_DADOS)
    municipio = next(
        (item for item in municipios
         if item["codigo_ibge"] == req.codigo_ibge),
        None,
    )
    if municipio is None:
        raise HTTPException(status_code=404, detail="Município não encontrado.")

    with _status_cnpj_lock:
        if _status_cnpj and not _status_cnpj.get("concluido"):
            raise HTTPException(
                status_code=409,
                detail="Já existe uma coleta de CNPJs em andamento.",
            )
        inicio = time.monotonic()
        _status_cnpj = {
            "codigo_ibge": req.codigo_ibge,
            "municipio": municipio["nome"],
            "uf": municipio["uf"],
            "mensagem": "Preparando coleta de CNPJs",
            "etapa": "iniciando",
            "empresas": 0,
            "total": 0,
            "processadas": 0,
            "pendentes": 0,
            "tempo_decorrido": 0,
            "inicio": inicio,
            "inicio_etapa": inicio,
            "concluido": False,
            "erro": None,
        }

    threading.Thread(
        target=_executar_coleta_cnpj,
        args=(req.codigo_ibge, municipio["nome"], municipio["uf"]),
        daemon=True,
        name=f"coleta-cnpj-{req.codigo_ibge}",
    ).start()
    return {"iniciada": True, "codigo_ibge": req.codigo_ibge}


@app.post("/api/cnpj/importar-csv")
def importar_csv_municipio_cnpj(
        req: CnpjColetaRequest,
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token")):
    _ = x_admin_token
    municipios, _ = carregar_municipios(PASTA_DADOS)
    municipio = next(
        (item for item in municipios
         if item["codigo_ibge"] == req.codigo_ibge),
        None,
    )
    if municipio is None:
        raise HTTPException(status_code=404, detail="Município não encontrado.")

    sem_acentos = unicodedata.normalize("NFKD", municipio["nome"])
    slug = "".join(
        caractere for caractere in sem_acentos
        if not unicodedata.combining(caractere)
    ).upper()
    slug = re.sub(r"[^A-Z0-9]+", "_", slug).strip("_")
    caminho = os.path.join(
        BASE, "utils", f"cnpj_{slug}_{municipio['uf']}.csv")
    if not os.path.isfile(caminho):
        raise HTTPException(
            status_code=404,
            detail=f"Não existe CSV local de CNPJ para {municipio['nome']}/{municipio['uf']}.",
        )

    con = init_db(DB_PADRAO)
    try:
        resumo = importar_csv_cnpj(
            con, caminho, req.codigo_ibge, municipio["nome"], municipio["uf"])
        return {**resumo, "origem": os.path.basename(caminho)}
    except (OSError, ValueError) as erro:
        raise HTTPException(
            status_code=422,
            detail=f"Não foi possível importar o CSV: {erro}",
        ) from erro
    finally:
        con.close()


def _situacoes_cadastrais_param(valor: str) -> list[str]:
    return list(dict.fromkeys(
        situacao.strip()
        for situacao in valor.split(",")
        if situacao.strip()
    ))


@app.get("/api/cnpj/empresas")
def listar_empresas_municipio(
        codigo_ibge: str,
        busca: str = "",
        capital_min: Optional[float] = None,
        capital_max: Optional[float] = None,
        pagina: int = 1,
        por_pagina: int = 50,
        situacoes_cadastrais: str = ""):
    con = init_db(DB_PADRAO)
    try:
        return listar_empresas_cnpj(
            con,
            codigo_ibge,
            busca=busca,
            capital_min=capital_min,
            capital_max=capital_max,
            pagina=pagina,
            por_pagina=por_pagina,
            situacoes_cadastrais=_situacoes_cadastrais_param(
                situacoes_cadastrais),
        )
    finally:
        con.close()


@app.get("/api/cnpj/empresas/export")
def exportar_empresas_municipio(
        codigo_ibge: str,
        busca: str = "",
        capital_min: Optional[float] = None,
        capital_max: Optional[float] = None,
        formato: str = "csv",
        situacoes_cadastrais: str = ""):
    con = init_db(DB_PADRAO)
    try:
        dados = listar_empresas_cnpj(
            con,
            codigo_ibge,
            busca=busca,
            capital_min=capital_min,
            capital_max=capital_max,
            pagina=1,
            por_pagina=100000,
            situacoes_cadastrais=_situacoes_cadastrais_param(
                situacoes_cadastrais),
        )
        registros = dados["resultados"]
        if not registros:
            registros = [{"cnpj": "", "razao_social": "", "nome_fantasia": "", "situacao_cadastral": "", "capital_social": "", "cnae_fiscal": "", "cnae_descricao": "", "porte": "", "endereco": "", "logradouro": "", "numero": "", "complemento": "", "bairro": "", "cep": "", "telefone": ""}]
        df = pd.DataFrame(registros)
        nome_municipio = "municipio"
        municipios, _ = carregar_municipios(PASTA_DADOS)
        municipio = next((m for m in municipios if str(m["codigo_ibge"]) == str(codigo_ibge)), None)
        if municipio:
            nome_municipio = municipio["nome"]
        safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", nome_municipio).strip("_") or "municipio"
        filename_base = f"empresas_{safe_name}_{codigo_ibge}"
        if formato.lower() == "xlsx":
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df.to_excel(writer, index=False)
            buffer.seek(0)
            return StreamingResponse(
                buffer,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename={filename_base}.xlsx"},
            )
        output = io.StringIO()
        df.to_csv(output, index=False, sep=';')
        payload = output.getvalue().encode("utf-8")
        return Response(
            payload,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.csv"},
        )
    finally:
        con.close()


_LIMIAR_RELATORIO_CNPJ = 5


def _resumo_beneficios_cnpj(codigo_ibge):
    municipios, _ = carregar_municipios(PASTA_DADOS)
    por_codigo = {
        str(municipio["codigo_ibge"]): municipio
        for municipio in municipios
    }
    con = init_db(DB_PADRAO)
    try:
        grupos = resumir_beneficios_cnpj(con, codigo_ibge)
    finally:
        con.close()

    divulgaveis = []
    for grupo in grupos:
        if grupo["beneficiarios"] < _LIMIAR_RELATORIO_CNPJ:
            continue
        municipio = por_codigo.get(grupo["codigo_ibge"], {})
        divulgaveis.append({
            **grupo,
            "municipio": municipio.get("nome", grupo["codigo_ibge"]),
            "uf": municipio.get("uf", ""),
        })
    return {
        "municipios_outros": [
            grupo for grupo in divulgaveis
            if grupo["codigo_ibge"] != str(codigo_ibge)
        ],
        "grupos": divulgaveis,
    }


@app.get("/api/cnpj/beneficios")
def consultar_beneficios_cnpj(codigo_ibge: str):
    return _resumo_beneficios_cnpj(codigo_ibge)["municipios_outros"]


@app.get("/api/cnpj/relatorio")
def exportar_relatorio_cnpj(codigo_ibge: str):
    resumo = _resumo_beneficios_cnpj(codigo_ibge)
    municipios, _ = carregar_municipios(PASTA_DADOS)
    municipio_origem = next(
        (item for item in municipios
         if str(item["codigo_ibge"]) == str(codigo_ibge)),
        None,
    )
    if municipio_origem is None:
        raise HTTPException(status_code=404, detail="Município não encontrado.")

    con = init_db(DB_PADRAO)
    try:
        totais = con.execute(
            """
            SELECT COUNT(DISTINCT e.cnpj), COUNT(DISTINCT s.id)
            FROM cnpj_empresa e
            LEFT JOIN cnpj_socio s ON s.cnpj=e.cnpj
            WHERE e.codigo_ibge=?
            """,
            (str(codigo_ibge),),
        ).fetchone()
    finally:
        con.close()

    output = io.StringIO(newline="")
    escritor = csv.writer(output, delimiter=";", lineterminator="\n")
    escritor.writerow([
        "codigo_ibge_cnpj", "municipio_cnpj", "uf_cnpj",
        "empresas_cadastradas", "socios_cadastrados",
        "codigo_ibge_beneficio", "municipio_beneficio", "uf_beneficio",
        "programa", "beneficiarios_correspondencia_forte",
        "competencia_inicial", "competencia_final",
    ])
    for grupo in resumo["grupos"]:
        escritor.writerow([
            codigo_ibge, municipio_origem["nome"], municipio_origem["uf"],
            totais[0], totais[1], grupo["codigo_ibge"], grupo["municipio"],
            grupo["uf"], grupo["beneficio"], grupo["beneficiarios"],
            grupo["periodo_inicial"], grupo["periodo_final"],
        ])

    safe_municipio = re.sub(
        r"[^a-zA-Z0-9]+", "_", municipio_origem["nome"]).strip("_")
    return Response(
        output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                f"attachment; filename=relatorio_cnpj_{safe_municipio}.csv",
        },
    )


@app.get("/api/cnpj/grafo")
def grafo_cnpj_municipio(codigo_ibge: str, limite: int = 200):
    con = init_db(DB_PADRAO)
    try:
        grafo = criar_grafo_cnpj(con, codigo_ibge, limite=max(20, min(int(limite), 500)))
        return parse_graph_to_vis(grafo)
    finally:
        con.close()


@app.get("/api/cnpj/status")
def status_coleta_cnpj(codigo_ibge: str):
    with _status_cnpj_lock:
        if not _status_cnpj or _status_cnpj["codigo_ibge"] != codigo_ibge:
            return {"status": None}
        status = {
            chave: valor for chave, valor in _status_cnpj.items()
            if chave not in {"inicio", "inicio_etapa"}
        }
        agora = time.monotonic()
        status["tempo_decorrido"] = round(agora - _status_cnpj["inicio"], 1)
        status["tempo_etapa"] = round(
            agora - _status_cnpj.get("inicio_etapa", _status_cnpj["inicio"]), 1)
        return {"status": status}


@app.get("/api/cnpj/cruzamento")
def consultar_cruzamento_cnpj(
        codigo_ibge: str, pagina: int = 1, por_pagina: int = 50,
        busca: str = "", capital_min: Optional[float] = None,
        capital_max: Optional[float] = None,
        situacoes_cadastrais: str = "", programa: str = ""):
    if pagina < 1:
        raise HTTPException(status_code=422, detail="A página deve ser positiva.")
    if por_pagina < 1 or por_pagina > 200:
        raise HTTPException(
            status_code=422,
            detail="O tamanho da página deve estar entre 1 e 200.",
        )
    con = init_db(DB_PADRAO)
    try:
        return cruzar_beneficiarios_cnpj(
            con,
            codigo_ibge,
            pagina=pagina,
            por_pagina=por_pagina,
            busca=busca,
            capital_min=capital_min,
            capital_max=capital_max,
            situacoes_cadastrais=_situacoes_cadastrais_param(
                situacoes_cadastrais),
            programa=programa,
        )
    finally:
        con.close()


@app.get("/api/cnpj/cruzamento/relatorio.pdf")
def exportar_relatorio_cruzamento_pdf(
        codigo_ibge: str, situacoes_cadastrais: str = "", busca: str = "",
        capital_min: Optional[float] = None,
        capital_max: Optional[float] = None, programa: str = ""):
    situacoes_selecionadas = _situacoes_cadastrais_param(
        situacoes_cadastrais)
    municipios, _ = carregar_municipios(PASTA_DADOS)
    municipio = next(
        (item for item in municipios
         if str(item["codigo_ibge"]) == str(codigo_ibge)),
        None,
    )
    if municipio is None:
        raise HTTPException(status_code=404, detail="Município não encontrado.")

    con = init_db(DB_PADRAO)
    try:
        cruzamento = obter_cruzamento_beneficiarios_cnpj(
            con,
            codigo_ibge,
            detalhado=True,
            situacoes_cadastrais=situacoes_selecionadas,
            busca=busca,
            capital_min=capital_min,
            capital_max=capital_max,
            programa=programa,
        )
    finally:
        con.close()

    pdf = gerar_relatorio_cruzamento_pdf(
        municipio["nome"],
        municipio["uf"],
        codigo_ibge,
        cruzamento,
        situacoes_selecionadas,
        {
            "busca": busca,
            "capital_min": capital_min,
            "capital_max": capital_max,
            "programa": programa,
        },
    )
    safe_municipio = re.sub(
        r"[^a-zA-Z0-9]+", "_", municipio["nome"]).strip("_") or "municipio"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f"attachment; filename=relatorio_beneficiarios_socios_{safe_municipio}.pdf",
        },
    )


@app.get("/")
def serve_frontend():
    caminho_html = os.path.join(PASTA_FRONTEND, "index.html")
    if os.path.exists(caminho_html):
        return FileResponse(caminho_html)
    return JSONResponse(
        status_code=503,
        content={
            "erro": "Frontend de produção ainda não compilado.",
            "instrucoes": "Execute npm install e npm run build.",
        },
    )


if os.path.isdir(os.path.join(PASTA_FRONTEND, "assets")):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(PASTA_FRONTEND, "assets")),
        name="frontend-assets",
    )