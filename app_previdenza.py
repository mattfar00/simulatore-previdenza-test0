import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Simulatore Previdenziale Pro", layout="wide")
st.title("🚀 Confronto Previdenziale: Fondo vs PAC + TFR")

# --- SIDEBAR: PARAMETRI ---
st.sidebar.header("1. Reddito e Carriera")
ral = st.sidebar.number_input("RAL Lorda Annuale Partenza (€)", value=40000, step=1000)
profilo_crescita = st.sidebar.selectbox(
    "Profilo di crescita",
    ["Moderata (3–6%/scatto)", "Media (6–10%/scatto)", "Spinta (10–20%/scatto)"],
    index=1
)
modalita = st.sidebar.radio("Modalità scenario", ["Mediana P50 (1000 simulazioni)", "Scenario casuale"])
if modalita == "Scenario casuale":
    scenario_idx = st.sidebar.slider("Variante casuale #", 1, 1000, 1) - 1
else:
    scenario_idx = None

st.sidebar.header("2. Fondo Pensione")
versamento_fondo = st.sidebar.number_input("Versamento Volontario Annuo (€)", min_value=0, value=1944, step=100)
tfr_annuo = st.sidebar.number_input("Quota TFR Annua (€)", min_value=0, value=2200, step=100)
contributo_azienda = st.sidebar.number_input("Contributo Aziendale Annuo (€)", min_value=0, value=700, step=50)
rend_fondo = st.sidebar.slider("Rendimento Annuo NETTO Fondo (%)", 1.0, 8.0, 4.0, 0.1) / 100
tassa_uscita_fondo = st.sidebar.slider("Tassazione Uscita Fondo (%)", 9, 23, 12)

st.sidebar.header("3. PAC (ETF)")
versamento_pac = st.sidebar.number_input("Versamento PAC Annuo (€)", min_value=0, value=3445, step=100)
rend_pac = st.sidebar.slider("Rendimento Lordo PAC (%)", 1.0, 12.0, 7.0, 0.1) / 100
tassa_uscita_pac = st.sidebar.slider("Tassazione Plusvalenze PAC (%)", 0, 26, 26)

st.sidebar.header("4. TFR in Azienda")
rend_tfr = st.sidebar.slider("Rendimento Annuo TFR in Azienda (%)", 0.0, 7.0, 2.5, 0.1) / 100
tassa_tfr = st.sidebar.slider("Tassazione TFR Uscita (%)", 23, 43, 27)

st.sidebar.header("5. Orizzonte Temporale")
durata = st.sidebar.slider("Anni di investimento", 1, 40, 20)


# --- GENERAZIONE 1000 SIMULAZIONI MONTE CARLO ---
@st.cache_data
def genera_scenari(profilo: str, n: int = 1000, seed: int = 42) -> list[list[float]]:
    """
    Genera n percorsi di carriera realistici.
    Ogni percorso è una lista di moltiplicatori sulla RAL iniziale (lunghezza 40).
    Logica:
      - Crescita organica annua modesta (inflazione + anzianità) negli anni 3-10
      - Salti salariali periodici (promozioni / cambio azienda) con frequenza 1-3 anni
      - Ampiezza dei salti dipende dal profilo scelto
    """
    rng = np.random.default_rng(seed)
    scenari = []

    for _ in range(n):
        molt = 1.0
        attesa = 0
        target = rng.integers(1, 4)
        percorso = [1.0]

        for anno in range(1, 40):
            attesa += 1

            # Crescita organica leggera nei primi anni di carriera
            if 3 <= anno <= 10:
                molt *= rng.uniform(1.03, 1.04)

            # Salto salariale (promozione / job change)
            if attesa >= target:
                if "Moderata" in profilo:
                    salto = rng.uniform(1.03, 1.06)
                elif "Media" in profilo:
                    salto = rng.uniform(1.06, 1.10)
                else:  # Spinta
                    salto = rng.uniform(1.10, 1.20)

                # Piccola componente stocastica attorno al salto
                rumore = rng.normal(0, 0.015)
                molt *= max(1.0, salto + rumore)
                attesa = 0
                target = rng.integers(1, 4)

            percorso.append(molt)

        scenari.append(percorso)

    return scenari


