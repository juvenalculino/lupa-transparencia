import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import Chart from "chart.js/auto";
import {
  Activity, AlertCircle, AlertOctagon, BarChart2, BarChart3, CheckCircle,
  Clock, CloudDownload, Database, DollarSign, Download, DownloadCloud,
  ExternalLink, GitFork, GitMerge, Globe, Loader2, Save, Search, Server,
  Share2, ShieldCheck, Table, UserCheck, Users,
} from "lucide-react";
import "./styles.css";
import "vis-network/styles/vis-network.min.css";

const API_URL = import.meta.env.VITE_API_BASE_URL || "/api";
const ICONS = {
  Activity, AlertCircle, AlertOctagon, BarChart2, BarChart3, CheckCircle,
  Clock, CloudDownload, Database, DollarSign, Download, DownloadCloud,
  ExternalLink, GitFork, GitMerge, Globe, Loader2, Save, Search, Server,
  Share2, ShieldCheck, Table, UserCheck, Users,
};

function Icon({ name, className }) {
  const iconName = name.split("-").map(part => part.charAt(0).toUpperCase() + part.slice(1)).join("");
  const IconComponent = ICONS[iconName];
  return IconComponent ? <IconComponent className={className} aria-hidden="true" /> : null;
}

const REQUEST_TIMEOUT_MS = 12_000;
const COLLECTION_TIMEOUT_MS = 30 * 60 * 1000;

