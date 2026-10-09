# Como contribuir
1. Python simples, só biblioteca padrão (sem dependências novas).
2. Toda regra nova de extração/análise precisa de um caso em `casos/` ou teste em `tests/test_cenarios.py`.
3. Mudou algo em `vincula_analise.py`? Faça o espelho em `mapa_template.html` (JS) e confirme paridade com `python testar.py --e2e`.
4. Rode `python testar.py` antes de abrir PR.
