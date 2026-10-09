# VINCULA 2.1 — comece aqui

Mapa de vínculos OSINT que **pensa**: você entrega reportagens, registros oficiais, um registro de chamadas
e/ou agendas de aparelhos, e o VINCULA desenha o mapa e **analisa**: grupos, pontes, caminho entre duas
pessoas, linha do tempo, contradições entre fontes, selo de integridade e pivôs OSINT.
Tudo roda no seu computador, só com o Python.

## 3 passos

1. **Tenha o Python 3** (testado em 3.11, 3.12 e 3.13). Se não tiver: https://www.python.org/downloads/
   (no Windows, marque *Add python.exe to PATH*).
2. **Dois cliques no lançador do seu sistema** (extraia o zip antes):
   - Windows → `INICIAR-Windows.bat`
   - macOS → `INICIAR-Mac.command` (1ª vez: botão direito → *Abrir*)
   - Linux → `INICIAR-Linux.sh`
3. O navegador abre sozinho. Clique em **Carregar caso demo** (dados fictícios) e depois em **Grupos** e **Importância**.

> Se o navegador não abrir, copie o endereço da janela preta (algo como `http://127.0.0.1:8765/`).

## O que tem na pasta

| Item | Para quê |
|---|---|
| `manual/manual.html` | **Manual ilustrado** (abra no navegador). Comece por ele. |
| `vincula.py` + `vincula_analise.py` | O programa (só biblioteca padrão do Python). |
| `mapa_template.html` | Modelo da página do mapa (necessário ao programa). |
| `caso_demo/` | Reportagens, registros oficiais, chamadas e agendas fictícios + `mapa_demo.html` pronto. |
| `tests/` | Testes automatizados (unitários e de navegador). |
| `RELATORIO-TESTES.md` | Resultado dos testes em nuvem e o que **não** foi testado. |

## Linha de comando (opcional)

    python vincula.py demo
    python vincula.py analisar caso_demo/mapa_demo.html
    python vincula.py caminho caso_demo/mapa_demo.html "Carlos Menezes" "Marina Duarte" --forte
    python vincula.py exportar caso_demo/mapa_demo.html --formato stix
    python vincula.py verificar caso_demo/mapa_demo.html

## Três regras que valem ouro

1. **Declarado não é provado.** Confirme em fonte oficial.
2. **Inferência não é prova.** Duas coisas na mesma frase são só uma pista.
3. **Coincidência não é crime.** Alertas são indícios para investigar, nunca conclusão.

Chamadas e agendas de terceiros exigem base legal (ordem judicial, consentimento ou aparelho próprio).
Dados pessoais aparecem **mascarados** por padrão. Trate tudo conforme a LGPD.

Veja também `docs/GUIA-PRATICO.md` (8 exercícios com gabarito) e rode `python vincula.py diagnostico` se algo não abrir.
