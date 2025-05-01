# ES-2024_25-2Sem-Quinta-LIGE-L

Gonçalo Maio Nº110750
Miguel Carvalhal Nº106191
Tomás Silva Nº111393

1. Carregar Dados:
Backend: recebe CSV (vários separadores), faz pd.read_csv, valida colunas mínimas e guarda num DataFrame global.
Front-end: <input type="file"> + FileReader → envia CSV a /process_properties_graph e /process_owners_graph.
---
2. Grafo de Propriedades (adjacência geométrica):
Backend: Converte cada WKT em objeto Shapely e reprojeta para UTM.
Para cada par de polígonos, testa touches/intersects.
Constrói nós (OBJECTID) e arestas (propriedades vizinhas) e preenche property_adjacency_list.
Front-end: botão “Criar Grafo de Propriedades” chama /process_properties_graph, recebe {nodes, edges}, desenha com Vis-Network.
---
3. Grafo de Proprietários (conexões por dono)
Backend: Agrupa OBJECTID por OWNER.
Gera nós para cada parcela e arestas ligando todas as parcelas do mesmo dono.
Front-end: botão “Criar Grafo de Proprietários” chama /process_owners_graph, obtém {nodes, edges} e desenha grafo.
---
4. Área Média Simples:
Backend: Filtra DataFrame por Freguesia/Concelho/Distrito.
Calcula média de Shape_Area (m²) — ou, se não existir, reprojeta WKT e usa geom.area.
Retorna { level, name, mean_area_m2, unit, count }.
Front-end: dropdown + input + botão “Área Média” chamam /average_area e mostram resultado no <div>.
---
5. Área Média Agrupada:
Backend:Filtra por Freguesia/Concelho/Distrito.
Para cada OWNER, percorre o grafo de adjacência (BFS) para juntar parcelas contíguas num “componente”.
Soma Shape_Area (ou usa Shapely+UTM/unary_union) para cada componente e calcula a média dessas áreas.
Devolve { level, name, mean_area_m2, unit, count }.
Front-end: botão “Área Média Agrupada” chama /average_area_grouped, recebe resposta e atualiza o mesmo <div> do cálculo simples.
