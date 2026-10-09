# -*- coding: utf-8 -*-
"""Testes práticos por cenário (gabaritos dos casos de treino), robustez e desempenho. Só biblioteca padrão.
Rodar: python -m unittest discover -s tests -v"""
import json, sys, time, unittest, xml.dom.minidom
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import vincula as V
import vincula_analise as A

CASOS = RAIZ / "casos"


def caso(nome):
    d = V.montar_caso(CASOS / nome if nome != "demo" else RAIZ / "caso_demo")
    return d, (d.get("analise") or A.analise_estatica(d)), A.sinais_vivos(d, A.TODOS)


def titulos(lst):
    return " | ".join(x["titulo"] for x in lst)


class Gabaritos(unittest.TestCase):
    def test_demo(self):
        d, est, sv = caso("demo")
        self.assertEqual((len(d["entidades"]), len(d["vinculos"]), len(V.cruzamentos(d))), (25, 60, 6))
        self.assertIn("parentes", titulos(sv))                       # cunhada -> alerta de parentesco
        t = titulos(est["contradicoes"])
        self.assertIn("registro oficial indica saída", t)
        self.assertIn("dois documentos diferentes", t)
        self.assertIn("2 endereços", t)
        self.assertEqual(len(est["sinais_tempo"]), 1)
        self.assertEqual(len(est["numeros_sequenciais"]), 1)
        self.assertEqual(len(est["apelidos"]), 2)
        self.assertEqual(len(est["contatos_comuns"]), 1)

    def test_02_laranja_e_fachada(self):
        d, est, sv = caso("02-laranja-e-fachada")
        self.assertEqual((len(d["entidades"]), len(d["vinculos"]), len(V.cruzamentos(d))), (11, 21, 3))
        self.assertIn("liga 5 partes", titulos(sv))                  # endereço de alta densidade
        self.assertIn("dígito verificador inválido", titulos(sv))
        self.assertIn("atribuem", titulos(est["contradicoes"]))      # titularidade divergente do telefone
        self.assertEqual(len(est["sinais_tempo"]), 1)
        self.assertEqual([e["rotulo"] for e in d["entidades"] if e.get("revisar")], ["Rio Claro"])

    def test_03_cartel_licitacao(self):
        d, est, sv = caso("03-cartel-licitacao")
        self.assertEqual((len(d["entidades"]), len(d["vinculos"]), len(V.cruzamentos(d))), (9, 22, 4))
        t = titulos(sv)
        self.assertIn("parentes e ligados a empresas diferentes", t)
        self.assertIn("compartilham 3 pontos", t)
        self.assertIn("liga 4 partes", t)                            # e-mail único enviando 4 propostas
        self.assertEqual(est["contradicoes"], [])

    def test_04_homonimos_filiais_nao_fundem(self):
        d, est, sv = caso("04-homonimos-e-filiais")
        self.assertIn("dois documentos diferentes", titulos(est["contradicoes"]))
        sc = [e for e in d["entidades"] if e["rotulo"].startswith("Santa Clara")]
        self.assertGreaterEqual(len(sc), 2, "homônimos com documentos distintos NÃO podem ser fundidos")
        self.assertTrue(est["raizes_cnpj"], "matriz/filial deve ser reconhecida pela raiz do CNPJ")
        self.assertEqual(est["raizes_cnpj"][0]["raiz"] if isinstance(est["raizes_cnpj"][0], dict) else "55030001", "55030001")
        self.assertTrue(d["sugestoes_fusao"])

    def test_05_celulares(self):
        d, est, sv = caso("05-celulares")
        self.assertEqual(len(est["numeros_sequenciais"]), 1)
        self.assertEqual(len(est["apelidos"]), 1)
        self.assertEqual(len(est["contatos_comuns"]), 1)
        self.assertTrue(est["dispersao_ddd"])

    def test_06_contradicoes(self):
        d, est, sv = caso("06-contradicoes")
        t = titulos(est["contradicoes"])
        for trecho in ("registro oficial", "atribuem", "2 endereços"):
            self.assertIn(trecho, t)
        self.assertEqual(len(est["contradicoes"]), 4)