def percentile_per_anno(scenari: list, durata: int, p: float) -> list[float]:
    return [float(np.percentile([s[a] for s in scenari], p)) for a in range(durata)]


def simula_capitale(fattori: list[float], params: dict) -> pd.DataFrame:
    """
    Dato un percorso di fattori moltiplicativi sulla RAL,
    simula anno per anno i capitali di fondo, PAC e TFR.
    I versamenti crescono proporzionalmente alla RAL.
    """
    ral = params["ral"]
    vf0 = params["vf"]
    tf0 = params["tf"]
    ca0 = params["ca"]
    vp0 = params["vp"]
    rf = params["rf"]
    rp = params["rp"]
    tf2 = params["tf2"] / 100
    tp = params["tp"] / 100
    rt = params["rt"]
    tt = params["tt"] / 100
    ter_fondo = 0.002
    ter_pac = 0.002

    cap_fondo = 0.0
    cap_pac = 0.0
    cap_tfr = 0.0
    versato_pac_cum = 0.0
    rows = []

    for a, f in enumerate(fattori):
        anno = a + 1
        ral_curr = ral * f

        # Versamenti proporzionali alla crescita RAL
        vf_curr = vf0 * f
        tf_curr = tf0 * f
        ca_curr = ca0 * f
        vp_curr = vp0 * f

        # --- Fondo pensione ---
        cap_fondo += vf_curr + tf_curr + ca_curr
        cap_fondo *= (1 + rf)
        cap_fondo *= (1 - ter_fondo)

        # --- PAC ETF ---
        versato_pac_cum += vp_curr
        cap_pac += vp_curr
        cap_pac *= (1 + rp)
        cap_pac *= (1 - ter_pac)

        # --- TFR in azienda ---
        cap_tfr += tf_curr
        cap_tfr *= (1 + rt)

        # --- Valori netti a uscita (se liquidassi oggi) ---
        plusval_pac = max(0.0, cap_pac - versato_pac_cum)
        netto_fondo = cap_fondo * (1 - tf2)
        netto_pac = cap_pac - plusval_pac * tp
        netto_tfr = cap_tfr * (1 - tt)
        netto_pac_tfr = netto_pac + netto_tfr

        rows.append({
            "Anno": anno,
            "RAL (€)": ral_curr,
            "Vers. Volontario (€)": vf_curr,
            "TFR al Fondo (€)": tf_curr,
            "Contrib. Aziendale (€)": ca_curr,
            "PAC annuo (€)": vp_curr,
            "Fondo Pensione Netto (€)": netto_fondo,
            "PAC + TFR Netto (€)": netto_pac_tfr,
        })

    return pd.DataFrame(rows)


# --- CALCOLO ---
profilo_key = profilo_crescita.split(" ")[0]
scenari = genera_scenari(profilo_crescita, n=1000)

params = dict(
    ral=ral, vf=versamento_fondo, tf=tfr_annuo, ca=contributo_azienda,
    vp=versamento_pac, rf=rend_fondo, rp=rend_pac,
    tf2=tassa_uscita_fondo, tp=tassa_uscita_pac,
    rt=rend_tfr, tt=tassa_tfr,
)

# Percentili per la banda di confidenza
p25_ral = percentile_per_anno(scenari, durata, 25)
p50_ral = percentile_per_anno(scenari, durata, 50)
p75_ral = percentile_per_anno(scenari, durata, 75)

# Simula tutti gli scenari per fondo e PAC+TFR
all_fondo = []
all_pac = []
for s in scenari:
    df_s = simula_capitale(s[:durata], params)
    all_fondo.append(df_s["Fondo Pensione Netto (€)"].tolist())
    all_pac.append(df_s["PAC + TFR Netto (€)"].tolist())

p25_fondo = [float(np.percentile([r[a] for r in all_fondo], 25)) for a in range(durata)]
p50_fondo = [float(np.percentile([r[a] for r in all_fondo], 50)) for a in range(durata)]
p75_fondo = [float(np.percentile([r[a] for r in all_fondo], 75)) for a in range(durata)]

