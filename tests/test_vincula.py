# -*- coding: utf-8 -*-
"""Testes automatizados do VINCULA (somente biblioteca padrao). Rodar: python -m unittest discover -s tests -v"""
import json, sys, threading, unittest, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import vincula as V

DEMO = Path(__file__).resolve().parent.parent / "caso_demo"


def por_rotulo(d, rot):
    return next(e for e in d["entidades"] if e["rotulo"].startswith(rot))


class Documentos(unittest.TestCase):
    def test_cnpj_valido_e_invalido(self):
        self.assertTrue(V.cnpj_valido("11.222.333/0001-81"))
        self.assertFalse(V.cnpj_valido("11.222.333/0001-82"))
        self.assertFalse(V.cnpj_valido("00.000.000/0000-00"))

    def test_cpf(self):
        self.assertTrue(V.cpf_valido("529.982.247-25"))
        self.assertFalse(V.cpf_valido("529.982.247-26"))
        self.assertTrue(V.cpf_valido("***.982.247-**"))  # mascarado em reportagem


class Telefones(unittest.TestCase):
    def tels(self, t):
        return [x[1] for x in V.telefones_na_frase(t)]

    def test_formatos_validos(self):
        self.assertEqual(self.tels("ligue (31) 99999-0000"), ["+5531999990000"])
        self.assertEqual(self.tels("fixo +55 11 3333-4444"), ["+551133334444"])

    def test_rejeita_ddd_invalido_e_numeros_soltos(self):
        self.assertEqual(self.tels("(20) 99999-0000"), [])
        self.assertEqual(self.tels("valor 1234567890"), [])
        self.assertEqual(self.tels("CEP 30130-010"), [])

    def test_cnpj_nao_vira_telefone(self):
        d = V.extrair_textos([("t", "A Alfa Frota Ltda (CNPJ 11.222.333/0001-81) foi citada.")])
        self.assertFalse([e for e in d["entidades"] if e["tipo"] == "telefone"])


class Frases(unittest.TestCase):
    def test_ltda_seguido_de_maiuscula_encerra_frase(self):
        fr = V.dividir_frases("Carlos Silva é sócio da Delta Serviços Ltda. Marina Lopes é sócia da Beta Ltda.")
        self.assertEqual(len(fr), 2)

    def test_titulo_nao_quebra(self):
        fr = V.dividir_frases("O Dr. Paulo Souza mora na Av. Paulista, 100.")
        self.assertEqual(len(fr), 1)


class Evidencias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = V.extrair([DEMO / "reportagem_1.txt", DEMO / "reportagem_2.txt", DEMO / "reportagem_3.txt"])
        cls.ids = {e["id"]: e["rotulo"] for e in cls.d["entidades"]}

    def vinc(self, a, b):
        return [v for v in self.d["vinculos"] if {self.ids[v["de"]], self.ids[v["para"]]} == {a, b}]

    def test_declarado_socio(self):
        v = self.vinc("Carlos Menezes Silva", "Alfa Frota Ltda")
        self.assertEqual(v[0]["tipo"], "Declarado")

    def test_telefone_vai_para_o_dono_mais_proximo(self):
        self.assertEqual(self.vinc("(31) 99000-0202 [móvel]", "Ricardo Tavares Neto")[0]["tipo"], "Declarado")
        self.assertEqual(self.vinc("(31) 99000-0101 [móvel]", "Alfa Frota Ltda")[0]["tipo"], "Declarado")

    def test_cocitacao_e_inferencia_e_nao_duplica_declarado(self):
        for v in self.d["vinculos"]:
            if v["tipo"] == "Inferência":
                outros = [w for w in self.d["vinculos"] if w["tipo"] != "Inferência"
                          and {w["de"], w["para"]} == {v["de"], v["para"]}]
                self.assertEqual(outros, [])

    def test_nenhum_oficial_sem_csv(self):
        self.assertFalse([v for v in self.d["vinculos"] if v["tipo"] == "Oficial"])

    def test_cada_vinculo_tem_fonte_e_trecho(self):
        for v in self.d["vinculos"]:
            self.assertTrue(v["evidencias"])
            self.assertTrue(all(e["fonte"] and e["trecho"] for e in v["evidencias"]))

    def test_instituicoes_e_lugares_nao_viram_pessoa(self):
        nomes = {e["rotulo"] for e in self.d["entidades"] if e["tipo"] == "pessoa"}
        self.assertEqual(nomes, {"Carlos Menezes Silva", "Marina Duarte Lopes", "Ricardo Tavares Neto", "Carlos Silva"})

    def test_homonimo_vira_sugestao_nunca_fusao_automatica(self):
        self.assertEqual(len(self.d["sugestoes_fusao"]), 2)
        pares = [{self.ids[a], self.ids[b]} for a, b, _ in self.d["sugestoes_fusao"]]
        self.assertIn({"Carlos Menezes Silva", "Carlos Silva"}, pares)

    def test_hash_da_fonte(self):
        self.assertEqual(len(self.d["meta"]["fontes"]), 3)
        t = (DEMO / "reportagem_1.txt").read_text(encoding="utf-8")
        self.assertEqual(self.d["meta"]["fontes"][0]["sha256"], V.sha256_texto(t))


