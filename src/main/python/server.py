from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import networkx as nx
from io import StringIO
import numpy as np
from scipy.spatial.distance import cdist
import plotly.graph_objects as go
import geopandas as gpd
from shapely import wkt  # Para lidar com geometria WKT (Well-Known Text)

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

        df = pd.read_csv(StringIO(csv_data), sep=';', skipinitialspace=True)

        if 'Freguesia' not in df.columns or 'Municipio' not in df.columns or 'geometry' not in df.columns:
            return JSONResponse(
                content={"error": "O ficheiro CSV deve conter as colunas 'Freguesia', 'Municipio' e 'geometry'."},
                status_code=400,
            )

        G = nx.Graph()
        for idx, row in df.iterrows():
            property_id = str(row['Freguesia']) + "_" + str(row['Municipio'])
            try:
                geom = wkt.loads(row['geometry'])
                if geom.is_empty:
                    raise ValueError(f"Geometria vazia para {property_id}")
                centroid = geom.centroid
                lat, lon = centroid.y, centroid.x
                G.add_node(property_id, lat=lat, lon=lon)
            except Exception as e:
                print(f"Erro na geometria para {property_id}: {e}")
                continue

        distance_threshold = 2
        nodes = list(G.nodes())
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                node_i = nodes[i]
                node_j = nodes[j]
                lat1, lon1 = G.nodes[node_i]['lat'], G.nodes[node_i]['lon']
                lat2, lon2 = G.nodes[node_j]['lat'], G.nodes[node_j]['lon']
                distance = calculate_distance(lat1, lon1, lat2, lon2)
                if distance < distance_threshold:
                    G.add_edge(node_i, node_j)

        pos = nx.spring_layout(G, seed=42)
        edge_x, edge_y = [], []
        for edge in G.edges():
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x += [x0, x1, None]
            edge_y += [y0, y1, None]

        node_x = [pos[node][0] for node in G.nodes()]
        node_y = [pos[node][1] for node in G.nodes()]

        trace_edges = go.Scatter(x=edge_x, y=edge_y, mode='lines', line=dict(width=0.5, color='black'))
        trace_nodes = go.Scatter(x=node_x, y=node_y, mode='markers', marker=dict(size=5, color='red'))

        fig = go.Figure(data=[trace_edges, trace_nodes], layout=go.Layout(title="Grafo de Propriedades Rústicas", showlegend=False))

        return JSONResponse(content={"graph": fig.to_html(full_html=False, include_plotlyjs='cdn')})

    except Exception as e:
        print("Erro genérico:", e)
        return JSONResponse(content={"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
