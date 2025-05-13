# ES-2024_25-2Sem-Quinta-LIGE-L

**Gonçalo Maio Nº110750**  
**Miguel Carvalhal Nº106191**  
**Tomás Silva Nº111393**

**demo** https://www.youtube.com/watch?v=Bcg2kWJBUEI

---
## 1. Carregar Dados

**Backend:**  
Recebe um CSV (com vários separadores), faz `pd.read_csv`, valida colunas mínimas e armazena num DataFrame global.

**Front-end:**  
Usa `<input type="file">` com `FileReader` para ler e enviar o CSV para os endpoints:
- `/process_properties_graph`
- `/process_owners_graph`

---
## 2. Grafo de Propriedades (adjacência geométrica)

**Backend:**  
Converte cada WKT em objeto Shapely e reprojeta para UTM.  
Para cada par de polígonos, testa `touches`/`intersects`.  
Constrói:
- Nós: `OBJECTID`
- Arestas: relações de vizinhança geométrica  
Popula `property_adjacency_list`.

**Front-end:**  
Botão “Criar Grafo de Propriedades” chama `/process_properties_graph`, recebe `{nodes, edges}` e desenha com **Vis-Network**.

---
## 3. Grafo de Proprietários (conexões por dono)

**Backend:**  
Agrupa `OBJECTID` por `OWNER`, gera nós e cria arestas ligando todas as parcelas do mesmo proprietário.

**Front-end:**  
Botão “Criar Grafo de Proprietários” chama `/process_owners_graph`, recebe `{nodes, edges}` e desenha com Vis-Network.

---
## 4. Área Média Simples

**Backend:**  
Filtra o DataFrame por `Freguesia`, `Concelho` ou `Distrito`.  
Calcula média de `Shape_Area` (m²). Se não existir, reprojeta `WKT` e usa `geom.area`.

Retorna:
```json
{ "level": ..., "name": ..., "mean_area_m2": ..., "unit": "m2", "count": ... }
```

**Front-end:**  
Dropdown + input + botão “Área Média” → chama `/average_area` → exibe no `<div>`.

---
## 5. Área Média Agrupada

**Backend:**  
Filtra por `Freguesia`, `Concelho` ou `Distrito`.  
Para cada `OWNER`, usa BFS no grafo de adjacência para encontrar componentes (parcelas contíguas).  
Calcula soma de `Shape_Area` para cada grupo e retorna a média entre os componentes.

**Front-end:**  
Botão “Área Média Agrupada” chama `/average_area_grouped` e atualiza o mesmo `<div>` com o resultado.

---
## 6. Troca de Propriedades

**Backend:**  
Filtra o DataFrame por área (`Freguesia`, `Concelho` ou `Distrito`).  
Agrupa parcelas por `OWNER`.  
Para cada par de donos e para cada par de parcelas entre eles:

- Simula troca de parcelas.
- Recalcula as novas médias de área de cada dono.
- Calcula o ganho na soma dessas médias.
- Avalia a **diferença de área** entre as parcelas trocadas.
- Define a pontuação de potencial:
  
  ```
  potencial = ganho_total / (diferença_area + ε)
  ```

Este método favorece trocas entre parcelas de área próxima, assumindo menor custo e maior viabilidade de execução.

**Front-end:**  
Adiciona um campo “Top N sugestões” e botão “Sugestões de Trocas”.  
Chama:

```
/suggest_trades?level=...&name=...&top=N
```

Renderiza uma lista `<ul>` com as sugestões, mostrando:
- Proprietários
- IDs das parcelas
- Áreas
- Ganho de média
- Potencial da troca

---
## 7. Troca entre Propriedades com Características Similares

**Backend:**  
Além da área, são consideradas outras características no cálculo da **similaridade entre propriedades**:

- `Valor_Estimado`
- `Distancia_Vias`
- `Distancia_Urbana`

Cada característica possui um peso configurável.  
A similaridade é calculada como:

- **Numérica:** `1 - (|v1 - v2| / max(|v1|, |v2|, 1))`
- **Textual:** 1 se iguais, 0 se diferentes (case insensitive)

O score final de troca é ajustado considerando a similaridade:

```python
potential_score = ganho_area * (1 + similaridade)
```

Ou seja, quanto mais parecidas as propriedades, maior o score e a chance de sugestão.

**Front-end:**  
A lista de sugestões exibe também o índice de similaridade entre as parcelas.  
Nada muda na interação do usuário, apenas o critério interno se torna mais robusto e realista.
