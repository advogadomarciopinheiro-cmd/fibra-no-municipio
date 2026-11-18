#!/usr/bin/env python3
"""Generate the static site from processed Anatel/IBGE JSON."""
from __future__ import annotations

import json
import os
import math
import shutil
import sys
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.paths import ASSETS_SRC, DATA_PROCESSED, SITE, ROOT  # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")
SITE_NAME = "Fibra no Município"
MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def load() -> dict:
    def j(name):
        return json.loads((DATA_PROCESSED / name).read_text(encoding="utf-8"))

    return {
        "meta": j("meta.json"),
        "index": j("index.json"),
        "municipios": j("municipios.json"),
        "prestadoras": j("prestadoras.json"),
        "published": j("published.json")["ibge"],
        "nightly": _read_nightly(),
    }


def _read_nightly() -> list:
    path = DATA_PROCESSED / "nightly_log.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and not (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))


def fmt_int(n) -> str:
    if not is_num(n):
        return "—"
    return f"{int(n):,}".replace(",", ".")


def fmt_pct(x, ratio=True) -> str:
    if not is_num(x):
        return "—"
    val = x * 100 if ratio else x
    s = f"{val:.1f}".replace(".", ",")
    return s + "%"


def fmt_num(x, d=1) -> str:
    if not is_num(x):
        return "—"
    return f"{x:.{d}f}".replace(".", ",")


def mes_extenso(ym: str | None) -> str:
    if not ym or "-" not in ym:
        return "—"
    y, m = ym.split("-")
    return f"{MESES[int(m) - 1]} de {y}"


def now_br() -> str:
    return datetime.now(TZ).strftime("%d/%m/%Y %H:%M") + " (horário de Brasília, UTC-3)"



def normalize_base(base: str) -> str:
    base = (base or "/").strip() or "/"
    if not base.startswith("/"):
        base = "/" + base
    if not base.endswith("/"):
        base += "/"
    return base


def get_base_url() -> str:
    return normalize_base(os.environ.get("BASE_URL", "/"))


def get_site_url() -> str:
    return (os.environ.get("SITE_URL") or "").rstrip("/")


def url(path: str = "") -> str:
    """Site-root path under BASE_URL, e.g. /fibra-no-municipio/metodologia.html."""
    base = get_base_url()
    path = (path or "").lstrip("/")
    if path in {"", "index.html"}:
        return base
    return base + path


def abs_url(path: str = "") -> str:
    """Absolute URL when SITE_URL is set; otherwise the BASE_URL path."""
    site = get_site_url()
    path = (path or "").lstrip("/")
    if path in {"index.html"}:
        path = ""
    if site:
        return site + "/" + path if path else site + "/"
    return url(path)


def rel(depth: int, path: str) -> str:
    # depth is ignored: links are always rooted at BASE_URL so GitHub Pages subpaths work.
    return url(path)


