# Changelog

## 2.1
- Novo comando `diagnostico` (autoteste do ambiente e do caso demo) e `caso <pasta>` (caso.json).
- Parentesco ("cunhada de X") vira vínculo Declarado e alerta de nepotismo.
- Cruzamentos agrupam partes independentes (pessoa + própria empresa não conta duas vezes).
- Desempenho: resolução de nomes indexada, intermediação exata ≤800 nós e amostrada acima, Dijkstra com heap, sobreposição por índice invertido; JS e Python com paridade verificada.
- `importar_oficial` aceita dois formatos de CSV e erros citam a linha.
- Casos de treino 02–06 com gabarito; `tests/test_cenarios.py`; guia prático `GUIA-PRATICO.md`; CI no GitHub Actions.
- Correção: vizinhos co-citados em lista não formam mais cliques artificiais de "sobreposição".

## 2.0
Primeira versão completa (mapa interativo, selo SHA-256, STIX/GraphML/CSV/Mermaid, celulares).
