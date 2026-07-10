"""Motor de cruce línea de entrada (baseline) ↔ línea de salida (endline).

Responde la pregunta de cobertura del endline: de las personas que medimos en la
**línea de base** (filtrando al grupo **Tratamiento**, el universo de seguimiento),
¿a cuántas volvimos a alcanzar en la **encuesta de salida** y quiénes faltan?

Diseño (ver `~/.claude/plans/atomic-imagining-hollerith.md`):
- La identidad del endline la exponen `kobo.get_identities` / `db.get_identities`.
- La base se lee de `Preprocesamiento/outputs/AMA_encuesta_unificada.csv`.
- El documento solo está en ~70% de la base ⇒ no se puede cruzar solo por documento.
  Cascada: (1) documento normalizado → (2) nombre+colegio exacto → (3) nombre+colegio
  fuzzy (tildes/orden/2º nombre faltante) → (4) teléfono como desempate.
- Sin PII en la salida pública: para el dashboard live se exportan llaves **HMAC**
  (salt en secrets, no commiteado), no texto plano de nombres/documentos.

Módulo puro (pandas + stdlib): no importa streamlit, así se puede testear suelto.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

import pandas as pd


# ── Columnas de la base unificada (ver diccionario_datos.csv) ────────────────────
BASE_COLS = {
    "ADM_02": "codigo",
    "DEM_01": "nombre",
    "DEM_02": "documento",
    "DEM_03": "telefono",
    "DEM_05": "colegio",
    "DEM_06": "grado",
    "META_03": "pais",
    "META_04": "grupo",
}

# Variantes ortográficas de colegio → nombre canónico (de colegios_grados_*.md).
COLEGIO_CANON = {
    "unidad educativa cascales": "Institución Educativa Cascales",
    "ue napo": "Unidad Educativa NAPO",
}

FUZZY_THRESHOLD = 0.88


# ════════════════════════════════════════════════════════════════════════════════
# Normalización de llaves
# ════════════════════════════════════════════════════════════════════════════════

def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def _is_placeholder_doc(digits: str) -> bool:
    """Documento centinela que el encuestador tipea cuando no tiene la cédula real.

    Ej.: 11111111 (199 casos), 12345678, 99999999999, 123456. No son identificadores:
    si los tratáramos como documento, el dedup colapsaría personas distintas que
    comparten el mismo relleno y se perderían respuestas reales del endline."""
    if len(set(digits)) == 1:  # 11111111, 99999999, 0000…
        return True
    if digits in "123456789012345" or digits in "543210987654321":  # 12345678, 123456…
        return True
    return False


def norm_doc(value) -> str | None:
    """Documento → solo dígitos, sin ceros a la izquierda. None si es muy corto o centinela."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    digits = re.sub(r"\D", "", str(value))
    digits = digits.lstrip("0")
    if len(digits) < 5 or _is_placeholder_doc(digits):
        return None
    return digits


def norm_phone(value) -> str | None:
    """Teléfono → últimos 9 dígitos (ignora prefijo país/0 inicial). None si <7."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) < 7:
        return None
    return digits[-9:]


def norm_name(value) -> str | None:
    """Nombre → sin tildes, minúsculas, solo letras, tokens ordenados.

    Order-independiente (apellidos antes/después) y robusto a tildes; un 2º nombre
    faltante cambia el set de tokens, por eso además existe el match fuzzy."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = _strip_accents(str(value)).lower()
    s = re.sub(r"[^a-z\s]", " ", s)
    tokens = [t for t in s.split() if len(t) > 1]
    return " ".join(sorted(tokens)) if tokens else None


def norm_colegio(value) -> str | None:
    """Colegio → canónico (consolida variantes), sin tildes, minúsculas."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = re.sub(r"\s+", " ", str(value).strip())
    key = _strip_accents(s).lower()
    canon = COLEGIO_CANON.get(key, s)
    return _strip_accents(canon).lower()


def display_colegio(value) -> str | None:
    """Nombre de colegio para mostrar (aplica consolidación de variantes)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = re.sub(r"\s+", " ", str(value).strip())
    return COLEGIO_CANON.get(_strip_accents(s).lower(), s)


