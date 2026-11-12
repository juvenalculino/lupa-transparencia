#!/usr/bin/env python3
"""Cliente da API do Portal da Transparencia + persistencia em SQLite.

Uso:
    from coleta import PortalClient, init_db, dados_agregado_existem, ...

A chave da API NAO fica salva em arquivo: passe via argumento ou variavel
de ambiente PORTAL_API_KEY.
"""
import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Lock
from zoneinfo import ZoneInfo

BASE_URL = "https://api.portaldatransparencia.gov.br/api-de-dados"
FUSO_API = ZoneInfo("America/Sao_Paulo")
ENDPOINTS_RESTRITOS = frozenset({
    "documentos-por-favorecido",
    "bolsa-familia-disponivel-por-cpf-ou-nis",
})

# Endpoints de agregado mensal por municipio (valor + quantidadeBeneficiados)
PROGRAMAS_AGREGADO = {
    "Garantia Safra": "safra-por-municipio",
    "BPC": "bpc-por-municipio",
    "Bolsa Familia": "bolsa-familia-por-municipio",
    "Novo Bolsa Familia": "novo-bolsa-familia-por-municipio",
    "Auxilio Brasil": "auxilio-brasil-por-municipio",
    "PETI": "peti-por-municipio",
    "Seguro Defeso": "seguro-defeso-por-municipio",
    "Auxilio Emergencial": "auxilio-emergencial-por-municipio",
}

# Endpoints de beneficiarios (paginados, um registro por pessoa)
PROGRAMAS_BENEFICIARIO = {
    "Garantia Safra": "safra-beneficiario-por-municipio",
    "BPC": "bpc-beneficiario-por-municipio",
    "PETI": "peti-beneficiario-por-municipio",
    "Seguro Defeso": "seguro-defeso-beneficiario-por-municipio",
    "Auxilio Emergencial": "auxilio-emergencial-beneficiario-por-municipio",
    "Bolsa Familia (disponivel)": "bolsa-familia-disponivel-beneficiario-por-municipio",
    "Bolsa Familia (sacado)": "bolsa-familia-sacado-beneficiario-por-municipio",
    "Novo Bolsa Familia (sacado)": "novo-bolsa-familia-sacado-beneficiario-por-municipio",
    "Auxilio Brasil (sacado)": "auxilio-brasil-sacado-beneficiario-por-municipio",
}


def _limite_por_minuto():
    """Retorna o limite geral por minuto conforme o horário de Brasília."""
    return 700 if 0 <= datetime.now(FUSO_API).hour < 6 else 400


def _endpoint_restrito(endpoint):
    """Indica se o caminho corresponde a um endpoint com limite especial."""
    caminho = urllib.parse.urlsplit(endpoint).path.rstrip("/").split("/")[-1]
    return caminho in ENDPOINTS_RESTRITOS


