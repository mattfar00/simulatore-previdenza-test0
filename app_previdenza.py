import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

# --- GENERAZIONE MONTE CARLO DELLE CARRIERE ---
# Usiamo un seed fisso in modo che i 50 scenari rimangano coerenti tra un ricalcolo e l'altro di Streamlit
np.random.seed(42) 
NUM_SCENARI = 50
MAX_ANNI = 40
scenari_carriera = []

for _ in range(NUM_SCENARI):
    # Ogni profilo ha un suo "DNA" di carriera univoco
    # Probabilità di avere uno scatto in un dato anno (es. dal 10% al 35% di probabilità)
    prob_scatto = np.random.uniform(0.10, 0.35) 
    # Moltiplicatore medio in caso di scatto (es. salto di RAL dal +3% al +15%)
    media_scatto = np.random.uniform(1.03, 1.15) 
    
    percorso = [1.0] # L'anno 1 parte sempre dalla RAL base (moltiplicatore 1x)
    moltiplicatore_attuale = 1.0
    
    for _ in range(1, MAX_ANNI):
        # Lancio dei dadi: c'è stata una promozione quest'anno?
        if np.random.rand() < prob_scatto:
            # Aggiunge un po' di rumore statistico all'aumento
            salto = np.random.normal(media_scatto, 0.02) 
            moltiplicatore_attuale *= max(1.0, salto) # Impediamo che lo stipendio scenda
        percorso.append(moltiplicatore_attuale)
        
    scenari_carriera.append(percorso)

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Simulatore Previdenziale Pro", layout="wide")
st.title("🚀 Confronto Previdenziale: Fondo vs PAC + TFR")

# --- SIDEBAR: FISCO E REDDITO ---
st.sidebar.header("1. Parametri Fiscali (Anno 1)")
ral = st.sidebar.number_input("RAL Lorda Annuale Partenza (€)", value=40000, step=1000)
mensilita = st.sidebar.selectbox("Mensilità stipendio (per calcolo costo mensile)", [12, 13, 14], index=0)

def calcola_irpef_totale(imponibile):
    imponibile = max(0, imponibile)
    if imponibile <= 28000:
        return imponibile * 0.23
    elif imponibile <= 50000:
        return (28000 * 0.23) + ((imponibile - 28000) * 0.35)
    else:
        return (28000 * 0.23) + (22000 * 0.35) + ((imponibile - 50000) * 0.43)

limite_deducibilita = 5164.57

# --- INVESTIMENTI ---
st.sidebar.header("2. Fondo Pensione (Base Anno 1)")
versamento_fondo = st.sidebar.number_input("Versamento Volontario Annuo (€)", min_value=0, value=1944, step=100)
tfr_annuo = st.sidebar.number_input("Quota TFR Annua (€)", min_value=0, value=2200, step=100)
contributo_azienda = st.sidebar.number_input("Contributo Aziendale Annuo (€)", min_value=0, value=700, step=50)
rend_fondo = st.sidebar.slider("Rendimento Annuo NETTO Fondo (%)", 1.0, 8.0, 4.0, 0.1) / 100
costo_perc_fondo = st.sidebar.number_input("TER Fondo (%)", value=0.20, step=0.01) / 100
costo_fisso_fondo = st.sidebar.number_input("Costo Fisso Annuo Fondo (€)", value=22.0, step=1.0)
tassa_uscita_fondo = st.sidebar.slider("Tassazione Uscita Fondo (%)", 9, 23, 12)

st.sidebar.header("3. PAC Indipendente (ETF - Base Anno 1)")
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

st.sidebar.header("6. Evoluzione Carriera (Monte Carlo)")
st.sidebar.write("Esplora 50 futuri di carriera casuali a step.")
scenario_scelto = st.sidebar.slider("Seleziona Scenario Specifico", 1, NUM_SCENARI, 15)
percorso_carriera_attivo = scenari_carriera[scenario_scelto - 1]

