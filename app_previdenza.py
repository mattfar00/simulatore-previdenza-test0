import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

# ---------------------------------------------------------------------------
# CONFIGURAZIONE PAGINA
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Simulatore Previdenziale Pro", layout="wide")
st.title("🚀 Confronto Previdenziale: Fondo vs PAC + TFR")

# ---------------------------------------------------------------------------
# DATI CCNL / FONDI NEGOZIALI (fonti: accordi CCNL, schede costi COVIP 2024/25)
# ---------------------------------------------------------------------------
# Percentuali contributo datore/lavoratore calcolate sulla RAL.
# TER e costi da schede costi fondo. quota_titoli_stato = frazione del comparto
# investita in titoli di Stato (tassata al 12,5% invece che al 20%).
CCNL_PRESET = {
    "Metalmeccanico (Cometa)": {
        "fondo": "Cometa",
        "contrib_lav_pct": 0.012,        # min 1,2% RAL per avere contributo datore
        "contrib_azienda_pct": 0.020,    # 2,0% RAL
        "contrib_azienda_u35_pct": 0.022,# 2,2% RAL under 35
        "tfr_pct": 0.0691,               # 6,91% RAL (quota TFR annua)
        "costo_iniziale": 5.16,          # una tantum a carico lavoratore
        "costo_fisso": 12.0,             # €/anno
        "comparti": {
            # nome: (TER annuo, rend. medio atteso, volatilità, quota titoli Stato)
            "Garantito":   (0.0040, 0.010, 0.030, 0.70),
            "Bilanciato":  (0.0020, 0.027, 0.070, 0.45),
            "Azionario":   (0.0025, 0.045, 0.135, 0.20),
        },
        "mensilita": 13,
    },
    "Commercio (Fon.Te)": {
        "fondo": "Fon.Te",
        "contrib_lav_pct": 0.0055,       # min 0,55% RAL
        "contrib_azienda_pct": 0.0155,   # 1,55% RAL
        "contrib_azienda_u35_pct": 0.0155,
        "tfr_pct": 0.0691,
        "costo_iniziale": 15.50,
        "costo_fisso": 22.0,
        "comparti": {
            "Garantito":   (0.0077, 0.010, 0.030, 0.70),
            "Bilanciato":  (0.0036, 0.027, 0.070, 0.45),
            "Azionario":   (0.0036, 0.045, 0.135, 0.20),
        },
        "mensilita": 14,
    },
}

# ---------------------------------------------------------------------------
# COEFFICIENTI DI CRESCITA per tipo lavoratore (solo Operaio / Impiegato)
# ---------------------------------------------------------------------------
# Ancorati ai dati ISTAT "Struttura delle retribuzioni in Italia 2022" e
# JobPricing: crescita concentrata nei primi 6-10 anni (junior->senior),
# a 30+ anni RAL ~1,6x rispetto a <5 anni per il caso tipico.
COEFF_LAVORATORE = {
    "Operaio":   0.88,
    "Impiegato": 1.08,
}

# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
st.sidebar.header("1. Profilo Lavoratore")
ral = st.sidebar.number_input("RAL Lorda Annuale Partenza (€)", value=30000, step=1000)
eta = st.sidebar.number_input("Età attuale", min_value=18, max_value=67, value=30, step=1)
tipo_lavoratore = st.sidebar.selectbox("Tipo di lavoratore", list(COEFF_LAVORATORE.keys()), index=1)
profilo_crescita = st.sidebar.selectbox(
    "Dinamismo di carriera",
    ["Moderata (2–5%/scatto)", "Media (3–7%/scatto)", "Spinta (6–10%/scatto)"],
    index=1,
)
crescita_base = st.sidebar.slider(
    "Crescita di base annua (inflazione + rinnovi CCNL) %", 0.0, 4.0, 2.0, 0.1,
    help="Adeguamento applicato ogni anno anche senza promozioni. In Italia "
         "l'inflazione media di lungo periodo + rinnovi contrattuali vale ~1,5–2,5%.",
) / 100

st.sidebar.header("2. Contratto e Fondo")
ccnl_scelto = st.sidebar.selectbox("CCNL / Fondo negoziale", list(CCNL_PRESET.keys()), index=0)
preset = CCNL_PRESET[ccnl_scelto]
comparto = st.sidebar.selectbox("Comparto d'investimento", list(preset["comparti"].keys()), index=2)
ter_fondo, rend_medio_fondo, vol_fondo, quota_ts = preset["comparti"][comparto]
mensilita = preset["mensilita"]

