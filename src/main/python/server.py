# Resumo:
# Este módulo implementa uma API REST usando FastAPI para processar dados de propriedades geoespaciais.
# Funcionalidades principais:
# 1. Carregamento e parsing de CSVs com separadores variados.
# 2. Projeção de geometrias WKT de WGS84 para UTM.
# 3. Construção de grafos de adjacência espacial e de propriedade.
# 4. Cálculo de área média simples e agrupada por proprietário.
# 5. Geração de sugestões de trocas de propriedades com base em área média e similaridade de características.

from functools import partial  # Para criar funções parciais na projeção de coordenadas
from fastapi import (
    FastAPI,
    Query,
    HTTPException,
)  # Framework para API e validação de parâmetros
from fastapi.responses import JSONResponse  # Para retornos JSON customizados
from fastapi.middleware.cors import CORSMiddleware  # Middleware para CORS
import pandas as pd  # Manipulação de dados em DataFrame
from io import StringIO  # Leitura de strings como arquivos
from collections import defaultdict  # Dicionário com lista padrão
from typing import Optional  # Anotações de tipo opcionais
from shapely.wkt import loads  # Converte WKT em objeto Shapely
from shapely.ops import transform  # Transforma geometrias
import pyproj  # Para re-projeção de coordenadas
from itertools import combinations  # Para pares de itens em iteráveis

# Criação da aplicação FastAPI
app = FastAPI()

# Middleware para permitir chamadas de qualquer origem (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite qualquer origem
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos os métodos HTTP
    allow_headers=["*"],  # Permite todos os headers
)

# Variáveis globais para guardar os dados carregados
df_properties = None  # DataFrame global para propriedades
property_adjacency_list = defaultdict(
    list
)  # Grafo de adjacência: {OBJECTID: [vizinhos]}

# --- Funções auxiliares ---


def parse_csv_data(csv_data: str):
    """
    Tenta ler um CSV com diferentes separadores (";", ",", "\t").
    Retorna DataFrame se sucesso ou None caso falhe.
    """
    separadores_possiveis = [";", ",", "\t"]
    for sep in separadores_possiveis:
        try:
            df = pd.read_csv(StringIO(csv_data), sep=sep, skipinitialspace=True)
            # Se leu mais de uma coluna, considera válido
            if df.shape[1] > 1:
                return df
        except pd.errors.ParserError:
            continue
    return None


def project_geometry(geom_wkt: str, src_crs="EPSG:4326", target_crs="EPSG:32628"):
    """
    Projeta geometria WKT de um CRS fonte para um CRS alvo (ex: WGS84 -> UTM).
    Retorna objeto Shapely transformado ou None em caso de erro.
    """
    try:
        geom = loads(geom_wkt)  # Carrega WKT
        if geom.is_empty:
            return None
        # Cria função de projeção parcial
        project = partial(
            pyproj.transform, pyproj.Proj(src_crs), pyproj.Proj(target_crs)
        )
        # Aplica transformação
        return transform(project, geom)
    except Exception as e:
        print(f"Erro ao projetar geometria: {e}")
        return None


def check_adjacency(geom1, geom2):
    """
    Verifica se duas geometrias são adjacentes (tocam ou intersectam).
    Retorna True se adjacentes, False caso contrário.
    """
    if geom1 is None or geom2 is None:
        return False
    return geom1.touches(geom2) or geom1.intersects(geom2)


# --- Endpoints ---


@app.get("/properties/{objectid}")
async def get_property_details(objectid: str):
    """
    Retorna detalhes de uma propriedade pelo OBJECTID,
    incluindo proprietário, freguesia e IDs de propriedades adjacentes.
    """
    global df_properties, property_adjacency_list
    if df_properties is None:
        return JSONResponse(
            content={"error": "Os dados das propriedades não foram carregados."},
            status_code=400,
        )
    try:
        # Filtra DataFrame pelo ID
        prop_row = df_properties[
            df_properties["OBJECTID"].astype(str) == objectid
        ].iloc[0]
        owner = prop_row.get("OWNER")
        freguesia = prop_row.get("Freguesia")
        # Recupera vizinhos do grafo
        adj = property_adjacency_list.get(objectid, [])
        return JSONResponse(
            content={
                "id": objectid,
                "owner": str(owner) if pd.notna(owner) else None,
                "freguesia": str(freguesia) if pd.notna(freguesia) else None,
                "adjacent_properties": [str(pid) for pid in adj],
            }
        )
    except Exception:
        return JSONResponse(
            content={"error": f"Propriedade com ID {objectid} não encontrada."},
            status_code=404,
        )


