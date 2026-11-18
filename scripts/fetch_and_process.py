#!/usr/bin/env python3
"""Download (or reuse) official Anatel/IBGE files and build processed JSON.

Never invents plans, prices or neighborhood coverage. Fiber = Meio de Acesso == "Fibra".
"""
from __future__ import annotations

import csv
import io
import json
import re
import struct
import sys
import unicodedata
import urllib.request
import zipfile
import zlib
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.paths import DATA_PROCESSED, DATA_RAW, ROOT  # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")

ACESSOS_ZIP = "https://www.anatel.gov.br/dadosabertos/paineis_de_dados/acessos/acessos_banda_larga_fixa.zip"
RQUAL_ZIP = "https://www.anatel.gov.br/dadosabertos/paineis_de_dados/qualidade/indicadores_rqual.zip"
SELOS_ZIP = "https://www.anatel.gov.br/dadosabertos/paineis_de_dados/qualidade/indices_selos.zip"
IBGE_POP = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/6579/"
    "periodos/2026/variaveis/9324?localidades=N6%5Ball%5D"
)
ACESSOS_PAGE = "https://dados.gov.br/dados/conjuntos-dados/acessos---banda-larga-fixa"
RQUAL_PAGE = "https://dados.gov.br/dados/conjuntos-dados/indicadores-de-qualidade-dos-servicos--rqual"
SELOS_PAGE = "https://dados.gov.br/dados/conjuntos-dados/qualidade---selos-de-qualidade-e-ndice-de-qualidade-dos-servios---iqs"
ANATEL_PAINEL = "https://informacoes.anatel.gov.br/paineis/acessos/banda-larga-fixa"
IBGE_PAGE = "https://www.ibge.gov.br/estatisticas/sociais/populacao/9103-estimativas-de-populacao.html"

COLUNAS_MEMBER = "Acessos_Banda_Larga_Fixa_2026_Colunas.csv"
DENSIDADE_MEMBER = "Densidade_Banda_Larga_Fixa.csv"

# Interior cities (IBGE codes) used in the starter set if they are not already in the top 20.
INTERIOR_IBGE = [
    "3543402",  # Ribeirão Preto - SP
    "3170206",  # Uberlândia - MG
    "2910800",  # Feira de Santana - BA
    "4113700",  # Londrina - PR
    "4209102",  # Joinville - SC
    "2504009",  # Campina Grande - PB
    "3136702",  # Juiz de Fora - MG
    "4115200",  # Maringá - PR
    "4305108",  # Caxias do Sul - RS
    "1506807",  # Santarém - PA
    "5003702",  # Dourados - MS
    "2611101",  # Petrolina - PE
]


def now_br() -> datetime:
    return datetime.now(TZ)


def http_last_modified(url: str) -> tuple[int, str | None]:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        size = int(r.headers.get("Content-Length") or 0)
        return size, r.headers.get("Last-Modified")


def parse_http_date_br(value: str | None) -> str | None:
    if not value:
        return None
    # e.g. Wed, 04 Nov 2026 10:32:22 GMT
    dt = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
    local = dt.astimezone(TZ)
    return local.strftime("%d/%m/%Y %H:%M") + " (horário de Brasília, UTC-3)"


def slugify(*parts: str) -> str:
    raw = " ".join(p for p in parts if p)
    s = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "item"


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"\b(s\.?a\.?|ltda\.?|me\.?|epp\.?|telecom|telecomunicacoes|comunicações|comunicacoes)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def ibge7(value) -> str:
    if value is None:
        text = ""
    else:
        text = str(value)
        if text.lower() in {"nan", "none", "nat"}:
            text = ""
    digits = re.sub(r"\D", "", text)
    if not digits:
        return ""
    return digits.zfill(7)[-7:]


def cnpj14(value) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.zfill(14)[-14:]



def safe_str(value) -> str:
    if value is None:
        return ""
    try:
        import math
        if isinstance(value, float) and math.isnan(value):
            return ""
    except Exception:
        pass
    s = str(value).strip()
    if s.lower() in {"nan", "none", "nat"}:
        return ""
    return s

