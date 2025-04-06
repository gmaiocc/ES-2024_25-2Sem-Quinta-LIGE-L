from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from io import StringIO

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

        print("Cabeçalho do DataFrame carregado:\n", df.head())

        if 'Freguesia' not in df.columns or 'Municipio' not in df.columns or 'Shape_Area' not in df.columns:
            return JSONResponse(
                content={"error": "O ficheiro CSV deve conter as colunas 'Freguesia', 'Municipio' e 'Shape_Area'."},
                status_code=400,
            )

        # Group by Freguesia and Municipio and sum Shape_Area
        grouped_data = df.groupby(['Freguesia', 'Municipio'])['Shape_Area'].sum().reset_index()

        # Prepare data for Plotly 3D bar chart
        bar_data = {
            'x': grouped_data['Freguesia'].tolist(),
            'y': grouped_data['Municipio'].tolist(),
            'z': grouped_data['Shape_Area'].tolist(),
            'type': 'bar3d'
        }

        print("Dados para gráfico de barras 3D criados com sucesso!")
        return JSONResponse(content=bar_data)

    except Exception as e:
        print("Erro genérico no processamento:", e)
        return JSONResponse(content={"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)