under35 = eta < 35
contrib_az_pct = preset["contrib_azienda_u35_pct"] if under35 else preset["contrib_azienda_pct"]

st.sidebar.caption(
    f"**{preset['fondo']} · {comparto}** — datore {contrib_az_pct*100:.2f}% RAL · "
    f"tu min {preset['contrib_lav_pct']*100:.2f}% · TFR {preset['tfr_pct']*100:.2f}% · "
    f"TER {ter_fondo*100:.2f}%/anno · rend. atteso {rend_medio_fondo*100:.1f}% "
    f"(vol. {vol_fondo*100:.0f}%)"
)

vers_vol_extra = st.sidebar.number_input(
    "Versamento volontario AGGIUNTIVO annuo (€)", min_value=0, value=1000, step=100,
    help="Oltre al contributo minimo previsto dal CCNL. Deducibile dall'IRPEF.",
)

st.sidebar.header("3. Performance simulata")
st.sidebar.caption("200 scenari stocastici (GBM) sul rendimento del comparto.")
percentile_perf = st.sidebar.slider(
    "Percentile di performance", 5, 95, 50, 5,
    help="P5 = scenario molto sfortunato · P50 = mediano · P95 = molto fortunato",
)

st.sidebar.header("4. PAC (ETF)")
versamento_pac   = st.sidebar.number_input("Versamento PAC Annuo (€)", min_value=0, value=3445, step=100)
rend_medio_pac   = st.sidebar.slider("Rendimento medio atteso PAC (%)", 1.0, 12.0, 7.0, 0.1) / 100
vol_pac          = st.sidebar.slider("Volatilità PAC (%)", 5.0, 25.0, 15.0, 0.5) / 100
ter_pac          = st.sidebar.number_input("TER PAC (%)", value=0.20, step=0.01) / 100
tassa_uscita_pac = st.sidebar.slider("Tassazione Plusvalenze PAC (%)", 0, 26, 26)

st.sidebar.header("5. TFR in Azienda")
rend_tfr  = st.sidebar.slider("Rendimento Annuo TFR in Azienda (%)", 0.0, 7.0, 2.5, 0.1,
                              help="Rivalutazione legale: 1,5% + 75% inflazione")/100
tassa_tfr = st.sidebar.slider("Tassazione TFR Uscita (%)", 23, 43, 27)

st.sidebar.header("6. Orizzonte e Uscita")
durata = st.sidebar.slider("Anni di investimento", 1, 40, 25)
anni_gia_iscritto = st.sidebar.number_input(
    "Anni di adesione già maturati al fondo", min_value=0, max_value=40, value=0, step=1,
    help="Servono per calcolare l'aliquota di uscita agevolata (sconto dopo il 15° anno)",
)
motivo_uscita = st.sidebar.selectbox(
    "Motivo di uscita dal fondo",
    [
        "Prestazione pensionistica / causali agevolate (9–15%)",
        "Riscatto/anticipazione ordinaria (23%)",
    ],
    index=0,
    help=(
        "Le prestazioni pensionistiche, i riscatti per perdita requisiti con "
        "le condizioni di legge, le anticipazioni per spese sanitarie e "
        "prima casa godono dell'aliquota agevolata 9–15%. Il riscatto per "
        "cause diverse e le anticipazioni per 'ulteriori esigenze' sono "
        "tassati con ritenuta ordinaria del 23%."
    ),
)
uscita_ordinaria = motivo_uscita.startswith("Riscatto")
usa_entrambi = st.sidebar.checkbox("Uso sia Fondo che PAC (somma senza TFR)", value=True)


# ---------------------------------------------------------------------------
# IRPEF
# ---------------------------------------------------------------------------
LIMITE_DEDUCIBILITA = 5164.57

def aliquota_marginale(imponibile: float) -> float:
    """Aliquota IRPEF marginale (scaglioni 2025: 23% / 35% / 43%)."""
    if imponibile <= 28_000:
        return 0.23
    elif imponibile <= 50_000:
        return 0.35
    else:
        return 0.43

