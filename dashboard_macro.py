"""
Dashboard de indicadores macroeconómicos por país.

Cómo correrlo:
    streamlit run dashboard_macro.py

Requiere:
    pip install streamlit pandas plotly pyarrow
    # opcional, para la línea de tendencia en el gráfico de dispersión:
    pip install statsmodels

Lee siempre el archivo parquet fijo definido en DATA_PATH más abajo
(por ejemplo, el que generas en tu notebook con merged_df.to_parquet(...)).
No hay selector de archivo ni carga desde la interfaz: el dashboard usa
únicamente esta fuente de datos.
"""

import os

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Dashboard Macro", layout="wide")

# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------

# Ruta fija del archivo de datos. Ajusta esta ruta a donde guardes tu parquet
# (por ejemplo, el resultado de merged_df.to_parquet('Macro paises.parquet')).
DATA_PATH = "Macro paises.parquet"


@st.cache_data
def load_data(path: str, mtime: float) -> pd.DataFrame:
    # `mtime` no se usa dentro de la función, pero forma parte de la llave de
    # caché: si el archivo cambia de fecha de modificación (se regeneró desde
    # el notebook), Streamlit invalida el caché automáticamente y recarga.
    df = pd.read_parquet(path)
    df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
    return df


if not os.path.isfile(DATA_PATH):
    st.error(
        f"No encontré el archivo de datos '{DATA_PATH}'. "
        "Verifica que exista en la carpeta desde donde corres la app "
        "(o ajusta la constante DATA_PATH en el script)."
    )
    st.stop()

df = load_data(DATA_PATH, os.path.getmtime(DATA_PATH))

indicadores = [c for c in df.columns if c not in ["economy", "time"]]
paises_disponibles = sorted(df["economy"].dropna().unique())

# ---------------------------------------------------------------------------
# Controles (selector de países en el dashboard)
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Filtros")

    paises_default = paises_disponibles[:5] if len(paises_disponibles) >= 5 else paises_disponibles
    paises_sel = st.multiselect(
        "Países a comparar",
        options=paises_disponibles,
        default=paises_default,
    )

    indicador_sel = st.selectbox("Indicador principal", options=indicadores)

    anio_min, anio_max = int(df["time"].min()), int(df["time"].max())
    rango_anios = st.slider(
        "Rango de años",
        min_value=anio_min, max_value=anio_max,
        value=(anio_min, anio_max),
    )

if not paises_sel:
    st.warning("Selecciona al menos un país en la barra lateral.")
    st.stop()

df_f = df[
    df["economy"].isin(paises_sel)
    & df["time"].between(rango_anios[0], rango_anios[1])
].sort_values(["economy", "time"])

# ---------------------------------------------------------------------------
# Layout principal
# ---------------------------------------------------------------------------

st.title("📊 Dashboard Macroeconómico")
st.caption(f"Comparando {len(paises_sel)} país(es) — {rango_anios[0]}–{rango_anios[1]}")

# --- Fila 1: serie de tiempo comparativa del indicador principal ---
st.subheader(f"Evolución de {indicador_sel}")
fig_linea = px.line(
    df_f, x="time", y=indicador_sel, color="economy",
    markers=True,
    labels={"time": "Año", "economy": "País", indicador_sel: indicador_sel},
)
fig_linea.update_layout(height=450, legend_title_text="País")
st.plotly_chart(fig_linea, width='stretch')

# --- Mapa: último año disponible del indicador principal ---
st.subheader(f"Mapa — {indicador_sel} (último año disponible)")
df_valid_mapa = df_f.dropna(subset=[indicador_sel])
if df_valid_mapa.empty:
    st.info("No hay datos de este indicador para los países/rango seleccionados.")
else:
    ultimo_anio_mapa = df_valid_mapa["time"].max()
    df_mapa = df_valid_mapa[df_valid_mapa["time"] == ultimo_anio_mapa]
    fig_mapa = px.choropleth(
        df_mapa, locations="economy", color=indicador_sel,
        title=f"{indicador_sel} — {ultimo_anio_mapa}",
        color_continuous_scale="Viridis",
    )
    fig_mapa.update_layout(height=450, margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig_mapa, width='stretch')

# --- Fila 2: comparación del último año disponible (barras) ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("Comparación último año disponible")
    df_valid = df_f.dropna(subset=[indicador_sel])
    if df_valid.empty:
        st.info("No hay datos para este indicador en el rango/países seleccionados.")
    else:
        ultimo_por_pais = (
            df_valid.sort_values("time")
            .groupby("economy")
            .tail(1)
            .sort_values(indicador_sel, ascending=False)
        )
        fig_barras = px.bar(
            ultimo_por_pais, x="economy", y=indicador_sel, color="economy",
            text_auto=".2s",
            labels={"economy": "País", indicador_sel: indicador_sel},
        )
        fig_barras.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig_barras, width='stretch')

