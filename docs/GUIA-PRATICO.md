# VINCULA 2.1 — Guia prático (laboratório com gabarito)

Cada exercício usa um caso sintético da pasta `casos/` (nenhuma pessoa ou empresa é real). Rode o comando, compare com o **gabarito**, leia a **armadilha**. Todos os gabaritos são verificados automaticamente em `tests/test_cenarios.py`.

> Antes de tudo: `python vincula.py diagnostico` — deve terminar com "Tudo certo".

## Como rodar um caso
```
python vincula.py caso casos/02-laranja-e-fachada      # gera casos/02-.../mapa.html e imprime o resumo
python vincula.py analisar casos/02-laranja-e-fachada/mapa.html   # painel de alertas em texto
```
Ou, na interface (`python vincula.py`), use **Abrir caso** e escolha a pasta.

## Exercício 1 — Demonstração (`caso_demo`)
`python vincula.py demo` → **25 entidades · 60 vínculos · 6 cruzamentos**.
Procure: alerta alto de **parentesco** (cunhada ligada a empresa concorrente); contradição "registro oficial indica saída, reportagem apresenta como vigente"; 1 sinal de tempo; números sequenciais; 2 apelidos no mesmo número.
*Armadilha:* "Ricardo" não é sócio da Beta só porque a cunhada é — o vínculo familiar é **Declarado**, não societário.

## Exercício 2 — Laranja e fachada (02)
Gabarito: 11 · 21 · 3. Alertas: endereço que **liga 5 partes** (alta densidade), CNPJ com **dígito inválido** (Pico Alto), telefone atribuído a titulares diferentes (reportagem × oficial), evento a 66 dias de mudança societária.
*Armadilha:* "Rio Claro" fica **a revisar** (pode ser cidade, rio ou empresa) — o programa não decide por você.

## Exercício 3 — Cartel em licitação (03)
Gabarito: 9 · 22 · 4. Alerta alto de parentes em empresas concorrentes; 3 pontos compartilhados entre Rota Verde e Via Azul; **um e-mail único** liga as 4 propostas.
*Armadilha:* sobreposição não é prova de conluio; é motivo para pedir os documentos da licitação.

## Exercício 4 — Homônimos e filiais (04)
Gabarito: 9 · 19 · 1. Duas "Santa Clara Alimentos" com **CNPJs diferentes não são fundidas**; a raiz `55030001` mostra matriz/filial; há 2 sugestões de fusão **para você aprovar**.
*Armadilha:* nome igual ≠ mesma entidade. Aceite a fusão só com documento ou fonte que a sustente.

## Exercício 5 — Celulares (05)
Gabarito: 8 · 16 · 0 cruzamentos. Importa chamadas (CDR) + 2 agendas: contatos em comum entre Jonas e Tiago, números sequenciais (…0101–0103), apelidos diferentes no mesmo número, dispersão de DDD (BA/MG/SP).
*Armadilha:* 0 cruzamentos na rede não significa 0 relação — os sinais de celular ficam no painel de análise.

## Exercício 6 — Fontes que se contradizem (06)
Gabarito: 6 · 6 · 1, **4 contradições**: saída societária × vigente, telefone com titulares diferentes, sócio × não sócio, dois endereços.
*Armadilha:* contradição não diz quem está certo. Marque a fonte oficial como referência e peça a certidão.

## Exercício 7 — Integridade (selo SHA-256)
1. Gere o mapa de qualquer caso; no painel, **Verificar selo** → "íntegro".
2. Edite um rótulo no arquivo `.html` salvo, abra de novo → selo **não íntegro**.
3. Em linha de comando: `python vincula.py analisar mapa.html` mostra a última linha "SELO: …".

## Exercício 8 — Seus próprios dados
1. Texto de reportagem em `.txt`, um por arquivo; 2. registros oficiais em CSV (formato A simples ou B completo — o erro mostra a linha); 3. `python vincula.py gerar r1.txt r2.txt --oficial reg.csv -o meu.html`.
Crie `caso.json` na pasta para repetir o caso: `{"titulo":"...","reportagens":["r1.txt"],"oficial":"reg.csv","chamadas":"cdr.csv","agendas":[{"arquivo":"a.vcf","dono":"Nome"}]}`.

## Problemas comuns
| Sintoma | Causa provável | Solução |
|---|---|---|
| "Não reconheci as colunas do CSV" | cabeçalho diferente | use um dos dois formatos da mensagem |
| "Não achei porta livre" | outro programa nas portas 8765–8784 | feche-o ou `abrir --porta 9000` |
| Pessoa não apareceu | nome sem verbo/cargo próximo | adicione `--dicionario` ou revise o texto |
| Mapa lento | milhares de nós | use filtros; análise usa amostragem acima de 800 nós |

## Limites honestos
Extração por regras (não é IA): erra com ironia, siglas e nomes raros. Parentesco só é detectado com termos explícitos ("cunhada de…"). Alertas são **indícios**, não conclusões; use fontes abertas e respeite a LGPD (máscara ativa por padrão).
