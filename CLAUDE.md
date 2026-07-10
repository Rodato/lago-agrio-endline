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
├── app.py                  # Selector de fuente + tabs: AVANCE, COMPLETITUD, COBERTURA, BOT
├── data/
│   └── baseline_keys.parquet  # Llaves HMAC de la base (sin PII) para la cobertura live
└── lib/
    ├── db.py               # Cliente Typeform + cache 30s + paginación + get_identities
    ├── kobo.py             # Cliente KoboToolbox + cache 30s + completitud + get_identities
    ├── normalize.py        # form_response Typeform → (response_row, [answer_rows])
    ├── completion.py       # % completitud por pregunta Typeform (maneja matrices)
    ├── coverage.py         # Motor de cruce base↔endline (normalización, match, HMAC)
    └── theme.py            # CSS Bloomberg + base_layout() Plotly + html_table()
scripts/
├── cruce_cobertura.py      # CLI: reporte privado de cobertura (PII) + parquet de llaves
├── informe_cobertura_excel.py     # CLI: cobertura uno-a-uno .xlsx multi-hoja (PII)
├── informe_salida_excel.py        # CLI: conteo de salida (únicos) por ciudad/colegio
├── informe_base_vs_salida_excel.py  # CLI: comparativo agregado base↔salida por colegio
└── informe_entrada_salida_excel.py  # CLI: export 2 pestañas (entrada + salida) nivel persona
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
- **Iconos Material vs override de fuente**: el CSS de `theme.py` fuerza monospace
  global con `!important` sobre `[class*="css"]`, lo que pisa la fuente de los iconos
  Material Symbols de Streamlit y los muestra como **texto** (p. ej. la flecha de
  colapsar el sidebar salía como "keyboard_double_arrow_left"). Hay una regla al final
  de `_CSS` que restaura `font-family: 'Material Symbols Rounded'` para
  `[data-testid="stIconMaterial"]`. Si agregas widgets nuevos con iconos que salgan
  como texto, amplía ese selector.
- **Tablas/charts largos → contenedores scrolleables, no estirar la página**:
  `theme.py::html_table(..., max_height=360)` envuelve la tabla en un div scrolleable
  con header sticky. Para gráficas Plotly altas (p. ej. completitud con ~108 preguntas)
  usar `with st.container(height=...)` alrededor del `st.plotly_chart`. Mantener este
  patrón si agregas tablas/charts que crezcan con los datos.
- **`use_container_width` deprecado**: Streamlit (>=1.57 instalado) avisa que se
  reemplaza por `width='stretch'`/`'content'` (deadline ya pasó: 2025-12-31). Hoy solo
  warnings, no rompe. Migrar los `st.plotly_chart(..., use_container_width=True)` cuando
  toque limpiar.
- **`.venv` con shebang roto**: el proyecto se movió de `~/Desktop/Dev/AMA` a
  `~/Documents/Dev/AMA`, así que el shebang de los scripts del venv apunta a una ruta
  vieja y `streamlit run ...` directo falla. Workaround local: `.venv/bin/python -m
  streamlit run dashboard/app.py`. Prod (Streamlit Cloud) no se afecta.

## Cobertura · versus línea de base (tab COBERTURA)

Responde lo esencial del endline: de los que medimos en la **línea de base** (grupo
**Tratamiento**, 1.683 personas), ¿a cuántos re-alcanzamos y **quiénes faltan**.

- **Base**: `~/Documents/Dev/AMA/Preprocesamiento/outputs/AMA_encuesta_unificada.csv`
  (Iquitos+Lago Agrio), filtrada a `META_04=='Tratamiento'`. Los colegios de cada grupo
  son fijos (ver `EncuestaSalida/koboreferenceforms/colegios_grados_iquitosylagoagrio.md`);
  los labels de colegio del endline **coinciden exactos** con `DEM_05`.
- **Identidad endline**: `kobo.get_identities()` (Iquitos+Lago Agrio, grupo
  `datos_personales/`) + `db.get_identities()` (Typeform Lago Agrio, por título de
  pregunta). Se unen y deduplican en `coverage.build_endline_identities`.