def _segundos_retry_after(valor):
    """Converte Retry-After em segundos; usa 60s se o valor não for válido."""
    if valor is None:
        return 60.0
    try:
        return max(0.0, float(valor))
    except ValueError:
        try:
            data = parsedate_to_datetime(valor)
            if data.tzinfo is None:
                data = data.replace(tzinfo=timezone.utc)
            return max(0.0, (data - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 60.0


class PortalClient:
    """Cliente da API com controle compartilhado de chamadas por chave."""

    _rate_lock = Lock()
    _requests_by_key = {}

    def __init__(self, chave_api, margem=0.95, timeout=60):
        """Inicializa o cliente com uma ou mais chaves e margem de segurança."""
        if isinstance(chave_api, str):
            chaves = [chave_api]
        else:
            chaves = list(chave_api or [])
        if not chaves:
            fallback_key = os.environ.get("PORTAL_API_KEY", "")
            chaves = [fallback_key] if fallback_key else []
        self.chaves = list(dict.fromkeys(key for key in chaves if key))
        if not self.chaves:
            raise ValueError("Informe a chave da API (argumento ou PORTAL_API_KEY).")
        if not 0 < margem <= 1:
            raise ValueError("A margem deve ser maior que 0 e menor ou igual a 1.")
        self.margem = margem
        self.timeout = timeout
        self._indice_chave = 0
        self.chave = self.chaves[0]
        self._identificador_chave = hashlib.sha256(
            self.chave.encode("utf-8")).hexdigest()
        self.total_requisicoes = 0
        self.tempo_total_ms = 0.0

    def _usar_chave(self, chave):
        self.chave = chave
        self._identificador_chave = hashlib.sha256(
            chave.encode("utf-8")).hexdigest()

    def _esperar_ritmo(self, endpoint):
        """Reserva um horário que respeita os limites móveis de 60 segundos."""
        restrito = _endpoint_restrito(endpoint)
        limite_restrito = max(1, int(180 * self.margem))
        while True:
            with self._rate_lock:
                agora = time.monotonic()
                limite_geral = max(
                    1, int(_limite_por_minuto() * self.margem))
                requisicoes = self._requests_by_key.setdefault(
                    self._identificador_chave, deque())
                while requisicoes and requisicoes[0][0] <= agora - 60:
                    requisicoes.popleft()

                restritas = [momento for momento, eh_restrita in requisicoes
                             if eh_restrita]
                esperas = []
                if len(requisicoes) >= limite_geral:
                    esperas.append(requisicoes[0][0] + 60)
                if requisicoes:
                    intervalo_geral = 60 / limite_geral
                    esperas.append(requisicoes[-1][0] + intervalo_geral)
                if restrito and len(restritas) >= limite_restrito:
                    esperas.append(restritas[0] + 60)
                if restrito and restritas:
                    intervalo_restrito = 60 / limite_restrito
                    esperas.append(restritas[-1] + intervalo_restrito)

                liberar_em = max(esperas, default=agora)
                if liberar_em <= agora:
                    requisicoes.append((agora, restrito))
                    return
                aguardar = liberar_em - agora
            time.sleep(aguardar)

    def get(self, endpoint, params, tentativas=5):
        """Faz GET com retry; retorna a lista JSON e a duração da resposta."""
        if tentativas < 1:
            raise ValueError("O número de tentativas deve ser pelo menos 1.")
        url = f"{BASE_URL}/{endpoint}?{urllib.parse.urlencode(params)}"
        ultimo_erro = None
        quantidade_chaves = len(self.chaves)
        indices = [
            (self._indice_chave + deslocamento) % quantidade_chaves
            for deslocamento in range(quantidade_chaves)
        ]
        for indice in indices:
            self._indice_chave = indice
            self._usar_chave(self.chaves[indice])
            for tentativa in range(tentativas):
                self._esperar_ritmo(endpoint)
                req = urllib.request.Request(url, headers={
                    "chave-api-dados": self.chave,
                    "Accept": "application/json",
                    "User-Agent": "portal-beneficios/1.0",
                })
                t0 = time.perf_counter()
                self.total_requisicoes += 1
                corpo = b""
                content_type = "desconhecido"
                try:
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        headers = getattr(resp, "headers", None)
                        if headers is not None:
                            content_type = headers.get(
                                "Content-Type", content_type)
                        corpo = resp.read()
                    ms = (time.perf_counter() - t0) * 1000
                    self.tempo_total_ms += ms
                    return json.loads(corpo), ms
                except urllib.error.HTTPError as e:
                    ms = (time.perf_counter() - t0) * 1000
                    self.tempo_total_ms += ms
                    ultimo_erro = f"HTTP {e.code}"
                    if e.code == 429:
                        if len(indices) > 1:
                            break
                        valor_retry = (e.headers.get("Retry-After")
                                       if e.headers else None)
                        espera = _segundos_retry_after(valor_retry)
                    else:
                        espera = 2 * (2 ** tentativa)
                    if tentativa + 1 < tentativas:
                        time.sleep(espera)
                except json.JSONDecodeError as e:
                    ms = (time.perf_counter() - t0) * 1000
                    self.tempo_total_ms += ms
                    ultimo_erro = (
                        f"JSONDecodeError (Content-Type: {content_type}; "
                        f"{len(corpo)} bytes; linha {e.lineno}, "
                        f"coluna {e.colno})"
                    )
                    if tentativa + 1 < tentativas:
                        time.sleep(2 * (2 ** tentativa))
                except Exception as e:          # timeout / rede
                    ms = (time.perf_counter() - t0) * 1000
                    self.tempo_total_ms += ms
                    ultimo_erro = f"{type(e).__name__}"
                    if tentativa + 1 < tentativas:
                        time.sleep(2 * (2 ** tentativa))
        raise RuntimeError(f"Falhou apos {tentativas} tentativas ({url}): {ultimo_erro}")

    def paginar(self, endpoint, params, on_pagina=None):
        """Busca páginas sucessivas até a API retornar uma lista vazia."""
        pagina, todos, tempos = 1, [], []
        while True:
            dados, ms = self.get(endpoint, {**params, "pagina": pagina})
            tempos.append(ms)
            if not dados:
                break
            todos.extend(dados)
            if on_pagina:
                on_pagina(pagina, len(dados), ms)
            pagina += 1
        return todos, tempos


# ------------------------------------------------- vigencia ----
# Vigencia de cada programa (inicio AAAAMM, fim AAAAMM ou None se ativo).
PROGRAMAS_VIGENCIA = {
    "Bolsa Familia": ("200310", "202110"),       # 1a versao
    "Auxilio Emergencial": ("202004", "202110"),
    "Auxilio Brasil": ("202111", "202302"),
    "Novo Bolsa Familia": ("202303", None),      # 2a versao, em atividade
    "BPC": ("199601", None),
    "PETI": ("199601", "200512"),
    "Seguro Defeso": ("199101", None),
    "Garantia Safra": ("200201", None),
}

_MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun",
             "jul", "ago", "set", "out", "nov", "dez"]


def fmt_mes(aaaamm):
    """Formata um período AAAAMM como mês/ano abreviado em português."""
    return f"{_MESES_PT[int(aaaamm[4:6]) - 1]}/{aaaamm[:4]}"


def vigencia_programa(beneficio):
    """Retorna a vigência do programa base, inclusive em modalidades."""
    programa_base = beneficio.split(" (", 1)[0]
    return PROGRAMAS_VIGENCIA[programa_base]


def rotulo_programa(beneficio):
    """Monta o rótulo do benefício incluindo seu período de vigência."""
    ini, fim = vigencia_programa(beneficio)
    return f"{beneficio} ({fmt_mes(ini)} - {fmt_mes(fim) if fim else 'atual'})"


def programa_ativo(beneficio, mes_ano):
    """(ativo, mensagem). Mensagem explica a vigencia se inativo."""
    ini, fim = vigencia_programa(beneficio)
    periodo = f"{fmt_mes(ini)} a {fmt_mes(fim) if fim else 'atual'}"
    if mes_ano < ini:
        return False, (f"O {beneficio} so passou a existir em {fmt_mes(ini)} "
                       f"(vigencia: {periodo}).")
    if fim and mes_ano > fim:
        return False, (f"O {beneficio} foi encerrado em {fmt_mes(fim)} "
                       f"(vigencia: {periodo}).")
    return True, ""


def meses_validos_ano(beneficio, ano):
    """Meses do ano em que o programa existiu (para nao buscar a toa)."""
    ini, fim = vigencia_programa(beneficio)
    return [f"{m:02d}" for m in range(1, 13)
            if ini <= f"{ano}{m:02d}" <= (fim or "999912")]


def meses_agregado_faltantes(con, beneficio, ano, codigo_ibge, meses):
    """Meses validos que ainda nao estao salvos no banco."""
    if not meses:
        return []
    tem = {r[0] for r in con.execute(
        "SELECT substr(mes_ano,5,2) FROM beneficio_mensal "
        "WHERE beneficio=? AND substr(mes_ano,1,4)=? AND codigo_ibge=?",
        (beneficio, str(ano), codigo_ibge))}
    return [m for m in meses if m not in tem]


# ---------------------------------------------------------- municipios ----
_MUN_CACHE = {}


def carregar_municipios(pasta_dados):
    """(municipios, ufs) a partir dos JSONs do IBGE. Resultado em cache."""
    if pasta_dados in _MUN_CACHE:
        return _MUN_CACHE[pasta_dados]

    def _load(nome):
        """Lê um arquivo JSON de dados do IBGE."""
        with open(os.path.join(pasta_dados, nome), encoding="utf-8-sig") as f:
            return json.load(f)

    estados = {e["codigo_uf"]: e["uf"] for e in _load("estados.json")}
    muns = sorted(
        ({"codigo_ibge": str(m["codigo_ibge"]), "nome": m["nome"],
          "uf": estados.get(m["codigo_uf"], "?")}
         for m in _load("municipios.json")),
        key=lambda x: (x["uf"], x["nome"]))
    ufs = sorted({m["uf"] for m in muns})
    _MUN_CACHE[pasta_dados] = (muns, ufs)
    return muns, ufs


# ---------------------------------------------------------------- banco ----
SCHEMA = """
CREATE TABLE IF NOT EXISTS municipio (
    codigo_ibge TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    uf TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS beneficio_mensal (
    beneficio TEXT NOT NULL,
    mes_ano TEXT NOT NULL,            -- AAAAMM
    codigo_ibge TEXT NOT NULL,
    valor REAL,
    qtd_beneficiados INTEGER,
    coletado_em TEXT NOT NULL,
    PRIMARY KEY (beneficio, mes_ano, codigo_ibge)
);
CREATE INDEX IF NOT EXISTS idx_beneficio_mensal_municipio
    ON beneficio_mensal (codigo_ibge);
CREATE TABLE IF NOT EXISTS beneficiario (
    beneficio TEXT NOT NULL,
    mes_ano TEXT NOT NULL,
    codigo_ibge TEXT NOT NULL,
    nis TEXT NOT NULL,
    nome TEXT,
    cpf_mascarado TEXT,
    valor REAL,
    extras TEXT,                      -- JSON com campos especificos do programa
    PRIMARY KEY (beneficio, mes_ano, codigo_ibge, nis)
);
CREATE INDEX IF NOT EXISTS idx_beneficiario_municipio_programa_mes_nis
    ON beneficiario (codigo_ibge, beneficio, mes_ano, nis);
CREATE INDEX IF NOT EXISTS idx_beneficiario_municipio_mes_programa_nis
    ON beneficiario (codigo_ibge, mes_ano, beneficio, nis);
CREATE INDEX IF NOT EXISTS idx_beneficiario_nis_municipio_programa
    ON beneficiario (nis, codigo_ibge, beneficio);
CREATE TABLE IF NOT EXISTS coleta_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quando TEXT NOT NULL,
    tipo TEXT NOT NULL,                -- 'agregado' | 'beneficiario'
    beneficio TEXT NOT NULL,
    mes_ano TEXT NOT NULL,             -- AAAAMM ou AAAA (ano)
    codigo_ibge TEXT NOT NULL,
    paginas INTEGER,
    registros INTEGER,
    requisicoes INTEGER,
    tempo_total_ms REAL
);
CREATE INDEX IF NOT EXISTS idx_coleta_log_tipo_municipio
    ON coleta_log (tipo, codigo_ibge);
CREATE TABLE IF NOT EXISTS cnpj_empresa (
    cnpj TEXT PRIMARY KEY,
    codigo_ibge TEXT NOT NULL,
    razao_social TEXT,
    nome_fantasia TEXT,
    situacao_cadastral TEXT,
    capital_social REAL,
    cnae_fiscal TEXT,
    cnae_descricao TEXT,
    porte TEXT,
    endereco TEXT,
    logradouro TEXT,
    numero TEXT,
    complemento TEXT,
    bairro TEXT,
    cep TEXT,
    telefone TEXT,
    atualizado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cnpj_empresa_municipio
    ON cnpj_empresa (codigo_ibge, cnpj);
CREATE TABLE IF NOT EXISTS cnpj_socio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj TEXT NOT NULL,
    socio_nome TEXT,
    socio_cpf_cnpj_mascarado TEXT,
    socio_qualificacao TEXT,
    socio_tipo TEXT,
    socio_data_entrada TEXT,
    socio_faixa_etaria TEXT,
    UNIQUE (cnpj, socio_nome, socio_cpf_cnpj_mascarado, socio_qualificacao)
);
CREATE INDEX IF NOT EXISTS idx_cnpj_socio_empresa
    ON cnpj_socio (cnpj);
CREATE TABLE IF NOT EXISTS cnpj_coleta (
    codigo_ibge TEXT PRIMARY KEY,
    coletado_em TEXT NOT NULL,
    origem TEXT NOT NULL,
    empresas INTEGER NOT NULL,
    socios INTEGER NOT NULL
);
"""


def init_db(caminho):
    """Cria as tabelas necessárias e devolve uma conexão SQLite."""
    con = sqlite3.connect(caminho)
    con.executescript(SCHEMA)
    migrar_beneficiarios_novo_bolsa_familia(con)
    con.commit()
    return con


def migrar_beneficiarios_novo_bolsa_familia(con):
    """Preenche os campos tabulares dos registros antigos salvos em extras."""
    beneficio = "Novo Bolsa Familia (sacado)"
    registros = con.execute(
        """
        SELECT mes_ano, codigo_ibge, nis, extras
        FROM beneficiario
        WHERE beneficio=? AND nis LIKE 'sem-nis-%'
          AND CASE WHEN json_valid(extras)
              THEN json_extract(
                  extras, '$.beneficiarioNovoBolsaFamilia.nis') IS NOT NULL
              ELSE 0
          END
        """,
        (beneficio,),
    ).fetchall()
    for mes_ano, codigo_ibge, nis_antigo, extras in registros:
        item = json.loads(extras)
        nis, nome, cpf_masc, valor = _beneficiario_campos(item)
        if not nis:
            continue
        con.execute(
            """
            UPDATE beneficiario
            SET nis=?, nome=?, cpf_mascarado=?, valor=?
            WHERE beneficio=? AND mes_ano=? AND codigo_ibge=? AND nis=?
            """,
            (nis, nome, cpf_masc, valor, beneficio, mes_ano,
             codigo_ibge, nis_antigo),
        )


def garantir_municipio(con, codigo_ibge, nome, uf):
    """Insere o município no catálogo se ainda não estiver cadastrado."""
    con.execute("INSERT OR IGNORE INTO municipio VALUES (?,?,?)",
                (codigo_ibge, nome, uf))


def agregado_existe(con, beneficio, ano, codigo_ibge):
    """True se ja houver algum mes do ano salvo (para o aviso de duplicada)."""
    n = con.execute(
        "SELECT COUNT(*) FROM beneficio_mensal "
        "WHERE beneficio=? AND substr(mes_ano,1,4)=? AND codigo_ibge=?",
        (beneficio, str(ano), codigo_ibge)).fetchone()[0]
    return n > 0


def beneficiarios_existem(con, beneficio, mes_ano, codigo_ibge):
    """Indica se há registros de beneficiários para o período e município."""
    n = con.execute(
        "SELECT COUNT(*) FROM beneficiario "
        "WHERE beneficio=? AND mes_ano=? AND codigo_ibge=?",
        (beneficio, mes_ano, codigo_ibge)).fetchone()[0]
    return n > 0


def meses_beneficiarios_faltantes(con, beneficio, ano, codigo_ibge, meses):
    """Meses sem registros nem log de coleta para o programa e municipio."""
    if not meses:
        return []
    salvos = {
        r[0] for r in con.execute(
            """
            SELECT mes_ano FROM beneficiario
            WHERE beneficio=? AND substr(mes_ano,1,4)=? AND codigo_ibge=?
            UNION
            SELECT mes_ano FROM coleta_log
            WHERE tipo='beneficiario' AND beneficio=?
              AND substr(mes_ano,1,4)=? AND codigo_ibge=?
            """,
            (beneficio, str(ano), codigo_ibge,
             beneficio, str(ano), codigo_ibge),
        )
    }
    return [mes for mes in meses if f"{ano}{mes}" not in salvos]


def salvar_agregado(con, beneficio, mes_ano, codigo_ibge, valor, qtd):
    """Insere ou atualiza o valor agregado mensal do município."""
    con.execute(
        "INSERT OR REPLACE INTO beneficio_mensal VALUES (?,?,?,?,?,?)",
        (beneficio, mes_ano, codigo_ibge, valor, qtd,
         datetime.now().isoformat(timespec="seconds")))


def salvar_beneficiario(con, beneficio, mes_ano, codigo_ibge,
                        nis, nome, cpf_masc, valor, extras=None):
    """Insere ou atualiza o registro de uma pessoa beneficiária."""
    con.execute(
        "INSERT OR REPLACE INTO beneficiario VALUES (?,?,?,?,?,?,?,?)",
        (beneficio, mes_ano, codigo_ibge, nis, nome, cpf_masc, valor,
         json.dumps(extras or {}, ensure_ascii=False)))


def registrar_log(con, tipo, beneficio, mes_ano, codigo_ibge,
                  paginas, registros, requisicoes, tempo_ms):
    """Registra no banco o resumo de uma coleta concluída."""
    con.execute(
        "INSERT INTO coleta_log VALUES (NULL,?,?,?,?,?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), tipo, beneficio,
         mes_ano, codigo_ibge, paginas, registros, requisicoes, tempo_ms))


