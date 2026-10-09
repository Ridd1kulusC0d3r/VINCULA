# VINCULA 2.0 — Relatório de testes em nuvem

**Data:** 08/10/2026 · **Ambiente:** Python 3.13, Chromium headless (Playwright), stix2 3.0.2, Linux (nuvem)

## Resumo
| Suíte | Resultado |
|---|---|
| Testes unitários (`python -m unittest tests.test_vincula`) | 36/36 OK |
| Python 3.11 / 3.12 / 3.13 | OK / OK / OK |
| Sintaxe compatível com Python 3.8 (ast) | OK |
| Navegador ponta a ponta (`python tests/e2e_navegador.py`) | 28/28 OK (3 execuções) |
| Paridade Python ↔ JavaScript (grupos, intermediação, cruzamentos, caminho) | OK |
| Selo de integridade (Python e navegador; detecta adulteração) | OK |
| STIX 2.1 validado com `stix2` (86 objetos no demo) | OK |
| Lançador Linux com e sem Python | OK |
| Caso demo (`python vincula.py demo`) | 25 entidades · 60 vínculos · 6 cruzamentos (gabarito) |

## Verificações no navegador
- ✔ bancada abre com aba Importar
- ✔ mapa vazio mostra orientacao
- ✔ demo: 25 entidades, 60 vinculos, 6 cruzamentos
- ✔ selo integro
- ✔ abas Alertas/Analise/Tempo
- ✔ alertas listados
- ✔ barra de tempo visivel
- ✔ paridade comunidades
- ✔ paridade intermediacao
- ✔ paridade cruzamentos
- ✔ paridade caminho
- ✔ grupos desenham contornos
- ✔ painel de grupos
- ✔ caminho mostrado no painel
- ✔ pivos OSINT com links
- ✔ busca seleciona
- ✔ linha do tempo filtra e restaura
- ✔ mascara ligada por padrao
- ✔ excluir muda selo para editado
- ✔ desfazer restaura selo
- ✔ exporta stix
- ✔ exporta graphml
- ✔ exporta csv
- ✔ exporta mermaid
- ✔ exporta json
- ✔ relatorio com resumo e selo
- ✔ mapa salvo reabre offline com 25 nos
- ✔ sem erros JS

## O que NÃO foi testado (limites honestos)
- Windows e macOS reais: `INICIAR-Windows.bat` e `INICIAR-Mac.command` não foram executados nesses sistemas.
- Firefox, Safari e navegadores de celular (apenas Chromium).
- Links de pivô OSINT (Google, Jusbrasil, BrasilAPI, Wayback, WhatsApp, WHOIS…) foram montados por padrão de URL e não abertos contra os sites reais.
- Busca por URL na internet aberta: testada só contra servidor local.
- Precisão em reportagens, CDR e agendas reais: os dados de teste são sintéticos.
- Mapas muito grandes (milhares de nós): sem teste de desempenho.

---
## Atualização 2.1 (2026-10-09)
- Unitários + cenários: **51/51** (`python -m unittest discover -s tests`), incluindo gabaritos dos casos 02–06 e demo, selo/adulteração, exportações válidas, formatos de CSV, entradas malformadas e guarda de desempenho.
- E2E no navegador (Chromium/Playwright): **28/28**; mapa de 1805 nós carrega em ~1,9 s com paridade Py×JS.
- Fuzz de 25 entradas malformadas: sem travamentos nem exceções não tratadas.
- Limite: testado em ambiente Linux em nuvem; Windows/macOS não foram executados aqui (launchers são scripts simples).
