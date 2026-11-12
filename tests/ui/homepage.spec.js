import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route(
    "https://api.portaldatransparencia.gov.br/**",
    route => route.abort(),
  );
});

async function mockSuccessfulApi(page) {
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/municipios") {
      await route.fulfill({
        json: {
          municipios: [{ codigo_ibge: "2910750", nome: "Fátima", uf: "BA" }],
          ufs: ["BA"],
        },
      });
    } else if (url.pathname === "/api/filtros") {
      await route.fulfill({ json: { programas: ["Novo Bolsa Familia (sacado)"] } });
    } else if (url.pathname === "/api/consultar") {
      await route.fulfill({ json: { dados: [], registros: 0, total_paginas: 1 } });
    } else if (url.pathname === "/api/status") {
      await route.fulfill({ json: { status: null } });
    } else if (url.pathname === "/api/config/api-key") {
      await route.fulfill({ json: { enabled: true, configured: false } });
    } else {
      await route.fulfill({ json: { nodes: [], edges: [], resultados: [] } });
    }
  });
}

test("recarrega a tela inicial sem erros de renderização", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  await mockSuccessfulApi(page);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Portal Transparência" })).toBeVisible();
  await expect(page.getByText("Fátima - BA")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Portal Transparência" })).toBeVisible();
  await expect(page.locator("#root svg").first()).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test("apresenta a página About, fontes e informações LGPD", async ({ page }) => {
  await mockSuccessfulApi(page);

  await page.goto("/");
  await page.getByRole("button", { name: "About" }).click();
  await expect(page.getByRole("heading", { name: "Sobre o painel e seus dados" })).toBeVisible();
  await page.getByRole("button", { name: "LGPD e privacidade" }).click();
  await expect(page.getByText("Controlador e contato:", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Fontes de dados" }).click();
  await expect(page.locator('a[href="https://portaldatransparencia.gov.br/"]')).toHaveAttribute(
    "href",
    "https://portaldatransparencia.gov.br/",
  );
  await expect(page.getByRole("link", { name: "Casa dos Dados — pesquisa de CNPJ" })).toBeVisible();
});

test("limita anos e meses de download à vigência do programa", async ({ page }) => {
  await mockSuccessfulApi(page);

  await page.goto("/");
  await page.getByRole("button", { name: "Gestão & API Gov.br" }).click();
  const programa = page.getByLabel("Programa para Download");
  const ano = page.getByLabel("Ano do benefício");
  const mes = page.getByLabel("Mês do benefício");

  await programa.selectOption("Auxilio Brasil");
  await expect(ano).toHaveValue("2023");
  await expect(mes.locator("option")).toHaveCount(2);
  await expect(mes.locator('option[value="03"]')).toHaveCount(0);
  await expect(ano.locator('option[value="2024"]')).toHaveCount(0);

  await programa.selectOption("Novo Bolsa Familia");
  await expect(ano).toHaveValue("2023");
  await expect(mes).toHaveValue("03");
  await expect(mes.locator('option[value="02"]')).toHaveCount(0);

  await programa.selectOption("Auxilio Emergencial");
  await expect(ano).toHaveValue("2021");
  await expect(mes.locator('option[value="11"]')).toHaveCount(0);
});

test("explica e permite repetir a conexão quando o backend não responde", async ({ page }) => {
  let requests = 0;
  await page.route("**/api/municipios", async route => {
    requests += 1;
    await route.fulfill({ status: 500, contentType: "text/plain", body: "" });
  });

  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("servidor FastAPI está ativo");
  await expect(page.getByRole("alert")).toContainText("uvicorn api:app --reload");
  await page.getByRole("button", { name: "Tentar novamente" }).click();
  await expect.poll(() => requests).toBe(2);
});

test("filtra municípios com dados e permite escolher outro estado para coleta", async ({ page }) => {
  const consultas = [];
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/municipios") {
      await route.fulfill({
        json: {
          municipios: [
            { codigo_ibge: "2910750", nome: "Fátima", uf: "BA" },
            { codigo_ibge: "2805505", nome: "Poço Verde", uf: "SE" },
          ],
          codigos_municipios_com_dados: ["2910750"],
          codigos_municipios_com_agregados: ["2910750", "2805505"],
          codigos_municipios_com_beneficiarios: ["2805505"],
          ufs: ["BA", "SE"],
        },
      });
    } else if (url.pathname === "/api/filtros") {
      await route.fulfill({ json: { programas: [] } });
    } else if (url.pathname === "/api/consultar") {
      consultas.push(route.request().postDataJSON());
      await route.fulfill({
        json: {
          dados: [],
          registros: 0,
          resumo: {
            registros: 0,
            total_valor: 0,
            total_beneficiados: 0,
            meses: 0,
          },
        },
      });
    } else {
      await route.fulfill({ json: { dados: [], resultados: [], nodes: [], edges: [] } });
    }
  });

  await page.goto("/");
  await page.getByLabel("Lista de municípios").selectOption("com_dados");
  await expect(page.getByLabel("UF", { exact: true }).locator("option")).toHaveText(["BA (1 com dados)"]);
  await expect(page.getByLabel("Município", { exact: true }).locator("option")).toHaveText(["Fátima — BA"]);

  await page.getByLabel("Lista de municípios").selectOption("todos");
  await page.getByLabel("UF", { exact: true }).selectOption("SE");
  await page.getByLabel("Município", { exact: true }).selectOption("2805505");
  await page.getByRole("button", { name: "Gestão & API Gov.br" }).click();
  await expect(page.getByText("Poço Verde - SE")).toBeVisible();
  await expect.poll(
    () => page.evaluate(() => localStorage.getItem(
      "painel-beneficios.municipio-codigo-ibge",
    )),
  ).toBe("2805505");
  await page.reload();
  await expect(page.getByLabel("Município", { exact: true })).toHaveValue("2805505");
  await page.getByRole("button", { name: "Visão Geral" }).click();
  await expect(page.getByText("Pessoas Únicas")).toBeVisible();
  await expect.poll(() => consultas.at(-1)?.codigo_ibge).toBe("2805505");
  expect(consultas.at(-1)).toMatchObject({
    tipo: "Adicionar beneficiários",
    resumo: true,
    permitir_novos: false,
  });
});

test("navega entre abas da tabela, busca e gestão", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  await mockSuccessfulApi(page);

  await page.goto("/");
  await page.getByRole("button", { name: "Tabela" }).click();
  await expect(page.getByRole("table")).toBeVisible();
  await page.getByRole("button", { name: "Rede Programas" }).click();
  await expect(page.locator(".vis-network canvas")).toBeVisible();
  await page.getByRole("button", { name: "Busca Global" }).click();
  await expect(page.getByText("Busca Global Indexada (Todos os Anos)")).toBeVisible();
  await page.getByRole("button", { name: "Gestão & API Gov.br" }).click();
  await expect(page.getByText("Coleta Automática Gov.br")).toBeVisible();
  await page.getByRole("button", { name: "Consultar Banco de Dados" }).click();
  await expect(page.getByText(/Consulta realizada\./)).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(pageErrors).toEqual([]);
});

