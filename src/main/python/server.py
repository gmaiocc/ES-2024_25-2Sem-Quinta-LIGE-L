# Importações necessárias
from functools import partial
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from io import StringIO
from collections import defaultdict
from typing import Optional
import shapely
from shapely.wkt import loads
from shapely.geometry import Polygon
from shapely.ops import transform
import pyproj
from itertools import combinations, product
from collections import deque

# Criação da aplicação FastAPI
app = FastAPI()

# Middleware para permitir chamadas de qualquer origem (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Variáveis globais para guardar os dados carregados
df_properties = None
property_adjacency_list = defaultdict(list)  # Grafo de adjacência de propriedades


# Função para tentar detetar e ler um CSV com diferentes separadores
def parse_csv_data(csv_data: str):
    separadores_possiveis = [";", ",", "\t"]
    df = None
    for sep in separadores_possiveis:
        try:
            df = pd.read_csv(StringIO(csv_data), sep=sep, skipinitialspace=True)
            if df.shape[1] > 1:
                return df  # Devolve se tiver mais do que 1 coluna (CSV válido)
        except pd.errors.ParserError:
            continue
    return None


# Função para projetar geometria de WKT entre dois sistemas de coordenadas (ex: WGS84 para UTM)
def project_geometry(geom_wkt: str, src_crs="EPSG:4326", target_crs="EPSG:32628"):
    try:
        geom = loads(geom_wkt)  # Converte string WKT para objeto Shapely
        if geom.is_empty:
            return None
        project_wgs_to_utm = partial(
            pyproj.transform, pyproj.Proj(src_crs), pyproj.Proj(target_crs)
        )
        return transform(
            project_wgs_to_utm, geom
        )  # Aplica a transformação de coordenadas
    except Exception as e:
        print(f"Erro ao projetar geometria: {e}")
        return None


# Verifica se duas geometrias são adjacentes (tocam-se ou sobrepõem-se)
def check_adjacency(geom1, geom2):
    if geom1 is None or geom2 is None:
        return False
    return geom1.touches(geom2) or geom1.intersects(geom2)


# Endpoint para obter detalhes de uma propriedade com base no seu ID
@app.get("/properties/{objectid}")
async def get_property_details(objectid: str):
    global df_properties, property_adjacency_list
    if df_properties is None:
        return JSONResponse(
            content={"error": "Os dados das propriedades não foram carregados."},
            status_code=400,
        )

    try:
        # Filtra a linha com o ID correspondente
        property_row = df_properties[
            df_properties["OBJECTID"].astype(str) == objectid
        ].iloc[0]
        if property_row.empty:
            return JSONResponse(
                content={"error": f"Propriedade com ID {objectid} não encontrada."},
                status_code=404,
            )

        owner = property_row.get("OWNER")
        freguesia = property_row.get("Freguesia")

        # Busca as propriedades adjacentes
        adjacent_properties = property_adjacency_list.get(objectid, [])

        return JSONResponse(
            content={
                "id": str(objectid),
                "owner": str(owner) if pd.notna(owner) else None,
                "freguesia": str(freguesia) if pd.notna(freguesia) else None,
                "adjacent_properties": [
                    str(prop_id) for prop_id in adjacent_properties
                ],
            }
        )
    except IndexError:
        return JSONResponse(
            content={"error": f"Propriedade com ID {objectid} não encontrada."},
            status_code=404,
        )
    except Exception as e:
        print(f"Erro ao obter detalhes da propriedade: {e}")
        return JSONResponse(
            content={"error": "Erro interno do servidor"}, status_code=500
        )