def layout(title, description, body, *, depth=0, path="", crumbs=None, extra_head=""):
    root = url("")
    canon = abs_url(path)
    nav = [
        ("index.html", "Início", path in {"", "index.html"}),
        ("ranking.html", "Ranking", path == "ranking.html"),
        ("metodologia.html", "Metodologia", path == "metodologia.html"),
        ("sobre.html", "Sobre", path == "sobre.html"),
        ("privacidade.html", "Privacidade", path == "privacidade.html"),
    ]
    nav_html = "".join(
        f'<a href="{root if href=="index.html" else root+href}"'
        f'{" aria-current=page" if cur else ""}>{lab}</a>'
        for href, lab, cur in nav
    )
    crumbs_html = ""
    if crumbs:
        parts = []
        for label, href in crumbs:
            if href:
                parts.append(f'<a href="{href}">{escape(label)}</a>')
            else:
                parts.append(escape(label))
        crumbs_html = '<nav class="crumbs" aria-label="Trilha">' + " › ".join(parts) + "</nav>"
    schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": canon,
        "inLanguage": "pt-BR",
        "description": "Diretório de prestadoras de banda larga fixa em fibra por município, com dados abertos da Anatel. Este site não é a Anatel.",
    }
    return f"""<!DOCTYPE html>
<html lang="pt-BR" data-root="{escape(root)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(description)}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{escape(canon)}">
  <meta property="og:title" content="{escape(title)}">
  <meta property="og:description" content="{escape(description)}">
  <meta property="og:locale" content="pt_BR">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{escape(canon)}">
  <link rel="stylesheet" href="{url('assets/style.css')}">
  {extra_head}
  <script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
</head>
<body>
  <a class="skip" href="#conteudo">Ir para o conteúdo</a>
  <div class="disclaimer-bar">
    <div class="wrap"><strong>Este site não é a Anatel</strong> e não substitui os canais oficiais.
      Usamos dados abertos da Agência. Não publicamos preços, planos nem cobertura por bairro ou CEP.</div>
  </div>
  <header class="site">
    <div class="wrap">
      <a class="brand" href="{root}">
        <em>Fibra no Município</em>
        <span>Diretório com dados abertos da Anatel</span>
      </a>
      <nav class="site" aria-label="Principal">{nav_html}</nav>
    </div>
  </header>
  <main id="conteudo"><div class="wrap">{crumbs_html}{body}</div></main>
  <footer class="site">
    <div class="wrap">
      <p><strong>Fibra no Município</strong> é um diretório independente. Não somos a Anatel, não vendemos planos e não afirmamos cobertura de rua.</p>
      <p>Fonte principal: Agência Nacional de Telecomunicações (Anatel), dados abertos de acessos do SCM (banda larga fixa). Qualidade: RQUAL e Selos/IQS. População: estimativas do IBGE. <a href="{root}metodologia.html">Metodologia</a> · <a href="{root}privacidade.html">Privacidade</a> · <a href="{root}sobre.html">Sobre</a></p>
      <p>Página gerada em {escape(now_br())}.</p>
    </div>
  </footer>
  <div class="cookie wrap" id="cookie">
    <form>
      <p>Este site não usa cookies de marketing. Só guardamos no seu navegador, se você aceitar, um aviso de que já leu esta nota. Links de afiliados, quando existirem, serão identificados como <strong>Publicidade</strong> (CONAR) e o destino pode definir cookies próprios. Veja a <a href="{root}privacidade.html">política de privacidade</a>.</p>
      <button type="submit">Ok, entendi</button>
    </form>
  </div>
  <script src="{url('assets/app.js')}" defer></script>
</body>
</html>
"""


def affiliate_box() -> str:
    return """
<section class="affiliate" aria-label="Publicidade">
  <div class="publi">Publicidade</div>
  <p>Espaço reservado para indicações de planos de internet, com identificação obrigatória nos termos do Guia CONAR (vigente desde 1º de junho de 2026).</p>
  <div class="placeholder-slot">Ainda não há links de afiliados ou indicação comercial ativos nesta página. Quando houver, o link virá com o rótulo visível de Publicidade. Não inventamos preços nem ofertas.</div>
</section>
"""


def source_block(meta: dict, depth: int) -> str:
    ac = meta["fontes"]["acessos"]
    rq = meta["fontes"]["rqual"]
    se = meta["fontes"]["selos"]
    return f"""
<p class="source">Fontes: Anatel, <a href="{escape(ac['arquivo'])}">acessos de banda larga fixa</a>
(arquivo publicado em {escape(ac.get('last_modified_brasilia') or 'data não informada no cabeçalho HTTP')};
mês de referência dos acessos: {escape(mes_extenso(meta['mes_referencia_acessos']))}).
Qualidade: <a href="{escape(rq['arquivo'])}">indicadores RQUAL</a>
({escape(mes_extenso(meta.get('mes_referencia_rqual')))}; arquivo de {escape(rq.get('last_modified_brasilia') or '—')})
e <a href="{escape(se['arquivo'])}">Selos/IQS</a> (ano-base {escape(str(meta.get('ano_selos') or '—'))}).
População: IBGE, estimativas 2026 (agregado 6579).
<a href="{rel(depth,'metodologia.html')}">Como lemos os dados</a>.</p>
"""


def mix_pills(mapping: dict, total: int | None = None) -> str:
    if not mapping:
        return '<p class="muted">Sem detalhe declarado neste recorte.</p>'
    tot = total or sum(mapping.values()) or 1
    bits = []
    for k, v in list(mapping.items())[:8]:
        bits.append(f"<span>{escape(k)}: {fmt_int(v)} ({fmt_pct(v/tot)})</span>")
    return '<div class="mix">' + "".join(bits) + "</div>"


