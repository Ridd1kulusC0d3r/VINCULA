# VINCULA 2.1

Mapa de vínculos OSINT a partir de **reportagens, registros oficiais e celulares** (chamadas e agendas). Python puro (só biblioteca padrão), roda local, sem enviar dados a ninguém.

```
python vincula.py diagnostico      # confere se está tudo certo
python vincula.py                  # abre a bancada no navegador
python vincula.py demo             # caso demonstrativo (25 · 60 · 6)
python vincula.py caso casos/03-cartel-licitacao
```
Leigos: dois cliques em `INICIAR-Windows.bat`, `INICIAR-Mac.command` ou `INICIAR-Linux.sh` (veja `COMECE-AQUI.md` e `manual/manual.html`).

## Inovações
- **Classes de evidência** (Oficial > Declarado > Inferência) que pesam caminhos e alertas.
- **Selo SHA-256** com cadeia de hash: detecta edição do mapa, verificável em Python e no navegador.
- **Contradições entre fontes** (saída societária × "vigente", titular de telefone, endereços, documentos) e **sinais de tempo**.
- **Parentesco textual** → alerta de nepotismo; **homônimos nunca fundem sozinhos** (você aprova).
- **Celulares**: contatos em comum entre agendas, números sequenciais, apelidos no mesmo número, dispersão de DDD.
- Exporta **STIX 2.1**, GraphML, CSV, Mermaid; análise idêntica em Python e no mapa HTML offline.

## Treino e testes
`docs/GUIA-PRATICO.md` traz 8 exercícios com gabarito (`casos/`). `python -m unittest discover -s tests -v` roda 51 testes; `tests/e2e_navegador.py` (requer Playwright + Chromium) valida o mapa no navegador.

## Aviso
Alertas são indícios, não conclusões. Dados dos casos são sintéticos. Use apenas fontes abertas e respeite a LGPD. Sem licença definida — escolha uma antes de abrir o uso a terceiros.