# --- INIZIALIZZAZIONE VARIABILI ---
capitale_fondo = 0.0
capitale_pac = 0.0
capitale_tfr = 0.0
capitale_irpef_rimborsata = 0.0
dati_grafico = []
imposta_bollo = 0.002 

totale_imponibile_dedotto = 0.0
totale_risparmio_irpef = 0.0
totale_versato_fondo_globale = 0.0
totale_versato_pac_globale = 0.0

# Calcoli esborso iniziale (Anno 1) per la sezione Costo Mensile
inps_anno1 = ral * 0.0919
imponibile_anno1 = ral - inps_anno1
spazio_deducibilita_anno1 = max(0, limite_deducibilita - contributo_azienda)
deducibile_anno1 = min(versamento_fondo, spazio_deducibilita_anno1)
risparmio_fiscale_anno1 = calcola_irpef_totale(imponibile_anno1) - calcola_irpef_totale(imponibile_anno1 - deducibile_anno1)
esborso_mensile_fondo_anno1 = (versamento_fondo - risparmio_fiscale_anno1) / mensilita
esborso_mensile_pac_anno1 = versamento_pac / mensilita

# --- MOTORE DI CALCOLO ANNO PER ANNO ---
for anno in range(1, durata + 1):
    
    # Lettura del moltiplicatore Monte Carlo per l'anno corrente
    fattore_crescita = percorso_carriera_attivo[anno - 1]
    ral_corrente = ral * fattore_crescita
    
    # Adeguamento proporzionale di tutti i versamenti
    v_fondo_curr = versamento_fondo * fattore_crescita
    tfr_curr = tfr_annuo * fattore_crescita
    c_azienda_curr = contributo_azienda * fattore_crescita
    v_pac_curr = versamento_pac * fattore_crescita
    
    # Ricalcolo tasse e rimborsi dell'anno corrente
    inps_curr = ral_corrente * 0.0919
    imponibile_curr = ral_corrente - inps_curr
    
    spazio_ded_curr = max(0, limite_deducibilita - c_azienda_curr)
    volontario_ded_curr = min(v_fondo_curr, spazio_ded_curr)
    
    risparmio_fiscale_curr = calcola_irpef_totale(imponibile_curr) - calcola_irpef_totale(imponibile_curr - volontario_ded_curr)
    
    # Accumulo totali fiscali storici
    totale_imponibile_dedotto += volontario_ded_curr
    totale_risparmio_irpef += risparmio_fiscale_curr
    totale_versato_fondo_globale += (v_fondo_curr + tfr_curr + c_azienda_curr)
    totale_versato_pac_globale += v_pac_curr
    
    # Simulazione Fondo Pensione
    capitale_fondo += (v_fondo_curr + tfr_curr + c_azienda_curr)
    capitale_fondo += (capitale_fondo * rend_fondo) 
    capitale_fondo -= (capitale_fondo * costo_perc_fondo + costo_fisso_fondo)
    
    # Simulazione Interessi IRPEF
    capitale_irpef_rimborsata += risparmio_fiscale_curr
    capitale_irpef_rimborsata += (capitale_irpef_rimborsata * rend_fondo)
    capitale_irpef_rimborsata -= (capitale_irpef_rimborsata * costo_perc_fondo)
    
    # Simulazione PAC
    capitale_pac += v_pac_curr
    capitale_pac += (capitale_pac * rend_pac)
    capitale_pac -= (capitale_pac * (costo_perc_pac + imposta_bollo) + costo_fisso_pac)
    
    # Simulazione TFR Azienda
    capitale_tfr += tfr_curr
    capitale_tfr += (capitale_tfr * rend_tfr)
    
    # --- CALCOLO NETTI FINALI ---
    tassa_fondo = totale_versato_fondo_globale * (tassa_uscita_fondo / 100)
    inv_fondo_netto = capitale_fondo - tassa_fondo
    
    plusvalenza_pac = max(0, capitale_pac - totale_versato_pac_globale)
    inv_pac_netto = capitale_pac - (plusvalenza_pac * (tassa_uscita_pac / 100))
    
    inv_tfr_netto = capitale_tfr * (1 - (tassa_tfr / 100))
    
    dati_grafico.append({
        "Anno": anno,
        "Fondo Pensione Netto": inv_fondo_netto,
        "PAC Netto": inv_pac_netto,
        "TFR in Azienda Netto": inv_tfr_netto,
        "Strategia PAC + TFR": inv_pac_netto + inv_tfr_netto,
        "RAL Corrente": ral_corrente
    })

