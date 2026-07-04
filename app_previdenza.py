import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Simulatore Previdenziale Pro", layout="wide")
st.title("Previdenze complementari")

# --- SIDEBAR: FISCO E REDDITO ---
st.sidebar.header("1. Parametri Fiscali")
ral = st.sidebar.number_input("RAL Lorda Annuale (€)", value=40000, step=1000)
mensilita = st.sidebar.selectbox("Mensilità stipendio (per calcolo costo mensile)", [12, 13, 14], index=0)

inps_rate = 0.0919 
inps_annuo = ral * inps_rate
imponibile_irpef_lordo = ral - inps_annuo

def calcola_irpef_totale(imponibile):
    imponibile = max(0, imponibile)
    if imponibile <= 28000:
        return imponibile * 0.23
    elif imponibile <= 50000:
        return (28000 * 0.23) + ((imponibile - 28000) * 0.35)
    else:
        return (28000 * 0.23) + (22000 * 0.35) + ((imponibile - 50000) * 0.43)

# Il limite di legge esatto per la deducibilità
limite_deducibilita = 5164.57

# --- INVESTIMENTI ---
st.sidebar.header("2. Fondo Pensione")
versamento_fondo = st.sidebar.number_input("Versamento Volontario Annuo (€)", min_value=0, value=1944, step=100)
tfr_annuo = st.sidebar.number_input("Quota TFR Annua (€)", min_value=0, value=2200, step=100)
contributo_azienda = st.sidebar.number_input("Contributo Aziendale Annuo (€)", min_value=0, value=700, step=50)
rend_fondo = st.sidebar.slider("Rendimento Annuo NETTO Fondo (%)", 1.0, 8.0, 4.0, 0.1) / 100
costo_perc_fondo = st.sidebar.number_input("TER Fondo (%)", value=0.20, step=0.01) / 100
costo_fisso_fondo = st.sidebar.number_input("Costo Fisso Annuo Fondo (€)", value=22.0, step=1.0)
tassa_uscita_fondo = st.sidebar.slider("Tassazione Uscita Fondo (%)", 9, 23, 12)

st.sidebar.header("3. PAC Indipendente (ETF)")
versamento_pac = st.sidebar.number_input("Versamento PAC Annuo (€)", min_value=0, value=3445, step=100)
rend_pac = st.sidebar.slider("Rendimento Lordo PAC (%)", 1.0, 10.0, 7.0, 0.1) / 100
costo_perc_pac = st.sidebar.number_input("TER PAC (%) - Gestione annua", value=0.20, step=0.01) / 100
costo_fisso_pac = st.sidebar.number_input("Costo Fisso Annuo PAC (€)", value=0.0, step=1.0)
tassa_uscita_pac = st.sidebar.slider("Tassazione Plusvalenze PAC (%)", 0, 26, 26)

st.sidebar.header("4. TFR in Azienda")
rend_tfr = st.sidebar.slider("Rendimento annuo stimato TFR in Azienda (%)", 0.0, 7.0, 2.5, 0.1) / 100
tassa_tfr = st.sidebar.slider("Tassazione TFR (Separata all'uscita) (%)", 23, 43, 27)

st.sidebar.header("5. Orizzonte Temporale e Visive")
durata = st.sidebar.slider("Anni di investimento", 1, 40, 20)
unisci_pac_tfr = st.sidebar.checkbox("Unisci PAC e TFR in una singola linea", value=True)

# --- CALCOLO FISCALE E FLUSSI DI CASSA ---
# Il contributo azienda erode il plafond dei 5164,57€, ma NON genera rimborso IRPEF.
spazio_deducibilita_residuo = max(0, limite_deducibilita - contributo_azienda)
versamento_volontario_deducibile = min(versamento_fondo, spazio_deducibilita_residuo)

risparmio_fiscale_annuo = calcola_irpef_totale(imponibile_irpef_lordo) - calcola_irpef_totale(imponibile_irpef_lordo - versamento_volontario_deducibile)

totale_imponibile_dedotto = versamento_volontario_deducibile * durata
totale_risparmio_irpef = risparmio_fiscale_annuo * durata

# Esborso mensile reale in base alle mensilità scelte
esborso_mensile_fondo = (versamento_fondo - risparmio_fiscale_annuo) / mensilita
esborso_mensile_pac = versamento_pac / mensilita

# --- MOTORE DI CALCOLO ---
capitale_fondo = 0.0
capitale_pac = 0.0
capitale_tfr = 0.0
dati_grafico = []
imposta_bollo = 0.002 