# Endpoint para processar grafo de adjacência entre propriedades
@app.post("/process_properties_graph")
async def process_properties_graph(
    data: dict,
    limit: Optional[int] = Query(None, description="Limite para o número de nós"),
):
    try:
        csv_data = data.get("data")
        df = parse_csv_data(csv_data)
        if df is None:
            return JSONResponse(
                content={"error": "Não foi possível determinar o formato do CSV."},
                status_code=400,
            )

        # Armazena o DataFrame globalmente e limpa lista de adjacência
        global df_properties, property_adjacency_list
        df_properties = df
        property_adjacency_list.clear()

        # Verifica se todas as colunas necessárias estão presentes
        required_columns = ["OBJECTID", "geometry", "OWNER", "Freguesia"]
        if not all(col in df.columns for col in required_columns):
            return JSONResponse(
                content={
                    "error": f"O CSV deve conter as colunas: {', '.join(required_columns)} para o grafo de propriedades."
                },
                status_code=400,
            )

        # Criação de nós e armazenamento das geometrias
        nodes = []
        property_geometries = {}
        for index, row in df.iterrows():
            prop_id = str(row["OBJECTID"])
            nodes.append(
                {
                    "id": prop_id,
                    "label": f"Propriedade {prop_id}",
                    "title": f"ID: {prop_id}",
                }
            )
            property_geometries[prop_id] = row["geometry"]
            if limit is not None and len(nodes) >= limit:
                break

        # Criação de arestas com base em adjacência
        edges = []
        processed_pairs = set()
        property_ids = list(property_geometries.keys())

        projected_geometries = {
            prop_id: project_geometry(geom_wkt)
            for prop_id, geom_wkt in property_geometries.items()
        }

        for i in range(len(property_ids)):
            prop1_id = property_ids[i]
            geom1_proj = projected_geometries.get(prop1_id)
            for j in range(i + 1, len(property_ids)):
                prop2_id = property_ids[j]
                geom2_proj = projected_geometries.get(prop2_id)

                sorted_pair = tuple(sorted((prop1_id, prop2_id)))
                if sorted_pair not in processed_pairs:
                    if check_adjacency(geom1_proj, geom2_proj):
                        edges.append({"from": prop1_id, "to": prop2_id})
                        property_adjacency_list[prop1_id].append(prop2_id)
                        property_adjacency_list[prop2_id].append(prop1_id)
                    processed_pairs.add(sorted_pair)
                    if limit is not None and len(edges) >= limit * 5:
                        break
            if limit is not None and len(edges) >= limit * 5:
                break

        return JSONResponse(content={"nodes": nodes, "edges": edges})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


# Endpoint para gerar grafo com base na ligação entre propriedades do mesmo proprietário
@app.post("/process_owners_graph")
async def process_owners_graph(
    data: dict,
    limit: Optional[int] = Query(
        None, description="Limite para o número de nós e arestas"
    ),
):
    try:
        csv_data = data.get("data")
        df = parse_csv_data(csv_data)
        if df is None:
            return JSONResponse(
                content={"error": "Não foi possível determinar o formato do CSV."},
                status_code=400,
            )

        required_columns = ["OWNER", "OBJECTID"]
        if not all(col in df.columns for col in required_columns):
            return JSONResponse(
                content={
                    "error": f"O CSV deve conter as colunas: {', '.join(required_columns)} para o grafo de proprietários."
                },
                status_code=400,
            )

        # Agrupamento de propriedades por proprietário
        properties_by_owner = defaultdict(list)
        for index, row in df.iterrows():
            owner = row["OWNER"]
            prop_id = str(row["OBJECTID"])
            properties_by_owner[owner].append(prop_id)
            if limit is not None and index >= limit:
                break

        # Criação dos nós (propriedades)
        nodes = []
        for index, row in df.iterrows():
            prop_id = str(row["OBJECTID"])
            nodes.append(
                {
                    "id": prop_id,
                    "label": f"Propriedade {prop_id}",
                    "title": f"ID: {prop_id}<br>Proprietário: {row['OWNER']}",
                }
            )
            if limit is not None and len(nodes) >= limit:
                break

        # Criação das arestas entre propriedades do mesmo dono
        edges = []
        processed_edges = set()
        for owner, prop_list in properties_by_owner.items():
            for i in range(len(prop_list)):
                for j in range(i + 1, len(prop_list)):
                    prop1_id = prop_list[i]
                    prop2_id = prop_list[j]
                    sorted_edge = tuple(sorted((prop1_id, prop2_id)))
                    if sorted_edge not in processed_edges:
                        edges.append({"from": prop1_id, "to": prop2_id})
                        processed_edges.add(sorted_edge)
                        if limit is not None and len(edges) >= limit * 5:
                            break
                if limit is not None and len(edges) >= limit * 5:
                    break

        return JSONResponse(content={"nodes": nodes, "edges": edges})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