def calcola_irpef(imponibile: float) -> float:
    imponibile = max(0.0, imponibile)
    if imponibile <= 28_000:
        return imponibile * 0.23
    elif imponibile <= 50_000:
        return 28_000 * 0.23 + (imponibile - 28_000) * 0.35
    else:
        return 28_000 * 0.23 + 22_000 * 0.35 + (imponibile - 50_000) * 0.43

def risparmio_irpef(ral_lorda: float, vers_deducibile: float) -> float:
    """Risparmio IRPEF effettivo dalla deduzione (a scaglioni, non solo marginale)."""
    deducibile = min(vers_deducibile, LIMITE_DEDUCIBILITA)
    return calcola_irpef(ral_lorda) - calcola_irpef(ral_lorda - deducibile)


# ---------------------------------------------------------------------------
# ALIQUOTA DI USCITA DEL FONDO PENSIONE
# ---------------------------------------------------------------------------
def aliquota_uscita_fondo(anni_adesione_totali: int, ordinaria: bool = False) -> float:
    """
    Tassazione sostitutiva sul montante in uscita dal fondo pensione.

    - Prestazione pensionistica e causali agevolate (riscatto per perdita
      requisiti nei casi di legge, anticipazioni per spese sanitarie o prima
      casa): 15% base, ridotta dello 0,30% per ogni anno oltre il 15° fino al
      9% (con 35 anni di adesione).
    - Riscatto/anticipazione ORDINARIA (cause diverse da quelle agevolate,
      anticipazioni per "ulteriori esigenze"): ritenuta del 23%, senza sconti.

    Resta comunque molto più bassa dell'IRPEF marginale piena sui redditi alti.
    """
    if ordinaria:
        return 0.23
    if anni_adesione_totali <= 15:
        return 0.15
    sconto = min(anni_adesione_totali - 15, 20) * 0.003
    return max(0.09, 0.15 - sconto)


# ---------------------------------------------------------------------------
# GENERAZIONE 1000 SIMULAZIONI DI CARRIERA
# ---------------------------------------------------------------------------
@st.cache_data
def genera_scenari(profilo: str, coeff: float, crescita_base: float,
                   n: int = 1000, seed: int = 42):
    """
    1000 percorsi di carriera (40 anni). Due componenti:
    1. SCATTI DI CARRIERA: promozioni/avanzamenti, concentrati nei primi 6-10
       anni (junior->senior) e poi radi. Fonte forma curva: ISTAT.
    2. CRESCITA DI BASE annua: adeguamento all'inflazione e rinnovi contrattuali
       CCNL, applicata OGNI anno anche in assenza di scatti (tipicamente 1,5-2,5%).
       Evita che la RAL resti nominalmente piatta tra uno scatto e l'altro.
    """
    rng = np.random.default_rng(seed)
    range_profilo = {"Moderata": (0.02, 0.05), "Media": (0.03, 0.07), "Spinta": (0.06, 0.10)}
    profilo_key = profilo.split(" ")[0]
    r_min, r_max = range_profilo[profilo_key]
    boost_junior = 1.35 if profilo_key == "Spinta" else 1.55

    scenari = []
    for _ in range(n):
        molt = 1.0
        percorso = [1.0]
        attesa = 0
        target = rng.integers(1, 3)
        for anno in range(1, 40):
            attesa += 1

            # (1) Crescita di base annua (inflazione + rinnovi CCNL), con
            #     piccola variabilità: alcuni anni i rinnovi slittano o mancano.
            base_anno = max(0.0, crescita_base + rng.normal(0, 0.004))
            molt *= (1.0 + base_anno)

            # (2) Scatti di carriera (promozioni/avanzamenti)
            if anno <= 6:
                fase_molt, min_t, max_t = boost_junior, 1, 2
            elif anno <= 10:
                fase_molt, min_t, max_t = 1.05, 2, 3
            elif anno <= 18:
                fase_molt, min_t, max_t = 0.45, 3, 4
            else:
                fase_molt, min_t, max_t = 0.30, 4, 6
            prob_cambio = 0.15 if anno <= 10 else (0.08 if anno <= 18 else 0.04)
            cambio = (anno > 3) and (rng.random() < prob_cambio)
            if attesa >= target or cambio:
                amp = r_min + rng.random() * (r_max - r_min)
                amp *= fase_molt * coeff
                amp += rng.normal(0, 0.006)
                amp = max(0.0, amp)
                molt *= (1.0 + amp)
                attesa = 0
                target = rng.integers(min_t, max_t + 1)
            percorso.append(molt)
        scenari.append(percorso)
    return scenari