# ------------------------------------------------------------- coletas ----
def _beneficiario_campos(item):
    """Extrai (nis, nome, cpf_mascarado, valor) de qualquer DTO de beneficiario."""
    b = (item.get("beneficiario")
         or item.get("beneficiarioSafra")
         or item.get("beneficiarioNovoBolsaFamilia")
         or {})
    valor = item.get("valor")
    if valor is None:
        valor = item.get("valorSaque")
    return (b.get("nis") or "", b.get("nome") or "",
            b.get("cpfFormatado") or "", valor)


def _representante_legal(item):
    """Extrai os dados públicos do representante legal do DTO do BPC."""
    beneficiario = item.get("beneficiario") or {}
    representante = {
        "nome": beneficiario.get("nomeRepresentanteLegal"),
        "nis": beneficiario.get("nisRepresentanteLegal"),
        "cpf_mascarado": beneficiario.get("cpfRepresentanteLegalFormatado"),
    }
    return {campo: valor for campo, valor in representante.items() if valor}


def coletar_agregado_ano(client, con, beneficio, ano, codigo_ibge,
                         nome_mun, uf, meses=None, on_mes=None,
                         sobrescrever=False):
    """Busca valor+qtd de cada mes do ano e salva. Retorna estatisticas."""
    endpoint = PROGRAMAS_AGREGADO[beneficio]
    garantir_municipio(con, codigo_ibge, nome_mun, uf)
    meses = meses or [f"{m:02d}" for m in range(1, 13)]
    invalidos = [
        f"{ano}{mes}" for mes in meses
        if not programa_ativo(beneficio, f"{ano}{mes}")[0]
    ]
    if invalidos:
        raise ValueError(
            f"Competências fora da vigência de {beneficio}: "
            + ", ".join(invalidos)
        )
    requisicoes_antes = client.total_requisicoes
    tempo_antes = client.tempo_total_ms
    stats = {"meses_ok": 0, "requisicoes": 0, "tempo_ms": 0.0}
    for mes in meses:
        mes_ano = f"{ano}{mes}"
        dados, ms = client.get(endpoint,
                               {"mesAno": mes_ano, "codigoIbge": codigo_ibge,
                                "pagina": 1})
        for row in dados:   # normalmente 1 linha; soma se vier mais de um tipo
            salvar_agregado(con, beneficio, mes_ano, codigo_ibge,
                            row.get("valor"), row.get("quantidadeBeneficiados"))
            stats["meses_ok"] += 1
        if on_mes:
            on_mes(mes_ano, len(dados), ms)
    stats["requisicoes"] = client.total_requisicoes - requisicoes_antes
    stats["tempo_ms"] = client.tempo_total_ms - tempo_antes
    registrar_log(con, "agregado", beneficio, str(ano), codigo_ibge,
                  len(meses), stats["meses_ok"],
                  stats["requisicoes"], stats["tempo_ms"])
    con.commit()
    return stats