test("solicita páginas de beneficiários ao backend", async ({ page }) => {
  const requestedPages = [];
  const pageErrors = [];
  let resumoCarregado = false;
  page.on("pageerror", error => pageErrors.push(error.message));
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/municipios") {
      await route.fulfill({
        json: {
          municipios: [{ codigo_ibge: "2910750", nome: "Fátima", uf: "BA" }],
          ufs: ["BA"],
        },
      });
    } else if (url.pathname === "/api/filtros") {
      await route.fulfill({ json: { programas: ["Novo Bolsa Familia (sacado)"] } });
    } else if (url.pathname === "/api/consultar") {
      const request = route.request().postDataJSON();
      if (request.pagina) requestedPages.push(request.pagina);
      if (request.resumo) {
        await route.fulfill({
          json: {
            dados: [{
              mes: 1,
              mes_num: 1,
              ano: 2025,
              valor: 600,
              beneficiados: 1,
            }],
            registros: 250,
            resumo: {
              registros: 250,
              total_valor: 600,
              total_beneficiados: 1,
              meses: 1,
            },
          },
        });
        resumoCarregado = true;
        return;
      }
      await route.fulfill({
        json: {
          dados: request.pagina ? Array.from({ length: 100 }, (_, index) => ({
            programa: "Novo Bolsa Familia (sacado)",
            nis: `1234567890${request.pagina}${String(index).padStart(2, "0")}`,
            nome: index === 0
              ? `BENEFICIARIO PAGINA ${request.pagina}`
              : `BENEFICIARIO PAGINA ${request.pagina} LINHA ${index}`,
            mes: 1,
            ano: 2025,
            valor_saque: 600,
          })) : [],
          registros: request.pagina ? 250 : 0,
          pagina: request.pagina || null,
          por_pagina: 100,
          total_paginas: request.pagina ? 3 : 1,
        },
      });
    } else {
      await route.fulfill({ json: { status: null, nodes: [], edges: [] } });
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Beneficiários (Listagem Pessoal)" }).click();
  await expect.poll(() => resumoCarregado).toBe(true);
  await expect(page.getByText("R$ 600,00").first()).toBeVisible();
  await page.getByRole("button", { name: "Tabela" }).click();
  await expect(page.getByRole("cell", { name: "BENEFICIARIO PAGINA 1", exact: true })).toBeVisible();
  await expect(page.getByRole("table").locator("tbody tr")).toHaveCount(100);
  await expect(page.getByText("Exibindo 250 registros no banco")).toBeVisible();
  await page.getByRole("button", { name: "Próximo" }).click();
  await expect(page.getByRole("cell", { name: "BENEFICIARIO PAGINA 2", exact: true })).toBeVisible();
  await expect(page.getByText("Página 2 de 3")).toBeVisible();
  expect(requestedPages).toContain(2);
  expect(pageErrors).toEqual([]);
});

