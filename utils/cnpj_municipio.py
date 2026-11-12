#!/usr/bin/env python3
"""CNPJs de um municipio via Casa dos Dados + enriquecimento via BrasilAPI.

Versao 2 — o que mudou em relacao a v1 (e por que ela era lenta):

1. SEM subprocess/curl por requisicao. A v1 criava um processo `curl` novo
   para cada CNPJ (fork + TLS handshake + teardown, ~1 s cada) e ainda
   dormia 0,3 s entre eles: 1.872 CNPJs = 30-40 min so no enriquecimento.
   A v2 usa `requests.Session` com keep-alive: a conexao TLS e reutilizada
   e o custo por requisicao cai para o tempo de rede puro.
   (O problema antigo do urllib era o User-Agent padrao "python-urllib",
   que o servidor da Casa dos Dados derruba. Com UA de navegador o
   requests funciona — testado em 29/10/2026 para FATIMA/BA.)
2. PARALELISMO no enriquecimento. BrasilAPI e consultada com
   ThreadPoolExecutor (padrao 10 workers). Nao e CPU-bound, e I/O-bound:
   enquanto uma thread espera a rede, as outras trabalham. Medido em
   29/10/2026 (50 CNPJs de Fatima): 1 worker = 1,6/s (proj. ~20 min);
   10 workers = 21,5/s (proj. ~1,5 min) sem nenhum 429; 20 workers deu a
   mesma velocidade mas 7/50 respostas 429 — ou seja, 10 e o ponto otimo,
   acima disso a API estrangula sem ganhar nada. Retry com backoff trata
   o 429 que eventualmente aparecer.
3. Casa dos Dados: continua sequencial (obrigatorio — cada rodada depende
   da lista `excluir` da anterior, e o endpoint devolve so 20 CNPJs por
   rodada), mas o sleep entre rodadas caiu de 3 s para 0,3 s e o payload
   `excluir` vai no corpo JSON (na v1 ele ia como argumento de linha de
   comando do curl, o que estourou o limite do Windows com 1.872 CNPJs).
4. CACHE resumable de verdade. Cada CNPJ enriquecido e gravado na hora
   num arquivo .jsonl (uma linha por CNPJ). Se o processo cair, re-rodar
   pula tudo que ja esta no cache — a v1 so reaproveitava o CSV final e
   reprocessava a lista inteira na memoria.
5. NOVOS CAMPOS (BrasilAPI): endereco completo da empresa e CPF/CNPJ
   mascarado do socio.
   - CPF COMPLETO NAO EXISTE em API publica gratuita: a Receita mascara
     (`***500765**`). Qualquer fonte que prometa CPF cheio de socio esta
     fora do dado publico. O campo `cnpj_cpf_do_socio` da BrasilAPI e o
     maximo legal/publico disponivel.
   - ENDERECO DO SOCIO NAO EXISTE na BrasilAPI: o endereco devolvido e o
     da empresa (logradouro/numero/bairro/CEP/municipio/UF). Nao inventar
     endereco de socio a partir do da empresa.
   - Correcao de bug da v1: `tipo_socio` nao vem mais no QSA da BrasilAPI,
     entao todo socio caia como "PF". A v2 usa `identificador_de_socio`
     (1 = PJ, 2 = PF), com fallback para o campo antigo.

Uso:
    pip install requests          # se ainda nao tiver
    python3 cnpj_municipio_v2.py BA FATIMA
    python3 cnpj_municipio_v2.py BA FATIMA --workers 10 --limite 100  # teste
Saida:
    cnpj_FATIMA_BA.csv             (delimitador ;, UTF-8 com BOM p/ Excel)
    cnpj_FATIMA_BA.checkpoint.json (lista da Casa dos Dados)
    cnpj_FATIMA_BA.enriquecido.jsonl (cache resumable do enriquecimento)
"""
import argparse
import csv
import json
import os
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("Falta o pacote 'requests'. Instale com: pip install requests")

CDD_URL = "https://api.casadosdados.com.br/v5/public/cnpj/pesquisa"
BRASILAPI = "https://brasilapi.com.br/api/cnpj/v1/{}"
UA = "Mozilla/5.0 (X11; Linux x86_64) EyeBrasil/2.0 (pesquisa dados publicos)"

