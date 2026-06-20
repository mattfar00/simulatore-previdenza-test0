
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Simulatore R.I.T.A. Pro", layout="wide")
st.title("🚀 Confronto Previdenziale: Fondo vs PAC")

# --- SIDEBAR: FISCO E REDDITO ---
st.sidebar.header("1. Parametri Fiscali e Reddito")
ral = st.sidebar.number_input("RAL Lorda Annuale (€)", value=40000, step=1000)

inps_rate = 0.0919 
inps_annuo = ral * inps_rate
imponibile_irpef = ral - inps_annuo

def calcola_irpef(imponibile):
    if imponibile <= 28000:
        tax = imponibile * 0.23
        aliquota_marginale = 23
    elif imponibile <= 50000:
        tax = (28000 * 0.23) + ((imponibile - 28000) * 0.33)
        aliquota_marginale = 33
    else:
        tax = (28000 * 0.23) + (22000 * 0.33) + ((imponibile - 50000) * 0.43)
        aliquota_marginale = 43
    return tax, aliquota_marginale

irpef_annua, aliquota_marginale = calcola_irpef(imponibile_irpef)
stipendio_netto_mensile = (ral - inps_annuo - irpef_annua) / 12

st.sidebar.write(f"**Netto Mensile:** € {stipendio_netto_mensile:,.0f}")
st.sidebar.write(f"**Aliquota Marginale:** {aliquota_marginale}%")
limite_deducibilita = 5300

# --- INVESTIMENTI ---
st.sidebar.header("2. Fondo Pensione")
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
costo_perc_pac = st.sidebar.number_input("TER PAC (%) - Gestione annua", value=0.20, step=0.01) / 100
tassa_uscita_pac = st.sidebar.slider("Tassazione Plusvalenze PAC (%)", 0, 26, 26)
rend_tfr = st.sidebar.slider("Rendimento atteso TFR (investito separatamente) (%)", 0.0, 7.0, 3.0, 0.1) / 100
tassa_tfr = st.sidebar.slider("Tassazione TFR (Separata) (%)", 23, 43, 30)

st.sidebar.header("4. Orizzonte Temporale")
durata = st.sidebar.slider("Anni di investimento", 1, 40, 20)

# --- MOTORE DI CALCOLO ---
risparmio_fiscale_annuo = min(versamento_fondo + contributo_azienda, limite_deducibilita) * (aliquota_marginale / 100)
costo_reale_fondo_annuo = versamento_fondo - risparmio_fiscale_annuo
costo_reale_pac_annuo = versamento_pac

disponibile_mensile_fondo = stipendio_netto_mensile - (costo_reale_fondo_annuo / 12)
disponibile_mensile_pac = stipendio_netto_mensile - (costo_reale_pac_annuo / 12)

capitale_fondo = 0.0
capitale_pac = 0.0
capitale_tfr = 0.0
liquidita_cumulata_fondo = 0.0
liquidita_cumulata_pac = 0.0
dati_grafico = []
imposta_bollo = 0.002 

for anno in range(1, durata + 1):
    capitale_fondo += (versamento_fondo + tfr_annuo + contributo_azienda)
    capitale_fondo += (capitale_fondo * rend_fondo) 
    capitale_fondo -= (capitale_fondo * costo_perc_fondo + costo_fisso_fondo)
    
    capitale_pac += versamento_pac
    capitale_pac += (capitale_pac * rend_pac)
    capitale_pac -= (capitale_pac * (costo_perc_pac + imposta_bollo))
    
    capitale_tfr += tfr_annuo
    capitale_tfr += (capitale_tfr * rend_tfr)
    capitale_tfr -= (capitale_tfr * (costo_perc_pac + imposta_bollo))
    
    liquidita_cumulata_fondo += (disponibile_mensile_fondo * 12)
    liquidita_cumulata_pac += (disponibile_mensile_pac * 12)
    
    # Netto Investimenti (già tassati)
    inv_fondo_netto = (capitale_fondo * (1 - (tassa_uscita_fondo / 100))) + (risparmio_fiscale_annuo * anno)
    plus_pac = max(0, capitale_pac - (versamento_pac * anno))
    inv_pac_tfr_netto = (capitale_pac - (plus_pac * (tassa_uscita_pac / 100))) + (capitale_tfr * (1 - (tassa_tfr / 100)))
    
    dati_grafico.append({
        "Anno": anno,
        "Investimento Fondo Netto": inv_fondo_netto,
        "Investimento PAC+TFR Netto": inv_pac_tfr_netto,
        "Ricchezza Totale Fondo": liquidita_cumulata_fondo + inv_fondo_netto,
        "Ricchezza Totale PAC": liquidita_cumulata_pac + inv_pac_tfr_netto,
        "Liquidità Fondo": liquidita_cumulata_fondo,
        "Liquidità PAC": liquidita_cumulata_pac,
        "Netto Mensile Fondo": disponibile_mensile_fondo,
        "Netto Mensile PAC": disponibile_mensile_pac
    })