# FEATURE 4: Permita calcular a área média das propriedades, de uma área geográfica/administrativa indicada pelo utilizador
# (freguesia, concelho, distrito);
@app.get("/average_area")
async def get_average_area(
    level: str = Query(..., regex="^(Freguesia|Concelho|Distrito)$"),
    name: str = Query(...),
):
    global df_properties
    if df_properties is None:
        raise HTTPException(400, "Dados de propriedades não carregados.")

    if level not in df_properties.columns:
        raise HTTPException(400, f"Coluna '{level}' não existe nos dados.")

    df_filtro = df_properties[df_properties[level] == name]
    if df_filtro.empty:
        raise HTTPException(404, f"Nenhuma propriedade para {level} = '{name}'.")

    if "Shape_Area" in df_filtro.columns:
        arr = df_filtro["Shape_Area"].dropna().astype(float)
        if arr.empty:
            raise HTTPException(500, "Shape_Area está vazio ou inválido.")
        mean_area = float(arr.mean())
        count = int(arr.count())
    else:
        areas = []
        for _, row in df_filtro.iterrows():
            geom_proj = project_geometry(row["geometry"])
            if geom_proj and not geom_proj.is_empty:
                a = geom_proj.area
                if a == a and abs(a) < 1e30:
                    areas.append(a)
        if not areas:
            raise HTTPException(500, "Não foi possível calcular áreas geométricas.")
        mean_area = float(sum(areas) / len(areas))
        count = len(areas)

    return {
        "level": level,
        "name": name,
        "mean_area_m2": mean_area,
        "unit": "m²",
        "count": count,
    }


# FEATURE 5: Permita calcular a área média das propriedades, assumindo que propriedades adjacentes, do mesmo proprietário,
# devem ser consideradas como uma única propriedade, para uma área geográfica/administrativa indicada pelo utilizador;

@app.get("/average_area_grouped")
async def get_average_area_grouped(
    level: str = Query(..., regex="^(Freguesia|Concelho|Distrito)$"),
    name: str = Query(...),
):
    global df_properties
    if df_properties is None:
        raise HTTPException(400, "Dados de propriedades não carregados.")
    if level not in df_properties.columns:
        raise HTTPException(400, f"Coluna '{level}' não existe.")

    df_filtro = df_properties[df_properties[level] == name]
    if df_filtro.empty:
        raise HTTPException(404, f"Nenhuma propriedade para {level} = '{name}'.")

    # Usa Shape_Area para agrupar por OWNER
    if "Shape_Area" in df_filtro.columns:
        # soma a área de cada proprietário
        series = df_filtro.groupby("OWNER")["Shape_Area"].sum().dropna().astype(float)
        if series.empty:
            raise HTTPException(500, "Shape_Area inválido ou vazio.")
        areas = series.tolist()
    else:
        # fallback geométrico: projeta + junta tudo de cada owner
        from shapely.ops import unary_union

        owner_groups = df_filtro.groupby("OWNER")["geometry"]
        areas = []
        for wkt_list in owner_groups:
            geoms = [
                g
                for g in (project_geometry(w) for w in wkt_list[1].dropna())
                if g and not g.is_empty
            ]
            if not geoms:
                continue
            merged = unary_union(geoms)
            # se devolve GeometryCollection, extrai polígonos
            comps = (
                [merged]
                if merged.geom_type.startswith("Polygon")
                else list(merged.geoms)
            )
            for poly in comps:
                a = poly.area
                if a == a and abs(a) < 1e30:
                    areas.append(a)

        if not areas:
            raise HTTPException(
                500, "Não foi possível calcular áreas geométricas agrupadas."
            )

    mean_area = float(sum(areas) / len(areas))
    return {
        "level": level,
        "name": name,
        "mean_area_m2": mean_area,
        "unit": "m²",
        "count": len(areas),
    }


# Definir as características a considerar para a similaridade (além da área)
CARACTERISTICAS_SIMILARIDADE = ["Shape_Area", "Valor_Estimado", "Distancia_Vias", "Distancia_Urbana"]
PESOS_SIMILARIDADE = {
    "Shape_Area": 0.4,  # Peso para a área
    "Valor_Estimado": 0.3, # Peso para o valor estimado
    "Distancia_Vias": 0.15, # Peso para a distância a vias
    "Distancia_Urbana": 0.15 # Peso para a distância a zonas urbanas
}


