import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Simulatore R.I.T.A. Pro", layout="wide")
st.title(" Simulatore: Fondo Pensione vs PAC ")

# --- SIDEBAR ---
st.sidebar.header("1. Parametri Fiscali")
aliquota_irpef = st.sidebar.selectbox("Aliquota IRPEF (%)", [23, 33, 43], index=1)
limite_deducibilita = 5300

st.sidebar.header("2. Fondo Pensione ")
versamento_fondo = st.sidebar.number_input("Versamento Volontario Annuo (€)", min_value=0, value=5300, step=100)
tfr_annuo = st.sidebar.number_input("Quota TFR Annua (€)", min_value=0, value=2200, step=100)
contributo_azienda = st.sidebar.number_input("Contributo Aziendale Annuo (€)", min_value=0, value=700, step=50)
rend_fondo = st.sidebar.slider("Rendimento Annuo NETTO Fondo (%)", 1.0, 8.0, 4.0, 0.1) / 100
costo_perc_fondo = st.sidebar.number_input("TER Fondo (%)", value=0.20, step=0.01) / 100
costo_fisso_fondo = st.sidebar.number_input("Costo Fisso Annuo (€)", value=22.0, step=1.0)
# NUOVO: Slider Tassazione Finale Fondo
tassa_uscita_fondo = st.sidebar.slider("Tassazione Uscita Fondo (%)", 9, 23, 12, help="Es: 9% per RITA, 15% standard")

st.sidebar.header("3. PAC Indipendente (ETF)")
versamento_pac = st.sidebar.number_input("Versamento PAC Annuo (€)", min_value=0, value=3445, step=100)
rend_pac = st.sidebar.slider("Rendimento Lordo PAC (%)", 1.0, 10.0, 7.0, 0.1) / 100
costo_perc_pac = st.sidebar.number_input("TER PAC (%)", value=0.20, step=0.01) / 100
# NUOVO: Slider Tassazione Plusvalenze PAC
tassa_uscita_pac = st.sidebar.slider("Tassazione Plusvalenze PAC (%)", 0, 26, 26, help="Tassa sui guadagni realizzati")

st.sidebar.header("4. Orizzonte Temporale")
durata = st.sidebar.slider("Anni di investimento", 1, 40, 20)

# --- CALCOLO COSTI NETTI ---
quota_dedotta = min(versamento_fondo + contributo_azienda, limite_deducibilita)
risparmio_irpef_annuo = quota_dedotta * (aliquota_irpef / 100)
costo_netto_fondo = max(0, versamento_fondo - risparmio_irpef_annuo)
costo_netto_pac = versamento_pac

# --- MOTORE DI CALCOLO ---
capitale_fondo = 0.0
capitale_pac = 0.0
risparmio_irpef_accumulato = 0.0
dati_grafico = []

# Variabili per calcolo plusvalenze PAC
totale_investito_pac = 0.0

for anno in range(1, durata + 1):
    # LOGICA FONDO
    capitale_fondo += (versamento_fondo + tfr_annuo + contributo_azienda)
    capitale_fondo += (capitale_fondo * rend_fondo) 
    capitale_fondo -= (capitale_fondo * costo_perc_fondo + costo_fisso_fondo)
    
    # LOGICA PAC
    totale_investito_pac += (versamento_pac + tfr_annuo)
    capitale_pac += (versamento_pac + tfr_annuo)
    capitale_pac += (capitale_pac * rend_pac)
    capitale_pac -= (capitale_pac * costo_perc_pac)
    
    # Accumulo risparmio IRPEF
    risparmio_irpef_accumulato += risparmio_irpef_annuo
    
    dati_grafico.append({
        "Anno": anno,
        "Capitale Fondo": capitale_fondo,
        "Capitale PAC": capitale_pac,
        "Beneficio Totale (Fondo + IRPEF)": capitale_fondo + risparmio_irpef_accumulato
    })

df = pd.DataFrame(dati_grafico)

# --- RISULTATI FINALI CON TASSE SCELTE DALL'UTENTE ---
final_fondo_netto = capitale_fondo * (1 - (tassa_uscita_fondo / 100))
plusvalenza_pac = max(0, capitale_pac - totale_investito_pac)
final_pac_netto = capitale_pac - (plusvalenza_pac * (tassa_uscita_pac / 100))

# --- VISUALIZZAZIONE ---
st.subheader("📊 Analisi Sforzo Economico")
col1, col2 = st.columns(2)
with col1:
    st.metric("Costo Netto Reale (Fondo)", f"€ {costo_netto_fondo:,.2f}")
with col2:
    st.metric("Costo Netto Reale (PAC)", f"€ {costo_netto_pac:,.2f}")

st.subheader("🏁 Risultato Finale (Netto Tasse)")
col_a, col_b = st.columns(2)
with col_a:
    st.info(f"**Netto Finale Fondo:** € {final_fondo_netto:,.0f}")
with col_b:
    st.info(f"**Netto Finale PAC:** € {final_pac_netto:,.0f}")

fig = go.Figure()
fig.add_trace(go.Scatter(x=df["Anno"], y=df["Beneficio Totale (Fondo + IRPEF)"], 
                         name='Beneficio Totale (Fondo+IRPEF)', line=dict(color='#2ca02c', width=4, dash='dash')))
fig.add_trace(go.Scatter(x=df["Anno"], y=df["Capitale Fondo"], 
                         name='Capitale Fondo', line=dict(color='#98df8a', width=2)))
fig.add_trace(go.Scatter(x=df["Anno"], y=df["Capitale PAC"], 
                         name='Capitale PAC', line=dict(color='#1f77b4', width=3)))

fig.update_layout(title="Andamento del Capitale nel Tempo", xaxis_title="Anni", yaxis_title="Euro (€)", hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)