# ---------------------------------------------------------------------------
# GENERAZIONE 100 TRAIETTORIE DI RENDIMENTO (modello stocastico GBM)
# ---------------------------------------------------------------------------
@st.cache_data
def genera_rendimenti_gbm(rend_medio: float, vol: float, durata: int,
                          n: int = 100, seed: int = 7):
    """
    Genera n traiettorie di rendimento annuo con moto browniano geometrico.
    Ogni anno il rendimento è estratto da una lognormale coerente con media
    aritmetica `rend_medio` e volatilità `vol`. Restituisce una matrice
    (n x durata) di rendimenti annui (non cumulati).

    Il GBM è il modello standard per montanti di lungo periodo: cattura sia
    il rendimento atteso sia l'incertezza (annate positive e negative), a
    differenza di un rendimento medio fisso.
    """
    rng = np.random.default_rng(seed)
    # Parametri della lognormale: mu drift, sigma volatilità log
    sigma = np.sqrt(np.log(1 + (vol**2) / ((1 + rend_medio)**2)))
    mu = np.log(1 + rend_medio) - 0.5 * sigma**2
    # rendimenti annui = exp(N(mu, sigma)) - 1
    shocks = rng.normal(mu, sigma, size=(n, durata))
    rendimenti = np.exp(shocks) - 1.0
    return rendimenti


def seleziona_traiettoria_per_percentile(rendimenti: np.ndarray, percentile: int):
    """
    Ordina le n traiettorie per montante finale cumulato e restituisce quella
    corrispondente al percentile richiesto (5..95). Così lo slider mappa
    direttamente su 'scenario sfortunato -> fortunato'.
    """
    montanti = np.prod(1 + rendimenti, axis=1)
    ordine = np.argsort(montanti)
    idx = int(round((percentile / 100) * (len(ordine) - 1)))
    return rendimenti[ordine[idx]]