p25_pac = [float(np.percentile([r[a] for r in all_pac], 25)) for a in range(durata)]
p50_pac = [float(np.percentile([r[a] for r in all_pac], 50)) for a in range(durata)]
p75_pac = [float(np.percentile([r[a] for r in all_pac], 75)) for a in range(durata)]

anni = list(range(1, durata + 1))

# Scenario per la tabella e le metriche
if scenario_idx is not None:
    df_main = simula_capitale(scenari[scenario_idx][:durata], params)
    label_scenario = f"Scenario casuale #{scenario_idx + 1}"
else:
    # Mediana: costruiamo un percorso con i fattori mediani anno per anno
    fattori_mediani = [float(np.percentile([s[a] for s in scenari], 50)) for a in range(durata)]
    df_main = simula_capitale(fattori_mediani, params)
    label_scenario = "Mediana P50 (1000 simulazioni)"

# --- KPI ---
col1, col2, col3 = st.columns(3)
col1.metric(
    "Fondo Pensione Netto (fine periodo)",
    f"€ {df_main['Fondo Pensione Netto (€)'].iloc[-1]:,.0f}",
    help=f"P25: {p25_fondo[-1]:,.0f} € — P75: {p75_fondo[-1]:,.0f} €"
)
col2.metric(
    "PAC + TFR Netto (fine periodo)",
    f"€ {df_main['PAC + TFR Netto (€)'].iloc[-1]:,.0f}",
    help=f"P25: {p25_pac[-1]:,.0f} € — P75: {p75_pac[-1]:,.0f} €"
)
col3.metric(
    "RAL finale stimata",
    f"€ {df_main['RAL (€)'].iloc[-1]:,.0f}",
    help=f"P25: {ral * p25_ral[-1]:,.0f} € — P75: {ral * p75_ral[-1]:,.0f} €"
)

# --- GRAFICO ---
st.subheader(f"📊 Andamento Capitale Netto — {label_scenario}")
st.caption("La banda colorata mostra il range P25–P75 delle 1000 simulazioni di carriera.")

fig = go.Figure()

# Bande di confidenza
fig.add_trace(go.Scatter(
    x=anni + anni[::-1],
    y=p75_fondo + p25_fondo[::-1],
    fill="toself", fillcolor="rgba(42,120,214,0.12)",
    line=dict(color="rgba(0,0,0,0)"), name="Fondo P25–P75", showlegend=True
))
fig.add_trace(go.Scatter(
    x=anni + anni[::-1],
    y=p75_pac + p25_pac[::-1],
    fill="toself", fillcolor="rgba(27,175,122,0.12)",
    line=dict(color="rgba(0,0,0,0)"), name="PAC+TFR P25–P75", showlegend=True
))

# Linee scenario selezionato
fig.add_trace(go.Scatter(
    x=anni, y=df_main["Fondo Pensione Netto (€)"],
    name="Fondo Pensione", line=dict(color="#2a78d6", width=3)
))
fig.add_trace(go.Scatter(
    x=anni, y=df_main["PAC + TFR Netto (€)"],
    name="PAC + TFR in Azienda", line=dict(color="#1baf7a", width=3)
))

fig.update_layout(
    xaxis_title="Anno",
    yaxis_title="Capitale Netto (€)",
    yaxis_tickformat="€,.0f",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=420,
)
st.plotly_chart(fig, use_container_width=True)

# --- TABELLA ANNO PER ANNO ---
st.subheader("📋 Dettaglio Anno per Anno")
st.caption(f"Versamenti proporzionali alla crescita RAL simulata — {label_scenario}")

fmt_cols = {
    "RAL (€)": "€ {:,.0f}",
    "Vers. Volontario (€)": "€ {:,.0f}",
    "TFR al Fondo (€)": "€ {:,.0f}",
    "Contrib. Aziendale (€)": "€ {:,.0f}",
    "PAC annuo (€)": "€ {:,.0f}",
    "Fondo Pensione Netto (€)": "€ {:,.0f}",
    "PAC + TFR Netto (€)": "€ {:,.0f}",
}
st.dataframe(
    df_main.style.format(fmt_cols),
    use_container_width=True,
    height=400,
)