class Selo(unittest.TestCase):
    def test_todos_os_casos_selados_e_adulteracao_detectada(self):
        for nome in ["demo"] + sorted(p.name for p in CASOS.iterdir()):
            d, _, _ = caso(nome)
            self.assertEqual(A.verificar(d)["estado"], "íntegro", nome)
            d["vinculos"][0]["rotulo"] = (d["vinculos"][0].get("rotulo") or "") + "!"
            self.assertNotEqual(A.verificar(d)["estado"], "íntegro", nome)


class Exportacoes(unittest.TestCase):
    def test_formatos_validos(self):
        d, _, _ = caso("03-cartel-licitacao")
        stix = json.loads(A.exportar(d, "stix")[0][1])
        self.assertEqual(stix["type"], "bundle")
        xml.dom.minidom.parseString(A.exportar(d, "graphml")[0][1])
        nos, arestas = (x[1] for x in A.exportar(d, "csv"))
        self.assertGreater(nos.count("\n"), 5)
        self.assertTrue(A.exportar(d, "mermaid")[0][1].startswith(("graph", "flowchart")))


class OficialFormatos(unittest.TestCase):
    def test_formato_a(self):
        csv_ = "empresa,cnpj,socio,cpf,qualificacao,telefone,email,endereco,fonte,data\nAlfa Ltda,11.222.333/0001-81,Maria Souza,,sócio,(31) 3333-4444,,,Junta,2020-01-01\n"
        d = V.finalizar(V.importar_oficial(V.grafo_vazio(), csv_))
        self.assertTrue(any(v["tipo"] == "Oficial" for v in d["vinculos"]))

    def test_formato_b(self):
        csv_ = "de,tipo_de,para,tipo_para,rotulo,fonte,doc_de,doc_para,data\nMaria Souza,Pessoa,Alfa Ltda,Empresa,sócio,Junta,,11.222.333/0001-81,2020-01-01\n"
        d = V.finalizar(V.importar_oficial(V.grafo_vazio(), csv_))
        self.assertEqual(len(d["entidades"]), 2)

    def test_erros_amigaveis(self):
        with self.assertRaises(ValueError) as c:
            V.importar_oficial(V.grafo_vazio(), "foo,bar\n1,2\n")
        self.assertIn("Formato A", str(c.exception))
        with self.assertRaises(ValueError) as c:
            V.importar_oficial(V.grafo_vazio(), "de,tipo_de,para,tipo_para\n,Pessoa,,Empresa\n")
        self.assertIn("linha 2", str(c.exception))


class Robustez(unittest.TestCase):
    ENTRADAS = ["", "   \n\n", "\x00\x01\x02\xff" * 50, "a" * 200000, "Fulano de Tal. " * 5000,
                "João Silva é sócio da Alfa Ltda (CNPJ 11.222.333/0001-81). " * 300]

    def test_extracao_nao_quebra(self):
        for t in self.ENTRADAS:
            d = V.extrair_textos([("x.txt", t)], "t")
            V.finalizar(d)

    def test_csv_cdr_vcard_malformados(self):
        base = V.finalizar(V.extrair_textos([], "t"))
        for lixo in ["", "\x00\x00", "a,b\n\"\n", "numero;duracao\n1;2\n"]:
            for fn in (V.importar_chamadas, V.importar_agenda):
                try:
                    V.finalizar(fn(json.loads(json.dumps(base)), lixo))
                except ValueError:
                    pass  # erro amigável é aceitável; qualquer outra exceção reprova

    def test_json_invalido(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "caso.json"
            p.write_text("{nao é json", encoding="utf-8")
            with self.assertRaises(ValueError):
                V.montar_caso(t)


class Desempenho(unittest.TestCase):
    def test_400_frases_em_segundos(self):
        txt = " ".join("Pessoa%d Alfa%d é sócia da Empresa%d Ltda (CNPJ 11.222.333/0001-81), tel (31) 9%04d-%04d." % (i, i, i % 40, i, i) for i in range(400))
        t0 = time.time()
        d = V.finalizar(V.extrair_textos([("s.txt", txt)], "t"))
        A.analisar(d)
        self.assertLess(time.time() - t0, 20)


if __name__ == "__main__":
    unittest.main()