test("importa CSV local de CNPJ e mostra correspondências no município", async ({ page }) => {
  let importRequest;
  let pdfReportRequest;
  const cnpjRequests = [];
  const pageErrors = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/api/cnpj/")) cnpjRequests.push(url.pathname);
    if (url.pathname === "/api/municipios") {
      await route.fulfill({
        json: {
          municipios: [{ codigo_ibge: "2910750", nome: "Fátima", uf: "BA" }],
          ufs: ["BA"],
        },
      });
    } else if (url.pathname === "/api/filtros") {
      await route.fulfill({ json: { programas: [] } });
    } else if (url.pathname === "/api/cnpj/cruzamento") {
      await route.fulfill({
        json: {
          empresas: 1872,
          socios: 598,
          beneficiarios_com_cnpj: 1,
          pagina: 1,
          por_pagina: 50,
          total_paginas: 1,
          origem: "csv",
          resultados: [{
            nome: "JOAO DA SILVA",
            cpf_mascarado: "***.123.456-**",
            programas: ["Novo Bolsa Familia"],
            empresas: [{
              cnpj: "12345678000199",
              razao_social: "EMPRESA TESTE",
              situacao_cadastral: "ATIVA",
              capital_social: 123456.78,
            }],
          }],
        },
      });
    } else if (url.pathname === "/api/cnpj/beneficios") {
      await route.fulfill({
        json: [{
          codigo_ibge: "2805505",
          municipio: "Poço Verde",
          uf: "SE",
          beneficio: "Novo Bolsa Familia",
          beneficiarios: 5,
          periodo_inicial: "202501",
          periodo_final: "202505",
        }],
      });
    } else if (url.pathname === "/api/cnpj/relatorio") {
      await route.fulfill({
        contentType: "text/csv; charset=utf-8",
        body: "municipio;programa;beneficiarios\n",
      });
    } else if (url.pathname === "/api/cnpj/cruzamento/relatorio.pdf") {
      pdfReportRequest = url;
      await route.fulfill({
        contentType: "application/pdf",
        body: "%PDF-1.4\n%%EOF",
      });
    } else if (url.pathname === "/api/cnpj/status") {
      await route.fulfill({ json: { status: null } });
    } else if (url.pathname === "/api/cnpj/importar-csv") {
      importRequest = {
        headers: route.request().headers(),
        body: route.request().postDataJSON(),
      };
      await route.fulfill({
        json: {
          empresas: 1872,
          socios: 598,
          origem: "cnpj_FATIMA_BA.csv",
        },
      });
    } else if (url.pathname === "/api/cnpj/grafo") {
      await route.fulfill({ json: { nodes: [], edges: [] } });
    } else {
      await route.fulfill({ json: { status: null, dados: [], registros: 0 } });
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "CNPJs" }).click();
  await expect(page.getByText("Beneficiários que também constam como sócios")).toBeVisible();
  await expect(page.getByText("Poço Verde/SE")).toBeVisible();
  await expect(page.getByText("EMPRESA TESTE")).toBeVisible();
  await expect(page.getByText("Capital social: R$ 123.456,78")).toBeVisible();
  await expect(page.getByText("Preparando o grafo em segundo plano...")).toBeHidden();
  expect(pageErrors).toEqual([]);
  await expect.poll(() => cnpjRequests.length).toBe(5);
  const consultasPesadasAntesDeSair = cnpjRequests.filter(
    path => path !== "/api/cnpj/status",
  ).length;
  await page.getByRole("button", { name: "About" }).click();
  await page.getByRole("button", { name: "CNPJs" }).click();
  await expect.poll(
    () => cnpjRequests.filter(path => path !== "/api/cnpj/status").length,
  ).toBe(consultasPesadasAntesDeSair);
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Baixar benefícios intermunicipais (CSV)" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("relatorio_cnpj_F_tima.csv");
  const pdfDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Baixar relatório detalhado (PDF)" }).click();
  const pdfDownload = await pdfDownloadPromise;
  expect(pdfDownload.suggestedFilename()).toBe(
    "relatorio_beneficiarios_socios_F_tima.pdf",
  );
  expect(pdfReportRequest.searchParams.get("codigo_ibge")).toBe("2910750");
  await page.getByRole("button", { name: "Importar CSV local" }).click();
  await expect(page.getByRole("status")).toContainText(/1\.872 empresas e 598 sócios/);
  expect(importRequest.body).toEqual({ codigo_ibge: "2910750" });
  expect(importRequest.headers["x-admin-token"]).toBeUndefined();
  expect(pageErrors).toEqual([]);
});

