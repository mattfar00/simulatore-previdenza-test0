import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Simulatore Previdenziale Pro", layout="wide")
st.title("🚀 Confronto Previdenziale: Fondo vs PAC + TFR")

# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
st.sidebar.header("1. Reddito e Carriera")
ral = st.sidebar.number_input("RAL Lorda Annuale Partenza (€)", value=40000, step=1000)
mensilita = st.sidebar.selectbox("Mensilità (per calcolo costo mensile)", [12, 13, 14], index=0)
profilo_crescita = st.sidebar.selectbox(
    "Profilo di crescita",
    ["Moderata (1–4%/scatto)", "Media (2–5%/scatto)", "Spinta (4–7%/scatto)"],
    index=1,
)
modalita = st.sidebar.radio("Modalità scenario", ["Mediana P50 (1000 simulazioni)", "Scenario casuale"])
if modalita == "Scenario casuale":
    scenario_idx = st.sidebar.slider("Variante casuale #", 1, 1000, 1) - 1
else:
    scenario_idx = None

st.sidebar.header("2. Fondo Pensione")
versamento_fondo = st.sidebar.number_input("Versamento Volontario Annuo (€)", min_value=0, value=1944, step=100)
tfr_annuo        = st.sidebar.number_input("Quota TFR Annua (€)", min_value=0, value=2200, step=100)
contributo_azienda = st.sidebar.number_input("Contributo Aziendale Annuo (€)", min_value=0, value=700, step=50)
rend_fondo       = st.sidebar.slider("Rendimento Annuo NETTO Fondo (%)", 1.0, 8.0, 4.0, 0.1) / 100
tassa_uscita_fondo = st.sidebar.slider("Tassazione Uscita Fondo (%)", 9, 23, 12)

st.sidebar.header("3. PAC (ETF)")
versamento_pac   = st.sidebar.number_input("Versamento PAC Annuo (€)", min_value=0, value=3445, step=100)
rend_pac         = st.sidebar.slider("Rendimento Lordo PAC (%)", 1.0, 12.0, 7.0, 0.1) / 100
tassa_uscita_pac = st.sidebar.slider("Tassazione Plusvalenze PAC (%)", 0, 26, 26)

st.sidebar.header("4. TFR in Azienda")
rend_tfr  = st.sidebar.slider("Rendimento Annuo TFR in Azienda (%)", 0.0, 7.0, 2.5, 0.1) / 100
tassa_tfr = st.sidebar.slider("Tassazione TFR Uscita (%)", 23, 43, 27)

st.sidebar.header("5. Orizzonte Temporale")
durata = st.sidebar.slider("Anni di investimento", 1, 40, 20)

st.sidebar.header("6. Modalità combinata")
usa_entrambi = st.sidebar.checkbox(
    "Uso sia Fondo che PAC (mostra somma Fondo + PAC senza TFR)",
    value=False,
)


# ---------------------------------------------------------------------------
# IRPEF helpers
# ---------------------------------------------------------------------------
LIMITE_DEDUCIBILITA = 5164.57

def calcola_irpef(imponibile: float) -> float:
    imponibile = max(0.0, imponibile)
    if imponibile <= 28_000:
        return imponibile * 0.23
    elif imponibile <= 50_000:
        return 28_000 * 0.23 + (imponibile - 28_000) * 0.35
    else:
        return 28_000 * 0.23 + 22_000 * 0.35 + (imponibile - 50_000) * 0.43

def risparmio_irpef_fondo(ral_lorda: float, vers_volontario: float) -> float:
    """Risparmio IRPEF grazie alla deducibilità del versamento al fondo."""
    deducibile = min(vers_volontario, LIMITE_DEDUCIBILITA)
    irpef_senza = calcola_irpef(ral_lorda)
    irpef_con   = calcola_irpef(ral_lorda - deducibile)
    return irpef_senza - irpef_con


