from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from io import StringIO
from collections import defaultdict
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/process_graph")
async def process_graph(data: dict, limit: Optional[int] = Query(None, description="Limit the number of nodes and edges for testing")):
    try:
        csv_data = data.get("data")
        print("Recebido CSV para grafo:\n", csv_data[:100] + "..." if len(csv_data) > 100 else csv_data)

        separadores_possiveis = [';', ',', '\t']
        df = None
        used_separator = None
        for sep in separadores_possiveis:
            try:
                temp_df = pd.read_csv(StringIO(csv_data), sep=sep, skipinitialspace=True)
                if temp_df.shape[1] > 1:
                    df = temp_df
                    used_separator = sep
                    break
            except pd.errors.ParserError:
                continue

        if df is None:
            return JSONResponse(content={"error": "Não foi possível determinar o formato do CSV."}, status_code=400)

        print(f"CSV carregado com separador: '{used_separator}'")
        print("Cabeçalho do DataFrame carregado para o grafo:\n", df.head())

        required_columns = ['OBJECTID', 'OWNER', 'Freguesia']
        if not all(col in df.columns for col in required_columns):
            return JSONResponse(
                content={"error": f"O ficheiro CSV deve conter as colunas: {', '.join(required_columns)}."},
                status_code=400,
            )

        nodes = []
        edges = []
        property_map = {}
        processed_count = 0

        for index, row in df.iterrows():
            property_id = str(row['OBJECTID'])
            nodes.append({
                'id': property_id,
                'label': f"Propriedade {property_id}\n({row['OWNER']})",
                'title': f"ID: {property_id}<br>Proprietário: {row['OWNER']}<br>Freguesia: {row['Freguesia']}<br>Município: {row['Municipio'] if 'Municipio' in row else 'N/A'}",
            })
            property_map[property_id] = index
            processed_count += 1
            if limit is not None and processed_count >= limit:
                print(f"Limite de {limit} nós atingido.")
                break

        final_nodes = nodes  # Apply limit to nodes

        owner_freguesia_properties = defaultdict(list)
        for index, row in df.iterrows():
            if limit is not None and index >= limit:
                break
            owner_freguesia = (row['OWNER'], row['Freguesia'])
            owner_freguesia_properties[owner_freguesia].append(str(row['OBJECTID']))

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
            if limit is not None and len(edges) > limit * 5: # Heuristic to limit edges
                print(f"Limite aproximado de {limit * 5} arestas atingido.")
                break

        unique_edges = set()
        final_edges = []
        for edge in edges:
            sorted_edge = tuple(sorted((edge['from'], edge['to'])))
            if sorted_edge not in unique_edges:
                unique_edges.add(sorted_edge)
                final_edges.append(edge)
            if limit is not None and len(final_edges) >= limit * 5:
                break

        graph_data = {
            'nodes': final_nodes,
            'edges': final_edges
        }

        print(f"Dados do grafo criados com sucesso (limit={'all' if limit is None else limit} nodes, {len(final_edges)} edges).")
        return JSONResponse(content=graph_data)

    except Exception as e:
        print("Erro genérico no processamento do grafo:", e)
        return JSONResponse(content={"error": str(e)}, status_code=500)