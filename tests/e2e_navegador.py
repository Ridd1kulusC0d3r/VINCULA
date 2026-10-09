# -*- coding: utf-8 -*-
"""Teste ponta a ponta 2.0 (Chromium headless via Playwright). Requer: pip install playwright.
Uso: python tests/e2e_navegador.py -> PASS/FAIL por verificacao; codigo 1 se algo falhar."""
import json, subprocess, sys, time, tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import vincula as V, vincula_analise as A
PORTA = 8792
URL = f"http://127.0.0.1:{PORTA}/"
res = []


def ok(nome, cond, extra=""):
    res.append((nome, bool(cond)))
    print(("PASS " if cond else "FAIL ") + nome + (f"  [{extra}]" if extra and not cond else ""), flush=True)


def main():
    srv = subprocess.Popen([sys.executable, str(RAIZ / "vincula.py"), "abrir", "--sem-navegador", "--porta", str(PORTA)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=RAIZ)
    time.sleep(1.5)
    erros = []
    try:
        with sync_playwright() as p:
            br = p.chromium.launch()
            ctx = br.new_context(viewport={"width": 1400, "height": 850}, accept_downloads=True)
            page = ctx.new_page()
            page.on("pageerror", lambda e: erros.append(str(e)))
            page.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
            page.goto(URL)
            ok("bancada abre com aba Importar", page.locator("#tab-imp.on").count() == 1)
            ok("mapa vazio mostra orientacao", "Comece" in page.locator("#vp").text_content())
            page.click("#i-demo")
            page.wait_for_selector("g[data-id]")
            est = page.evaluate("()=>({e:VINCULA.estado().ents.length,l:VINCULA.estado().links.length,c:VINCULA.cruz().length})")
            ok("demo: 25 entidades, 60 vinculos, 6 cruzamentos", (est["e"], est["l"], est["c"]) == (25, 60, 6), str(est))
            ok("selo integro", page.evaluate("()=>VINCULA.selo()") == "íntegro" or page.locator("#selo.ok").count() == 1)
            ok("abas Alertas/Analise/Tempo", all(page.locator(f'#tabs button[data-t="{t}"]').count() for t in ("ale", "ana", "tmp")))
            ok("alertas listados", page.locator("#crs .cr").count() == 6)
            ok("barra de tempo visivel", page.locator("#tl").is_visible())
            # paridade Python <-> JS
            d = V.montar_demo(RAIZ / "caso_demo")
            com = A.comunidades(d, A.TODOS)
            js = page.evaluate("()=>VINCULA.comunidades()")
            ok("paridade comunidades", js["grupo"] == {k: v for k, v in com["grupo"].items()} or
               {k: v for k, v in js["grupo"].items() if v} == {k: v for k, v in com["grupo"].items() if v})
            bet = A.intermediacao(d, A.TODOS)
            jb = page.evaluate("()=>VINCULA.intermediacao()")
            ok("paridade intermediacao", all(abs(jb[k] - bet[k]) < 1e-6 for k in bet))
            cr = A.cruzamentos(d)
            jc = page.evaluate("()=>VINCULA.cruz()")
            ok("paridade cruzamentos", sorted((c["no"], c["score"]) for c in cr) == sorted((c["no"], c["score"]) for c in jc))
            ids = {e["rotulo"]: e["id"] for e in d["entidades"]}
            a, b = ids["Carlos Menezes Silva"], ids["Ricardo Tavares Neto"]
            pc = A.caminho(d, a, b, False)
            jp = page.evaluate("([a,b])=>VINCULA.caminho(a,b,false)", [a, b])
            ok("paridade caminho", (pc is None and jp is None) or (pc["nos"] == jp["nos"]))
            # ferramentas
            page.click("#b-grp"); page.click("#b-imp")
            ok("grupos desenham contornos", page.locator("#vp path").count() >= 2)
            page.click("#tabs button[data-t=ana]")
            ok("painel de grupos", page.locator("#grp .cr").count() >= 2)
            page.click("#t-path")
            page.locator(f'g[data-id="{a}"]').click(force=True)
            page.locator(f'g[data-id="{b}"]').click(force=True)
            page.wait_for_timeout(200)
            ok("caminho mostrado no painel", "elo" in page.locator("#cam").inner_text())
            page.click("#t-sel")
            page.keyboard.press("Escape")
            page.locator(f'g[data-id="{a}"]').click(force=True)
            page.click("#tabs button[data-t=det]")
            ok("pivos OSINT com links", page.locator("#piv a").count() >= 3)
            page.fill("#q", "marina")
            ok("busca seleciona", page.locator("#st2").inner_text().startswith("Encontradas"))
            page.fill("#q", "")
            page.evaluate("()=>document.activeElement.blur()")
            # linha do tempo
            page.evaluate("()=>{const r=document.querySelector('#tl-r');r.value=0;r.dispatchEvent(new Event('input'))}")
            n0 = page.locator("g[data-id]").count()
            page.click("#tl-all")
            n1 = page.locator("g[data-id]").count()
            ok("linha do tempo filtra e restaura", n0 <= n1 and n1 == 25, f"{n0}/{n1}")
            # mascara
            ok("mascara ligada por padrao", "99000" not in page.locator("#vp").text_content())
            # edicao + selo
            page.click("#t-sel")
            page.evaluate("()=>document.activeElement.blur()")
            page.keyboard.press("Escape")
            page.locator(f'g[data-id="{a}"]').click(force=True)
            page.keyboard.press("Delete")
            page.wait_for_timeout(300)
            ok("excluir muda selo para editado", page.locator("#selo.mod").count() == 1)
            ok("desfazer restaura selo", (page.click("#b-undo") or True) and page.wait_for_timeout(300) is None and page.locator("#selo.ok").count() == 1)
            # exportacoes
            for fmt in ("stix", "graphml", "csv", "mermaid", "json"):
                page.select_option("#x-fmt", fmt)
                with page.expect_download(timeout=5000) as dl:
                    page.click("#b-exp")
                ok("exporta " + fmt, dl.value.suggested_filename != "")
                page.wait_for_timeout(700)  # downloads extras (CSV tem 2 arquivos)
            # relatorio
            page.click("#b-rel")
            ok("relatorio com resumo e selo", "Selo do mapa" in page.locator("#rel").inner_text())
            page.click("#r-voltar")
            # salvar mapa html e reabrir standalone
            with page.expect_download() as dl:
                page.click("#b-html")
            tmp = Path(tempfile.mkdtemp()) / "m.html"
            dl.value.save_as(tmp)
            pg2 = ctx.new_page(); e2 = []
            pg2.on("pageerror", lambda e: e2.append(str(e)))
            pg2.goto(tmp.as_uri()); pg2.wait_for_timeout(1000); pg2.on("console", lambda m: e2.append(m.text) if m.type=="error" else None)
            ok("mapa salvo reabre offline com 25 nos", pg2.locator("g[data-id]").count() == 25 and not e2, str(e2) + str(pg2.locator("g[data-id]").count()) + pg2.locator("#st4").inner_text())
            ok("sem erros JS", not erros, str(erros))
            br.close()
    finally:
        srv.terminate()
    falhas = [n for n, c in res if not c]
    print(f"\n{len(res)-len(falhas)}/{len(res)} verificações passaram")
    sys.exit(1 if falhas else 0)


main()
