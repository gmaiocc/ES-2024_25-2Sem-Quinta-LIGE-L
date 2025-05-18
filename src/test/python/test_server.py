import sys
import os
from fastapi.testclient import TestClient
import pytest
from shapely.wkt import dumps
from shapely.geometry import Polygon

# Adiciona o caminho src/main/python ao sys.path para permitir a importação do módulo 'server'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../main/python")))

# Importa a aplicação FastAPI do módulo 'server'
from server import app

# Cria uma instância do TestClient para simular requisições HTTP
client = TestClient(app)

# Dados de teste com geometrias WKT válidas
csv_example = """OBJECTID,OWNER,Freguesia,geometry,Shape_Area,Valor_Estimado,Distancia_Vias,Distancia_Urbana
1,João,Santo Tirso,"POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))",1000,100000,100,50
2,João,Santo Tirso,"POLYGON((1 0, 1 1, 2 1, 2 0, 1 0))",2000,200000,200,100
3,Ana,Gaia,"POLYGON((3 0, 3 1, 4 1, 4 0, 3 0))",1500,150000,150,75
4,Ana,Santo Tirso,"POLYGON((2 0, 2 1, 3 1, 3 0, 2 0))",2500,250000,250,125
"""

def test_process_properties_graph_success():
    """
    Testa o processamento bem-sucedido do grafo de propriedades.
    Verifica se:
    1. A resposta tem status 200
    2. Contém nós e arestas
    3. O número de nós corresponde ao CSV
    4. Existem arestas entre propriedades adjacentes
    """
    response = client.post("/process_properties_graph?limit=10", json={"data": csv_example})
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 4  # 4 propriedades no CSV
    assert len(data["edges"]) > 0  # Deve haver arestas entre propriedades adjacentes

def test_process_owners_graph_success():
    """
    Testa o processamento bem-sucedido do grafo de proprietários.
    Verifica se:
    1. A resposta tem status 200
    2. Contém nós e arestas
    3. O número de nós corresponde ao CSV
    4. Existem arestas entre propriedades do mesmo proprietário
    """
    response = client.post("/process_owners_graph?limit=10", json={"data": csv_example})
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 4
    # Deve haver arestas entre propriedades do mesmo proprietário
    assert len(data["edges"]) >= 2  # João tem 2 propriedades, Ana tem 2 propriedades

def test_get_property_details():
    """
    Testa a obtenção de detalhes de uma propriedade específica.
    Verifica se:
    1. A resposta tem status 200
    2. Contém informações corretas da propriedade
    3. Lista propriedades adjacentes
    """
    # Primeiro processa o grafo
    client.post("/process_properties_graph", json={"data": csv_example})
    # Depois busca detalhes
    response = client.get("/properties/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "1"
    assert data["owner"] == "João"
    assert data["freguesia"] == "Santo Tirso"
    assert isinstance(data["adjacent_properties"], list)

def test_get_average_area():
    """
    Testa o cálculo de área média para uma freguesia.
    Verifica se:
    1. A resposta tem status 200
    2. Contém área média correta
    3. Inclui contagem de propriedades
    """
    # Primeiro processa o grafo
    client.post("/process_properties_graph", json={"data": csv_example})
    # Depois calcula área média
    response = client.get("/average_area?level=Freguesia&name=Santo Tirso")
    assert response.status_code == 200
    data = response.json()
    assert "mean_area_m2" in data
    assert "count" in data
    assert data["count"] == 3  # 3 propriedades em Santo Tirso

def test_get_average_area_grouped():
    """
    Testa o cálculo de área média agrupada por proprietário.
    Verifica se:
    1. A resposta tem status 200
    2. Contém área média agrupada
    3. Inclui contagem de grupos
    """
    # Primeiro processa o grafo
    client.post("/process_properties_graph", json={"data": csv_example})
    # Depois calcula área média agrupada
    response = client.get("/average_area_grouped?level=Freguesia&name=Santo Tirso")
    assert response.status_code == 200
    data = response.json()
    assert "mean_area_m2" in data
    assert "count" in data
    assert data["count"] == 2  # 2 proprietários em Santo Tirso

def test_suggest_trades():
    """
    Testa a geração de sugestões de trocas.
    Verifica se:
    1. A resposta tem status 200
    2. Contém lista de sugestões
    3. Cada sugestão tem informações completas
    """
    # Primeiro processa o grafo
    client.post("/process_properties_graph", json={"data": csv_example})
    # Depois gera sugestões
    response = client.get("/suggest_trades?level=Freguesia&name=Santo Tirso&top=2")
    assert response.status_code == 200
    data = response.json()
    assert "suggestions" in data
    assert len(data["suggestions"]) <= 2  # Limitado a 2 sugestões
    if data["suggestions"]:
        suggestion = data["suggestions"][0]
        assert all(key in suggestion for key in [
            "owner1", "prop1", "area1",
            "owner2", "prop2", "area2",
            "delta_avg_total", "potential_score"
        ])

def test_invalid_csv_format():
    """
    Testa o comportamento com CSV inválido.
    Verifica se:
    1. A resposta tem status 400
    2. Contém mensagem de erro apropriada
    """
    invalid_csv = """ID,NOME,ZONA
1,Ana,Norte
2,Pedro,Sul"""
    response = client.post("/process_properties_graph", json={"data": invalid_csv})
    assert response.status_code == 400
    assert "error" in response.json()

def test_missing_required_columns():
    """
    Testa o comportamento quando colunas obrigatórias estão faltando.
    Verifica se:
    1. A resposta tem status 400
    2. Contém mensagem de erro específica sobre colunas faltantes
    """
    incomplete_csv = """OBJECTID,OWNER
1,João
2,Ana"""
    response = client.post("/process_properties_graph", json={"data": incomplete_csv})
    assert response.status_code == 400
    assert "error" in response.json()
    assert "colunas" in response.json()["error"].lower()

def test_invalid_area_level():
    """
    Testa o comportamento com nível de área inválido.
    Verifica se:
    1. A resposta tem status 422 (Unprocessable Entity)
    2. Contém mensagem de erro de validação
    """
    response = client.get("/average_area?level=InvalidLevel&name=Test")
    assert response.status_code == 422

def test_nonexistent_area():
    """
    Testa o comportamento com área geográfica inexistente.
    Verifica se:
    1. A resposta tem status 404
    2. Contém mensagem de erro apropriada
    """
    # Primeiro processa o grafo
    client.post("/process_properties_graph", json={"data": csv_example})
    # Depois tenta buscar área inexistente
    response = client.get("/average_area?level=Freguesia&name=Inexistente")
    assert response.status_code == 404
    json_response = response.json()
    assert "detail" in json_response
    assert json_response["detail"] == "Nenhuma propriedade encontrada para Freguesia='Inexistente'."