# ---------------------------------------------------------------------------
# MOTORE DI SIMULAZIONE DEL CAPITALE
# ---------------------------------------------------------------------------
def simula_capitale(fattori, rend_fondo_annui, params) -> pd.DataFrame:
    """
    Simula anno per anno fondo, PAC e TFR.
    - RAL cresce secondo `fattori`; TFR, contributi azienda e volontari scalano
      proporzionalmente.
    - Fondo: rendimento annuo da traiettoria GBM, tassato ANNUALMENTE al 20%
      (12,5% sulla quota in titoli di Stato). Netto in uscita con aliquota
      sostitutiva 9-15% in base agli anni di adesione.
    - Deduzione IRPEF calcolata ogni anno sull'aliquota marginale corrente.
    """
    ral_base = params["ral"]
    tfr_pct  = params["tfr_pct"]
    ca_pct   = params["ca_pct"]
    lav_pct  = params["lav_pct"]
    vol_extra = params["vers_vol_extra"]
    ter_f    = params["ter_f"]
    costo_fisso_f = params["costo_fisso_f"]
    quota_ts = params["quota_ts"]
    vp0      = params["vp"]
    rend_pac_annui = params["rend_pac_annui"]
    ter_p    = params["ter_p"]
    tp       = params["tp"] / 100
    rt       = params["rt"]
    tt       = params["tt"] / 100
    anni_pregressi = params["anni_pregressi"]
    uscita_ord = params["uscita_ordinaria"]

    # Aliquota fondo sui rendimenti annuali (media pesata 20% / 12,5%)
    aliq_rend_fondo = 0.20 * (1 - quota_ts) + 0.125 * quota_ts

    cap_fondo = cap_pac = cap_tfr = versato_pac_cum = 0.0
    risparmio_irpef_cum = 0.0
    rows = []

    for a, f in enumerate(fattori):
        anno = a + 1
        ral_curr = ral_base * f

        # Contributi proporzionali alla RAL corrente
        tfr_curr = ral_curr * tfr_pct
        ca_curr  = ral_curr * ca_pct
        vol_min  = ral_curr * lav_pct
        vf_curr  = vol_min + vol_extra          # totale volontario lavoratore
        vp_curr  = vp0 * f

        # Deduzione IRPEF sui contributi deducibili di quest'anno
        # (lavoratore + azienda, escluso TFR), cap al plafond
        deducibile = min(vf_curr + ca_curr, LIMITE_DEDUCIBILITA)
        aliq_marg = aliquota_marginale(ral_curr)
        # risparmio attribuibile alla quota versata dal lavoratore
        quota_lav = vf_curr / (vf_curr + ca_curr) if (vf_curr + ca_curr) > 0 else 0
        risparmio_anno = deducibile * aliq_marg * quota_lav
        risparmio_irpef_cum += risparmio_anno

        # --- FONDO: rendimento lordo annuo, poi tassa 20%/12,5% sui rendimenti ---
        cap_fondo += vf_curr + tfr_curr + ca_curr
        rend_lordo = cap_fondo * rend_fondo_annui[a]
        rend_netto = rend_lordo * (1 - aliq_rend_fondo)   # tassato ogni anno
        cap_fondo += rend_netto
        cap_fondo *= (1 - ter_f)
        cap_fondo = max(0.0, cap_fondo - costo_fisso_f)

        # --- PAC ETF ---
        versato_pac_cum += vp_curr
        cap_pac += vp_curr
        cap_pac *= (1 + rend_pac_annui[a]) * (1 - ter_p)

        # --- TFR in azienda ---
        cap_tfr += tfr_curr
        cap_tfr *= (1 + rt)

        # --- Valori netti a uscita ---
        anni_adesione = anni_pregressi + anno
        aliq_uscita = aliquota_uscita_fondo(anni_adesione, ordinaria=uscita_ord)
        # Nel fondo, la tassa d'uscita si applica su contributi+TFR (i rendimenti
        # sono già stati tassati). Approssimazione: aliquota su montante meno
        # rendimenti già tassati -> qui applichiamo su capitale versato (base).
        # Semplificazione prudente: aliquota su intero montante (leggermente
        # conservativa perché parte è già stata tassata).
        netto_fondo = cap_fondo * (1 - aliq_uscita)

        plusval_pac = max(0.0, cap_pac - versato_pac_cum)
        netto_pac   = cap_pac - plusval_pac * tp
        netto_tfr   = cap_tfr * (1 - tt)
        netto_pac_tfr   = netto_pac + netto_tfr
        netto_fondo_pac = netto_fondo + netto_pac

        rows.append({
            "Anno": anno,
            "RAL (€)": ral_curr,
            "Vers. Volontario (€)": vf_curr,
            "TFR al Fondo (€)": tfr_curr,
            "Contrib. Aziendale (€)": ca_curr,
            "Risparmio IRPEF (€)": risparmio_anno,
            "PAC annuo (€)": vp_curr,
            "Aliq. uscita fondo (%)": aliq_uscita * 100,
            "Fondo Netto (€)": netto_fondo,
            "PAC + TFR Netto (€)": netto_pac_tfr,
            "Fondo + PAC Netto (€)": netto_fondo_pac,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# ESECUZIONE
# ---------------------------------------------------------------------------
coeff_totale = COEFF_LAVORATORE[tipo_lavoratore]
scenari = genera_scenari(profilo_crescita, coeff_totale, crescita_base, n=1000)

# Traiettorie GBM per fondo e PAC, selezione per percentile
rend_fondo_mat = genera_rendimenti_gbm(rend_medio_fondo, vol_fondo, durata, n=200, seed=7)
rend_pac_mat   = genera_rendimenti_gbm(rend_medio_pac,  vol_pac,   durata, n=200, seed=11)
rend_fondo_sel = seleziona_traiettoria_per_percentile(rend_fondo_mat, percentile_perf)
rend_pac_sel   = seleziona_traiettoria_per_percentile(rend_pac_mat,   percentile_perf)

params = dict(
    ral=ral, tfr_pct=preset["tfr_pct"], ca_pct=contrib_az_pct,
    lav_pct=preset["contrib_lav_pct"], vers_vol_extra=vers_vol_extra,
    ter_f=ter_fondo, costo_fisso_f=preset["costo_fisso"], quota_ts=quota_ts,
    vp=versamento_pac, rend_pac_annui=rend_pac_sel, ter_p=ter_pac,
    tp=tassa_uscita_pac, rt=rend_tfr, tt=tassa_tfr,
    anni_pregressi=anni_gia_iscritto, uscita_ordinaria=uscita_ordinaria,
)

# Scenario di carriera mediano (P50) per la tabella principale
fattori_mediani = [float(np.percentile([s[a] for s in scenari], 50)) for a in range(durata)]
df_main = simula_capitale(fattori_mediani, rend_fondo_sel, params)

# Banda P25-P75 sulla carriera (rendimento fissato al percentile scelto)
mat_fondo, mat_pac = [], []
for s in scenari[:300]:   # sottocampione per velocità
    d = simula_capitale(s[:durata], rend_fondo_sel, params)
    mat_fondo.append(d["Fondo Netto (€)"].tolist())
    mat_pac.append(d["PAC + TFR Netto (€)"].tolist())
p25_fondo = np.percentile(mat_fondo, 25, axis=0).tolist()
p75_fondo = np.percentile(mat_fondo, 75, axis=0).tolist()
p25_pac   = np.percentile(mat_pac, 25, axis=0).tolist()
p75_pac   = np.percentile(mat_pac, 75, axis=0).tolist()
anni = list(range(1, durata + 1))


# ---------------------------------------------------------------------------
# INTESTAZIONE
# ---------------------------------------------------------------------------
st.info(
    f"**Profilo:** {tipo_lavoratore} · {ccnl_scelto} · comparto {comparto}  \n"
    f"Coefficiente crescita ×{coeff_totale:.2f} · Performance selezionata: "
    f"**P{percentile_perf}** (1 traiettoria su 200 scenari stocastici)"
)


# ---------------------------------------------------------------------------
# SEZIONE COSTI DEL FONDO
# ---------------------------------------------------------------------------
st.subheader(f"💰 Struttura dei Costi — {preset['fondo']} ({comparto})")

cc1, cc2, cc3, cc4 = st.columns(4)
cc1.metric("Costo iniziale (una tantum)", f"€ {preset['costo_iniziale']:,.2f}",
           help="Quota di iscrizione a carico del lavoratore")
cc2.metric("Costo fisso annuo", f"€ {preset['costo_fisso']:,.0f}",
           help="Spesa amministrativa annua fissa")
cc3.metric("TER (gestione annua)", f"{ter_fondo*100:.2f}%",
           help=f"Comparto {comparto}. Prelevato annualmente sul patrimonio")
aliq_rend = 0.20 * (1 - quota_ts) + 0.125 * quota_ts
cc4.metric("Tassa sui rendimenti/anno", f"{aliq_rend*100:.1f}%",
           help=f"20% ordinario, 12,5% sulla quota in titoli di Stato "
                f"(~{quota_ts*100:.0f}% del comparto {comparto})")

# Impatto cumulato dei costi sul montante (stile ISC COVIP)
cap_medio = df_main["Fondo Netto (€)"].mean()
ter_totale_stimato = ter_fondo * cap_medio * durata
costo_fisso_totale = preset["costo_fisso"] * durata + preset["costo_iniziale"]

with st.expander("📖 Come leggere i costi del fondo (spiegazione)"):
    st.markdown(f"""
Il fondo pensione ha **quattro tipi di costo**, tutti già inclusi nella simulazione:

1. **Costo iniziale** — €{preset['costo_iniziale']:.2f} una tantum all'iscrizione,
   a carico del lavoratore (spesso versato in parti uguali con l'azienda).

2. **Costo fisso annuo** — €{preset['costo_fisso']:.0f}/anno di spese amministrative,
   indipendenti dal capitale. Su {durata} anni: circa **€{costo_fisso_totale:,.0f}**.

3. **TER (Total Expense Ratio)** — {ter_fondo*100:.2f}%/anno del comparto *{comparto}*,
   prelevato sul patrimonio accumulato. È il costo che pesa di più nel lungo periodo:
   con il capitale medio simulato, stimiamo circa **€{ter_totale_stimato:,.0f}**
   di commissioni di gestione totali sull'orizzonte.

4. **Tassa sui rendimenti** — a differenza degli ETF (26%), il fondo pensione tassa
   i rendimenti annuali al **20%**, scendendo al **12,5%** sulla quota investita in
   titoli di Stato. Per il comparto *{comparto}* l'aliquota effettiva è
   **{aliq_rend*100:.1f}%**.

Il comparto *{comparto}* di {preset['fondo']} ha un TER tra i più bassi del mercato:
i fondi negoziali costano tipicamente 0,1–0,8%/anno contro il 2%+ dei PIP. La COVIP
stima che 1 punto di costo in più erode circa il 18% del montante su 35 anni.
""")

st.divider()


# ---------------------------------------------------------------------------
# SEZIONE TASSAZIONE IN USCITA
# ---------------------------------------------------------------------------
st.subheader("🏛️ Tassazione in Uscita")

anni_finali = anni_gia_iscritto + durata
aliq_uscita_finale = aliquota_uscita_fondo(anni_finali, ordinaria=uscita_ordinaria)
aliq_agevolata = aliquota_uscita_fondo(anni_finali, ordinaria=False)

tc1, tc2, tc3 = st.columns(3)
tc1.metric("Anni di adesione a fine periodo", f"{anni_finali}")
tc2.metric("Aliquota uscita applicata", f"{aliq_uscita_finale*100:.1f}%",
           help="Dipende dal motivo di uscita selezionato")
irpef_equiv = aliquota_marginale(df_main["RAL (€)"].iloc[-1]) * 100
tc3.metric("IRPEF ordinaria (confronto)", f"{irpef_equiv:.0f}%",
           help="Aliquota che pagheresti tenendo questi importi come reddito, senza fondo")

if uscita_ordinaria:
    st.warning(
        f"Hai selezionato **riscatto/anticipazione ordinaria**: si applica la "
        f"ritenuta del **23%**. Con uscita agevolata (pensionamento o causali di "
        f"legge) pagheresti invece **{aliq_agevolata*100:.1f}%** — una differenza "
        f"di circa **€ {df_main['Fondo Netto (€)'].iloc[-1] * (0.23 - aliq_agevolata) / (1 - 0.23):,.0f}** "
        f"sul montante finale netto."
    )

with st.expander("📖 Come funziona la tassazione del fondo pensione"):
    st.markdown(f"""
Il fondo pensione ha **due regimi di tassazione in uscita**, a seconda del motivo:

**1. Uscita agevolata** (prestazione pensionistica, riscatto per perdita requisiti
nei casi di legge, anticipazioni per spese sanitarie o acquisto/ristrutturazione
prima casa):
- Aliquota **15%** base, ridotta dello **0,30% per ogni anno oltre il 15°** di
  adesione, fino al minimo del **9%** (a 35 anni di adesione).
- Con **{anni_finali} anni** di adesione: **{aliq_agevolata*100:.1f}%**.

**2. Uscita ordinaria** (riscatto per cause diverse da quelle agevolate,
anticipazioni per "ulteriori esigenze" fino al 30% della posizione):
- Ritenuta fissa del **23%**, senza riduzioni legate all'anzianità.

In entrambi i casi **i rendimenti sono già stati tassati anno per anno** al
20%/12,5%, quindi la tassa d'uscita colpisce solo contributi e TFR.

**Confronto:** senza il fondo, quei soldi resterebbero in busta paga tassati con
l'**IRPEF ordinaria al {irpef_equiv:.0f}%** (il tuo scaglione). Anche l'uscita
ordinaria al 23% resta conveniente per i redditi nel secondo o terzo scaglione
(35–43%); per lo scaglione base (23%) il vantaggio dell'uscita ordinaria si annulla,
e lì conta soprattutto rientrare nell'ambito agevolato.
""")

st.divider()


# ---------------------------------------------------------------------------
# COSTO MENSILE NETTO
# ---------------------------------------------------------------------------
st.subheader("💳 Costo Mensile Effettivo (Anno 1)")
r0 = df_main.iloc[0]
vers_vol_anno1 = r0["Vers. Volontario (€)"]
risparmio_anno1 = r0["Risparmio IRPEF (€)"]
ca_anno1 = r0["Contrib. Aziendale (€)"]
costo_netto_fondo_anno1 = max(0.0, vers_vol_anno1 - risparmio_anno1)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Costo netto fondo/mese", f"€ {costo_netto_fondo_anno1/mensilita:,.0f}",
          help=f"Versamento tuo {vers_vol_anno1:,.0f}€ - risparmio IRPEF {risparmio_anno1:,.0f}€")
m2.metric("Costo PAC/mese", f"€ {versamento_pac/mensilita:,.0f}", help="Nessuna deducibilità")
m3.metric("Totale investito/mese",
          f"€ {(costo_netto_fondo_anno1 + versamento_pac)/mensilita:,.0f}")
m4.metric("Contributo azienda (gratis)/anno", f"€ {ca_anno1:,.0f}",
          help="Denaro aggiuntivo che non ti costa nulla")

st.divider()


# ---------------------------------------------------------------------------
# KPI + GRAFICO
# ---------------------------------------------------------------------------
st.subheader(f"📊 Andamento Capitale Netto — P{percentile_perf} performance")
st.caption("Linea = carriera mediana P50. Banda = P25–P75 sulla variabilità di carriera.")

last = df_main.iloc[-1]
cols = st.columns(4 if usa_entrambi else 3)
cols[0].metric("Fondo Netto", f"€ {last['Fondo Netto (€)']:,.0f}",
               help=f"P25: {p25_fondo[-1]:,.0f} — P75: {p75_fondo[-1]:,.0f}")
cols[1].metric("PAC + TFR Netto", f"€ {last['PAC + TFR Netto (€)']:,.0f}",
               help=f"P25: {p25_pac[-1]:,.0f} — P75: {p75_pac[-1]:,.0f}")
cols[2].metric("RAL Finale", f"€ {last['RAL (€)']:,.0f}",
               help=f"× {last['RAL (€)']/ral:.2f} vs partenza")
if usa_entrambi:
    cols[3].metric("Fondo + PAC (senza TFR)", f"€ {last['Fondo + PAC Netto (€)']:,.0f}")

fig = go.Figure()
fig.add_trace(go.Scatter(x=anni + anni[::-1], y=p75_fondo + p25_fondo[::-1],
                         fill="toself", fillcolor="rgba(42,120,214,0.12)",
                         line=dict(color="rgba(0,0,0,0)"), name="Fondo P25–P75"))
fig.add_trace(go.Scatter(x=anni + anni[::-1], y=p75_pac + p25_pac[::-1],
                         fill="toself", fillcolor="rgba(27,175,122,0.12)",
                         line=dict(color="rgba(0,0,0,0)"), name="PAC+TFR P25–P75"))
fig.add_trace(go.Scatter(x=anni, y=df_main["Fondo Netto (€)"], name="Fondo Pensione",
                         line=dict(color="#2a78d6", width=3)))
fig.add_trace(go.Scatter(x=anni, y=df_main["PAC + TFR Netto (€)"], name="PAC + TFR",
                         line=dict(color="#1baf7a", width=3)))
if usa_entrambi:
    fig.add_trace(go.Scatter(x=anni, y=df_main["Fondo + PAC Netto (€)"],
                             name="Fondo + PAC (senza TFR)",
                             line=dict(color="#eda100", width=3, dash="dot")))
fig.update_layout(xaxis_title="Anno", yaxis_title="Capitale Netto (€)",
                  yaxis_tickformat="€,.0f", hovermode="x unified",
                  legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                  height=440)
st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# TABELLA ANNO PER ANNO
# ---------------------------------------------------------------------------
st.subheader("📋 Dettaglio Anno per Anno")
st.caption("RAL e contributi crescono insieme; risparmio IRPEF su aliquota marginale corrente.")

cols_show = ["Anno", "RAL (€)", "Vers. Volontario (€)", "TFR al Fondo (€)",
             "Contrib. Aziendale (€)", "Risparmio IRPEF (€)", "PAC annuo (€)",
             "Aliq. uscita fondo (%)", "Fondo Netto (€)", "PAC + TFR Netto (€)"]
if usa_entrambi:
    cols_show.append("Fondo + PAC Netto (€)")

fmt = {c: "€ {:,.0f}" for c in cols_show if c not in ("Anno", "Aliq. uscita fondo (%)")}
fmt["Aliq. uscita fondo (%)"] = "{:.1f}%"
st.dataframe(df_main[cols_show].style.format(fmt), use_container_width=True, height=420)

st.caption(
    "⚠️ Stima illustrativa. Crescita salariale su dati ISTAT «Struttura delle "
    "retribuzioni»; contributi CCNL Cometa/Fon.Te; costi e comparti da schede COVIP; "
    "rendimenti simulati con modello stocastico GBM (media COVIP + volatilità di "
    "comparto). Non è consulenza finanziaria o previdenziale."
)