# ---------------------------------------------------------------------------
# GENERAZIONE 1000 SIMULAZIONI MONTE CARLO
# ---------------------------------------------------------------------------
@st.cache_data
def genera_scenari(profilo: str, n: int = 1000, seed: int = 42) -> list[list[float]]:
    """
    Genera n percorsi di carriera realistici (40 anni ciascuno).

    Logica degli scatti:
    - I salti salariali sono più frequenti e corposi nei primi anni (<= 10),
      poi diventano progressivamente più rari e contenuti.
    - Fase 0–10 anni: scatti ogni 1–3 anni, ampiezza al massimo del range.
    - Fase 11–20 anni: scatti ogni 2–4 anni, ampiezza ridotta al 70% del range.
    - Fase 21+ anni: scatti ogni 3–5 anni, ampiezza ridotta al 40% del range.
      (a meno di cambio lavoro simulato: ~12% di probabilità/anno di un salto extra).
    - Nessuna crescita organica annua aggiuntiva: la RAL rimane piatta tra uno
      scatto e l'altro, come nella realtà aziendale italiana.

    Range degli scatti per profilo:
      Moderata : 1–4%
      Media    : 2–5%
      Spinta   : 4–7%
    """
    rng = np.random.default_rng(seed)

    range_profilo = {
        "Moderata": (0.01, 0.04),
        "Media":    (0.02, 0.05),
        "Spinta":   (0.04, 0.07),
    }
    profilo_key = profilo.split(" ")[0]
    r_min, r_max = range_profilo[profilo_key]

    scenari = []
    for _ in range(n):
        molt = 1.0
        percorso = [1.0]
        attesa = 0
        target = rng.integers(1, 4)

        for anno in range(1, 40):
            attesa += 1

            if anno <= 10:
                fase_molt  = 1.0
                min_target = 1
                max_target = 3
            elif anno <= 20:
                fase_molt  = 0.70
                min_target = 2
                max_target = 4
            else:
                fase_molt  = 0.40
                min_target = 3
                max_target = 5

            cambio_lavoro = (anno > 5) and (rng.random() < 0.12)

            if attesa >= target or cambio_lavoro:
                ampiezza = r_min + rng.random() * (r_max - r_min)
                ampiezza *= fase_molt
                ampiezza += rng.normal(0, 0.005)
                ampiezza = max(0.0, ampiezza)
                molt *= (1.0 + ampiezza)
                attesa = 0
                target = rng.integers(min_target, max_target + 1)

            percorso.append(molt)

        scenari.append(percorso)

    return scenari


def percentile_per_anno(matrix: list[list[float]], durata: int, p: float) -> list[float]:
    arr = np.array(matrix)
    return np.percentile(arr[:, :durata], p, axis=0).tolist()