test("filtra a listagem de CNPJs e o PDF pelas situações escolhidas", async ({ page }) => {
  const situacoesConsultadas = [];
  const cruzamentoConsultado = [];
  let pdfReportRequest;
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/municipios") {
      await route.fulfill({
        json: {
          municipios: [{ codigo_ibge: "2910750", nome: "Fátima", uf: "BA" }],
          ufs: ["BA"],
        },
      });
    } else if (url.pathname === "/api/filtros") {
      await route.fulfill({ json: { programas: [] } });
    } else if (url.pathname === "/api/cnpj/empresas") {
      const situacao = url.searchParams.get("situacoes_cadastrais");
      situacoesConsultadas.push(situacao);
      const empresa = situacao === "BAIXADA"
        ? {
          cnpj: "22222222000122",
          razao_social: "EMPRESA BAIXADA",
          situacao_cadastral: "BAIXADA",
          capital_social: 200,
        }
        : {
          cnpj: "11111111000111",
          razao_social: "EMPRESA ATIVA",
          situacao_cadastral: "ATIVA",
          capital_social: 100,
        };
      await route.fulfill({
        json: {
          total: 1,
          total_paginas: 1,
          capital_total: empresa.capital_social,
          resultados: [empresa],
          situacoes_cadastrais: ["ATIVA", "BAIXADA"],
        },
      });
    } else if (url.pathname === "/api/cnpj/cruzamento") {
      cruzamentoConsultado.push(new URLSearchParams(url.search));
      const programa = url.searchParams.get("programa");
      await route.fulfill({
        json: {
          empresas: 1,
          socios: 1,
          beneficiarios_com_cnpj: 1,
          pagina: 1,
          por_pagina: 50,
          total_paginas: 1,
          programas_disponiveis: ["BPC", "Auxilio Emergencial"],
          resultados: [{
            nome: "JOAO DA SILVA",
            cpf_mascarado: "***.123.456-**",
            programas: programa ? [programa] : ["BPC", "Auxilio Emergencial"],
            empresas: [{
              cnpj: "22222222000122",
              razao_social: "EMPRESA BAIXADA",
              situacao_cadastral: "BAIXADA",
              capital_social: 200,
            }],
          }],
        },
      });
    } else if (url.pathname === "/api/cnpj/cruzamento/relatorio.pdf") {
      pdfReportRequest = url;
      await route.fulfill({
        contentType: "application/pdf",
        body: "%PDF-1.4\n%%EOF",
      });
    } else if (url.pathname === "/api/cnpj/status") {
      await route.fulfill({ json: { status: null } });
    } else {
      await route.fulfill({
        json: { status: null, resultados: [], nodes: [], edges: [] },
      });
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "CNPJs" }).click();
  await page.getByPlaceholder("Buscar por nome ou CNPJ").fill("22222222000122");
  await page.getByPlaceholder("Capital mínimo").fill("100");
  await page.getByPlaceholder("Capital máximo").fill("300");
  await page.getByLabel("Situação: BAIXADA").check();
  await page.getByRole("button", { name: "Aplicar filtros" }).click();

  await expect.poll(() => situacoesConsultadas.at(-1)).toBe("BAIXADA");
  await expect.poll(
    () => cruzamentoConsultado.at(-1)?.get("situacoes_cadastrais"),
  ).toBe("BAIXADA");
  await expect(cruzamentoConsultado.at(-1).get("busca")).toBe("22222222000122");
  await expect(cruzamentoConsultado.at(-1).get("capital_min")).toBe("100");
  await expect(cruzamentoConsultado.at(-1).get("capital_max")).toBe("300");
  await expect(page.getByText("EMPRESA BAIXADA")).toHaveCount(2);
  await expect(page.getByText("EMPRESA ATIVA")).toHaveCount(0);

  await page.getByLabel("Programa do benefício").selectOption("BPC");
  await expect.poll(() => cruzamentoConsultado.at(-1)?.get("programa")).toBe("BPC");
  await expect(page.getByRole("cell", { name: "BPC", exact: true })).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Auxilio Emergencial", exact: true }),
  ).toHaveCount(0);
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Baixar relatório detalhado (PDF)" }).click();
  await downloadPromise;
  expect(pdfReportRequest.searchParams.get("situacoes_cadastrais")).toBe("BAIXADA");
  expect(pdfReportRequest.searchParams.get("busca")).toBe("22222222000122");
  expect(pdfReportRequest.searchParams.get("capital_min")).toBe("100");
  expect(pdfReportRequest.searchParams.get("capital_max")).toBe("300");
  expect(pdfReportRequest.searchParams.get("programa")).toBe("BPC");
});