def calcular_similaridade(prop1, prop2, caracteristicas, pesos):
    """Calcula um score de similaridade entre duas propriedades com base nas características e pesos fornecidos."""
    score = 0
    total_peso = 0

    for carac in caracteristicas:
        if carac in prop1 and carac in prop2 and pd.notna(prop1[carac]) and pd.notna(prop2[carac]) and carac in pesos:
            peso = pesos[carac]
            total_peso += peso
            val1 = prop1[carac]
            val2 = prop2[carac]

            if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                # Normalizar a diferença (quanto menor a diferença, maior a similaridade)
                max_val = max(abs(val1), abs(val2), 1) # Evitar divisão por zero
                diff_normalizada = abs(val1 - val2) / max_val
                similaridade_carac = 1 - diff_normalizada
                score += peso * similaridade_carac
            elif isinstance(val1, str) and isinstance(val2, str):
                # Similaridade binária para strings (igual ou diferente)
                if val1.lower() == val2.lower():
                    score += peso * 1
                else:
                    score += peso * 0

    return score / total_peso if total_peso > 0 else 0


@app.get("/suggest_trades")
async def suggest_trades(
    level: str = Query(..., regex="^(Freguesia|Concelho|Distrito)$"),
    name: str = Query(...),
    top: int = Query(5, ge=1),
):
    global df_properties
    if df_properties is None:
        raise HTTPException(400, "Dados não carregados.")
    if level not in df_properties.columns:
        raise HTTPException(400, f"Coluna '{level}' não existe.")

    # filtra pela área indicada
    df = df_properties[df_properties[level] == name]
    if df.empty:
        raise HTTPException(404, "Sem propriedades nessa área.")

    if "Shape_Area" not in df.columns:
        raise HTTPException(500, "É necessária coluna Shape_Area.")

    # agrupa por OWNER: lista de dicts com OBJECTID e todas as características
    owners_data = {
        owner: g.to_dict('records')
        for owner, g in df.groupby("OWNER")
        if len(g) > 0
    }
    if len(owners_data) < 2:
        raise HTTPException(404, "Menos de dois proprietários para trocar.")

    suggestions = []
    # para cada par de proprietários
    for o1, o2 in combinations(owners_data.keys(), 2):
        props1 = owners_data[o1]
        props2 = owners_data[o2]
        # cada possível troca de uma propriedade
        for prop1 in props1:
            for prop2 in props2:
                id1 = prop1['OBJECTID']
                a1 = prop1['Shape_Area']
                id2 = prop2['OBJECTID']
                a2 = prop2['Shape_Area']

                # Calcular a área total atual para cada proprietário (agrupada)
                sum1 = sum(p['Shape_Area'] for p in props1)
                sum2 = sum(p['Shape_Area'] for p in props2)
                cnt1 = len(props1)
                cnt2 = len(props2)

                # Calcular a área média após a troca
                new_avg1 = (sum1 - a1 + a2) / cnt1 if cnt1 > 0 else 0
                new_avg2 = (sum2 - a2 + a1) / cnt2 if cnt2 > 0 else 0
                delta = (new_avg1 - sum1 / cnt1 if cnt1 > 0 else 0) + (new_avg2 - sum2 / cnt2 if cnt2 > 0 else 0)
                area_diff = abs(a1 - a2)
                potential_area = delta / (area_diff + 1e-6)

                # Calcular a similaridade entre as propriedades
                similaridade = calcular_similaridade(prop1, prop2, CARACTERISTICAS_SIMILARIDADE, PESOS_SIMILARIDADE)

                # Combinar o potencial de área com a similaridade
                potential_score = potential_area * (1 + similaridade) # Ajuste a fórmula conforme necessário

                suggestions.append(
                    {
                        "owner1": o1,
                        "prop1": id1,
                        "area1": a1,
                        "owner2": o2,
                        "prop2": id2,
                        "area2": a2,
                        "delta_avg_total": delta,
                        "potential_score": potential_score,
                        "similaridade": similaridade, # Adicionado para possível visualização/debug
                    }
                )

    # ordena por potencial e devolve top N
    best = sorted(suggestions, key=lambda s: s["potential_score"], reverse=True)[:top]
    return {"level": level, "name": name, "suggestions": best}