import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Simulatore R.I.T.A. Pro", layout="wide")
st.title(" Simulatore: Fondo Pensione vs PAC")

# --- SIDEBAR ---
st.sidebar.header("1. Parametri Fiscali")
aliquota_irpef = st.sidebar.selectbox("Aliquota IRPEF (%)", [23, 33, 43], index=1)
limite_deducibilita = 5300

st.sidebar.header("2. Fondo Pensione")
versamento_fondo = st.sidebar.number_input("Versamento Volontario Annuo (€)", min_value=0, value=5300, step=100)
tfr_annuo = st.sidebar.number_input("Quota TFR Annua (€)", min_value=0, value=2200, step=100)
contributo_azienda = st.sidebar.number_input("Contributo Aziendale Annuo (€)", min_value=0, value=700, step=50)
rend_fondo = st.sidebar.slider("Rendimento Annuo NETTO Fondo (%)", 1.0, 8.0, 4.0, 0.1) / 100
costo_perc_fondo = st.sidebar.number_input("TER Fondo (%)", value=0.20, step=0.01) / 100
costo_fisso_fondo = st.sidebar.number_input("Costo Fisso Annuo (€)", value=22.0, step=1.0)
tassa_uscita_fondo = st.sidebar.slider("Tassazione Uscita Fondo (%)", 9, 23, 12, help="Es: 9% per RITA, 15% standard")

st.sidebar.header("3. PAC Indipendente (ETF)")
versamento_pac = st.sidebar.number_input("Versamento PAC Annuo (€)", min_value=0, value=3445, step=100)
rend_pac = st.sidebar.slider("Rendimento Lordo PAC (%)", 1.0, 10.0, 7.0, 0.1) / 100
costo_perc_pac = st.sidebar.number_input("TER PAC (%)", value=0.20, step=0.01) / 100
tassa_uscita_pac = st.sidebar.slider("Tassazione Plusvalenze PAC (%)", 0, 26, 26, help="Tassa sui guadagni realizzati")

# Rendimento TFR separato
rend_tfr = st.sidebar.slider("Rendimento atteso TFR (se investito separatamente) (%)", 0.0, 7.0, 3.0, 0.1) / 100

st.sidebar.header("4. Orizzonte Temporale")
durata = st.sidebar.slider("Anni di investimento", 1, 40, 20)

# --- CALCOLO COSTI ---
quota_dedotta = min(versamento_fondo + contributo_azienda, limite_deducibilita)
risparmio_irpef_annuo = quota_dedotta * (aliquota_irpef / 100)
costo_netto_fondo = max(0, versamento_fondo - risparmio_irpef_annuo)

# --- ANALISI COSTI ATTIVI ---
st.subheader("💡 Analisi Efficienza (Sacrificio vs Capitale Investito)")
# Costo = Sacrificio reale dal netto mensile
costo_sacrificio_fondo = costo_netto_fondo
costo_sacrificio_pac = versamento_pac

# Capitale che lavora = Soldi che entrano nell'investimento
capitale_annuo_fondo = versamento_fondo + tfr_annuo + contributo_azienda
capitale_annuo_pac = versamento_pac + tfr_annuo

df_costi = pd.DataFrame({
    "Metrica": ["Sacrificio dal Netto (Costo)", "Capitale Investito Annuo (TFR+Azienda inclusi)", "Vantaggio Fiscale Annuo"],
    "Fondo Pensione": [costo_sacrificio_fondo, capitale_annuo_fondo, risparmio_irpef_annuo],
    "PAC + TFR": [costo_sacrificio_pac, capitale_annuo_pac, 0]
})
st.table(df_costi.style.format({ "Fondo Pensione": "{:,.2f}", "PAC + TFR": "{:,.2f}"}))

# --- MOTORE DI CALCOLO ---
capitale_fondo = 0.0
capitale_pac_volontario = 0.0
totale_investito_pac = 0.0
capitale_tfr_investito = 0.0
risparmio_irpef_accumulato = 0.0
dati_grafico = []

for anno in range(1, durata + 1):
    capitale_fondo += (versamento_fondo + tfr_annuo + contributo_azienda)
    capitale_fondo += (capitale_fondo * rend_fondo) 
    capitale_fondo -= (capitale_fondo * costo_perc_fondo + costo_fisso_fondo)
    
    totale_investito_pac += versamento_pac
    capitale_pac_volontario += versamento_pac
    capitale_pac_volontario += (capitale_pac_volontario * rend_pac)
    capitale_pac_volontario -= (capitale_pac_volontario * costo_perc_pac)
    
    capitale_tfr_investito += tfr_annuo
    capitale_tfr_investito += (capitale_tfr_investito * rend_tfr)
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

# --- RISULTATI FINALI E GRAFICI ---
final_fondo_netto = capitale_fondo * (1 - (tassa_uscita_fondo / 100))
plusvalenza_pac = max(0, capitale_pac_volontario - totale_investito_pac)
final_pac_netto = capitale_pac_volontario - (plusvalenza_pac * (tassa_uscita_pac / 100))

st.subheader("🏁 Risultato Finale (Netto Tasse)")
col_a, col_b = st.columns(2)
with col_a:
    st.info(f"**Netto Finale Fondo (Volontario + TFR + Az.):** € {final_fondo_netto:,.0f}")
with col_b:
    st.info(f"**Netto Finale PAC (Solo Volontario):** € {final_pac_netto:,.0f}")

st.subheader("📊 Analisi Strategia Volontaria")
fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=df["Anno"], y=df["Beneficio Totale (Fondo + IRPEF)"], name='Beneficio Totale (Fondo + IRPEF)', line=dict(color='#2ca02c', width=4, dash='dash')))
fig1.add_trace(go.Scatter(x=df["Anno"], y=df["Capitale Fondo"], name='Capitale Fondo (Nominale)', line=dict(color='#98df8a', width=2)))
fig1.add_trace(go.Scatter(x=df["Anno"], y=df["Capitale PAC Volontario"], name='PAC (Solo Volontario)', line=dict(color='#1f77b4', width=3)))
fig1.update_layout(title="Fondo Pensione vs PAC (Sforzo Volontario)", xaxis_title="Anni", yaxis_title="Euro (€)")
st.plotly_chart(fig1, use_container_width=True, key="grafico_strategia_volontaria")

st.subheader("📊 Analisi TFR (Investito separatamente)")
fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=df["Anno"], y=df["Capitale TFR Investito"], name='TFR Investito', line=dict(color='#ff7f0e', width=3)))
fig2.update_layout(title=f"Crescita del TFR (Rendimento {rend_tfr*100:.1f}%)", xaxis_title="Anni", yaxis_title="Euro (€)")
st.plotly_chart(fig2, use_container_width=True, key="grafico_tfr")