@app.post("/process_properties_graph")
async def process_properties_graph(
    data: dict,
    limit: Optional[int] = Query(None, description="Limite para o número de nós"),
):
    """
    Constrói grafo de adjacência espacial entre propriedades.
    Recebe CSV, parseia, projeta geometrias e gera nós e arestas.
    """
    global df_properties, property_adjacency_list
    csv_data = data.get("data")
    df = parse_csv_data(csv_data)
    if df is None:
        return JSONResponse(
            content={"error": "Não foi possível determinar o formato do CSV."},
            status_code=400,
        )
    # Atualiza DataFrame global e limpa grafo
    df_properties = df
    property_adjacency_list.clear()
    # Verifica colunas essenciais
    required_cols = ["OBJECTID", "geometry", "OWNER", "Freguesia"]
    if not all(col in df.columns for col in required_cols):
        return JSONResponse(
            content={
                "error": f"O CSV deve conter colunas: {', '.join(required_cols)}."
            },
            status_code=400,
        )
    # Prepara nós
    nodes = []
    geom_map = {}
    for idx, row in df.iterrows():
        pid = str(row["OBJECTID"])
        nodes.append({"id": pid, "label": f"Propriedade {pid}", "title": f"ID: {pid}"})
        geom_map[pid] = row["geometry"]
        if limit and len(nodes) >= limit:
            break
    # Projeta geometrias uma vez
    proj_geoms = {pid: project_geometry(wkt) for pid, wkt in geom_map.items()}
    # Gera arestas
    edges = []
    seen = set()
    pids = list(proj_geoms.keys())
    for i in range(len(pids)):
        for j in range(i + 1, len(pids)):
            pair = tuple(sorted((pids[i], pids[j])))
            if pair in seen:
                continue
            seen.add(pair)
            if check_adjacency(proj_geoms[pids[i]], proj_geoms[pids[j]]):
                edges.append({"from": pids[i], "to": pids[j]})
                property_adjacency_list[pids[i]].append(pids[j])
                property_adjacency_list[pids[j]].append(pids[i])
            if limit and len(edges) >= limit * 5:
                break
        if limit and len(edges) >= limit * 5:
            break
    return JSONResponse(content={"nodes": nodes, "edges": edges})


@app.post("/process_owners_graph")
async def process_owners_graph(
    data: dict,
    limit: Optional[int] = Query(None, description="Limite para nós e arestas"),
):
    """
    Constrói grafo ligando propriedades pelo mesmo OWNER.
    Cada nó é uma parcela, arestas ligam parcelas de mesmo dono.
    """
    csv_data = data.get("data")
    df = parse_csv_data(csv_data)
    if df is None:
        return JSONResponse(
            content={"error": "Formato do CSV indefinido."}, status_code=400
        )
    # Verifica colunas
    if not all(col in df.columns for col in ["OWNER", "OBJECTID"]):
        return JSONResponse(
            content={"error": "CSV deve conter OWNER e OBJECTID."},
            status_code=400,
        )
    # Agrupa IDs por OWNER
    props_by_owner = defaultdict(list)
    for idx, row in df.iterrows():
        props_by_owner[row["OWNER"]].append(str(row["OBJECTID"]))
        if limit and idx >= limit:
            break
    # Cria nós
    nodes = [
        {"id": str(r["OBJECTID"]), "label": f"Propriedade {r['OBJECTID']}"}
        for _, r in df.iterrows()
    ][:limit]
    # Cria arestas entre IDs do mesmo dono
    edges = []
    used = set()
    for owner, plist in props_by_owner.items():
        for a, b in combinations(plist, 2):
            pair = tuple(sorted((a, b)))
            if pair not in used:
                edges.append({"from": pair[0], "to": pair[1]})
                used.add(pair)
                if limit and len(edges) >= limit * 5:
                    break
        if limit and len(edges) >= limit * 5:
            break
    return JSONResponse(content={"nodes": nodes, "edges": edges})


# FEATURE 4: Cálculo de área média simples
@app.get("/average_area")
async def get_average_area(
    level: str = Query(..., regex="^(Freguesia|Concelho|Distrito)$"),
    name: str = Query(...),
):
    """
    Retorna a área média (m²) das propriedades em uma área geográfica dada.
    """
    global df_properties
    if df_properties is None:
        raise HTTPException(400, "Dados de propriedades não carregados.")
    # Valida coluna de filtragem
    if level not in df_properties.columns:
        raise HTTPException(400, f"Coluna '{level}' não existe.")
    df_filt = df_properties[df_properties[level] == name]
    if df_filt.empty:
        raise HTTPException(
            404, f"Nenhuma propriedade encontrada para {level}='{name}'."
        )
    # Se Shape_Area existe, usa diretamente
    if "Shape_Area" in df_filt.columns:
        arr = df_filt["Shape_Area"].dropna().astype(float)
        mean_area = float(arr.mean())
        count = int(arr.count())
    else:
        # Caso não, projeta e calcula área geométrica
        areas = []
        for _, r in df_filt.iterrows():
            geom = project_geometry(r["geometry"])
            if geom and not geom.is_empty:
                areas.append(geom.area)
        mean_area = float(sum(areas) / len(areas))
        count = len(areas)
    return {
        "level": level,
        "name": name,
        "mean_area_m2": mean_area,
        "unit": "m²",
        "count": count,
    }