def coletar_beneficiarios(client, con, beneficio, mes_ano, codigo_ibge,
                          nome_mun, uf, on_pagina=None):
    """Percorre todas as paginas de beneficiarios e salva. Retorna estatisticas."""
    ativo, motivo = programa_ativo(beneficio, str(mes_ano))
    if not ativo:
        raise ValueError(motivo)
    endpoint = PROGRAMAS_BENEFICIARIO[beneficio]
    garantir_municipio(con, codigo_ibge, nome_mun, uf)
    req_antes = client.total_requisicoes
    ms_antes = client.tempo_total_ms
    pagina, total, tempos = 1, 0, []
    while True:
        dados, ms = client.get(endpoint, {"mesAno": mes_ano,
                                          "codigoIbge": codigo_ibge,
                                          "pagina": pagina})
        tempos.append(ms)
        if not dados:
            break
        for item in dados:
            nis, nome, cpf_masc, valor = _beneficiario_campos(item)
            extras = {k: v for k, v in item.items()
                      if k not in ("beneficiario", "beneficiarioSafra",
                                   "beneficiarioNovoBolsaFamilia",
                                   "municipio", "valor", "valorSaque")}
            representante = _representante_legal(item)
            if representante:
                extras["representanteLegal"] = representante
            salvar_beneficiario(con, beneficio, mes_ano, codigo_ibge,
                                nis or f"sem-nis-{item.get('id')}",
                                nome, cpf_masc, valor, extras)
        total += len(dados)
        if on_pagina:
            on_pagina(pagina, len(dados), ms)
        pagina += 1
    stats = {"registros": total,
             "paginas": len(tempos),
             "requisicoes": client.total_requisicoes - req_antes,
             "tempo_ms": client.tempo_total_ms - ms_antes}
    registrar_log(con, "beneficiario", beneficio, mes_ano, codigo_ibge,
                  stats["paginas"], total,
                  stats["requisicoes"], stats["tempo_ms"])
    con.commit()
    return stats