_local = threading.local()


def sessao():
    """Uma Session por thread (requests.Session nao e thread-safe p/ uso
    concorrente na mesma instancia; thread-local resolve sem custo)."""
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept": "application/json"})
        _local.s = s
    return s


def post_casa(sess, payload, tentativas=8):
    for t in range(tentativas):
        try:
            r = sess.post(CDD_URL, json=payload, timeout=60)
            if r.status_code == 429:
                espera = int(r.headers.get("Retry-After", 2 ** t))
                print(f"    Casa 429: esperando {espera}s", flush=True)
                time.sleep(min(espera, 60))
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if t == tentativas - 1:
                raise
            espera = min(2 ** t, 30)
            print(f"    Casa retry {t+1}/{tentativas} em {espera}s ({e})", flush=True)
            time.sleep(espera)
    raise RuntimeError("Casa dos Dados: sem resposta")


def buscar_cnpjs(uf, municipio, chk, on_progress=None):
    vistos = {}
    if os.path.exists(chk):
        vistos = {e["cnpj"]: e for e in json.load(open(chk, encoding="utf-8"))}
        print(f"retomando lista: {len(vistos)} ja coletados", flush=True)
    sess = sessao()
    rodada = 1
    while True:
        payload = {"uf": [uf], "municipio": [municipio]}
        if vistos:
            payload["excluir"] = {"cnpj": list(vistos.keys())}
        resp = post_casa(sess, payload)
        itens = resp.get("cnpjs", [])
        total_restante = resp.get("total")
        try:
            total_estimado = len(vistos) + int(total_restante)
        except (TypeError, ValueError):
            total_estimado = None
        novos = sum(1 for it in itens
                    if it.get("cnpj") and it["cnpj"] not in vistos)
        for it in itens:
            if it.get("cnpj"):
                vistos[it["cnpj"]] = it
        print(f"rodada {rodada}: {len(itens)} itens, {novos} novos "
              f"(acumulado {len(vistos)}, total API {resp.get('total')})",
              flush=True)
        with open(chk, "w", encoding="utf-8") as f:
            json.dump(list(vistos.values()), f, ensure_ascii=False)
        if on_progress:
            on_progress({
                "etapa": "listando",
                "empresas": len(vistos),
                "total": total_estimado,
                "mensagem": f"Lista municipal: {len(vistos)} empresas encontradas",
            })
        if not itens or novos == 0:
            break
        rodada += 1
        time.sleep(0.3)  # era 3 s na v1; 0,3 s basta e nao toma 429
    return list(vistos.values())


def get_brasilapi(cnpj, tentativas=5):
    """Retorna (dict|None, status). None + 404 = CNPJ nao encontrado
    (comum em MEI baixado/antigo); None + outro status = falha apos retry."""
    url = BRASILAPI.format(cnpj)
    for t in range(tentativas):
        try:
            r = sessao().get(url, timeout=30)
            if r.status_code == 404:
                return None, 404
            if r.status_code == 429:
                espera = int(r.headers.get("Retry-After", 2 ** t))
                time.sleep(min(espera, 60))
                continue
            r.raise_for_status()
            return r.json(), 200
        except Exception:
            if t == tentativas - 1:
                return None, 0
            time.sleep(min(2 ** t, 30))
    return None, 0


def montar_endereco(rua, numero, complemento, bairro, municipio, uf, cep):
    endereco = " ".join(p for p in [rua, str(numero or ""),
                                    str(complemento or "")] if p).strip()
    if bairro:
        endereco = f"{endereco} - {bairro}" if endereco else bairro
    cidade_uf = f"{municipio}/{uf}".strip("/")
    if cidade_uf:
        endereco = f"{endereco} {cidade_uf}".strip()
    if cep:
        endereco = f"{endereco} CEP {cep}".strip()
    return endereco


def tipo_socio(s):
    """1 = PJ, 2 = PF (layout Receita). Fallback: campo antigo tipo_socio."""
    ident = s.get("identificador_de_socio")
    if ident == 1:
        return "PJ"
    if ident == 2:
        return "PF"
    return "PJ" if s.get("tipo_socio") == "Pessoa Jurídica" else "PF"


