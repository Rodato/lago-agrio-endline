# CLAUDE.md

Guía para Claude Code trabajando en este repo.

## Qué es esto

Dashboard en vivo del **endline del programa AMA** (Estudio Plural). Lee directo de
**dos fuentes** (seleccionables con un toggle en el sidebar) y muestra avance +
completitud por pregunta al equipo de campo mientras todavía se puede corregir:

- **Typeform** — form de Lago Agrio.
- **KoboToolbox** — "Encuesta de Salida AMA", cubre Iquitos (Perú) + Lago Agrio (Ecuador).

Enlaces:
- App live: https://lago-agrio-endline-pcm4jbzyvmekla63l4lwl8.streamlit.app/
- Repo: https://github.com/Rodato/lago-agrio-endline
- Línea de base (proyecto hermano, ya procesado): `~/Documents/Dev/AMA/Preprocesamiento/`

## Stack

- **Streamlit** + `streamlit-autorefresh` (refresh global cada 30s).
- **httpx** para llamar las APIs de Typeform y Kobo directo, sin DB intermedia.
- **plotly.graph_objects** para todas las gráficas, con tema oscuro custom.
- **pandas** para la transformación de datos in-memory.
- **Python 3.11** (Homebrew). Definido en `runtime.txt`.

Sin Supabase, sin webhooks, sin Airtable. Esa decisión fue intencional — ver
`memory/feedback_minimum_stack.md` para el contexto.

## Estructura

```
dashboard/
├── app.py                  # Selector de fuente + dos tabs: AVANCE y COMPLETITUD
└── lib/
    ├── db.py               # Cliente Typeform + cache 30s + paginación
    ├── kobo.py             # Cliente KoboToolbox + cache 30s + completitud por label
    ├── normalize.py        # form_response Typeform → (response_row, [answer_rows])
    ├── completion.py       # % completitud por pregunta Typeform (maneja matrices)
    └── theme.py            # CSS Bloomberg + base_layout() Plotly + html_table()
```

**Vistas agnósticas de la fuente**: cada rama (Typeform / Kobo) produce un
`responses` DataFrame con columnas comunes (`response_id`, `submitted_at` tz-aware,
y `hidden_*` opcionales) y un `comp` DataFrame `[pregunta, respondidas, total, pct]`.
Los tabs AVANCE/COMPLETITUD consumen esas dos estructuras sin saber la fuente.

Estilo visual: **Bloomberg Terminal** — fondo negro `#080808`, acento amber
`#FFB300`, IBM Plex Mono. Inspirado en `~/Documents/Dev/AMA/Bot_monitoring/src/app.py`.
Ese repo es el template canónico — si toca expandir el theme, reusar de ahí.

## Datos del form

### Typeform (`FORM_ID = iQOI4UBK`)
- **Title**: "Colegios: Encuesta de línea salida Programa AMA Lago Agrio".
- **47 preguntas únicas** (52 fields top-level — la pregunta "¿En qué grado estás?"
  tiene 6 variantes con branching por colegio).
- **Hidden fields nativos: ninguno**. El "encuestador", "colegio" y "barrio" son
  preguntas regulares dentro del form; se mapean a columnas `hidden_*` vía
  `secrets.toml::field_refs` (ver `db.py::_attach_field_refs_as_hidden`).
- **Datos sucios conocidos**: encuestadores escritos inconsistentemente
  ("Katherine Gómez" en 5 variantes). Decidimos dejarlo así por ahora; si toca
  normalizar, opciones: lowercase + strip, o fuzzy matching con lista canónica.

### Kobo (`KOBO_ASSET_UID = aDwUvGp5bSWbRcXyhESW7R`, servidor global `kf.kobotoolbox.org`)
- **Title**: "Encuesta de Salida AMA". Cubre Iquitos + Lago Agrio.
- Envíos = dicts planos con claves `grupo/pregunta` (`datos_colegio/colegio_final`,
  `phq9/phq_1`). El último segmento de la clave es el `name` del XLSForm.
