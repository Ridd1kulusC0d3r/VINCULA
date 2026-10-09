#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VINCULA 2.0 - mapa de vinculos OSINT a partir de reportagens, celulares (chamadas e agendas) e registros publicos.

Somente biblioteca padrao do Python. Nenhuma instalacao de pacotes.
Testado em Python 3.11, 3.12 e 3.13 (sintaxe verificada para 3.8+).

Uso rapido (leigos):  de dois cliques no lancador do seu sistema (veja COMECE-AQUI.md).
Uso por linha de comando:
  python vincula.py                      abre a bancada no navegador
  python vincula.py abrir [--porta N]    idem, com opcoes
  python vincula.py gerar reportagem.txt [mais.txt] [--oficial registros.csv] [-o mapa.html]
  python vincula.py extrair reportagem.txt -o rede.json
  python vincula.py mapa rede.json -o mapa.html
  python vincula.py demo                 gera o caso demonstrativo (dados sinteticos)

Regra de evidencia (o coracao da ferramenta):
  Oficial    = veio de registro publico/oficial informado por voce (CSV). Nunca e gerado do texto.
  Declarado  = a reportagem afirma a relacao (socio, usa telefone, endereco...).
  Inferencia = houve apenas co-citacao na mesma frase. E hipotese, nao fato.
