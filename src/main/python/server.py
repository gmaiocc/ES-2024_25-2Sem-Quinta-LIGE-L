from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import networkx as nx
from io import StringIO
import numpy as np
from scipy.spatial.distance import cdist
import plotly.graph_objects as go  # Importar corretamente o plotly.graph_objects

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def calculate_distance(lat1, lon1, lat2, lon2):
    # Calcular distância entre dois pontos usando a fórmula Haversine
    R = 6371  # Raio da Terra em km
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c  # Retorna a distância em km

@app.post("/process_data")
async def process_data(data: dict):
    try:
        csv_data = data.get("data")
        print("Recebido CSV:\n", csv_data[:100] + "..." if len(csv_data) > 100 else csv_data)

        separadores_possiveis = [',', ';', '\t']
        df = None
        for sep in separadores_possiveis:
            try:
                df = pd.read_csv(StringIO(csv_data), sep=sep, skipinitialspace=True)
                break
            except pd.errors.ParserError:
                continue

        if df is None:
            return JSONResponse(content={"error": "Não foi possível determinar o formato do CSV."}, status_code=400)

        # Verifica se as colunas necessárias estão no CSV
        if 'Freguesia' not in df.columns or 'Municipio' not in df.columns or 'Latitude' not in df.columns or 'Longitude' not in df.columns:
            return JSONResponse(
                content={"error": "O ficheiro CSV deve conter as colunas 'Freguesia', 'Municipio', 'Latitude' e 'Longitude'."},
                status_code=400,
            )

        # Criação do grafo de propriedades rústicas
        G = nx.Graph()

        # Adiciona as propriedades como nós
        for idx, row in df.iterrows():
            property_id = row['Freguesia'] + "_" + row['Municipio']  # Criando um ID único
            G.add_node(property_id, lat=row['Latitude'], lon=row['Longitude'])

        # Calcula as distâncias entre as propriedades e cria arestas se a distância for menor que um limite
        distance_threshold = 2  # km (exemplo de limite de proximidade)
        coords = df[['Latitude', 'Longitude']].values
        distances = cdist(coords, coords, metric='haversine')  # Calcula as distâncias em km

        # Adiciona arestas para as propriedades adjacentes (dentro do limite de distância)
        for i in range(len(df)):
            for j in range(i + 1, len(df)):
                if distances[i, j] < distance_threshold:
                    property_i = df.iloc[i]['Freguesia'] + "_" + df.iloc[i]['Municipio']
                    property_j = df.iloc[j]['Freguesia'] + "_" + df.iloc[j]['Municipio']
                    G.add_edge(property_i, property_j)

        # Visualização 2D usando Plotly
        pos = nx.spring_layout(G, seed=42)  # Calcula as posições em 2D para os nós
        edge_x = []
        edge_y = []
        for edge in G.edges():
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x += [x0, x1, None]
            edge_y += [y0, y1, None]

        node_x = []
        node_y = []
        for node in G.nodes():
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)

        # Criar o gráfico 2D
        trace_edges = go.Scatter(x=edge_x, y=edge_y, mode='lines', line=dict(width=0.5, color='black'))
        trace_nodes = go.Scatter(x=node_x, y=node_y, mode='markers', marker=dict(size=5, color='red'))

        layout = go.Layout(title="Grafo de Propriedades Rústicas", showlegend=False)
        fig = go.Figure(data=[trace_edges, trace_nodes], layout=layout)

        # Retorna o HTML do gráfico
        return JSONResponse(content={"graph": fig.to_html()})

    except Exception as e:
        print("Erro genérico no processamento:", e)
        return JSONResponse(content={"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
