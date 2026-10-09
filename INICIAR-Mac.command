#!/bin/bash
# VINCULA 2.1 - duplo clique no macOS
cd "$(dirname "$0")"
echo
echo "  Iniciando o VINCULA 2.1 ..."
echo
if command -v python3 >/dev/null 2>&1; then
  python3 vincula.py
else
  echo "  O Python 3 nao foi encontrado."
  echo "  Instale em https://www.python.org/downloads/ e de dois cliques de novo."
  read -n 1 -s -r -p "  Pressione qualquer tecla para fechar..."
fi