test("monitora listagem e enriquecimento e confirma a conclusão da coleta de CNPJs", async ({ page }) => {
  let coletaIniciada = false;
  let consultasStatus = 0;
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/municipios") {
      await route.fulfill({
        json: {
          municipios: [{ codigo_ibge: "2910750", nome: "Fátima", uf: "BA" }],
          ufs: ["BA"],
        },
      });
    } else if (url.pathname === "/api/filtros") {
      await route.fulfill({ json: { programas: [] } });
    } else if (url.pathname === "/api/cnpj/status") {
      if (!coletaIniciada) {
        await route.fulfill({ json: { status: null } });
      } else {
        const etapa = consultasStatus++;
        const status = etapa === 0
          ? {
            etapa: "listando",
            mensagem: "Lista municipal: 40 empresas encontradas",
            empresas: 40,
            total: 2843,
            tempo_decorrido: 5,
            concluido: false,
          }
          : etapa === 1
            ? {
              etapa: "enriquecendo",
              mensagem: "Enriquecendo 2843 empresas",
              empresas: 2843,
              processadas: 12,
              pendentes: 2843,
              tempo_decorrido: 12,
              tempo_etapa: 12,
              concluido: false,
            }
            : {
              etapa: "concluida",
              mensagem: "Coleta de CNPJs concluída",
              empresas: 2843,
              socios: 510,
              tempo_decorrido: 30,
              concluido: true,
              erro: null,
            };
        await route.fulfill({ json: { status } });
      }
    } else if (url.pathname === "/api/cnpj/coletar") {
      coletaIniciada = true;
      await route.fulfill({ status: 202, json: { iniciada: true } });
    } else {
      await route.fulfill({ json: { resultados: [], nodes: [], edges: [] } });
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "CNPJs" }).click();
  await expect(page.getByRole("button", { name: "Baixar CNPJs" })).toBeVisible();
  await expect.poll(() => consultasStatus).toBe(0);
  await page.getByRole("button", { name: "Baixar CNPJs" }).click();

  await expect(page.getByText("Monitor de coleta de CNPJs")).toBeVisible();
  const monitor = page.locator('div[role="status"]');
  await expect(page.getByRole("progressbar", { name: "Progresso da lista de CNPJs" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("40 empresas encontradas de aproximadamente 2.843");
  await expect(page.getByRole("progressbar", { name: "Progresso do enriquecimento dos CNPJs" })).toBeVisible();
  await expect(monitor).toContainText("12/2843 enriquecidas");
  await expect(monitor).toContainText("Ritmo médio: 1 CNPJs por segundo · estimativa restante: ~47 min 11 s");
  await expect(page.getByRole("status")).toContainText("Coleta concluída: 2.843 empresas e 510 sócios salvos.");
});

test("exibe erro da coleta de CNPJs e libera nova tentativa", async ({ page }) => {
  let coletaIniciada = false;
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/municipios") {
      await route.fulfill({
        json: {
          municipios: [{ codigo_ibge: "2910750", nome: "Fátima", uf: "BA" }],
          ufs: ["BA"],
        },
      });
    } else if (url.pathname === "/api/filtros") {
      await route.fulfill({ json: { programas: [] } });
    } else if (url.pathname === "/api/cnpj/status") {
      await route.fulfill({
        json: {
          status: coletaIniciada ? {
            etapa: "erro",
            mensagem: "Falha ao coletar CNPJs",
            empresas: 40,
            concluido: true,
            erro: "Fonte indisponível",
          } : null,
        },
      });
    } else if (url.pathname === "/api/cnpj/coletar") {
      coletaIniciada = true;
      await route.fulfill({ status: 202, json: { iniciada: true } });
    } else {
      await route.fulfill({ json: { resultados: [], nodes: [], edges: [] } });
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "CNPJs" }).click();
  await page.getByRole("button", { name: "Baixar CNPJs" }).click();

  await expect(page.getByRole("alert")).toContainText("Falha na coleta de CNPJs: Fonte indisponível");
  await expect(page.getByRole("button", { name: "Baixar CNPJs" })).toBeEnabled();
});

