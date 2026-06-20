import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Simulatore R.I.T.A.", layout="wide")

st.title("🚀 Simulatore: Fondo Pensione vs PAC")
st.markdown("Analisi comparativa professionale: **Fondo Fon.Te** vs **PAC Indipendente**")

# Sidebar - Input professionali
st.sidebar.header("Input di Simulazione")
irpef = st.sidebar.selectbox("Aliquota IRPEF (%)", [23, 35, 43], index=1)
v_fondo = st.sidebar.number_input("Versamento annuo Fondo (€)", 0, 15000, 5300)
tfr_fondo = st.sidebar.number_input("TFR annuo nel Fondo (€)", 0, 5000, 2200)
rend_fondo = st.sidebar.slider("Rendimento Lordo Fondo (%)", 1.0, 8.0, 5.0) / 100
v_pac = st.sidebar.number_input("Versamento annuo PAC (€)", 0, 15000, 3500)
rend_pac = st.sidebar.slider("Rendimento Lordo PAC (%)", 1.0, 8.0, 7.0) / 100
anni = st.sidebar.slider("Durata (Anni)", 5, 40, 20)

# Calcolo risparmio IRPEF
risparmio_annuo = min(v_fondo, 5300) * (irpef / 100)
st.metric("Risparmio IRPEF Annuo", f"€ {risparmio_annuo:,.2f}")

# Logica di calcolo (senza exit tax per non distorcere le curve)
data = []
cap_fondo, cap_pac, risparmio_tot = 0, 0, 0

for i in range(1, anni + 1):
    # Fondo
    cap_fondo += (v_fondo + tfr_fondo)
    cap_fondo += (cap_fondo * (rend_fondo - 0.002)) # Tolto TER 0.2%
    cap_fondo -= 22 # Tolta quota fissa
    cap_fondo -= (cap_fondo * rend_fondo * 0.2) # Tolto 20% sul maturato
    
    # PAC
    cap_pac += v_pac
    cap_pac += (cap_pac * (rend_pac - 0.002))
    
    risparmio_tot += risparmio_annuo
    data.append([i, cap_fondo, cap_pac, cap_fondo + risparmio_tot])

df = pd.DataFrame(data, columns=["Anno", "Fondo", "PAC", "Beneficio Totale"])

# Visualizzazione
fig = go.Figure()
fig.add_trace(go.Scatter(x=df.Anno, y=df["Beneficio Totale"], name="Beneficio Totale (Fondo+IRPEF)", line=dict(color='green', width=4)))
fig.add_trace(go.Scatter(x=df.Anno, y=df.Fondo, name="Solo Fondo", line=dict(color='darkgreen', dash='dot')))
fig.add_trace(go.Scatter(x=df.Anno, y=df.PAC, name="PAC", line=dict(color='blue', width=3)))

st.plotly_chart(fig, use_container_width=True)
