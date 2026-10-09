# -*- coding: utf-8 -*-
"""Roda tudo em um comando: diagnóstico + testes unitários/cenários (+ e2e no navegador se Playwright existir).
Uso: python testar.py [--e2e]"""
import subprocess, sys
from pathlib import Path
R = Path(__file__).resolve().parent


def passo(nome, cmd):
    print(f"\n=== {nome} ===")
    r = subprocess.run([sys.executable] + cmd, cwd=R)
    print(f"-> {'OK' if r.returncode == 0 else 'FALHOU'}")
    return r.returncode == 0


ok = passo("diagnóstico", ["vincula.py", "diagnostico"])
ok = passo("unitários e cenários", ["-m", "unittest", "discover", "-s", "tests"]) and ok
if "--e2e" in sys.argv:
    ok = passo("navegador (e2e)", ["tests/e2e_navegador.py"]) and ok
print("\nRESULTADO GERAL:", "TUDO OK" if ok else "HÁ FALHAS")
raise SystemExit(0 if ok else 1)
