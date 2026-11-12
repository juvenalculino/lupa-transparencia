# Benefícios por Município

Coleta dados do [Portal da Transparência](https://api.portaldatransparencia.gov.br/swagger-ui/index.html#/)
(API de dados) e salva em SQLite. A interface principal é um painel React +
FastAPI; há também uma versão alternativa em Streamlit.

## O que faz

- **Agregados por ano**: para um benefício, município e ano, permite escolher
  meses específicos ou todos os meses e busca `valor` e `quantidadeBeneficiados`.
- **Beneficiários**: permite adicionar ao banco os dados de um mês ou de todos
  os meses válidos do ano, com NIS, nome, CPF mascarado e valor.
- **Municípios**: o seletor da barra lateral pode mostrar somente municípios
  com dados de benefícios já coletados ou todos os municípios, para selecionar
  um novo local na aba de Gestão & API Gov.br. A lista ativa é agrupada por UF
  e atualizada ao concluir uma coleta.
- **Busca de pessoas**: agrupa os registros já coletados por pessoa e programa,
  mostrando a quantidade de ocorrências e os anos em que foram encontradas.
- **Busca geral de beneficiário**: procura por nome ou NIS em todos os
  programas e anos salvos para o município selecionado, sem depender do
  programa/ano dos filtros principais, e lista os programas encontrados.
- **Painel municipal**: apresenta indicadores, cobertura por programa e gráficos
  mensais de titulares e pagamentos, além de uma tabela pesquisável de
  beneficiários agrupados por NIS.
- **Grafo inteligente**: explora programas com NIS em comum ou os programas,
  competências e representantes legais registrados para uma pessoa. Relações
  entre programas indicam apenas beneficiários em comum; não comprovam
  parentesco nem residência conjunta. Nomes iguais com NIS diferentes são
  mantidos como pessoas distintas, e NIS não é exibido integralmente no grafo.
- **Novo Bolsa Família**: mostra titulares, CPF mascarado, meses encontrados e
  valores recebidos, inclusive para os registros que já estavam no banco.
- **CNPJs**: importa um CSV municipal disponível em `utils/` ou baixa empresas
  do município selecionado, salva empresas e sócios no SQLite e cruza sócios
  pessoa física com beneficiários do mesmo município.
- **About**: descreve o sistema, as fontes consultadas e uma seção de
  transparência sobre tratamento de dados e LGPD.
- **Ver dados**: tabelas e gráficos dos dados salvos.
- Meses já coletados são ignorados ao adicionar dados, evitando novas chamadas
  para períodos que já estão completos.

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

### Painel Web (React + FastAPI)

Instale as dependências do frontend e gere os arquivos otimizados:

```bash
npm install
npm run build
```

Inicie a API e abra `http://localhost:8000`:

```bash
uvicorn api:app --reload
```

Durante o desenvolvimento, use `npm run dev` e mantenha a API na porta 8000;
o Vite encaminha automaticamente as rotas `/api` para ela. O build de produção
é servido pelo FastAPI a partir de `dist/`.

Se o painel abrir apenas com o fundo escuro e não carregar municípios, confirme
que o FastAPI está ativo em `http://127.0.0.1:8000` e inicie-o em outro terminal
com `uvicorn api:app --reload`. A tela mostra essa orientação quando a API não
responde; executar somente `npm run dev` inicia o frontend, não o backend.

#### Chave da API em servidor

O painel permite salvar várias chaves do Portal da Transparência, criptografadas
no servidor. Para preparar a chave de criptografia uma vez, execute:

```bash
.venv/bin/python configurar_segredos.py
```

Isso cria `.secrets/server.env` com a chave Fernet, com permissões restritas.
O FastAPI carrega esse valor automaticamente ao iniciar; variáveis de ambiente
explícitas têm precedência. Reinicie o servidor depois de gerar o arquivo.
Mantenha esse arquivo protegido e não o inclua no repositório ou em logs. As
chaves cifradas ficam por padrão em `.secrets/portal_api_key.enc`, também com
permissões restritas, e podem ser movidas definindo `PORTAL_API_KEY_FILE`. Faça
backup protegido de `server.env` e do arquivo cifrado: sem a chave Fernet, não
será possível recuperar as chaves salvas. Não troque a chave Fernet enquanto
houver chaves da API salvas.

Na aba **Gestão & API Gov.br**, informe uma chave e use **Salvar chave
criptografada** para adicioná-la à lista; as chaves são exibidas mascaradas e
podem ser removidas individualmente. Ao receber HTTP 429 por limite de uso, a
coleta tenta automaticamente outra chave cadastrada. O gerenciamento de chaves
é restrito a conexões locais; não exponha o servidor na rede ou na internet sem
adicionar uma camada própria de autenticação e controle de acesso.

O seletor **Lista de municípios** da barra lateral alterna entre os municípios
com dados de benefícios coletados (incluindo os registrados no histórico de
coletas) e todos os municípios disponíveis. Para iniciar uma coleta em uma
nova cidade, escolha **Todos os municípios — consultar/baixar**, selecione a UF
e o município e inicie a coleta na aba de Gestão. Ao concluir, ele passa a
aparecer na lista de municípios com dados. Os dados e indicadores da aba CNPJs
permanecem carregados ao navegar para outras páginas e voltar; uma nova
consulta ocorre ao trocar o município, refazer filtros ou atualizar a coleta.
Na Visão Geral e na Tabela, o painel prioriza os registros detalhados de
beneficiários quando eles existem; se o município tiver somente dados
agregados, usa esse modo. Após uma coleta, os filtros são ajustados para o
programa e período baixados, e a seleção do município detecta novamente o tipo
de dado disponível após recarregar a página.

Os testes de interface usam Playwright. Instale o Chromium uma vez com
`npx playwright install chromium` e execute `npm run test:e2e`. Para usar um
Chrome já instalado, defina `CHROME_EXECUTABLE_PATH` antes do comando.

#### Empresas e sócios (CNPJs)

Na aba **CNPJs**, o município acompanha a seleção de UF/município do painel.
**Importar CSV local** carrega o arquivo correspondente disponível em `utils/`
(por exemplo, `cnpj_FATIMA_BA.csv`). **Baixar CNPJs** consulta a Casa dos Dados
e a BrasilAPI, mostra o andamento e grava empresas/sócios no banco; a lista e o
enriquecimento usam cache retomável em `utils/`. A operação não exige token de
administrador. O painel também mostra o capital social do município, a lista de
empresas com filtros por nome, capital e situação cadastral (com seleção de
múltiplas situações ou todas) e o grafo de relacionamento entre empresas e
sócios, além de exportar CSV/XLSX. Os dados ficam nas tabelas
`cnpj_empresa`, `cnpj_socio` e `cnpj_coleta`.

Na lista de empresas, **Baixar lista (CSV/XLSX)** exporta os CNPJs conforme os
filtros aplicados. Esses mesmos filtros limitam a seção **Beneficiários que
também constam como sócios**, que também permite selecionar um programa do
benefício ou **Todos os programas**. O **relatório detalhado (PDF)** aplica os
filtros de empresa e o programa selecionado. **Baixar benefícios intermunicipais (CSV)**
gera um resumo agregado de empresas/sócios e correspondências por programa e
município no banco local. Grupos com menos de cinco beneficiários distintos
são omitidos; esse CSV não inclui nomes, NIS nem CPF.

**Baixar relatório detalhado (PDF)** gera um arquivo completo, sem paginação,
dos beneficiários com correspondência forte no município selecionado. Inclui
CPF sempre mascarado, programas, competências e valores registrados, além dos
dados empresariais disponíveis (CNPJ, situação, capital, CNAE, porte e endereço)
e os dados disponíveis do sócio correspondente. NIS e CPF completo não são
incluídos. O relatório reflete os dados atualmente armazenados localmente e
informa a data/origem da coleta; resultados são indicativos, não comprovam
identidade, renda ou irregularidade.

Na seção de beneficiários que também constam como sócios, o capital social é
exibido por empresa e representa o valor cadastrado para a empresa, não o
patrimônio pessoal do beneficiário. O grafo usa um conjunto limitado de empresas
e uma estabilização curta para reduzir o impacto no carregamento da tela.

O cruzamento usa registros do mesmo município e sócios pessoa física. Para
evitar associações frágeis, exige igualdade do nome após normalização de
acentos/pontuação e dos seis dígitos visíveis do CPF mascarado. A máscara não é
um identificador único e os resultados são indicativos, não comprovam
identidade, renda ou irregularidade. Não se usa correspondência aproximada de
nomes nem o CNPJ de sócios pessoa jurídica.

O resumo intermunicipal parte das correspondências locais por nome e CPF
mascarado e procura os mesmos NIS no histórico dos demais municípios. Os totais
são agrupados por município e programa e só são exibidos/exportados quando há
pelo menos cinco NIS distintos no grupo. A contagem representa registros
encontrados no banco local, não confirma residência atual, pagamento simultâneo
ou irregularidade.

O município selecionado no painel é lembrado neste navegador e restaurado após
recarregar a página, desde que ainda esteja disponível na lista do backend.

A seção **About > LGPD e privacidade** informa os dados técnicos observados no
projeto. O controlador, seu CNPJ institucional e o canal para solicitações de
titulares não estão configurados no código e devem ser preenchidos pelo
responsável pela implantação; o projeto não define a base legal nem um prazo
automático de retenção.

### Painel Streamlit

```bash
streamlit run app.py
```

1. Cole sua **chave da API** na barra lateral
   (gerada em https://api.portaldatransparencia.gov.br — ela não é salva em arquivo).
2. Escolha o que buscar (agregado mensal do ano ou adicionar beneficiários),
   o programa e o estado. No campo **Buscar município**, digite parte do nome
   ou o código IBGE; o seletor reúne todos os municípios do estado, sem uma
   segunda lista duplicada.
3. Em **Agregado mensal do ano**, selecione todos os meses ou escolha meses
   específicos. Por padrão, ano e meses são limitados aos dados já salvos
   para o programa e município selecionados. Marque **Incluir competências
   ainda não salvas** para consultar outros períodos pela API.
4. Em **Adicionar beneficiários**, escolha um mês ou o ano inteiro. Clique em
   **Adicionar dados do programa** para ver as competências já registradas;
   ano e meses disponíveis são filtrados pelo programa e município. Para
   consultar novas competências, marque **Incluir competências ainda não
   salvas**. A ação mostra um resumo e a tabela dos dados salvos.
5. No painel municipal, abra **Famílias e beneficiários** para filtrar por
   programa, ano, nome ou NIS. O Novo Bolsa Família é selecionado por padrão
   quando há registros disponíveis.
6. A tabela resume os pagamentos por titular/NIS e reúne todos os programas
   encontrados para cada pessoa. No BPC, identifica titulares menores de 16
   anos e mostra os dados do representante legal quando a API os fornece.
   Para meses coletados antes dessa informação ser salva, marque
   **Reconsultar meses já coletados** em **Adicionar beneficiários** para
   atualizar os dados. A lista é paginada para manter a navegação rápida. A
   API não informa a composição completa da família.
7. O app valida a vigência do programa e evita coletar novamente meses já
   incluídos no banco.
8. Em **Grafo inteligente**, escolha entre ver NIS compartilhados por programa
   ou buscar uma pessoa pelo nome/NIS para visualizar os programas registrados.
   Opcionalmente, veja outras pessoas que aparecem nos mesmos programas; essa
   coincidência não significa parentesco ou composição familiar.
9. Use **Buscar beneficiário em qualquer programa** para pesquisar em todo o
   histórico local do município selecionado. A busca mostra os programas e
   competências de cada pessoa identificada, independentemente dos filtros
   de programa e período escolhidos acima.

## Vigência dos programas

O app sabe o período de cada programa e avisa antes de buscar à toa
(ex.: Auxílio Brasil só existiu de nov/2021 a fev/2023):

| Programa | Início | Fim |
|---|---|---|
| Bolsa Família (1ª versão) | out/2003 | out/2021 |
| Auxílio Emergencial | abr/2020 | out/2021 |
| Auxílio Brasil | nov/2021 | fev/2023 |
| Novo Bolsa Família (2ª versão) | mar/2023 | em atividade |
| BPC | jan/1996 | em atividade |
| PETI | 1996 | 2005 |
| Seguro Defeso | 1991 | em atividade |
| Garantia Safra | 2002 | em atividade |

## Limites da API

- 00:00–05:59 (horário de Brasília): até 700 requisições/minuto.
- 06:00–23:59 (horário de Brasília): até 400 requisições/minuto.
- Endpoints restritos, como `despesas/documentos-por-favorecido` e
  `bolsa-familia-disponivel-por-cpf-ou-nis`: até 180 requisições/minuto.

O cliente reserva chamadas dentro de uma janela móvel de 60 segundos e aplica
95% desses limites como margem de segurança: até 665 req/min à noite, 380
req/min durante o dia e 171 req/min para endpoints restritos. A cota geral
também é aplicada às chamadas de endpoints restritos. O controle é compartilhado
entre instâncias do cliente com a mesma chave dentro do mesmo processo; se o app
for executado em mais de um processo ou máquina, cada processo terá seu próprio
controle.

As rotas atualmente usadas pelo painel são as consultas por município e não
incluem os dois endpoints restritos citados acima. Se uma delas passar a ser
usada, sua classificação deve ser confirmada com a documentação da API. Em
resposta HTTP 429, o cliente respeita `Retry-After` quando informado e conta
tentativas com erro nos totais registrados.

Para não exceder a cota nem depender de suporte da API a chamadas paralelas, as
páginas de beneficiários são consultadas sequencialmente. O cliente evita
consultas de meses já salvos e não adiciona uma pausa extra após a resposta da
API; isso aproveita melhor o limite sem aumentar a concorrência. Para aumentar
a velocidade além disso, é preciso medir a latência real e confirmar se a API
permite requisições paralelas.

## Banco de dados

`beneficios.db` (SQLite, criado na pasta do app):

- `municipio` — código IBGE, nome, UF
- `beneficio_mensal` — benefício, mês (AAAAMM), município, valor, qtd. beneficiados
- `beneficiario` — benefício, mês, município, NIS, nome, CPF mascarado, valor
- `coleta_log` — histórico de cada coleta (páginas, registros, tempo)

## Arquivos

- `app.py` — painel Streamlit
- `coleta.py` — cliente da API + banco (reutilizável sem o Streamlit)
- `dados/municipios.json`, `dados/estados.json` — IBGE de todos os municípios
  (fonte: https://github.com/kelvins/municipios-brasileiros)
