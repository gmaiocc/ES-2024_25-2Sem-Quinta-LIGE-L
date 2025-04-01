from fastapi import FastAPI
from fastapi.responses import JSONResponse
import pandas as pd
import networkx as nx
from io import StringIO

app = FastAPI()

@app.post("/process_data")
async def process_data(data: dict):
    try:
        csv_data = data.get("data")
        print("Recebido CSV:\n", csv_data)

        df = pd.read_csv(StringIO(csv_data))
        print("DataFrame carregado:\n", df.head())

        G = nx.Graph()

        for _, row in df.iterrows():
            G.add_node(row['ID'], name=row['Nome'])
            adjacentes = row['Adjacentes'].split(';') if pd.notna(row['Adjacentes']) else []
            for adj in adjacentes:
                G.add_edge(row['ID'], adj)

        graph_data = {
            "nodes": [{"id": str(n)} for n in G.nodes()],
            "links": [{"source": str(s), "target": str(t)} for s, t in G.edges()]
        }

        print("Grafo criado com sucesso!")
        return JSONResponse(content=graph_data)

    except Exception as e:
        print("Erro no processamento:", e)
        return JSONResponse(content={"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
