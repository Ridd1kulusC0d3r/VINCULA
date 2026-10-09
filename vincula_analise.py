# -*- coding: utf-8 -*-
"""VINCULA 2.0 - motor de analise (somente biblioteca padrao).

Funcoes puras sobre o grafo em formato dict (o mesmo JSON que o mapa carrega):
  cruzamentos, comunidades, intermediacao, caminho, sobreposicao, sinais_vivos,
  analise_estatica (contradicoes, cronologia, numeros sequenciais, apelidos, raiz de CNPJ, sinais de tempo),
  selar/verificar (selo de integridade com cadeia SHA-256), exportar (STIX 2.1, GraphML, CSV, Mermaid),
  resumo_texto.

As funcoes de rede (comunidades, intermediacao, caminho, sobreposicao, cruzamentos) tem gemeas identicas em
JavaScript no mapa; os testes comparam as duas implementacoes para garantir o mesmo resultado.
"""
import csv, hashlib, heapq, io, json, math, re, unicodedata, uuid
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from itertools import combinations
from xml.sax.saxutils import escape as xesc

PESO = {"Oficial": 3, "Declarado": 2, "Inferência": 1}
CUSTO = {3: 2, 2: 3, 1: 6}          # custo inteiro de um elo: 6/peso (evidencia forte = caminho curto)
TODOS = ("Oficial", "Declarado", "Inferência")
DONOS = ("pessoa", "empresa", "consorcio")
IDENT = ("telefone", "email", "endereco")
CONF_STIX = {"Oficial": 85, "Declarado": 50, "Inferência": 15}

UF_DDD = {}
for _uf, _ddds in {
    "SP": "11 12 13 14 15 16 17 18 19", "RJ": "21 22 24", "ES": "27 28", "MG": "31 32 33 34 35 37 38",
    "PR": "41 42 43 44 45 46", "SC": "47 48 49", "RS": "51 53 54 55", "DF": "61", "GO": "62 64", "TO": "63",
    "MT": "65 66", "MS": "67", "AC": "68", "RO": "69", "BA": "71 73 74 75 77", "SE": "79", "PE": "81 87",
    "AL": "82", "PB": "83", "RN": "84", "CE": "85 88", "PI": "86 89", "PA": "91 93 94", "AM": "92 97",
    "RR": "95", "AP": "96", "MA": "98 99"}.items():
    for _d in _ddds.split():
        UF_DDD[_d] = _uf


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


CUE_SOCIO_REL = re.compile(r"s[oó]ci[oa]s?|administrador|integra")
RX_FIM = re.compile(r"\b(ex-?\s?socio\w*|ex-?\s?socia\w*|ex-?administrador\w*|retirou|retirada|saiu|saida|desligad\w*|"
                    r"baixad\w*|encerrad\w*|ex-?diretor\w*)\b")
RX_EVENTO = re.compile(r"\b(licitac\w*|contrat\w*|aditiv\w*|venceu|vencedor\w*|assin\w*|homologad\w*|pregao|dispensa|"
                       r"adjudicad\w*)\b")


# ---------------------------------------------------------------- estrutura base
def _tipos(d):
    return {e["id"]: e["tipo"] for e in d["entidades"]}


def _rot(d):
    return {e["id"]: e["rotulo"] for e in d["entidades"]}


def rotulo_curto(e):
    return re.sub(r"\s*\[.*?\]", "", e["rotulo"])


AGENDA = "tem na agenda"


def incidentes(d):
    """{id: [vinculos que tocam o no]} - evita varrer todos os vinculos para cada entidade."""
    inc = defaultdict(list)
    for v in d["vinculos"]:
        inc[v["de"]].append(v)
        if v["para"] != v["de"]:
            inc[v["para"]].append(v)
    return inc


def adjacencia(d, tipos=TODOS, sem_agenda=False):
    """(ids ordenados, {id: {vizinho: peso maximo}}) - grafo nao dirigido, sem laços nem duplicatas.
    sem_agenda=True ignora 'tem na agenda' (ter um contato salvo nao e ser o titular do numero)."""
    ids = sorted(e["id"] for e in d["entidades"])
    w = {i: {} for i in ids}
    for v in d["vinculos"]:
        if v["tipo"] not in tipos or (sem_agenda and v["rotulo"] == AGENDA):
            continue
        a, b = v["de"], v["para"]
        if a == b or a not in w or b not in w:
            continue
        p = PESO[v["tipo"]]
        w[a][b] = max(w[a].get(b, 0), p)
        w[b][a] = w[a][b]
    return ids, w


# ---------------------------------------------------------------- cruzamentos (pivôs)
def _partes_independentes(donos, viz, tipo):
    """Quantas 'partes' distintas ha entre os donos: pessoa + a propria empresa (socio/administrador) contam como uma so."""
    pai = {x: x for x in donos}

    def raiz(x):
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x
    for x in donos:
        if tipo.get(x) != "pessoa":
            continue
        for o, v in viz.get(x, ()):
            if o in pai and tipo.get(o) in ("empresa", "consorcio") and v["tipo"] != "Inferência" and CUE_SOCIO_REL.search(norm(v["rotulo"])) and "integra" not in norm(v["rotulo"]):
                pai[raiz(x)] = raiz(o)
    return len({raiz(x) for x in donos})