def write(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def city_url(depth: int, slug: str) -> str:
    return rel(depth, f"municipio/{slug}/")


def prest_url(depth: int, slug: str) -> str:
    return rel(depth, f"prestadora/{slug}/")


def indicators_table(items: list) -> str:
    if not items:
        return '<p class="muted">Não há indicador RQUAL mensal associado a este nome de prestadora neste município, no mês de referência.</p>'
    rows = []
    for it in items:
        badge = "sim" if it.get("estatistica_representativa") else "não"
        res = fmt_num(it.get("resultado"), 2) if is_num(it.get("resultado")) else escape(it.get("resultado_bruto") or "—")
        rows.append(
            "<tr>"
            f"<td>{escape(it.get('indicador') or '')}<br><span class='muted'>{escape(it.get('descricao') or '')}</span></td>"
            f"<td class='num'>{res} {escape(it.get('unidade') or '')}</td>"
            f"<td>{escape(badge)}</td>"
            f"<td>{escape(it.get('ref_inferior') or '—')} / {escape(it.get('ref_superior') or '—')}</td>"
            "</tr>"
        )
    return (
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Indicador</th><th class='num'>Resultado</th><th>Amostra representativa?</th><th>Referências (inf./sup.)</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
        "<p class='muted'>Só consideramos a medição representativa quando a Anatel marca o campo Estatística como SIM. "
        "Valores com amostra não representativa aparecem por transparência, não como nota conclusiva.</p>"
    )


def page_home(data: dict) -> str:
    meta = data["meta"]
    published = set(data["published"])
    cities = [data["municipios"][c] for c in data["published"] if c in data["municipios"]]
    cities.sort(key=lambda c: (-(c.get("populacao") or 0), c["nome"]))
    cards = []
    for c in cities:
        cards.append(
            f'<a class="card" href="{url("municipio/" + c["slug"] + "/")}">'
            f'<h3>{escape(c["nome"])} <span class="pill">{escape(c["uf"])}</span></h3>'
            f'<p>{fmt_int(c["acessos_fibra_pf_internet"])} acessos de internet em fibra para pessoa física · '
            f'{c["prestadoras"] and sum(1 for p in c["prestadoras"] if p["acessos_fibra"]>0)} prestadoras com fibra</p>'
            f'</a>'
        )
    n_pub = len(cities)
    n_all = meta.get("n_municipios_com_acessos")
    body = f"""
    <h1>Quem tem internet em fibra, município a município</h1>
    <p class="lede">Um diretório pequeno e monótono: prestadoras de banda larga fixa com acessos em fibra, a partir dos dados abertos da Anatel. Sem plano, sem preço, sem mapa de rua.</p>
    <div class="search-box">
      <form id="city-form" action="#" method="get">
        <div>
          <label for="q">Buscar município</label>
          <input type="search" id="q" name="q" placeholder="Ex.: Ribeirão Preto" autocomplete="off">
        </div>
        <div>
          <label for="cep">Ou informar um CEP</label>
          <input type="text" id="cep" name="cep" inputmode="numeric" placeholder="00000-000" maxlength="9">
        </div>
        <button type="submit" form="cep-form">Buscar CEP</button>
      </form>
      <form id="cep-form" action="#" method="get"></form>
      <ul id="search-results" class="search-results"></ul>
      <p class="search-note" id="cep-out">O CEP serve só para descobrir o município (consulta à BrasilAPI no seu navegador). A Anatel, neste conjunto, não informa acessos por bairro ou CEP.</p>
    </div>
    <div class="kpis">
      <div class="kpi"><b>{fmt_int(n_pub)}</b><span>municípios com página publicada</span></div>
      <div class="kpi"><b>{fmt_int(n_all)}</b><span>municípios processados na base de acessos</span></div>
      <div class="kpi"><b>{escape(mes_extenso(meta["mes_referencia_acessos"]))}</b><span>mês de referência dos acessos</span></div>
      <div class="kpi"><b>{fmt_int(meta.get("n_prestadoras_com_fibra"))}</b><span>prestadoras com algum acesso em fibra no Brasil</span></div>
    </div>
    <h2>Municípios publicados</h2>
    <p>O conjunto inicial cobre as 20 cidades mais populosas (estimativas do IBGE para 2026) e oito municípios do interior. O roteiro noturno acrescenta uma página por execução, por isso esta lista pode crescer.</p>
    <div class="city-grid">{''.join(cards)}</div>
    {affiliate_box()}
    {source_block(meta, 0)}
    """
    return layout(
        f"{SITE_NAME} — prestadoras de internet fibra por município",
        "Diretório em português com acessos de banda larga fixa em fibra por município e prestadora, a partir de dados abertos da Anatel. Este site não é a Anatel.",
        body,
        depth=0,
        path="index.html",
    )


def page_city(data: dict, city: dict) -> str:
    meta = data["meta"]
    depth = 2
    prests = [p for p in city["prestadoras"] if p["acessos_fibra"] > 0]
    total_pf = city["acessos_fibra_pf_internet"] or 0
    total = city["acessos_total"] or 0
    fibra_share = (city["acessos_fibra"] / total) if total else None
    rows = []
    for p in prests:
        share = p.get("share_fibra_pf_internet")
        selo = (p.get("selo") or {}).get("selo") or "—"
        selo_cls = selo if selo in {"A", "B", "C", "D", "E"} else ""
        bar = int((share or 0) * 100)
        rows.append(
            "<tr>"
            f'<td><a href="{prest_url(depth, p["slug"])}">{escape(p["nome"])}</a><br><span class="muted">{escape(p.get("porte") or "")} · {escape(p.get("grupo") or "")}</span></td>'
            f'<td class="num">{fmt_int(p["acessos_fibra_pf_internet"])}</td>'
            f'<td class="num">{fmt_int(p["acessos_fibra"])}</td>'
            f'<td class="num">{fmt_pct(share)}<div class="bar" aria-hidden="true"><i style="width:{bar}%"></i></div></td>'
            f'<td><span class="selo {selo_cls}">{escape(str(selo))}</span></td>'
            "</tr>"
        )
    # detail for top 8
    details = []
    for p in prests[:8]:
        selo = p.get("selo")
        selo_html = ""
        if selo and selo.get("selo"):
            selo_html = (
                f'<p>Selo municipal de qualidade da Anatel ({escape(str(selo.get("ano")))}), banda larga fixa: '
                f'<span class="selo {escape(selo["selo"])}">{escape(selo["selo"])}</span>'
                f' · IQS {fmt_num(selo.get("iqs"), 0)}</p>'
            )
        elif selo and selo.get("iqs") is not None:
            selo_html = f'<p>IQS municipal ({escape(str(selo.get("ano")))}): {fmt_num(selo.get("iqs"), 0)}. Selo não informado neste registro.</p>'
        details.append(
            f'<article class="card" id="{escape(p["slug"])}">'
            f'<h3><a href="{prest_url(depth, p["slug"])}">{escape(p["nome"])}</a></h3>'
            f'<p>{fmt_int(p["acessos_fibra_pf_internet"])} acessos PF internet em fibra'
            f' ({fmt_pct(p.get("share_fibra_pf_internet"))} deste recorte no município). '
            f'Total em fibra (inclui PJ e outros produtos): {fmt_int(p["acessos_fibra"])}.</p>'
            f'<p class="muted">Tecnologias declaradas no recorte PF + internet + fibra:</p>'
            f'{mix_pills(p.get("tecnologias_fibra_pf_internet") or {})}'
            f'<p class="muted">Faixas de velocidade (mesmo recorte):</p>'
            f'{mix_pills(p.get("faixas_fibra_pf_internet") or {})}'
            f"{selo_html}"
            f"<details><summary>Indicadores RQUAL de {escape(mes_extenso(meta.get('mes_referencia_rqual')))}</summary>"
            f"{indicators_table(p.get('indicadores') or [])}</details>"
            "</article>"
        )
    schema = {
        "@context": "https://schema.org",
        "@type": "AdministrativeArea",
        "name": f'{city["nome"]} ({city["uf"]})',
        "identifier": city["ibge"],
        "description": f'Acessos de banda larga fixa em fibra em {city["nome"]} segundo dados abertos da Anatel.',
    }
    extra = f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>'
    body = f"""
    <h1>Internet fibra em {escape(city["nome"])} ({escape(city["uf"])})</h1>
    <p class="lede">Acessos em serviço declarados à Anatel no mês de {escape(mes_extenso(city["mes_referencia"]))}. Código IBGE {escape(city["ibge"])}. Isto não é um mapa de cobertura de bairro e não lista planos.</p>
    <div class="kpis">
      <div class="kpi"><b>{fmt_int(city["acessos_fibra_pf_internet"])}</b><span>internet em fibra, pessoa física</span></div>
      <div class="kpi"><b>{fmt_int(city["acessos_fibra"])}</b><span>total de acessos em fibra</span></div>
      <div class="kpi"><b>{fmt_pct(fibra_share)}</b><span>da banda larga fixa do município está em fibra</span></div>
      <div class="kpi"><b>{fmt_int(city.get("populacao"))}</b><span>população estimada IBGE 2026</span></div>
    </div>
    <p class="meta-line">Densidade de banda larga fixa (todas as tecnologias, Anatel): {fmt_num(city.get("densidade"), 2)} acessos por 100 habitantes, no mesmo mês. Prestadoras com algum acesso em fibra: {fmt_int(len(prests))}.</p>
    <h2>Meios de acesso no município</h2>
    <p>Todos os acessos de banda larga fixa, para contexto. O recorte deste diretório é o meio <strong>Fibra</strong>.</p>
    {mix_pills(city.get("meios") or {}, city.get("acessos_total"))}
    <h2>Tecnologias dentro da fibra (pessoa física, internet)</h2>
    {mix_pills(city.get("tecnologias_fibra_pf_internet") or {}, city.get("acessos_fibra_pf_internet"))}
    <h2>Prestadoras</h2>
    <p>Participação calculada sobre os acessos de <strong>internet em fibra para pessoa física</strong> no município. A tabela lista quem declarou acesso em fibra.</p>
    <div class="table-wrap"><table>
      <thead><tr>
        <th>Prestadora</th>
        <th class="num">PF internet em fibra</th>
        <th class="num">Total em fibra</th>
        <th class="num">Participação PF</th>
        <th>Selo Anatel {escape(str(meta.get("ano_selos") or ""))}</th>
      </tr></thead>
      <tbody>{''.join(rows) if rows else '<tr><td colspan="5">Nenhuma prestadora com acesso em fibra neste município no mês de referência.</td></tr>'}</tbody>
    </table></div>
    <h2>Detalhe das maiores no recorte residencial</h2>
    <div class="cards">{''.join(details) if details else '<p class="muted">Sem detalhe para exibir.</p>'}</div>
    {affiliate_box()}
    {source_block(meta, depth)}
    """
    title = f"Internet fibra em {city['nome']} ({city['uf']}): prestadoras e acessos | {SITE_NAME}"
    desc = (
        f"Prestadoras com acessos de banda larga fixa em fibra em {city['nome']} ({city['uf']}), "
        f"segundo a Anatel em {mes_extenso(city['mes_referencia'])}. Sem preços nem cobertura por bairro."
    )
    return layout(
        title,
        desc,
        body,
        depth=depth,
        path=f"municipio/{city['slug']}/",
        crumbs=[(SITE_NAME, rel(depth, "")), (f'{city["nome"]} ({city["uf"]})', None)],
        extra_head=extra,
    )


def page_prestadora(data: dict, prest: dict, published: set[str]) -> str:
    meta = data["meta"]
    depth = 2
    pubs = [m for m in prest.get("municipios") or [] if m["ibge"] in published]
    pubs.sort(key=lambda x: (-x["acessos_fibra_pf_internet"], x["nome"]))
    rows = "".join(
        "<tr>"
        f'<td><a href="{city_url(depth, m["slug"])}">{escape(m["nome"])} ({escape(m["uf"])})</a></td>'
        f'<td class="num">{fmt_int(m["acessos_fibra_pf_internet"])}</td>'
        f'<td class="num">{fmt_int(m["acessos_fibra"])}</td>'
        "</tr>"
        for m in pubs
    )
    grupos = ", ".join(prest.get("grupos") or {}) or "—"
    body = f"""
    <h1>{escape(prest["nome"])}</h1>
    <p class="lede">Acessos de banda larga fixa declarados à Anatel em {escape(mes_extenso(meta["mes_referencia_acessos"]))}. Grupo econômico no arquivo: {escape(grupos)}. Este retrato não é oferta comercial.</p>
    <div class="kpis">
      <div class="kpi"><b>{fmt_int(prest["acessos_fibra_pf_internet"])}</b><span>internet em fibra, pessoa física, no Brasil</span></div>
      <div class="kpi"><b>{fmt_int(prest["acessos_fibra"])}</b><span>total de acessos em fibra no Brasil</span></div>
      <div class="kpi"><b>{fmt_int(prest["n_municipios_fibra_pf"])}</b><span>municípios com PF internet em fibra</span></div>
      <div class="kpi"><b>{fmt_int(prest["n_municipios_fibra"])}</b><span>municípios com algum acesso em fibra</span></div>
    </div>
    <h2>Tecnologias no recorte PF + internet + fibra (Brasil)</h2>
    {mix_pills(prest.get("tecnologias_fibra_pf_internet") or {}, prest.get("acessos_fibra_pf_internet"))}
    <h2>Municípios já publicados neste site</h2>
    <p>{fmt_int(len(pubs))} de {fmt_int(prest["n_municipios_fibra"])} municípios em que a prestadora declarou acesso em fibra no arquivo da Anatel. A lista abaixo não é a lista completa do país — só as páginas já geradas.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Município</th><th class="num">PF internet em fibra</th><th class="num">Total em fibra</th></tr></thead>
      <tbody>{rows or '<tr><td colspan="3">Ainda não há município publicado com fibra desta prestadora.</td></tr>'}</tbody>
    </table></div>
    {affiliate_box()}
    {source_block(meta, depth)}
    """
    return layout(
        f'{prest["nome"]}: acessos em fibra no Brasil | {SITE_NAME}',
        f'Acessos de banda larga fixa em fibra da prestadora {prest["nome"]} segundo a Anatel em {mes_extenso(meta["mes_referencia_acessos"])}.',
        body,
        depth=depth,
        path=f"prestadora/{prest['slug']}/",
        crumbs=[(SITE_NAME, rel(depth, "")), (prest["nome"], None)],
    )


def page_ranking(data: dict) -> str:
    meta = data["meta"]
    prests = sorted(
        data["prestadoras"].values(),
        key=lambda p: (-p["acessos_fibra_pf_internet"], p["nome"]),
    )[:40]
    rows = []
    for i, p in enumerate(prests, 1):
        rows.append(
            "<tr>"
            f"<td class='num'>{i}</td>"
            f'<td><a href="{url("prestadora/" + p["slug"] + "/")}">{escape(p["nome"])}</a></td>'
            f'<td class="num">{fmt_int(p["acessos_fibra_pf_internet"])}</td>'
            f'<td class="num">{fmt_int(p["acessos_fibra"])}</td>'
            f'<td class="num">{fmt_int(p["n_municipios_fibra_pf"])}</td>'
            "</tr>"
        )
    body = f"""
    <h1>Ranking nacional de acessos em fibra</h1>
    <p class="lede">Prestadoras com mais acessos de internet em fibra para pessoa física no Brasil, no mês de {escape(mes_extenso(meta["mes_referencia_acessos"]))}. É um recorte do arquivo da Anatel, não um ranking de qualidade nem de preço.</p>
    <div class="table-wrap"><table>
      <thead><tr><th class="num">#</th><th>Prestadora</th><th class="num">PF internet em fibra</th><th class="num">Total em fibra</th><th class="num">Municípios (PF)</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    {affiliate_box()}
    {source_block(meta, 0)}
    """
    return layout(
        f"Ranking de internet fibra no Brasil | {SITE_NAME}",
        "Ranking de prestadoras por acessos de internet em fibra para pessoa física, segundo dados abertos da Anatel.",
        body,
        path="ranking.html",
        crumbs=[(SITE_NAME, url("")), ("Ranking", None)],
    )


def page_metodologia(data: dict) -> str:
    meta = data["meta"]
    body = f"""
    <article class="prose">
    <h1>Metodologia</h1>
    <p>Este site só publica o que está nos arquivos abertos da Anatel e nas estimativas do IBGE. Não completamos lacuna com chute, não exibimos preço e não desenhamos cobertura de bairro.</p>
    <h2>O que é um acesso em fibra aqui</h2>
    <p>{escape(meta["definicao_fibra"])}</p>
    <p>{escape(meta["definicao_residencial"])}</p>
    <h2>Mês de referência</h2>
    <p>No arquivo de colunas mensais de 2026, o último mês disponível no momento da coleta foi <strong>{escape(mes_extenso(meta["mes_referencia_acessos"]))}</strong>. O ZIP de acessos da Anatel tinha Last-Modified HTTP em {escape(meta["fontes"]["acessos"].get("last_modified_brasilia") or "—")}.</p>
    <h2>Participação de mercado</h2>
    <p>A participação de uma prestadora no município é a divisão dos acessos de internet em fibra para pessoa física daquela empresa pelo total desse mesmo recorte no município. Não usamos receita, nem domicílios cobertos, nem velocidade vendida.</p>
    <h2>Qualidade</h2>
    <p>{escape(meta["ida"])}</p>
    <p>Indicadores mensais do RQUAL, quando o arquivo foi processado, entram com o resultado, a unidade, as referências e o aviso de se a Anatel considerou a amostra representativa (campo Estatística = SIM). Neste build, o mês RQUAL é {escape(mes_extenso(meta.get("mes_referencia_rqual")))}. Selos municipais de banda larga fixa são anuais (ano-base {escape(str(meta.get("ano_selos") or "—"))}).</p>
    <h2>CEP e bairro</h2>
    <p>{escape(meta["limitacao_cep_bairro"])}</p>
    <h2>Arquivos e catálogos</h2>
    <ul>
      <li>Acessos: <a href="{escape(meta['fontes']['acessos']['arquivo'])}">{escape(meta['fontes']['acessos']['arquivo'])}</a> · catálogo <a href="{escape(meta['fontes']['acessos']['catalogo'])}">dados.gov.br</a></li>
      <li>RQUAL: <a href="{escape(meta['fontes']['rqual']['arquivo'])}">{escape(meta['fontes']['rqual']['arquivo'])}</a></li>
      <li>Selos/IQS: <a href="{escape(meta['fontes']['selos']['arquivo'])}">{escape(meta['fontes']['selos']['arquivo'])}</a></li>
      <li>População: API SIDRA/IBGE, agregado 6579, variável 9324, período 2026.</li>
    </ul>
    <h2>O que este site não é</h2>
    <p>Não é a Anatel, não é um comparador de planos, não é o Anatel Busca Ofertas e não é um cadastro de cobertura. Erros de declaração das prestadoras à Agência podem existir no arquivo de origem.</p>
    </article>
    """
    return layout(
        f"Metodologia | {SITE_NAME}",
        "Como o diretório Fibra no Município lê os dados abertos da Anatel e do IBGE, e o que ele deliberadamente não afirma.",
        body,
        path="metodologia.html",
        crumbs=[(SITE_NAME, url("")), ("Metodologia", None)],
    )


def page_sobre(data: dict) -> str:
    body = f"""
    <article class="prose">
    <h1>Sobre</h1>
    <p><strong>Fibra no Município</strong> é um diretório estático, em português do Brasil, feito para consulta local. Nasceu como um site pequeno que pode ganhar uma página útil por noite, sempre com fonte oficial.</p>
    <p><strong>Não somos a Anatel.</strong> Não emitimos selo, não regulamos prestadora, não vendemos plano e não falamos em nome da Agência. Os números vêm dos dados abertos do Serviço de Comunicação Multimídia (banda larga fixa) e das bases de qualidade (RQUAL e Selos).</p>
    <p>Quando houver parcerias de indicação ou afiliados, cada link comercial terá o rótulo visível <strong>Publicidade</strong>, conforme o Guia CONAR de marketing e publicidade por influenciadores digitais (atualização com vigor em 1º de junho de 2026). Hoje esses espaços estão vazios de propósito.</p>
    <p>Dúvidas sobre os dados brutos devem ir aos canais da Anatel. A metodologia deste site está em <a href="{url('metodologia.html')}">Metodologia</a>. Privacidade e cookies, em <a href="{url('privacidade.html')}">Privacidade</a>.</p>
    </article>
    """
    return layout(
        f"Sobre | {SITE_NAME}",
        "O que é o diretório Fibra no Município, por que ele não é a Anatel e como trata publicidade e dados oficiais.",
        body,
        path="sobre.html",
        crumbs=[(SITE_NAME, url("")), ("Sobre", None)],
    )


def page_privacidade(_data: dict) -> str:
    body = """
    <article class="prose">
    <h1>Privacidade e cookies</h1>
    <p>Este site é estático. Nas páginas geradas aqui não há ferramenta de analytics, pixel de rede social nem cookie de marketing próprio.</p>
    <h2>O que podemos guardar no seu navegador</h2>
    <p>Só se você aceitar o aviso, gravamos uma chave local (<code>fnm-cookie-ok</code>) para não repetir o banner. Não é um identificador enviado a servidor nosso.</p>
    <h2>Busca por CEP</h2>
    <p>Se você usar a busca por CEP, o navegador consulta a API pública da BrasilAPI diretamente. Nós não intermediamos nem armazenamos o CEP. Essa consulta serve apenas para descobrir o município. Não gera afirmação de cobertura.</p>
    <h2>Links de afiliados (futuro)</h2>
    <p>Quando houver indicação comercial, o destino (operadora ou rede de afiliados) pode definir cookies e tratar dados segundo a política dele. Esses links virão com o rótulo <strong>Publicidade</strong>, visível na primeira tela do bloco. Esta página será atualizada se a prática mudar.</p>
    <h2>LGPD</h2>
    <p>Não pedimos cadastro e não temos, neste protótipo, base própria de dados pessoais de visitantes. Se no futuro houver formulário, haverá aviso de finalidade, base legal e canal de direitos (Lei 13.709/2018).</p>
    <p>Para exercer direitos ou tirar dúvida sobre esta política, use o canal que o operador do site indicar na página Sobre, quando o projeto estiver no ar em domínio próprio. Esta cópia é uma prévia local.</p>
    </article>
    """
    return layout(
        f"Privacidade | {SITE_NAME}",
        "Como o diretório Fibra no Município trata cookies, busca por CEP, LGPD e futura publicidade de afiliados.",
        body,
        path="privacidade.html",
        crumbs=[(SITE_NAME, url("")), ("Privacidade", None)],
    )


def page_fila(_data: dict) -> str:
    body = """
    <article class="prose">
    <h1>Cidade ainda não publicada</h1>
    <p>Processamos a base nacional de acessos, mas o conjunto inicial de páginas é limitado. O script <code>nightly.py</code> publica uma cidade útil por execução, na ordem da fila (em geral, as mais populosas que ainda não saíram).</p>
    <p>Volte à <a href="{url('')}">busca inicial</a> ou acompanhe as cidades já publicadas. Isso não significa que a prestadora não atenda o município — só que a página ainda não foi gerada.</p>
    </article>
    """
    return layout(
        f"Fila de municípios | {SITE_NAME}",
        "Esta cidade já pode estar na base processada, mas a página ainda não foi publicada pelo roteiro noturno.",
        body,
        path="fila.html",
        crumbs=[(SITE_NAME, url("")), ("Fila", None)],
    )


def page_diario(data: dict) -> str:
    rows = list(reversed(data.get("nightly") or []))
    items = []
    for ev in rows[:30]:
        href = ev.get("href") or "#"
        items.append(
            f'<li><a href="{escape(href)}">{escape(ev.get("titulo") or ev.get("tipo") or "entrada")}</a> '
            f'— {escape(ev.get("quando") or "")}. {escape(ev.get("resumo") or "")}</li>'
        )
    body = f"""
    <article class="prose">
    <h1>Páginas do roteiro noturno</h1>
    <p>Cada execução do script noturno acrescenta uma página nova de município (ou registra que não havia item novo). O histórico local está abaixo.</p>
    <ul>{''.join(items) if items else '<li>Nenhuma execução noturna registrada ainda além do conjunto inicial.</li>'}</ul>
    </article>
    """
    return layout(
        f"Roteiro noturno | {SITE_NAME}",
        "Histórico das páginas acrescentadas pelo script noturno do diretório Fibra no Município.",
        body,
        path="diario/index.html",
        crumbs=[(SITE_NAME, url("")), ("Roteiro noturno", None)],
        depth=1,
    )


def robots_txt() -> str:
    sitemap_loc = abs_url("sitemap.xml")
    return f"User-agent: *\nAllow: /\nSitemap: {sitemap_loc}\n"


def sitemap(paths: list[str]) -> str:
    urls = "".join(f"  <url><loc>{escape(abs_url(p))}</loc></url>\n" for p in paths)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n"


def build() -> dict:
    data = load()
    if SITE.exists():
        # keep nothing stale
        for child in SITE.iterdir():
            if child.name.startswith("."):
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        SITE.mkdir(parents=True)

    assets = SITE / "assets"
    assets.mkdir()
    shutil.copy2(ASSETS_SRC / "style.css", assets / "style.css")
    shutil.copy2(ASSETS_SRC / "app.js", assets / "app.js")

    published = data["published"]
    munics = data["municipios"]
    paths = ["index.html", "ranking.html", "metodologia.html", "sobre.html", "privacidade.html", "fila.html", "diario/"]

    write(SITE / "index.html", page_home(data))
    write(SITE / "ranking.html", page_ranking(data))
    write(SITE / "metodologia.html", page_metodologia(data))
    write(SITE / "sobre.html", page_sobre(data))
    write(SITE / "privacidade.html", page_privacidade(data))
    write(SITE / "fila.html", page_fila(data))
    write(SITE / "diario" / "index.html", page_diario(data))

    used_prests = set()
    n_city = 0
    for ibge in published:
        city = munics.get(ibge)
        if not city:
            continue
        write(SITE / "municipio" / city["slug"] / "index.html", page_city(data, city))
        paths.append(f"municipio/{city['slug']}/")
        n_city += 1
        for p in city.get("prestadoras") or []:
            if p.get("acessos_fibra", 0) > 0:
                used_prests.add(p["slug"])

    n_prest = 0
    for slug in sorted(used_prests):
        prest = data["prestadoras"].get(slug)
        if not prest:
            continue
        write(SITE / "prestadora" / slug / "index.html", page_prestadora(data, prest, set(published)))
        paths.append(f"prestadora/{slug}/")
        n_prest += 1

    # compact search index (all processed municipalities)
    busca = [
        {
            "ibge": row["ibge"],
            "slug": row["slug"],
            "nome": row["nome"],
            "uf": row["uf"],
            "populacao": row.get("populacao"),
            "publicado": row["ibge"] in set(published),
        }
        for row in data["index"]
    ]
    write(SITE / "dados" / "busca.json", json.dumps(busca, ensure_ascii=False, separators=(",", ":")))
    write(SITE / "robots.txt", robots_txt())
    write(SITE / "sitemap.xml", sitemap(paths))
    write(SITE / ".nojekyll", "")

    summary = {
        "cidades": n_city,
        "prestadoras": n_prest,
        "urls": len(paths),
        "saida": str(SITE),
        "base_url": get_base_url(),
        "site_url": get_site_url() or None,
    }
    print(
        f"site gerado: {n_city} municípios, {n_prest} prestadoras, {len(paths)} URLs em {SITE} "
        f"(BASE_URL={get_base_url()} SITE_URL={get_site_url() or '—'})"
    )
    return summary


if __name__ == "__main__":
    build()