def enriquecer(cnpj):
    d, status = get_brasilapi(cnpj)
    if not d:
        return {"cnpj": cnpj, "brasilapi_status": status}
    qsa = []
    for s in d.get("qsa", []):
        qsa.append({
            "nome": s.get("nome_socio", ""),
            # CPF (PF) ou CNPJ (PJ) do socio, MASCARADO pela fonte.
            "cpf_cnpj_mascarado": s.get("cnpj_cpf_do_socio", ""),
            "qualificacao": s.get("qualificacao_socio", ""),
            "tipo": tipo_socio(s),
            "data_entrada": s.get("data_entrada_sociedade", ""),
            "faixa_etaria": s.get("faixa_etaria", ""),
        })
    tipo_log = d.get("descricao_tipo_de_logradouro", "")
    logr = d.get("logradouro", "")
    rua = f"{tipo_log} {logr}".strip()
    # Sem "-" solto quando nao ha logradouro (empresas antigas muitas
    # vezes so tem bairro/CEP na BrasilAPI).
    endereco = montar_endereco(rua, d.get("numero", ""), d.get("complemento", ""),
                               d.get("bairro", ""), d.get("municipio", ""),
                               d.get("uf", ""), d.get("cep", ""))
    return {
        "cnpj": cnpj,
        "brasilapi_status": status,
        "capital_social": d.get("capital_social"),
        "cnae_fiscal": d.get("cnae_fiscal", ""),
        "cnae_descricao": d.get("cnae_fiscal_descricao", ""),
        "porte": d.get("porte", ""),
        "endereco": endereco,
        "logradouro": f"{tipo_log} {logr}".strip(),
        "numero": str(d.get("numero", "") or ""),
        "complemento": d.get("complemento", ""),
        "bairro": d.get("bairro", ""),
        "cep": d.get("cep", ""),
        "telefone": d.get("ddd_telefone_1", ""),
        "qsa": qsa,
    }


def carregar_cache(path):
    """Cache resumable. Entradas com status 0 (falha apos retries, em
    geral 429) NAO sao dadas como prontas: na proxima rodada elas entram
    em `pendentes` e sao tentadas de novo (o append sobrescreve na leitura,
    pois a ultima linha vence). 404 e definitivo e fica no cache."""
    cache = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    try:
                        e = json.loads(linha)
                        if e.get("brasilapi_status") != 0:
                            cache[e["cnpj"]] = e
                    except (json.JSONDecodeError, KeyError):
                        continue
    return cache


