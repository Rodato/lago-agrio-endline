# Encuesta de línea de salida · Programa AMA

**🚀 Dashboard en vivo:** https://lago-agrio-endline-pcm4jbzyvmekla63l4lwl8.streamlit.app/

Monitorea el levantamiento de la encuesta de salida del Programa AMA desde **dos
fuentes** seleccionables en el sidebar — **Typeform** (Lago Agrio) y **KoboToolbox**
(Iquitos + Lago Agrio). Lee directo de cada API con cache de 30s — sin base de datos,
sin webhooks. Estilo Bloomberg Terminal.

```
Typeform API  ─┐
               ├──poll cache 30s──  Streamlit  (selector de fuente)
Kobo API      ─┘
```

## Estructura

```
lago-agrio/
├── requirements.txt           # deps para Streamlit Cloud
├── runtime.txt                # python-3.11
├── pyproject.toml
├── .streamlit/secrets.toml.example
└── dashboard/
    ├── app.py                 # selector de fuente + dos tabs (AVANCE + COMPLETITUD)
    └── lib/
        ├── db.py              # cliente Typeform + cache
        ├── kobo.py            # cliente KoboToolbox + cache + completitud por label
        ├── normalize.py       # answers Typeform → filas planas
        ├── completion.py      # % completitud por pregunta (Typeform)
        └── theme.py           # CSS Bloomberg + helpers Plotly/HTML
```

## Setup

### 1. Entorno Python

```bash
cd ~/Documents/Dev/AMA/Lineasalida2026/lago-agrio
/opt/homebrew/bin/python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Credenciales de las fuentes

**Typeform**
1. https://admin.typeform.com → **Account → Personal tokens → Generate**.
   Scopes mínimos: `responses:read`, `forms:read`. Guardar el token (`tfp_...`).
2. El `FORM_ID` es el código alfanumérico al final de la URL del form:
   `https://admin.typeform.com/form/<FORM_ID>/...`.

**KoboToolbox** (servidor global `kf.kobotoolbox.org`)
1. Token: ícono de cuenta → **Account Settings → Security → API Key**
   (o https://kf.kobotoolbox.org/token/?format=json estando logueado).
2. El `KOBO_ASSET_UID` es el código en la URL del form:
   `https://kf.kobotoolbox.org/#/forms/<UID>/...`.

### 3. Secrets de Streamlit

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Rellenar TYPEFORM_TOKEN + FORM_ID, KOBO_TOKEN + KOBO_ASSET_UID, y opcionalmente goals.
```

### 4. Levantar el dashboard

```bash
streamlit run dashboard/app.py
```

Abre http://localhost:8501. Elige la **FUENTE** (Typeform / Kobo) en el sidebar; los tabs
AVANCE y COMPLETITUD se recalculan para la fuente elegida. Auto-refresh cada 30s.

## Deploy a Streamlit Community Cloud

1. https://share.streamlit.io → **New app** → conectar GitHub.
2. Seleccionar repo `Rodato/lago-agrio-endline`, branch `main`,
   **Main file path**: `dashboard/app.py`.
3. **Advanced settings → Secrets**: pegar exactamente el contenido de tu
   `.streamlit/secrets.toml` local (tokens y IDs de Typeform **y Kobo**, field_refs, goals).
4. **Deploy**. Streamlit Cloud detecta `requirements.txt` y `runtime.txt` solo.
5. Compartir el link al equipo de campo (puedes proteger el app con
   `streamlit_authenticator` o el control de acceso GitHub si quieres limitarlo).

## Hidden fields esperados

El dashboard auto-detecta hidden fields que contengan `encuestador`,
`comunidad`, `colegio`, `barrio` o `lugar` en su nombre. El link compartido
al equipo de campo debe incluirlos como query params:

```
https://....typeform.com/to/{FORM_ID}#encuestador=Juan&comunidad=Nueva+Loja
```

## Fuente Kobo

- Asset "Encuesta de Salida AMA" (`kf.kobotoolbox.org`), cubre Iquitos (Perú) y
  Lago Agrio (Ecuador).
- **No captura encuestador** (envíos vía web, `_submitted_by` vacío). Kobo añade un
  **filtro de CIUDAD** en el sidebar. (El ranking del tab AVANCE es **por colegio** en
  ambas fuentes; el de encuestadores se quitó por datos sucios en Typeform.)
- `colegio` y `ciudad` salen de `colegio_final` y `ciudad` del form; los códigos
  (`ie_cascales`, `lago_agrio`) se mapean a etiquetas legibles vía las listas de
  opciones del asset.

## Operación

- Si el form cambia (preguntas nuevas), el dashboard se actualiza solo en el
  siguiente refresh del cache (60s para form definition).
- Si Typeform tiene caída, el dashboard mostrará error. Reintenta solo cuando
  vuelve.
- Para análisis offline al final del levantamiento: el endpoint `GET /forms/{id}/responses`
  pagina todo, exportarlo a CSV es trivial (escribimos un script si hace falta).

## Fuera de alcance (siguiente fase)

- Distribuciones P31-P46 en vivo (reusando código de `~/Documents/Dev/AMA/Preprocesamiento/src/`).
- Comparación baseline vs endline.
- Notificaciones (Slack/email) al llegar a meta.
- Export final a CSV con el formato del informe del baseline.
