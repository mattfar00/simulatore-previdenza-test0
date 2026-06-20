import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Simulatore R.I.T.A. Pro", layout="wide")
st.title(" Simulatore: Fondo Pensione vs PAC)

# --- SIDEBAR: INPUT DATI ---
st.sidebar.header("1. Parametri Fiscali")
# Modifica richiesta: Aliquota 33% invece di 35%
aliquota_irpef = st.sidebar.selectbox("Aliquota IRPEF (%)", [23, 33, 43], index=1)
limite_deducibilita = 5300

st.sidebar.header("2. Fondo Pensione (Fon.Te)")
versamento_fondo = st.sidebar.number_input("Versamento Volontario Annuo (€)", min_value=0, value=5300, step=100)
tfr_annuo = st.sidebar.number_input("Quota TFR Annua (€)", min_value=0, value=2200, step=100)
contributo_azienda = st.sidebar.number_input("Contributo Aziendale Annuo (€)", min_value=0, value=700, step=50)
rend_fondo = st.sidebar.slider("Rendimento Lordo Fondo (%)", 1.0, 10.0, 5.0, 0.1) / 100
costo_perc_fondo = st.sidebar.number_input("TER Fondo (%)", value=0.20, step=0.01) / 100
costo_fisso_fondo = st.sidebar.number_input("Costo Fisso Annuo (€)", value=22.0, step=1.0)

st.sidebar.header("3. PAC Indipendente (ETF)")
versamento_pac = st.sidebar.number_input("Versamento PAC Annuo (€)", min_value=0, value=3445, step=100)
rend_pac = st.sidebar.slider("Rendimento Lordo PAC (%)", 1.0, 10.0, 7.0, 0.1) / 100
costo_perc_pac = st.sidebar.number_input("TER PAC (%)", value=0.20, step=0.01) / 100

st.sidebar.header("4. Orizzonte Temporale")
durata = st.sidebar.slider("Anni di investimento", 1, 40, 20)

# --- CALCOLO COSTI NETTI ---
# Il costo reale del fondo è quanto esce dalla tua tasca meno il risparmio fiscale
quota_dedotta = min(versamento_fondo + contributo_azienda, limite_deducibilita)
risparmio_irpef_annuo = quota_dedotta * (aliquota_irpef / 100)
costo_netto_fondo = max(0, versamento_fondo - risparmio_irpef_annuo)
costo_netto_pac = versamento_pac

st.subheader("📊 Analisi Sforzo Economico")
col1, col2 = st.columns(2)
with col1:
    st.metric("Costo Netto Reale (Fondo)", f"€ {costo_netto_fondo:,.2f}", help="Cosa ti costa effettivamente in busta paga")
with col2:
    st.metric("Costo Netto Reale (PAC)", f"€ {costo_netto_pac:,.2f}", help="Il sacrificio economico diretto")

# --- MOTORE DI CALCOLO ---
capitale_fondo = 0.0
capitale_pac = 0.0
dati_grafico = []

for anno in range(1, durata + 1):
    # LOGICA FONDO (Aggiunto contributo azienda nel montante)
    capitale_fondo += (versamento_fondo + tfr_annuo + contributo_azienda)
    guadagno_fondo = capitale_fondo * rend_fondo
    costi_fondo = (capitale_fondo * costo_perc_fondo) + costo_fisso_fondo
    utile_netto_fondo = guadagno_fondo - costi_fondo
    tassa_maturato = max(0, utile_netto_fondo * 0.20)
    capitale_fondo += (utile_netto_fondo - tassa_maturato)
    
    # LOGICA PAC
    capitale_pac += versamento_pac
    guadagno_pac = capitale_pac * rend_pac
    costi_pac = capitale_pac * costo_perc_pac
    capitale_pac += (guadagno_pac - costi_pac)
    
    dati_grafico.append({
        "Anno": anno,
        "Capitale Fondo": capitale_fondo,
        "Capitale PAC": capitale_pac
    })

df = pd.DataFrame(dati_grafico)

# --- VISUALIZZAZIONE ---
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Anno"], y=df["Capitale Fondo"], name='Capitale Fondo (incl. Azienda)', line=dict(color='#2ca02c', width=3)))
fig.add_trace(go.Scatter(x=df["Anno"], y=df["Capitale PAC"], name='Capitale PAC', line=dict(color='#1f77b4', width=3)))

fig.update_layout(title="Andamento del Capitale Accumulato", xaxis_title="Anni", yaxis_title="Euro (€)", hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)