"""
import argparse, csv, difflib, hashlib, html.parser, io, ipaddress, json, re, socket, sys
import threading, unicodedata, urllib.parse, urllib.request, webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import combinations
from pathlib import Path

import vincula_analise as A
from vincula_analise import cruzamentos

VERSAO = "2.1"
PESO = {"Oficial": 3, "Declarado": 2, "Inferência": 1}
DONOS = ("pessoa", "empresa", "consorcio")
IDENT = ("telefone", "email", "endereco")
DDDS = set("11 12 13 14 15 16 17 18 19 21 22 24 27 28 31 32 33 34 35 37 38 41 42 43 44 45 46 47 48 49 "
           "51 53 54 55 61 62 63 64 65 66 67 68 69 71 73 74 75 77 79 81 82 83 84 85 86 87 88 89 "
           "91 92 93 94 95 96 97 98 99".split())

# ---------------------------------------------------------------- utilidades
def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def sha256_texto(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def so_digitos(s):
    return re.sub(r"\D", "", s)


def _dv(base, pesos):
    r = sum(int(a) * b for a, b in zip(base, pesos)) % 11
    return "0" if r < 2 else str(11 - r)


def cnpj_valido(d):
    d = so_digitos(d)
    if len(d) != 14 or len(set(d)) == 1:
        return False
    d1 = _dv(d[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = _dv(d[:12] + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return d[12:] == d1 + d2


def cpf_valido(txt):
    if "*" in txt:  # CPF mascarado em reportagem: aceita o formato, nao da para conferir
        return True
    d = so_digitos(txt)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        r = sum(int(d[i]) * (n + 1 - i) for i in range(n)) * 10 % 11 % 10
        if r != int(d[n]):
            return False
    return True


# ---------------------------------------------------------------- extracao
RE_CNPJ = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
RE_CPF = re.compile(r"[\d*]{3}\.[\d*]{3}\.[\d*]{3}-[\d*]{2}")
RE_TEL = re.compile(r"(?<![\d.])(?:\+?55\s?)?\(?(\d{2})\)?[\s.-]?(9?\d{4})[\s.-]?(\d{4})(?![\d])")
RE_MAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RE_CONS = re.compile(r"Cons[óo]rcio\s+(?:[A-ZÀ-Ú][\wÀ-ú&.-]*(?:\s+(?:d[aeo]s?\s+(?=[A-ZÀ-Ú]))?|\b)){1,4}")
RE_EMP = re.compile(r"(?:[A-ZÀ-Ú][\wÀ-ú&.'-]*\s+(?:d[aeo]s?\s+(?=[A-ZÀ-Ú]))?){1,5}(?:Ltda|LTDA|SA|S/A|EIRELI|EPP|ME|MEI)\b")
RE_PARENTE = re.compile(r"\b(cunhad[oa]|espos[oa]|marido|mulher|irma[o]?|filh[oa]|pai|mae|prim[oa]|sobrinh[oa]|tio|tia|genro|nora|"
                        r"sogr[oa]|companheir[oa]|namorad[oa]|ex-?espos[oa]|ex-?mulher|ex-?marido|compadre|comadre|entead[oa]|neto|neta|avo)"
                        r"\s+(?:d[oae]s?)\s+$")
RE_END = re.compile(r"(?:Rua|Avenida|Alameda|Rodovia|Travessa|Pra[çc]a|Estrada)\s[^,.;\n]{3,50}?"
                    r"(?=,|;|\.|\s+(?:em|no|na|e|onde|que|foi|era|é|com)\b|$)"
                    r"(?:,\s*(?:n[ºo°.]*\s*)?\d+[A-Za-z]?)?")
RE_NOME = re.compile(r"\b[A-ZÀ-Ú][a-zà-ú]+(?:(?:\s+(?:da|de|do|das|dos|e))?\s+[A-ZÀ-Ú][a-zà-ú]+){1,4}")

STOP = set("""segundo conforme procurado procurada ainda tambem mas entao porem assim depois antes durante
sobre apos contudo entretanto alem dessa desse esta este essa esse nesta neste numa num pela pelo pelas pelos
sr sra dr dra prof ex janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro
segunda terca quarta quinta sexta sabado domingo hoje ontem amanha""".split())
INSTITUCIONAL = set("""ministerio policia tribunal controladoria prefeitura governo secretaria camara assembleia
receita justica banco caixa delegacia promotoria procuradoria superintendencia conselho agencia instituto
universidade partido escritorio contabil contabilidade""".split())
LUGARES = set("""belo horizonte sao paulo rio de janeiro brasilia minas gerais curitiba salvador fortaleza recife
porto alegre goiania manaus belem contagem betim vale azul bahia parana santa catarina espirito santo""".split())
LUGARES_FRASES = {"belo horizonte", "sao paulo", "rio de janeiro", "minas gerais", "porto alegre", "santa catarina",
                  "espirito santo", "vale azul", "brasilia", "curitiba", "salvador", "fortaleza", "recife",
                  "goiania", "manaus", "belem", "contagem", "betim"}
ARTIGOS = {"a", "o", "as", "os", "da", "do", "de", "pela", "pelo", "na", "no", "em", "e", "com"}

CUE_SOCIO = re.compile(r"\b(socio|socia|socios|administrador|administradora|proprietari\w*|dono|dona|diretor|"
                       r"diretora|representante legal|titular)\b")
CUE_PESSOA = re.compile(CUE_SOCIO.pattern[:-3] + r"|investigad\w*|acusad\w*|presidente|secretari\w*)\b")
CUE_INTEGRA = re.compile(r"\b(integra|integram|formad[oa]s? (?:por|pel[ao]s?)|compost[oa]s? (?:por|pel[ao]s?)|"
                         r"consorciad\w*|participa|participam|consorcio entre)\b")
CUE_TEL = re.compile(r"\b(telefone|celular|contato|ligou|numero|whatsapp|fone|tel)\b")
CUE_MAIL = re.compile(r"\b(e-?mail|correio eletronico)\b")
CUE_END = re.compile(r"\b(sede|endereco|funciona|registrad\w*|localizad\w*|mora|residencia|domicilio|situad\w*|"
                     r"estabelecid\w*|cadastrad\w*)\b")
CUE_COMPART_ANTES = re.compile(r"\b(mesm[oa]s?|ambas|ambos|todas|todos)\b")
CUE_COMPART = re.compile(r"\b(mesmo|mesma|tambem|consta|cadastro)\b")
CUE_SOCIO_REL = re.compile(r"s[oó]ci[oa]s?|administrador|integra")


MAX_FRASE = 1500   # caracteres por "frase"; acima disso o texto e fatiado


def proteger_abreviaturas(t):
    # "Ltda." / "SA." seguidos de maiuscula contam como fim de frase; titulos e "Av." perdem o ponto
    t = re.sub(r"\bS\.\s?A\.?", "SA.", t)
    t = re.sub(r"\b(Av|Dr|Dra|Sr|Sra|Prof|Profa|Cia|Ltd|Exmo|Exma)\.", r"\1", t)
    return t


def dividir_frases(texto):
    t = proteger_abreviaturas(texto.replace("\r", ""))
    t = re.sub(r"(?<!\n)\n(?!\n)", " ", t)
    partes = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ú\"“(])|\n{2,}", t)
    out = []
    for p in partes:
        p = p.strip()
        while len(p) > MAX_FRASE:            # texto sem pontuacao (lista, tabela colada): evita custo quadratico
            corte = p.rfind(" ", 0, MAX_FRASE)
            corte = corte if corte > MAX_FRASE // 2 else MAX_FRASE
            out.append(p[:corte].strip())
            p = p[corte:].strip()
        if p:
            out.append(p)
    return out


MESES = {m: i for i, m in enumerate("janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro".split(), 1)}
MESES.update({"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12})
RE_D_EXT = re.compile(r"(?<!\d)(\d{1,2})\s*(?:º|o)?\s+de\s+([A-Za-zçÇ]+)\s+de\s+(\d{4})(?!\d)", re.I)
RE_D_NUM = re.compile(r"(?<![\d/.])(\d{1,2})/(\d{1,2})/(\d{4})(?![\d/])")
RE_MA_EXT = re.compile(r"\b([A-Za-zçÇ]+)\s+de\s+(\d{4})(?!\d)", re.I)
RE_MA_NUM = re.compile(r"(?<![\d/.])(\d{1,2})/(\d{4})(?![\d/])")
RE_ANO = re.compile(r"\b(?:em|desde|at[ée]|no ano de|ano de|a partir de)\s+(19[5-9]\d|20[0-3]\d)(?!\d)", re.I)


def datas_na_frase(t):
    """[(pos, iso, prec, texto)] com prec 'd' (dia), 'm' (mes) ou 'a' (ano). Ignora CNPJ/CPF/telefones."""
    for rx in (RE_CNPJ, RE_CPF, RE_TEL):
        t = rx.sub(lambda m: " " * len(m.group()), t)
    out = []

    def varre(rx, f):
        nonlocal t
        spans = []
        for m in rx.finditer(t):
            r = f(m)
            if r:
                out.append((m.start(), r[0], r[1], m.group().strip()))
                spans.append(m)
        for m in spans:
            t = _branquear(t, m)

    def mk(y, mo, di, prec):
        try:
            return date(y, mo, di).isoformat(), prec
        except ValueError:
            return None
    varre(RE_D_EXT, lambda m: mk(int(m.group(3)), MESES.get(norm(m.group(2)), 0), int(m.group(1)), "d"))
    varre(RE_D_NUM, lambda m: mk(int(m.group(3)), int(m.group(2)), int(m.group(1)), "d"))
    varre(RE_MA_EXT, lambda m: mk(int(m.group(2)), MESES.get(norm(m.group(1)), 0), 1, "m"))
    varre(RE_MA_NUM, lambda m: mk(int(m.group(2)), int(m.group(1)), 1, "m"))
    varre(RE_ANO, lambda m: mk(int(m.group(1)), 1, 1, "a"))
    return sorted(out)


def parse_data_flex(s):
    """Texto de data de planilha -> (iso, prec) ou (None, None)."""
    s = (s or "").strip()
    for rx, f in ((r"^(\d{4})-(\d{2})-(\d{2})", lambda g: (g[0], g[1], g[2], "d")), (r"^(\d{1,2})/(\d{1,2})/(\d{4})", lambda g: (g[2], g[1], g[0], "d")),
                  (r"^(\d{4})-(\d{2})$", lambda g: (g[0], g[1], 1, "m")), (r"^(\d{1,2})/(\d{4})$", lambda g: (g[1], g[0], 1, "m")),
                  (r"^(\d{4})$", lambda g: (g[0], 1, 1, "a"))):
        m = re.match(rx, s)
        if m:
            y, mo, di, prec = f(m.groups())
            try:
                return date(int(y), int(mo), int(di)).isoformat(), prec
            except ValueError:
                return None, None
    return None, None


def _branquear(t, m):
    return t[:m.start()] + " " * (m.end() - m.start()) + t[m.end():]


def _tel_fmt(ddd, num):
    """(e164, rotulo, tipo) ou None. Valida DDD e formato brasileiro."""
    if ddd not in DDDS:
        return None
    if len(num) == 9 and num[0] == "9":
        tipo = "móvel"
    elif len(num) == 8 and num[0] in "2345":
        tipo = "fixo"
    else:
        return None
    return f"+55{ddd}{num}", f"({ddd}) {num[:-4]}-{num[-4:]} [{tipo}]", tipo


def tel_normaliza(txt):
    """Numero em qualquer formato (so digitos, +55, parenteses) -> (e164, rotulo, tipo) ou None."""
    d = so_digitos(txt)
    if len(d) in (12, 13) and d.startswith("55"):
        d = d[2:]
    if len(d) not in (10, 11):
        return None
    return _tel_fmt(d[:2], d[2:])


def telefones_na_frase(t):
    """[(pos, e164, rotulo, tipo, span)] - valida DDD e formato; exige parenteses, +55 ou hifen."""
    out = []
    for m in RE_TEL.finditer(t):
        bruto = m.group(0)
        if not ("(" in bruto or "+" in bruto or "-" in bruto or bruto.startswith("55")):
            continue
        ddd, a, b = m.groups()
        r = _tel_fmt(ddd, a + b)
        if not r:
            continue
        out.append((m.start(), r[0], r[1], r[2], m))
    return out


def limpar_inicio(r, tipo):
    toks = r.split()
    while toks and norm(toks[0]) in (STOP | ARTIGOS):
        toks.pop(0)
    r = " ".join(toks).strip(" .,;")
    return r


def menciona(frase, dicionario=None):
    """Extrai mencoes de uma frase. Retorna lista de dicts {pos,tipo,rotulo,doc,alta}."""
    t = frase
    ms = []
    docs = []
    for rx, kind in ((RE_CNPJ, "cnpj"), (RE_CPF, "cpf")):
        for m in rx.finditer(t):
            docs.append({"pos": m.start(), "kind": kind, "txt": m.group()})
        t = rx.sub(lambda m: " " * len(m.group()), t)
    for nome, tipo in (dicionario or []):
        for m in re.finditer(r"(?<!\w)" + re.escape(nome) + r"(?!\w)", t, re.I):
            ms.append({"pos": m.start(), "tipo": tipo, "rotulo": nome, "doc": None, "alta": True})
            t = _branquear(t, m)
    for m in RE_MAIL.finditer(t):
        ms.append({"pos": m.start(), "tipo": "email", "rotulo": m.group().lower().rstrip("."), "doc": None, "alta": True})
    t = RE_MAIL.sub(lambda m: " " * len(m.group()), t)
    for pos, e164, rot, tp, m in telefones_na_frase(t):
        ms.append({"pos": pos, "tipo": "telefone", "rotulo": rot, "doc": e164, "alta": True})
    for pos, e164, rot, tp, m in telefones_na_frase(t):
        t = _branquear(t, m)
    for m in RE_END.finditer(t):
        ms.append({"pos": m.start(), "tipo": "endereco", "rotulo": m.group().strip(), "doc": None, "alta": True})
    t = RE_END.sub(lambda m: " " * len(m.group()), t)
    for rx, tipo in ((RE_CONS, "consorcio"), (RE_EMP, "empresa")):
        for m in rx.finditer(t):
            r = limpar_inicio(m.group(), tipo)
            if not r or (tipo == "empresa" and len(r.split()) < 2):
                continue
            ms.append({"pos": m.start(), "tipo": tipo, "rotulo": r, "doc": None, "alta": True})
        t = rx.sub(lambda m: " " * len(m.group()), t)
    for m in RE_NOME.finditer(t):
        r = limpar_inicio(m.group(), "pessoa")
        toks = r.split()
        if len(toks) < 2:
            continue
        n1 = norm(toks[0])
        if n1 in INSTITUCIONAL or norm(r) in LUGARES_FRASES or all(norm(x) in LUGARES for x in toks):
            continue
        ms.append({"pos": m.start(), "tipo": "pessoa", "rotulo": r, "doc": None, "alta": False})
    ms.sort(key=lambda x: x["pos"])
    # documentos (CNPJ/CPF): anexa a empresa/pessoa mais proxima; se nao houver, vira entidade propria
    for d in docs:
        alvo_t = "empresa" if d["kind"] == "cnpj" else "pessoa"
        cand = [x for x in ms if (x["tipo"] in ("empresa", "consorcio") if alvo_t == "empresa" else x["tipo"] == "pessoa")
                and x["doc"] is None]
        cand.sort(key=lambda x: abs(x["pos"] - d["pos"]))
        valido = cnpj_valido(d["txt"]) if d["kind"] == "cnpj" else cpf_valido(d["txt"])
        chave = so_digitos(d["txt"]) if "*" not in d["txt"] else re.sub(r"[^\d*]", "", d["txt"])
        if cand and abs(cand[0]["pos"] - d["pos"]) < 90:
            cand[0]["doc"] = (d["kind"], chave, d["txt"], valido)
        else:
            ms.append({"pos": d["pos"], "tipo": alvo_t, "rotulo": d["txt"], "doc": (d["kind"], chave, d["txt"], valido),
                       "alta": True})
    ms.sort(key=lambda x: x["pos"])
    return ms


# ---------------------------------------------------------------- grafo
class _Alias(dict):
    """dict (tipo, chave) -> id que mantem indices: ordem de insercao, por tamanho e por token.
    Evita varrer todas as entidades a cada mencao (custo quadratico em textos grandes)."""

    def __init__(self):
        super().__init__()
        self.ordem, self.por_tam, self.tok = {}, {}, {}

    def __setitem__(self, k, v):
        if k not in self:
            tipo, chave = k
            self.ordem[k] = len(self.ordem)
            self.por_tam.setdefault((tipo, len(chave)), []).append(chave)
            for t in set(chave.split()):
                self.tok.setdefault((tipo, t), []).append(chave)
        super().__setitem__(k, v)


class Grafo:
    def __init__(self, titulo="Mapa de Vínculos"):
        self.meta = {"titulo": titulo, "base": datetime.now().strftime("%d/%m/%Y"), "versao": VERSAO,
                     "gerado": datetime.now().isoformat(timespec="seconds"), "fontes": []}
        self.ents = {}      # id -> dict
        self.alias = _Alias()   # (tipo, chave_nome) -> id  (com indices para busca rapida)
        self.links = {}     # chave -> dict
        self.redirect = {}
        self.sugestoes = []
        self.mencoes = {}   # id -> n de fontes distintas

    # -- resolucao de entidades
    def chave_nome(self, rotulo, tipo):
        n = norm(rotulo)
        if tipo in ("empresa", "consorcio"):
            n = re.sub(r"\b(ltda|sa|s/a|eireli|epp|me|mei)\b", "", n)
        n = re.sub(r"^av\b\.?", "avenida", n)
        n = re.sub(r"^r\b\.?", "rua", n)
        return re.sub(r"[^a-z0-9@. ]", "", n).strip()

    def achar(self, i):
        while i in self.redirect:
            i = self.redirect[i]
        return i

    def resolver(self, tipo, rotulo, doc=None, alta=True, fonte=""):
        nn = self.chave_nome(rotulo, tipo)
        if tipo == "telefone" or tipo == "email":
            ident = doc and f"telefone:{doc}" if tipo == "telefone" else f"email:{rotulo.lower()}"
            e = self.ents.setdefault(ident, {"id": ident, "tipo": tipo, "rotulo": rotulo, "aliases": [], "revisar": False})
            self._conta(ident, fonte)
            return ident
        docid = None
        if doc:
            kind, chave, txt, valido = doc
            docid = f"{tipo}:{kind}:{chave}"
        alvo = self.alias.get((tipo, nn))
        if alvo:
            alvo = self.achar(alvo)
        if docid:
            separado = False
            if alvo and alvo != docid:
                if self.ents.get(alvo, {}).get("doc"):
                    # o nome ja pertence a outro documento: filial, homonimo ou erro de digitacao -> nao funde, sugere
                    separado = True
                    if not any({alvo, docid} == {x[0], x[1]} for x in self.sugestoes):
                        self.sugestoes.append([alvo, docid, "mesmo nome, documentos distintos (filial, homônimo ou erro de digitação)"])
                else:
                    self._fundir(alvo, docid, tipo, rotulo)
            e = self.ents.setdefault(docid, {"id": docid, "tipo": tipo, "rotulo": rotulo, "aliases": [], "revisar": False})
            e["doc"] = doc[2]
            if not doc[3]:
                e["aviso"] = "documento com dígito verificador inválido"
            if not separado:
                self.alias[(tipo, nn)] = docid
            if len(rotulo) >= len(e["rotulo"]) or e["rotulo"] == doc[2]:
                e["rotulo"] = rotulo
            self._conta(docid, fonte)
            return docid
        if alvo:
            if alta and self.ents.get(alvo, {}).get("revisar"):
                self.ents[alvo]["revisar"] = False       # uma mencao posterior com cargo/papel claro confirma a pessoa
            self._conta(alvo, fonte)
            return alvo
        # fuzzy: mesma grafia com pequenos erros -> funde; subconjunto de nomes -> apenas sugere
        if tipo in ("pessoa", "empresa", "consorcio"):
            limiar = 0.94 if tipo == "pessoa" else 0.92
            L = len(nn)
            cands = []
            for tam in range(max(1, int(L * 0.8)), int(L / 0.8) + 2):
                cands.extend(self.alias.por_tam.get((tipo, tam), ()))
            cands.sort(key=lambda k2: self.alias.ordem[(tipo, k2)])
            for k2 in cands:
                i2 = self.alias.get((tipo, k2))
                if i2 is None:
                    continue
                i2 = self.achar(i2)
                if nn[0] != k2[0] and nn[-1] != k2[-1]:   # erro de digitacao raramente troca inicio E fim do nome
                    continue
                sm = difflib.SequenceMatcher(None, nn, k2)
                if sm.real_quick_ratio() < limiar or sm.quick_ratio() < limiar:
                    continue
                r = sm.ratio()
                if r >= limiar:
                    self.alias[(tipo, nn)] = i2
                    al = self.ents[i2]["aliases"]
                    if rotulo not in al and rotulo != self.ents[i2]["rotulo"]:
                        al.append(rotulo)
                    self._conta(i2, fonte)
                    return i2
        novo = f"{tipo}:{nn.replace(' ', '-')}" if nn else f"{tipo}:{len(self.ents)}"
        if novo in self.ents:
            novo += f"-{len(self.ents)}"
        self.ents[novo] = {"id": novo, "tipo": tipo, "rotulo": rotulo, "aliases": [], "revisar": not alta}
        self.alias[(tipo, nn)] = novo
        self._sugerir(novo, tipo, nn)
        self._conta(novo, fonte)
        return novo

    def _conta(self, i, fonte):
        self.mencoes.setdefault(i, set()).add(fonte)

    def _fundir(self, velho, novo, tipo, rotulo):
        if velho == novo:
            return
        ev = self.ents.pop(velho, None)
        self.redirect[velho] = novo
        for k, v in list(self.alias.items()):
            if v == velho:
                self.alias[k] = novo
        if novo not in self.ents:
            self.ents[novo] = {"id": novo, "tipo": tipo, "rotulo": rotulo, "aliases": [], "revisar": False}
        if ev:
            self.ents[novo]["aliases"] += [x for x in [ev["rotulo"]] + ev.get("aliases", [])
                                           if x != self.ents[novo]["rotulo"] and x not in self.ents[novo]["aliases"]]
            self.mencoes.setdefault(novo, set()).update(self.mencoes.pop(velho, set()))

    def _sugerir(self, i, tipo, nn):
        if tipo not in ("pessoa", "empresa", "consorcio"):
            return
        a = nn.split()
        if not a:
            return
        cand = set()
        for t in set(a):
            cand.update(self.alias.tok.get((tipo, t), ()))
        cand.discard(nn)
        usados = {frozenset(s[:2]) for s in self.sugestoes}
        for k2 in sorted(cand, key=lambda k: self.alias.ordem[(tipo, k)]):
            i2 = self.achar(self.alias[(tipo, k2)])
            if i2 == i:
                continue
            b = k2.split()
            if tipo == "pessoa":
                ok = a and b and a[0] == b[0] and a[-1] == b[-1] and (set(a) <= set(b) or set(b) <= set(a))
                motivo = "mesmo primeiro e último nome (pode ser a mesma pessoa ou homônimo)"
            else:
                ok = len(a) >= 2 and len(b) >= 2 and (set(a) <= set(b) or set(b) <= set(a))
                motivo = "um nome contém o outro"
            if ok and frozenset((i, i2)) not in usados:
                usados.add(frozenset((i, i2)))
                self.sugestoes.append([i2, i, motivo])

    # -- vinculos
    def ligar(self, a, b, tipo, rotulo, fonte, trecho="", data=None, prec=None, extra=None):
        a, b = self.achar(a), self.achar(b)
        if a == b:
            return
        x, y = sorted((a, b)) if tipo == "Inferência" else (a, b)
        k = (x, y, tipo, rotulo) if tipo != "Inferência" else (x, y, tipo, rotulo)
        v = self.links.setdefault(k, {"de": x, "para": y, "tipo": tipo, "rotulo": rotulo, "evidencias": []})
        if extra:
            v.update(extra)
        ev = {"fonte": fonte, "trecho": trecho[:240]}
        if data:
            ev["data"], ev["prec"] = data, prec or "d"
        if ev not in v["evidencias"]:
            v["evidencias"].append(ev)

    def fechar(self):
        """Remapeia fusoes, deduplica e descarta co-citacao redundante."""
        vistos = {}
        for v in self.links.values():
            a, b = self.achar(v["de"]), self.achar(v["para"])
            if a == b or a not in self.ents or b not in self.ents:
                continue
            k = (a, b, v["tipo"], v["rotulo"]) if v["tipo"] != "Inferência" else (*sorted((a, b)), v["tipo"], v["rotulo"])
            w = vistos.setdefault(k, {"de": k[0], "para": k[1], "tipo": v["tipo"], "rotulo": v["rotulo"], "evidencias": []})
            for extra in ("dir", "n"):
                if extra in v:
                    w[extra] = v[extra]
            for ev in v["evidencias"]:
                if ev not in w["evidencias"]:
                    w["evidencias"].append(ev)
        fortes = {frozenset((w["de"], w["para"])) for w in vistos.values() if w["tipo"] != "Inferência"}
        lista = [w for w in vistos.values() if w["tipo"] != "Inferência" or frozenset((w["de"], w["para"])) not in fortes]
        for i, e in self.ents.items():
            if e["tipo"] == "pessoa" and len(self.mencoes.get(i, ())) >= 2:
                e["revisar"] = False
        sug = []
        for a, b, m in self.sugestoes:
            a, b = self.achar(a), self.achar(b)
            if a != b and a in self.ents and b in self.ents:
                sug.append([a, b, m])
        return {"meta": self.meta, "entidades": list(self.ents.values()), "vinculos": lista, "sugestoes_fusao": sug}

    @staticmethod
    def de_json(d):
        g = Grafo(d.get("meta", {}).get("titulo", "Mapa de Vínculos"))
        g.meta = d.get("meta", g.meta)
        for e in d.get("entidades", []):
            g.ents[e["id"]] = dict(e)
            g.alias[(e["tipo"], g.chave_nome(e["rotulo"], e["tipo"]))] = e["id"]
            for a in e.get("aliases", []):
                g.alias[(e["tipo"], g.chave_nome(a, e["tipo"]))] = e["id"]
        for v in d.get("vinculos", []):
            k = (v["de"], v["para"], v["tipo"], v["rotulo"])
            g.links[k] = {**v, "evidencias": list(v.get("evidencias", []))}
        g.sugestoes = [list(s) for s in d.get("sugestoes_fusao", [])]
        return g


def relacionar(g, ids_ms, frase, fonte):
    """ids_ms: [(id, mencao)] ja resolvidas. Aplica as regras de evidencia da frase."""
    nf = norm(frase)
    ds = datas_na_frase(frase)
    pos = {i: m["pos"] for i, m in ids_ms}

    def dt(a, b):
        """data da frase mais proxima do meio entre as duas mencoes (heuristica; o painel mostra a frase)"""
        if not ds or a not in pos or b not in pos:
            return {}
        _, iso, prec, _t = min(ds, key=lambda x: abs(x[0] - (pos[a] + pos[b]) / 2))
        return {"data": iso, "prec": prec}
    t = lambda m: m["tipo"]
    donos = [(i, m) for i, m in ids_ms if t(m) in DONOS]
    pessoas = [(i, m) for i, m in donos if t(m) == "pessoa"]
    empresas = [(i, m) for i, m in donos if t(m) in ("empresa", "consorcio")]
    feitos = set()

    def decl(a, b, rot):
        g.ligar(a, b, "Declarado", rot, fonte, frase, **dt(a, b))
        feitos.add(frozenset((a, b)))

    # parentesco: "Beatriz, cunhada de Odair" -> vinculo pessoal; Odair NAO vira socio so por estar na frase
    parentes = set()
    for i, m in pessoas:
        k = RE_PARENTE.search(norm(frase[max(0, m["pos"] - 40):m["pos"]]) + " ")
        if not k:
            continue
        depois = norm(frase[m["pos"] + len(m["rotulo"]):m["pos"] + len(m["rotulo"]) + 40])
        if not CUE_SOCIO.search(depois):          # "irmão de Marina, sócia da Beta": Marina continua candidata a sócia
            parentes.add(i)
        antes = [x for x in pessoas if x[1]["pos"] < m["pos"] and x[0] != i]
        if antes:
            decl(antes[-1][0], i, "parente (%s)" % k.group(1).replace("ex-", "ex ").strip())
    if parentes:
        pessoas = [x for x in pessoas if x[0] not in parentes]

    if CUE_SOCIO.search(nf) and pessoas and empresas and len(pessoas) * len(empresas) <= 12:
        # par declarado quando a empresa e a mais proxima da pessoa OU a pessoa e a mais proxima da empresa
        dist = lambda a, b: abs(a[1]["pos"] - b[1]["pos"])
        for p in pessoas:
            mais_e = min(empresas, key=lambda e: dist(p, e))
            for e in empresas:
                mais_p = min(pessoas, key=lambda q: dist(q, e))
                if e is mais_e or p is mais_p:
                    decl(p[0], e[0], "sócio/administrador")
    cons = [x for x in empresas if t(x[1]) == "consorcio"]
    emps = [x for x in empresas if t(x[1]) == "empresa"]
    if cons and emps and CUE_INTEGRA.search(nf):
        for c in cons:
            for e in emps:
                decl(e[0], c[0], "integra consórcio")
    for i, m in ids_ms:
        if t(m) not in IDENT or not donos:
            continue
        cue = {"telefone": CUE_TEL, "email": CUE_MAIL, "endereco": CUE_END}[t(m)].search(nf)
        rot = {"telefone": "usa telefone", "email": "usa e-mail", "endereco": "endereço"}[t(m)]
        antes = [x for x in donos if x[1]["pos"] < m["pos"]]
        depois = [x for x in donos if x[1]["pos"] > m["pos"]]
        principal = antes[-1] if antes else (depois[0] if depois else None)
        extras = []
        if cue and CUE_COMPART.search(nf):
            extras = depois if antes else depois[1:]
        if cue and antes and CUE_COMPART_ANTES.search(nf):
            # "A Rota Verde e a Via Azul informaram o MESMO telefone": todos os donos listados antes dividem o dado
            extras = extras + [x for x in antes[:-1] if m["pos"] - x[1]["pos"] <= 160 and x[1]["tipo"] in ("empresa", "consorcio", "pessoa")]
        for d in donos:
            if cue and d is principal:
                decl(d[0], i, rot)
            elif cue and d in extras:
                decl(d[0], i, rot)
            elif frozenset((d[0], i)) not in feitos:
                g.ligar(d[0], i, "Inferência", "co-citação", fonte, frase, **dt(d[0], i))
                feitos.add(frozenset((d[0], i)))
    if len(ids_ms) <= 8:
        for (a, ma), (b, mb) in combinations(ids_ms, 2):
            if a == b or frozenset((a, b)) in feitos:
                continue
            if t(ma) in IDENT and t(mb) in IDENT:
                continue
            g.ligar(a, b, "Inferência", "co-citação", fonte, frase, **dt(a, b))
            feitos.add(frozenset((a, b)))


def carregar_dicionario(caminho):
    out = []
    for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
        if ";" in linha and not linha.strip().startswith("#"):
            tp, nome = linha.split(";", 1)
            tp = norm(tp).replace("consorcio / scp", "consorcio")
            if tp in ("pessoa", "empresa", "consorcio", "endereco"):
                out.append((nome.strip(), tp))
    return out


def extrair_textos(textos, titulo="Mapa de Vínculos", dicionario=None, g=None):
    """textos: [(nome_fonte, texto)]. Retorna dict do grafo."""
    g = g or Grafo(titulo)
    for nome, texto in textos:
        g.meta["fontes"].append({"nome": nome, "sha256": sha256_texto(texto), "bytes": len(texto.encode("utf-8"))})
        for frase in dividir_frases(texto):
            ms = menciona(frase, dicionario)
            if not ms:
                continue
            cue = bool(CUE_PESSOA.search(norm(frase)))
            ids_ms, vistos = [], set()
            for m in ms:
                i = g.resolver(m["tipo"], m["rotulo"], m["doc"], m["alta"] or cue, nome)
                if i in vistos:
                    continue
                vistos.add(i)
                ids_ms.append((i, m))
            relacionar(g, ids_ms, frase, nome)
    return g.fechar()


def extrair(arquivos, titulo="Mapa de Vínculos", dicionario=None):
    textos = [(Path(a).name, Path(a).read_text(encoding="utf-8", errors="ignore")) for a in arquivos]
    return extrair_textos(textos, titulo, dicionario)


TIPOS_VALIDOS = ("pessoa", "empresa", "consorcio", "endereco", "email", "telefone")
ESQUEMA_AJUDA = ("Formato A (simples, uma linha por empresa): empresa,cnpj,socio,cpf,qualificacao,telefone,email,endereco,fonte,data\n"
                 "Formato B (completo, uma linha por ligação): de,tipo_de,para,tipo_para,rotulo,fonte,doc_de,doc_para,data")


def _linhas_oficial(csv_texto):
    """Le o CSV (virgula ou ponto e virgula; BOM; maiusculas/acentos nos cabecalhos) e devolve (formato, [linhas])."""
    csv_texto = csv_texto.lstrip("\ufeff")
    if not csv_texto.strip():
        raise ValueError("O CSV de registros oficiais está vazio.\n" + ESQUEMA_AJUDA)
    cab = csv_texto.splitlines()[0]
    delim = ";" if cab.count(";") > cab.count(",") else ","   # Excel em portugues salva com ponto e virgula
    rd = csv.DictReader(io.StringIO(csv_texto), delimiter=delim)
    campos = {norm(c).replace(" ", "_"): c for c in (rd.fieldnames or []) if c}
    linhas = [{k: (r.get(c) or "").strip() for k, c in campos.items()} for r in rd]
    if {"de", "para", "tipo_de", "tipo_para"} <= set(campos):
        return "B", linhas
    if "empresa" in campos or "socio" in campos:
        return "A", linhas
    raise ValueError("Não reconheci as colunas do CSV (%s).\n%s" % (", ".join(campos) or "nenhuma", ESQUEMA_AJUDA))


def _expande_simples(r, n):
    """Formato A -> ligações no formato B: [(de, tipo_de, doc_de, para, tipo_para, doc_para, rotulo)]."""
    q = r.get("qualificacao") or r.get("papel") or r.get("cargo") or r.get("rotulo") or "sócio-administrador (QSA)"
    out = []
    emp, cnpj = r.get("empresa", ""), r.get("cnpj", "")
    soc, cpf = r.get("socio", ""), r.get("cpf", "")
    dono = ("empresa", emp, cnpj) if emp else (("pessoa", soc, cpf) if soc else None)
    if not dono:
        raise ValueError("linha %d: informe ao menos 'empresa' ou 'socio'." % n)
    if emp and soc:
        out.append((soc, "pessoa", cpf, emp, "empresa", cnpj, q))
    for col, tp, rot in (("telefone", "telefone", "usa telefone"), ("email", "email", "usa e-mail"), ("endereco", "endereco", "sede")):
        if r.get(col):
            out.append((dono[1], dono[0], dono[2], r[col], tp, "", rot))
    if not out:
        raise ValueError("linha %d: só há %s; acrescente socio, telefone, email ou endereco para formar uma ligação." % (n, dono[0]))
    return out


def importar_oficial(d, csv_texto, nome_fonte="registro oficial"):
    """CSV de registros oficiais -> vinculos 'Oficial'. Aceita o formato A (simples) ou B (completo); erros citam a linha."""
    formato, linhas = _linhas_oficial(csv_texto)
    csv_texto = csv_texto.lstrip("\ufeff")
    g = Grafo.de_json(d)
    g.meta.setdefault("fontes", []).append({"nome": nome_fonte, "sha256": sha256_texto(csv_texto),
                                            "bytes": len(csv_texto.encode("utf-8"))})
    n = 0
    for num, r in enumerate(linhas, 2):          # linha 1 = cabecalho
        if not any(r.values()):
            continue
        if formato == "B":
            if not r.get("de") or not r.get("para"):
                raise ValueError("linha %d: 'de' e 'para' são obrigatórios." % num)
            ligs = [(r["de"], r["tipo_de"], r.get("doc_de", ""), r["para"], r["tipo_para"], r.get("doc_para", ""), r.get("rotulo") or "registro")]
        else:
            ligs = _expande_simples(r, num)
        for de, tde, dde, para, tpa, dpa, rotulo in ligs:
            ids = []
            for rot, tp, dd in ((de, tde, dde), (para, tpa, dpa)):
                tp = norm(tp).replace("consorcio / scp", "consorcio")
                if tp not in TIPOS_VALIDOS:
                    raise ValueError("linha %d: tipo inválido %r (use: %s)." % (num, tp, ", ".join(TIPOS_VALIDOS)))
                doc = None
                if dd and tp in ("empresa", "pessoa"):
                    kind = "cnpj" if tp == "empresa" else "cpf"
                    doc = (kind, re.sub(r"[^\d*]", "", dd), dd, cnpj_valido(dd) if kind == "cnpj" else cpf_valido(dd))
                if tp == "telefone":
                    tels = telefones_na_frase(rot if "(" in rot or "+" in rot else f"({rot[:2]}) {rot[2:]}")
                    if tels:
                        ids.append(g.resolver("telefone", tels[0][2], tels[0][1], True, nome_fonte))
                        continue
                    raise ValueError("linha %d: telefone não reconhecido: %r (use DDD, ex.: (31) 99999-0000)." % (num, rot))
                ids.append(g.resolver(tp, rot, doc, True, nome_fonte))
            iso, prec = parse_data_flex(r.get("data"))
            g.ligar(ids[0], ids[1], "Oficial", rotulo, (r.get("fonte") or nome_fonte).strip(), f"{de} — {para}", data=iso, prec=prec)
            n += 1
    out = g.fechar()
    out["meta"]["oficial_linhas"] = n
    return out


# ---------------------------------------------------------------- celulares: chamadas e agendas
def _achar_col(campos, opcoes):
    mapa = {norm(c).replace(" ", "_"): c for c in (campos or []) if c}
    for o in opcoes:
        if o in mapa:
            return mapa[o]
    return None


def _data_hora(txt):
    txt = (txt or "").strip()
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(txt, f)
        except ValueError:
            pass
    return None


def _segundos(txt):
    txt = (txt or "").strip()
    if not txt:
        return 0
    if ":" in txt:
        p = [int(x) for x in re.findall(r"\d+", txt)][-3:]
        while len(p) < 3:
            p.insert(0, 0)
        return p[0] * 3600 + p[1] * 60 + p[2]
    try:
        return int(float(txt.replace(",", ".")))
    except ValueError:
        return 0


def _hms(seg):
    return f"{seg // 3600:d}h{seg % 3600 // 60:02d}min{seg % 60:02d}s"


def _ler_csv(texto):
    texto = texto.lstrip("﻿")
    cab = texto.splitlines()[0] if texto.strip() else ""
    delim = ";" if cab.count(";") > cab.count(",") else ","
    return csv.DictReader(io.StringIO(texto), delimiter=delim)


def importar_chamadas(d, csv_texto, nome_fonte="registro de chamadas (CSV)"):
    """CSV de chamadas (CDR): origem,destino[,data,duracao,tipo] -> um vinculo 'Oficial' por par (a->b) com totais.
    O arquivo e informado por voce (ex.: dados obtidos por ordem judicial); a ferramenta so le, local, nada sai do computador."""
    rd = _ler_csv(csv_texto)
    co = _achar_col(rd.fieldnames, ("origem", "a", "numero_a", "de", "caller", "chamador", "telefone_a", "msisdn_a"))
    cd = _achar_col(rd.fieldnames, ("destino", "b", "numero_b", "para", "callee", "chamado", "telefone_b", "msisdn_b"))
    if not co or not cd:
        raise ValueError("O CSV de chamadas precisa das colunas 'origem' e 'destino' (opcionais: data, duracao, tipo).")
    cdt = _achar_col(rd.fieldnames, ("data", "data_hora", "datahora", "inicio", "timestamp", "data_inicio"))
    cdu = _achar_col(rd.fieldnames, ("duracao", "duracao_s", "segundos", "duration", "duracao_seg"))
    g = Grafo.de_json(d)
    g.meta.setdefault("fontes", []).append({"nome": nome_fonte, "sha256": sha256_texto(csv_texto), "bytes": len(csv_texto.encode("utf-8"))})
    agg, linhas, ign = {}, 0, 0
    for r in rd:
        linhas += 1
        a, b = tel_normaliza(r.get(co) or ""), tel_normaliza(r.get(cd) or "")
        if not a or not b or a[0] == b[0]:
            ign += 1
            continue
        k = (a, b)
        x = agg.setdefault(k, {"n": 0, "seg": 0, "prim": None, "ult": None, "noite": 0})
        x["n"] += 1
        x["seg"] += _segundos(r.get(cdu)) if cdu else 0
        dh = _data_hora(r.get(cdt)) if cdt else None
        if dh:
            x["prim"] = dh if not x["prim"] or dh < x["prim"] else x["prim"]
            x["ult"] = dh if not x["ult"] or dh > x["ult"] else x["ult"]
            if dh.hour >= 22 or dh.hour < 5:
                x["noite"] += 1
    for (a, b), x in sorted(agg.items()):
        ia = g.resolver("telefone", a[1], a[0], True, nome_fonte)
        ib = g.resolver("telefone", b[1], b[0], True, nome_fonte)
        sa, sb = re.sub(r"\s*\[.*?\]", "", a[1]), re.sub(r"\s*\[.*?\]", "", b[1])
        t = f"{x['n']} chamada(s) de {sa} para {sb}"
        if x["seg"]:
            t += f"; duração total {_hms(x['seg'])}"
        if x["prim"]:
            t += f"; de {x['prim']:%d/%m/%Y} a {x['ult']:%d/%m/%Y}"
        if x["noite"]:
            t += f"; {x['noite']} entre 22h e 5h"
        g.ligar(ia, ib, "Oficial", f"{x['n']} ligação" if x["n"] == 1 else f"{x['n']} ligações", nome_fonte, t,
                data=x["prim"].date().isoformat() if x["prim"] else None, prec="d", extra={"dir": True, "n": x["n"]})
    out = g.fechar()
    out["meta"]["chamadas"] = {"fonte": nome_fonte, "linhas": linhas, "ignoradas": ign, "pares": len(agg)}
    return out


def ler_contatos(texto):
    """vCard (.vcf) ou CSV (nome,telefone[,email,empresa]) -> [{nome, tels, emails, org}]"""
    cards = []
    if "BEGIN:VCARD" in texto.upper():
        t = re.sub(r"\n[ \t]", "", texto.replace("\r\n", "\n").replace("\r", "\n"))
        cur = None
        for linha in t.split("\n"):
            l = linha.strip()
            if l.upper() == "BEGIN:VCARD":
                cur = {"nome": "", "tels": [], "emails": [], "org": ""}
            elif l.upper() == "END:VCARD" and cur is not None:
                cards.append(cur)
                cur = None
            elif cur is not None and ":" in l:
                chave, _, val = l.partition(":")
                campo = chave.split(";")[0].upper().split(".")[-1]
                if campo == "FN":
                    cur["nome"] = val.strip()
                elif campo == "N" and not cur["nome"]:
                    p = val.split(";")
                    cur["nome"] = " ".join(x for x in ((p[1] if len(p) > 1 else ""), p[0]) if x).strip()
                elif campo == "TEL":
                    cur["tels"].append(val.strip())
                elif campo == "EMAIL":
                    cur["emails"].append(val.strip().lower())
                elif campo == "ORG":
                    cur["org"] = val.replace(";", " ").strip()
        return cards
    rd = _ler_csv(texto)
    cn = _achar_col(rd.fieldnames, ("nome", "name", "contato", "fn"))
    ct = _achar_col(rd.fieldnames, ("telefone", "celular", "numero", "tel", "phone", "fone"))
    if not cn or not ct:
        raise ValueError("A agenda precisa ser vCard (.vcf) ou CSV com as colunas 'nome' e 'telefone'.")
    ce = _achar_col(rd.fieldnames, ("email", "e-mail", "e_mail"))
    co = _achar_col(rd.fieldnames, ("empresa", "organizacao", "org"))
    for r in rd:
        cards.append({"nome": (r.get(cn) or "").strip(), "tels": [x for x in re.split(r"[;|]", r.get(ct) or "") if x.strip()],
                      "emails": [(r.get(ce) or "").strip().lower()] if ce and (r.get(ce) or "").strip() else [], "org": (r.get(co) or "").strip() if co else ""})
    return cards


def importar_agenda(d, texto, nome_fonte="agenda do aparelho", dono=None, limite=5000):
    """Agenda de contatos (vCard/CSV). Com 'dono', liga o dono a cada numero salvo; o nome com que o numero foi salvo
    vira 'apelido' do telefone (o mesmo numero salvo com nomes diferentes aparece como alerta).
    Se o nome do contato for igual ao de uma pessoa/empresa ja no mapa, o telefone e ligado a ela."""
    cards = ler_contatos(texto)[:limite]
    g = Grafo.de_json(d)
    g.meta.setdefault("fontes", []).append({"nome": nome_fonte, "sha256": sha256_texto(texto), "bytes": len(texto.encode("utf-8"))})
    dono_id = g.resolver("pessoa", dono, None, True, nome_fonte) if dono else None
    usados, ign = 0, 0
    for c in cards:
        alvos = []
        if c["nome"]:
            for tp in ("pessoa", "empresa"):
                a = g.alias.get((tp, g.chave_nome(c["nome"], tp)))
                if a:
                    a = g.achar(a)
                    if a != dono_id and a in g.ents:
                        alvos.append(a)
        for tel in c["tels"]:
            r = tel_normaliza(tel)
            if not r:
                ign += 1
                continue
            tid = g.resolver("telefone", r[1], r[0], True, nome_fonte)
            ap = g.ents[tid].setdefault("apelidos", [])
            reg = {"nome": c["nome"] or "(sem nome)", "fonte": nome_fonte}
            if c["org"]:
                reg["org"] = c["org"]
            if reg not in ap:
                ap.append(reg)
            usados += 1
            trecho = f"salvo como «{reg['nome']}»" + (f" ({c['org']})" if c["org"] else "")
            if dono_id:
                g.ligar(dono_id, tid, "Declarado", "tem na agenda", nome_fonte, trecho)
            for a in alvos:
                g.ligar(a, tid, "Declarado", "salvo na agenda", nome_fonte, trecho + (f" · agenda de {dono}" if dono else ""))
        for em in c["emails"]:
            if "@" not in em:
                continue
            eid = g.resolver("email", em, None, True, nome_fonte)
            if dono_id:
                g.ligar(dono_id, eid, "Declarado", "tem na agenda", nome_fonte, f"salvo como «{c['nome'] or em}»")
            for a in alvos:
                g.ligar(a, eid, "Declarado", "salvo na agenda", nome_fonte, f"salvo como «{c['nome']}»")
    out = g.fechar()
    out["meta"].setdefault("agendas", []).append({"fonte": nome_fonte, "dono": dono or "", "contatos": len(cards), "numeros": usados, "ignorados": ign})
    return out


def finalizar(d):
    """Calcula o que e derivado (cruzamentos, analise estatica) e sela o conteudo (selo de integridade)."""
    d["cruzamentos"] = cruzamentos(d) if d.get("entidades") else []
    d["analise"] = A.analise_estatica(d) if d.get("entidades") else {}
    if d.get("entidades"):
        d["selo"] = A.selar(d)
    return d


def ler_dados(caminho):
    """Le um .json do VINCULA ou um mapa .html salvo (o JSON vai embutido no proprio HTML)."""
    t = Path(caminho).read_text(encoding="utf-8")
    if t.lstrip().startswith("<"):
        m = re.search(r'<script id="dados" type="application/json">(.*?)</script>', t, re.S)
        if not m:
            raise ValueError("Não encontrei dados do VINCULA neste HTML.")
        t = m.group(1)
    return json.loads(t)


def achar_entidade(d, termo):
    q = norm(termo)
    qd = so_digitos(termo)
    ex, par = [], []
    for e in d["entidades"]:
        nomes = [e["rotulo"]] + list(e.get("aliases", [])) + [a["nome"] for a in e.get("apelidos", [])]
        ns = [norm(x) for x in nomes]
        if e["id"] == termo or q in [re.sub(r"\s*\[.*?\]", "", n).strip() for n in ns]:
            ex.append(e)
        elif any(q in n for n in ns) or (len(qd) >= 6 and qd in so_digitos(e["id"] + " " + e["rotulo"])):
            par.append(e)
    c = ex or par
    if not c:
        raise ValueError(f"Não achei nenhuma entidade com “{termo}”.")
    if len(c) > 1:
        raise ValueError(f"“{termo}” é ambíguo: " + "; ".join(e["rotulo"] for e in c[:6]) + ". Seja mais específico.")
    return c[0]


# ---------------------------------------------------------------- busca de reportagem por URL
class _Texto(html.parser.HTMLParser):
    IGNORA = {"script", "style", "nav", "header", "footer", "aside", "noscript", "form", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nivel_ign, self.partes, self.titulo, self._t, self.em_art, self.art = 0, [], "", False, 0, []

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORA:
            self.nivel_ign += 1
        if tag == "title":
            self._t = True
        if tag == "article":
            self.em_art += 1
        if tag in ("p", "br", "li", "h1", "h2", "h3", "div"):
            self.partes.append("\n\n" if tag != "br" else "\n")
            if self.em_art:
                self.art.append("\n\n")

    def handle_endtag(self, tag):
        if tag in self.IGNORA and self.nivel_ign:
            self.nivel_ign -= 1
        if tag == "title":
            self._t = False
        if tag == "article" and self.em_art:
            self.em_art -= 1

    def handle_data(self, data):
        if self._t:
            self.titulo += data
        if self.nivel_ign:
            return
        self.partes.append(data)
        if self.em_art:
            self.art.append(data)


def host_privado(host):
    try:
        for fam, _, _, _, sa in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(sa[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return True
    except Exception:
        return True
    return False


def buscar_url(url, permitir_local=False, limite=2_000_000, timeout=15):
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("Use um endereço http:// ou https://")
    if not permitir_local and host_privado(u.hostname):
        raise ValueError("Endereço de rede interna bloqueado por segurança.")
    req = urllib.request.Request(url, headers={"User-Agent": "VINCULA/1.0 (+uso local de pesquisa)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        bruto = r.read(limite + 1)
        cs = r.headers.get_content_charset() or "utf-8"
    if len(bruto) > limite:
        raise ValueError("Página grande demais (limite 2 MB).")
    try:
        txt = bruto.decode(cs)
    except Exception:
        txt = bruto.decode("latin-1")
    p = _Texto()
    p.feed(txt)
    corpo = "".join(p.art) if len("".join(p.art).strip()) > 300 else "".join(p.partes)
    corpo = re.sub(r"[ \t]+", " ", corpo)
    corpo = re.sub(r"\n\s*\n\s*", "\n\n", corpo).strip()
    return {"nome": (p.titulo.strip() or u.hostname)[:120] + f" <{url}>", "texto": corpo, "url": url}


# ---------------------------------------------------------------- mapa HTML
def carregar_template():
    return (Path(__file__).resolve().parent / "mapa_template.html").read_text(encoding="utf-8")


def gerar_html(d, api=False):
    d = dict(d)
    if d.get("entidades"):
        d["cruzamentos"] = cruzamentos(d)
        d["analise"] = A.analise_estatica(d)
        if "selo" not in d:
            d["selo"] = A.selar(d)
    dados = json.dumps(d, ensure_ascii=False).replace("<", "\\u003c")
    return carregar_template().replace("__DADOS__", dados).replace("__CFG__", json.dumps({"api": api, "ddd": A.UF_DDD}))


def grafo_vazio():
    return {"meta": {"titulo": "Mapa de Vínculos", "base": datetime.now().strftime("%d/%m/%Y"), "versao": VERSAO, "fontes": []},
            "entidades": [], "vinculos": [], "sugestoes_fusao": []}


# ---------------------------------------------------------------- servidor local (bancada)
class Manipulador(BaseHTTPRequestHandler):
    server_version = "VINCULA/" + VERSAO
    DEMO_DIR = Path(__file__).resolve().parent / "caso_demo"
    permitir_local_url = False

    def log_message(self, *a):
        pass

    def _host_ok(self):
        h = (self.headers.get("Host") or "").split(":")[0]
        return h in ("127.0.0.1", "localhost")

    def _json(self, codigo, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"erro": "host não permitido"})
        if self.path.split("?")[0] not in ("/", "/index.html"):
            return self._json(404, {"erro": "não encontrado"})
        b = gerar_html(grafo_vazio(), api=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        if not self._host_ok() or self.headers.get("X-Vincula") != "1":
            return self._json(403, {"erro": "requisição não permitida"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 20_000_000:
                return self._json(413, {"erro": "arquivo grande demais"})
            corpo = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/extrair":
                textos = [(t.get("nome", "texto"), t.get("texto", "")) for t in corpo.get("textos", [])]
                d = extrair_textos(textos, corpo.get("titulo") or "Mapa de Vínculos")
                if corpo.get("oficial"):
                    d = importar_oficial(d, corpo["oficial"], "registro oficial (CSV)")
                if corpo.get("chamadas"):
                    d = importar_chamadas(d, corpo["chamadas"], corpo.get("chamadas_nome") or "registro de chamadas (CSV)")
                for ag in corpo.get("agendas", []):
                    d = importar_agenda(d, ag.get("texto", ""), ag.get("nome") or "agenda do aparelho", (ag.get("dono") or "").strip() or None)
                return self._json(200, finalizar(d))
            if self.path == "/api/exportar":
                arqs = A.exportar(corpo["dados"], corpo.get("formato", "json"))
                return self._json(200, {"arquivos": [{"nome": n, "conteudo": c, "mime": m} for n, c, m in arqs]})
            if self.path == "/api/url":
                return self._json(200, buscar_url(corpo.get("url", ""), self.permitir_local_url))
            if self.path == "/api/demo":
                return self._json(200, montar_demo(self.DEMO_DIR))
            return self._json(404, {"erro": "rota desconhecida"})
        except Exception as e:  # erro legivel para leigos
            return self._json(400, {"erro": str(e)[:300]})


def servir(porta=8765, abrir_navegador=True, bloco=True):
    srv = None
    for p in range(porta, porta + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), Manipulador)
            break
        except OSError:
            continue
    if srv is None:
        raise SystemExit("Não achei porta livre (8765–8784). Feche outros programas e tente de novo.")
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    if bloco:
        print(f"\n  VINCULA {VERSAO} está rodando.\n  Abra no navegador: {url}\n  (para encerrar: feche esta janela ou pressione Ctrl+C)\n")
        if abrir_navegador:
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n  Encerrado.")
        finally:
            srv.server_close()
    return srv, url


# ---------------------------------------------------------------- demo / CLI
def montar_caso(pasta):
    """Monta um caso a partir de <pasta>/caso.json:
    {"titulo", "reportagens":[...], "oficial":"x.csv", "chamadas":"y.csv", "agendas":[{"arquivo","dono"}]}
    (caminhos relativos a pasta). Sem caso.json, usa a convencao do caso demo."""
    pasta = Path(pasta)
    mf = pasta / "caso.json"
    if mf.exists():
        try:
            cfg = json.loads(mf.read_text(encoding="utf-8"))
        except ValueError as e:
            raise ValueError(f"caso.json inválido em {pasta}: {e}")
    else:
        cfg = {"titulo": "Demonstração — licitação de frota (dados sintéticos)",
               "reportagens": [p.name for p in sorted(pasta.glob("reportagem_*.txt"))],
               "oficial": "registros_oficiais_demo.csv", "chamadas": "chamadas_demo.csv",
               "agendas": [{"arquivo": "agenda_marina.vcf", "dono": "Marina Duarte Lopes"},
                           {"arquivo": "agenda_ricardo.csv", "dono": "Ricardo Tavares Neto"}]}
    arqs = [pasta / r for r in cfg.get("reportagens", [])]
    faltam = [str(a) for a in arqs if not a.exists()]
    if faltam or not (arqs or cfg.get("chamadas") or cfg.get("agendas")):
        raise FileNotFoundError("Caso não encontrado ou incompleto em %s %s" % (pasta, faltam))
    d = extrair(arqs, cfg.get("titulo", "Mapa de Vínculos")) if arqs else grafo_vazio()
    d["meta"]["titulo"] = cfg.get("titulo", d["meta"].get("titulo"))
    for chave, fn in (("oficial", importar_oficial), ("chamadas", importar_chamadas)):
        nome = cfg.get(chave)
        if nome and (pasta / nome).exists():
            d = fn(d, (pasta / nome).read_text(encoding="utf-8-sig"), nome)
    for ag in cfg.get("agendas", []):
        p = pasta / ag["arquivo"]
        if p.exists():
            d = importar_agenda(d, p.read_text(encoding="utf-8-sig"), ag["arquivo"], ag.get("dono"))
    return finalizar(d)


def montar_demo(pasta):
    return montar_caso(pasta)


def resumo(d):
    c = cruzamentos(d)
    print(f"{len(d['entidades'])} entidades · {len(d['vinculos'])} vínculos · {len(c)} cruzamentos")
    ids = {e['id']: e for e in d["entidades"]}
    for x in c:
        print(f"  [{x['score']}] {x['tipo']}: {ids[x['no']]['rotulo']} liga {', '.join(ids[i]['rotulo'] for i in x['liga'])}")
    rv = [e for e in d["entidades"] if e.get("revisar")]
    if rv:
        print(f"  A revisar ({len(rv)}): " + "; ".join(e["rotulo"] for e in rv))


def relatorio_texto(d, sem_inferencia=False):
    """Painel de analise em texto (CLI): grupos, pontes, sobreposicoes, alertas, contradicoes, tempo e selo."""
    tipos = ("Oficial", "Declarado") if sem_inferencia else A.TODOS
    rot = {e["id"]: A.rotulo_curto(e) for e in d["entidades"]}
    com, bet, sob = A.comunidades(d, tipos), A.intermediacao(d, tipos), A.sobreposicao(d, tipos)
    est = d.get("analise") or A.analise_estatica(d)
    L = ["", A.resumo_texto(d), "", "GRUPOS"]
    for g in com["grupos"][:8]:
        L.append(f"  {g['rotulo']}  ({g['tamanho']} nós)")
    L.append("PONTES (maior intermediação)")
    for i in sorted((i for i in bet if bet[i] > 0), key=lambda i: (-bet[i], i))[:5]:
        L.append(f"  {bet[i]:.3f}  {rot[i]}")
    L.append("SOBREPOSIÇÃO ENTRE PARTES")
    for s_ in sob[:6]:
        L.append(f"  {rot[s_['a']]} × {rot[s_['b']]}: {len(s_['comum'])} em comum (Jaccard {s_['jaccard']})")
    L.append("ALERTAS")
    for s_ in A.sinais_vivos(d, tipos):
        L.append(f"  [{s_['nivel']}] {s_['titulo']}")
    for c in est.get("contradicoes", []):
        L.append(f"  [contradição/{c['gravidade']}] {c['titulo']}")
    for c in est.get("sinais_tempo", []):
        L.append(f"  [tempo] {c['titulo']}")
    for c in est.get("numeros_sequenciais", []):
        L.append(f"  [números sequenciais] {', '.join(n.split(' [')[0] for n in c['numeros'])}")
    for c in est.get("contatos_comuns", []):
        L.append(f"  [contatos em comum] {rot[c['a']]} e {rot[c['b']]} têm {len(c['nos'])} número(s)/e-mail(s) salvos nas duas agendas")
    for c in est.get("apelidos", []):
        L.append(f"  [nomes diferentes no mesmo número] {c['numero'].split(' [')[0]}: {' / '.join(c['nomes'])}")
    v = A.verificar(d) if d.get("selo") else None
    L.append("SELO: " + (f"{v['estado']} — {v['detalhe']}" if v else "sem selo"))
    L.append("Lembrete: alertas são indícios para investigar, não conclusões.")
    return "\n".join(L)


def _montar(x):
    """Extrai textos (opcionais) + oficial + chamadas + agendas dos argumentos da linha de comando."""
    dic = carregar_dicionario(x.dicionario) if x.dicionario else None
    d = extrair(x.arquivos, x.titulo, dic) if x.arquivos else extrair_textos([], x.titulo)
    if x.oficial:
        d = importar_oficial(d, Path(x.oficial).read_text(encoding="utf-8-sig"), Path(x.oficial).name)
    if x.chamadas:
        d = importar_chamadas(d, Path(x.chamadas).read_text(encoding="utf-8-sig"), Path(x.chamadas).name)
    for ag in x.agenda or []:
        arq, _, dono = ag.partition("=")
        d = importar_agenda(d, Path(arq).read_text(encoding="utf-8-sig"), Path(arq).name, dono.strip() or None)
    return finalizar(d)


def diagnostico():
    """Autoteste em 1 comando: ambiente, arquivos, porta, escrita e caso demo (gabarito 25/60/6 + selo)."""
    import tempfile
    base = Path(__file__).resolve().parent
    res = []

    def ok(nome, bom, detalhe=""):
        res.append(bom)
        print(f"  [{'OK ' if bom else 'FALHA'}] {nome}" + (f" — {detalhe}" if detalhe else ""))
    print(f"\nVINCULA {VERSAO} — diagnóstico\n")
    ok("Python 3.8 ou mais novo", sys.version_info >= (3, 8), sys.version.split()[0])
    ok("Modelo do mapa presente", (base / "mapa_template.html").exists())
    ok("Módulo de análise presente", (base / "vincula_analise.py").exists())
    ok("Caso demo presente", (base / "caso_demo" / "caso.json").exists())
    try:
        s = ThreadingHTTPServer(("127.0.0.1", 0), Manipulador)
        ok("Porta local disponível", True, "127.0.0.1:%d" % s.server_address[1])
        s.server_close()
    except OSError as e:
        ok("Porta local disponível", False, str(e))
    try:
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "x.txt").write_text("ok", encoding="utf-8")
        ok("Permissão de escrita", True)
    except OSError as e:
        ok("Permissão de escrita", False, str(e))
    try:
        d = montar_caso(base / "caso_demo")
        n = (len(d["entidades"]), len(d["vinculos"]), len(cruzamentos(d)))
        ok("Caso demo: 25 entidades · 60 vínculos · 6 cruzamentos", n == (25, 60, 6), "obtido %s·%s·%s" % n)
        h = gerar_html(d)
        ok("Mapa HTML gerado", "__DADOS__" not in h and len(h) > 20000, "%d KB" % (len(h) // 1024))
        v = A.verificar(d)
        ok("Selo de integridade (SHA-256)", v["estado"] == "íntegro", v["estado"])
        d["entidades"][0]["rotulo"] += " X"
        ok("Selo detecta adulteração", A.verificar(d)["estado"] != "íntegro")
    except Exception as e:  # diagnostico nunca deve quebrar sem explicar
        ok("Execução do caso demo", False, repr(e))
    bom = all(res)
    print("\n" + ("Tudo certo: pode usar." if bom else "Há falhas acima: corrija e rode de novo (veja o Guia, seção Problemas)."))
    return 0 if bom else 1


def main(argv=None):
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")   # consoles Windows antigos
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd")
    a = sp.add_parser("abrir"); a.add_argument("--porta", type=int, default=8765); a.add_argument("--sem-navegador", action="store_true")
    for nome, padrao in (("extrair", "rede.json"), ("gerar", "mapa_vinculos.html")):
        e = sp.add_parser(nome); e.add_argument("arquivos", nargs="*"); e.add_argument("-o", default=padrao)
        e.add_argument("--titulo", default="Mapa de Vínculos"); e.add_argument("--oficial"); e.add_argument("--dicionario")
        e.add_argument("--chamadas", help="CSV de chamadas: origem,destino[,data,duracao]")
        e.add_argument("--agenda", action="append", help="agenda .vcf/.csv; use arquivo=Nome do dono (repetível)")
    m = sp.add_parser("mapa"); m.add_argument("json"); m.add_argument("-o", default="mapa_vinculos.html"); m.add_argument("--oficial")
    dm = sp.add_parser("demo"); dm.add_argument("-o")
    cs = sp.add_parser("caso", help="monta o mapa de uma pasta com caso.json (ver casos/)"); cs.add_argument("pasta"); cs.add_argument("-o")
    sp.add_parser("diagnostico", help="verifica se o seu computador está pronto e se tudo funciona")
    an = sp.add_parser("analisar"); an.add_argument("arquivo"); an.add_argument("--sem-inferencia", action="store_true")
    ca = sp.add_parser("caminho"); ca.add_argument("arquivo"); ca.add_argument("de"); ca.add_argument("para"); ca.add_argument("--forte", action="store_true")
    ex = sp.add_parser("exportar"); ex.add_argument("arquivo"); ex.add_argument("--formato", default="stix"); ex.add_argument("-o", default=".")
    ve = sp.add_parser("verificar"); ve.add_argument("arquivo")
    x = ap.parse_args(argv)
    if x.cmd in (None, "abrir"):
        servir(getattr(x, "porta", 8765), not getattr(x, "sem_navegador", False))
    elif x.cmd in ("extrair", "gerar"):
        if not (x.arquivos or x.chamadas or x.agenda):
            raise SystemExit("Informe ao menos uma reportagem, --chamadas ou --agenda.")
        d = _montar(x)
        if x.cmd == "extrair":
            Path(x.o).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            Path(x.o).write_text(gerar_html(d), encoding="utf-8")
        resumo(d)
        print(f"-> {x.o}\nRevise nomes de pessoas marcados 'a revisar' antes de concluir qualquer coisa.")
    elif x.cmd == "mapa":
        d = ler_dados(x.json)
        if x.oficial:
            d = finalizar(importar_oficial(d, Path(x.oficial).read_text(encoding="utf-8-sig"), Path(x.oficial).name))
        Path(x.o).write_text(gerar_html(d), encoding="utf-8")
        resumo(d)
        print(f"-> {x.o}")
    elif x.cmd == "demo":
        pasta = Path(__file__).resolve().parent / "caso_demo"
        d = montar_demo(pasta)
        saida = Path(x.o) if x.o else pasta / "mapa_demo.html"
        saida.write_text(gerar_html(d), encoding="utf-8")
        resumo(d)
        print(f"-> {saida}")
    elif x.cmd == "caso":
        pasta = Path(x.pasta)
        try:
            d = montar_caso(pasta)
        except (FileNotFoundError, ValueError) as err:
            raise SystemExit(str(err))
        saida = Path(x.o) if x.o else pasta / "mapa.html"
        saida.write_text(gerar_html(d), encoding="utf-8")
        resumo(d)
        print(f"-> {saida}")
    elif x.cmd == "diagnostico":
        raise SystemExit(diagnostico())
    elif x.cmd == "analisar":
        d = ler_dados(x.arquivo)
        print(relatorio_texto(d, x.sem_inferencia))
    elif x.cmd == "caminho":
        d = ler_dados(x.arquivo)
        try:
            a_, b_ = achar_entidade(d, x.de), achar_entidade(d, x.para)
        except ValueError as err:
            raise SystemExit(str(err))
        c = A.caminho(d, a_["id"], b_["id"], x.forte)
        print(A.frase_caminho(d, c))
    elif x.cmd == "exportar":
        d = ler_dados(x.arquivo)
        pasta = Path(x.o)
        pasta.mkdir(parents=True, exist_ok=True)
        for nome, conteudo, _m in A.exportar(d, x.formato):
            (pasta / nome).write_text(conteudo, encoding="utf-8")
            print("->", pasta / nome)
    elif x.cmd == "verificar":
        v = A.verificar(ler_dados(x.arquivo))
        print(f"{v['estado'].upper()}: {v['detalhe']}")
        raise SystemExit(0 if v["integro"] else 2)


if __name__ == "__main__":
    main()
