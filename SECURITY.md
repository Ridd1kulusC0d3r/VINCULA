# Segurança

- A bancada escuta só em `127.0.0.1`, valida o cabeçalho `Host` e exige `X-Vincula` nas chamadas; busca de URLs bloqueia endereços internos (SSRF).
- Nada é enviado a terceiros; só biblioteca padrão do Python.
- Os casos do repositório são **sintéticos**. Não suba dados reais de investigações para o GitHub.
- Achou falha? Abra uma issue privada (Security advisory) ou fale com o mantenedor antes de divulgar.
