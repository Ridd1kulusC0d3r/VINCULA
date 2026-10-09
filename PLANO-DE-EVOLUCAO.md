# VINCULA — Planos de evolução

Princípio: **Python simples, stdlib por padrão**; qualquer dependência é opcional e o programa continua funcionando sem ela. Cada item tem *critério de pronto* verificável por teste.

## Onde estamos (2.1)
Extração por regras → grafo com classes de evidência → análises (comunidades, intermediação, caminho, sobreposição, contradições, tempo, celulares) → mapa HTML offline selado com SHA-256. 51 testes + 28 e2e.
**Dívidas conhecidas:** extração só por regras (frases complexas escapam); parentesco só com termos explícitos; sem persistência entre casos; sem carimbo de tempo externo; sem Windows/macOS testados em CI; manual ilustrado sem capturas novas da 2.1.

## Plano A — Robustez (2.2, curto prazo, 2–3 semanas)
| # | Entrega | Critério de pronto |
|---|---|---|
| A1 | CI em Windows e macOS (matriz `os`) | workflow verde nos 3 sistemas |
| A2 | Capturas e SVGs novos no manual (2.1) | seção 13 com imagens anotadas |
| A3 | Corpus de regressão: 30+ trechos reais *anonimizados* de reportagens com gabarito de entidades | `tests/corpus/` + métrica de precisão/revocação impressa pelo teste |
| A4 | Limites e mensagens: tamanho máx. de arquivo, encoding (utf-8/latin-1 autodetecção) | CSV em latin-1 abre sem erro |
| A5 | Teste de propriedades (aleatório com semente): extrair→exportar→reimportar mantém o grafo | 1.000 casos aleatórios sem divergência |
| A6 | `vincula.py validar mapa.html` (selo + esquema) para auditor externo | exit code 0/1 documentado |

## Plano B — Profundidade analítica (2.3–2.5, médio prazo)
1. **Resolução de entidades de verdade:** *blocking* + pontuação (nome, documento, endereço, telefone) com limiar ajustável e fila de revisão; fonética pt-BR própria (stdlib) para "Jhonatan/Jonatã". *Pronto:* F1 ≥ 0,9 no corpus A3.
2. **Tempo como cidadão de primeira classe:** vínculos com início/fim, "linha do tempo de controle societário", detecção de *troca de laranja* (sócio sai e entra parente em janela curta). *Pronto:* caso novo 07 com gabarito.
3. **Persistência:** SQLite (`sqlite3`, stdlib) para vários casos, histórico de revisões e "quem aprovou a fusão". *Pronto:* reabrir caso mantém decisões.
4. **Confiança calibrada:** cada alerta com explicação auditável ("por que apareceu": quais vínculos e fontes). *Pronto:* botão "explicar" no mapa e no CLI.
5. **Comparar casos/versões (diff de grafos):** o que mudou entre dois mapas selados. *Pronto:* `vincula.py comparar a.html b.html`.
6. **Modo equipe sem servidor:** pacote `.vincula` (zip com caso + selo + cadeia) para trocar entre analistas.

## Plano C — Inovações OSINT (pesquisa; ligar com RBI/Tratado)
Cada uma vira experimento curto com hipótese, dado e métrica.
- **Cadeia de custódia com carimbo externo:** ancorar o selo SHA-256 em OpenTimestamps (opcional) → prova de que o mapa existia em dada data. (Conecta com PASSEltr.)
- **Dados abertos BR em lote, offline:** importar dumps públicos (quadro societário da Receita, candidatos/doadores do TSE, contratos no PNCP, sanções do Portal da Transparência) para cruzar com o caso sem consultar nada online — reduz pegada e melhora reprodutibilidade. *Verifique a licença e o layout de cada base antes de implementar.*
- **Validação oficial de documentos:** `python-stdnum` (opcional) para CPF/CNPJ/IE além do dígito verificador atual.
- **Telefonia:** `phonenumbers` (opcional) para operadora/região e portabilidade provável; hoje usamos E.164 + DDD.
- **Similaridade textual escalável:** `rapidfuzz` (opcional) no lugar de `difflib` quando passar de ~10 mil entidades.
- **Grafos grandes:** `networkx` (opcional) apenas como *oráculo de teste* da nossa implementação (comparar centralidade), mantendo o produto stdlib.
- **Assinatura estilística / coordenação:** detectar textos de reportagens/posts reaproveitados (shingling + Jaccard, stdlib) como indício de campanha coordenada. (Conecta com MOSAIV.)
- **Hipóteses concorrentes:** em vez de um alerta, listar explicações alternativas (acaso, relação legítima, fraude) com o que refutaria cada uma — redução de viés de confirmação (ângulo Camada 8).
- **Paper:** "Vínculos auditáveis a partir de fontes abertas: classes de evidência, contradição entre fontes e selo de integridade" — usar o corpus A3 e os casos 02–06 como estudo.

## Plano D — Produto e adoção
- Empacotar: `pipx install vincula` (pyproject, sem dependências) e executável único (zipapp `python -m zipapp`) para leigos.
- Tradução EN do manual e dos alertas (internacionalização por dicionário).
- Release no GitHub com zip, hashes SHA-256 e notas (CHANGELOG).
- Licença: **decidir** (MIT/Apache-2.0 para abrir; ou proprietária se for ativo da Clavis). Hoje o repositório não tem LICENSE.
- Trilha de treino: transformar os casos 02–06 em desafios graduados (D→S) no formato do OSINT no Jutsu.

## Roteiro sugerido
| Janela | Foco | Entregas |
|---|---|---|
| Semanas 1–3 | A1–A6 | 2.2 com CI 3 SOs, corpus, manual atualizado |
| Mês 2 | B1 + B4 | resolução de entidades e "explicar alerta" |
| Mês 3 | B2 + B3 | tempo e persistência; caso 07 |
| Mês 4 | C (2 experimentos) | OpenTimestamps + dumps abertos; rascunho de artigo |
| Mês 5–6 | D | pacote, release, licença, EN |

## Riscos
- **Falso positivo vira acusação:** manter linguagem de "indício", explicações e fila de revisão.
- **LGPD:** dados reais só localmente; casos do repo sempre sintéticos.
- **Escopo:** cada versão só sai com critério de pronto testado.
