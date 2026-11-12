#!/usr/bin/env python3
"""
Módulo de detecção de anomalias para análise de grafos de programas sociais.

Este módulo fornece funções para detectar nós anômalos em um grafo com base
em métricas de centralidade e clustering, usando métodos estatísticos como
Z-Score e modificadores deIQR.
"""
import pandas as pd
import numpy as np
from scipy import stats
import networkx as nx


def detect_anomalies_in_graph(graph, z_threshold=2.0):
    """
    Detecta anomalias em um grafo com base em desvio padrão (Z-Score) das métricas de nó.
    
    Args:
        graph: Um objeto networkx.Graph representando a rede a ser analisada.
        z_threshold: Limiar de Z-Score acima do qual um nó é considerado anômalo.
                     Padrão é 2.0 (aproximadamente os top 5% em uma distribuição normal).

    Returns:
        Uma lista de tuplas, onde cada tupla contém:
        (node_id, anomaly_score, reason_string)
        node_id: O identificador do nó no grafo.
        anomaly_score: O maior Z-Score encontrado para aquele nó (indicador de gravidade).
        reason_string: Uma string legível explicando o motivo da detecção.
    """
    if graph.number_of_nodes() == 0:
        return []

    # Calcula métricas para cada nó
    try:
        degree_centrality_vals = nx.degree_centrality(graph)
    except:
        # Se falhar, usa grau simples normalizado
        degrees = dict(graph.degree())
        max_degree = max(degrees.values()) if degrees else 1
        degree_centrality_vals = {n: degrees.get(n, 0) / max_degree for n in graph.nodes()}
    
    try:
        clustering_coeffs = nx.clustering(graph)
    except (ZeroDivisionError, nx.NetworkXError):
        # Pode falhar em nós com grau < 2 em certas versões ou topologias
        clustering_coeffs = {n: 0.0 for n in graph.nodes()}
        
    try:
        betweenness_centrality_vals = nx.betweenness_centrality(graph, normalized=True, endpoints=False)
    except:
        betweenness_centrality_vals = {n: 0.0 for n in graph.nodes()}

    anomalies = []

    for node_id in graph.nodes():
        node_data = graph.nodes[node_id]
        label = node_data.get('label', str(node_id))
        node_type = node_data.get('tipo', 'desconhecido')

        # Coleta as métricas para este nó
        degree_val = degree_centrality_vals.get(node_id, 0)
        clustering_val = clustering_coeffs.get(node_id, 0)
        betweenness_val = betweenness_centrality_vals.get(node_id, 0)
        
        metrics = {
            'degree_centrality': degree_val,
            'clustering_coefficient': clustering_val,
            'betweenness_centrality': betweenness_val
        }

        # Calcula o Z-Score para cada métrica e pega o máximo
        max_z_score = 0
        reasons = []
        
        # Prepara listas de valores para cada métrica
        degree_values = [degree_centrality_vals.get(n, 0) for n in graph.nodes()]
        clustering_values = [clustering_coeffs.get(n, 0) for n in graph.nodes()]
        betweenness_values = [betweenness_centrality_vals.get(n, 0) for n in graph.nodes()]
        
        metric_lists = {
            'degree_centrality': degree_values,
            'clustering_coefficient': clustering_values,
            'betweenness_centrality': betweenness_values
        }

        for metric_name, value in metrics.items():
            # Coleta todos os valores dessa métrica para calcular a média e desvio padrão
            all_values = metric_lists[metric_name]
            
            # Filtra valores não numéricos
            numeric_values = [v for v in all_values if isinstance(v, (int, float))]
            if len(numeric_values) < 2:
                continue # Não é possível calcular Z-score com menos de 2 amostras

            mean_val = np.mean(numeric_values)
            std_val = np.std(numeric_values)
            
            if std_val == 0:
                z_score = 0
            else:
                z_score = abs((value - mean_val) / std_val)

            if z_score > max_z_score:
                max_z_score = z_score
            
            # Acumula razões se o Z-score for significativo
            if z_score > z_threshold:
                if metric_name == 'degree_centrality':
                    reasons.append(f"centralidade de grau elevada ({value:.3f} > média {mean_val:.3f})")
                elif metric_name == 'clustering_coefficient':
                    reasons.append(f"coeficiente de clustering elevado ({value:.3f} > média {mean_val:.3f})")
                elif metric_name == 'betweenness_centrality':
                    reasons.append(f"centralidade de intermediação elevada ({value:.3f} > média {mean_val:.3f})")

        # Se alguma métrica ultrapassou o limiar, registra como anomalia
        if max_z_score > z_threshold and reasons:
            reason_text = "; ".join(reasons)
            anomalies.append((node_id, max_z_score, f"Nó '{label}' ({node_type}): {reason_text}"))

    # Ordena pelo score de anomalia (maior primeiro)
    anomalies.sort(key=lambda x: x[1], reverse=True)
    
    return anomalies


def generate_anomaly_insights(anomalies):
    """
    Gera insights legíveis em linguagem natural a partir da lista de anomalias detectadas.
    
    Args:
        anomalies: Lista de tuplas (node_id, score, reason) retornada por detect_anomalies_in_graph.
        
    Returns:
        Uma lista de strings, onde cada string é um insight acionável ou informativo.
    """
    if not anomalies:
        return ["Nenhuma anomalia significativa detectada nos dados atuais."]
    
    insights = []
    total_anomalies = len(anomalies)
    
    # Insight geral
    insights.append(
        f"Foram detectadas {total_anomalies} estruturas de rede com padrões de conexão "
        f"estatisticamente incomuns em comparação com o restante da população analisada."
    )
    
    # Insights sobre os top 3 anômalos (se existirem)
    top_anomalies = anomalies[:3]
    for i, (node_id, score, reason) in enumerate(top_anomalies, 1):
        # Extrai o label do motivo para tornar a frase mais natural
        # Ex: "Nó 'BOLSA FAMILIA' (programa): coeficiente de clustering elevado (0.85 > média 0.12)"
        try:
            # Encontrar o nó entre aspas simples
            import re
            label_match = re.search(r"'([^']*)'", reason)
            label_part = label_match.group(1) if label_match else "um nó"
            
            # Encontrar o tipo entre parênteses
            type_match = re.search(r'$([^)]*)$', reason)
            type_part = type_match.group(1) if type_match else ""
            
            # Pegar o texto após os dois pontos
            insight_match = re.search(r': (.*)', reason)
            insight_text = insight_match.group(1) if insight_match else reason
            
            insights.append(
                f"{i}. {label_part} ({type_part}) apresenta padrão de conexão atípico: {insight_text.lower()}."
            )
        except Exception:
            # Fallback caso o parsing falhe
            insights.append(f"{i}. {reason}")

    # Insight sobre a possível interpretação
    if total_anomalies > 0:
        insights.append(
            "Recomenda-se investigar esses nós para verificar se estão relacionados a "
            "erros de cadastro, fraudes, ou políticas públicas excepcionalmente eficazes ou problemáticas."
        )
        
    return insights