def simula_capitale(fattori: list[float], params: dict) -> pd.DataFrame:
    ral_base = params["ral"]
    vf0  = params["vf"]
    tf0  = params["tf"]
    ca0  = params["ca"]
    vp0  = params["vp"]
    rf   = params["rf"]
    rp   = params["rp"]
    tf2  = params["tf2"] / 100
    tp   = params["tp"] / 100
    rt   = params["rt"]
    tt   = params["tt"] / 100
    ter  = 0.002

    cap_fondo = cap_pac = cap_tfr = versato_pac_cum = 0.0
    rows = []

    for a, f in enumerate(fattori):
        anno     = a + 1
        ral_curr = ral_base * f

        vf_curr = vf0 * f
        tf_curr = tf0 * f
        ca_curr = ca0 * f
        vp_curr = vp0 * f

        # Fondo pensione
        cap_fondo += vf_curr + tf_curr + ca_curr
        cap_fondo *= (1 + rf) * (1 - ter)

        # PAC ETF
        versato_pac_cum += vp_curr
        cap_pac += vp_curr
        cap_pac *= (1 + rp) * (1 - ter)

        # TFR in azienda
        cap_tfr += tf_curr
        cap_tfr *= (1 + rt)

        # Netti a uscita
        plusval_pac     = max(0.0, cap_pac - versato_pac_cum)
        netto_fondo     = cap_fondo * (1 - tf2)
        netto_pac       = cap_pac - plusval_pac * tp
        netto_tfr       = cap_tfr * (1 - tt)
        netto_pac_tfr   = netto_pac + netto_tfr
        netto_fondo_pac = netto_fondo + netto_pac

        rows.append({
            "Anno":                      anno,
            "RAL (€)":                   ral_curr,
            "Vers. Volontario (€)":      vf_curr,
            "TFR al Fondo (€)":          tf_curr,
            "Contrib. Aziendale (€)":    ca_curr,
            "PAC annuo (€)":             vp_curr,
            "Fondo Pensione Netto (€)":  netto_fondo,
            "PAC + TFR Netto (€)":       netto_pac_tfr,
            "Fondo + PAC Netto (€)":     netto_fondo_pac,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CALCOLO COSTO MENSILE NETTO
# ---------------------------------------------------------------------------
def calcola_costo_mensile(ral: float, vers_vol: float, vers_pac: float, mensilita: int) -> dict:
    risparmio = risparmio_irpef_fondo(ral, vers_vol)
    costo_annuo_fondo_netto = max(0.0, vers_vol - risparmio)
    costo_mensile_fondo     = costo_annuo_fondo_netto / mensilita
    costo_mensile_pac       = vers_pac / mensilita
    costo_mensile_tot       = costo_mensile_fondo + costo_mensile_pac

    return {
        "vers_vol":                vers_vol,
        "risparmio_irpef":         risparmio,
        "costo_annuo_fondo_netto": costo_annuo_fondo_netto,
        "costo_mensile_fondo":     costo_mensile_fondo,
        "costo_mensile_pac":       costo_mensile_pac,
        "costo_mensile_tot":       costo_mensile_tot,
        "aliquota_marginale":      (calcola_irpef(ral) - calcola_irpef(ral - 1)) * 100,
    }


# ---------------------------------------------------------------------------
# ESECUZIONE SIMULAZIONI
# ---------------------------------------------------------------------------
scenari = genera_scenari(profilo_crescita, n=1000)

params = dict(
    ral=ral, vf=versamento_fondo, tf=tfr_annuo, ca=contributo_azienda,
    vp=versamento_pac, rf=rend_fondo, rp=rend_pac,
    tf2=tassa_uscita_fondo, tp=tassa_uscita_pac,
    rt=rend_tfr, tt=tassa_tfr,
)

mat_ral   = [[s[a] for a in range(durata)] for s in scenari]
mat_fondo, mat_pac, mat_comb = [], [], []
for s in scenari:
    df_s = simula_capitale(s[:durata], params)
    mat_fondo.append(df_s["Fondo Pensione Netto (€)"].tolist())
    mat_pac.append(df_s["PAC + TFR Netto (€)"].tolist())
    mat_comb.append(df_s["Fondo + PAC Netto (€)"].tolist())

def pct(mat, p): return percentile_per_anno(mat, durata, p)

p25_ral, p50_ral, p75_ral       = pct(mat_ral, 25),   pct(mat_ral, 50),   pct(mat_ral, 75)
p25_fondo, p50_fondo, p75_fondo = pct(mat_fondo, 25), pct(mat_fondo, 50), pct(mat_fondo, 75)
p25_pac, p50_pac, p75_pac       = pct(mat_pac, 25),   pct(mat_pac, 50),   pct(mat_pac, 75)
p25_comb, p50_comb, p75_comb    = pct(mat_comb, 25),  pct(mat_comb, 50),  pct(mat_comb, 75)

anni = list(range(1, durata + 1))

if scenario_idx is not None:
    df_main        = simula_capitale(scenari[scenario_idx][:durata], params)
    label_scenario = f"Scenario casuale #{scenario_idx + 1}"
else:
    fattori_mediani = [float(np.percentile([s[a] for s in scenari], 50)) for a in range(durata)]
    df_main         = simula_capitale(fattori_mediani, params)
    label_scenario  = "Mediana P50 (1000 simulazioni)"


# ---------------------------------------------------------------------------
# SEZIONE: COSTO MENSILE NETTO
# ---------------------------------------------------------------------------
st.subheader("💳 Costo Mensile Effettivo (Anno 1)")
info = calcola_costo_mensile(ral, versamento_fondo, versamento_pac, mensilita)

c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "Costo netto fondo/mese",
    f"€ {info['costo_mensile_fondo']:,.0f}",
    help=(
        f"Versamento lordo: {info['vers_vol']:,.0f} €/anno\n"
        f"Risparmio IRPEF: -{info['risparmio_irpef']:,.0f} €/anno\n"
        f"Netto annuo: {info['costo_annuo_fondo_netto']:,.0f} €"
    ),
)
c2.metric(
    "Costo PAC/mese",
    f"€ {info['costo_mensile_pac']:,.0f}",
    help="Nessuna deducibilità — costo pieno",
)
c3.metric(
    "Totale investito/mese",
    f"€ {info['costo_mensile_tot']:,.0f}",
)
c4.metric(
    "Risparmio IRPEF annuo (fondo)",
    f"€ {info['risparmio_irpef']:,.0f}",
    help=f"Aliquota marginale stimata: {info['aliquota_marginale']:.0f}%",
)

with st.expander("ℹ️ Come si calcola il costo netto del fondo"):
    st.markdown(
        f"""
Il versamento volontario al fondo pensione è **deducibile dal reddito imponibile**
fino a **€ {LIMITE_DEDUCIBILITA:,.2f}/anno** (art. 8 D.Lgs. 252/2005).

Con una RAL di **€ {ral:,.0f}**, la tua aliquota marginale IRPEF è circa
**{info['aliquota_marginale']:.0f}%**. Versando **€ {info['vers_vol']:,.0f}/anno**,
risparmi **€ {info['risparmio_irpef']:,.0f} di IRPEF**, quindi il costo effettivo
annuo del fondo è solo **€ {info['costo_annuo_fondo_netto']:,.0f}**
({info['costo_mensile_fondo']:,.0f} €/mese su {mensilita} mensilità).
        """
    )

st.divider()


# ---------------------------------------------------------------------------
# KPI FINALI
# ---------------------------------------------------------------------------
st.subheader(f"📊 Andamento Capitale Netto — {label_scenario}")
st.caption("Banda colorata = range P25–P75 delle 1000 simulazioni di carriera.")

last = df_main.iloc[-1]
cols = st.columns(4 if usa_entrambi else 3)

cols[0].metric(
    "Fondo Pensione Netto",
    f"€ {last['Fondo Pensione Netto (€)']:,.0f}",
    help=f"P25: {p25_fondo[-1]:,.0f} € — P75: {p75_fondo[-1]:,.0f} €",
)
cols[1].metric(
    "PAC + TFR Netto",
    f"€ {last['PAC + TFR Netto (€)']:,.0f}",
    help=f"P25: {p25_pac[-1]:,.0f} € — P75: {p75_pac[-1]:,.0f} €",
)
cols[2].metric(
    "RAL Finale Stimata",
    f"€ {last['RAL (€)']:,.0f}",
    help=f"P25: {ral * p25_ral[-1]:,.0f} € — P75: {ral * p75_ral[-1]:,.0f} €",
)
if usa_entrambi:
    cols[3].metric(
        "Fondo + PAC (senza TFR)",
        f"€ {last['Fondo + PAC Netto (€)']:,.0f}",
        help=f"P25: {p25_comb[-1]:,.0f} € — P75: {p75_comb[-1]:,.0f} €",
    )


# ---------------------------------------------------------------------------
# GRAFICO
# ---------------------------------------------------------------------------
fig = go.Figure()

def banda(x, y_hi, y_lo, color, name):
    fig.add_trace(go.Scatter(
        x=x + x[::-1], y=y_hi + y_lo[::-1],
        fill="toself", fillcolor=color,
        line=dict(color="rgba(0,0,0,0)"),
        name=name, showlegend=True,
    ))

def linea(x, y, color, name, dash="solid"):
    fig.add_trace(go.Scatter(
        x=x, y=y, name=name,
        line=dict(color=color, width=3, dash=dash),
    ))

banda(anni, p75_fondo, p25_fondo, "rgba(42,120,214,0.12)", "Fondo P25–P75")
banda(anni, p75_pac,   p25_pac,   "rgba(27,175,122,0.12)", "PAC+TFR P25–P75")
if usa_entrambi:
    banda(anni, p75_comb, p25_comb, "rgba(237,161,0,0.12)", "Fondo+PAC P25–P75")

linea(anni, df_main["Fondo Pensione Netto (€)"], "#2a78d6", "Fondo Pensione")
linea(anni, df_main["PAC + TFR Netto (€)"],      "#1baf7a", "PAC + TFR in Azienda")
if usa_entrambi:
    linea(anni, df_main["Fondo + PAC Netto (€)"], "#eda100", "Fondo + PAC (senza TFR)", dash="dot")

fig.update_layout(
    xaxis_title="Anno",
    yaxis_title="Capitale Netto (€)",
    yaxis_tickformat="€,.0f",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=430,
)
st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# TABELLA ANNO PER ANNO
# ---------------------------------------------------------------------------
st.subheader("📋 Dettaglio Anno per Anno")
st.caption(f"Versamenti proporzionali alla crescita RAL — {label_scenario}")

cols_show = [
    "Anno", "RAL (€)", "Vers. Volontario (€)", "TFR al Fondo (€)",
    "Contrib. Aziendale (€)", "PAC annuo (€)",
    "Fondo Pensione Netto (€)", "PAC + TFR Netto (€)",
]
if usa_entrambi:
    cols_show.append("Fondo + PAC Netto (€)")

fmt_cols = {c: "€ {:,.0f}" for c in cols_show if c != "Anno"}

st.dataframe(
    df_main[cols_show].style.format(fmt_cols),
    use_container_width=True,
    height=400,
)
