from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from io import StringIO
from collections import defaultdict
from typing import Optional

# Criação da instância do FastAPI
app = FastAPI()

# Configuração do middleware CORS para permitir requisições de qualquer origem
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite requisições de qualquer origem
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos os métodos HTTP
    allow_headers=["*"],  # Permite todos os cabeçalhos
)


# Rota POST para processar o grafo a partir de um CSV
@app.post("/process_graph")
async def process_graph(data: dict, limit: Optional[int] = Query(None,
                                                                 description="Limite para o número de nós e arestas durante os testes")):
    try:
        # Obtém os dados CSV passados na requisição
        csv_data = data.get("data")
        print("Recebido CSV para grafo:\n", csv_data[:100] + "..." if len(csv_data) > 100 else csv_data)

        # Definição de separadores possíveis para o CSV (pode ser ponto e vírgula, vírgula ou tabulação)
        separadores_possiveis = [';', ',', '\t']
        df = None
        used_separator = None

        # Tenta carregar o CSV com cada separador possível
        for sep in separadores_possiveis:
            try:
                temp_df = pd.read_csv(StringIO(csv_data), sep=sep, skipinitialspace=True)
                if temp_df.shape[1] > 1:  # Verifica se o CSV foi carregado corretamente (pelo menos 2 colunas)
                    df = temp_df
                    used_separator = sep
                    break
            except pd.errors.ParserError:
                continue  # Caso ocorra um erro ao ler o CSV com o separador, tenta o próximo separador

        # Se não for possível determinar o formato do CSV, retorna erro
        if df is None:
            return JSONResponse(content={"error": "Não foi possível determinar o formato do CSV."}, status_code=400)

        print(f"CSV carregado com separador: '{used_separator}'")
        print("Cabeçalho do DataFrame carregado para o grafo:\n", df.head())

        # Colunas obrigatórias no CSV
        required_columns = ['OBJECTID', 'OWNER', 'Freguesia']
        if not all(col in df.columns for col in required_columns):
            return JSONResponse(
                content={"error": f"O ficheiro CSV deve conter as colunas: {', '.join(required_columns)}."},
                status_code=400,
            )

        # Inicializa as listas de nós e arestas, e um dicionário para mapear as propriedades
        nodes = []
        edges = []
        property_map = {}
        processed_count = 0

        # Itera sobre as linhas do DataFrame para criar os nós do grafo
        for index, row in df.iterrows():
            property_id = str(row['OBJECTID'])
            # Adiciona um nó com informações sobre a propriedade
            nodes.append({
                'id': property_id,
                'label': f"Propriedade {property_id}\n({row['OWNER']})",
                'title': f"ID: {property_id}<br>Proprietário: {row['OWNER']}<br>Freguesia: {row['Freguesia']}<br>Município: {row['Municipio'] if 'Municipio' in row else 'N/A'}",
            })
            # Mapeia o ID da propriedade para o índice da linha
            property_map[property_id] = index
            processed_count += 1
            if limit is not None and processed_count >= limit:  # Aplica o limite de nós se necessário
                print(f"Limite de {limit} nós atingido.")
                break

        final_nodes = nodes  # Aplica o limite aos nós

        # Cria um dicionário para agrupar as propriedades por proprietário e freguesia
        owner_freguesia_properties = defaultdict(list)
        for index, row in df.iterrows():
            if limit is not None and index >= limit:
                break
            owner_freguesia = (row['OWNER'], row['Freguesia'])
            owner_freguesia_properties[owner_freguesia].append(str(row['OBJECTID']))

        # Cria as arestas entre as propriedades com o mesmo proprietário e freguesia
        for properties in owner_freguesia_properties.values():
            if len(properties) > 1:
                for i in range(len(properties)):
                    for j in range(i + 1, len(properties)):
                        source = properties[i]
                        target = properties[j]
                        edges.append({
                            'from': source,
                            'to': target,
                        })
            if limit is not None and len(edges) > limit * 5:  # Heurística para limitar o número de arestas
                print(f"Limite aproximado de {limit * 5} arestas atingido.")
                break

        # Remove arestas duplicadas, garantindo que cada aresta é única
        unique_edges = set()
        final_edges = []
        for edge in edges:
            sorted_edge = tuple(sorted((edge['from'], edge['to'])))
            if sorted_edge not in unique_edges:
                unique_edges.add(sorted_edge)
                final_edges.append(edge)
            if limit is not None and len(final_edges) >= limit * 5:  # Aplica o limite de arestas
                break

        # Dados finais do grafo a serem retornados na resposta
        graph_data = {
            'nodes': final_nodes,
            'edges': final_edges
        }

        print(
            f"Dados do grafo criados com sucesso (limit={'todos' if limit is None else limit} nós, {len(final_edges)} arestas).")
        return JSONResponse(content=graph_data)

    except Exception as e:
        # Se ocorrer um erro genérico durante o processamento, retorna um erro 500
        print("Erro genérico no processamento do grafo:", e)
        return JSONResponse(content={"error": str(e)}, status_code=500)