class Oficial(unittest.TestCase):
    def test_csv_gera_oficial_e_unifica_por_cnpj(self):
        d = V.extrair([DEMO / "reportagem_1.txt"])
        d = V.importar_oficial(d, (DEMO / "registros_oficiais_demo.csv").read_text(encoding="utf-8"), "csv")
        self.assertEqual(sum(v["tipo"] == "Oficial" for v in d["vinculos"]), 7)
        beta = por_rotulo(d, "Beta Logística")
        self.assertEqual(beta["id"], "empresa:cnpj:11222334000126")
        self.assertEqual(len([e for e in d["entidades"] if e["rotulo"].startswith("Beta")]), 1)

    def test_csv_do_excel_com_bom_e_ponto_e_virgula(self):
        csv_pt = "\ufeffde;tipo_de;para;tipo_para;rotulo;fonte\nMarina Duarte Lopes;pessoa;Beta Logística Ltda;empresa;sócia (QSA);Receita (sintético)\n"
        d = V.importar_oficial(V.extrair([DEMO / "reportagem_1.txt"]), csv_pt)
        self.assertEqual(sum(v["tipo"] == "Oficial" for v in d["vinculos"]), 1)

    def test_tipo_invalido_no_csv(self):
        d = V.extrair([DEMO / "reportagem_1.txt"])
        with self.assertRaises(ValueError):
            V.importar_oficial(d, "de,tipo_de,para,tipo_para,rotulo,fonte\nA,xyz,B,pessoa,r,f\n")

    def test_cnpj_invalido_gera_aviso(self):
        d = V.extrair_textos([("t", "A Zeta Obras Ltda (CNPJ 11.222.333/0001-99) venceu.")])
        self.assertIn("inválido", por_rotulo(d, "Zeta")["aviso"])


class Cruzamentos(unittest.TestCase):
    def test_demo_completo(self):
        d = V.montar_demo(DEMO)
        c = V.cruzamentos(d)
        ids = {e["id"]: e["rotulo"] for e in d["entidades"]}
        tipos = sorted((x["tipo"], ids[x["no"]]) for x in c)
        self.assertEqual(len(c), 6)
        self.assertIn(("sócio em comum", "Carlos Menezes Silva"), tipos)
        self.assertIn(("sócio em comum", "Marina Duarte Lopes"), tipos)
        self.assertIn(("identificador compartilhado", "Rua das Acácias, 120"), tipos)
        self.assertEqual([x["score"] for x in c], sorted([x["score"] for x in c], reverse=True))

    def test_sem_cruzamento_em_texto_simples(self):
        d = V.extrair_textos([("t", "A Alfa Frota Ltda usa o telefone (31) 99000-0101.")])
        self.assertEqual(V.cruzamentos(d), [])


class Dicionario(unittest.TestCase):
    def test_nome_conhecido_sem_sufixo(self):
        d = V.extrair_textos([("t", "A Quality Flux venceu o contrato, segundo a apuração.")], dicionario=[("Quality Flux", "empresa")])
        self.assertEqual(por_rotulo(d, "Quality Flux")["tipo"], "empresa")


