import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Simulatore R.I.T.A. Pro", layout="wide")
st.title("🚀 Simulatore: Fondo Pensione vs PAC (Advanced)")

# --- SIDEBAR ---
st.sidebar.header("1. Parametri Fiscali")
aliquota_irpef = st.sidebar.selectbox("Aliquota IRPEF (%)", [23, 33, 43], index=1)
limite_deducibilita = 5300

st.sidebar.header("2. Fondo Pensione (Fon.Te)")
versamento_fondo = st.sidebar.number_input("Versamento Volontario Annuo (€)", min_value=0, value=5300, step=100)
tfr_annuo = st.sidebar.number_input("Quota TFR Annua (€)", min_value=0, value=2200, step=100)
contributo_azienda = st.sidebar.number_input("Contributo Aziendale Annuo (€)", min_value=0, value=700, step=50)
rend_fondo = st.sidebar.slider("Rendimento Annuo NETTO Fondo (%)", 1.0, 8.0, 4.0, 0.1) / 100
costo_perc_fondo = st.sidebar.number_input("TER Fondo (%)", value=0.20, step=0.01) / 100
costo_fisso_fondo = st.sidebar.number_input("Costo Fisso Annuo (€)", value=22.0, step=1.0)
tassa_uscita_fondo = st.sidebar.slider("Tassazione Uscita Fondo (%)", 9, 23, 12)

st.sidebar.header("3. PAC Indipendente (ETF)")
versamento_pac = st.sidebar.number_input("Versamento PAC Annuo (€)", min_value=0, value=3445, step=100)
rend_pac = st.sidebar.slider("Rendimento Lordo PAC (%)", 1.0, 10.0, 7.0, 0.1) / 100
costo_perc_pac = st.sidebar.number_input("TER PAC (%)", value=0.20, step=0.01) / 100
tassa_uscita_pac = st.sidebar.slider("Tassazione Plusvalenze PAC (%)", 0, 26, 26)

st.sidebar.header("4. Orizzonte Temporale")
durata = st.sidebar.slider("Anni di investimento", 1, 40, 20)

# --- CALCOLO COSTI ---
quota_dedotta = min(versamento_fondo + contributo_azienda, limite_deducibilita)
risparmio_irpef_annuo = quota_dedotta * (aliquota_irpef / 100)
costo_netto_fondo = max(0, versamento_fondo - risparmio_irpef_annuo)

# --- MOTORE DI CALCOLO ---
capitale_fondo = 0.0
capitale_pac_volontario = 0.0
capitale_tfr_investito = 0.0
risparmio_irpef_accumulato = 0.0
dati_grafico = []

for anno in range(1, durata + 1):
    # 1. FONDO (Tutto dentro)
    capitale_fondo += (versamento_fondo + tfr_annuo + contributo_azienda)
    capitale_fondo += (capitale_fondo * rend_fondo) 
    capitale_fondo -= (capitale_fondo * costo_perc_fondo + costo_fisso_fondo)
    
    # 2. PAC VOLONTARIO (Solo i tuoi soldi)
    capitale_pac_volontario += versamento_pac
    capitale_pac_volontario += (capitale_pac_volontario * rend_pac)
    capitale_pac_volontario -= (capitale_pac_volontario * costo_perc_pac)
    
    # 3. TFR INVESTITO (Grafico separato)
    capitale_tfr_investito += tfr_annuo
    capitale_tfr_investito += (capitale_tfr_investito * rend_pac)
    capitale_tfr_investito -= (capitale_tfr_investito * costo_perc_pac)
    
    risparmio_irpef_accumulato += risparmio_irpef_annuo
    
    dati_grafico.append({
        "Anno": anno,
        "Capitale Fondo": capitale_fondo,
        "Capitale PAC Volontario": capitale_pac_volontario,
        "Capitale TFR Investito": capitale_tfr_investito,
        "Beneficio Totale (Fondo + IRPEF)": capitale_fondo + risparmio_irpef_accumulato
    })

df = pd.DataFrame(dati_grafico)

# --- VISUALIZZAZIONE ---
st.subheader("📊 Analisi Strategia Volontaria")
fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=df["Anno"], y=df["Beneficio Totale (Fondo + IRPEF)"], name='Fondo (Totale)', line=dict(color='#2ca02c', width=4)))
fig1.add_trace(go.Scatter(x=df["Anno"], y=df["Capitale PAC Volontario"], name='PAC (Solo Volontario)', line=dict(color='#1f77b4', width=3)))
fig1.update_layout(title="Fondo Pensione vs PAC (Sforzo Volontario)", xaxis_title="Anni", yaxis_title="Euro (€)")
st.plotly_chart(fig1, use_container_width=True)

st.subheader("📊 Analisi TFR (Investito nel mercato)")
fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=df["Anno"], y=df["Capitale TFR Investito"], name='TFR Investito', line=dict(color='#ff7f0e', width=3)))
fig2.update_layout(title="Crescita del TFR se investito nel mercato", xaxis_title="Anni", yaxis_title="Euro (€)")
st.plotly_chart(fig2, use_container_width=True)