df = pd.DataFrame(dati_grafico)

# --- VISUALIZZAZIONE ---
st.subheader(f"📊 Andamento Capitale Netto (Scenario Monte Carlo #{scenario_scelto})")
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

st.subheader("💸 Analisi del Costo Mensile Effettivo (Riferito all'Anno 1)")
st.write(f"Confronto iniziale di quanto esce **realmente** dalle tue tasche mese per mese, calcolato su **{mensilita} mensilità**.")

col_a, col_b = st.columns(2)
with col_a:
    st.info(f"**🟢 Fondo Pensione**\n\n"
            f"- Versamento lordo in busta paga: **€ {versamento_fondo/mensilita:,.0f}** / mese\n"
            f"- Rimborso IRPEF stimato: **€ {risparmio_fiscale_anno1/mensilita:,.0f}** / mese\n"
            f"---\n"
            f"**👉 Sforzo netto reale: € {esborso_mensile_fondo_anno1:,.0f} / mese**")
with col_b:
    st.info(f"**🔵 PAC Indipendente**\n\n"
            f"- Versamento richiesto: **€ {versamento_pac/mensilita:,.0f}** / mese\n"
            f"- Rimborso fiscale: **€ 0** / mese\n"
            f"---\n"
            f"**👉 Sforzo netto reale: € {esborso_mensile_pac_anno1:,.0f} / mese**")

st.markdown("---")

col1, col2 = st.columns(2)

# --- NUOVA SEZIONE: IL SUPERPOTERE DEL FONDO ---
with col1:
    st.subheader("⚖️ Il Superpotere del Fondo (Fisco + Interessi)")
    
    tassa_totale_uscita = totale_versato_fondo_globale * (tassa_uscita_fondo / 100)
    interessi_totali_fondo = capitale_fondo - totale_versato_fondo_globale
    guadagno_netto_totale = totale_risparmio_irpef + interessi_totali_fondo - tassa_totale_uscita
    
    st.write(f"- IRPEF che lo Stato ti ha rimborsato negli anni: **+ € {totale_risparmio_irpef:,.0f}**")
    st.write(f"- Interessi totali generati (su Volont. + Datore + TFR): **+ € {interessi_totali_fondo:,.0f}**")
    st.write(f"- Tassa totale all'uscita (su Volont. + Datore + TFR): **- € {tassa_totale_uscita:,.0f}**")
    st.markdown("---")
    st.success(f"**🔥 Valore Netto Aggiunto: € {guadagno_netto_totale:,.0f}**")
    st.caption(f"Nota: Tasse e rimborsi si sono adeguati ai salti di carriera del profilo scelto. A fine simulazione (Anno {durata}) la tua RAL stimata è diventata di **€ {df.iloc[-1]['RAL Corrente']:,.0f}**.")

with col2:
    st.subheader("🎯 Capitale Netto a Scadenza")
    st.write(f"🟢 **Fondo Pensione:** € {df.iloc[-1]['Fondo Pensione Netto']:,.0f}")
    if unisci_pac_tfr:
        st.write(f"🔵 **PAC + TFR in Azienda:** € {df.iloc[-1]['Strategia PAC + TFR']:,.0f}")
    else:
        st.write(f"🔵 **PAC Indipendente:** € {df.iloc[-1]['PAC Netto']:,.0f}")
        st.write(f"🟠 **TFR in Azienda:** € {df.iloc[-1]['TFR in Azienda Netto']:,.0f}")