def cruzamentos(d):
    """Pontos de cruzamento: identificador ligado a 2+ donos; pessoa ligada a 2+ empresas (socio em comum).
    score = soma das evidencias (3/2/1); forca = score / (partes - 1): pivo que liga muita gente informa menos."""
    tipo = _tipos(d)
    viz = {}
    for v in d["vinculos"]:
        viz.setdefault(v["de"], []).append((v["para"], v))
        viz.setdefault(v["para"], []).append((v["de"], v))
    out = []
    for i, ls in viz.items():
        if tipo.get(i) in IDENT:
            donos = {}
            for o, v in ls:
                if tipo.get(o) in DONOS and v["rotulo"] != AGENDA:
                    donos[o] = max(donos.get(o, 0), PESO[v["tipo"]])
            if len(donos) >= 2 and _partes_independentes(donos, viz, tipo) >= 2:
                s = sum(donos.values())
                out.append({"no": i, "tipo": "identificador compartilhado", "liga": sorted(donos), "score": s,
                            "forca": round(s / (len(donos) - 1), 2)})
        elif tipo.get(i) == "pessoa":
            emp = {}
            for o, v in ls:
                if tipo.get(o) in ("empresa", "consorcio") and CUE_SOCIO_REL.search(norm(v["rotulo"])):
                    emp[o] = max(emp.get(o, 0), PESO[v["tipo"]])
            if len(emp) >= 2:
                s = sum(emp.values())
                out.append({"no": i, "tipo": "sócio em comum", "liga": sorted(emp), "score": s,
                            "forca": round(s / (len(emp) - 1), 2)})
    return sorted(out, key=lambda c: (-c["score"], c["no"]))


# ---------------------------------------------------------------- grupos (propagacao de rotulos)
def comunidades(d, tipos=TODOS):
    """Deteccao de grupos por propagacao de rotulos ponderada (deterministica). Nos sem ligacao ficam em grupo 0."""
    ids, w = adjacencia(d, tipos)
    lab = {i: i for i in ids}
    for _ in range(50):
        mudou = False
        for i in ids:
            if not w[i]:
                continue
            soma = {}
            for j, p in w[i].items():
                soma[lab[j]] = soma.get(lab[j], 0) + p
            melhor = max(soma.values())
            cands = sorted(l for l, s in soma.items() if s == melhor)
            novo = lab[i] if lab[i] in cands else cands[0]
            if novo != lab[i]:
                lab[i] = novo
                mudou = True
        if not mudou:
            break
    por = defaultdict(list)
    for i in ids:
        if w[i]:
            por[lab[i]].append(i)
    tipo, rot = _tipos(d), _rot(d)
    ordem = sorted(por.values(), key=lambda m: (-len(m), m[0]))
    grupo = {i: 0 for i in ids}
    grupos = []
    for n, m in enumerate(ordem, 1):
        for i in m:
            grupo[i] = n
        topo = sorted((i for i in m if tipo[i] in DONOS), key=lambda i: (-len(w[i]), i))[:2]
        grupos.append({"n": n, "membros": m, "tamanho": len(m),
                       "rotulo": "Grupo %d — %s" % (n, ", ".join(re.sub(r"\s*\[.*?\]", "", rot[i]) for i in topo) or "sem donos")})
    return {"grupo": grupo, "grupos": grupos}


# ---------------------------------------------------------------- pontes (intermediacao de Brandes)
EXATO_ATE = 800     # acima disso a intermediacao e aproximada por amostragem de origens (mesma regra no JS)
PIVOS_ALVO = 300


_CACHE = {}


def _memo(nome, d, tipos, calcula):
    """Memoriza o ultimo resultado por conteudo do grafo (a mesma analise e pedida varias vezes por geracao)."""
    chave = (nome, tuple(tipos), hashlib.md5(("|".join(sorted(e["id"] for e in d["entidades"])) + "#" + "|".join(sorted(
        "%s>%s>%s>%s" % (v["de"], v["para"], v["tipo"], v["rotulo"] == AGENDA) for v in d["vinculos"]))).encode("utf-8")).hexdigest())
    if chave not in _CACHE:
        if len(_CACHE) > 8:
            _CACHE.clear()
        _CACHE[chave] = calcula()
    return _CACHE[chave]


def intermediacao(d, tipos=TODOS):
    ids = len(d["entidades"])
    if ids <= EXATO_ATE:
        return _intermediacao(d, tipos)
    return _memo("bet", d, tipos, lambda: _intermediacao(d, tipos))