test("mostra na Visão Geral os dados recém-baixados do Portal da Transparência", async ({ page }) => {
  let dashboardQuery;
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/municipios") {
      await route.fulfill({
        json: {
          municipios: [{ codigo_ibge: "2910750", nome: "Fátima", uf: "BA" }],
          codigos_municipios_com_dados: ["2910750"],
          ufs: ["BA"],
        },
      });
    } else if (url.pathname === "/api/filtros") {
      await route.fulfill({ json: { programas: ["Novo Bolsa Familia (sacado)"] } });
    } else if (url.pathname === "/api/config/api-key") {
      await route.fulfill({ json: { enabled: false, configured: false } });
    } else if (url.pathname === "/api/consultar") {
      const request = route.request().postDataJSON();
      if (request.permitir_novos) {
        await route.fulfill({ json: { dados: [], registros: 5 } });
      } else if (request.tipo === "Adicionar beneficiários") {
        dashboardQuery = request;
        await route.fulfill({
          json: {
            dados: [{
              ano: 2026,
              mes_num: 1,
              mes: "01",
              valor_saque: 600,
              nis: "12345678901",
            }],
            registros: 1,
            resumo: {
              registros: 1,
              total_valor: 600,
              total_beneficiados: 1,
              meses: 1,
            },
          },
        });
      } else {
        await route.fulfill({ json: { dados: [], registros: 0 } });
      }
    } else {
      await route.fulfill({ json: { status: null, resultados: [], nodes: [], edges: [] } });
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Gestão & API Gov.br" }).click();
  await page.getByLabel("Chave da API do Portal da Transparência").fill("portal-api-secret");
  await page.getByRole("button", { name: "Iniciar Download Integral" }).click();
  await expect(page.getByText(/Coleta concluída! 5 beneficiários/)).toBeVisible();

  await page.getByRole("button", { name: "Visão Geral" }).click();
  await expect(page.getByText("Pessoas Únicas")).toBeVisible();
  await expect(page.getByText("R$ 600,00").first()).toBeVisible();
  await expect.poll(() => dashboardQuery).toMatchObject({
    tipo: "Adicionar beneficiários",
    programa: "Novo Bolsa Familia",
    ano: "2026",
    mes: "01",
    resumo: true,
    permitir_novos: false,
  });
});