- **Match en cascada** (`coverage.match`): documento normalizado → nombre+colegio
  exacto → nombre+colegio fuzzy (`difflib`, ≥0.88) → teléfono. El documento solo está
  en ~70% de la base, por eso el fuzzy de nombre es imprescindible.
- **Dedup — dos fixes (2026-06-23, subestimaban la salida ~3,9 pts):**
  1. **Documentos placeholder**: los encuestadores tipean rellenos cuando no tienen la
     cédula (`11111111` = 199 casos, `12345678`, `99999999999`, `123456` — 223 respuestas).
     Como el `person_key` del dedup era el documento, colapsaban personas distintas que
     compartían el relleno y se **borraban ~269 respuestas reales** antes del match.
     `coverage.norm_doc` ahora los descarta (`_is_placeholder_doc`: todo-mismo-dígito o
     secuencia) → cuentan como "sin documento".
  2. **NaN truthy en `_pkey`**: el chequeo era `if r["ndoc"]:`, pero un `NaN` de pandas es
     truthy → al volverse None los placeholders, se re-colapsaban a una sola llave NaN.
     Corregido a `isinstance(r["ndoc"], str)` (la convención del resto del módulo).
  Efecto: cobertura 889→**955/1683 (52.8%→56.7%)**; salida única 2288→**2557**.
- **PII**: la lista nominal de faltantes (nombre, documento, teléfono) **nunca toca el
  dashboard público**. Vive solo en `outputs/` (gitignored). El dashboard lee
  `data/baseline_keys.parquet`, que contiene **HMAC** de las llaves (salt
  `COVERAGE_SALT`, no commiteado) — sin texto plano. El tab cruza esos hashes contra el
  endline live: es una **cota mínima** (solo match exacto, sin fuzzy/teléfono).

### Regenerar el cruce
```bash
COVERAGE_SALT=... .venv/bin/python scripts/cruce_cobertura.py
```
Produce (en `outputs/`, gitignored): `faltantes.csv` (PII, para campo),
`cobertura_resumen.csv` (agregado anónimo), `endline_no_en_base.csv` (QA: endline en
colegios Tratamiento sin match = posibles nuevos / IDs sucios). Y reescribe
`dashboard/data/baseline_keys.parquet`. **El salt debe ser el mismo en el script y en
los secrets del dashboard** (local + Streamlit Cloud); si lo rotas, regenera el parquet.

### Informe Excel por ciudad/colegio (para el equipo)
```bash
.venv/bin/python scripts/informe_cobertura_excel.py
```
Reusa el mismo motor (`lib/coverage.py`) y arma `outputs/informe_cobertura_AMA_<fecha>.xlsx`
(gitignored, PII) con 5 hojas: **Resumen** (cobertura por colegio + métodos de match +
semáforo), **Cobertura x grado** (con cohorte Escolar/Egresado en Iquitos), **Faltan**
(nominal de "de menos"), **Revisar match** (los matches `fuzzy`+`teléfono`, baja confianza,
con base vs salida lado a lado para verificar a mano) y **De más** (endline en colegios
Tratamiento sin match). Necesita `openpyxl` (instalado en el `.venv`, **NO** en
`requirements.txt` a propósito: es herramienta de análisis, no del deploy del dashboard).

**Clave para interpretar "De más":** que un registro caiga ahí **no** implica que sea una
persona ajena a la base — casi siempre es alguien que SÍ estaba en la base pero cuyo
registro no coincidió con el patrón de cruce (documento digitado distinto, nombre escrito de
otra forma, base sin documento, o teléfono que no pega). Es material de **revisión manual**,
no un conteo de "nuevos".

**Camilo Gallegos — Typeform+Kobo = COMPLEMENTO, no duplicado** (confirmado por campo,
jun-2026): ese colegio se encuestó por los dos canales cubriendo cursos distintos (verificado:
152 solo-Kobo + 86 solo-Typeform + 54 en ambas). NO deduplicar entre fuentes ni tratar su
footprint alto como inflado. El deck de campo reporta 175 encuestados pero el pull live ve
~292 distintos → ahí el corto es el deck, no el cruce.

