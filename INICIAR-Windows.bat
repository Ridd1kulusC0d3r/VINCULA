@echo off
chcp 65001 >nul
cd /d "%~dp0"
title VINCULA 2.1 - nao feche esta janela enquanto usar
echo.
echo   Iniciando o VINCULA 2.1 ...
echo.
where py >nul 2>nul
if %errorlevel%==0 ( py -3 vincula.py & goto fim )
where python >nul 2>nul
if %errorlevel%==0 ( python vincula.py & goto fim )
echo   O Python 3 nao foi encontrado neste computador.
echo.
echo   1) Abra  https://www.python.org/downloads/
echo   2) Baixe e instale (marque a caixa "Add python.exe to PATH")
echo   3) De dois cliques neste arquivo de novo.
:fim
echo.
pause