class Url(unittest.TestCase):
    def test_bloqueia_rede_interna(self):
        for u in ("http://127.0.0.1/x", "http://localhost/x", "file:///etc/passwd", "ftp://a/b"):
            with self.assertRaises(ValueError):
                V.buscar_url(u)

    def test_le_artigo_html_local(self):
        pag = ("<html><head><title>Matéria teste</title></head><body><nav>menu lixo</nav><article><p>"
               + "O sócio Carlos Menezes Silva atua na Alfa Frota Ltda. " * 8 + "</p></article></body></html>").encode()

        class H(BaseHTTPRequestHandler):
            def do_GET(s):
                s.send_response(200); s.send_header("Content-Type", "text/html; charset=utf-8"); s.end_headers(); s.wfile.write(pag)
            def log_message(s, *a): pass
        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        r = V.buscar_url(f"http://127.0.0.1:{srv.server_address[1]}/", permitir_local=True)
        srv.shutdown(); srv.server_close()
        self.assertIn("Carlos Menezes Silva", r["texto"])
        self.assertNotIn("menu lixo", r["texto"])


class Servidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.url = V.servir(8790, abrir_navegador=False, bloco=False)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def post(self, rota, corpo, header=True, host=None):
        h = {"Content-Type": "application/json"}
        if header: h["X-Vincula"] = "1"
        if host: h["Host"] = host
        req = urllib.request.Request(self.url.rstrip("/") + rota, json.dumps(corpo).encode(), h)
        try:
            with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_pagina_inicial(self):
        with urllib.request.urlopen(self.url) as r:
            self.assertIn("VINCULA", r.read().decode())

    def test_extrai_via_api(self):
        st, d = self.post("/api/extrair", {"textos": [{"nome": "x", "texto": "O sócio Carlos Menezes Silva atua na Alfa Frota Ltda."}]})
        self.assertEqual(st, 200)
        self.assertEqual(len(d["entidades"]), 2)

    def test_exige_cabecalho_anti_csrf(self):
        st, d = self.post("/api/extrair", {"textos": []}, header=False)
        self.assertEqual(st, 403)

    def test_rejeita_host_estranho(self):
        st, d = self.post("/api/extrair", {"textos": []}, host="evil.example")
        self.assertEqual(st, 403)

    def test_url_interna_bloqueada(self):
        st, d = self.post("/api/url", {"url": "http://127.0.0.1:1/"})
        self.assertEqual(st, 400)

    def test_demo_api(self):
        st, d = self.post("/api/demo", {})
        self.assertEqual((st, len(d["cruzamentos"])), (200, 6))


class Analise20(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import vincula_analise as A, json, tempfile, os
        cls.A, cls.json = A, json
        cls.d = V.montar_demo(DEMO)

    def test_comunidades_e_pontes(self):
        c = self.A.comunidades(self.d, self.A.TODOS)
        self.assertGreaterEqual(len(c["grupos"]), 2)
        b = self.A.intermediacao(self.d, self.A.TODOS)
        self.assertTrue(max(b.values()) > 0)

    def test_caminho_e_elo_fraco(self):
        ids = {e["rotulo"]: e["id"] for e in self.d["entidades"]}
        a = ids["Carlos Menezes Silva"]; b = ids["Marina Duarte Lopes"]
        r = self.A.caminho(self.d, a, b, False)
        self.assertTrue(r is None or r["nos"][0] == a and r["nos"][-1] == b)

    def test_datas_e_cronologia(self):
        self.assertTrue(self.A.cronologia(self.d))

    def test_selo_integro_e_detecta_adulteracao(self):
        self.d["selo"] = self.A.selar(self.d)
        self.assertTrue(self.A.verificar(self.d)["integro"])
        d2 = self.json.loads(self.json.dumps(self.d))
        d2["vinculos"][0]["rotulo"] = "adulterado"
        self.assertFalse(self.A.verificar(d2)["integro"])

    def test_exportacoes(self):
        for fmt in ("stix", "graphml", "csv", "mermaid", "json"):
            arqs = self.A.exportar(self.d, fmt)
            self.assertTrue(arqs and all(t for _, t, _ in arqs), fmt)
        st = self.json.loads(self.A.exportar(self.d, "stix")[0][1])
        self.assertEqual(st["type"], "bundle")
        ids = {o["id"] for o in st["objects"]}
        for o in st["objects"]:
            for k in ("source_ref", "target_ref"):
                if k in o:
                    self.assertIn(o[k], ids)

    def test_chamadas_e_agenda_no_demo(self):
        self.assertTrue(any(v.get("n") for v in self.d["vinculos"]))
        self.assertTrue(any(e.get("apelidos") for e in self.d["entidades"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