**Snapshot (2026-06-23, post-fix):** cobertura global 955/1683 (**56.7%**) · Iquitos
~401/935 (~42.9%, arrastrado por egresados pendientes) · Lago Agrio ~554/748 (~74.1%).
Faltan 728, "de más" ~246, matches a revisar ~111. (Pre-fix 2026-06-22 era 889/52.8% —
la diferencia son los +66 que recuperó el fix de placeholders.)

## Dos lecturas distintas: cobertura (uno-a-uno) vs agregado (volumen)

**No confundir.** El equipo pidió (jun-2026) un informe de salida simple y se aclaró que la
cobertura subestima por diseño:

- **Cobertura** (`informe_cobertura_excel.py`): cuenta a una persona de la base **solo si la
  enlaza, una a una**, con una respuesta de la salida. Es lo que mide impacto/seguimiento,
  pero **pierde información** porque no hay identificador compartido confiable:
  (1) el documento falta en ~30% de la base (**320 de 728 faltantes sin cédula**) y viene
  falseado en la salida (placeholders, ya filtrados); (2) sin documento cae a nombre+colegio,
  frágil entre dos encuestas con meses de diferencia (abreviaturas, apellido faltante, typos);
  (3) **los estudiantes nuevos no suman** a cobertura (no están en la base). Tras el fix la fuga
  residual es chica (~6 faltantes con nombre casi-igual en la salida; antes 47) → los 728 que
  faltan son, mayormente, **gente todavía no encuestada** (sobre todo Iquitos, levantamiento abierto).
- **Agregado / volumen** (`informe_salida_excel.py`, `informe_base_vs_salida_excel.py`): cuenta
  **cuántos respondieron por colegio**, sin enlazar persona a persona. No castiga por nombres mal
  escritos ni por no poder cruzar; es la lectura honesta del avance. Por eso un colegio puede
  pasar de 100% (Camilo, Lumbaqui) al incluir estudiantes nuevos. Es lo que se le envió al equipo.

### Informes nuevos
```bash
.venv/bin/python scripts/informe_salida_excel.py          # salida: únicos por ciudad/colegio
.venv/bin/python scripts/informe_base_vs_salida_excel.py  # base (todos los grupos) vs salida
.venv/bin/python scripts/informe_entrada_salida_excel.py  # export 2 pestañas nivel persona (PII)
```
- **`informe_salida_excel.py`** → `informe_salida_AMA_<fecha>.xlsx` (agregado, sin PII en texto
  plano): personas únicas de la salida por ciudad/colegio, **todos** los colegios
  (Tratamiento+Control+otros), con desglose Kobo/Typeform. Una fila `(colegio sin registrar)`
  para los envíos sin colegio (Iquitos 154).
- **`informe_base_vs_salida_excel.py`** → `informe_base_vs_salida_AMA_<fecha>.xlsx` (agregado):
  comparativo de volumen base↔salida por ciudad/colegio (+ resumen por grupo). Base =
  `load_baseline(grupo=None)` (3.280 = Trat 1.683 + Control 1.588 + 9 sin asignar). Todos los
  colegios de la salida cruzan con la base (los únicos que no son registros sin colegio).
  `Salida/Base %` es **volumen, no cobertura**.
- **`informe_entrada_salida_excel.py`** → `entrada_salida_AMA_<fecha>.xlsx` (**PII nivel persona,
  uso interno**): dos pestañas. *Entrada* = consolidado base nivel persona (3.280, todos los grupos,
  con columna Grupo para filtrar a Tratamiento). *Salida* = identidades cruzadas Kobo+Typeform
  deduplicadas (2.557, con columna Fuente). El documento en *Salida* se deja **crudo** (placeholders
  visibles); el "limpio" se refiere al dedup, no a borrar valores.

**Verificado (2026-06-23):** el dedup de la salida NO pierde personas distintas — de las 424
respuestas que quita, **423 colapsan por documento idéntico** (misma persona) y 1 por nombre+colegio
(mismo teléfono, Typeform+Kobo). Salida única 2.557 (2.981 crudas). Base↔salida: Lago Agrio
prácticamente al día (1.485/1.532), Iquitos rezagado (1.072/1.748).