def parse_decimal(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s.upper() in {"NO", "NA", "N/A", "-", "NULL"}:
        return None
    s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") > 1 else s.replace(",", ".")
    # Anatel uses 27,1898 or 99 or 1,99 — comma as decimal, no thousands sep usually
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return None


def download(url: str, dest: Path, force: bool = False) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"  reuse {dest} ({dest.stat().st_size} bytes)")
        return dest
    print(f"  download {url} -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "FibraNoMunicipio/1.0 (dados abertos; site estático local)"})
    with urllib.request.urlopen(req, timeout=600) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    print(f"  wrote {dest.stat().st_size} bytes")
    return dest


def zip_central_directory(url: str):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        size = int(r.headers["Content-Length"])
        last = r.headers.get("Last-Modified")
    start = max(0, size - 512 * 1024)
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{size-1}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        tail = r.read()
    eocd_pos = tail.rfind(b"PK\x05\x06")
    eocd = tail[eocd_pos:]
    cd_size = struct.unpack_from("<I", eocd, 12)[0]
    cd_off = struct.unpack_from("<I", eocd, 16)[0]
    if cd_off < start:
        req = urllib.request.Request(url, headers={"Range": f"bytes={cd_off}-{cd_off + cd_size - 1}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            cd = r.read()
    else:
        cd = tail[cd_off - start : cd_off - start + cd_size]
    return size, last, cd


def zip_members(cd: bytes, wanted: set[str]) -> dict:
    found = {}
    off = 0
    while off + 46 <= len(cd):
        if cd[off : off + 4] != b"PK\x01\x02":
            break
        method, = struct.unpack_from("<H", cd, off + 10)
        comp, uncomp = struct.unpack_from("<II", cd, off + 20)
        namelen, extra, comment = struct.unpack_from("<HHH", cd, off + 28)
        local_off, = struct.unpack_from("<I", cd, off + 42)
        name = cd[off + 46 : off + 46 + namelen].decode("utf-8", "replace")
        extra_bytes = cd[off + 46 + namelen : off + 46 + namelen + extra]
        if name in wanted:
            if comp == 0xFFFFFFFF or uncomp == 0xFFFFFFFF or local_off == 0xFFFFFFFF:
                e = 0
                while e + 4 <= len(extra_bytes):
                    eid, elen = struct.unpack_from("<HH", extra_bytes, e)
                    payload = extra_bytes[e + 4 : e + 4 + elen]
                    p = 0
                    if eid == 1:
                        if uncomp == 0xFFFFFFFF and p + 8 <= len(payload):
                            uncomp = struct.unpack_from("<Q", payload, p)[0]
                            p += 8
                        if comp == 0xFFFFFFFF and p + 8 <= len(payload):
                            comp = struct.unpack_from("<Q", payload, p)[0]
                            p += 8
                        if local_off == 0xFFFFFFFF and p + 8 <= len(payload):
                            local_off = struct.unpack_from("<Q", payload, p)[0]
                            p += 8
                    e += 4 + elen
            found[name] = (local_off, comp, uncomp, method)
        off += 46 + namelen + extra + comment
    return found


def extract_member_http(url: str, name: str, meta: tuple, dest: Path, force: bool = False) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    local_off, comp, uncomp, method = meta
    if dest.exists() and dest.stat().st_size == uncomp and not force:
        print(f"  reuse {dest}")
        return dest
    print(f"  extract {name} ({comp/1e6:.1f} MB comp) -> {dest}")
    req = urllib.request.Request(url, headers={"Range": f"bytes={local_off}-{local_off + 29}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        lh = r.read()
    if lh[:4] != b"PK\x03\x04":
        raise RuntimeError(f"bad local header for {name}")
    nlen, elen = struct.unpack_from("<HH", lh, 26)
    data_start = local_off + 30 + nlen + elen
    req = urllib.request.Request(url, headers={"Range": f"bytes={data_start}-{data_start + comp - 1}"})
    dec = zlib.decompressobj(-zlib.MAX_WBITS) if method == 8 else None
    with urllib.request.urlopen(req, timeout=600) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(dec.decompress(chunk) if dec else chunk)
        if dec:
            f.write(dec.flush())
    print(f"  wrote {dest.stat().st_size} bytes")
    return dest


def load_ibge_pop(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    series = data[0]["resultados"][0]["series"]
    out = {}
    period = None
    for item in series:
        loc = item["localidade"]
        code = ibge7(loc["id"])
        nome_uf = loc["nome"]  # "Salvador - BA"
        if " - " in nome_uf:
            nome, uf = nome_uf.rsplit(" - ", 1)
        else:
            nome, uf = nome_uf, ""
        serie = item["serie"]
        period = sorted(serie.keys())[-1]
        raw = serie[period]
        if raw in {None, "...", "-", "X"}:
            continue
        pop = int(str(raw).replace(".", "").replace(",", ""))
        out[code] = {"ibge": code, "nome": nome, "uf": uf, "populacao": pop, "ano": period}
    return out


def process_acessos(colunas_path: Path) -> tuple[str, dict, dict, dict]:
    import pandas as pd

    print("  reading acessos colunas…")
    df = pd.read_csv(
        colunas_path,
        sep=";",
        encoding="utf-8-sig",
        dtype=str,
        low_memory=False,
    )
    month_cols = sorted([c for c in df.columns if re.fullmatch(r"\d{4}-\d{2}", c)])
    if not month_cols:
        raise RuntimeError("no month columns in acessos file")
    month = month_cols[-1]
    print(f"  reference month: {month} (columns {month_cols[0]}…{month_cols[-1]})")
    df[month] = pd.to_numeric(df[month], errors="coerce").fillna(0).astype(int)
    df = df[df[month] > 0].copy()
    df["ibge"] = df["Código IBGE Município"].map(ibge7)
    df["cnpj"] = df["CNPJ"].map(cnpj14)
    df["Empresa"] = df["Empresa"].fillna("").str.strip()
    df["Grupo Econômico"] = df["Grupo Econômico"].fillna("").str.strip()
    df["Meio de Acesso"] = df["Meio de Acesso"].fillna("").str.strip()
    df["Tecnologia"] = df["Tecnologia"].fillna("").str.strip()
    df["Tipo de Pessoa"] = df["Tipo de Pessoa"].fillna("").str.strip()
    df["Tipo de Produto"] = df["Tipo de Produto"].fillna("").str.strip()
    df["Porte da Prestadora"] = df["Porte da Prestadora"].fillna("").str.strip()
    df["Faixa de Velocidade"] = df["Faixa de Velocidade"].fillna("").str.strip()
    df["UF"] = df["UF"].fillna("").str.strip()
    df["Município"] = df["Município"].fillna("").str.strip()

    # Municipal totals by access medium (all technologies) and fiber cuts.
    munics: dict[str, dict] = {}
    # prestadora national + per-city
    prest: dict[str, dict] = {}

    def munic_rec(row) -> dict:
        code = row["ibge"]
        rec = munics.get(code)
        if rec is None:
            rec = {
                "ibge": code,
                "nome": row["Município"],
                "uf": row["UF"],
                "acessos_total": 0,
                "acessos_fibra": 0,
                "acessos_fibra_pf_internet": 0,
                "acessos_fibra_pj_internet": 0,
                "meios": defaultdict(int),
                "tecnologias_fibra": defaultdict(int),
                "tecnologias_fibra_pf_internet": defaultdict(int),
                "faixas_fibra_pf_internet": defaultdict(int),
                "prestadoras": {},
            }
            munics[code] = rec
        return rec

    def prest_key(nome: str) -> str:
        return slugify(nome)

    def prest_rec(nome: str, grupo: str, porte: str) -> dict:
        key = prest_key(nome)
        rec = prest.get(key)
        if rec is None:
            rec = {
                "slug": key,
                "nome": nome,
                "grupos": defaultdict(int),
                "portes": defaultdict(int),
                "cnpjs": set(),
                "acessos_fibra": 0,
                "acessos_fibra_pf_internet": 0,
                "acessos_total": 0,
                "municipios_fibra_pf": set(),
                "municipios_fibra": set(),
                "tecnologias_fibra_pf_internet": defaultdict(int),
                "por_municipio": {},
            }
            prest[key] = rec
        rec["grupos"][grupo or nome] += 0
        rec["portes"][porte or ""] += 0
        return rec

    print("  aggregating rows…", len(df))
    # Use itertuples for speed
    cols = {c: df.columns.get_loc(c) for c in df.columns}
    mcol = cols[month]
    for tup in df.itertuples(index=False, name=None):
        acessos = int(tup[mcol])
        if acessos <= 0:
            continue
        meio = tup[cols["Meio de Acesso"]]
        tec = tup[cols["Tecnologia"]]
        pessoa = tup[cols["Tipo de Pessoa"]]
        produto = tup[cols["Tipo de Produto"]]
        empresa = tup[cols["Empresa"]] or "Não informado"
        grupo = tup[cols["Grupo Econômico"]]
        porte = tup[cols["Porte da Prestadora"]]
        faixa = tup[cols["Faixa de Velocidade"]]
        ibge = tup[cols["ibge"]]
        cnpj = tup[cols["cnpj"]]
        row = {
            "ibge": ibge,
            "Município": tup[cols["Município"]],
            "UF": tup[cols["UF"]],
        }
        m = munic_rec(row)
        p = prest_rec(empresa, grupo, porte)
        p["cnpjs"].add(cnpj)
        p["grupos"][grupo or empresa] += acessos
        p["portes"][porte or "não informado"] += acessos
        p["acessos_total"] += acessos
        m["acessos_total"] += acessos
        m["meios"][meio or "Não informado"] += acessos

        is_fibra = meio == "Fibra"
        is_pf_net = is_fibra and pessoa == "Pessoa Física" and produto == "INTERNET"
        is_pj_net = is_fibra and pessoa == "Pessoa Jurídica" and produto == "INTERNET"

        if is_fibra:
            m["acessos_fibra"] += acessos
            m["tecnologias_fibra"][tec or "Não informado"] += acessos
            p["acessos_fibra"] += acessos
            p["municipios_fibra"].add(ibge)
        if is_pf_net:
            m["acessos_fibra_pf_internet"] += acessos
            m["tecnologias_fibra_pf_internet"][tec or "Não informado"] += acessos
            m["faixas_fibra_pf_internet"][faixa or "Não informado"] += acessos
            p["acessos_fibra_pf_internet"] += acessos
            p["municipios_fibra_pf"].add(ibge)
            p["tecnologias_fibra_pf_internet"][tec or "Não informado"] += acessos
        if is_pj_net:
            m["acessos_fibra_pj_internet"] += acessos

        # per munic-prestadora
        if is_fibra or True:
            key = p["slug"]
            pr = m["prestadoras"].get(key)
            if pr is None:
                pr = {
                    "slug": key,
                    "nome": empresa,
                    "grupo": grupo or empresa,
                    "porte": porte,
                    "cnpjs": set(),
                    "acessos_total": 0,
                    "acessos_fibra": 0,
                    "acessos_fibra_pf_internet": 0,
                    "acessos_fibra_pj_internet": 0,
                    "tecnologias_fibra": defaultdict(int),
                    "tecnologias_fibra_pf_internet": defaultdict(int),
                    "faixas_fibra_pf_internet": defaultdict(int),
                    "meios": defaultdict(int),
                }
                m["prestadoras"][key] = pr
            pr["cnpjs"].add(cnpj)
            pr["acessos_total"] += acessos
            pr["meios"][meio or "Não informado"] += acessos
            if is_fibra:
                pr["acessos_fibra"] += acessos
                pr["tecnologias_fibra"][tec or "Não informado"] += acessos
            if is_pf_net:
                pr["acessos_fibra_pf_internet"] += acessos
                pr["tecnologias_fibra_pf_internet"][tec or "Não informado"] += acessos
                pr["faixas_fibra_pf_internet"][faixa or "Não informado"] += acessos
            if is_pj_net:
                pr["acessos_fibra_pj_internet"] += acessos

            if is_fibra:
                pm = p["por_municipio"].get(ibge)
                if pm is None:
                    pm = {
                        "ibge": ibge,
                        "nome": row["Município"],
                        "uf": row["UF"],
                        "acessos_fibra": 0,
                        "acessos_fibra_pf_internet": 0,
                    }
                    p["por_municipio"][ibge] = pm
                pm["acessos_fibra"] += acessos if is_fibra else 0
                if is_pf_net:
                    pm["acessos_fibra_pf_internet"] += acessos

    return month, munics, prest, {"month_cols": month_cols}


def process_densidade(path: Path, month: str) -> dict[str, float]:
    import pandas as pd

    year, mon = month.split("-")
    year_i, mon_i = int(year), int(mon)
    usecols = ["Ano", "Mês", "Código IBGE", "Densidade", "Nível Geográfico Densidade"]
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str, usecols=usecols)
    df["Ano"] = pd.to_numeric(df["Ano"], errors="coerce")
    df["Mês"] = pd.to_numeric(df["Mês"], errors="coerce")
    df = df[(df["Ano"] == year_i) & (df["Mês"] == mon_i) & (df["Nível Geográfico Densidade"].str.lower() == "municipio")]
    out = {}
    for rec in df.itertuples(index=False):
        code = ibge7(rec[2])
        val = parse_decimal(rec[3])
        if val is not None:
            out[code] = val
    print(f"  densidade municipal {month}: {len(out)} municípios")
    return out


def filter_rqual(zip_path: Path, dest_csv: Path, force: bool = False) -> Path:
    if dest_csv.exists() and dest_csv.stat().st_size > 0 and not force:
        print(f"  reuse {dest_csv}")
        return dest_csv
    print("  filtering RQUAL (Banda Larga Fixa, 2025–2026)…")
    written = 0
    max_ym = (0, 0)
    dest_csv.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z, z.open("Tabela_CSV_Indicadores_RQUAL.csv") as raw, open(
        dest_csv, "w", encoding="utf-8", newline=""
    ) as out:
        wrapper = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(wrapper, delimiter=";")
        fields = reader.fieldnames or []
        writer = csv.DictWriter(out, fieldnames=fields, delimiter=";")
        writer.writeheader()
        for row in reader:
            if safe_str(row.get("Serviço")) != "Banda Larga Fixa":
                continue
            try:
                ano = int(row.get("Ano") or 0)
                mes = int(row.get("Mês") or 0)
            except ValueError:
                continue
            if ano < 2025:
                continue
            if (ano, mes) > max_ym:
                max_ym = (ano, mes)
            writer.writerow(row)
            written += 1
            if written % 200000 == 0:
                print(f"    … {written} BLF rows")
    print(f"  wrote {written} RQUAL BLF rows, max period {max_ym[0]}-{max_ym[1]:02d}")
    return dest_csv


def process_rqual(path: Path) -> tuple[str, dict]:
    """Return latest month and map (ibge, norm_prestadora) -> indicators."""
    import pandas as pd

    df = pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str)
    df["Ano"] = pd.to_numeric(df["Ano"], errors="coerce")
    df["Mês"] = pd.to_numeric(df["Mês"], errors="coerce")
    df = df.dropna(subset=["Ano", "Mês"])
    max_ano = int(df["Ano"].max())
    max_mes = int(df[df["Ano"] == max_ano]["Mês"].max())
    month = f"{max_ano}-{max_mes:02d}"
    cur = df[(df["Ano"] == max_ano) & (df["Mês"] == max_mes)].copy()
    print(f"  RQUAL latest BLF month: {month} ({len(cur)} rows)")
    out: dict[tuple[str, str], list] = defaultdict(list)
    by_prest_month: dict[str, dict] = {}  # unused placeholder
    for rec in cur.itertuples(index=False):
        # access by column name via Series would be slower; use to_dict in chunks? 
        pass
    # simpler
    records = []
    for _, row in cur.iterrows():
        code = ibge7(row.get("Código IBGE") or "")
        prest = safe_str(row.get("Prestadora"))
        if not code or code == "0000000" or not prest:
            continue
        resultado_raw = safe_str(row.get("Resultado"))
        resultado = parse_decimal(resultado_raw) if resultado_raw not in {"", "NO"} else None
        item = {
            "indicador": safe_str(row.get("Indicador")),
            "descricao": safe_str(row.get("Descrição")),
            "tipo": safe_str(row.get("Tipo")),
            "grupo": safe_str(row.get("Grupo")),
            "resultado": resultado,
            "resultado_bruto": resultado_raw,
            "unidade": safe_str(row.get("Unidade de Medida")),
            "erro_amostral": parse_decimal(row.get("Erro Amostral")),
            "estatistica_representativa": safe_str(row.get("Estatística")).upper() == "SIM",
            "estatistica": safe_str(row.get("Estatística")),
            "ref_inferior": safe_str(row.get("Valor de Referência Inferior")),
            "ref_superior": safe_str(row.get("Valor de Referência Superior")),
            "prestadora_rotulo": prest,
        }
        out[(code, norm_name(prest))].append(item)
        records.append(item)
    return month, out


def process_selos(path: Path) -> tuple[int, dict]:
    import pandas as pd

    df = pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str)
    df = df[
        (df["GRANULARIDADE"].str.strip() == "Municipal")
        & (df["SERVIÇO"].str.strip() == "Banda Larga Fixa")
    ].copy()
    anos = sorted({int(a) for a in df["ANO"].dropna() if str(a).isdigit()})
    ano = anos[-1] if anos else None
    if ano:
        df = df[df["ANO"].astype(str) == str(ano)]
    out = {}
    for _, row in df.iterrows():
        code = ibge7(row.get("CÓDIGO IBGE") or "")
        prest = safe_str(row.get("PRESTADORA"))
        selo = safe_str(row.get("SELO"))
        if not code or not prest:
            continue
        if not selo and not safe_str(row.get("IQS")):
            continue
        out[(code, norm_name(prest))] = {
            "ano": ano,
            "selo": selo or None,
            "iqs": parse_decimal(row.get("IQS")),
            "iqp": parse_decimal(row.get("IQP")),
            "ir": parse_decimal(row.get("IR")),
            "prestadora_rotulo": prest,
        }
    print(f"  selos municipais BLF {ano}: {len(out)} pares município-prestadora com nota/IQS")
    return ano, out


def serialize_maps(d: dict) -> dict:
    if isinstance(d, defaultdict):
        d = dict(d)
    return {str(k): int(v) for k, v in sorted(d.items(), key=lambda kv: (-kv[1], str(kv[0]))) }


def build_payloads(month, munics, prest, densidade, pop, rqual_month, rqual, selos_ano, selos, source_meta):
    # attach pop/density
    index = []
    munic_out = {}
    for code, m in munics.items():
        poprec = pop.get(code)
        if poprec:
            m["nome"] = poprec["nome"]  # official IBGE spelling
            m["uf"] = poprec["uf"]
            m["populacao"] = poprec["populacao"]
            m["populacao_ano"] = poprec["ano"]
        else:
            m["populacao"] = None
            m["populacao_ano"] = None
        m["densidade"] = densidade.get(code)
        m["slug"] = slugify(m["nome"], m["uf"])
        total_pf = m["acessos_fibra_pf_internet"]
        prest_list = []
        for slug, pr in m["prestadoras"].items():
            if pr["acessos_fibra"] <= 0 and pr["acessos_fibra_pf_internet"] <= 0:
                # still may appear only with other media; skip on fiber directory lists
                continue
            share = (pr["acessos_fibra_pf_internet"] / total_pf) if total_pf else None
            key = (code, norm_name(pr["nome"]))
            # also try grupo
            selo = selos.get(key) or selos.get((code, norm_name(pr["grupo"])))
            inds = rqual.get(key) or rqual.get((code, norm_name(pr["grupo"]))) or []
            prest_list.append(
                {
                    "slug": pr["slug"],
                    "nome": pr["nome"],
                    "grupo": pr["grupo"],
                    "porte": pr["porte"],
                    "cnpjs": sorted(pr["cnpjs"]),
                    "acessos_total": int(pr["acessos_total"]),
                    "acessos_fibra": int(pr["acessos_fibra"]),
                    "acessos_fibra_pf_internet": int(pr["acessos_fibra_pf_internet"]),
                    "acessos_fibra_pj_internet": int(pr["acessos_fibra_pj_internet"]),
                    "share_fibra_pf_internet": share,
                    "tecnologias_fibra": serialize_maps(pr["tecnologias_fibra"]),
                    "tecnologias_fibra_pf_internet": serialize_maps(pr["tecnologias_fibra_pf_internet"]),
                    "faixas_fibra_pf_internet": serialize_maps(pr["faixas_fibra_pf_internet"]),
                    "meios": serialize_maps(pr["meios"]),
                    "selo": selo,
                    "indicadores": inds,
                }
            )
        prest_list.sort(key=lambda x: (-x["acessos_fibra_pf_internet"], -x["acessos_fibra"], x["nome"]))
        rec = {
            "ibge": code,
            "slug": m["slug"],
            "nome": m["nome"],
            "uf": m["uf"],
            "populacao": m["populacao"],
            "populacao_ano": m["populacao_ano"],
            "densidade": m["densidade"],
            "mes_referencia": month,
            "acessos_total": int(m["acessos_total"]),
            "acessos_fibra": int(m["acessos_fibra"]),
            "acessos_fibra_pf_internet": int(m["acessos_fibra_pf_internet"]),
            "acessos_fibra_pj_internet": int(m["acessos_fibra_pj_internet"]),
            "meios": serialize_maps(m["meios"]),
            "tecnologias_fibra": serialize_maps(m["tecnologias_fibra"]),
            "tecnologias_fibra_pf_internet": serialize_maps(m["tecnologias_fibra_pf_internet"]),
            "faixas_fibra_pf_internet": serialize_maps(m["faixas_fibra_pf_internet"]),
            "prestadoras": prest_list,
        }
        munic_out[code] = rec
        index.append(
            {
                "ibge": code,
                "slug": rec["slug"],
                "nome": rec["nome"],
                "uf": rec["uf"],
                "populacao": rec["populacao"],
                "acessos_fibra": rec["acessos_fibra"],
                "acessos_fibra_pf_internet": rec["acessos_fibra_pf_internet"],
                "n_prestadoras_fibra": sum(1 for p in prest_list if p["acessos_fibra"] > 0),
            }
        )
    index.sort(key=lambda x: (-(x["populacao"] or 0), x["nome"]))

    prest_out = {}
    for slug, p in prest.items():
        if p["acessos_fibra"] <= 0:
            continue
        cidades = sorted(
            p["por_municipio"].values(),
            key=lambda x: (-x["acessos_fibra_pf_internet"], -x["acessos_fibra"], x["nome"]),
        )
        # attach official names from pop
        for c in cidades:
            if c["ibge"] in pop:
                c["nome"] = pop[c["ibge"]]["nome"]
                c["uf"] = pop[c["ibge"]]["uf"]
            c["slug"] = slugify(c["nome"], c["uf"])
        prest_out[slug] = {
            "slug": slug,
            "nome": p["nome"],
            "grupos": serialize_maps(p["grupos"]),
            "portes": serialize_maps(p["portes"]),
            "cnpjs": sorted(p["cnpjs"]),
            "acessos_total": int(p["acessos_total"]),
            "acessos_fibra": int(p["acessos_fibra"]),
            "acessos_fibra_pf_internet": int(p["acessos_fibra_pf_internet"]),
            "n_municipios_fibra": len(p["municipios_fibra"]),
            "n_municipios_fibra_pf": len(p["municipios_fibra_pf"]),
            "tecnologias_fibra_pf_internet": serialize_maps(p["tecnologias_fibra_pf_internet"]),
            "municipios": [
                {
                    "ibge": c["ibge"],
                    "slug": c["slug"],
                    "nome": c["nome"],
                    "uf": c["uf"],
                    "acessos_fibra": int(c["acessos_fibra"]),
                    "acessos_fibra_pf_internet": int(c["acessos_fibra_pf_internet"]),
                }
                for c in cidades
            ],
        }

    # starter set
    with_pop = [x for x in index if x["populacao"]]
    top20 = with_pop[:20]
    top_codes = {x["ibge"] for x in top20}
    interior = []
    for code in INTERIOR_IBGE:
        if code in top_codes:
            continue
        if code in munic_out:
            interior.append(code)
        if len(interior) >= 8:
            break
    starter = [x["ibge"] for x in top20] + interior

    queue = [x["ibge"] for x in with_pop if x["ibge"] not in starter and x["acessos_fibra"] > 0]

    meta = {
        "gerado_em": now_br().strftime("%d/%m/%Y %H:%M") + " (horário de Brasília, UTC-3)",
        "mes_referencia_acessos": month,
        "mes_referencia_rqual": rqual_month,
        "ano_selos": selos_ano,
        "definicao_fibra": (
            "Consideramos acesso em fibra quando o campo 'Meio de Acesso' da Anatel é igual a 'Fibra'. "
            "A tecnologia declarada (FTTH, FTTB, Ethernet etc.) é exibida como detalhe, sem ser usada como filtro principal."
        ),
        "definicao_residencial": (
            "O recorte mais próximo de internet residencial é Tipo de Pessoa = Pessoa Física e Tipo de Produto = INTERNET, "
            "em meio de acesso Fibra. Também exibimos o total de acessos em fibra (incluindo pessoa jurídica e outros produtos)."
        ),
        "limitacao_cep_bairro": (
            "A base de acessos da Anatel usada aqui é municipal. Não há, neste conjunto, acessos por bairro ou por CEP. "
            "Busca por CEP só identifica o município (via API pública no navegador) e nunca afirma cobertura de rua."
        ),
        "ida": (
            "O antigo IDA (Índice de Desempenho no Atendimento) não foi usado: a série vigente de qualidade da Anatel "
            "é o RQUAL (indicadores mensais e Selos/IQS anuais). O conjunto de Selos foi baixado; indicadores RQUAL mensais "
            "entram quando o arquivo filtrado está disponível."
        ),
        "fontes": source_meta,
        "starter_ibge": starter,
        "n_municipios_com_acessos": len(munic_out),
        "n_prestadoras_com_fibra": len(prest_out),
    }
    return meta, index, munic_out, prest_out, starter, queue


def dump_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  wrote {path} ({path.stat().st_size} bytes)")


def main(argv: list[str] | None = None) -> int:
    force = "--refresh" in (argv or sys.argv[1:])
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)

    print("== fontes oficiais ==")
    acessos_size, acessos_lm = http_last_modified(ACESSOS_ZIP)
    rqual_size, rqual_lm = http_last_modified(RQUAL_ZIP)
    selos_size, selos_lm = http_last_modified(SELOS_ZIP)
    source_meta = {
        "acessos": {
            "arquivo": ACESSOS_ZIP,
            "catalogo": ACESSOS_PAGE,
            "painel": ANATEL_PAINEL,
            "last_modified_http": acessos_lm,
            "last_modified_brasilia": parse_http_date_br(acessos_lm),
            "bytes": acessos_size,
            "membros": [COLUNAS_MEMBER, DENSIDADE_MEMBER],
            "licenca": "Dados abertos da Anatel (atribuição exigida). Conferir o termo no portal da Agência.",
        },
        "rqual": {
            "arquivo": RQUAL_ZIP,
            "catalogo": RQUAL_PAGE,
            "last_modified_http": rqual_lm,
            "last_modified_brasilia": parse_http_date_br(rqual_lm),
            "bytes": rqual_size,
        },
        "selos": {
            "arquivo": SELOS_ZIP,
            "catalogo": SELOS_PAGE,
            "last_modified_http": selos_lm,
            "last_modified_brasilia": parse_http_date_br(selos_lm),
            "bytes": selos_size,
        },
        "ibge_populacao": {
            "api": IBGE_POP,
            "pagina": IBGE_PAGE,
            "agregado": "6579",
            "variavel": "9324 — População residente estimada",
            "periodo": "2026",
        },
    }
    print(json.dumps({k: v.get("last_modified_brasilia") or v.get("periodo") for k, v in source_meta.items()}, ensure_ascii=False, indent=2))

    print("== extrair acessos ==")
    _, _, cd = zip_central_directory(ACESSOS_ZIP)
    found = zip_members(cd, {COLUNAS_MEMBER, DENSIDADE_MEMBER})
    colunas = extract_member_http(ACESSOS_ZIP, COLUNAS_MEMBER, found[COLUNAS_MEMBER], DATA_RAW / COLUNAS_MEMBER, force)
    densidade_csv = extract_member_http(
        ACESSOS_ZIP, DENSIDADE_MEMBER, found[DENSIDADE_MEMBER], DATA_RAW / DENSIDADE_MEMBER, force
    )

    print("== baixar selos, RQUAL, IBGE ==")
    selos_zip = download(SELOS_ZIP, DATA_RAW / "indices_selos.zip", force)
    if not (DATA_RAW / "Tabela_CSV_Indices_Selos.csv").exists() or force:
        with zipfile.ZipFile(selos_zip) as z:
            z.extract("Tabela_CSV_Indices_Selos.csv", DATA_RAW)
    rqual_zip = download(RQUAL_ZIP, DATA_RAW / "indicadores_rqual.zip", force)
    ibge_path = download(IBGE_POP, DATA_RAW / "ibge_populacao_estimada_2026.json", force)

    print("== processar ==")
    month, munics, prest, _ = process_acessos(colunas)
    densidade = process_densidade(densidade_csv, month)
    pop = load_ibge_pop(ibge_path)
    print(f"  IBGE municípios com população: {len(pop)}")

    rqual_filt = DATA_RAW / "rqual_banda_larga_fixa_2025_2026.csv"
    rqual_month, rqual = None, {}
    try:
        filter_rqual(rqual_zip, rqual_filt, force)
        rqual_month, rqual = process_rqual(rqual_filt)
    except Exception as exc:
        print(f"  AVISO: não foi possível processar o RQUAL ({exc}). Seguimos com acessos e selos.")

    selos_ano, selos = process_selos(DATA_RAW / "Tabela_CSV_Indices_Selos.csv")

    meta, index, munic_out, prest_out, starter, queue = build_payloads(
        month, munics, prest, densidade, pop, rqual_month, rqual, selos_ano, selos, source_meta
    )

    published_path = DATA_PROCESSED / "published.json"
    if published_path.exists() and not force:
        prev = json.loads(published_path.read_text(encoding="utf-8"))
        # keep already published, ensure starter is included
        published = list(dict.fromkeys(list(prev.get("ibge", [])) + starter))
    else:
        published = list(starter)

    meta["n_publicados"] = len(published)
    dump_json(DATA_PROCESSED / "meta.json", meta)
    dump_json(DATA_PROCESSED / "index.json", index)
    dump_json(DATA_PROCESSED / "municipios.json", munic_out)
    dump_json(DATA_PROCESSED / "prestadoras.json", prest_out)
    dump_json(DATA_PROCESSED / "published.json", {"ibge": published})
    dump_json(DATA_PROCESSED / "queue.json", {"ibge": [c for c in queue if c not in published]})
    if not (DATA_PROCESSED / "nightly_log.jsonl").exists():
        (DATA_PROCESSED / "nightly_log.jsonl").write_text("", encoding="utf-8")
    print(f"== ok: {len(published)} municípios no conjunto inicial, {len(queue)} na fila ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