# FEATURE 5: Cálculo de área média agrupada por proprietário
@app.get("/average_area_grouped")
async def get_average_area_grouped(
    level: str = Query(..., regex="^(Freguesia|Concelho|Distrito)$"),
    name: str = Query(...),
):
    """
    Calcula a área média considerando propriedades adjacentes do mesmo proprietário como uma única unidade.
    """
    global df_properties
    if df_properties is None:
        raise HTTPException(400, "Dados não carregados.")
    df_filt = df_properties[df_properties[level] == name]
    # Usa Shape_Area agrupada se disponível
    if "Shape_Area" in df_filt.columns:
        series = df_filt.groupby("OWNER")["Shape_Area"].sum()
        areas = series.tolist()
    else:
        # Fallback: projeta geometrias e une por OWNER
        from shapely.ops import unary_union

        areas = []
        for owner, group in df_filt.groupby("OWNER"):
            geoms = [project_geometry(w) for w in group["geometry"].dropna()]
            merged = unary_union([g for g in geoms if g and not g.is_empty])
            if hasattr(merged, "geoms"):
                polys = list(merged.geoms)
            else:
                polys = [merged]
            areas.extend([p.area for p in polys])
    mean_area = float(sum(areas) / len(areas))
    return {
        "level": level,
        "name": name,
        "mean_area_m2": mean_area,
        "unit": "m²",
        "count": len(areas),
    }


# Configurações de similaridade para sugestões de trocas
CARACTERISTICAS_SIMILARIDADE = [
    "Shape_Area",
    "Valor_Estimado",
    "Distancia_Vias",
    "Distancia_Urbana",
]
PESOS_SIMILARIDADE = {
    "Shape_Area": 0.4,
    "Valor_Estimado": 0.3,
    "Distancia_Vias": 0.15,
    "Distancia_Urbana": 0.15,
}


def calcular_similaridade(prop1, prop2, caracteristicas, pesos):
    """
    Calcula similaridade entre duas propriedades com base em múltiplas características e pesos.
    """
    score, total_peso = 0, 0
    for carac in caracteristicas:
        if (
            carac in prop1
            and carac in prop2
            and pd.notna(prop1[carac])
            and pd.notna(prop2[carac])
        ):
            peso = pesos.get(carac, 0)
            total_peso += peso
            v1, v2 = prop1[carac], prop2[carac]
            if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                diff = abs(v1 - v2) / max(abs(v1), abs(v2), 1)
                score += peso * (1 - diff)
            elif isinstance(v1, str) and isinstance(v2, str):
                score += peso * (1 if v1.lower() == v2.lower() else 0)
    return score / total_peso if total_peso > 0 else 0


@app.get("/suggest_trades")
async def suggest_trades(
    level: str = Query(..., regex="^(Freguesia|Concelho|Distrito)$"),
    name: str = Query(...),
    top: int = Query(5, ge=1),
):
    """
    Gera as melhores sugestões de trocas entre propriedades para maximizar área média e similaridade.
    """
    global df_properties
    if df_properties is None:
        raise HTTPException(400, "Dados não carregados.")
    df = df_properties[df_properties[level] == name]
    owners = {o: g.to_dict("records") for o, g in df.groupby("OWNER")}
    if len(owners) < 2:
        raise HTTPException(404, "Menos de dois proprietários.")
    suggestions = []
    for o1, o2 in combinations(owners, 2):
        for p1 in owners[o1]:
            for p2 in owners[o2]:
                a1, a2 = p1["Shape_Area"], p2["Shape_Area"]
                sum1, sum2 = len(owners[o1]), len(owners[o2])
                # Cálculo de ganho de área média
                new_avg_gain = (
                    sum(p["Shape_Area"] for p in owners[o1]) - a1 + a2
                ) / sum1 + (sum(p["Shape_Area"] for p in owners[o2]) - a2 + a1) / sum2
                area_diff = abs(a1 - a2)
                potencia = new_avg_gain / (area_diff + 1e-6)
                sim = calcular_similaridade(
                    p1, p2, CARACTERISTICAS_SIMILARIDADE, PESOS_SIMILARIDADE
                )
                score = potencia * (1 + sim)
                suggestions.append(
                    {
                        "owner1": o1,
                        "prop1": p1["OBJECTID"],
                        "owner2": o2,
                        "prop2": p2["OBJECTID"],
                        "score": score,
                    }
                )
    best = sorted(suggestions, key=lambda x: x["score"], reverse=True)[:top]
    return {"level": level, "name": name, "suggestions": best}