test("dashboard de beneficiários consulta apenas o resumo agregado", async ({ page }) => {
  const beneficiaryQueries = [];
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/municipios") {
      await route.fulfill({
        json: {
          municipios: [{ codigo_ibge: "2910750", nome: "Fátima", uf: "BA" }],
          ufs: ["BA"],
        },
      });
    } else if (url.pathname === "/api/filtros") {
      await route.fulfill({ json: { programas: ["Novo Bolsa Familia (sacado)"] } });
    } else if (url.pathname === "/api/consultar") {
      const request = route.request().postDataJSON();
      if (request.tipo === "Adicionar beneficiários") {
        beneficiaryQueries.push(request);
      }
      await route.fulfill({
        json: request.resumo ? {
          dados: [
            { ano: 2025, mes: 1, mes_num: 1, valor: 1000, beneficiados: 2 },
            { ano: 2025, mes: 2, mes_num: 2, valor: 700, beneficiados: 1 },
          ],
          registros: 3,
          resumo: {
            registros: 3,
            total_valor: 1700,
            total_beneficiados: 3,
            meses: 2,
          },
        } : { dados: [], registros: 0, total_paginas: 1 },
      });
    } else {
      await route.fulfill({ json: { status: null } });
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Beneficiários (Listagem Pessoal)" }).click();
  await expect(page.getByText("R$ 1.700,00")).toBeVisible();
  expect(beneficiaryQueries.length).toBeGreaterThan(0);
  expect(beneficiaryQueries.at(-1).resumo).toBe(true);
  expect(beneficiaryQueries.at(-1)).not.toHaveProperty("pagina");
});

