import networkx as nx

# 1. Inicializa um grafo direcionado (as relações têm sentido, ex: Pessoa -> RECEBE -> Benefício)
G = nx.DiGraph()

# 2. Adiciona os Vértices (Nós) com suas propriedades (atributos)
# Usamos IDs únicos para os nós e adicionamos a propriedade 'tipo' para organização
G.add_node("m_sp", tipo="Municipio", nome="São Paulo", uf="SP")
G.add_node("p_joao", tipo="Pessoa", nome="João da Silva", cpf="123.456.789-00")
G.add_node("b_bf", tipo="ProgramaSocial", nome="Bolsa Família")
G.add_node("b_ag", tipo="ProgramaSocial", nome="Auxílio Gás")
G.add_node("e_cnpj", tipo="Empresa", cnpj="12.345.678/0001-99", razao_social="João Silva ME")

# 3. Adiciona as Arestas (Relacionamentos)
G.add_edge("p_joao", "m_sp", rel="MORA_EM")
G.add_edge("p_joao", "b_bf", rel="RECEBE")
G.add_edge("p_joao", "b_ag", rel="RECEBE")
G.add_edge("p_joao", "e_cnpj", rel="SÓCIO_DE")

# 4. Método para buscar os dados associados a uma pessoa específica por Nome e Município
def buscar_dados_pessoa(grafo, nome_busca, municipio_busca):
    # Encontra o ID do nó da pessoa pelo nome
    id_pessoa = None
    for no, atributos in grafo.nodes(data=True):
        if atributos.get("tipo") == "Pessoa" and atributos.get("nome") == nome_busca:
            id_pessoa = no
            break
            
    if not id_pessoa:
        return "Pessoa não encontrada."

    # Verifica se a pessoa mora no município indicado olhando os vizinhos de saída (successors)
    mora_no_municipio_correto = False
    for vizinho in grafo.successors(id_pessoa):
        if grafo.nodes[vizinho].get("tipo") == "Municipio" and grafo.nodes[vizinho].get("nome") == municipio_busca:
            mora_no_municipio_correto = True
            break
            
    if not mora_no_municipio_correto:
        return f"{nome_busca} não mora em {municipio_busca}."

    # Se passou na validação, coleta todos os dados conectados a ela
    resultado = {
        "Nome": nome_busca,
        "Município": municipio_busca,
        "Benefícios": [],
        "Empresas (CNPJ)": []
    }
    
    for vizinho in grafo.successors(id_pessoa):
        dados_vizinho = grafo.nodes[vizinho]
        tipo_vizinho = dados_vizinho.get("tipo")
        
        if tipo_vizinho == "ProgramaSocial":
            resultado["Benefícios"].append(dados_vizinho.get("nome"))
        elif tipo_vizinho == "Empresas": # Corrigido para bater com o tipo do nó
            resultado["Empresas (CNPJ)"].append(dados_vizinho.get("cnpj"))
        elif tipo_vizinho == "Empresa":
            resultado["Empresas (CNPJ)"].append(dados_vizinho.get("cnpj"))

    return resultado

# Executando a busca
dados_encontrados = buscar_dados_pessoa(G, "João da Silva", "São Paulo")
print(dados_encontrados)