def _intermediacao(d, tipos=TODOS):
    """Intermediacao de Brandes (normalizada). Exata ate EXATO_ATE nos; acima disso usa ~PIVOS_ALVO origens
    igualmente espacadas na ordem dos ids (deterministico) e reescala: aproximacao boa para achar as pontes."""
    ids, w = adjacencia(d, tipos)
    n = len(ids)
    pos = {i: k for k, i in enumerate(ids)}
    adj = [[pos[u] for u in w[i]] for i in ids]
    cb = [0.0] * n
    passo = 1 if n <= EXATO_ATE else -(-n // PIVOS_ALVO)
    origens = range(0, n, passo)
    escala = n / len(origens) if passo > 1 else 1.0
    for s in origens:
        S = []
        P = [[] for _ in range(n)]
        sig = [0] * n
        dist = [-1] * n
        sig[s], dist[s] = 1, 0
        q = deque([s])
        while q:
            v = q.popleft()
            S.append(v)
            dv = dist[v] + 1
            for u in adj[v]:
                if dist[u] < 0:
                    dist[u] = dv
                    q.append(u)
                if dist[u] == dv:
                    sig[u] += sig[v]
                    P[u].append(v)
        delta = [0.0] * n
        while S:
            u = S.pop()
            coef = (1 + delta[u]) / sig[u]
            for v in P[u]:
                delta[v] += sig[v] * coef
            if u != s:
                cb[u] += delta[u]
    f = escala / ((n - 1) * (n - 2)) if n > 2 else 0.0
    return {i: cb[pos[i]] * f for i in ids}


# ---------------------------------------------------------------- caminho entre dois nos
def caminho(d, a, b, forte=False):
    """Caminho de menor custo (evidencia forte = elo curto). forte=True ignora Inferencia."""
    tipos = ("Oficial", "Declarado") if forte else TODOS
    ids, w = adjacencia(d, tipos)
    if a not in w or b not in w:
        return None
    INF = 10 ** 9
    custo = {i: INF for i in ids}
    saltos = {i: INF for i in ids}
    ant = {}
    custo[a], saltos[a] = 0, 0
    feito = set()
    fila = [(0, 0, a)]
    while fila:
        c0, s0, u = heapq.heappop(fila)
        if u in feito:
            continue
        feito.add(u)
        if u == b:
            break
        for v, p in sorted(w[u].items()):
            c, sl = c0 + CUSTO[p], s0 + 1
            if (c, sl) < (custo[v], saltos[v]):
                custo[v], saltos[v] = c, sl
                ant[v] = u
                heapq.heappush(fila, (c, sl, v))
    if custo[b] >= INF:
        return None
    nos = [b]
    while nos[-1] != a:
        nos.append(ant[nos[-1]])
    nos.reverse()
    elos = []
    for x, y in zip(nos, nos[1:]):
        melhores = [v for v in d["vinculos"] if v["tipo"] in tipos and {v["de"], v["para"]} == {x, y}]
        v = sorted(melhores, key=lambda v: (-PESO[v["tipo"]], v["rotulo"], v["de"]))[0]
        elos.append({"de": x, "para": y, "tipo": v["tipo"], "rotulo": v["rotulo"], "fonte": (v.get("evidencias") or [{}])[0].get("fonte", "")})
    fraco = min(elos, key=lambda e: PESO[e["tipo"]])["tipo"] if elos else None
    return {"nos": nos, "elos": elos, "custo": custo[b], "elo_mais_fraco": fraco}


def frase_caminho(d, c):
    rot = {e["id"]: rotulo_curto(e) for e in d["entidades"]}
    if not c:
        return "Não há caminho entre as duas entidades com as evidências disponíveis."
    p = [rot[c["nos"][0]]]
    for e, n in zip(c["elos"], c["nos"][1:]):
        p.append("—[%s · %s]→ %s" % (e["rotulo"], e["tipo"], rot[n]))
    return " ".join(p) + " (elo mais fraco: %s)" % c["elo_mais_fraco"]


# ---------------------------------------------------------------- sobreposicao entre donos
def sobreposicao(d, tipos=TODOS, minimo=2):
    """Pares de donos (pessoa/empresa/consorcio) que compartilham >= `minimo` vizinhos (telefone, endereco, socio...)."""
    tipo = _tipos(d)
    ids, w = adjacencia(d, tipos, sem_agenda=True)
    eh_dono = {i: tipo[i] in DONOS for i in ids}
    pares = defaultdict(list)
    for c in ids:                                   # indice invertido: cada vizinho "empurra" seus pares de donos
        # vizinho-dono so conta se a ligacao for declarada/oficial: co-citacao em lista ("A, B, C e D") cria cliques artificiais
        ds = [x for x in w[c] if eh_dono[x] and (not eh_dono[c] or w[c][x] >= 2)]
        if len(ds) < 2:
            continue
        ds.sort()
        for x in range(len(ds)):
            for y in range(x + 1, len(ds)):
                pares[(ds[x], ds[y])].append(c)
    out = []
    for (a, b), comum in pares.items():
        if len(comum) < minimo:
            continue
        uniao = len((set(w[a]) | set(w[b])) - {a, b})
        out.append({"a": a, "b": b, "comum": comum, "identificadores": [c for c in comum if tipo[c] in IDENT],
                    "jaccard": round(len(comum) / uniao, 3) if uniao else 0.0,
                    "peso": sum(min(w[a][c], w[b][c]) for c in comum)})
    return sorted(out, key=lambda s: (-s["peso"], -len(s["comum"]), s["a"], s["b"]))


# ---------------------------------------------------------------- alertas "vivos" (recalculados a cada edicao)
def sinais_vivos(d, tipos=TODOS, pre=None):
    pre = pre or {}
    tipo, rot = _tipos(d), {e["id"]: rotulo_curto(e) for e in d["entidades"]}
    ids, w = adjacencia(d, tipos, sem_agenda=True)
    ida, wa = adjacencia(d, tipos)
    com = pre.get("grupos") or comunidades(d, tipos)
    bet = pre.get("intermediacao") or intermediacao(d, tipos)
    out = []
    for s in (pre.get("sobreposicao") if pre.get("sobreposicao") is not None else sobreposicao(d, tipos))[:10]:
        if s["peso"] < 4:          # so co-citacoes (Inferencia): nao vira alerta
            continue
        alto = (len(s["comum"]) >= 3 or len(s["identificadores"]) >= 2) and s["peso"] >= 6
        out.append({"nivel": "alto" if alto else "médio", "tipo": "sobreposição",
                    "titulo": "%s e %s compartilham %d pontos" % (rot[s["a"]], rot[s["b"]], len(s["comum"])),
                    "detalhe": "em comum: " + "; ".join(rot[c] for c in s["comum"]), "nos": [s["a"], s["b"]] + s["comum"]})
    for i in ids:
        if tipo[i] in IDENT:
            donos = [j for j in w[i] if tipo[j] in DONOS]
            if len(donos) >= 4:
                out.append({"nivel": "info", "tipo": "alta densidade",
                            "titulo": "%s liga %d partes" % (rot[i], len(donos)),
                            "detalhe": "identificador muito compartilhado costuma ser escritório virtual, contabilidade ou número "
                                       "genérico: peso menor como indício", "nos": [i] + donos})
    top = sorted((i for i in ids if bet[i] > 0), key=lambda i: (-bet[i], i))[:5]
    for i in top:
        gs = {com["grupo"][j] for j in wa[i] if com["grupo"][j]}
        if len(gs) >= 2:
            out.append({"nivel": "médio", "tipo": "ponte", "titulo": "%s faz ponte entre %d grupos" % (rot[i], len(gs)),
                        "detalhe": "intermediação %.2f: sem esta entidade os grupos ficam desconectados" % bet[i], "nos": [i]})
    # parentesco entre pessoas ligadas a empresas diferentes (padrao classico em fraude de licitacao)
    empresas_de = defaultdict(set)
    for v in d["vinculos"]:
        if v["tipo"] != "Inferência" and CUE_SOCIO_REL.search(norm(v["rotulo"])) and "integra" not in norm(v["rotulo"]):
            for x, y in ((v["de"], v["para"]), (v["para"], v["de"])):
                if tipo.get(x) == "pessoa" and tipo.get(y) in ("empresa", "consorcio"):
                    empresas_de[x].add(y)
    for v in d["vinculos"]:
        if v["rotulo"].startswith("parente") and v["tipo"] != "Inferência" and v["de"] in empresas_de and v["para"] in empresas_de:
            ea, eb = empresas_de[v["de"]], empresas_de[v["para"]]
            if ea != eb and not (ea & eb):
                out.append({"nivel": "alto", "tipo": "parentesco", "titulo": "%s e %s são parentes e ligados a empresas diferentes" % (rot[v["de"]], rot[v["para"]]),
                            "detalhe": "%s · empresas: %s × %s — parentesco entre sócios de concorrentes é um indício clássico em licitações" % (
                                v["rotulo"], ", ".join(sorted(rot[x] for x in ea)), ", ".join(sorted(rot[x] for x in eb))),
                            "nos": [v["de"], v["para"]] + sorted(ea | eb)})
    for e in d["entidades"]:
        if e.get("aviso"):
            out.append({"nivel": "info", "tipo": "documento", "titulo": "%s: %s" % (rotulo_curto(e), e["aviso"]),
                        "detalhe": "provável erro de digitação na fonte ou documento inventado", "nos": [e["id"]]})
    ordem = {"alto": 0, "médio": 1, "info": 2}
    return sorted(out, key=lambda s: ordem[s["nivel"]])


# ---------------------------------------------------------------- datas e cronologia
def data_ord(iso):
    return date.fromisoformat(iso[:10])


def cronologia(d):
    rot = {e["id"]: rotulo_curto(e) for e in d["entidades"]}
    ev = []
    for v in d["vinculos"]:
        for e in v.get("evidencias", []):
            if e.get("data"):
                ev.append({"data": e["data"], "prec": e.get("prec", "d"), "tipo": v["tipo"], "de": v["de"], "para": v["para"],
                           "rotulo": v["rotulo"], "fonte": e.get("fonte", ""), "trecho": e.get("trecho", ""),
                           "texto": "%s → %s: %s" % (rot.get(v["de"], "?"), rot.get(v["para"], "?"), v["rotulo"])})
    return sorted(ev, key=lambda x: (x["data"], x["texto"]))


def sinais_tempo(d, janela=180):
    """Vinculo societario com data ate `janela` dias ANTES de um evento contratual da mesma empresa."""
    tipo = _tipos(d)
    rot = {e["id"]: rotulo_curto(e) for e in d["entidades"]}
    out, vistos = [], set()
    inc = incidentes(d)
    evento_ok = {}      # id(evidencia) -> evidencia e evento contratual datado (cache)
    for soc in d["vinculos"]:
        if soc["tipo"] == "Inferência" or not CUE_SOCIO_REL.search(norm(soc["rotulo"])):
            continue
        for es in soc.get("evidencias", []):
            if es.get("prec", "d") not in ("d", "m") or not es.get("data"):
                continue
            for ponta in (soc["de"], soc["para"]):
                if tipo.get(ponta) not in ("empresa", "consorcio"):
                    continue
                for ev in inc.get(ponta, ()):
                    if ev is soc:
                        continue
                    for ee in ev.get("evidencias", []):
                        if ee.get("prec", "d") not in ("d", "m") or not ee.get("data"):
                            continue
                        ok = evento_ok.get(id(ee))
                        if ok is None:
                            ok = evento_ok[id(ee)] = bool(RX_EVENTO.search(norm(ee.get("trecho", ""))))
                        if not ok:
                            continue
                        dias = (data_ord(ee["data"]) - data_ord(es["data"])).days
                        k = (ponta, es["data"], ee["data"])
                        if 0 < dias <= janela and k not in vistos:
                            vistos.add(k)
                            out.append({"empresa": ponta, "dias": dias, "data_vinculo": es["data"], "data_evento": ee["data"],
                                        "titulo": "%s: vínculo societário a %d dias de um evento contratual" % (rot[ponta], dias),
                                        "detalhe": "sociedade %s (%s) · evento %s: “%s”" % (es["data"], es.get("fonte", ""), ee["data"], ee.get("trecho", "")[:140])})
    return out


# ---------------------------------------------------------------- contradicoes
def contradicoes(d):
    tipo = _tipos(d)
    rot = {e["id"]: rotulo_curto(e) for e in d["entidades"]}
    out = []
    por_par = defaultdict(list)
    for v in d["vinculos"]:
        por_par[frozenset((v["de"], v["para"]))].append(v)
    # 1. registro oficial encerra o que a reportagem declara como ativo
    for par, ls in por_par.items():
        fim = [v for v in ls if v["tipo"] == "Oficial" and RX_FIM.search(norm(v["rotulo"]))]
        ativo = [v for v in ls if v["tipo"] == "Declarado" and CUE_SOCIO_REL.search(norm(v["rotulo"]))]
        if fim and ativo:
            a, b = sorted(par)
            out.append({"gravidade": "alta", "tipo": "oficial encerra declarado", "nos": [a, b],
                        "titulo": "%s e %s: o registro oficial indica saída, a reportagem apresenta como vigente" % (rot[a], rot[b]),
                        "detalhe": "oficial: %s · declarado: %s" % (fim[0]["rotulo"], ativo[0]["rotulo"])})
    # 2. mais de um endereco para a mesma empresa, com pelo menos um oficial
    por_dono = defaultdict(list)
    for v in d["vinculos"]:
        for x, y in ((v["de"], v["para"]), (v["para"], v["de"])):
            if tipo.get(x) in ("empresa", "consorcio") and tipo.get(y) == "endereco":
                por_dono[x].append((y, v))
    for x, ls in por_dono.items():
        ends = {y for y, _ in ls}
        if len(ends) >= 2 and any(v["tipo"] == "Oficial" for _, v in ls):
            out.append({"gravidade": "média", "tipo": "endereços divergentes", "nos": [x] + sorted(ends),
                        "titulo": "%s tem %d endereços diferentes nas fontes" % (rot[x], len(ends)),
                        "detalhe": "; ".join("%s (%s)" % (rot[y], v["tipo"]) for y, v in ls) + " — pode ser filial, mudança ou dado errado"})
    # 3. mesma relacao com datas de anos diferentes em fontes diferentes
    for par, ls in por_par.items():
        for v in ls:
            anos = {}
            for e in v.get("evidencias", []):
                if e.get("data"):
                    anos.setdefault(e["data"][:4], set()).add(e.get("fonte", ""))
            if len(anos) >= 2 and v["tipo"] != "Inferência":
                a, b = sorted(par)
                out.append({"gravidade": "média", "tipo": "datas divergentes", "nos": [a, b],
                            "titulo": "%s e %s: %s com datas diferentes (%s)" % (rot[a], rot[b], v["rotulo"], ", ".join(sorted(anos))),
                            "detalhe": "fontes distintas dão datas distintas para a mesma relação"})
    # 4. telefone: titular oficial diferente do que a reportagem declara
    inc = incidentes(d)
    for i, t in tipo.items():
        if t != "telefone":
            continue
        of = {(v["de"] if v["para"] == i else v["para"]) for v in inc.get(i, ()) if v["tipo"] == "Oficial" and tipo.get(v["de"] if v["para"] == i else v["para"]) in DONOS}
        dc = {(v["de"] if v["para"] == i else v["para"]) for v in inc.get(i, ()) if v["tipo"] == "Declarado" and tipo.get(v["de"] if v["para"] == i else v["para"]) in DONOS}
        if of and (dc - of):
            out.append({"gravidade": "média", "tipo": "titularidade divergente", "nos": [i] + sorted(of | dc),
                        "titulo": "%s: reportagem e registro oficial atribuem a donos diferentes" % rot[i],
                        "detalhe": "oficial: %s · declarado: %s" % (", ".join(rot[x] for x in sorted(of)), ", ".join(rot[x] for x in sorted(dc - of)))})
    # 5. mesmo nome, documentos diferentes
    for s in d.get("sugestoes_fusao", []):
        if "documentos distintos" in s[2]:
            out.append({"gravidade": "média", "tipo": "mesmo nome, documentos diferentes", "nos": [s[0], s[1]],
                        "titulo": "%s aparece com dois documentos diferentes" % rot.get(s[0], s[0]), "detalhe": s[2]})
    ordem = {"alta": 0, "média": 1}
    return sorted(out, key=lambda c: (ordem[c["gravidade"]], c["titulo"]))


# ---------------------------------------------------------------- telefones
def info_telefone(e164):
    m = re.match(r"\+55(\d{2})(\d{8,9})$", e164 or "")
    if not m:
        return None
    ddd, num = m.groups()
    return {"ddd": ddd, "uf": UF_DDD.get(ddd, "?"), "tipo": "móvel" if len(num) == 9 else "fixo", "numero": int(ddd + num)}


def numeros_sequenciais(d, folga=10):
    """Grupos de numeros quase consecutivos (mesmo DDD, diferenca <= folga) - tipico de linhas contratadas em bloco."""
    rot = {e["id"]: e["rotulo"] for e in d["entidades"]}
    tels = []
    for e in d["entidades"]:
        if e["tipo"] == "telefone":
            m = re.match(r"telefone:(\+55\d{10,11})$", e["id"])
            inf = info_telefone(m.group(1)) if m else None
            if inf:
                tels.append((inf["ddd"], inf["numero"], e["id"]))
    tels.sort()
    grupos, atual = [], []
    for t in tels:
        if atual and t[0] == atual[-1][0] and 0 < t[1] - atual[-1][1] <= folga:
            atual.append(t)
        else:
            if len(atual) >= 2:
                grupos.append(atual)
            atual = [t]
    if len(atual) >= 2:
        grupos.append(atual)
    tipo = _tipos(d)
    out = []
    for g in grupos:
        ids = [t[2] for t in g]
        donos = sorted({(v["de"] if v["para"] in ids else v["para"]) for v in d["vinculos"] if (v["de"] in ids or v["para"] in ids) and tipo.get(v["de"] if v["para"] in ids else v["para"]) in DONOS})
        out.append({"nos": ids, "numeros": [rot[i] for i in ids], "donos": donos})
    return out


def apelidos_telefone(d):
    """Telefones salvos com nomes diferentes (uma ou mais agendas): possiveis apelidos/alias do mesmo titular."""
    out = []
    for e in d["entidades"]:
        ap = e.get("apelidos") or []
        nomes = {}
        for a in ap:
            nomes.setdefault(norm(a["nome"]), a["nome"])
        if len(nomes) >= 2:
            out.append({"no": e["id"], "numero": e["rotulo"], "nomes": sorted(nomes.values()),
                        "agendas": sorted({a.get("fonte", "") for a in ap})})
    return out


def raizes_cnpj(d):
    por = defaultdict(list)
    for e in d["entidades"]:
        dig = re.sub(r"\D", "", e.get("doc") or "")
        if e["tipo"] == "empresa" and len(dig) == 14:
            por[dig[:8]].append(e["id"])
    return [{"raiz": r, "nos": sorted(v)} for r, v in sorted(por.items()) if len(v) >= 2]


def dispersao_ddd(d):
    """Donos ligados a telefones de 3+ UFs diferentes."""
    tipo = _tipos(d)
    out = []
    inc = incidentes(d)
    for e in d["entidades"]:
        if e["tipo"] not in DONOS:
            continue
        ufs = set()
        for v in inc.get(e["id"], ()):
            o = v["para"] if v["de"] == e["id"] else (v["de"] if v["para"] == e["id"] else None)
            if o and tipo.get(o) == "telefone":
                m = re.match(r"telefone:(\+55\d{10,11})$", o)
                inf = info_telefone(m.group(1)) if m else None
                if inf:
                    ufs.add(inf["uf"])
        if len(ufs) >= 3:
            out.append({"no": e["id"], "ufs": sorted(ufs)})
    return out


def contatos_comuns(d):
    """Numeros/e-mails salvos em 2+ agendas diferentes, agrupados por par de donos de agenda."""
    tipo = _tipos(d)
    por = defaultdict(set)
    for v in d["vinculos"]:
        if v["rotulo"] == AGENDA and tipo.get(v["para"]) in IDENT:
            por[v["para"]].add(v["de"])
    pares = defaultdict(list)
    for i, donos in por.items():
        for a, b in combinations(sorted(donos), 2):
            pares[(a, b)].append(i)
    return [{"a": a, "b": b, "nos": sorted(n)} for (a, b), n in sorted(pares.items(), key=lambda kv: (-len(kv[1]), kv[0]))]


def analise_estatica(d):
    return {"contatos_comuns": contatos_comuns(d), "contradicoes": contradicoes(d), "sinais_tempo": sinais_tempo(d), "numeros_sequenciais": numeros_sequenciais(d),
            "apelidos": apelidos_telefone(d), "raizes_cnpj": raizes_cnpj(d), "dispersao_ddd": dispersao_ddd(d)}


def analisar(d, tipos=TODOS):
    com, bet, sob = comunidades(d, tipos), intermediacao(d, tipos), sobreposicao(d, tipos)
    return {"grupos": com, "intermediacao": bet, "sobreposicao": sob,
            "cruzamentos": cruzamentos(d),
            "sinais": sinais_vivos(d, tipos, {"grupos": com, "intermediacao": bet, "sobreposicao": sob}),
            "estatica": analise_estatica(d), "cronologia": cronologia(d)}


# ---------------------------------------------------------------- selo de integridade
def canonico(d):
    """Forma canonica (independe de posicao na tela e de campos calculados). Igual no Python e no navegador."""
    ev = lambda e: {k: e[k] for k in ("fonte", "trecho", "data", "prec") if e.get(k) not in (None, "")}
    base = {
        "fontes": [{"nome": f["nome"], "sha256": f["sha256"], "bytes": f["bytes"]} for f in d.get("meta", {}).get("fontes", [])],
        "entidades": sorted(({"id": e["id"], "tipo": e["tipo"], "rotulo": e["rotulo"]} for e in d["entidades"]),
                            key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))),
        "vinculos": sorted(({"de": v["de"], "para": v["para"], "tipo": v["tipo"], "rotulo": v["rotulo"],
                             "evidencias": sorted((ev(e) for e in v.get("evidencias", [])), key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":")))}
                            for v in d["vinculos"]), key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))),
    }
    return json.dumps(base, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def selar(d):
    h, cadeia = "0" * 64, []
    for f in d.get("meta", {}).get("fontes", []):
        h = _sha(h + f["sha256"])
        cadeia.append({"fonte": f["nome"], "elo": h})
    corpo = _sha(canonico(d))
    return {"algoritmo": "SHA-256", "cadeia": cadeia, "conteudo": corpo, "raiz": _sha(h + corpo),
            "gerado": datetime.now().isoformat(timespec="seconds"), "entidades": len(d["entidades"]), "vinculos": len(d["vinculos"])}


def verificar(d):
    s = d.get("selo")
    if not s:
        return {"estado": "sem selo", "integro": False, "detalhe": "o arquivo não tem selo de integridade"}
    novo = selar(d)
    ok = novo["raiz"] == s["raiz"]
    det = "conteúdo idêntico ao gerado em %s" % s.get("gerado", "?")
    if not ok:
        det = "o conteúdo difere do selado (%d→%d entidades, %d→%d vínculos)" % (s["entidades"], novo["entidades"], s["vinculos"], novo["vinculos"])
        if d.get("meta", {}).get("editado"):
            det += "; edição manual registrada em %s" % d["meta"]["editado"]
    return {"estado": "íntegro" if ok else "alterado", "integro": ok, "detalhe": det, "raiz": s["raiz"]}


# ---------------------------------------------------------------- exportacoes
NS_STIX = uuid.UUID("3b1c4a52-7d1e-5b0a-9a52-5a1f3e0c7a11")


def _uid(tipo, chave):
    return "%s--%s" % (tipo, uuid.uuid5(NS_STIX, tipo + "|" + chave))


def _agora(d):
    g = d.get("meta", {}).get("gerado")
    try:
        t = datetime.fromisoformat(g) if g else datetime.now()
    except ValueError:
        t = datetime.now()
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def exportar_stix(d):
    """STIX 2.1: identity (pessoa/empresa), location (endereco), email-addr, x-phone-number, relationship, report."""
    ts, objs, ids = _agora(d), [], {}
    base = {"spec_version": "2.1", "created": ts, "modified": ts}
    for e in d["entidades"]:
        t = e["tipo"]
        if t in ("pessoa", "empresa", "consorcio"):
            o = {"type": "identity", "id": _uid("identity", e["id"]), "name": rotulo_curto(e),
                 "identity_class": "individual" if t == "pessoa" else "organization", **base}
            if e.get("doc") and t == "empresa":
                o["external_references"] = [{"source_name": "CNPJ", "external_id": e["doc"]}]
            if e.get("aliases"):
                o["x_vincula_aliases"] = e["aliases"]
        elif t == "endereco":
            o = {"type": "location", "id": _uid("location", e["id"]), "name": e["rotulo"], "street_address": e["rotulo"], "country": "BR", **base}
        elif t == "email":
            o = {"type": "email-addr", "id": _uid("email-addr", e["id"]), "value": e["rotulo"]}
        else:
            o = {"type": "x-phone-number", "id": _uid("x-phone-number", e["id"]), "value": e["id"].replace("telefone:", ""),
                 "x_rotulo": e["rotulo"]}
            if e.get("apelidos"):
                o["x_vincula_apelidos"] = [a["nome"] for a in e["apelidos"]]
        ids[e["id"]] = o["id"]
        objs.append(o)
    for n, v in enumerate(d["vinculos"]):
        if v["de"] not in ids or v["para"] not in ids:
            continue
        datas = sorted(e["data"] for e in v.get("evidencias", []) if e.get("data"))
        o = {"type": "relationship", "id": _uid("relationship", "%s|%s|%s|%s|%d" % (v["de"], v["para"], v["tipo"], v["rotulo"], n)),
             "relationship_type": "related-to", "source_ref": ids[v["de"]], "target_ref": ids[v["para"]],
             "description": v["rotulo"], "confidence": CONF_STIX[v["tipo"]], "x_vincula_evidencia": v["tipo"],
             "external_references": [{"source_name": e.get("fonte", "fonte"), "description": e.get("trecho", "")[:200]}
                                     for e in v.get("evidencias", [])] or [{"source_name": "analista"}], **base}
        if datas:
            o["start_time"] = datas[0][:10] + "T00:00:00.000Z"
        objs.append(o)
    rid = _uid("report", d.get("meta", {}).get("titulo", "VINCULA") + ts)
    objs.append({"type": "report", "id": rid, "name": d.get("meta", {}).get("titulo", "Mapa de Vínculos"), "published": ts,
                 "report_types": ["threat-report"], "object_refs": [o["id"] for o in objs], **base,
                 "description": "Exportado do VINCULA. Confiança: Oficial 85, Declarado 50, Inferência 15."})
    return json.dumps({"type": "bundle", "id": _uid("bundle", rid), "objects": objs}, ensure_ascii=False, indent=1)


def exportar_graphml(d):
    com, bet = comunidades(d), intermediacao(d)
    L = ['<?xml version="1.0" encoding="UTF-8"?>', '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">']
    for k, nome, dom, para in (("d0", "tipo", "string", "node"), ("d1", "rotulo", "string", "node"), ("d2", "grupo", "int", "node"),
                               ("d3", "intermediacao", "double", "node"), ("d4", "evidencia", "string", "edge"),
                               ("d5", "natureza", "string", "edge"), ("d6", "peso", "int", "edge"), ("d7", "fontes", "string", "edge")):
        L.append('<key id="%s" for="%s" attr.name="%s" attr.type="%s"/>' % (k, para, nome, dom))
    L.append('<graph id="vincula" edgedefault="undirected">')
    for e in d["entidades"]:
        L.append('<node id="%s"><data key="d0">%s</data><data key="d1">%s</data><data key="d2">%d</data><data key="d3">%.6f</data></node>'
                 % (xesc(e["id"], {'"': "&quot;"}), e["tipo"], xesc(e["rotulo"]), com["grupo"].get(e["id"], 0), bet.get(e["id"], 0)))
    for n, v in enumerate(d["vinculos"]):
        L.append('<edge id="e%d" source="%s" target="%s"><data key="d4">%s</data><data key="d5">%s</data><data key="d6">%d</data><data key="d7">%s</data></edge>'
                 % (n, xesc(v["de"], {'"': "&quot;"}), xesc(v["para"], {'"': "&quot;"}), v["tipo"], xesc(v["rotulo"]), PESO[v["tipo"]],
                    xesc(" | ".join(sorted({e.get("fonte", "") for e in v.get("evidencias", [])})))))
    L += ["</graph>", "</graphml>"]
    return "\n".join(L)


def exportar_csv(d):
    com, bet = comunidades(d), intermediacao(d)
    grau = defaultdict(int)
    for v in d["vinculos"]:
        grau[v["de"]] += 1
        grau[v["para"]] += 1
    a, b = io.StringIO(), io.StringIO()
    w = csv.writer(a, lineterminator="\n")
    w.writerow(["id", "tipo", "rotulo", "documento", "grupo", "intermediacao", "grau"])
    for e in d["entidades"]:
        w.writerow([e["id"], e["tipo"], e["rotulo"], e.get("doc", ""), com["grupo"].get(e["id"], 0), "%.6f" % bet.get(e["id"], 0), grau[e["id"]]])
    w = csv.writer(b, lineterminator="\n")
    w.writerow(["de", "para", "evidencia", "natureza", "n_ligacoes", "primeira_data", "fontes"])
    for v in d["vinculos"]:
        datas = sorted(e["data"] for e in v.get("evidencias", []) if e.get("data"))
        w.writerow([v["de"], v["para"], v["tipo"], v["rotulo"], v.get("n", ""), datas[0] if datas else "",
                    " | ".join(sorted({e.get("fonte", "") for e in v.get("evidencias", [])}))])
    return a.getvalue(), b.getvalue()


def exportar_mermaid(d):
    cor = {"pessoa": "#2f5da8", "empresa": "#5c7a4a", "consorcio": "#2d6a4f", "endereco": "#b8742a", "email": "#7a4fb0", "telefone": "#555"}
    n = {e["id"]: "n%d" % i for i, e in enumerate(d["entidades"])}
    L = ["graph LR"]
    for e in d["entidades"]:
        t = rotulo_curto(e).replace('"', "'")
        L.append('  %s["%s"]:::%s' % (n[e["id"]], t, e["tipo"]))
    for v in d["vinculos"]:
        if v["de"] in n and v["para"] in n:
            seta = {"Oficial": "==>", "Declarado": "-->", "Inferência": "-.->"}[v["tipo"]]
            L.append('  %s %s|"%s"| %s' % (n[v["de"]], seta, v["rotulo"].replace('"', "'"), n[v["para"]]))
    for t, c in cor.items():
        L.append("  classDef %s stroke:%s,stroke-width:2px;" % (t, c))
    return "\n".join(L)


def exportar(d, formato):
    """-> [(nome_arquivo, texto, mime)]"""
    f = formato.lower()
    if f == "stix":
        return [("vincula_stix21.json", exportar_stix(d), "application/json")]
    if f == "graphml":
        return [("vincula.graphml", exportar_graphml(d), "application/xml")]
    if f == "csv":
        n, a = exportar_csv(d)
        return [("vincula_nos.csv", n, "text/csv"), ("vincula_arestas.csv", a, "text/csv")]
    if f == "mermaid":
        return [("vincula.mmd", exportar_mermaid(d), "text/plain")]
    if f == "json":
        return [("rede.json", json.dumps(d, ensure_ascii=False, indent=1), "application/json")]
    raise ValueError("formato desconhecido: %s (use stix, graphml, csv, mermaid ou json)" % formato)


# ---------------------------------------------------------------- resumo em linguagem natural
def fmt_data(iso):
    return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")


def resumo_texto(d):
    ents = d["entidades"]
    n = defaultdict(int)
    for e in ents:
        n[e["tipo"]] += 1
    nv = defaultdict(int)
    for v in d["vinculos"]:
        nv[v["tipo"]] += 1
    com, bet, cr = comunidades(d), intermediacao(d), cruzamentos(d)
    rot = {e["id"]: rotulo_curto(e) for e in ents}
    p = ["O mapa reúne %d entidades (%d pessoas, %d empresas/consórcios, %d telefones, %d endereços, %d e-mails) e %d vínculos: "
         "%d oficiais, %d declarados e %d inferências." % (len(ents), n["pessoa"], n["empresa"] + n["consorcio"], n["telefone"], n["endereco"], n["email"],
                                                         len(d["vinculos"]), nv["Oficial"], nv["Declarado"], nv["Inferência"])]
    if com["grupos"]:
        g = com["grupos"][0]
        p.append("Há %d grupo(s) conectados; o maior (%s) tem %d nós." % (len(com["grupos"]), g["rotulo"].split(" — ", 1)[1], g["tamanho"]))
    if cr:
        p.append("Foram encontrados %d cruzamento(s); o mais forte é %s (liga %s)." % (len(cr), rot[cr[0]["no"]], ", ".join(rot[i] for i in cr[0]["liga"])))
    top = sorted((i for i in bet if bet[i] > 0), key=lambda i: (-bet[i], i))[:1]
    if top:
        p.append("A entidade mais central (maior intermediação) é %s." % rot[top[0]])
    est = d.get("analise") or analise_estatica(d)
    if est["contradicoes"]:
        p.append("Há %d contradição(ões) entre fontes a conferir." % len(est["contradicoes"]))
    if est["sinais_tempo"]:
        p.append("%d vínculo(s) societário(s) ocorreram até 180 dias antes de um evento contratual." % len(est["sinais_tempo"]))
    return " ".join(p)