- **No hay encuestador** (`_submitted_by = None`, envíos web). → Kobo añade filtro
  **CIUDAD**. El ranking del tab AVANCE es **por colegio en ambas fuentes** (el de
  encuestadores se quitó: datos sucios en Typeform). El KPI "ENCUESTADORES" sigue solo
  en Typeform (cuenta de `hidden_encuestador`); en Kobo el KPI es "COLEGIOS".
- `hidden_colegio` ← `datos_colegio/colegio_final` (código `ie_cascales` → etiqueta vía
  listas `escuelas_iquitos` + `escuelas_lagoagrio`). `hidden_ciudad` ← `ciudad`.
- **Completitud por label**: `kobo.completion_by_label` agrupa preguntas por etiqueta
  (colapsa las ~15 variantes de "¿En qué grado estás?" y las 2 de colegio, igual que
  la lógica de matrices de Typeform). Excluye `note`, `calculate`, `start/end/today`,
  grupos y `meta`. `submitted_at` = `_submission_time` (UTC).

## Cómo correr local

```bash
cd ~/Documents/Dev/AMA/Lineasalida2026/lago-agrio
source .venv/bin/activate     # python3.11 -m venv .venv si no existe
pip install -r requirements.txt
streamlit run dashboard/app.py
```

Necesitas `.streamlit/secrets.toml` con `TYPEFORM_TOKEN` + `FORM_ID` (+ `field_refs`) y
`KOBO_TOKEN` + `KOBO_ASSET_UID` (+ `KOBO_BASE`). Plantilla en `.streamlit/secrets.toml.example`.

## Deploy

- **Streamlit Community Cloud** conectado al repo. Cada push a `main` redespliega.
- Secrets viven en Streamlit Cloud → app settings (no en el repo). Al agregar Kobo,
  pegar `KOBO_BASE`/`KOBO_TOKEN`/`KOBO_ASSET_UID` ahí también.
- Si rotas un token (`TYPEFORM_TOKEN` o `KOBO_TOKEN`), actualízalo en Streamlit Cloud.

## Bugs conocidos / cosas a saber

- **NaN truthiness**: pandas devuelve `np.nan` (que es truthy) en celdas vacías.
  En `db.py::_attach_field_refs_as_hidden` usamos `.where(notna())` en vez de `or`.
  Si añades coalesce de columnas, no uses `r.get(c1) or r.get(c2)`.
- **Matrices Typeform**: las preguntas tipo `matrix` mandan answers con el
  `field_id` de cada **subpregunta** (fila), no del contenedor. `completion.py`
  expande con `_all_ids()` para incluir subfields. Si Typeform agrega más tipos
  de container (group, etc.), revisar.
- **Cold start de Streamlit Cloud**: si nadie abre el link por horas, la app
  duerme. Primera carga después tarda ~15-20s.

## Fuera de alcance hoy (siguiente fase)

Si el usuario pide algo de esto, queda claro que es trabajo nuevo:
- Distribuciones **P31-P46 en vivo** (reusar `src/variables_encuesta_informe.py`
  y `src/generar_graficas_informe.py` del repo `Preprocesamiento/`).
- Comparación **baseline vs endline** (cruzar con
  `outputs/AMA_encuesta_LagoAgrio_cleaned.csv` del baseline).
- **Export a CSV** con el formato del informe del baseline para alimentar el
  pipeline de análisis final.
- Notificaciones (Slack/email) por meta cumplida o anomalías.
- Normalización fuzzy de nombres de encuestadores.

## Convenciones

- Comentarios en español, código en inglés (variables, funciones).
- Datos no se commitean — el repo es solo código.
- Si tocas el form en Typeform (agregar/quitar pregunta), no hay que cambiar
  código: el dashboard adapta solo en el siguiente refresh (60s para form
  definition).