## Match asistido por LLM de los no-cruzados (2026-06-25)

Sobre los registros que el cruce **determinista** no pudo enlazar (los **728 faltantes** y los
**333 "de más"** = endline en colegios Tratamiento sin cruce), se hizo un segundo pase de
record-linkage con **Claude Sonnet 4.6** para recuperar lo que `difflib<0.88` pierde: base con
solo nombre + 1er apellido y **sin documento** (p.ej. base "Anna Apagueño" → salida "Ana Rosita
Apagüeño Angulo"), orden de apellidos, abreviaturas, typos de documento.

- **Cómo** (no hay `ANTHROPIC_API_KEY` local, por eso NO se usó el SDK): **8 subagentes** vía el
  Agent tool de Claude Code, **uno por colegio** (bloqueo por colegio; los labels coinciden exactos
  base↔endline). Cada subagente recibió las dos listas del colegio y devolvió pares
  `{codigo, response_id, confianza alto|medio|bajo, razón}`. Criterio conservador (son menores) y
  1-a-1. Teléfono ignorado (en Typeform suele ser el del encuestador).
- **Resultado:** **101 pares propuestos** (86 alto, 15 medio) + 4 dudosos. **Cero IDs alucinados**
  (todos validados contra `faltantes.csv`/`endline_no_en_base.csv`). Efecto potencial si se
  confirman: 56.7% → **61.9%** (solo alto) → **62.7%** (alto+medio). Es **worklist de verificación
  humana, NO cobertura auto-aplicada**: no se tocó el cruce ni el parquet del dashboard.
- **Re-corrida de cobertura 2026-06-25:** 955/1683 = **56.7%** (idéntica a 23-jun; salida única 2.557).
  El cruce fresco confirma el universo que vio el LLM (faltantes 728=728, de más 333=333).

**Entregable:** `outputs/matching_AMA_<fecha>.xlsx` (PII de menores, gitignored), 4 hojas:
**Resumen** · **Match determinista** (955 ya cruzados, con nombre tal como aparece en la salida +
método; solo referencia) · **Match LLM · validar** (101, con columnas vacías `¿Correcto? (sí/no/dudo)`
/ `Validado por` / `Notas` para que un humano confirme; verde=alto, amarillo=medio; muestra nombre
de salida) · **Revisar · otras** (855 = 4 dudosos + 623 faltantes sin candidato + 228 "de más";
autofiltro por Ciudad/Tipo). Los "faltante sin candidato" (Iq 493, LA 130) son, casi seguro, gente
**aún no encuestada** (Iquitos rezagado).

**Pipeline NO persistido:** el prep por colegio (`inputs/*.json`), los prompts de los 8 subagentes y
el ensamblador (`build_xlsx_v2.py`) quedaron en el scratchpad de esa sesión (efímero), no en
`scripts/`. Para re-correr: regenerar los 8 bloques por colegio desde `faltantes.csv` +
`endline_no_en_base.csv`, lanzar 8 subagentes Sonnet 4.6 (uno por colegio), y ensamblar el xlsx.

## Fuera de alcance hoy (siguiente fase)

Si el usuario pide algo de esto, queda claro que es trabajo nuevo:
- Distribuciones **P31-P46 en vivo** (reusar `src/variables_encuesta_informe.py`
  y `src/generar_graficas_informe.py` del repo `Preprocesamiento/`).
- **Export a CSV** con el formato del informe del baseline para alimentar el
  pipeline de análisis final.
- **Análisis de cambio** entrada→salida por variable (impacto), distinto de cobertura.
- Notificaciones (Slack/email) por meta cumplida o anomalías.
- Normalización fuzzy de nombres de encuestadores.

## Convenciones

- Comentarios en español, código en inglés (variables, funciones).
- Datos no se commitean — el repo es solo código.
- Si tocas el form en Typeform (agregar/quitar pregunta), no hay que cambiar
  código: el dashboard adapta solo en el siguiente refresh (60s para form
  definition).
