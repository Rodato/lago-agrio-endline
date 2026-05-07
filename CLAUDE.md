# CLAUDE.md

Guía para Claude Code trabajando en este repo.

## Qué es esto

Dashboard en vivo del **endline del programa AMA en Lago Agrio** (Estudio Plural).
Lee directo de la Typeform API y muestra avance + completitud por pregunta al
equipo de campo mientras todavía se puede corregir.

- App live: https://lago-agrio-endline-pcm4jbzyvmekla63l4lwl8.streamlit.app/
- Repo: https://github.com/Rodato/lago-agrio-endline
- Línea de base (proyecto hermano, ya procesado): `~/Desktop/Dev/AMA/Preprocesamiento/`

## Stack

- **Streamlit** + `streamlit-autorefresh` (refresh global cada 30s).
- **httpx** para llamar la Typeform API directo, sin DB intermedia.
- **plotly.graph_objects** para todas las gráficas, con tema oscuro custom.
- **pandas** para la transformación de datos in-memory.
- **Python 3.11** (Homebrew). Definido en `runtime.txt`.

Sin Supabase, sin webhooks, sin Airtable. Esa decisión fue intencional — ver
`memory/feedback_minimum_stack.md` para el contexto.

## Estructura

```
dashboard/
├── app.py                  # Una página, dos tabs: AVANCE y COMPLETITUD
└── lib/
    ├── db.py               # Cliente Typeform + cache 30s + paginación
    ├── normalize.py        # form_response → (response_row, [answer_rows])
    ├── completion.py       # % completitud por pregunta (maneja matrices)
    └── theme.py            # CSS Bloomberg + base_layout() Plotly + html_table()
```

Estilo visual: **Bloomberg Terminal** — fondo negro `#080808`, acento amber
`#FFB300`, IBM Plex Mono. Inspirado en `~/Desktop/Dev/AMA/Bot_monitoring/src/app.py`.
Ese repo es el template canónico — si toca expandir el theme, reusar de ahí.

## Datos del form

- **FORM_ID**: `iQOI4UBK` (en `.streamlit/secrets.toml`).
- **Title**: "Colegios: Encuesta de línea salida Programa AMA Lago Agrio".
- **47 preguntas únicas** (52 fields top-level — la pregunta "¿En qué grado estás?"
  tiene 6 variantes con branching por colegio).
- **Hidden fields nativos: ninguno**. El "encuestador", "colegio" y "barrio" son
  preguntas regulares dentro del form; se mapean a columnas `hidden_*` vía
  `secrets.toml::field_refs` (ver `db.py::_attach_field_refs_as_hidden`).
- **Datos sucios conocidos**: encuestadores escritos inconsistentemente
  ("Katherine Gómez" en 5 variantes). Decidimos dejarlo así por ahora; si toca
  normalizar, opciones: lowercase + strip, o fuzzy matching con lista canónica.

## Cómo correr local

```bash
cd ~/Desktop/Dev/AMA/Lineasalida2026/lago-agrio
source .venv/bin/activate     # python3.11 -m venv .venv si no existe
pip install -r requirements.txt
streamlit run dashboard/app.py
```

Necesitas `.streamlit/secrets.toml` con `TYPEFORM_TOKEN`, `FORM_ID` y los `field_refs`.
Plantilla en `.streamlit/secrets.toml.example`.

## Deploy

- **Streamlit Community Cloud** conectado al repo. Cada push a `main` redespliega.
- Secrets viven en Streamlit Cloud → app settings (no en el repo).
- Si rotas el `TYPEFORM_TOKEN`, actualízalo en Streamlit Cloud directamente.

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