def canon_ciudad(value) -> str | None:
    """Ciudad → 'iquitos' / 'lago_agrio' desde PE/EC, códigos o etiquetas."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = _strip_accents(str(value)).lower()
    if s in ("pe", "peru") or "iquitos" in s:
        return "iquitos"
    if s in ("ec", "ecuador") or "lago" in s:
        return "lago_agrio"
    return s or None


def _add_norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ndoc"] = df["documento"].map(norm_doc)
    df["nphone"] = df["telefono"].map(norm_phone) if "telefono" in df else None
    df["nname"] = df["nombre"].map(norm_name)
    df["ncolegio"] = df["colegio"].map(norm_colegio)
    df["cciudad"] = df["ciudad"].map(canon_ciudad) if "ciudad" in df else None
    return df


# ════════════════════════════════════════════════════════════════════════════════
# Carga
# ════════════════════════════════════════════════════════════════════════════════

def load_baseline(path: str, grupo: str = "Tratamiento") -> pd.DataFrame:
    """Lee la base unificada, filtra al grupo dado y normaliza llaves.

    Devuelve columnas: codigo, nombre, documento, telefono, colegio (display), grado,
    ciudad ('iquitos'/'lago_agrio'), grupo + columnas normalizadas (ndoc/nphone/nname/
    ncolegio/cciudad)."""
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in BASE_COLS if c not in raw.columns]
    if missing:
        raise ValueError(f"Faltan columnas en la base: {missing}")
    df = raw[list(BASE_COLS)].rename(columns=BASE_COLS)
    if grupo:
        df = df[df["grupo"] == grupo].copy()
    df["ciudad"] = df["pais"].map(canon_ciudad)
    df["colegio"] = df["colegio"].map(display_colegio)
    df = _add_norm_cols(df)
    return df.reset_index(drop=True)


def build_endline_identities(*sources: pd.DataFrame) -> pd.DataFrame:
    """Une las identidades del endline (Kobo + Typeform), normaliza y deduplica.

    Una persona de Lago Agrio puede aparecer en ambas fuentes; se colapsa por
    documento normalizado o, si no hay, por (nombre, colegio)."""
    frames = [s for s in sources if s is not None and not s.empty]
    if not frames:
        return pd.DataFrame(
            columns=["response_id", "submitted_at", "ciudad", "colegio", "grado",
                     "nombre", "documento", "telefono", "correo", "fuente",
                     "ndoc", "nphone", "nname", "ncolegio", "cciudad", "person_key"]
        )
    end = pd.concat(frames, ignore_index=True)
    end["colegio"] = end["colegio"].map(display_colegio)
    end = _add_norm_cols(end)
    def _pkey(r):
        # isinstance, no `if v`: NaN de pandas es truthy y colapsaría todo a una llave.
        if isinstance(r["ndoc"], str) and r["ndoc"]:
            return r["ndoc"]
        if isinstance(r["nname"], str) and r["nname"] and isinstance(r["ncolegio"], str) and r["ncolegio"]:
            return f"{r['nname']}|{r['ncolegio']}"
        return f"rid:{r['response_id']}"  # sin llaves → no colapsar con otros
    end["person_key"] = end.apply(_pkey, axis=1)
    # Conserva el envío más reciente por persona.
    end = end.sort_values("submitted_at").drop_duplicates("person_key", keep="last")
    return end.reset_index(drop=True)


# ════════════════════════════════════════════════════════════════════════════════
# Match en cascada
# ════════════════════════════════════════════════════════════════════════════════

@dataclass
class MatchResult:
    baseline: pd.DataFrame      # base + columnas alcanzado/metodo/endline_response_id
    endline_no_en_base: pd.DataFrame
    aggregate: pd.DataFrame     # por ciudad/colegio/grado, sin PII


def _fuzzy_best(nname: str, candidatos: list[str]) -> float:
    best = 0.0
    for cand in candidatos:
        r = SequenceMatcher(None, nname, cand).ratio()
        if r > best:
            best = r
            if best >= 0.999:
                break
    return best


def match(
    baseline: pd.DataFrame, endline: pd.DataFrame, fuzzy_threshold: float = FUZZY_THRESHOLD
) -> MatchResult:
    """Marca cada persona de la base como alcanzada o no, con el método usado."""
    def ok(v) -> bool:  # str no vacío (evita NaN, que es truthy en pandas)
        return isinstance(v, str) and bool(v)

    doc_index: dict[str, str] = {}
    namecol_index: dict[tuple, str] = {}
    phone_index: dict[str, str] = {}
    names_by_colegio: dict[str, list[str]] = {}

    if not endline.empty:
        for _, e in endline.iterrows():
            rid = e["response_id"]
            if ok(e["ndoc"]):
                doc_index.setdefault(e["ndoc"], rid)
            if ok(e["nname"]) and ok(e["ncolegio"]):
                namecol_index.setdefault((e["nname"], e["ncolegio"]), rid)
                names_by_colegio.setdefault(e["ncolegio"], []).append(e["nname"])
            if ok(e["nphone"]):
                phone_index.setdefault(e["nphone"], rid)

    metodos: list[str | None] = []
    rids: list[str | None] = []
    for _, b in baseline.iterrows():
        metodo = None
        rid = None
        if ok(b["ndoc"]) and b["ndoc"] in doc_index:
            metodo, rid = "documento", doc_index[b["ndoc"]]
        elif ok(b["nname"]) and (b["nname"], b["ncolegio"]) in namecol_index:
            metodo, rid = "nombre+colegio", namecol_index[(b["nname"], b["ncolegio"])]
        elif ok(b["nname"]) and b["ncolegio"] in names_by_colegio:
            cands = names_by_colegio[b["ncolegio"]]
            if _fuzzy_best(b["nname"], cands) >= fuzzy_threshold:
                metodo = "nombre+colegio~fuzzy"
                # localizar el rid del mejor candidato
                best_r, best_name = 0.0, None
                for cand in cands:
                    r = SequenceMatcher(None, b["nname"], cand).ratio()
                    if r > best_r:
                        best_r, best_name = r, cand
                rid = namecol_index.get((best_name, b["ncolegio"]))
        if metodo is None and ok(b["nphone"]) and b["nphone"] in phone_index:
            metodo, rid = "telefono", phone_index[b["nphone"]]
        metodos.append(metodo)
        rids.append(rid)

    base = baseline.copy()
    base["metodo"] = metodos
    base["endline_response_id"] = rids
    base["alcanzado"] = base["metodo"].notna()

    # Endline que no cayó en ninguna persona de la base (posibles nuevos / IDs sucios).
    matched_rids = set(r for r in rids if r)
    no_base = endline[~endline["response_id"].isin(matched_rids)] if not endline.empty \
        else endline

    return MatchResult(
        baseline=base,
        endline_no_en_base=no_base.reset_index(drop=True),
        aggregate=aggregate(base),
    )


def aggregate(matched_baseline: pd.DataFrame) -> pd.DataFrame:
    """Cobertura por ciudad/colegio/grado. Sin nombres → apto para vista pública."""
    if matched_baseline.empty:
        return pd.DataFrame(
            columns=["ciudad", "colegio", "grado", "meta", "alcanzados", "faltan", "pct"]
        )
    g = (
        matched_baseline.assign(_grado=matched_baseline["grado"].replace("", "(sin grado)"))
        .groupby(["ciudad", "colegio", "_grado"], dropna=False)
        .agg(meta=("alcanzado", "size"), alcanzados=("alcanzado", "sum"))
        .reset_index()
        .rename(columns={"_grado": "grado"})
    )
    g["faltan"] = g["meta"] - g["alcanzados"]
    g["pct"] = (g["alcanzados"] / g["meta"] * 100).round(1)
    return g.sort_values(["ciudad", "colegio", "grado"]).reset_index(drop=True)


# ════════════════════════════════════════════════════════════════════════════════
# Llaves HMAC para el dashboard live (sin PII en texto plano)
# ════════════════════════════════════════════════════════════════════════════════

def _hmac(salt: str, value: str | None) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return hmac.new(salt.encode(), value.encode(), hashlib.sha256).hexdigest()


def build_baseline_keys(baseline: pd.DataFrame, salt: str) -> pd.DataFrame:
    """Tabla por persona de la base con llaves HMAC (no reversibles sin el salt).

    Columnas: codigo, ciudad, colegio, grado, grupo, hash_doc, hash_namecol. Seguro de
    commitear: no contiene nombres ni documentos en texto plano (el código AMA es
    pseudónimo). El dashboard hashea el endline live con el mismo salt y cuenta matches.
    """
    out = pd.DataFrame({
        "codigo": baseline["codigo"],
        "ciudad": baseline["ciudad"],
        "colegio": baseline["colegio"],
        "grado": baseline["grado"],
        "grupo": baseline["grupo"],
        "hash_doc": baseline["ndoc"].map(lambda v: _hmac(salt, v)),
        "hash_namecol": baseline.apply(
            lambda r: _hmac(salt, f"{r['nname']}|{r['ncolegio']}")
            if isinstance(r["nname"], str) and isinstance(r["ncolegio"], str) else None,
            axis=1,
        ),
    })
    return out.reset_index(drop=True)


def coverage_from_keys(keys: pd.DataFrame, endline: pd.DataFrame, salt: str) -> pd.DataFrame:
    """Cobertura live: marca alcanzado por match exacto de HMAC (doc o nombre+colegio).

    No incluye fuzzy ni teléfono (no se pueden hashear de forma exacta), así que es una
    **cota inferior** de la cobertura — el reporte de campo offline es la cifra completa.
    Devuelve `keys` + columnas alcanzado/metodo."""
    end_docs: set[str] = set()
    end_namecol: set[str] = set()
    if not endline.empty:
        for _, e in endline.iterrows():
            if isinstance(e["ndoc"], str) and e["ndoc"]:
                end_docs.add(_hmac(salt, e["ndoc"]))
            if isinstance(e["nname"], str) and isinstance(e["ncolegio"], str):
                end_namecol.add(_hmac(salt, f"{e['nname']}|{e['ncolegio']}"))

    def mark(row):
        if row["hash_doc"] and row["hash_doc"] in end_docs:
            return "documento"
        if row["hash_namecol"] and row["hash_namecol"] in end_namecol:
            return "nombre+colegio"
        return None

    out = keys.copy()
    out["metodo"] = out.apply(mark, axis=1)
    out["alcanzado"] = out["metodo"].notna()
    return out
