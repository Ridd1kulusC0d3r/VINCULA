#!/bin/sh
# VINCULA 2.1 - Linux. Duplo clique (Executar) ou: sh INICIAR-Linux.sh
cd "$(dirname "$0")"
echo
echo "  Iniciando o VINCULA 2.1 ..."
echo
if command -v python3 >/dev/null 2>&1; then
  python3 vincula.py
else
  echo "  Python 3 nao encontrado. Instale com o gerenciador de pacotes (ex.: sudo apt install python3)."
  printf "  Pressione Enter para fechar..."; read _
fi