test("salva, usa e remove uma chave sem exibir seu valor", async ({ page }) => {
  let keys = [];
  const managementRequests = [];
  let collectionRequest;
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/municipios") {
      await route.fulfill({
        json: {
          municipios: [{ codigo_ibge: "2910750", nome: "Fátima", uf: "BA" }],
          ufs: ["BA"],
        },
      });
    } else if (url.pathname === "/api/filtros") {
      await route.fulfill({ json: { programas: ["Novo Bolsa Familia (sacado)"] } });
    } else if (url.pathname === "/api/config/api-key" && route.request().method() === "GET") {
      await route.fulfill({ json: { enabled: true, configured: keys.length > 0, keys } });
    } else if (url.pathname === "/api/config/api-key" && route.request().method() === "PUT") {
      managementRequests.push({
        method: "PUT",
        headers: route.request().headers(),
        body: route.request().postDataJSON(),
      });
      keys = [{ id: "key-id", label: "••••cret" }];
      await route.fulfill({ json: { configured: true, keys } });
    } else if (url.pathname.startsWith("/api/config/api-key/") && route.request().method() === "DELETE") {
      managementRequests.push({
        method: "DELETE",
        headers: route.request().headers(),
      });
      keys = [];
      await route.fulfill({ json: { configured: false, keys } });
    } else if (url.pathname === "/api/consultar") {
      const request = route.request().postDataJSON();
      if (request.permitir_novos) {
        collectionRequest = {
          headers: route.request().headers(),
          body: request,
        };
      }
      await route.fulfill({ json: { dados: [], registros: 0, total_paginas: 1 } });
    } else {
      await route.fulfill({ json: { status: null } });
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Gestão & API Gov.br" }).click();
  await expect(page.getByLabel("Token de administrador")).toHaveCount(0);
  await page.getByLabel("Chave da API do Portal da Transparência").fill("portal-api-secret");
  await page.getByRole("button", { name: "Salvar chave criptografada" }).click();
  await expect(page.getByText("••••cret")).toBeVisible();
  expect(managementRequests[0].body).toEqual({ api_key: "portal-api-secret" });
  expect(managementRequests[0].headers["x-admin-token"]).toBeUndefined();
  await expect(page.getByLabel("Chave da API do Portal da Transparência")).toHaveValue("");

  await page.getByRole("button", { name: "Iniciar Download Integral" }).click();
  await expect(page.getByText(/Coleta concluída!/)).toBeVisible();
  expect(collectionRequest.headers["x-admin-token"]).toBeUndefined();
  expect(collectionRequest.body).not.toHaveProperty("api_key");
  expect(await page.evaluate(() => localStorage.length)).toBe(0);

  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "Remover" }).click();
  await expect(page.getByText("Chave removida do servidor.")).toBeVisible();
  expect(managementRequests.at(-1).method).toBe("DELETE");
  expect(managementRequests.at(-1).headers["x-admin-token"]).toBeUndefined();
});

test("inicia coleta com chave temporária do Portal sem token de administrador", async ({ page }) => {
  let collectionRequest;
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/municipios") {
      await route.fulfill({
        json: {
          municipios: [{ codigo_ibge: "2910750", nome: "Fátima", uf: "BA" }],
          ufs: ["BA"],
        },
      });
    } else if (url.pathname === "/api/filtros") {
      await route.fulfill({ json: { programas: ["Novo Bolsa Familia (sacado)"] } });
    } else if (url.pathname === "/api/config/api-key") {
      await route.fulfill({ json: { enabled: false, configured: false } });
    } else if (url.pathname === "/api/consultar") {
      const request = route.request().postDataJSON();
      if (request.permitir_novos) {
        collectionRequest = {
          headers: route.request().headers(),
          body: request,
        };
      }
      await route.fulfill({ json: { dados: [], registros: 0, total_paginas: 1 } });
    } else {
      await route.fulfill({ json: { status: null } });
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Gestão & API Gov.br" }).click();
  await page.getByLabel("Chave da API do Portal da Transparência").fill("portal-api-secret");
  await page.getByRole("button", { name: "Iniciar Download Integral" }).click();

  await expect(page.getByText(/Coleta concluída!/)).toBeVisible();
  expect(collectionRequest.headers["x-admin-token"]).toBeUndefined();
  expect(collectionRequest.body.api_key).toBe("portal-api-secret");
});

test("exibe a falha ao carregar municípios", async ({ page }) => {
  await page.route("**/api/municipios", route => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "serviço indisponível" }),
  }));

  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Não foi possível carregar os municípios");
  await expect(page.getByRole("alert")).toContainText("serviço indisponível");
});

test("exibe a falha ao carregar programas dos filtros", async ({ page }) => {
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/municipios") {
      await route.fulfill({
        json: {
          municipios: [{ codigo_ibge: "2910750", nome: "Fátima", uf: "BA" }],
          ufs: ["BA"],
        },
      });
    } else if (url.pathname === "/api/filtros") {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "erro no banco" }),
      });
    } else {
      await route.fulfill({ json: { dados: [], registros: 0 } });
    }
  });

  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Não foi possível carregar os programas disponíveis");
  await expect(page.getByRole("alert")).toContainText("erro no banco");
});