for anno in range(1, durata + 1):
    # Simulazione Fondo
    capitale_fondo += (versamento_fondo + tfr_annuo + contributo_azienda)
    capitale_fondo += (capitale_fondo * rend_fondo) 
    capitale_fondo -= (capitale_fondo * costo_perc_fondo + costo_fisso_fondo)
    
    # Simulazione PAC
    capitale_pac += versamento_pac
    capitale_pac += (capitale_pac * rend_pac)
    capitale_pac -= (capitale_pac * (costo_perc_pac + imposta_bollo) + costo_fisso_pac)
    
    # Simulazione TFR in Azienda
    capitale_tfr += tfr_annuo
    capitale_tfr += (capitale_tfr * rend_tfr)
    
    # -------------------------------------------------------------
    # CALCOLO NETTI FINALI
    # -------------------------------------------------------------
    # Fondo Pensione: la tassa di uscita si applica SOLO sul montante versato, non sugli interessi
    montante_versato_fondo = (versamento_fondo + tfr_annuo + contributo_azienda) * anno
    tassa_fondo = montante_versato_fondo * (tassa_uscita_fondo / 100)
    inv_fondo_netto = capitale_fondo - tassa_fondo
    
    # PAC: Tassazione solo sulla plusvalenza
    totale_versato_pac = versamento_pac * anno
    plusvalenza_pac = max(0, capitale_pac - totale_versato_pac)
    inv_pac_netto = capitale_pac - (plusvalenza_pac * (tassa_uscita_pac / 100))
    
    # TFR Azienda: Tassazione su tutto l'importo all'uscita
    inv_tfr_netto = capitale_tfr * (1 - (tassa_tfr / 100))
    
    dati_grafico.append({
        "Anno": anno,
        "Fondo Pensione Netto": inv_fondo_netto,
        "PAC Netto": inv_pac_netto,
        "TFR in Azienda Netto": inv_tfr_netto,
        "Strategia PAC + TFR": inv_pac_netto + inv_tfr_netto
    })

df = pd.DataFrame(dati_grafico)

# --- VISUALIZZAZIONE ---
st.subheader(" Andamento Capitale Netto")
fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=df["Anno"], y=df["Fondo Pensione Netto"], name='Fondo Pensione (Tutto dentro)', line=dict(color='#2ca02c', width=4)))

if unisci_pac_tfr:
    fig1.add_trace(go.Scatter(x=df["Anno"], y=df["Strategia PAC + TFR"], name='Strategia Alternativa (PAC + TFR in Azienda)', line=dict(color='#1f77b4', width=4)))
else:
    fig1.add_trace(go.Scatter(x=df["Anno"], y=df["PAC Netto"], name='Solo PAC Indipendente', line=dict(color='#1f77b4', width=3)))
    fig1.add_trace(go.Scatter(x=df["Anno"], y=df["TFR in Azienda Netto"], name='Solo TFR in Azienda', line=dict(color='#ff7f0e', width=3)))

fig1.update_layout(hovermode="x unified", yaxis_tickformat="€,.0f")
st.plotly_chart(fig1, use_container_width=True, key="grafico_linee")


# --- SEZIONE COSTO MENSILE E RISULTATI ---
st.markdown("---")

st.subheader(" Analisi del Costo Mensile Effettivo")
st.write(f"Confronto di quanto esce **realmente** dalle tue tasche mese per mese, calcolato su **{mensilita} mensilità**.")

col_a, col_b = st.columns(2)
with col_a:
    st.info(f"** Fondo Pensione**\n\n"
            f"- Versamento lordo in busta paga: **€ {versamento_fondo/mensilita:,.0f}** / mese\n"
            f"- Rimborso IRPEF stimato: **€ {risparmio_fiscale_annuo/mensilita:,.0f}** / mese\n"
            f"---\n"
            f"** costo netto reale: € {esborso_mensile_fondo:,.0f} / mese**")
with col_b:
    st.info(f"** PAC Indipendente**\n\n"
            f"- Versamento richiesto: **€ {versamento_pac/mensilita:,.0f}** / mese\n"
            f"- Rimborso fiscale: **€ 0** / mese\n"
            f"---\n"
            f"** costo: € {esborso_mensile_pac:,.0f} / mese**")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader(" Risparmio Fiscale (Fondo Pensione)")
    st.write(f"Totale dedotto in {durata} anni: **€ {totale_imponibile_dedotto:,.0f}**")
    st.write(f"IRPEF non pagata (rimborsata): **€ {totale_risparmio_irpef:,.0f}**")
    st.caption("*(Questo vantaggio si applica solo al Fondo Pensione)*")

with col2:
    st.subheader("🎯 Capitale Netto a Scadenza")
    st.write(f"🟢 **Fondo Pensione:** € {df.iloc[-1]['Fondo Pensione Netto']:,.0f}")
    if unisci_pac_tfr:
        st.write(f"🔵 **PAC + TFR in Azienda:** € {df.iloc[-1]['Strategia PAC + TFR']:,.0f}")
    else:
        st.write(f"🔵 **PAC Indipendente:** € {df.iloc[-1]['PAC Netto']:,.0f}")
        st.write(f"🟠 **TFR in Azienda:** € {df.iloc[-1]['TFR in Azienda Netto']:,.0f}")
        st.write(f" **TFR in Azienda:** € {df.iloc[-1]['TFR in Azienda Netto']:,.0f}")
