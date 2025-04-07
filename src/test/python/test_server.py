import sys
import os
from fastapi.testclient import TestClient

# Adiciona o caminho src/main/python ao sys.path para permitir a importação do módulo 'server'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../main/python")))

# Importa a aplicação FastAPI do módulo 'server'
from server import app

# Cria uma instância do TestClient, que é usada para simular requisições HTTP à API
client = TestClient(app)

# Exemplo de dados CSV que será usado nos testes
csv_example = """OBJECTID,OWNER,Freguesia,Municipio
1,João,Santo Tirso,Porto
2,João,Santo Tirso,Porto
3,Ana,Gaia,Porto
"""


# Função de teste para verificar se o processo de criação do grafo ocorre com sucesso
def test_process_graph_success():
    # Envia uma requisição POST para a rota '/process_graph' com o CSV exemplo e um limite de 10
    response = client.post("/process_graph?limit=10", json={"data": csv_example})

    # Verifica se o código de status da resposta é 200 (OK)
    assert response.status_code == 200

    # Obtém a resposta no formato JSON
    json_data = response.json()

    # Verifica se os dados de resposta contêm os campos 'nodes' e 'edges'
    assert "nodes" in json_data
    assert "edges" in json_data

    # Verifica se o número de nós é igual a 3 (esperado, pois temos 3 propriedades no exemplo)
    assert len(json_data["nodes"]) == 3

    # Verifica se o número de arestas é pelo menos 1 (deve haver pelo menos uma aresta entre propriedades com o mesmo proprietário e freguesia)
    assert len(json_data["edges"]) >= 1


# Função de teste para verificar o comportamento quando as colunas obrigatórias estão ausentes
def test_missing_columns():
    # Exemplo de CSV inválido, com colunas diferentes das esperadas
    csv_invalido = """ID,NOME,ZONA
1,Ana,Norte
2,Pedro,Sul"""

    # Envia uma requisição POST para a rota '/process_graph' com o CSV inválido
    response = client.post("/process_graph", json={"data": csv_invalido})

    # Verifica se o código de status da resposta é 400 (Bad Request), indicando que houve um erro na validação dos dados
    assert response.status_code == 400

    # Verifica se a resposta contém um campo de erro
    assert "error" in response.json()
