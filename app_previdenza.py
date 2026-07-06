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
# Percentuali contributo datore/lavoratore calcolate sui minimi tabellari.
# TER e costi da schede costi fondo. quota_titoli_stato = frazione del comparto
# investita in titoli di Stato (tassata al 12,5% invece che al 20%).
# livelli: {nome: minimo_tabellare_mensile}. mensilita moltiplicano per la RAL.
# scatto_valore: importo mensile medio di un singolo scatto di anzianità.
# scatto_ogni_anni / scatti_max: cadenza e numero massimo di scatti.
CCNL_PRESET = {
    "Metalmeccanico (Cometa)": {
        "fondo": "Cometa",
        "contrib_lav_pct": 0.012,        # min 1,2% per avere contributo datore
        "contrib_azienda_pct": 0.020,    # 2,0% dei minimi
        "contrib_azienda_u35_pct": 0.022,# 2,2% under 35
        "tfr_pct": 0.0691,               # 6,91% RAL (quota TFR annua)
        "costo_iniziale": 5.16,
        "costo_fisso": 12.0,
        "mensilita": 13,
        # Minimi tabellari mensili dal 1° giugno 2026 (Federmeccanica-Assistal,
        # verbale 16 giugno 2026). 13 mensilità. Valori ufficiali completi.
        "livelli": {
            "D1": 1784.94, "D2": 1979.37, "C1": 2022.12, "C2": 2064.88,
            "C3": 2211.43, "B1": 2370.33, "B2": 2542.98, "B3": 2838.99,
            "A1": 2907.01,
        },
        "scatto_valore": 30.0,   # €/mese medio per scatto
        "scatto_ogni_anni": 2,   # biennale
        "scatti_max": 5,
        "comparti": {
            # nome: (TER annuo, rend. medio atteso, volatilità, quota titoli Stato)
            "Garantito":   (0.0040, 0.010, 0.030, 0.70),
            "Bilanciato":  (0.0020, 0.027, 0.070, 0.45),
            "Azionario":   (0.0025, 0.045, 0.135, 0.20),
        },
    },
    "Commercio Confcommercio (Fon.Te)": {
        "fondo": "Fon.Te",
        "contrib_lav_pct": 0.0055,       # min 0,55%
        "contrib_azienda_pct": 0.0155,   # 1,55%
        "contrib_azienda_u35_pct": 0.0155,
        "tfr_pct": 0.0691,
        "costo_iniziale": 15.50,
        "costo_fisso": 22.0,
        "mensilita": 14,
        # Minimi tabellari mensili (paga base + contingenza) dal 1° novembre 2025
        # Fonte: CCNL Terziario Confcommercio (rinnovo 22 marzo 2024).
        # Copre la grande distribuzione / terziario, ~3 mln lavoratori.
        "livelli": {
            "Quadro": 2183.09, "I": 1966.54, "II": 1701.04, "III": 1453.94,
            "IV": 1257.46, "V": 1136.07, "VI": 1019.94, "VII": 873.22,
        },
        # Scatti triennali, max 5. Importo per livello (€/mese)
        "scatti_valore_livello": {
            "Quadro": 30.0, "I": 27.0, "II": 25.0, "III": 22.0,
            "IV": 20.0, "V": 18.0, "VI": 16.0, "VII": 15.0,
        },
        "scatto_valore": 20.0,
        "scatto_ogni_anni": 3,
        "scatti_max": 5,
        "comparti": {
            "Garantito":   (0.0077, 0.010, 0.030, 0.70),
            "Bilanciato":  (0.0036, 0.027, 0.070, 0.45),
            "Azionario":   (0.0036, 0.045, 0.135, 0.20),
        },
    },
    "Commercio Conflavoro PMI (Fon.Te)": {
        "fondo": "Fon.Te",
        "contrib_lav_pct": 0.0055,       # min 0,55%
        "contrib_azienda_pct": 0.0155,   # 1,55%
        "contrib_azienda_u35_pct": 0.0155,
        "tfr_pct": 0.0691,
        "costo_iniziale": 15.50,
        "costo_fisso": 22.0,
        "mensilita": 14,
        # Minimi tabellari mensili (retribuzione base) in vigore dal 1° giugno 2026
        # Fonte: CCNL Commercio Terziario Conflavoro PMI / Confsal / Fesica.
        # Orientato alle piccole e medie imprese. (*) Quadri: incl. indennità
        # di funzione 260,77 €.
        "livelli": {
            "Quadro": 2986.95, "I": 2507.20, "II": 2236.65, "III": 1985.15,
            "IV": 1785.00, "V": 1662.00, "VI": 1543.05, "VII": 1399.35,
        },
        # Scatti triennali, max 10. Importo per livello (€/mese)
        "scatti_valore_livello": {
            "Quadro": 26.0, "I": 25.0, "II": 23.0, "III": 22.0,
            "IV": 21.5, "V": 21.0, "VI": 20.5, "VII": 20.0,
        },
        "scatto_valore": 22.0,
        "scatto_ogni_anni": 3,
        "scatti_max": 10,
        "comparti": {
            "Garantito":   (0.0077, 0.010, 0.030, 0.70),
            "Bilanciato":  (0.0036, 0.027, 0.070, 0.45),
            "Azionario":   (0.0036, 0.045, 0.135, 0.20),
        },
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
# CATALOGO ETF PREDEFINITI (legenda) — ticker Yahoo Finance
# ---------------------------------------------------------------------------
# Catalogo indicativo di ETF UCITS comunemente usati nei PAC, organizzato per
# categoria. Nome leggibile -> ticker Yahoo Finance. Serve solo da comodo
# elenco di partenza: l'utente può comunque aggiungere qualsiasi altro ticker
# a mano nel campo "Aggiungi ticker manuale".
CATALOGO_ETF = {
    "Azionario Globale": {
        "iShares Core MSCI World (SWDA.MI)": "SWDA.MI",
        "Vanguard FTSE All-World (VWCE.DE)": "VWCE.DE",
        "Xtrackers MSCI World (XDWD.MI)": "XDWD.MI",
        "iShares MSCI ACWI (SSAC.MI)": "SSAC.MI",
    },
    "Azionario USA": {
        "iShares Core S&P 500 (CSSPX.MI)": "CSSPX.MI",
        "Xtrackers S&P 500 (XSPX.MI)": "XSPX.MI",
        "Invesco Nasdaq-100 (EQQQ.MI)": "EQQQ.MI",
    },
    "Azionario Europa": {
        "iShares Core MSCI EMU (EMU.MI)": "EMU.MI",
        "Xtrackers Euro Stoxx 50 (XESC.MI)": "XESC.MI",
        "iShares STOXX Europe 600 (EXSA.MI)": "EXSA.MI",
    },
    "Azionario Mercati Emergenti": {
        "iShares Core MSCI EM IMI (EIMI.MI)": "EIMI.MI",
        "Xtrackers MSCI Emerging Markets (XMME.MI)": "XMME.MI",
    },
    "Obbligazionario": {
        "iShares Core Global Aggregate Bond (AGGH.MI)": "AGGH.MI",
        "iShares Euro Government Bond 3-5y (IBGX.MI)": "IBGX.MI",
        "iShares Euro Corporate Bond (IEBC.MI)": "IEBC.MI",
        "Xtrackers Global Government Bond (XG7S.MI)": "XG7S.MI",
    },
    "Oro e Materie Prime": {
        "iShares Physical Gold (SGLN.MI)": "SGLN.MI",
        "Invesco Physical Gold (SGLD.MI)": "SGLD.MI",
        "WisdomTree Broad Commodities (WCOA.MI)": "WCOA.MI",
    },
    "Immobiliare (REIT)": {
        "iShares Developed Markets Property Yield (IWDP.MI)": "IWDP.MI",
        "Xtrackers FTSE EPRA/NAREIT Global (XREA.MI)": "XREA.MI",
    },
}
# Mappa inversa ticker -> nome leggibile, utile per mostrare la legenda finale
TICKER_TO_NOME = {t: nome for cat in CATALOGO_ETF.values() for nome, t in cat.items()}

# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
st.sidebar.header("1. Contratto e Inquadramento")
ccnl_scelto = st.sidebar.selectbox("CCNL / Fondo negoziale", list(CCNL_PRESET.keys()), index=0)
preset = CCNL_PRESET[ccnl_scelto]
mensilita = preset["mensilita"]

livello = st.sidebar.selectbox("Livello di inquadramento", list(preset["livelli"].keys()))
minimo_mensile = preset["livelli"][livello]
minimo_annuo = minimo_mensile * mensilita

# Importo scatto: per-livello se disponibile, altrimenti valore medio del preset
scatto_valore_livello = preset.get("scatti_valore_livello", {}).get(
    livello, preset["scatto_valore"]
)

st.sidebar.caption(
    f"Minimo tabellare **{livello}**: {minimo_mensile:,.0f} €/mese × {mensilita} "
    f"mensilità = **{minimo_annuo:,.0f} €/anno**"
)

st.sidebar.markdown("**Composizione della RAL**")
anni_anzianita_pregressi = st.sidebar.number_input(
    "Scatti di anzianità già maturati", min_value=0, max_value=preset["scatti_max"],
    value=0, step=1,
    help=f"Max {preset['scatti_max']} scatti, uno ogni {preset['scatto_ogni_anni']} anni. "
         f"Livello {livello}: {scatto_valore_livello:.1f} €/mese ciascuno",
)
superminimo_mensile = st.sidebar.number_input(
    "Superminimo (€/mese)", min_value=0, value=0, step=50,
    help="Voce individuale non prevista dal contratto. NON entra nella base "
         "di calcolo del contributo aziendale al fondo.",
)
premio_produzione_annuo = st.sidebar.number_input(
    "Premio di produzione (€/anno)", min_value=0, value=0, step=200,
    help="Premio di risultato variabile. NON entra nella base del contributo "
         "aziendale al fondo.",
)

st.sidebar.markdown("**Override manuale (opzionale)**")
ral_manuale = st.sidebar.number_input(
    "RAL effettiva a mano (€/anno, 0 = auto)", min_value=0, value=0, step=1000,
    help="Se la conosci, inserisci la tua RAL reale. Sostituisce quella calcolata "
         "e viene usata per TFR e IRPEF. Il contributo AZIENDA resta comunque "
         "calcolato sui minimi tabellari + scatti (come da contratto).",
)
capitale_iniziale_fondo = st.sidebar.number_input(
    "Capitale già presente nel fondo (€)", min_value=0, value=0, step=1000,
    help="Montante già accumulato se sei iscritto da tempo. Cresce con i "
         "rendimenti e viene tassato all'uscita in base agli anni di adesione.",
)
capitale_iniziale_pac = st.sidebar.number_input(
    "Capitale già presente nel PAC (€)", min_value=0, value=0, step=1000,
    help="Montante ETF già accumulato, se il PAC è già avviato da tempo. "
         "Cresce con i rendimenti simulati; viene trattato come capitale già "
         "versato ai fini del calcolo della plusvalenza tassata in uscita.",
)

st.sidebar.header("2. Profilo Lavoratore")
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

st.sidebar.markdown("**Passaggi di livello (promozioni pianificate)**")
usa_passaggi_livello = st.sidebar.checkbox(
    "Pianifica cambi di livello/mansione durante la carriera", value=False,
    help="Attiva per indicare TU in quali anni futuri passerai a un livello di "
         "inquadramento superiore (es. da C1 a C2 all'anno 5). Il nuovo minimo "
         "tabellare del livello sostituisce la base di partenza da quell'anno "
         "in poi; sopra continua comunque ad applicarsi la crescita simulata "
         "(scatti stocastici + inflazione).",
)
livelli_ccnl_lista = list(preset["livelli"].keys())
passaggi_livello = []  # lista di (anno_da, livello)
if usa_passaggi_livello:
    n_passaggi = st.sidebar.number_input(
        "Numero di passaggi di livello pianificati", min_value=1, max_value=10,
        value=1, step=1, key="n_passaggi_livello",
    )
    for i in range(int(n_passaggi)):
        pc1, pc2 = st.sidebar.columns([1, 2])
        anno_da = pc1.number_input(
            f"Anno #{i+1}", min_value=1, max_value=40, value=min(5 * (i + 1), 40),
            step=1, key=f"anno_passaggio_{i}",
        )
        livello_nuovo = pc2.selectbox(
            f"Nuovo livello #{i+1}", livelli_ccnl_lista,
            index=min(i + 1, len(livelli_ccnl_lista) - 1),
            key=f"livello_passaggio_{i}",
        )
        passaggi_livello.append((int(anno_da), livello_nuovo))
    # Ordina per anno crescente, utile per applicarli in sequenza nel motore
    passaggi_livello.sort(key=lambda x: x[0])
    st.sidebar.caption(
        " → ".join([f"Anno {a}: {liv}" for a, liv in passaggi_livello])
        if passaggi_livello else ""
    )

st.sidebar.header("3. Fondo")
comparto = st.sidebar.selectbox("Comparto d'investimento", list(preset["comparti"].keys()), index=2)
ter_fondo, rend_medio_fondo, vol_fondo, quota_ts = preset["comparti"][comparto]

under35 = eta < 35
contrib_az_pct = preset["contrib_azienda_u35_pct"] if under35 else preset["contrib_azienda_pct"]

st.sidebar.caption(
    f"**{preset['fondo']} · {comparto}** — datore {contrib_az_pct*100:.2f}% "
    f"(sui minimi+scatti) · tu min {preset['contrib_lav_pct']*100:.2f}% · "
    f"TFR {preset['tfr_pct']*100:.2f}% · TER {ter_fondo*100:.2f}%/anno · "
    f"rend. atteso {rend_medio_fondo*100:.1f}% (vol. {vol_fondo*100:.0f}%)"
)

vers_vol_extra = st.sidebar.number_input(
    "Versamento volontario AGGIUNTIVO annuo (€)", min_value=0, value=1000, step=100,
    help="Oltre al contributo minimo previsto dal CCNL. Deducibile dall'IRPEF.",
)

st.sidebar.header("4. Performance simulata")
st.sidebar.caption("200 scenari stocastici (GBM) sul rendimento del comparto.")
percentile_perf = st.sidebar.slider(
    "Percentile di performance", 5, 95, 50, 5,
    help="P5 = scenario molto sfortunato · P50 = mediano · P95 = molto fortunato",
)

st.sidebar.header("5. PAC (ETF)")
versamento_pac   = st.sidebar.number_input("Versamento PAC Annuo (€)", min_value=0, value=3445, step=100)

modo_pac = st.sidebar.radio(
    "Modalità PAC",
    ["Semplice (parametri manuali)", "Portafoglio ticker (dati storici)"],
    index=0,
    help="Con i ticker, rendimenti/volatilità/correlazioni vengono stimati dallo "
         "storico Yahoo Finance (rendimenti mensili) e la simulazione usa asset "
         "correlati via decomposizione di Cholesky.",
)
usa_portafoglio = modo_pac.startswith("Portafoglio")

rend_medio_pac, vol_pac = 0.07, 0.15   # fallback se il portafoglio non è disponibile
tickers_input = pesi_input = ""
anni_storico, override_rend, rend_override_val = 10, False, None

if usa_portafoglio:
    st.sidebar.markdown("**Catalogo ETF predefiniti**")
    st.sidebar.caption(
        "Seleziona uno o più ETF dalla legenda qui sotto, oppure aggiungine "
        "altri a mano nel campo in fondo. I ticker sono quelli usati da Yahoo "
        "Finance."
    )

    selezione_catalogo = {}
    for categoria, etfs in CATALOGO_ETF.items():
        scelti = st.sidebar.multiselect(categoria, list(etfs.keys()), key=f"cat_{categoria}")
        for nome in scelti:
            selezione_catalogo[etfs[nome]] = nome

    tickers_manuali_str = st.sidebar.text_input(
        "Aggiungi ticker manuale (separati da virgola, opzionale)", value="",
        help="Per ETF/azioni non presenti nel catalogo sopra. Es: XYZ.MI, ABC.DE",
    )
    tickers_manuali = [t.strip().upper() for t in tickers_manuali_str.split(",") if t.strip()]

    # Unione: catalogo (ordine di selezione) + manuali, senza duplicati
    tickers_scelti = list(selezione_catalogo.keys())
    for t in tickers_manuali:
        if t not in tickers_scelti:
            tickers_scelti.append(t)

    if len(tickers_scelti) == 0:
        st.sidebar.warning(
            "Nessun ticker selezionato: seleziona almeno un ETF dal catalogo "
            "o inseriscine uno a mano."
        )

    st.sidebar.markdown("**Pesi (%) per ciascun ticker selezionato**")
    pesi_dict = {}
    peso_default = round(100 / len(tickers_scelti), 1) if tickers_scelti else 0.0
    for t in tickers_scelti:
        etichetta = TICKER_TO_NOME.get(t, t)
        pesi_dict[t] = st.sidebar.number_input(
            f"Peso {etichetta}", min_value=0.0, max_value=100.0,
            value=peso_default, step=1.0, key=f"peso_{t}",
        )

    somma_pesi = sum(pesi_dict.values())
    if tickers_scelti:
        if abs(somma_pesi - 100.0) > 0.01:
            st.sidebar.caption(
                f"Somma pesi attuale: {somma_pesi:.1f}% — verrà normalizzata "
                f"automaticamente a 100% nella simulazione."
            )
        else:
            st.sidebar.caption(f"Somma pesi: {somma_pesi:.1f}% ✓")

    tickers_input = ", ".join(tickers_scelti)
    pesi_input = ", ".join(str(pesi_dict[t]) for t in tickers_scelti)

    with st.sidebar.expander("📖 Legenda completa ETF disponibili"):
        for categoria, etfs in CATALOGO_ETF.items():
            st.markdown(f"**{categoria}**")
            for nome, ticker in etfs.items():
                st.caption(f"`{ticker}` — {nome}")

    anni_storico = st.sidebar.slider("Anni di storico per la stima", 5, 20, 10)
    override_rend = st.sidebar.checkbox(
        "Correggi a mano il rendimento atteso", value=False,
        help="Volatilità e correlazioni restano quelle storiche (stime affidabili); "
             "il rendimento medio storico è un cattivo predittore del futuro e "
             "puoi sostituirlo con una tua stima prudente.",
    )
    if override_rend:
        rend_override_val = st.sidebar.slider(
            "Rendimento atteso portafoglio (%)", 1.0, 12.0, 6.0, 0.1) / 100
else:
    rend_medio_pac   = st.sidebar.slider("Rendimento medio atteso PAC (%)", 1.0, 12.0, 7.0, 0.1) / 100
    vol_pac          = st.sidebar.slider("Volatilità PAC (%)", 5.0, 25.0, 15.0, 0.5) / 100

ter_pac          = st.sidebar.number_input("TER PAC (%)", value=0.20, step=0.01) / 100
tassa_uscita_pac = st.sidebar.slider("Tassazione Plusvalenze PAC (%)", 0, 26, 26)

st.sidebar.header("6. TFR in Azienda")
rend_tfr  = st.sidebar.slider("Rendimento Annuo TFR in Azienda (%)", 0.0, 7.0, 2.5, 0.1,
                              help="Rivalutazione legale: 1,5% + 75% inflazione")/100
tassa_tfr = st.sidebar.slider("Tassazione TFR Uscita (%)", 23, 43, 27)

st.sidebar.header("7. Orizzonte e Uscita")
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
# PORTAFOGLIO A TICKER: download storico, stima parametri, Cholesky
# ---------------------------------------------------------------------------
def parse_ticker_pesi(tickers_str: str, pesi_str: str):
    """Converte le stringhe input in liste pulite, valida e normalizza i pesi."""
    tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
    pesi_raw = [p.strip() for p in pesi_str.split(",") if p.strip()]
    if len(tickers) == 0:
        raise ValueError("Inserisci almeno un ticker.")
    if len(pesi_raw) != len(tickers):
        raise ValueError(
            f"Hai {len(tickers)} ticker ma {len(pesi_raw)} pesi: devono combaciare."
        )
    pesi = np.array([float(p) for p in pesi_raw])
    if pesi.sum() <= 0:
        raise ValueError("La somma dei pesi deve essere positiva.")
    pesi = pesi / pesi.sum()   # normalizza a 1 anche se non sommano a 100
    return tickers, pesi


@st.cache_data(show_spinner=False)
def scarica_prezzi_mensili(tickers: tuple, anni: int):
    """
    Scarica lo storico giornaliero da Yahoo Finance per ciascun ticker e lo
    ricampiona a fine mese. Richiede connessione internet (yfinance).
    Restituisce un DataFrame (colonne=ticker, righe=mesi) di prezzi Adj Close,
    allineato sulle date comuni a tutti i ticker.
    """
    import yfinance as yf
    from datetime import date
    from dateutil.relativedelta import relativedelta

    end = date.today()
    start = end - relativedelta(years=anni)

    serie = {}
    for t in tickers:
        data = yf.download(t, start=start.isoformat(), end=end.isoformat(),
                            progress=False, auto_adjust=True)
        if data is None or data.empty:
            raise ValueError(f"Nessun dato scaricato per il ticker '{t}'. "
                              f"Verifica che sia corretto su Yahoo Finance.")
        col = "Close" if "Close" in data.columns else data.columns[0]
        prezzi_mensili = data[col].resample("ME").last()
        serie[t] = prezzi_mensili

    df = pd.DataFrame(serie).dropna()
    if len(df) < 24:
        raise ValueError(
            f"Storico comune troppo corto ({len(df)} mesi): riduci gli anni "
            f"richiesti o verifica i ticker (potrebbero non sovrapporsi nel tempo)."
        )
    return df


def stima_parametri_portafoglio(prezzi_df: pd.DataFrame, pesi: np.ndarray):
    """
    Da una matrice di prezzi mensili (colonne=ticker), calcola:
    - rendimenti mensili semplici per ciascun asset
    - rendimento medio annuo e volatilità annua per asset (dai rendimenti,
      MAI dai prezzi: la correlazione sui prezzi è distorta dal trend comune)
    - matrice di correlazione e di covarianza (annualizzate) tra i rendimenti
    - rendimento e volatilità del portafoglio pesato

    Ritorna un dizionario con tutti i pezzi, inclusa la matrice L di Cholesky
    della covarianza (mensile) per generare shock correlati nella simulazione.
    """
    rend_mensili = prezzi_df.pct_change().dropna()   # rendimenti, non prezzi

    media_mensile = rend_mensili.mean().values
    cov_mensile = rend_mensili.cov().values
    corr = rend_mensili.corr().values

    rend_annuo_asset = (1 + media_mensile) ** 12 - 1
    vol_annua_asset = rend_mensili.std().values * np.sqrt(12)

    # Portafoglio: rendimento = media pesata, volatilità = da matrice covarianza
    rend_portafoglio = float(np.dot(pesi, rend_annuo_asset))
    vol_portafoglio = float(np.sqrt(pesi @ (cov_mensile * 12) @ pesi))

    # Cholesky sulla covarianza mensile, per simulare shock mensili correlati
    # Piccolo ridge per stabilità numerica se la matrice è quasi singolare
    cov_reg = cov_mensile + np.eye(len(pesi)) * 1e-10
    L = np.linalg.cholesky(cov_reg)

    return {
        "tickers": list(prezzi_df.columns),
        "rend_annuo_asset": rend_annuo_asset,
        "vol_annua_asset": vol_annua_asset,
        "corr": corr,
        "media_mensile": media_mensile,
        "cholesky_mensile": L,
        "rend_portafoglio": rend_portafoglio,
        "vol_portafoglio": vol_portafoglio,
        "n_mesi_storico": len(rend_mensili),
        "prezzi_df": prezzi_df,
    }


@st.cache_data(show_spinner=False)
def genera_rendimenti_portafoglio_gbm(media_mensile, cholesky_mensile, pesi,
                                      durata_anni: int, rend_override=None,
                                      n: int = 200, seed: int = 13):
    """
    Genera n traiettorie annue del PORTAFOGLIO (già pesato) usando shock
    mensili correlati (Cholesky sulla covarianza storica), poi aggrega a
    rendimento annuo e infine seleziona per percentile come per gli altri
    motori GBM del simulatore.

    Se rend_override è fornito, si ridimensiona il drift mensile in modo che
    il rendimento medio annuo del portafoglio coincida con l'override, tenendo
    fissi volatilità e correlazioni storiche (vedi nota nell'app).
    """
    rng = np.random.default_rng(seed)
    n_asset = len(pesi)
    mesi_tot = durata_anni * 12

    drift = media_mensile.copy()
    if rend_override is not None:
        # Rendimento annuo attuale del portafoglio con questo drift
        rend_attuale = float(np.dot(pesi, (1 + drift) ** 12 - 1))
        # Scala il drift (in log-space approssimato) per centrare sull'override
        fattore_corr = np.log(1 + rend_override) / np.log(1 + rend_attuale) \
            if rend_attuale > -0.99 and rend_attuale != 0 else 1.0
        drift = drift * fattore_corr

    traiettorie_annue = np.zeros((n, durata_anni))
    for s in range(n):
        z = rng.standard_normal((mesi_tot, n_asset))
        shock_mensili = z @ cholesky_mensile.T          # correlati
        rend_mensili_asset = drift + shock_mensili       # (mesi_tot, n_asset)
        rend_mensile_portafoglio = rend_mensili_asset @ pesi   # (mesi_tot,)
        # Aggrega i 12 mesi di ciascun anno in un rendimento annuo composto
        rmp = rend_mensile_portafoglio.reshape(durata_anni, 12)
        rend_annuo = np.prod(1 + rmp, axis=1) - 1
        traiettorie_annue[s] = rend_annuo

    return traiettorie_annue


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
    ral_base = params["ral"]              # RAL totale anno 1 (tutte le voci)
    base_contrib0 = params["base_contrib"] # base contributiva anno 1 (minimi+scatti)
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
    cap_iniziale_fondo = params.get("cap_iniziale_fondo", 0.0)
    cap_iniziale_pac = params.get("cap_iniziale_pac", 0.0)
    molt_livello_annuo = params.get("molt_livello_annuo", None)  # lista per anno, opzionale

    # Aliquota fondo sui rendimenti annuali (media pesata 20% / 12,5%)
    aliq_rend_fondo = 0.20 * (1 - quota_ts) + 0.125 * quota_ts

    cap_fondo = float(cap_iniziale_fondo)   # montante di partenza già accumulato
    cap_pac = float(cap_iniziale_pac)       # montante ETF di partenza già accumulato
    # Il capitale PAC iniziale è considerato "già versato": non genera di per sé
    # plusvalenza, solo i rendimenti maturati da qui in avanti la generano.
    versato_pac_cum = float(cap_iniziale_pac)
    cap_tfr = 0.0
    risparmio_irpef_cum = 0.0
    rows = []

    for a, f in enumerate(fattori):
        anno = a + 1
        # Moltiplicatore di livello pianificato (promozione manuale): si applica
        # SOPRA la crescita stocastica di carriera (fattori), spostando l'intera
        # base retributiva al nuovo livello dall'anno indicato in poi.
        molt_liv = molt_livello_annuo[a] if molt_livello_annuo is not None else 1.0
        f_eff = f * molt_liv
        ral_curr = ral_base * f_eff
        base_contrib = base_contrib0 * f_eff  # minimi+scatti, cresce come la RAL

        # Contributi:
        # - TFR sull'intera retribuzione utile (approssimata = RAL)
        # - Contributo AZIENDA e minimo LAVORATORE calcolati sui MINIMI TABELLARI
        #   + scatti (la base contributiva), NON su superminimo e premio.
        tfr_curr = ral_curr * tfr_pct
        ca_curr  = base_contrib * ca_pct
        vol_min  = base_contrib * lav_pct
        vf_curr  = vol_min + vol_extra          # totale volontario lavoratore
        vp_curr  = vp0 * f

        # Deduzione IRPEF sui contributi deducibili (lavoratore + azienda, no TFR)
        deducibile = min(vf_curr + ca_curr, LIMITE_DEDUCIBILITA)
        aliq_marg = aliquota_marginale(ral_curr)
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
            "Contrib. Min. CCNL (€)": vol_min,
            "Vers. Volontario (€)": vol_extra,
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
# Composizione della RAL iniziale (Anno 1):
#   base contributiva = minimi tabellari + scatti già maturati
#   RAL totale         = base contributiva + superminimo + premio produzione
scatti_valore_annuo = (
    anni_anzianita_pregressi * scatto_valore_livello * mensilita
)
base_contrib_iniziale = minimo_annuo + scatti_valore_annuo
superminimo_annuo = superminimo_mensile * mensilita
ral_auto = base_contrib_iniziale + superminimo_annuo + premio_produzione_annuo

# Override manuale: se inserita, la RAL a mano sostituisce quella calcolata
# (usata per TFR e IRPEF). Il contributo azienda resta sui minimi+scatti.
ral_override = ral_manuale > 0
ral = ral_manuale if ral_override else ral_auto

coeff_totale = COEFF_LAVORATORE[tipo_lavoratore]
scenari = genera_scenari(profilo_crescita, coeff_totale, crescita_base, n=1000)

# Traiettorie GBM per fondo, selezione per percentile
rend_fondo_mat = genera_rendimenti_gbm(rend_medio_fondo, vol_fondo, durata, n=200, seed=7)
rend_fondo_sel = seleziona_traiettoria_per_percentile(rend_fondo_mat, percentile_perf)

# --- PAC: modalità semplice (GBM parametrico) oppure portafoglio a ticker ---
portafoglio_info = None
errore_portafoglio = None
if usa_portafoglio:
    if not tickers_input.strip():
        errore_portafoglio = (
            "Nessun ticker selezionato: seleziona almeno un ETF dal catalogo "
            "nella sidebar o inseriscine uno a mano."
        )
        rend_pac_mat = genera_rendimenti_gbm(0.07, 0.15, durata, n=200, seed=11)
    else:
        try:
            tickers, pesi = parse_ticker_pesi(tickers_input, pesi_input)
            prezzi_df = scarica_prezzi_mensili(tuple(tickers), anni_storico)
            portafoglio_info = stima_parametri_portafoglio(prezzi_df, pesi)
            rend_override_eff = rend_override_val if override_rend else None
            rend_pac_mat = genera_rendimenti_portafoglio_gbm(
                portafoglio_info["media_mensile"], portafoglio_info["cholesky_mensile"],
                pesi, durata, rend_override=rend_override_eff, n=200, seed=13,
            )
        except Exception as e:
            errore_portafoglio = str(e)
            # Fallback: GBM parametrico semplice se il download/stima fallisce
            rend_pac_mat = genera_rendimenti_gbm(0.07, 0.15, durata, n=200, seed=11)
else:
    rend_pac_mat = genera_rendimenti_gbm(rend_medio_pac, vol_pac, durata, n=200, seed=11)

rend_pac_sel = seleziona_traiettoria_per_percentile(rend_pac_mat, percentile_perf)

# --- Moltiplicatore di livello pianificato (promozioni manuali) ---
# Per ogni anno di simulazione, calcola di quanto sale il minimo tabellare
# rispetto al livello di partenza, in base ai passaggi che l'utente ha
# indicato manualmente (es. anno 5 -> C2). Si applica MOLTIPLICATIVAMENTE
# sopra la crescita stocastica di carriera (fattori), quindi i due effetti
# si sommano invece di escludersi a vicenda.
molt_livello_annuo = [1.0] * durata
if usa_passaggi_livello and passaggi_livello:
    livello_attivo = livello   # livello di partenza scelto in sidebar
    for a in range(durata):
        anno_corrente = a + 1
        # applica l'ultimo passaggio il cui anno_da <= anno_corrente
        for anno_da, liv_nuovo in passaggi_livello:
            if anno_da <= anno_corrente:
                livello_attivo = liv_nuovo
        minimo_attivo = preset["livelli"][livello_attivo]
        molt_livello_annuo[a] = minimo_attivo / minimo_mensile

params = dict(
    ral=ral, base_contrib=base_contrib_iniziale,
    tfr_pct=preset["tfr_pct"], ca_pct=contrib_az_pct,
    lav_pct=preset["contrib_lav_pct"], vers_vol_extra=vers_vol_extra,
    ter_f=ter_fondo, costo_fisso_f=preset["costo_fisso"], quota_ts=quota_ts,
    vp=versamento_pac, rend_pac_annui=rend_pac_sel, ter_p=ter_pac,
    tp=tassa_uscita_pac, rt=rend_tfr, tt=tassa_tfr,
    anni_pregressi=anni_gia_iscritto, uscita_ordinaria=uscita_ordinaria,
    cap_iniziale_fondo=capitale_iniziale_fondo,
    cap_iniziale_pac=capitale_iniziale_pac,
    molt_livello_annuo=molt_livello_annuo,
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
    f"**Profilo:** {tipo_lavoratore} · {ccnl_scelto} · livello {livello} · comparto {comparto}  \n"
    f"Coefficiente crescita ×{coeff_totale:.2f} · crescita di base "
    f"{crescita_base*100:.1f}%/anno (inflazione + rinnovi CCNL) · "
    f"Performance: **P{percentile_perf}** (1 traiettoria su 200 scenari stocastici)  \n"
    f"*I valori sono nominali: includono l'inflazione, coerentemente con contributi "
    f"e montante finale.*"
)

# --- Composizione della RAL iniziale ---
st.subheader("🧱 Composizione della RAL (Anno 1)")
if ral_override:
    rc1, rc2, rc3 = st.columns(3)
    rc1.metric("RAL inserita a mano", f"€ {ral:,.0f}",
               help="Override manuale attivo. Usata per TFR e IRPEF.")
    rc2.metric("Base contributiva fondo", f"€ {base_contrib_iniziale:,.0f}",
               help=f"Minimi {livello} + {anni_anzianita_pregressi} scatti. "
                    f"Il contributo azienda si calcola su questa, non sulla RAL manuale.")
    rc3.metric("RAL auto (confronto)", f"€ {ral_auto:,.0f}",
               help="RAL che risulterebbe dai minimi + voci inserite")
else:
    rc1, rc2, rc3, rc4 = st.columns(4)
    rc1.metric("Minimo tabellare", f"€ {minimo_annuo:,.0f}",
               help=f"Livello {livello}: {minimo_mensile:,.0f} €/mese × {mensilita} mensilità")
    rc2.metric("Scatti anzianità", f"€ {scatti_valore_annuo:,.0f}",
               help=f"{anni_anzianita_pregressi} scatti × {scatto_valore_livello:.1f} €/mese × {mensilita}")
    rc3.metric("Superminimo + premio", f"€ {superminimo_annuo + premio_produzione_annuo:,.0f}",
               help="Voci individuali, non entrano nel calcolo del contributo azienda")
    rc4.metric("RAL totale", f"€ {ral:,.0f}")

if usa_passaggi_livello and passaggi_livello:
    st.caption(
        "📈 **Passaggi di livello pianificati:** partenza da **" + livello + "** → "
        + " → ".join([f"anno {a}: **{liv}**" for a, liv in passaggi_livello])
        + ". Da ciascun anno indicato, il minimo tabellare del nuovo livello "
          "sostituisce quello di partenza come base; sopra si applica comunque "
          "la crescita simulata (scatti stocastici + inflazione)."
    )

cap_msg = ""
if capitale_iniziale_fondo > 0:
    cap_msg += (f" Nel fondo parti da un capitale già accumulato di "
                f"**€ {capitale_iniziale_fondo:,.0f}**.")
if capitale_iniziale_pac > 0:
    cap_msg += (f" Nel PAC parti da un capitale già accumulato di "
                f"**€ {capitale_iniziale_pac:,.0f}**.")

st.caption(
    f"Il contributo aziendale al fondo ({contrib_az_pct*100:.2f}%) e il tuo minimo "
    f"({preset['contrib_lav_pct']*100:.2f}%) si calcolano sulla **base contributiva** "
    f"di **€ {base_contrib_iniziale:,.0f}** (minimi tabellari + scatti), non sul "
    f"superminimo né sul premio. Il TFR ({preset['tfr_pct']*100:.2f}%) è sull'intera "
    f"retribuzione" + (" (RAL inserita a mano)." if ral_override else ".") + cap_msg
)
st.divider()


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
vers_vol_anno1 = r0["Contrib. Min. CCNL (€)"] + r0["Vers. Volontario (€)"]
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
# SEZIONE PORTAFOGLIO A TICKER (se attivo)
# ---------------------------------------------------------------------------
if usa_portafoglio:
    st.subheader("📈 Portafoglio PAC a Ticker")

    if not tickers_input.strip():
        st.warning(
            "Nessun ticker selezionato. Seleziona uno o più ETF dal catalogo "
            "nella sidebar (sezione '5. PAC (ETF)') oppure inserisci un ticker "
            "manuale. Nel frattempo uso un GBM di fallback (rend. 7%, vol. 15%)."
        )
    elif errore_portafoglio:
        st.error(
            f"Impossibile scaricare/stimare il portafoglio: {errore_portafoglio}  \n"
            f"Uso un GBM di fallback (rend. 7%, vol. 15%) finché non correggi "
            f"ticker/pesi o la connessione."
        )
    else:
        pi = portafoglio_info
        pc1, pc2, pc3 = st.columns(3)
        pc1.metric("Rendimento storico annuo (composto)", f"{pi['rend_portafoglio']*100:.2f}%",
                   help=f"Su {pi['n_mesi_storico']} mesi di storico. Media pesata dei "
                        f"rendimenti annualizzati dei singoli asset.")
        pc2.metric("Volatilità storica annua", f"{pi['vol_portafoglio']*100:.2f}%",
                   help="Da matrice di covarianza dei rendimenti mensili, annualizzata")
        pc3.metric("Asset nel portafoglio", f"{len(pi['tickers'])}")

        if override_rend:
            st.info(
                f"Rendimento atteso **corretto a mano** a {rend_override_val*100:.1f}% "
                f"(volatilità e correlazioni restano quelle storiche)."
            )

        # Tabella per singolo asset, con nome leggibile dal catalogo se disponibile
        nomi_leggibili = [TICKER_TO_NOME.get(t, t) for t in pi["tickers"]]
        df_asset = pd.DataFrame({
            "Nome": nomi_leggibili,
            "Ticker": pi["tickers"],
            "Peso (%)": (pesi * 100).round(1),
            "Rend. annuo storico (%)": (pi["rend_annuo_asset"] * 100).round(2),
            "Volatilità annua (%)": (pi["vol_annua_asset"] * 100).round(2),
        })
        st.dataframe(df_asset, use_container_width=True, hide_index=True)

        # Matrice di correlazione (sui rendimenti, non sui prezzi)
        with st.expander("🔗 Matrice di correlazione (sui rendimenti mensili)"):
            df_corr = pd.DataFrame(pi["corr"], index=pi["tickers"], columns=pi["tickers"])
            st.dataframe(df_corr.style.format("{:.2f}").background_gradient(
                cmap="RdYlGn_r", vmin=-1, vmax=1), use_container_width=True)
            st.caption(
                "Calcolata sui rendimenti mensili (non sui prezzi, che darebbero "
                "correlazioni gonfiate dal trend comune). Usata per generare shock "
                "correlati via decomposizione di Cholesky nella simulazione."
            )

        st.caption(
            "⚠️ Volatilità e correlazioni storiche sono stime ragionevoli del futuro; "
            "il rendimento medio storico lo è molto meno (un decennio favorevole non "
            "garantisce il prossimo). Valuta di correggerlo a mano con una stima prudente."
        )
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

cols_show = ["Anno", "RAL (€)", "Contrib. Min. CCNL (€)", "Vers. Volontario (€)", "TFR al Fondo (€)",
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