async function fetchJson(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const externalSignal = options.signal;
  let timedOut = false;
  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const abortRequest = () => controller.abort();

  if (externalSignal?.aborted) {
    controller.abort();
  } else {
    externalSignal?.addEventListener("abort", abortRequest, { once: true });
  }

  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const responseText = await response.text();
    let payload = {};
    if (responseText) {
      try {
        payload = JSON.parse(responseText);
      } catch {
        payload = {
          detail: response.ok
            ? "A API retornou uma resposta inválida."
            : `A API respondeu HTTP ${response.status} sem uma mensagem JSON válida.`,
        };
      }
    } else if (!response.ok) {
      payload.detail = `A API respondeu HTTP ${response.status} sem conteúdo. Verifique se o servidor FastAPI está ativo em http://127.0.0.1:8000.`;
    }
    if (!response.ok) {
      throw new Error(payload.detail || payload.erro || `Erro HTTP ${response.status}`);
    }
    if (payload.erro) throw new Error(payload.erro);
    return payload;
  } catch (error) {
    if (timedOut) {
      throw new Error(`A solicitação excedeu o limite de ${Math.ceil(timeoutMs / 1000)} segundos.`);
    }
    if (error instanceof TypeError) {
      throw new Error("Não foi possível alcançar a API. Inicie o backend com `uvicorn api:app --reload` e tente novamente.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
    externalSignal?.removeEventListener("abort", abortRequest);
  }
}

function isAbortError(error) {
  return error?.name === "AbortError";
}

function formatarDuracao(segundos) {
  const total = Math.ceil(Math.max(0, segundos));
  const horas = Math.floor(total / 3600);
  const minutos = Math.floor((total % 3600) / 60);
  const restoSegundos = total % 60;
  if (horas > 0) return `${horas} h ${minutos} min`;
  if (minutos > 0) return `${minutos} min ${restoSegundos} s`;
  return `${restoSegundos} s`;
}

const VIGENCIAS_BENEFICIOS = {
  "Novo Bolsa Familia": ["202303", null],
  "Auxilio Brasil": ["202111", "202302"],
  "Bolsa Familia": ["200310", "202110"],
  BPC: ["199601", null],
  "Garantia Safra": ["200201", null],
  "Seguro Defeso": ["199101", null],
  "Auxilio Emergencial": ["202004", "202110"],
  PETI: ["199601", "200512"],
};

const MESES_BENEFICIO = Array.from({ length: 12 }, (_, index) =>
  String(index + 1).padStart(2, "0"),
);

function obterAnosVigentes(programa) {
  const [inicio, fim] = VIGENCIAS_BENEFICIOS[programa] || ["199101", null];
  const anoInicio = Number(inicio.slice(0, 4));
  const anoFim = Math.min(
    Number(fim?.slice(0, 4) || new Date().getFullYear()),
    new Date().getFullYear(),
  );
  return Array.from(
    { length: anoFim - anoInicio + 1 },
    (_, index) => String(anoFim - index),
  );
}

function obterMesesVigentes(programa, ano) {
  if (!programa || programa === "Todos" || ano === "Todos") {
    return MESES_BENEFICIO;
  }
  const [inicio, fim] = VIGENCIAS_BENEFICIOS[programa] || ["199101", null];
  return MESES_BENEFICIO.filter(mes => {
    const competencia = `${ano}${mes}`;
    return competencia >= inicio && (!fim || competencia <= fim);
  });
}

function ajustarPeriodoVigente(programa, ano, mes) {
  if (ano === "Todos") return { ano, mes };
  const anos = obterAnosVigentes(programa);
  const anoAjustado = anos.includes(ano)
    ? ano
    : String(Math.max(
      Number(anos[anos.length - 1]),
      Math.min(Number(ano), Number(anos[0])),
    ));
  if (mes === "Todos") return { ano: anoAjustado, mes };
  const meses = obterMesesVigentes(programa, anoAjustado);
  if (meses.includes(mes)) return { ano: anoAjustado, mes };
  return {
    ano: anoAjustado,
    mes: Number(mes) < Number(meses[0])
      ? meses[0]
      : meses[meses.length - 1],
  };
}

function rotuloVigencia(programa) {
  const [inicio, fim] = VIGENCIAS_BENEFICIOS[programa] || ["199101", null];
  const formatar = competencia =>
    `${competencia.slice(4, 6)}/${competencia.slice(0, 4)}`;
  return `${formatar(inicio)} - ${fim ? formatar(fim) : "atual"}`;
}

    function App() {
      const [activeTab, setActiveTab] = useState("dashboard");
      const [selectedUf, setSelectedUf] = useState("BA");
      const [selectedMun, setSelectedMun] = useState(null);
      const [municipiosLista, setMunicipiosLista] = useState([]);
      const [codigosMunicipiosComDados, setCodigosMunicipiosComDados] = useState([]);
      const [codigosMunicipiosComAgregados, setCodigosMunicipiosComAgregados] = useState([]);
      const [codigosMunicipiosComBeneficiarios, setCodigosMunicipiosComBeneficiarios] = useState([]);
      const [filtroMunicipios, setFiltroMunicipios] = useState("todos");
      const [ufsLista, setUfsLista] = useState([]);
      const [municipiosReloadKey, setMunicipiosReloadKey] = useState(0);
      const [cnpjMontada, setCnpjMontada] = useState(false);
      
      const [selectedPrograma, setSelectedPrograma] = useState("Todos");
      const [programasDisponiveis, setProgramasDisponiveis] = useState([]);
      const [selectedAno, setSelectedAno] = useState("Todos");
      const [selectedMes, setSelectedMes] = useState("Todos");
      const [tipoConsulta, setTipoConsulta] = useState("Agregado mensal do ano");
      const [dados, setDados] = useState([]);
      const [metricasResumo, setMetricasResumo] = useState(null);
      const [loading, setLoading] = useState(false);
      const [erro, setErro] = useState(null);
      const [erroMunicipios, setErroMunicipios] = useState(null);
      const [erroFiltros, setErroFiltros] = useState(null);
      const [loadingMunicipios, setLoadingMunicipios] = useState(true);
      const [loadingFiltros, setLoadingFiltros] = useState(false);
      const [dbStatus, setDbStatus] = useState("Carregando sistema...");
      const [pagina, setPagina] = useState(1);
      const [buscaTabela, setBuscaTabela] = useState("");
      const [buscaTabelaDebounced, setBuscaTabelaDebounced] = useState("");
      const [totalRegistros, setTotalRegistros] = useState(0);
      const [totalPaginas, setTotalPaginas] = useState(1);

      const [nisGrafo, setNisGrafo] = useState("");
      const [termoBuscaGlobal, setTermoBuscaGlobal] = useState("");
      const [resultadosBuscaGlobal, setResultadosBuscaGlobal] = useState([]);
      const [loadingBuscaGlobal, setLoadingBuscaGlobal] = useState(false);
      const [erroBuscaGlobal, setErroBuscaGlobal] = useState(null);
      const consultaController = useRef(null);
      const buscaController = useRef(null);

      useEffect(() => {
        const timeout = window.setTimeout(
          () => setBuscaTabelaDebounced(buscaTabela),
          250,
        );
        return () => window.clearTimeout(timeout);
      }, [buscaTabela]);

      // Carregar Lista de Municípios
      useEffect(() => {
        const controller = new AbortController();
        setLoadingMunicipios(true);

        fetchJson(`${API_URL}/municipios`, { signal: controller.signal })
          .then(data => {
            if (Array.isArray(data.municipios) && data.municipios.length > 0) {
              setErroMunicipios(null);
              setDbStatus("API conectada. Município disponível para consulta.");
              setMunicipiosLista(data.municipios);
              setCodigosMunicipiosComDados(data.codigos_municipios_com_dados || []);
              setCodigosMunicipiosComAgregados(data.codigos_municipios_com_agregados || []);
              setCodigosMunicipiosComBeneficiarios(
                data.codigos_municipios_com_beneficiarios || [],
              );
              setUfsLista(data.ufs || ["BA"]);
              let codigoMunicipioSalvo = null;
              try {
                codigoMunicipioSalvo = window.localStorage.getItem(
                  "painel-beneficios.municipio-codigo-ibge",
                );
              } catch (storageError) {
                setErroMunicipios(
                  `Não foi possível recuperar o município salvo: ${storageError.message}`,
                );
              }
              const municipioAtual = data.municipios.find(
                municipio => municipio.codigo_ibge === selectedMun?.codigo_ibge,
              );
              const municipioSalvo = data.municipios.find(
                municipio => municipio.codigo_ibge === codigoMunicipioSalvo,
              );
              const fatima = data.municipios.find(
                municipio => municipio.nome.toLowerCase().includes("fátima")
                  || municipio.nome.toLowerCase().includes("fatima"),
              );
              const municipioInicial = municipioAtual
                || municipioSalvo
                || fatima
                || data.municipios[0];
              setSelectedMun(municipioInicial);
              setSelectedUf(municipioInicial.uf);
            } else {
              throw new Error("A API não retornou municípios disponíveis.");
            }
          })
          .catch(error => {
            if (isAbortError(error)) return;
            setErroMunicipios(`Não foi possível carregar os municípios: ${error.message}`);
            setDbStatus("API indisponível. Confira o backend FastAPI na porta 8000.");
          })
          .finally(() => {
            if (!controller.signal.aborted) setLoadingMunicipios(false);
          });

        return () => controller.abort();
      }, [municipiosReloadKey]);

      useEffect(() => {
        if (!selectedMun?.codigo_ibge) return;
        try {
          window.localStorage.setItem(
            "painel-beneficios.municipio-codigo-ibge",
            selectedMun.codigo_ibge,
          );
        } catch (storageError) {
          setErroMunicipios(
            `Não foi possível salvar o município selecionado: ${storageError.message}`,
          );
        }
      }, [selectedMun]);

      useEffect(() => {
        const codigoIbge = selectedMun?.codigo_ibge;
        if (!codigoIbge) return;
        const temBeneficiarios =
          codigosMunicipiosComBeneficiarios.includes(codigoIbge);
        const temAgregados = codigosMunicipiosComAgregados.includes(codigoIbge);
        if (temBeneficiarios) {
          setTipoConsulta("Adicionar beneficiários");
        } else if (temAgregados) {
          setTipoConsulta("Agregado mensal do ano");
        }
      }, [
        selectedMun?.codigo_ibge,
        codigosMunicipiosComAgregados,
        codigosMunicipiosComBeneficiarios,
      ]);

      // Buscar Programas Dinamicamente (Apenas salvos no banco local)
      useEffect(() => {
        if (!selectedMun?.codigo_ibge || !selectedAno) return undefined;
        const controller = new AbortController();
        const query = new URLSearchParams({
          codigo_ibge: selectedMun.codigo_ibge,
          ano: selectedAno,
        });
        setLoadingFiltros(true);
        setErroFiltros(null);

        fetchJson(`${API_URL}/filtros?${query}`, { signal: controller.signal })
          .then(data => {
            const limpos = Array.from(new Set((data.programas || []).map(p => p.replace(" (sacado)", "").trim()))).sort();
            setProgramasDisponiveis(limpos);
            if (selectedPrograma !== "Todos" && !limpos.includes(selectedPrograma)) {
              setSelectedPrograma("Todos");
            }
          })
          .catch(error => {
            if (isAbortError(error)) return;
            setErroFiltros(`Não foi possível carregar os programas disponíveis: ${error.message}`);
          })
          .finally(() => {
            if (!controller.signal.aborted) setLoadingFiltros(false);
          });

        return () => controller.abort();
      }, [selectedMun, selectedAno]);

      const municipiosElegiveis = useMemo(() => {
        const codigosAtivos = new Set(
          codigosMunicipiosComDados,
        );
        return municipiosLista.filter(municipio =>
          filtroMunicipios === "todos" || codigosAtivos.has(municipio.codigo_ibge),
        );
      }, [municipiosLista, codigosMunicipiosComDados, filtroMunicipios]);

      const municipiosFiltrados = useMemo(
        () => municipiosElegiveis.filter(municipio => municipio.uf === selectedUf),
        [municipiosElegiveis, selectedUf],
      );

      const ufsDisponiveis = useMemo(() => {
        const codigosAtivos = new Set(
          codigosMunicipiosComDados,
        );
        return ufsLista.filter(uf => municipiosLista.some(municipio =>
          municipio.uf === uf
          && (filtroMunicipios === "todos" || codigosAtivos.has(municipio.codigo_ibge)),
        ));
      }, [ufsLista, municipiosLista, codigosMunicipiosComDados, filtroMunicipios]);

      const selecionarFiltroMunicipios = (filtro) => {
        const codigosAtivos = new Set(
          codigosMunicipiosComDados,
        );
        const disponiveis = filtro === "todos"
          ? municipiosLista
          : municipiosLista.filter(municipio => codigosAtivos.has(municipio.codigo_ibge));
        const municipio = disponiveis.find(
          item => item.codigo_ibge === selectedMun?.codigo_ibge,
        ) || disponiveis.find(item => item.uf === selectedUf) || disponiveis[0];

        setFiltroMunicipios(filtro);
        if (municipio) {
          setSelectedUf(municipio.uf);
          setSelectedMun(municipio);
        }
        setPagina(1);
      };

      const requerDados = activeTab === "dashboard" || activeTab === "tabela";
      const paginarBeneficiarios = activeTab === "tabela" && tipoConsulta === "Adicionar beneficiários";

      const carregarDados = async (signal) => {
        if (!selectedMun) return;
        if (!signal) {
          consultaController.current?.abort();
          consultaController.current = new AbortController();
          signal = consultaController.current.signal;
        }
        setLoading(true);
        setErro(null);
        setDados([]);
        setMetricasResumo(null);
        try {
          const resData = await fetchJson(`${API_URL}/consultar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              tipo: tipoConsulta,
              programa: selectedPrograma,
              uf: selectedUf,
              codigo_ibge: selectedMun.codigo_ibge,
              nome_mun: selectedMun.nome,
              ano: selectedAno,
              mes: selectedMes,
              permitir_novos: false,
              ...(tipoConsulta === "Adicionar beneficiários" && !paginarBeneficiarios
                ? { resumo: true }
                : {}),
              ...(paginarBeneficiarios ? {
                pagina,
                por_pagina: 100,
                busca: buscaTabelaDebounced,
              } : {}),
            }),
            signal,
          });

          setDados(resData.dados || []);
          setMetricasResumo(resData.resumo || null);
          setTotalRegistros(resData.registros || 0);
          setTotalPaginas(resData.total_paginas || 1);
          setDbStatus(`Consulta realizada. ${resData.registros || 0} registros localizados no banco de dados local.`);
        } catch (error) {
          if (!isAbortError(error)) setErro(`Falha ao consultar o banco de dados: ${error.message}`);
        } finally {
          if (!signal.aborted) setLoading(false);
        }
      };

      useEffect(() => {
        if (!requerDados || !selectedMun?.codigo_ibge) return undefined;
        const controller = new AbortController();
        carregarDados(controller.signal);
        return () => controller.abort();
      }, [selectedMun, selectedPrograma, selectedAno, selectedMes, tipoConsulta, requerDados, paginarBeneficiarios, pagina, buscaTabelaDebounced]);

      const executarBuscaGlobal = async (termo) => {
        if (!termo || termo.length < 3 || !selectedMun) return;
        buscaController.current?.abort();
        buscaController.current = new AbortController();
        setLoadingBuscaGlobal(true);
        setErroBuscaGlobal(null);
        try {
          const query = new URLSearchParams({ codigo_ibge: selectedMun.codigo_ibge, termo });
          const data = await fetchJson(`${API_URL}/busca_global?${query}`, {
            signal: buscaController.current.signal,
          });
          setResultadosBuscaGlobal(data.resultados || []);
        } catch (error) {
          if (!isAbortError(error)) setErroBuscaGlobal(`Falha na busca: ${error.message}`);
        } finally {
          if (!buscaController.current?.signal.aborted) setLoadingBuscaGlobal(false);
        }
      };

      const downloadCSV = () => {
        if (!dados || dados.length === 0) return;
        const headers = Object.keys(dados[0]).join(",");
        const rows = dados.map(obj => Object.values(obj).map(val => `"${val}"`).join(","));
        const csvContent = "data:text/csv;charset=utf-8," + [headers, ...rows].join("\n");
        const encodedUri = encodeURI(csvContent);
        const link = document.createElement("a");
        link.setAttribute("href", encodedUri);
        const safeProgName = selectedPrograma.replace(/[^a-zA-Z0-9]/g, "_");
        const safeMunName = selectedMun.nome.replace(/[^a-zA-Z0-9]/g, "_");
        link.setAttribute("download", `relatorio_${safeMunName}_${safeProgName}_${selectedAno}_${selectedMes}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      };

      const anosFiltro = obterAnosVigentes(selectedPrograma);
      const mesesFiltro = obterMesesVigentes(selectedPrograma, selectedAno);

      return (
        <div className="flex h-screen overflow-hidden bg-slate-900">
          {/* SIDEBAR */}
          <aside className="w-80 bg-slate-800 border-r border-slate-700/80 flex flex-col flex-shrink-0 z-20 shadow-xl">
            <div className="p-5 border-b border-slate-700/80 flex items-center space-x-3">
              <div className="bg-brand-600 p-2.5 rounded-xl shadow-lg shadow-brand-600/30">
                <Icon name="shield-check" className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="font-bold text-sm text-white leading-tight">Portal Transparência</h1>
                <p className="text-xs text-slate-400">Monitor Local (Offline/Online)</p>
              </div>
            </div>

            <div className="p-5 space-y-5 overflow-y-auto flex-1">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Modo de Exibição</label>
                <div className="grid grid-cols-1 gap-2">
                  <button
                    onClick={() => { setTipoConsulta("Adicionar beneficiários"); setPagina(1); }}
                    className={`px-3 py-2 rounded-xl text-xs font-medium text-left transition-all border flex items-center space-x-2 ${tipoConsulta === "Adicionar beneficiários" ? "bg-brand-600/20 border-brand-500 text-brand-300" : "bg-slate-900/50 border-slate-700 text-slate-400"}`}
                  >
                    <Icon name="users" className="w-4 h-4" />
                    <span>Beneficiários (Listagem Pessoal)</span>
                  </button>
                  <button
                    onClick={() => { setTipoConsulta("Agregado mensal do ano"); setPagina(1); }}
                    className={`px-3 py-2 rounded-xl text-xs font-medium text-left transition-all border flex items-center space-x-2 ${tipoConsulta === "Agregado mensal do ano" ? "bg-brand-600/20 border-brand-500 text-brand-300" : "bg-slate-900/50 border-slate-700 text-slate-400"}`}
                  >
                    <Icon name="bar-chart-2" className="w-4 h-4" />
                    <span>Agregados (Totais e Custos)</span>
                  </button>
                </div>
              </div>

              <div className="space-y-3 pt-2 border-t border-slate-700/50">
                <div className="space-y-1">
                  <label htmlFor="municipality-scope" className="text-xs font-semibold text-slate-300">
                    Lista de municípios
                  </label>
                  <select
                    id="municipality-scope"
                    value={filtroMunicipios}
                    onChange={event => selecionarFiltroMunicipios(event.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200 focus:ring-2 focus:ring-brand-500 outline-none"
                  >
                    <option value="todos">Todos os municípios — consultar/baixar</option>
                    <option value="com_dados" disabled={codigosMunicipiosComDados.length === 0}>
                        Somente municípios com dados baixados ({codigosMunicipiosComDados.length})
                    </option>
                  </select>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div className="col-span-1 space-y-1">
                    <label htmlFor="municipality-uf" className="text-xs font-semibold text-slate-300">UF</label>
                    <select 
                      id="municipality-uf"
                      value={selectedUf}
                      onChange={(e) => {
                         setSelectedUf(e.target.value);
                         const novoMun = municipiosElegiveis.find(m => m.uf === e.target.value);
                         if (novoMun) setSelectedMun(novoMun);
                         setPagina(1);
                      }}
                      className="w-full bg-slate-900 border border-slate-700 rounded-xl px-2.5 py-2 text-xs text-slate-200 focus:ring-2 focus:ring-brand-500 outline-none"
                    >
                      {ufsDisponiveis.map(uf => {
                        const quantidadeAtivos = municipiosLista.filter(
                          municipio => municipio.uf === uf
                            && codigosMunicipiosComDados.includes(municipio.codigo_ibge),
                        ).length;
                        const rotulo = filtroMunicipios === "com_dados"
                          ? `${uf} (${quantidadeAtivos} com dados)`
                          : uf;
                        return <option key={uf} value={uf}>{rotulo}</option>;
                      })}
                    </select>
                  </div>
                  <div className="col-span-2 space-y-1">
                    <label htmlFor="municipality-select" className="text-xs font-semibold text-slate-300">Município</label>
                    <select 
                      id="municipality-select"
                      value={selectedMun?.codigo_ibge || ""}
                      onChange={(e) => {
                        const m = municipiosLista.find(item => item.codigo_ibge === e.target.value);
                        if (m) setSelectedMun(m);
                        setPagina(1);
                      }}
                      className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200 focus:ring-2 focus:ring-brand-500 outline-none"
                    >
                      {municipiosFiltrados.length === 0
                        ? <option value="">Nenhum município nesta lista</option>
                        : municipiosFiltrados.map(m => (
                          <option key={m.codigo_ibge} value={m.codigo_ibge}>
                            {m.nome} — {m.uf}
                          </option>
                        ))}
                    </select>
                  </div>
                </div>
                
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-300">Ano</label>
                    <select 
                      value={selectedAno}
                      onChange={(e) => {
                        const ano = e.target.value;
                        setSelectedAno(ano);
                        if (
                          selectedMes !== "Todos"
                          && !obterMesesVigentes(selectedPrograma, ano).includes(selectedMes)
                        ) {
                          setSelectedMes("Todos");
                        }
                        setPagina(1);
                      }}
                      className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200 focus:ring-2 focus:ring-brand-500 outline-none font-semibold text-brand-400"
                    >
                      <option value="Todos">Todos os anos</option>
                      {anosFiltro.map(ano => <option key={ano} value={ano}>{ano}</option>)}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-300">Mês</label>
                    <select 
                      value={selectedMes}
                      onChange={(e) => { setSelectedMes(e.target.value); setPagina(1); }}
                      className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200 focus:ring-2 focus:ring-brand-500 outline-none"
                    >
                      <option value="Todos">Todos os Meses</option>
                      {mesesFiltro.map(mes => <option key={mes} value={mes}>{mes}</option>)}
                    </select>
                  </div>
                </div>
              </div>

              <div className="space-y-1 pt-2 border-t border-slate-700/50">
                <label className="text-xs font-semibold text-slate-300 flex justify-between">
                  <span>Programas Locais (Salvos)</span>
                  <span className="text-[10px] text-brand-400 font-normal">
                    {loadingFiltros ? "Carregando..." : `${programasDisponiveis.length} salvos`}
                  </span>
                </label>
                <select
                  value={selectedPrograma}
                  onChange={(e) => {
                    const programa = e.target.value;
                    setSelectedPrograma(programa);
                    if (programa !== "Todos") {
                      const periodo = ajustarPeriodoVigente(
                        programa, selectedAno, selectedMes,
                      );
                      setSelectedAno(periodo.ano);
                      setSelectedMes(periodo.mes);
                    }
                    setPagina(1);
                  }}
                  className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200 focus:ring-2 focus:ring-brand-500 outline-none font-medium"
                >
                  <option value="Todos" className="font-bold text-brand-400">» Exibir Todos</option>
                  {programasDisponiveis.length === 0 ? (
                    <option disabled>Sem dados locais para este filtro</option>
                  ) : (
                    programasDisponiveis.map(prog => (
                      <option key={prog} value={prog}>{prog}</option>
                    ))
                  )}
                </select>
              </div>

              <button
                onClick={() => carregarDados()}
                disabled={loading}
                className="w-full bg-brand-600 hover:bg-brand-500 disabled:bg-slate-700 text-white font-semibold py-2.5 rounded-xl text-xs transition-all shadow-lg shadow-brand-600/20 flex items-center justify-center space-x-2"
              >
                {loading ? <Icon name="loader-2" className="w-4 h-4 animate-spin" /> : <Icon name="database" className="w-4 h-4" />}
                <span>{loading ? "Processando..." : "Consultar Banco de Dados"}</span>
              </button>

            </div>
            
            <div className="p-3.5 border-t border-slate-700/80 bg-slate-900/50 text-[11px] text-slate-400 truncate" title={loadingMunicipios ? "Carregando municípios..." : dbStatus}>
              {loadingMunicipios ? "Carregando municípios..." : dbStatus}
            </div>
          </aside>

          {/* MAIN CONTENT */}
          <main className="flex-1 flex flex-col overflow-hidden bg-slate-900">
            <header className="h-16 border-b border-slate-700/80 bg-slate-800/50 px-6 flex items-center justify-between flex-shrink-0">
              <nav className="flex space-x-1 bg-slate-900/80 p-1 rounded-xl border border-slate-700/60 overflow-x-auto">
                {['dashboard', 'tabela', 'grafo_programas', 'grafo_pessoa', 'busca_global', 'cnpj', 'gestao_api', 'about'].map(tab => (
                  <button 
                    key={tab}
                    onClick={() => {
                      setActiveTab(tab);
                      setPagina(1);
                      if (tab === "cnpj") setCnpjMontada(true);
                    }}
                    className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap ${activeTab === tab ? "bg-brand-600 text-white shadow" : "text-slate-400 hover:text-slate-200"}`}
                  >
                    <Icon name={
                      tab === 'dashboard' ? 'bar-chart-3' : 
                      tab === 'tabela' ? 'table' : 
                      tab === 'grafo_programas' ? 'git-fork' : 
                      tab === 'grafo_pessoa' ? 'user-check' : 
                      tab === 'busca_global' ? 'globe' :
                      tab === 'cnpj' ? 'database' :
                      tab === 'gestao_api' ? 'cloud-download' :
                      tab === 'about' ? 'shield-check' : 'cloud-download'
                    } className="w-4 h-4" />
                    <span>{
                      tab === 'dashboard' ? 'Visão Geral' : 
                      tab === 'tabela' ? 'Tabela' : 
                      tab === 'grafo_programas' ? 'Rede Programas' : 
                      tab === 'grafo_pessoa' ? 'Grafo Pessoa' : 
                      tab === 'busca_global' ? 'Busca Global' :
                      tab === 'cnpj' ? 'CNPJs' :
                      tab === 'gestao_api' ? 'Gestão & API Gov.br' : 'About'
                    }</span>
                  </button>
                ))}
              </nav>
              <button onClick={downloadCSV} disabled={dados.length===0} className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 border border-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium flex items-center space-x-1.5 transition-colors">
                <Icon name="download" className="w-3.5 h-3.5 text-emerald-400" />
                <span>{activeTab === "dashboard" && tipoConsulta === "Adicionar beneficiários" ? "Exportar resumo CSV" : "Exportar CSV"}</span>
              </button>
            </header>

            <div className="flex-1 p-6 overflow-y-auto relative">
              {erroMunicipios && (
                <div role="alert" className="mb-6 bg-rose-500/10 border border-rose-500/40 text-rose-200 p-5 rounded-2xl text-sm shadow-lg shadow-rose-950/20">
                  <h2 className="font-bold text-base text-rose-100">Não foi possível carregar os municípios</h2>
                  <p className="mt-2">{erroMunicipios}</p>
                  <p className="mt-3 text-rose-200/90">
                    Confira se o backend FastAPI está rodando na porta 8000. No terminal do projeto, execute:
                  </p>
                  <code className="inline-block mt-2 rounded-lg bg-slate-950/70 px-3 py-2 font-mono text-rose-100">
                    uvicorn api:app --reload
                  </code>
                  <div>
                    <button
                      type="button"
                      onClick={() => {
                        setErroMunicipios(null);
                        setMunicipiosReloadKey(value => value + 1);
                      }}
                      className="mt-4 rounded-lg border border-rose-300/40 px-3 py-2 text-xs font-semibold text-rose-100 hover:bg-rose-400/10"
                    >
                      Tentar novamente
                    </button>
                  </div>
                </div>
              )}
              {erroFiltros && (
                <div role="alert" className="mb-4 bg-rose-500/10 border border-rose-500/30 text-rose-400 p-4 rounded-2xl text-xs">
                  {erroFiltros}
                </div>
              )}
              {erro && (
                <div className="mb-6 bg-rose-500/10 border border-rose-500/30 text-rose-400 p-4 rounded-2xl flex items-start space-x-3 shadow-lg shadow-rose-900/20">
                  <Icon name="alert-circle" className="w-5 h-5 flex-shrink-0 mt-0.5" />
                  <div role="alert" className="text-xs"><p className="font-semibold">Falha ao carregar dados</p><p className="mt-0.5">{erro}</p></div>
                </div>
              )}

              {activeTab === "dashboard" && <DashboardView dados={dados} resumo={metricasResumo} selectedMun={selectedMun} selectedPrograma={selectedPrograma} selectedAno={selectedAno} selectedMes={selectedMes} tipoConsulta={tipoConsulta} loading={loading} />}
              {activeTab === "tabela" && <TabelaView dados={dados} loading={loading} tipoConsulta={tipoConsulta} onSelectPessoa={(nis) => { setNisGrafo(nis); setActiveTab("grafo_pessoa"); }} serverPagination={tipoConsulta === "Adicionar beneficiários"} pagina={pagina} totalPaginas={totalPaginas} totalRegistros={totalRegistros} onPageChange={setPagina} busca={buscaTabela} onSearch={(value) => { setBuscaTabela(value); setPagina(1); }} />}
              {activeTab === "grafo_programas" && <GrafoProgramasView selectedMun={selectedMun} selectedAno={selectedAno} apiUrl={API_URL} />}
              {activeTab === "grafo_pessoa" && <GrafoPessoaView nisGrafo={nisGrafo} setNisGrafo={setNisGrafo} selectedMun={selectedMun} selectedAno={selectedAno} apiUrl={API_URL} />}
              {activeTab === "busca_global" && <BuscaGlobalView termo={termoBuscaGlobal} setTermo={setTermoBuscaGlobal} resultados={resultadosBuscaGlobal} loading={loadingBuscaGlobal} erro={erroBuscaGlobal} onBuscar={executarBuscaGlobal} onSelectNis={(nis) => { setNisGrafo(nis); setActiveTab("grafo_pessoa"); }} />}
              {cnpjMontada && (
                <div hidden={activeTab !== "cnpj"}>
                  <CnpjView
                    active={activeTab === "cnpj"}
                    selectedMun={selectedMun}
                    apiUrl={API_URL}
                  />
                </div>
              )}
              {activeTab === "gestao_api" && <FormularioInsercaoDados selectedMun={selectedMun} apiUrl={API_URL} onSucesso={({ programa, ano, mes }) => {
                setTipoConsulta("Adicionar beneficiários");
                setSelectedPrograma(programa);
                setSelectedAno(ano);
                setSelectedMes(mes);
                setPagina(1);
                setBuscaTabela("");
                setMunicipiosReloadKey(value => value + 1);
              }} />}
              {activeTab === "about" && <AboutView />}
            </div>
          </main>
        </div>
      );
    }

    function AboutView() {
      const [section, setSection] = useState("sobre");
      const sections = [
        { id: "sobre", label: "Sobre o projeto" },
        { id: "lgpd", label: "LGPD e privacidade" },
        { id: "fontes", label: "Fontes de dados" },
      ];

      const sourceLink = (href, label, description) => (
        <a
          key={href}
          href={href}
          target="_blank"
          rel="noreferrer"
          className="group rounded-xl border border-slate-700 bg-slate-900/70 p-4 transition-colors hover:border-brand-500/60"
        >
          <span className="flex items-center gap-2 font-semibold text-brand-300 group-hover:text-brand-200">
            {label}
            <Icon name="external-link" className="h-3.5 w-3.5" />
          </span>
          <span className="mt-2 block break-all text-xs leading-relaxed text-slate-400">{description}</span>
        </a>
      );

      return (
        <div className="mx-auto max-w-5xl space-y-6 pb-12">
          <header className="rounded-2xl border border-brand-500/30 bg-slate-800 p-6">
            <p className="text-xs font-semibold uppercase tracking-widest text-brand-300">About</p>
            <h2 className="mt-2 text-2xl font-bold text-white">Sobre o painel e seus dados</h2>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-300">
              Informações sobre o funcionamento do painel, as fontes consultadas e o tratamento de dados pessoais.
            </p>
          </header>

          <nav aria-label="Seções About" className="flex flex-wrap gap-2 rounded-xl border border-slate-700 bg-slate-800/70 p-2">
            {sections.map(item => (
              <button
                key={item.id}
                type="button"
                aria-pressed={section === item.id}
                onClick={() => setSection(item.id)}
                className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                  section === item.id
                    ? "bg-brand-600 text-white"
                    : "text-slate-300 hover:bg-slate-700"
                }`}
              >
                {item.label}
              </button>
            ))}
          </nav>

          {section === "sobre" && (
            <section className="space-y-4 rounded-2xl border border-slate-700 bg-slate-800 p-6">
              <h3 className="text-lg font-bold text-white">Painel municipal de benefícios e CNPJs</h3>
              <p className="text-sm leading-relaxed text-slate-300">
                O sistema consulta dados públicos de benefícios por município, guarda os registros localmente em SQLite e permite visualizar totais, beneficiários e relações cadastrais de empresas. A coleta externa é iniciada pelo servidor da aplicação; a chave da API do Portal da Transparência é configurada separadamente na área de Gestão.
              </p>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-xl border border-slate-700 bg-slate-900/70 p-4">
                  <h4 className="font-semibold text-white">Dados de benefícios</h4>
                  <p className="mt-2 text-xs leading-relaxed text-slate-400">
                    Conforme a disponibilidade da fonte: programa, município, competência, valores, nome, NIS e CPF mascarado. Dados de representantes legais podem aparecer em registros que os forneçam.
                  </p>
                </div>
                <div className="rounded-xl border border-slate-700 bg-slate-900/70 p-4">
                  <h4 className="font-semibold text-white">Dados cadastrais de empresas</h4>
                  <p className="mt-2 text-xs leading-relaxed text-slate-400">
                    CNPJ, razão social, situação, endereço empresarial, capital, atividade econômica e quadro societário, conforme retornados pelas fontes consultadas.
                  </p>
                </div>
              </div>
              <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-xs leading-relaxed text-amber-100">
                Cruzamentos entre beneficiários e sócios são indicativos: exigem coincidência de nome normalizado e dos dígitos visíveis do CPF mascarado, mas não comprovam identidade, renda, irregularidade ou vínculo familiar.
              </p>
            </section>
          )}

          {section === "lgpd" && (
            <section className="space-y-5 rounded-2xl border border-slate-700 bg-slate-800 p-6">
              <div>
                <h3 className="text-lg font-bold text-white">LGPD e privacidade</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-300">
                  Esta página descreve o comportamento técnico identificado no sistema. Ela não substitui o aviso de privacidade do controlador nem define, por si só, a base legal de cada implantação.
                </p>
              </div>
              <dl className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl bg-slate-900/70 p-4">
                  <dt className="font-semibold text-white">Finalidade</dt>
                  <dd className="mt-2 text-xs leading-relaxed text-slate-400">Consultar e apresentar informações públicas de benefícios e cadastros empresariais por município, com filtros, relatórios e cruzamentos explicitados nesta página.</dd>
                </div>
                <div className="rounded-xl bg-slate-900/70 p-4">
                  <dt className="font-semibold text-white">Dados tratados</dt>
                  <dd className="mt-2 text-xs leading-relaxed text-slate-400">O banco local pode conter nomes, NIS, CPF mascarado, benefício, competência e valor; os dados empresariais podem conter CNPJ, endereço da empresa e informações de sócios, inclusive identificadores mascarados.</dd>
                </div>
                <div className="rounded-xl bg-slate-900/70 p-4">
                  <dt className="font-semibold text-white">Armazenamento e compartilhamento</dt>
                  <dd className="mt-2 text-xs leading-relaxed text-slate-400">Os dados coletados são armazenados no SQLite local e há arquivos de cache para coletas de CNPJ. A aplicação consulta os provedores listados em Fontes de dados. CSV/XLSX podem ser exportados por quem acessa o painel; restrinja o acesso ao servidor e aos arquivos.</dd>
                </div>
                <div className="rounded-xl bg-slate-900/70 p-4">
                  <dt className="font-semibold text-white">Prazo de retenção e segurança</dt>
                  <dd className="mt-2 text-xs leading-relaxed text-slate-400">O projeto não configura prazo automático de eliminação dos dados coletados. O responsável pela implantação deve definir retenção, controlar acessos, proteger backups e usar HTTPS/TLS quando houver acesso pela rede.</dd>
                </div>
              </dl>
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-xs leading-relaxed text-amber-100">
                <strong>Controlador e contato:</strong> a identificação do controlador, seu CNPJ institucional (quando aplicável) e um canal para solicitações de titulares não estão configurados neste projeto. Esses dados precisam ser informados pelo responsável pela implantação; não é possível inferi-los das fontes de dados.
              </div>
              <p className="text-xs leading-relaxed text-slate-400">
                O responsável pela implantação deve documentar a base legal, informar os titulares e disponibilizar um canal para exercício dos direitos previstos na LGPD. Consulte também as orientações da <a className="text-brand-300 underline" href="https://www.gov.br/anpd/pt-br" target="_blank" rel="noreferrer">Autoridade Nacional de Proteção de Dados (ANPD)</a>.
              </p>
            </section>
          )}

          {section === "fontes" && (
            <section className="space-y-5 rounded-2xl border border-slate-700 bg-slate-800 p-6">
              <div>
                <h3 className="text-lg font-bold text-white">Fontes de dados e integrações</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-300">
                  Os dados e identificadores de CNPJ listados abaixo são os usados para consultar e enriquecer os cadastros exibidos. O CNPJ institucional do operador do painel não é informado no código.
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {[
                  sourceLink("https://portaldatransparencia.gov.br/", "Portal da Transparência", "Portal federal de transparência e acesso aos dados públicos."),
                  sourceLink("https://portaldatransparencia.gov.br/api-de-dados", "API de Dados do Portal da Transparência", "Informações para obtenção da chave e documentação de acesso à API."),
                  sourceLink("https://api.portaldatransparencia.gov.br/swagger-ui/index.html#/", "Documentação Swagger da API", "Especificação dos endpoints consultados para benefícios e pagamentos."),
                  sourceLink("https://api.casadosdados.com.br/v5/public/cnpj/pesquisa", "Casa dos Dados — pesquisa de CNPJ", "Endpoint de pesquisa municipal usado para obter a lista de empresas."),
                  sourceLink("https://brasilapi.com.br/docs#tag/CNPJ", "BrasilAPI — CNPJ", "Consulta usada para complementar dados públicos da empresa e do quadro societário."),
                  sourceLink("https://github.com/kelvins/municipios-brasileiros", "Municípios brasileiros", "Referência do conjunto de municípios e códigos IBGE mencionado na documentação do projeto."),
                ]}
              </div>
              <p className="rounded-xl border border-slate-700 bg-slate-900/70 p-4 text-xs leading-relaxed text-slate-400">
                A disponibilidade, atualização e conteúdo dos registros dependem de cada provedor. Confira as condições de uso e a documentação das fontes antes de reutilizar os dados.
              </p>
            </section>
          )}
        </div>
      );
    }

    // --- DASHBOARD VIEW ---
    function DashboardView({ dados, resumo, selectedMun, selectedPrograma, selectedAno, selectedMes, tipoConsulta, loading }) {
      const chartRef = useRef(null);
      const chartInstance = useRef(null);

      const metricas = useMemo(() => {
        if (resumo) {
          const totalValor = Number(resumo.total_valor) || 0;
          const totalBeneficiados = Number(resumo.total_beneficiados) || 0;
          return {
            totalValor,
            totalBeneficiados,
            ticketMedio: totalBeneficiados ? totalValor / totalBeneficiados : 0,
            meses: Number(resumo.meses) || 0,
          };
        }
        if (!dados || dados.length === 0) return { totalValor: 0, totalBeneficiados: 0, ticketMedio: 0, meses: 0 };
        let totalValor = 0; let totalBeneficiados = 0;
        
        if (tipoConsulta === "Agregado mensal do ano") {
          totalValor = dados.reduce((acc, r) => acc + (parseFloat(r.valor) || 0), 0);
          totalBeneficiados = dados.reduce((acc, r) => acc + (parseInt(r.beneficiados) || 0), 0);
        } else {
          totalValor = dados.reduce((acc, r) => acc + (parseFloat(r.valor_saque) || 0), 0);
          totalBeneficiados = new Set(dados.map(r => r.nis)).size;
        }
        return { totalValor, totalBeneficiados, ticketMedio: totalBeneficiados ? totalValor/totalBeneficiados : 0, meses: new Set(dados.map(d => d.mes)).size };
      }, [dados, resumo, tipoConsulta]);

      useEffect(() => {
        if (chartInstance.current) { 
          chartInstance.current.destroy(); 
          chartInstance.current = null; 
        }
        if (!chartRef.current || !dados || dados.length === 0) return;

        const ctx = chartRef.current.getContext('2d');
        const agrupado = {};
        
        dados.forEach(item => {
          const val = parseFloat(item.valor || item.valor_saque) || 0;
          const ano = parseInt(item.ano) || 0;
          const mesNum = parseInt(item.mes_num || item.mes) || 0;
          
          const label = ano ? `${String(mesNum).padStart(2,'0')}/${ano}` : String(mesNum).padStart(2,'0');
          const sortKey = ano ? `${ano}-${String(mesNum).padStart(2, '0')}` : String(mesNum).padStart(2, '0');
          
          if (!agrupado[sortKey]) agrupado[sortKey] = { label, val: 0 };
          agrupado[sortKey].val += val;
        });

        const sortedKeys = Object.keys(agrupado).sort();
        const labels = sortedKeys.map(k => agrupado[k].label);
        const valores = sortedKeys.map(k => agrupado[k].val);

        chartInstance.current = new Chart(ctx, {
          type: 'bar',
          data: {
            labels: labels,
            datasets: [{
              label: 'Repasse Governamental (R$)',
              data: valores,
              backgroundColor: 'rgba(59, 130, 246, 0.7)',
              borderColor: 'rgba(59, 130, 246, 1)',
              borderWidth: 1, borderRadius: 6,
            }]
          },
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { labels: { color: '#94a3b8' } } },
            scales: { 
              x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } }, 
              y: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } } 
            }
          }
        });
      }, [dados, tipoConsulta]);

      if (!selectedMun) return null;

      return (
        <div className="space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-800/60 p-6 rounded-2xl border border-slate-700/60 shadow-md">
            <div>
              <h2 className="text-xl font-bold text-white flex items-center space-x-2">
                <span>{selectedPrograma === "Todos" ? "Todos os Programas Sociais" : selectedPrograma}</span>
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-brand-500/20 text-brand-300 border border-brand-500/30 font-medium">
                  {selectedMun.nome} - {selectedMun.uf} | Ano: {selectedAno} | Mês: {selectedMes}
                </span>
              </h2>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-slate-800 p-5 rounded-2xl border border-slate-700/70 shadow-lg relative overflow-hidden group">
              <div className="absolute -right-4 -top-4 opacity-5 group-hover:scale-110 transition-transform duration-500"><Icon name="dollar-sign" className="w-24 h-24" /></div>
              <span className="text-xs text-slate-400 font-medium relative z-10">Total Investido</span>
              <p className="text-2xl font-bold text-emerald-400 mt-2 relative z-10">R$ {metricas.totalValor.toLocaleString('pt-BR', {minimumFractionDigits:2})}</p>
            </div>
            <div className="bg-slate-800 p-5 rounded-2xl border border-slate-700/70 shadow-lg relative overflow-hidden group">
              <div className="absolute -right-4 -top-4 opacity-5 group-hover:scale-110 transition-transform duration-500"><Icon name="users" className="w-24 h-24" /></div>
              <span className="text-xs text-slate-400 font-medium relative z-10">{tipoConsulta === "Agregado mensal do ano" ? "Benefícios Pagos" : "Pessoas Únicas"}</span>
              <p className="text-2xl font-bold text-brand-400 mt-2 relative z-10">{metricas.totalBeneficiados.toLocaleString('pt-BR')}</p>
            </div>
            <div className="bg-slate-800 p-5 rounded-2xl border border-slate-700/70 shadow-lg">
              <span className="text-xs text-slate-400 font-medium">Ticket Médio</span>
              <p className="text-2xl font-bold text-amber-400 mt-2">R$ {metricas.ticketMedio.toLocaleString('pt-BR', {minimumFractionDigits:2})}</p>
            </div>
            <div className="bg-slate-800 p-5 rounded-2xl border border-slate-700/70 shadow-lg">
              <span className="text-xs text-slate-400 font-medium">Meses Encontrados</span>
              <p className="text-2xl font-bold text-purple-400 mt-2">{metricas.meses}</p>
            </div>
          </div>

          <div className="bg-slate-800 p-6 rounded-2xl border border-slate-700/70 h-[380px] shadow-lg relative flex flex-col">
            <h3 className="text-sm font-semibold text-white mb-4">Evolução de Repasses (R$)</h3>
            {loading ? (
              <div className="flex-1 flex flex-col items-center justify-center text-brand-500">
                <Icon name="loader-2" className="w-8 h-8 animate-spin mb-2" />
                <span className="text-xs font-medium text-slate-400">Processando cruzamentos do banco...</span>
              </div>
            ) : (!dados || dados.length === 0) ? (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-500 opacity-60">
                <Icon name="bar-chart-2" className="w-12 h-12 mb-2" />
                <span className="text-sm font-medium">Nenhum registro encontrado localmente.</span>
                <span className="text-xs mt-1">Use a aba "Gestão & API Gov.br" para coletar mais dados.</span>
              </div>
            ) : (
              <div className="w-full flex-1 relative animate-fadeIn"><canvas ref={chartRef}></canvas></div>
            )}
          </div>
        </div>
      );
    }

    // --- TABELA VIEW ---
    function TabelaView({
      dados, loading, tipoConsulta, onSelectPessoa, serverPagination,
      pagina, totalPaginas, totalRegistros, onPageChange, busca, onSearch,
    }) {
      const [filtroLocal, setFiltroLocal] = useState("");
      const [paginaLocal, setPaginaLocal] = useState(1);
      const porPagina = 25;

      const dadosFiltrados = useMemo(() => {
        if (serverPagination || !filtroLocal) return dados;
        const f = filtroLocal.toLowerCase();
        return dados.filter(item => 
          (item.nome && item.nome.toLowerCase().includes(f)) ||
          (item.nis && item.nis.includes(f)) ||
          (item.programa && item.programa.toLowerCase().includes(f))
        );
      }, [dados, filtroLocal, serverPagination]);

      const paginados = useMemo(() => {
        if (serverPagination) return dadosFiltrados;
        const inicio = (paginaLocal - 1) * porPagina;
        return dadosFiltrados.slice(inicio, inicio + porPagina);
      }, [dados, dadosFiltrados, paginaLocal, serverPagination]);
      const paginaAtual = serverPagination ? pagina : paginaLocal;
      const paginas = serverPagination
        ? totalPaginas
        : Math.ceil(dadosFiltrados.length / porPagina) || 1;
      const total = serverPagination ? totalRegistros : dadosFiltrados.length;
      const dadosCompativeis = paginados.every(
        item => item && typeof item.programa === "string",
      );

      return (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="relative w-full sm:w-96">
              <Icon name="search" className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
              <input type="text" placeholder="Buscar beneficiário, NIS ou programa..." value={serverPagination ? busca : filtroLocal} onChange={(e) => {
                if (serverPagination) onSearch(e.target.value);
                else { setFiltroLocal(e.target.value); setPaginaLocal(1); }
              }} className="w-full bg-slate-800 border border-slate-700 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-200 focus:ring-2 focus:ring-brand-500 outline-none shadow-sm" />
            </div>
            <div className="text-xs text-slate-400 font-medium">Exibindo {total.toLocaleString('pt-BR')} registros no banco</div>
          </div>
          
          <div className="bg-slate-800 rounded-2xl border border-slate-700/80 overflow-hidden shadow-xl">
            <div className="overflow-x-auto min-h-[300px]">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="bg-slate-900 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-700/80">
                  <tr>
                    {tipoConsulta === "Agregado mensal do ano" ? (
                      <><th className="p-4">Período</th><th className="p-4">Programa Governamental</th><th className="p-4">Beneficiados</th><th className="p-4 text-right">Repasse Total</th></>
                    ) : (
                      <><th className="p-4">Programa</th><th className="p-4">NIS</th><th className="p-4">Nome do Beneficiário</th><th className="p-4">Período</th><th className="p-4 text-right">Valor Pago</th><th className="p-4 text-center">Conexões</th></>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/50">
                  {loading ? (
                    <tr><td colSpan="6" className="p-12 text-center text-brand-500"><Icon name="loader-2" className="w-8 h-8 animate-spin mx-auto mb-3" />Montando grade de dados...</td></tr>
                  ) : !dadosCompativeis ? (
                    <tr><td colSpan="6" role="alert" className="p-12 text-center text-amber-300">Os dados estão sendo atualizados para o formato da tabela. Aguarde a consulta.</td></tr>
                  ) : paginados.length === 0 ? (
                    <tr><td colSpan="6" className="p-12 text-center text-slate-500">Tabela vazia para os filtros selecionados.</td></tr>
                  ) : (
                    paginados.map((item, idx) => (
                      <tr key={idx} className="hover:bg-slate-700/40 transition-colors">
                        {tipoConsulta === "Agregado mensal do ano" ? (
                          <>
                            <td className="p-4 font-semibold text-white">{item.ano ? `${String(item.mes_num).padStart(2,'0')}/${item.ano}` : item.mes}</td>
                            <td className="p-4 text-brand-300 font-medium">{item.programa.replace(' (sacado)','')}</td>
                            <td className="p-4">{parseInt(item.beneficiados).toLocaleString('pt-BR')}</td>
                            <td className="p-4 text-right font-bold text-emerald-400">R$ {parseFloat(item.valor).toLocaleString('pt-BR', {minimumFractionDigits:2})}</td>
                          </>
                        ) : (
                          <>
                            <td className="p-4 text-brand-300 font-medium">{item.programa.replace(' (sacado)','')}</td>
                            <td className="p-4 font-mono text-slate-400">{item.nis}</td>
                            <td className="p-4 font-medium text-slate-100">{item.nome}</td>
                            <td className="p-4 text-slate-400">{String(item.mes).padStart(2,'0')}/{item.ano}</td>
                            <td className="p-4 text-right font-bold text-emerald-400">R$ {parseFloat(item.valor_saque).toLocaleString('pt-BR', {minimumFractionDigits:2})}</td>
                            <td className="p-4 text-center">
                              <button onClick={() => onSelectPessoa(item.nis)} className="bg-brand-600/20 hover:bg-brand-600 border border-brand-500/30 hover:border-transparent text-brand-300 hover:text-white px-2.5 py-1.5 rounded-lg transition-all text-[11px] flex items-center justify-center space-x-1.5 mx-auto"><Icon name="share-2" className="w-3.5 h-3.5" /><span>Grafo</span></button>
                            </td>
                          </>
                        )}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            
            <div className="p-4 border-t border-slate-700/80 bg-slate-900/40 flex items-center justify-between text-xs text-slate-400">
              <span className="font-medium">Página {paginaAtual} de {paginas}</span>
              <div className="flex space-x-2">
                <button onClick={() => serverPagination ? onPageChange(paginaAtual - 1) : setPaginaLocal(paginaAtual - 1)} disabled={paginaAtual === 1} className="px-4 py-2 rounded-xl bg-slate-800 border border-slate-700 hover:bg-slate-700 disabled:opacity-40 transition-colors font-medium">Anterior</button>
                <button onClick={() => serverPagination ? onPageChange(paginaAtual + 1) : setPaginaLocal(paginaAtual + 1)} disabled={paginaAtual === paginas} className="px-4 py-2 rounded-xl bg-slate-800 border border-slate-700 hover:bg-slate-700 disabled:opacity-40 transition-colors font-medium">Próximo</button>
              </div>
            </div>
          </div>
        </div>
      );
    }

    // --- GRAFOS ---
    function GrafoProgramasView({ selectedMun, selectedAno, apiUrl }) {
      const containerRef = useRef(null); const [loading, setLoading] = useState(true);
      const [erro, setErro] = useState(null);
      useEffect(() => {
        if (!selectedMun) return undefined;
        const controller = new AbortController();
        let network;
        setLoading(true);
        setErro(null);
        const query = new URLSearchParams({
          codigo_ibge: selectedMun.codigo_ibge,
          ano: selectedAno,
        });

        fetchJson(`${apiUrl}/grafo/programas?${query}`, { signal: controller.signal })
          .then(async graphData => {
            const [{ Network }, { DataSet }] = await Promise.all([
              import("vis-network"),
              import("vis-data"),
            ]);
            if (controller.signal.aborted) return;
            if (containerRef.current && graphData.nodes) {
              const data = { nodes: new DataSet(graphData.nodes), edges: new DataSet(graphData.edges) };
              network = new Network(containerRef.current, data, { physics: { barnesHut: { gravitationalConstant: -3000, springLength: 120 } }, nodes: { shape: 'dot', size: 18 } });
            }
          })
          .catch(error => {
            if (!controller.signal.aborted && !isAbortError(error)) {
              setErro(`Falha ao carregar o grafo: ${error.message}`);
            }
          })
          .finally(() => {
            if (!controller.signal.aborted) setLoading(false);
          });

        return () => {
          controller.abort();
          network?.destroy();
        };
      }, [selectedMun, selectedAno, apiUrl]);

      if (!selectedMun) return null;
      return (
        <div className="bg-slate-800 rounded-2xl border border-slate-700/80 p-6 space-y-4 shadow-xl">
          <div><h3 className="text-base font-bold text-white flex items-center gap-2"><Icon name="git-merge" className="w-5 h-5 text-brand-400" /> Rede de Cruzamento entre Programas</h3><p className="text-xs text-slate-400 mt-1">Nós conectam programas que compartilham as mesmas pessoas (CPF/NIS) durante o ano de {selectedAno}.</p></div>
          {erro && <p role="alert" className="text-xs text-rose-400">{erro}</p>}
          <div className="h-[550px] bg-slate-900/90 rounded-xl border border-slate-700 relative overflow-hidden shadow-inner">
            {loading && <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900/80 z-10 text-brand-500"><Icon name="loader-2" className="w-8 h-8 animate-spin mb-2" /><span className="text-xs">Desenhando relações...</span></div>}
            <div ref={containerRef} className="w-full h-full"></div>
          </div>
        </div>
      );
    }

    function GrafoPessoaView({ nisGrafo, setNisGrafo, selectedMun, selectedAno, apiUrl }) {
      const containerRef = useRef(null);
      const [loading, setLoading] = useState(false);
      const [nisInput, setNisInput] = useState(nisGrafo);
      const [erro, setErro] = useState(null);

      useEffect(() => {
        if (!nisGrafo || !selectedMun) return undefined;
        const controller = new AbortController();
        let network;
        setNisInput(nisGrafo);
        setLoading(true);
        setErro(null);
        const query = new URLSearchParams({
          codigo_ibge: selectedMun.codigo_ibge,
          ano: selectedAno,
        });

        fetchJson(`${apiUrl}/grafo/pessoa/${encodeURIComponent(nisGrafo)}?${query}`, {
          signal: controller.signal,
        })
          .then(async graphData => {
            const [{ Network }, { DataSet }] = await Promise.all([
              import("vis-network"),
              import("vis-data"),
            ]);
            if (controller.signal.aborted) return;
            if (containerRef.current && graphData.nodes) {
              network = new Network(
                containerRef.current,
                { nodes: new DataSet(graphData.nodes), edges: new DataSet(graphData.edges) },
                { physics: { solver: 'forceAtlas2Based' } },
              );
            }
          })
          .catch(error => {
            if (!controller.signal.aborted && !isAbortError(error)) {
              setErro(`Falha ao carregar o grafo: ${error.message}`);
            }
          })
          .finally(() => {
            if (!controller.signal.aborted) setLoading(false);
          });

        return () => {
          controller.abort();
          network?.destroy();
        };
      }, [nisGrafo, selectedMun, selectedAno, apiUrl]);
      
      return (
        <div className="bg-slate-800 rounded-2xl border border-slate-700/80 p-6 space-y-4 shadow-xl">
          <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
            <div><h3 className="text-base font-bold text-white flex items-center gap-2"><Icon name="user-check" className="w-5 h-5 text-emerald-400" /> Grafo de Beneficiário Único</h3><p className="text-xs text-slate-400 mt-1">Conexões entre a pessoa, representantes legais e programas no município.</p></div>
            <div className="flex items-center space-x-2 w-full sm:w-auto bg-slate-900/50 p-1.5 rounded-xl border border-slate-700">
              <input type="text" placeholder="Cole o NIS aqui..." value={nisInput} onChange={(e) => setNisInput(e.target.value)} className="bg-transparent border-none px-3 py-1.5 text-xs text-slate-200 outline-none font-mono w-48" />
              <button onClick={() => setNisGrafo(nisInput)} className="bg-emerald-600 hover:bg-emerald-500 text-white font-medium px-4 py-1.5 rounded-lg text-xs transition-all shadow">Mapear</button>
            </div>
          </div>
          {erro && <p role="alert" className="text-xs text-rose-400">{erro}</p>}
          <div className="h-[550px] bg-slate-900/90 rounded-xl border border-slate-700 relative overflow-hidden shadow-inner">
            {loading && <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900/80 z-10 text-emerald-400"><Icon name="loader-2" className="w-8 h-8 animate-spin mb-2" /><span className="text-xs">Extraindo conexões...</span></div>}
            {(!nisGrafo && !loading) && <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm">Insira um NIS válido acima para desenhar o grafo.</div>}
            <div ref={containerRef} className="w-full h-full outline-none"></div>
          </div>
        </div>
      );
    }

    // --- BUSCA GLOBAL ---
    function BuscaGlobalView({ termo, setTermo, resultados, loading, erro, onBuscar, onSelectNis }) {
      return (
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="bg-slate-800 p-6 rounded-2xl border border-brand-500/30 shadow-xl shadow-brand-900/10 space-y-4">
            <h3 className="text-base font-bold text-white flex items-center gap-2"><Icon name="globe" className="w-5 h-5 text-brand-400" /> Busca Global Indexada (Todos os Anos)</h3>
            <div className="flex flex-col sm:flex-row gap-3">
              <input type="text" placeholder="Digite o nome completo, fragmento ou NIS do beneficiário..." value={termo} onChange={(e) => setTermo(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && onBuscar(termo)} className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-200 outline-none focus:ring-2 focus:ring-brand-500" />
              <button onClick={() => onBuscar(termo)} className="bg-brand-600 hover:bg-brand-500 text-white px-6 py-3 rounded-xl text-sm font-semibold transition-all shadow flex items-center justify-center gap-2 w-full sm:w-auto"><Icon name="search" className="w-4 h-4" /> Buscar em tudo</button>
            </div>
          </div>
          {erro && <p role="alert" className="text-sm text-rose-400">{erro}</p>}
          {loading ? (
            <div className="text-center py-12"><Icon name="loader-2" className="w-10 h-10 animate-spin mx-auto text-brand-500" /></div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {resultados.map((p, i) => (
                <div key={i} className="bg-slate-800 p-5 rounded-xl border border-slate-700/80 shadow flex justify-between items-center group hover:border-brand-500/50 transition-colors">
                  <div>
                    <p className="font-bold text-slate-100 text-sm group-hover:text-brand-300 transition-colors">{p.nome}</p>
                    <div className="flex items-center gap-3 mt-1.5">
                      <p className="font-mono text-xs text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-700">NIS: {p.nis}</p>
                      <p className="text-[10px] text-emerald-400 font-medium uppercase">{p.programas} vínculos encontrados</p>
                    </div>
                  </div>
                  <button onClick={() => onSelectNis(p.nis)} title="Ver Grafo" className="bg-slate-900 hover:bg-brand-600 border border-slate-700 hover:border-transparent text-slate-300 hover:text-white p-3 rounded-xl transition-all"><Icon name="share-2" className="w-4 h-4" /></button>
                </div>
              ))}
              {(!loading && termo.length > 2 && resultados.length === 0) && <div className="col-span-1 md:col-span-2 text-center text-slate-500 py-8 bg-slate-800/50 rounded-2xl border border-slate-700/50">Nenhuma pessoa encontrada com este termo no banco de dados local.</div>}
            </div>
          )}
        </div>
      );
    }

    function CnpjView({ active, selectedMun, apiUrl }) {
      const [data, setData] = useState(null);
      const [page, setPage] = useState(1);
      const [refresh, setRefresh] = useState(0);
      const [loading, setLoading] = useState(false);
      const [collecting, setCollecting] = useState(false);
      const [status, setStatus] = useState(null);
      const [error, setError] = useState(null);
      const [collectionError, setCollectionError] = useState(null);
      const [message, setMessage] = useState(null);
      const [beneficiosIntermunicipais, setBeneficiosIntermunicipais] = useState(null);
      const [listaEmpresas, setListaEmpresas] = useState({ total: 0, total_paginas: 1, capital_total: 0, resultados: [], situacoes_cadastrais: [] });
      const [filtrosEmpresas, setFiltrosEmpresas] = useState({ busca: "", capital_min: "", capital_max: "", situacoes_cadastrais: [] });
      const [filtrosAplicados, setFiltrosAplicados] = useState({ busca: "", capital_min: "", capital_max: "", situacoes_cadastrais: [] });
      const [programaSocio, setProgramaSocio] = useState("");
      const [listaPage, setListaPage] = useState(1);
      const [grafoData, setGrafoData] = useState(null);
      const [grafoLoading, setGrafoLoading] = useState(false);
      const networkRef = useRef(null);
      const cruzamentoCarregadoRef = useRef(null);
      const empresasCarregadasRef = useRef(null);
      const grafoCarregadoRef = useRef(null);
      const beneficiosCarregadosRef = useRef(null);
      const codigoIbge = selectedMun?.codigo_ibge;

      useEffect(() => {
        setPage(1);
        setListaPage(1);
        setProgramaSocio("");
        setFiltrosEmpresas(current =>
          current.busca || current.capital_min || current.capital_max || current.situacoes_cadastrais.length
            ? { busca: "", capital_min: "", capital_max: "", situacoes_cadastrais: [] }
            : current,
        );
        setFiltrosAplicados(current =>
          current.busca || current.capital_min || current.capital_max || current.situacoes_cadastrais.length
            ? { busca: "", capital_min: "", capital_max: "", situacoes_cadastrais: [] }
            : current,
        );
        setCollecting(false);
        setStatus(null);
        setError(null);
        setCollectionError(null);
        setMessage(null);
      }, [codigoIbge]);

      useEffect(() => {
        if (!active || !codigoIbge) return undefined;
        const requestKey = `${apiUrl}:${codigoIbge}:${JSON.stringify(filtrosAplicados)}:${programaSocio}:${page}:${refresh}`;
        if (cruzamentoCarregadoRef.current === requestKey) return undefined;
        const controller = new AbortController();
        setLoading(true);
        setError(null);
        const query = new URLSearchParams({
          codigo_ibge: codigoIbge,
          pagina: String(page),
          por_pagina: "50",
        });
        if (filtrosAplicados.busca) query.set("busca", filtrosAplicados.busca);
        if (filtrosAplicados.capital_min) query.set("capital_min", filtrosAplicados.capital_min);
        if (filtrosAplicados.capital_max) query.set("capital_max", filtrosAplicados.capital_max);
        if (filtrosAplicados.situacoes_cadastrais.length) {
          query.set("situacoes_cadastrais", filtrosAplicados.situacoes_cadastrais.join(","));
        }
        if (programaSocio) query.set("programa", programaSocio);
        fetchJson(`${apiUrl}/cnpj/cruzamento?${query}`, {
          signal: controller.signal,
        })
          .then(response => {
            if (controller.signal.aborted) return;
            setData(response);
            cruzamentoCarregadoRef.current = requestKey;
          })
          .catch(requestError => {
            if (!isAbortError(requestError)) {
              setError(`Não foi possível consultar os CNPJs: ${requestError.message}`);
            }
          })
          .finally(() => {
            if (!controller.signal.aborted) setLoading(false);
          });
        return () => controller.abort();
      }, [active, apiUrl, codigoIbge, filtrosAplicados, programaSocio, page, refresh]);

      useEffect(() => {
        if (!active || !codigoIbge) return undefined;
        const requestKey = `${apiUrl}:${codigoIbge}:${refresh}`;
        if (beneficiosCarregadosRef.current === requestKey) return undefined;
        const controller = new AbortController();
        setBeneficiosIntermunicipais(null);
        const query = new URLSearchParams({ codigo_ibge: codigoIbge });
        fetchJson(`${apiUrl}/cnpj/beneficios?${query}`, {
          signal: controller.signal,
        })
          .then(response => {
            if (controller.signal.aborted) return;
            if (!Array.isArray(response)) {
              throw new Error("O servidor retornou um resumo inválido.");
            }
            setBeneficiosIntermunicipais(response);
            beneficiosCarregadosRef.current = requestKey;
          })
          .catch(requestError => {
            if (!isAbortError(requestError)) {
              setError(`Não foi possível consultar os benefícios de outros municípios: ${requestError.message}`);
            }
          });
        return () => controller.abort();
      }, [active, apiUrl, codigoIbge, refresh]);

      useEffect(() => {
        if (!active || !codigoIbge) return undefined;
        const controller = new AbortController();
        fetchJson(
          `${apiUrl}/cnpj/status?codigo_ibge=${encodeURIComponent(codigoIbge)}`,
          { signal: controller.signal },
        )
          .then(response => {
            if (response.status && !response.status.concluido) {
              setStatus(response.status);
              setCollecting(true);
            }
          })
          .catch(requestError => {
            if (!isAbortError(requestError)) {
              setCollectionError(`Não foi possível consultar o andamento: ${requestError.message}`);
            }
          });
        return () => controller.abort();
      }, [active, apiUrl, codigoIbge]);

      useEffect(() => {
        if (!active || !collecting || !codigoIbge) return undefined;
        let ativo = true;
        let timeout;
        let controller;
        const consultarStatus = async () => {
          controller = new AbortController();
          try {
            const response = await fetchJson(
              `${apiUrl}/cnpj/status?codigo_ibge=${encodeURIComponent(codigoIbge)}`,
              { signal: controller.signal },
              5_000,
            );
            if (!ativo || !response.status) return;
            setCollectionError(null);
            setStatus(response.status);
            if (response.status.concluido) {
              setCollecting(false);
              setRefresh(value => value + 1);
              if (response.status.erro) {
                setCollectionError(`Falha na coleta de CNPJs: ${response.status.erro}`);
              } else {
                setMessage(
                  `Coleta concluída: ${response.status.empresas.toLocaleString("pt-BR")} empresas e ${response.status.socios.toLocaleString("pt-BR")} sócios salvos.`,
                );
              }
              return;
            }
          } catch (requestError) {
            if (!isAbortError(requestError)) {
              setCollectionError(`Não foi possível acompanhar a coleta: ${requestError.message}`);
            }
          } finally {
            if (ativo && !controller.signal.aborted) {
              timeout = window.setTimeout(consultarStatus, 1500);
            }
          }
        };
        consultarStatus();
        return () => {
          ativo = false;
          window.clearTimeout(timeout);
          controller?.abort();
        };
      }, [active, apiUrl, codigoIbge, collecting]);

      useEffect(() => {
        if (!active || !codigoIbge) return undefined;
        const requestKey = `${apiUrl}:${codigoIbge}:${JSON.stringify(filtrosAplicados)}:${listaPage}:${refresh}`;
        if (empresasCarregadasRef.current === requestKey) return undefined;
        const controller = new AbortController();
        const params = new URLSearchParams({
          codigo_ibge: codigoIbge,
          pagina: String(listaPage),
          por_pagina: "15",
        });
        if (filtrosAplicados.busca) params.set("busca", filtrosAplicados.busca);
        if (filtrosAplicados.capital_min) params.set("capital_min", filtrosAplicados.capital_min);
        if (filtrosAplicados.capital_max) params.set("capital_max", filtrosAplicados.capital_max);
        if (filtrosAplicados.situacoes_cadastrais.length) {
          params.set("situacoes_cadastrais", filtrosAplicados.situacoes_cadastrais.join(","));
        }
        fetchJson(`${apiUrl}/cnpj/empresas?${params.toString()}`, { signal: controller.signal })
          .then(response => {
            if (controller.signal.aborted) return;
            setListaEmpresas(response);
            empresasCarregadasRef.current = requestKey;
          })
          .catch(requestError => {
            if (!isAbortError(requestError)) {
              setError(`Não foi possível listar as empresas: ${requestError.message}`);
            }
          });
        return () => controller.abort();
      }, [active, apiUrl, codigoIbge, filtrosAplicados, listaPage, refresh]);

      useEffect(() => {
        if (!active || !codigoIbge) return undefined;
        const requestKey = `${apiUrl}:${codigoIbge}:${refresh}`;
        if (grafoCarregadoRef.current === requestKey) return undefined;
        const controller = new AbortController();
        const params = new URLSearchParams({ codigo_ibge: codigoIbge, limite: "40" });
        setGrafoLoading(true);
        fetchJson(`${apiUrl}/cnpj/grafo?${params.toString()}`, { signal: controller.signal })
          .then(response => {
            if (controller.signal.aborted) return;
            setGrafoData(response);
            grafoCarregadoRef.current = requestKey;
          })
          .catch(requestError => {
            if (!isAbortError(requestError)) {
              setGrafoLoading(false);
              setError(`Não foi possível carregar o grafo de CNPJs: ${requestError.message}`);
            }
          });
        return () => controller.abort();
      }, [active, apiUrl, codigoIbge, refresh]);

      const iniciarColeta = async () => {
        setError(null);
        setCollectionError(null);
        setMessage(null);
        setStatus({
          etapa: "iniciando",
          mensagem: "Preparando coleta de CNPJs",
          empresas: 0,
          total: 0,
          processadas: 0,
          pendentes: 0,
          tempo_decorrido: 0,
        });
        setCollecting(true);
        try {
          await fetchJson(`${apiUrl}/cnpj/coletar`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ codigo_ibge: codigoIbge }),
          });
        } catch (requestError) {
          setCollecting(false);
          setStatus(null);
          setCollectionError(`Não foi possível iniciar a coleta: ${requestError.message}`);
        }
      };

      const importarCsv = async () => {
        setError(null);
        setMessage(null);
        try {
          const response = await fetchJson(`${apiUrl}/cnpj/importar-csv`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ codigo_ibge: codigoIbge }),
          });
          setMessage(
            `CSV importado: ${response.empresas.toLocaleString("pt-BR")} empresas e ${response.socios.toLocaleString("pt-BR")} sócios.`,
          );
          setPage(1);
          setListaPage(1);
          setRefresh(value => value + 1);
        } catch (requestError) {
          setError(`Não foi possível importar o CSV local: ${requestError.message}`);
        }
      };

      const exportarLista = async (formato) => {
        const params = new URLSearchParams({
          codigo_ibge: codigoIbge,
          formato,
        });
        if (filtrosAplicados.busca) params.set("busca", filtrosAplicados.busca);
        if (filtrosAplicados.capital_min) params.set("capital_min", filtrosAplicados.capital_min);
        if (filtrosAplicados.capital_max) params.set("capital_max", filtrosAplicados.capital_max);
        if (filtrosAplicados.situacoes_cadastrais.length) {
          params.set("situacoes_cadastrais", filtrosAplicados.situacoes_cadastrais.join(","));
        }
        window.location.href = `${apiUrl}/cnpj/empresas/export?${params.toString()}`;
      };

      const alterarSituacaoCadastral = (situacao, marcada) => {
        setFiltrosEmpresas(current => {
          const selecionadas = new Set(current.situacoes_cadastrais);
          if (marcada) selecionadas.add(situacao);
          else selecionadas.delete(situacao);
          const disponiveis = listaEmpresas.situacoes_cadastrais || [];
          return {
            ...current,
            situacoes_cadastrais: selecionadas.size >= disponiveis.length
              ? []
              : [...selecionadas],
          };
        });
      };

      const baixarRelatorio = async (urlRelatorio, nomeArquivo, tipoRelatorio) => {
        setError(null);
        try {
          const response = await fetch(urlRelatorio);
          if (!response.ok) {
            const detalhe = await response.text();
            throw new Error(detalhe || `HTTP ${response.status}`);
          }
          const arquivo = await response.blob();
          const url = URL.createObjectURL(arquivo);
          const link = document.createElement("a");
          link.href = url;
          link.download = nomeArquivo;
          document.body.appendChild(link);
          link.click();
          link.remove();
          window.setTimeout(() => URL.revokeObjectURL(url), 0);
        } catch (requestError) {
          setError(`Não foi possível baixar ${tipoRelatorio}: ${requestError.message}`);
        }
      };

      const nomeMunicipioRelatorio = selectedMun.nome
        .replace(/[^a-zA-Z0-9]+/g, "_");
      const exportarRelatorio = () => {
        const params = new URLSearchParams({ codigo_ibge: codigoIbge });
        void baixarRelatorio(
          `${apiUrl}/cnpj/relatorio?${params}`,
          `relatorio_cnpj_${nomeMunicipioRelatorio}.csv`,
          "o relatório intermunicipal",
        );
      };

      const exportarRelatorioPDF = () => {
        const params = new URLSearchParams({ codigo_ibge: codigoIbge });
        if (filtrosAplicados.busca) params.set("busca", filtrosAplicados.busca);
        if (filtrosAplicados.capital_min) params.set("capital_min", filtrosAplicados.capital_min);
        if (filtrosAplicados.capital_max) params.set("capital_max", filtrosAplicados.capital_max);
        if (filtrosAplicados.situacoes_cadastrais.length) {
          params.set("situacoes_cadastrais", filtrosAplicados.situacoes_cadastrais.join(","));
        }
        if (programaSocio) params.set("programa", programaSocio);
        void baixarRelatorio(
          `${apiUrl}/cnpj/cruzamento/relatorio.pdf?${params}`,
          `relatorio_beneficiarios_socios_${nomeMunicipioRelatorio}.pdf`,
          "o relatório detalhado em PDF",
        );
      };

      const [grafoContainer, setGrafoContainer] = useState(null);
      useEffect(() => {
        if (!active || !grafoData || !grafoContainer) return undefined;
        let network;
        let ativo = true;
        let idleHandle;
        let timeoutHandle;
        const load = async () => {
          try {
            const [{ Network }, { DataSet }] = await Promise.all([
              import("vis-network"),
              import("vis-data"),
            ]);
            if (!ativo) return;
            network = new Network(grafoContainer, {
              nodes: new DataSet(grafoData.nodes),
              edges: new DataSet(grafoData.edges),
            }, {
              physics: {
                enabled: true,
                stabilization: { enabled: true, iterations: 80 },
              },
              interaction: { hover: true },
              nodes: { shape: "dot", size: 18, font: { color: "#e2e8f0" } },
              edges: { color: { color: "#94a3b8" }, arrows: { to: { enabled: false } } },
            });
            networkRef.current = network;
            network.once("stabilizationIterationsDone", () => {
              if (ativo) network.setOptions({ physics: { enabled: false } });
            });
            setGrafoLoading(false);
          } catch (loadError) {
            if (ativo) {
              setGrafoLoading(false);
              setError(`Não foi possível desenhar o grafo de CNPJs: ${loadError.message}`);
            }
          }
        };
        setGrafoLoading(true);
        if (typeof window.requestIdleCallback === "function") {
          idleHandle = window.requestIdleCallback(() => { void load(); }, { timeout: 1500 });
        } else {
          timeoutHandle = window.setTimeout(() => { void load(); }, 0);
        }
        return () => {
          ativo = false;
          if (idleHandle !== undefined && typeof window.cancelIdleCallback === "function") {
            window.cancelIdleCallback(idleHandle);
          }
          if (timeoutHandle !== undefined) window.clearTimeout(timeoutHandle);
          network?.destroy();
          if (networkRef.current === network) networkRef.current = null;
        };
      }, [active, grafoData, grafoContainer]);

      useEffect(() => {
        if (active && networkRef.current) {
          window.requestAnimationFrame(() => networkRef.current?.redraw());
        }
      }, [active]);

      if (!selectedMun) {
        return <p className="text-center p-12 text-slate-400">Selecione um município.</p>;
      }

      const ritmoEnriquecimento = status?.tempo_etapa > 0
        ? (status.processadas || 0) / status.tempo_etapa
        : 0;
      const restantesEnriquecimento = Math.max(
        0,
        (status?.pendentes || 0) - (status?.processadas || 0),
      );
      const estimativaEnriquecimento = ritmoEnriquecimento > 0
        && restantesEnriquecimento > 0
        ? restantesEnriquecimento / ritmoEnriquecimento
        : null;
      const programasSociosDisponiveis = new Set(
        data?.programas_disponiveis || [],
      );
      if (programaSocio) programasSociosDisponiveis.add(programaSocio);

      return (
        <div className="max-w-6xl mx-auto space-y-6 pb-12">
          <section className="bg-slate-800 border border-brand-500/30 rounded-2xl p-6 space-y-4">
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Icon name="database" className="w-5 h-5 text-brand-400" />
                Empresas e sócios de {selectedMun.nome} - {selectedMun.uf}
              </h2>
              <p className="text-xs text-slate-400 mt-2">
                Baixe os cadastros municipais, visualize empresas, sócios e o grafo de relacionamento do município.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row gap-3 justify-end">
              <button
                type="button"
                onClick={importarCsv}
                disabled={collecting || loading}
                className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-white rounded-xl px-4 py-2.5 text-xs font-semibold flex items-center justify-center gap-2"
              >
                <Icon name="database" className="w-4 h-4" />
                Importar CSV local
              </button>
              <button
                type="button"
                onClick={iniciarColeta}
                disabled={collecting || loading}
                className="bg-brand-600 hover:bg-brand-500 disabled:bg-slate-700 text-white rounded-xl px-5 py-2.5 text-sm font-semibold flex items-center justify-center gap-2"
              >
                {collecting ? <Icon name="loader-2" className="w-4 h-4 animate-spin" /> : <Icon name="download-cloud" className="w-4 h-4" />}
                {collecting ? "Coletando..." : "Baixar CNPJs"}
              </button>
            </div>
            {error && <p role="alert" className="text-sm text-rose-400">{error}</p>}
            {collectionError && <p role="alert" className="text-sm text-rose-400">{collectionError}</p>}
            {message && <p role="status" className="text-sm text-emerald-400">{message}</p>}
            {collecting && (
              <div role="status" className="bg-slate-900/70 border border-brand-500/20 rounded-xl p-4 text-xs text-brand-200">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold">Monitor de coleta de CNPJs</span>
                  <span className="text-slate-400">
                    {Math.floor(status?.tempo_decorrido || 0)}s
                  </span>
                </div>
                <p className="mt-2">{status?.mensagem || "Iniciando comunicação com as fontes de CNPJ..."}</p>
                {status?.empresas > 0 && (
                  <p className="mt-2 text-slate-400">
                    {status.empresas.toLocaleString("pt-BR")} empresas encontradas
                    {status.total > 0
                      ? ` de aproximadamente ${status.total.toLocaleString("pt-BR")}`
                      : ""}
                    {status.etapa === "enriquecendo" && status.pendentes > 0
                      ? ` · ${status.processadas || 0}/${status.pendentes} enriquecidas`
                      : ""}
                  </p>
                )}
                {status?.etapa === "listando" && status.total > 0 && (
                  <progress
                    className="mt-3 h-2 w-full accent-brand-500"
                    aria-label="Progresso da lista de CNPJs"
                    max={status.total}
                    value={Math.min(status.empresas, status.total)}
                  />
                )}
                {status?.etapa === "enriquecendo" && status.pendentes > 0 && (
                  <progress
                    className="mt-3 h-2 w-full accent-brand-500"
                    aria-label="Progresso do enriquecimento dos CNPJs"
                    max={status.pendentes}
                    value={Math.min(status.processadas || 0, status.pendentes)}
                  />
                )}
                {status?.etapa === "enriquecendo" && estimativaEnriquecimento !== null && (
                  <p className="mt-2 text-slate-400">
                    Ritmo médio: {ritmoEnriquecimento.toLocaleString("pt-BR", {
                      maximumFractionDigits: 1,
                    })} CNPJs por segundo · estimativa restante: ~{formatarDuracao(estimativaEnriquecimento)}
                  </p>
                )}
              </div>
            )}
          </section>

          <section className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              ["Empresas", data?.empresas],
              ["Sócios cadastrados", data?.socios],
              ["Beneficiários com correspondência forte", data?.beneficiarios_com_cnpj],
            ].map(([label, value]) => (
              <div key={label} className="bg-slate-800 border border-slate-700 rounded-2xl p-5">
                <p className="text-xs text-slate-400">{label}</p>
                <p className="text-2xl font-bold text-white mt-2">
                  {value === undefined ? "—" : Number(value).toLocaleString("pt-BR")}
                </p>
              </div>
            ))}
          </section>

          <section className="bg-slate-800 border border-slate-700 rounded-2xl p-5">
            <div className="flex items-center justify-between gap-3 mb-4">
              <div>
                <h3 className="font-bold text-white flex items-center gap-2"><Icon name="share-2" className="w-4 h-4 text-brand-400" /> Grafo de CNPJ do município</h3>
                <p className="text-[11px] text-slate-400 mt-1">Empresas conectadas por sócios em comum.</p>
              </div>
            </div>
            <div className="relative w-full h-[340px] bg-slate-900 rounded-xl border border-slate-700 overflow-hidden">
              <div ref={setGrafoContainer} className="absolute inset-0" />
              {grafoLoading && (
                <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-900/80 text-brand-300">
                  <Icon name="loader-2" className="w-7 h-7 animate-spin mb-2" />
                  <span className="text-xs">Preparando o grafo em segundo plano...</span>
                </div>
              )}
            </div>
          </section>

          <section className="bg-slate-800 border border-slate-700 rounded-2xl p-5 space-y-4">
            <div className="flex flex-col xl:flex-row xl:items-end xl:justify-between gap-4">
              <div>
                <h3 className="font-bold text-white flex items-center gap-2"><Icon name="table" className="w-4 h-4 text-brand-400" /> Empresas do município</h3>
                <p className="text-[11px] text-slate-400 mt-1">Capital social, filtro por nome e faixa de valor.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => exportarLista("csv")} className="rounded-xl bg-slate-700 px-3 py-2 text-xs font-semibold text-white">Baixar lista (CSV)</button>
                <button type="button" onClick={() => exportarLista("xlsx")} className="rounded-xl bg-brand-600 px-3 py-2 text-xs font-semibold text-white">Baixar lista (XLSX)</button>
                <button type="button" onClick={exportarRelatorio} disabled={!data?.empresas} className="rounded-xl bg-emerald-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">Baixar benefícios intermunicipais (CSV)</button>
                <button type="button" onClick={exportarRelatorioPDF} disabled={!data?.empresas} className="rounded-xl bg-indigo-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">Baixar relatório detalhado (PDF)</button>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <input value={filtrosEmpresas.busca} onChange={e => setFiltrosEmpresas({ ...filtrosEmpresas, busca: e.target.value })} placeholder="Buscar por nome ou CNPJ" className="bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200" />
              <input type="number" value={filtrosEmpresas.capital_min} onChange={e => setFiltrosEmpresas({ ...filtrosEmpresas, capital_min: e.target.value })} placeholder="Capital mínimo" className="bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200" />
              <input type="number" value={filtrosEmpresas.capital_max} onChange={e => setFiltrosEmpresas({ ...filtrosEmpresas, capital_max: e.target.value })} placeholder="Capital máximo" className="bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-200" />
              <fieldset className="md:col-span-4 rounded-xl border border-slate-700 bg-slate-900/60 p-3">
                <legend className="px-1 text-[11px] font-semibold text-slate-300">Situação cadastral</legend>
                <p className="mb-2 text-[10px] text-slate-400">Sem selecionar uma situação, todas são exibidas.</p>
                <div className="flex flex-wrap gap-x-4 gap-y-2">
                  <label className="flex items-center gap-2 text-xs text-slate-200">
                    <input
                      type="checkbox"
                      checked={!filtrosEmpresas.situacoes_cadastrais.length}
                      onChange={() => setFiltrosEmpresas({
                        ...filtrosEmpresas,
                        situacoes_cadastrais: [],
                      })}
                      aria-label="Todas as situações"
                    />
                    Todas
                  </label>
                  {(listaEmpresas.situacoes_cadastrais || []).map(situacao => {
                    const nomeSituacao = situacao === "__SEM_SITUACAO__"
                      ? "Não informada"
                      : situacao;
                    return (
                      <label key={situacao} className="flex items-center gap-2 text-xs text-slate-200">
                        <input
                          type="checkbox"
                          checked={filtrosEmpresas.situacoes_cadastrais.includes(situacao)}
                          onChange={event => alterarSituacaoCadastral(situacao, event.target.checked)}
                          aria-label={`Situação: ${nomeSituacao}`}
                        />
                        {nomeSituacao}
                      </label>
                    );
                  })}
                </div>
              </fieldset>
              <button type="button" onClick={() => { setPage(1); setListaPage(1); setFiltrosAplicados({ ...filtrosEmpresas }); setRefresh(v => v + 1); }} className="md:col-span-4 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl px-3 py-2 text-xs font-semibold">Aplicar filtros</button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-slate-900 border border-slate-700 rounded-2xl p-4">
                <p className="text-[10px] uppercase tracking-[0.2em] text-slate-400">Total</p>
                <p className="mt-2 text-2xl font-bold text-white">{listaEmpresas.total?.toLocaleString("pt-BR") || 0}</p>
              </div>
              <div className="bg-slate-900 border border-slate-700 rounded-2xl p-4">
                <p className="text-[10px] uppercase tracking-[0.2em] text-slate-400">Capital total</p>
                <p className="mt-2 text-2xl font-bold text-white">R$ {Number(listaEmpresas.capital_total || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
              </div>
              <div className="bg-slate-900 border border-slate-700 rounded-2xl p-4">
                <p className="text-[10px] uppercase tracking-[0.2em] text-slate-400">Páginas</p>
                <p className="mt-2 text-2xl font-bold text-white">{listaEmpresas.total_paginas || 1}</p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/70 text-slate-400">
                  <tr>
                    <th className="p-3">Empresa</th>
                    <th className="p-3">CNPJ</th>
                    <th className="p-3">Capital</th>
                    <th className="p-3">Situação</th>
                    <th className="p-3">Localização</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/70">
                  {listaEmpresas.resultados?.length ? listaEmpresas.resultados.map((empresa) => (
                    <tr key={empresa.cnpj} className="align-top text-slate-200">
                      <td className="p-3 font-medium">{empresa.razao_social || empresa.nome_fantasia || "—"}</td>
                      <td className="p-3 font-mono text-slate-400">{empresa.cnpj}</td>
                      <td className="p-3 text-emerald-300">R$ {Number(empresa.capital_social || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                      <td className="p-3">{empresa.situacao_cadastral || "—"}</td>
                      <td className="p-3 text-slate-400">{empresa.bairro || empresa.endereco || "—"}</td>
                    </tr>
                  )) : <tr><td colSpan="5" className="p-6 text-center text-slate-500">Nenhuma empresa encontrada para os filtros atuais.</td></tr>}
                </tbody>
              </table>
            </div>
            {listaEmpresas.total_paginas > 1 && (
              <div className="flex items-center justify-between border-t border-slate-700 pt-4 text-xs text-slate-400">
                <span>Página {listaPage} de {listaEmpresas.total_paginas}</span>
                <div className="flex gap-2">
                  <button type="button" disabled={listaPage <= 1} onClick={() => setListaPage((current) => current - 1)} className="rounded-lg border border-slate-600 px-3 py-1.5 disabled:opacity-40">Anterior</button>
                  <button type="button" disabled={listaPage >= listaEmpresas.total_paginas} onClick={() => setListaPage((current) => current + 1)} className="rounded-lg border border-slate-600 px-3 py-1.5 disabled:opacity-40">Próxima</button>
                </div>
              </div>
            )}
          </section>

          <section className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 text-xs text-amber-100">
            Uma correspondência é listada somente quando o nome normalizado coincide
            e os seis dígitos visíveis do CPF mascarado também coincidem. Máscara ou
            nome isolados não são suficientes. Mesmo uma correspondência forte é
            indicativa, não prova identidade nem irregularidade.
            {data?.coletado_em && (
              <span className="block mt-2 text-amber-200/80">
                Última atualização: {new Date(data.coletado_em).toLocaleString("pt-BR")}
                {data.origem ? ` · Fonte: ${data.origem}` : ""}
              </span>
            )}
          </section>

          <section className="bg-slate-800 border border-slate-700 rounded-2xl p-5">
            <h3 className="font-bold text-white">Benefícios registrados em outros municípios</h3>
            <p className="text-xs text-slate-400 mt-1">
              A correspondência local usa nome normalizado e seis dígitos visíveis do CPF; depois, o sistema procura o mesmo NIS nos demais municípios. O resultado é indicativo. Para reduzir a exposição de dados pessoais, só são exibidos grupos com pelo menos 5 beneficiários distintos por município e programa.
            </p>
            {beneficiosIntermunicipais === null ? (
              <p className="mt-4 text-xs text-slate-400">Consultando o histórico local...</p>
            ) : beneficiosIntermunicipais.length ? (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-900/70 text-slate-400">
                    <tr>
                      <th className="p-3">Município</th>
                      <th className="p-3">Programa</th>
                      <th className="p-3">Beneficiários</th>
                      <th className="p-3">Período no banco</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/70">
                    {beneficiosIntermunicipais.map((grupo, index) => (
                      <tr key={`${grupo.codigo_ibge}-${grupo.beneficio}-${index}`} className="text-slate-200">
                        <td className="p-3">{grupo.municipio}/{grupo.uf}</td>
                        <td className="p-3">{grupo.beneficio}</td>
                        <td className="p-3">{Number(grupo.beneficiarios).toLocaleString("pt-BR")}</td>
                        <td className="p-3">{grupo.periodo_inicial} - {grupo.periodo_final}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="mt-4 text-xs text-slate-400">
                Não há grupos divulgáveis no histórico local. Grupos com menos de 5 beneficiários são suprimidos.
              </p>
            )}
          </section>

          <section className="bg-slate-800 border border-slate-700 rounded-2xl overflow-hidden">
            <div className="p-5 border-b border-slate-700">
              <h3 className="font-bold text-white">Beneficiários que também constam como sócios</h3>
              <p className="text-xs text-slate-400 mt-1">
                A lista segue os filtros de empresa aplicados acima. O capital social é o valor cadastrado para a empresa, não o patrimônio pessoal do beneficiário; os dados pessoais permanecem mascarados.
              </p>
              <label className="mt-4 flex max-w-sm flex-col gap-1 text-xs text-slate-300">
                Programa do benefício
                <select
                  aria-label="Programa do benefício"
                  value={programaSocio}
                  onChange={event => {
                    setPage(1);
                    setProgramaSocio(event.target.value);
                  }}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-200"
                >
                  <option value="">Todos os programas</option>
                  {[...programasSociosDisponiveis]
                    .sort((a, b) => a.localeCompare(b, "pt-BR"))
                    .map(programa => (
                      <option key={programa} value={programa}>{programa}</option>
                    ))}
                </select>
              </label>
            </div>
            {loading ? (
              <div className="p-10 text-center text-brand-300"><Icon name="loader-2" className="w-6 h-6 animate-spin mx-auto" /></div>
            ) : data?.resultados?.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-900/70 text-slate-400">
                    <tr>
                      <th className="p-3">Beneficiário</th>
                      <th className="p-3">CPF mascarado</th>
                      <th className="p-3">Programas</th>
                      <th className="p-3">Empresa, situação e capital social</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/70">
                    {data.resultados.map((pessoa, index) => (
                      <tr key={`${pessoa.cpf_mascarado}-${index}`} className="align-top text-slate-200">
                        <td className="p-3 font-medium">{pessoa.nome}</td>
                        <td className="p-3 font-mono text-slate-400">{pessoa.cpf_mascarado}</td>
                        <td className="p-3 text-slate-300">{pessoa.programas.join(", ")}</td>
                        <td className="p-3 space-y-2">
                          {pessoa.empresas.map(empresa => (
                            <div key={empresa.cnpj}>
                              <span className="font-medium">{empresa.razao_social || empresa.nome_fantasia || "Razão social não informada"}</span>
                              <span className="block text-slate-400">
                                CNPJ {empresa.cnpj} · {empresa.situacao_cadastral || "situação não informada"}
                              </span>
                              <span className="block text-emerald-300">
                                {empresa.capital_social == null
                                  ? "Capital social não informado"
                                  : `Capital social: R$ ${Number(empresa.capital_social).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                              </span>
                            </div>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="p-8 text-center text-sm text-slate-400">
                {data?.empresas
                  ? "Nenhuma correspondência forte encontrada para este município."
                  : "Ainda não há dados de CNPJ salvos para este município."}
              </p>
            )}
            {data?.total_paginas > 1 && (
              <div className="flex items-center justify-between p-4 border-t border-slate-700 text-xs text-slate-400">
                <span>Página {page} de {data.total_paginas}</span>
                <div className="flex gap-2">
                  <button type="button" disabled={page <= 1} onClick={() => setPage((current) => current - 1)} className="rounded-lg border border-slate-600 px-3 py-1.5 disabled:opacity-40">Anterior</button>
                  <button type="button" disabled={page >= data.total_paginas} onClick={() => setPage((current) => current + 1)} className="rounded-lg border border-slate-600 px-3 py-1.5 disabled:opacity-40">Próxima</button>
                </div>
              </div>
            )}
          </section>
        </div>
      );
    }

    // --- FORMULARIO GESTÃO DE DADOS (API GOVERNO & MANUAL) ---
    function FormularioInsercaoDados({ selectedMun, apiUrl, onSucesso }) {
      // Estado para Gov API
      const [apiForm, setApiForm] = useState(() => {
        const agora = new Date();
        return {
          programa: "Novo Bolsa Familia",
          apiKey: "",
          ano: String(agora.getFullYear()),
          mes: String(agora.getMonth() + 1).padStart(2, "0"),
        };
      });
      const [apiStatusMsg, setApiStatusMsg] = useState(null);
      const [isApiSubmitting, setIsApiSubmitting] = useState(false);
      const [isSavingApiKey, setIsSavingApiKey] = useState(false);
      const [apiKeys, setApiKeys] = useState([]);
      const apiKeyStored = apiKeys.length > 0;
      const [apiKeyStoreEnabled, setApiKeyStoreEnabled] = useState(false);
      const [apiKeyConfigError, setApiKeyConfigError] = useState(null);
      const [monitorStatus, setMonitorStatus] = useState(null);
      const [monitorError, setMonitorError] = useState(null);
      const apiRequestController = useRef(null);

      const listaProgramasGoverno = [
        "Novo Bolsa Familia", "Auxilio Brasil", "Bolsa Familia", 
        "BPC", "Garantia Safra", "Seguro Defeso", "Auxilio Emergencial", "PETI"
      ];

      useEffect(() => {
        return () => {
          apiRequestController.current?.abort();
        };
      }, []);

      useEffect(() => {
        const controller = new AbortController();
        fetchJson(`${apiUrl}/config/api-key`, { signal: controller.signal })
          .then(data => {
            setApiKeyStoreEnabled(Boolean(data.enabled));
            setApiKeys(Array.isArray(data.keys) ? data.keys : []);
          })
          .catch(error => {
            if (!isAbortError(error)) {
              setApiKeyConfigError(`Não foi possível verificar a chave salva: ${error.message}`);
            }
          });
        return () => controller.abort();
      }, [apiUrl]);

      useEffect(() => {
        if (!isApiSubmitting) {
          setMonitorStatus(null);
          setMonitorError(null);
          return undefined;
        }

        let active = true;
        let timeout;
        let controller;
        const pollStatus = async () => {
          controller = new AbortController();
          try {
            const data = await fetchJson(`${apiUrl}/status`, {
              signal: controller.signal,
            }, 5_000);
            setMonitorStatus(data.status || null);
            setMonitorError(null);
          } catch (error) {
            if (!isAbortError(error)) {
              setMonitorError(`Não foi possível consultar o andamento da coleta: ${error.message}`);
            }
          } finally {
            if (active) timeout = window.setTimeout(pollStatus, 1500);
          }
        };
        pollStatus();

        return () => {
          active = false;
          window.clearTimeout(timeout);
          controller?.abort();
        };
      }, [isApiSubmitting, apiUrl]);

      const handleApiChange = (e) => {
        const { name, value } = e.target;
        setApiForm(current => {
          const next = { ...current, [name]: value };
          if (name === "programa" || name === "ano") {
            const periodo = ajustarPeriodoVigente(
              next.programa, next.ano, next.mes,
            );
            next.ano = periodo.ano;
            next.mes = periodo.mes;
          }
          return next;
        });
      };

      const handleSaveApiKey = async () => {
        if (!apiForm.apiKey) {
          setApiStatusMsg({ tipo: "erro", texto: "Informe a chave da API do Portal da Transparência." });
          return;
        }
        setIsSavingApiKey(true);
        setApiStatusMsg(null);
        try {
          const result = await fetchJson(`${apiUrl}/config/api-key`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: apiForm.apiKey }),
          });
          setApiKeys(Array.isArray(result.keys) ? result.keys : []);
          setApiKeyStoreEnabled(true);
          setApiForm(previous => ({ ...previous, apiKey: "" }));
          setApiStatusMsg({ tipo: "sucesso", texto: "Chave criptografada salva neste servidor." });
        } catch (error) {
          setApiStatusMsg({ tipo: "erro", texto: `Não foi possível salvar a chave: ${error.message}` });
        } finally {
          setIsSavingApiKey(false);
        }
      };

      const handleDeleteApiKey = async (key) => {
        if (!window.confirm(`Remover a chave ${key.label} salva neste servidor?`)) return;
        setApiStatusMsg(null);
        try {
          const data = await fetchJson(`${apiUrl}/config/api-key/${encodeURIComponent(key.id)}`, {
            method: "DELETE",
          });
          setApiKeys(Array.isArray(data.keys) ? data.keys : []);
          setApiStatusMsg({ tipo: "sucesso", texto: "Chave removida do servidor." });
        } catch (error) {
          setApiStatusMsg({ tipo: "erro", texto: `Não foi possível remover a chave: ${error.message}` });
        }
      };

      const handleApiSubmit = async (e) => {
        e.preventDefault();
        if (!selectedMun) return;
        if (!apiKeyStored && !apiForm.apiKey) {
          setApiStatusMsg({ tipo: "erro", texto: "Informe a chave da API do Portal da Transparência antes de iniciar a coleta." });
          return;
        }
        apiRequestController.current?.abort();
        const controller = new AbortController();
        apiRequestController.current = controller;
        setIsApiSubmitting(true); setApiStatusMsg(null); setMonitorStatus(null);
        setMonitorError(null);
        try {
          const data = await fetchJson(`${apiUrl}/consultar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              tipo: "Adicionar beneficiários", // Sempre detalhado para o banco enriquecer
              programa: apiForm.programa, uf: selectedMun.uf,
              codigo_ibge: selectedMun.codigo_ibge, nome_mun: selectedMun.nome,
              ano: apiForm.ano, mes: apiForm.mes, permitir_novos: true,
              ...(apiForm.apiKey ? { api_key: apiForm.apiKey } : {}),
            }),
            signal: controller.signal,
          }, COLLECTION_TIMEOUT_MS);
          if (data.erro) throw new Error(data.erro);
          setApiStatusMsg({ tipo: 'sucesso', texto: `Coleta concluída! ${data.registros} beneficiários foram puxados do Gov.br para ${apiForm.mes}/${apiForm.ano} e armazenados de forma permanente.` });
          if (onSucesso) {
            onSucesso({
              programa: apiForm.programa,
              ano: apiForm.ano,
              mes: apiForm.mes,
            });
          }
        } catch (error) {
          if (!isAbortError(error)) {
            setApiStatusMsg({ tipo: 'erro', texto: `Falha na coleta: ${error.message}` });
          }
        } finally {
          if (!controller.signal.aborted) setIsApiSubmitting(false);
        }
      };

      const renderAnoOptions = () => obterAnosVigentes(apiForm.programa)
        .map(ano => <option key={ano} value={ano}>{ano}</option>);
      const renderMesOptions = () => obterMesesVigentes(
        apiForm.programa, apiForm.ano,
      ).map(mes => <option key={mes} value={mes}>{mes}</option>);

      if (!selectedMun) return <div className="text-center p-12 text-slate-400">Selecione um município na barra lateral primeiro.</div>;

      return (
        <div className="max-w-6xl mx-auto grid grid-cols-1 xl:grid-cols-2 gap-8 pb-20">
          
          {/* PAINEL DE COLETA AUTOMATIZADA (API) */}
          <div className="bg-slate-800 border border-brand-500/40 rounded-3xl p-7 relative overflow-hidden shadow-2xl shadow-brand-900/10">
            <div className="absolute -top-10 -right-10 opacity-5 pointer-events-none transform rotate-12"><Icon name="cloud-download" className="w-56 h-56 text-brand-500" /></div>
            <div className="border-b border-slate-700/60 pb-5 mb-6 relative z-10">
              <h3 className="text-lg font-bold text-white flex items-center space-x-2"><Icon name="server" className="w-6 h-6 text-brand-400" /><span>Coleta Automática Gov.br</span></h3>
              <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">Conecta aos servidores federais e baixa integralmente as listas de beneficiários de <b className="text-brand-300">{selectedMun.nome} - {selectedMun.uf}</b> para o seu banco de dados local SQLite.</p>
            </div>
            
            {apiStatusMsg && <div className={`p-4 rounded-xl text-xs font-semibold mb-6 border relative z-10 flex items-start gap-3 shadow-lg ${apiStatusMsg.tipo === 'sucesso' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-rose-500/10 text-rose-400 border-rose-500/30'}`}><Icon name={apiStatusMsg.tipo === 'sucesso' ? 'check-circle' : 'alert-octagon'} className="w-5 h-5 flex-shrink-0" /><span className="mt-0.5">{apiStatusMsg.texto}</span></div>}
            
            {/* Monitor de Progresso em Tempo Real */}
            {isApiSubmitting && (
              <div className="mb-6 bg-brand-900/30 border border-brand-500/40 p-5 rounded-2xl relative z-10 shadow-inner overflow-hidden">
                <div className="absolute top-0 left-0 w-full h-1 bg-brand-900 overflow-hidden"><div className="h-full bg-brand-500 w-1/2 rounded animate-[ping_1.5s_cubic-bezier(0,0,0.2,1)_infinite]"></div></div>
                <h4 className="text-xs font-bold text-brand-300 mb-3 flex items-center gap-2 uppercase tracking-wide"><Icon name="activity" className="w-4 h-4 animate-pulse" /> Monitor de Coleta</h4>
                {monitorStatus ? (
                   <div className="grid grid-cols-2 gap-3 text-xs">
                     <div className="bg-slate-900/50 p-3 rounded-xl border border-brand-500/20"><span className="text-slate-400 block mb-1">Status Atual</span><span className="font-semibold text-brand-100">{monitorStatus.mensagem}</span></div>
                     <div className="bg-slate-900/50 p-3 rounded-xl border border-brand-500/20"><span className="text-slate-400 block mb-1">Registros Baixados</span><span className="font-bold text-emerald-400 text-base">{monitorStatus.registros_lidos.toLocaleString('pt-BR')} pessoas</span></div>
                     <div className="bg-slate-900/50 p-3 rounded-xl border border-brand-500/20"><span className="text-slate-400 block mb-1">Páginas Lidas (Gov API)</span><span className="font-semibold text-amber-300">{monitorStatus.paginas_lidas} páginas</span></div>
                     <div className="bg-slate-900/50 p-3 rounded-xl border border-brand-500/20"><span className="text-slate-400 block mb-1">Tempo Gasto</span><span className="font-mono text-brand-200">{monitorStatus.tempo_decorrido}s</span></div>
                   </div>
                ) : (
                   <div className="text-xs text-brand-400 font-medium flex items-center justify-center py-4"><Icon name="clock" className="w-4 h-4 mr-2 animate-spin" /> Inicializando comunicação segura com Portal da Transparência...</div>
                )}
                {monitorError && <p role="alert" className="mt-3 text-xs text-rose-400">{monitorError}</p>}
              </div>
            )}

            <form onSubmit={handleApiSubmit} className="space-y-5 relative z-10">
              <div className="grid grid-cols-2 gap-4">
                 <div>
                   <label className="block text-[11px] text-slate-400 mb-1.5 uppercase font-bold tracking-wider">Ano Específico</label>
                   <select aria-label="Ano do benefício" name="ano" value={apiForm.ano} onChange={handleApiChange} className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-semibold text-brand-300 outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-all">{renderAnoOptions()}</select>
                 </div>
                 <div>
                   <label className="block text-[11px] text-slate-400 mb-1.5 uppercase font-bold tracking-wider">Mês de Referência</label>
                   <select aria-label="Mês do benefício" name="mes" value={apiForm.mes} onChange={handleApiChange} className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-semibold text-brand-300 outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-all">{renderMesOptions()}</select>
                 </div>
              </div>
              <div>
                <label className="block text-[11px] text-slate-400 mb-1.5 uppercase font-bold tracking-wider">Programa para Download</label>
                <select aria-label="Programa para Download" name="programa" value={apiForm.programa} onChange={handleApiChange} className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-100 font-medium outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-all">
                    {listaProgramasGoverno.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
                <p className="mt-2 text-[11px] text-slate-400">
                  Vigência: {rotuloVigencia(apiForm.programa)}
                </p>
              </div>
              <div className="bg-slate-900/60 p-4 rounded-xl border border-slate-700/50">
                  <label className="block text-[11px] text-slate-400 mb-2 uppercase font-bold tracking-wider flex items-center justify-between">
                    <span>Token de Acesso (API Key Gov)</span>
                    <a href="https://portaldatransparencia.gov.br/api-de-dados" target="_blank" className="text-brand-400 hover:text-brand-300 lowercase text-[10px] font-medium flex items-center gap-1"><Icon name="external-link" className="w-3 h-3" /> Obter token</a>
                  </label>
                  <input type="password" name="apiKey" aria-label="Chave da API do Portal da Transparência" required={!apiKeyStored} placeholder={apiKeyStored ? "Chave salva; deixe vazio para manter" : "Insira seu código..."} value={apiForm.apiKey} onChange={handleApiChange} className="w-full bg-slate-800 border border-brand-500/40 rounded-xl px-4 py-3 text-sm text-brand-200 outline-none focus:ring-2 focus:ring-brand-500 font-mono tracking-widest shadow-inner placeholder:text-slate-600" />
                  <p className="mt-2 text-[11px] text-slate-400" role="status">
                    {apiKeyStored
                      ? `${apiKeys.length} chave(s) salva(s) com criptografia neste servidor.`
                      : apiKeyStoreEnabled
                        ? "Nenhuma chave salva. Insira uma chave para usar na coleta ou salve-a."
                        : "Cofre indisponível: configure a chave de criptografia no servidor para salvar."}
                  </p>
                  {apiKeyConfigError && <p role="alert" className="mt-2 text-[11px] text-rose-400">{apiKeyConfigError}</p>}
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button type="button" onClick={handleSaveApiKey} disabled={isSavingApiKey || !apiForm.apiKey || !apiKeyStoreEnabled} className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-100 px-3 py-2 rounded-lg text-xs font-semibold">
                      {isSavingApiKey ? "Salvando..." : "Salvar chave criptografada"}
                    </button>
                  </div>
                  {apiKeys.length > 0 && (
                    <div className="mt-4 border-t border-slate-700 pt-4">
                      <h4 className="text-[11px] text-slate-400 mb-2 uppercase font-bold tracking-wider">Chaves salvas</h4>
                      <ul className="space-y-2">
                        {apiKeys.map(key => (
                          <li key={key.id} className="flex items-center justify-between gap-3 text-xs">
                            <span className="font-mono text-slate-300">{key.label}</span>
                            <button type="button" onClick={() => handleDeleteApiKey(key)} className="bg-rose-900/60 hover:bg-rose-800 text-rose-200 px-3 py-1.5 rounded-lg font-semibold">Remover</button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
              </div>
              <div className="pt-2">
                  <button type="submit" disabled={isApiSubmitting} className="w-full bg-brand-600 hover:bg-brand-500 text-white font-bold py-3.5 rounded-xl text-sm transition-all shadow-xl shadow-brand-900/50 flex items-center justify-center space-x-2 disabled:bg-slate-700 disabled:shadow-none hover:-translate-y-0.5 active:translate-y-0">
                      {isApiSubmitting ? <Icon name="loader-2" className="w-5 h-5 animate-spin" /> : <Icon name="download-cloud" className="w-5 h-5" />}
                      <span>{isApiSubmitting ? "Coleta em andamento (Aguarde)..." : "Iniciar Download Integral"}</span>
                  </button>
              </div>
            </form>
          </div>

        </div>
      );
    }

const root = createRoot(document.getElementById("root"));
root.render(<App />);