with col2:
    st.subheader("Distribución del indicador (todo el rango)")
    fig_box = px.box(df_f, x="economy", y=indicador_sel, color="economy")
    fig_box.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig_box, width='stretch')

# --- Fila 3: radar comparativo multi-indicador (último año, normalizado) ---
st.subheader("Comparación multi-indicador (último año, normalizado 0–1)")
indicadores_radar = st.multiselect(
    "Indicadores a incluir en el radar",
    options=indicadores,
    default=indicadores[: min(6, len(indicadores))],
)

if indicadores_radar:
    ultimo_general = (
        df_f.dropna(subset=indicadores_radar, how="all")
        .sort_values("time")
        .groupby("economy")
        .tail(1)
    )
    df_norm = ultimo_general.copy()
    for ind in indicadores_radar:
        col_min, col_max = df[ind].min(), df[ind].max()
        rango = (col_max - col_min) or 1
        df_norm[ind] = (df_norm[ind] - col_min) / rango

    fig_radar = go.Figure()
    for _, fila in df_norm.iterrows():
        fig_radar.add_trace(go.Scatterpolar(
            r=[fila[ind] for ind in indicadores_radar],
            theta=indicadores_radar,
            fill="toself",
            name=fila["economy"],
        ))
    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 1]),
            domain=dict(x=[0.15, 0.85], y=[0.1, 0.9]),  # encoge el área del radar dentro de la figura
        ),
        height=420,
        margin=dict(l=40, r=40, t=40, b=40),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2),
    )
    # lo centramos y le damos menos ancho que el contenedor completo
    col_radar_a, col_radar_b, col_radar_c = st.columns([1, 3, 1])
    with col_radar_b:
        st.plotly_chart(fig_radar, width='stretch')
else:
    st.info("Elige al menos un indicador para el radar.")

# --- Fila 4: gráfico de dispersión entre dos indicadores ---
st.subheader("Dispersión entre dos indicadores")
col_x, col_y, col_color = st.columns(3)
with col_x:
    var_x = st.selectbox("Variable X", options=indicadores, index=0, key="scatter_x")
with col_y:
    idx_y_default = 1 if len(indicadores) > 1 else 0
    var_y = st.selectbox("Variable Y", options=indicadores, index=idx_y_default, key="scatter_y")
with col_color:
    modo_puntos = st.radio(
        "Puntos a mostrar",
        options=["Todos los años", "Solo último año por país"],
        index=1,
    )

df_scatter = df_f.dropna(subset=[var_x, var_y])

if modo_puntos == "Solo último año por país":
    df_scatter = (
        df_scatter.sort_values("time")
        .groupby("economy")
        .tail(1)
    )

if df_scatter.empty:
    st.info("No hay datos suficientes para graficar estas dos variables con los filtros actuales.")
else:
    try:
        import statsmodels.api as _sm  # noqa: F401
        usar_tendencia = len(df_scatter) > 2
    except ImportError:
        usar_tendencia = False

    fig_scatter = px.scatter(
        df_scatter, x=var_x, y=var_y, color="economy",
        hover_data=["time"],
        trendline="ols" if usar_tendencia else None,
        labels={var_x: var_x, var_y: var_y, "economy": "País"},
    )
    fig_scatter.update_traces(marker=dict(size=10, line=dict(width=1, color="white")))
    fig_scatter.update_layout(height=480, legend_title_text="País")
    st.plotly_chart(fig_scatter, width='stretch')

# --- Fila 5: matriz de correlación entre indicadores ---
st.subheader("Matriz de correlación entre indicadores")
indicadores_corr = st.multiselect(
    "Indicadores a incluir en la correlación",
    options=indicadores,
    default=indicadores,
    key="corr_indicadores",
)

if len(indicadores_corr) >= 2:
    corr = df_f[indicadores_corr].corr()
    fig_corr = px.imshow(
        corr, text_auto=".2f", color_continuous_scale="RdBu_r",
        zmin=-1, zmax=1,
        labels=dict(color="Correlación"),
    )
    fig_corr.update_layout(height=500, margin=dict(l=40, r=40, t=40, b=40))
    st.plotly_chart(fig_corr, width='stretch')
else:
    st.info("Elige al menos dos indicadores para calcular la correlación.")

# --- Fila 6: tabla de datos filtrados ---
with st.expander("Ver tabla de datos filtrados"):
    st.dataframe(df_f, width='stretch')
    st.download_button(
        "Descargar CSV filtrado",
        data=df_f.to_csv(index=False).encode("utf-8"),
        file_name="macro_filtrado.csv",
        mime="text/csv",
    )