def coletar_dados_municipio(
        uf, municipio, cache_dir, workers=10, on_progress=None):
    """Busca o cadastro municipal e devolve linhas no mesmo formato do CSV."""
    municipio = "".join(
        caractere for caractere in unicodedata.normalize("NFKD", municipio)
        if not unicodedata.combining(caractere)
    ).upper()
    uf = uf.upper()
    os.makedirs(cache_dir, exist_ok=True)
    base = os.path.join(cache_dir, f"cnpj_{municipio}_{uf}")
    empresas = buscar_cnpjs(
        uf, municipio, base + ".checkpoint.json", on_progress=on_progress)
    cache_path = base + ".enriquecido.jsonl"
    cache = carregar_cache(cache_path)
    pendentes = [empresa for empresa in empresas
                 if empresa["cnpj"] not in cache]

    if on_progress:
        on_progress({
            "etapa": "enriquecendo",
            "empresas": len(empresas),
            "processadas": 0,
            "pendentes": len(pendentes),
            "mensagem": f"Enriquecendo {len(pendentes)} empresas",
        })

    feitos = 0
    with open(cache_path, "a", encoding="utf-8") as arquivo_cache:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futuras = {
                executor.submit(enriquecer, empresa["cnpj"]): empresa["cnpj"]
                for empresa in pendentes
            }
            for futura in as_completed(futuras):
                cnpj = futuras[futura]
                try:
                    resultado = futura.result()
                except Exception as erro:
                    resultado = {
                        "cnpj": cnpj,
                        "brasilapi_status": 0,
                        "erro": str(erro),
                    }
                cache[cnpj] = resultado
                arquivo_cache.write(
                    json.dumps(resultado, ensure_ascii=False) + "\n")
                arquivo_cache.flush()
                feitos += 1
                if on_progress:
                    on_progress({
                        "etapa": "enriquecendo",
                        "empresas": len(empresas),
                        "processadas": feitos,
                        "pendentes": len(pendentes),
                        "mensagem": (
                            f"Enriquecendo empresas: {feitos}/"
                            f"{len(pendentes)} novas"
                        ),
                    })

    colunas = [
        "cnpj", "razao_social", "nome_fantasia", "situacao_cadastral",
        "capital_social", "cnae_fiscal", "cnae_descricao", "porte",
        "endereco", "logradouro", "numero", "complemento", "bairro",
        "cep", "municipio", "uf", "telefone", "socio_nome",
        "socio_cpf_cnpj_mascarado", "socio_qualificacao", "socio_tipo",
        "socio_data_entrada", "socio_faixa_etaria", "brasilapi_status",
    ]
    registros = []
    for empresa in empresas:
        enriquecido = cache.get(empresa["cnpj"], {})
        situacao = (
            empresa.get("situacao_cadastral") or {}
        ).get("situacao_atual", "")
        base_row = {
            "cnpj": empresa["cnpj"],
            "razao_social": empresa.get("razao_social", ""),
            "nome_fantasia": empresa.get("nome_fantasia", ""),
            "situacao_cadastral": situacao,
            "capital_social": enriquecido.get("capital_social") or "",
            "cnae_fiscal": enriquecido.get("cnae_fiscal", ""),
            "cnae_descricao": enriquecido.get("cnae_descricao", ""),
            "porte": enriquecido.get("porte", ""),
            "endereco": montar_endereco(
                enriquecido.get("logradouro", ""),
                enriquecido.get("numero", ""),
                enriquecido.get("complemento", ""),
                enriquecido.get("bairro", ""),
                municipio, uf, enriquecido.get("cep", "")) if (
                    enriquecido.get("cep") or enriquecido.get("bairro")
                    or enriquecido.get("logradouro")) else "",
            "logradouro": enriquecido.get("logradouro", ""),
            "numero": enriquecido.get("numero", ""),
            "complemento": enriquecido.get("complemento", ""),
            "bairro": enriquecido.get("bairro", ""),
            "cep": enriquecido.get("cep", ""),
            "municipio": municipio,
            "uf": uf,
            "telefone": enriquecido.get("telefone", ""),
            "brasilapi_status": enriquecido.get("brasilapi_status", 0),
        }
        qsa = enriquecido.get("qsa", [])
        if not qsa:
            registros.append(base_row)
        for socio in qsa:
            registros.append({
                **base_row,
                "socio_nome": socio.get("nome", ""),
                "socio_cpf_cnpj_mascarado": socio.get(
                    "cpf_cnpj_mascarado", ""),
                "socio_qualificacao": socio.get("qualificacao", ""),
                "socio_tipo": socio.get("tipo", ""),
                "socio_data_entrada": socio.get("data_entrada", ""),
                "socio_faixa_etaria": socio.get("faixa_etaria", ""),
            })
    return [{coluna: registro.get(coluna, "") for coluna in colunas}
            for registro in registros]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("uf")
    ap.add_argument("municipio")
    ap.add_argument("--workers", type=int, default=10,
                    help="threads paralelas na BrasilAPI (padrao 10; "
                         "20+ bate 429 sem ganhar velocidade)")
    ap.add_argument("--limite", type=int, default=0,
                    help="processar so os N primeiros (teste)")
    ap.add_argument("--so-lista", action="store_true",
                    help="so baixar a lista da Casa, sem enriquecer")
    args = ap.parse_args()

    uf, municipio = args.uf.upper(), args.municipio.upper()
    base = f"cnpj_{municipio}_{uf}"
    chk, cache_path, out = (base + ".checkpoint.json",
                            base + ".enriquecido.jsonl", base + ".csv")

    print(f"Buscando CNPJs de {municipio}/{uf} ...", flush=True)
    t0 = time.time()
    empresas = buscar_cnpjs(uf, municipio, chk)
    print(f"{len(empresas)} CNPJs em {time.time() - t0:.0f}s", flush=True)
    if args.so_lista:
        print(f"OK -> {chk}", flush=True)
        return
    if args.limite:
        empresas = empresas[:args.limite]

    cache = carregar_cache(cache_path)
    pendentes = [e for e in empresas if e["cnpj"] not in cache]
    print(f"enriquecimento: {len(cache)} em cache, {len(pendentes)} pendentes, "
          f"{args.workers} workers", flush=True)

    t0 = time.time()
    feitos = 0
    with open(cache_path, "a", encoding="utf-8") as cf:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(enriquecer, e["cnpj"]): e["cnpj"]
                    for e in pendentes}
            for fut in as_completed(futs):
                cnpj = futs[fut]
                try:
                    res = fut.result()
                except Exception as e:  # nao derruba o lote por 1 CNPJ
                    res = {"cnpj": cnpj, "brasilapi_status": 0, "erro": str(e)}
                cache[cnpj] = res
                cf.write(json.dumps(res, ensure_ascii=False) + "\n")
                cf.flush()
                feitos += 1
                if feitos % 100 == 0 or feitos == len(pendentes):
                    dt = time.time() - t0
                    taxa = feitos / dt if dt else 0
                    eta = (len(pendentes) - feitos) / taxa if taxa else 0
                    print(f"  {feitos}/{len(pendentes)} "
                          f"({taxa:.1f}/s, ETA {eta/60:.1f} min)", flush=True)
    print(f"enriquecimento em {time.time() - t0:.0f}s", flush=True)

    # CSV final na ordem da lista da Casa (paralelismo nao embaralha).
    cols = ["cnpj", "razao_social", "nome_fantasia", "situacao_cadastral",
            "capital_social", "cnae_fiscal", "cnae_descricao", "porte",
            "endereco", "logradouro", "numero", "complemento", "bairro",
            "cep", "municipio", "uf", "telefone",
            "socio_nome", "socio_cpf_cnpj_mascarado", "socio_qualificacao",
            "socio_tipo", "socio_data_entrada", "socio_faixa_etaria"]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";")
        w.writeheader()
        for emp in empresas:
            enr = cache.get(emp["cnpj"], {})
            sit = (emp.get("situacao_cadastral") or {}).get("situacao_atual", "")
            base_row = {
                "cnpj": emp["cnpj"], "razao_social": emp.get("razao_social", ""),
                "nome_fantasia": emp.get("nome_fantasia", ""),
                "situacao_cadastral": sit,
                "capital_social": enr.get("capital_social", "") or "",
                "cnae_fiscal": enr.get("cnae_fiscal", ""),
                "cnae_descricao": enr.get("cnae_descricao", ""),
                "porte": enr.get("porte", ""),
                # Recomputa a partir dos componentes: corrige o formato
                # de caches antigos sem precisar reconsultar a API.
                "endereco": montar_endereco(
                    enr.get("logradouro", ""), enr.get("numero", ""),
                    enr.get("complemento", ""), enr.get("bairro", ""),
                    municipio, uf, enr.get("cep", "")) if enr.get("cep") or enr.get("bairro") or enr.get("logradouro") else "",
                "logradouro": enr.get("logradouro", ""),
                "numero": enr.get("numero", ""),
                "complemento": enr.get("complemento", ""),
                "bairro": enr.get("bairro", ""),
                "cep": enr.get("cep", ""),
                "municipio": municipio, "uf": uf,
                "telefone": enr.get("telefone", ""),
            }
            qsa = enr.get("qsa", [])
            if not qsa:
                w.writerow(base_row)
            for s in qsa:
                w.writerow({**base_row,
                            "socio_nome": s["nome"],
                            "socio_cpf_cnpj_mascarado": s["cpf_cnpj_mascarado"],
                            "socio_qualificacao": s["qualificacao"],
                            "socio_tipo": s["tipo"],
                            "socio_data_entrada": s["data_entrada"],
                            "socio_faixa_etaria": s["faixa_etaria"]})
    print(f"OK -> {out} ({time.time() - t0:.0f}s no total)", flush=True)


if __name__ == "__main__":
    main()