df = pd.DataFrame(dati_grafico)

# --- 1. GRAFICO ALTO: CAPITALE INVESTITO ---
st.subheader("📊 Confronto Capitale Investito (Netto Tasse)")
fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=df["Anno"], y=df["Investimento Fondo Netto"], name='Capitale Fondo (+IRPEF)', line=dict(color='#2ca02c', width=4)))
fig1.add_trace(go.Scatter(x=df["Anno"], y=df["Investimento PAC+TFR Netto"], name='Capitale PAC + TFR', line=dict(color='#1f77b4', width=4)))
fig1.update_layout(xaxis_title="Anni", yaxis_title="Euro (€)", hovermode="x unified")
st.plotly_chart(fig1, use_container_width=True, key="grafico_investimento")

# --- 2. SEZIONE INTERMEDIA: DISPONIBILITÀ E LIQUIDITÀ ---
col1, col2 = st.columns(2)
with col1:
    st.subheader("💰 Disponibilità Mensile Residua")
    fig2 = go.Figure(data=[
        go.Bar(name='Fondo Pensione', x=['Netto Mensile'], y=[df["Netto Mensile Fondo"].iloc[-1]], marker_color='#2ca02c'),
        go.Bar(name='PAC Indipendente', x=['Netto Mensile'], y=[df["Netto Mensile PAC"].iloc[-1]], marker_color='#1f77b4')
    ])
    st.plotly_chart(fig2, use_container_width=True, key="barre_mensili")

with col2:
    st.subheader("📈 Liquidità Cumulata (In Banca)")
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(x=df["Anno"], y=df["Liquidità Fondo"], name='Cash Fondo', line=dict(color='#98df8a')))
    fig3.add_trace(go.Scatter(x=df["Anno"], y=df["Liquidità PAC"], name='Cash PAC', line=dict(color='#aec7e8')))
    st.plotly_chart(fig3, use_container_width=True, key="linee_cash")

# --- 3. GRAFICO BASSO: RICCHEZZA TOTALE ---
st.subheader("🚀 Ricchezza Totale (Capitale + Cash in Banca)")
fig4 = go.Figure()
fig4.add_trace(go.Scatter(x=df["Anno"], y=df["Ricchezza Totale Fondo"], name='Ricchezza Tot. Fondo', line=dict(color='#2ca02c', width=4, dash='dash')))
fig4.add_trace(go.Scatter(x=df["Anno"], y=df["Ricchezza Totale PAC"], name='Ricchezza Tot. PAC', line=dict(color='#1f77b4', width=4, dash='dash')))
st.plotly_chart(fig4, use_container_width=True, key="grafico_ricchezza_totale")

st.success(f"**Risultato finale dopo {durata} anni:**")
st.write(f"- Ricchezza Finale Fondo: **€ {df.iloc[-1]['Ricchezza Totale Fondo']:,.0f}**")
st.write(f"- Ricchezza Finale PAC+TFR: **€ {df.iloc[-1]['Ricchezza Totale PAC']:,.0f}**")


