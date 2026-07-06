import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os
import csv

# ---------------------------------------------------------------------------
# CONFIGURAZIONE PAGINA
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Simulatore Previdenziale Pro", layout="wide")
st.title("🚀 Confronto Previdenziale: Fondo vs PAC + TFR")

# ---------------------------------------------------------------------------
# DATI CCNL / FONDI NEGOZIALI (fonti: accordi CCNL, schede costi COVIP 2024/25)
# ---------------------------------------------------------------------------
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
            # NB: gli "atteso/vol" sono assunzioni forward-looking del GBM. In
            # modalità bootstrap si usano invece i rendimenti storici reali.
            "Garantito":   (0.0040, 0.010, 0.030, 0.70),
            "Bilanciato":  (0.0020, 0.027, 0.070, 0.45),
            "Azionario":   (0.0025, 0.045, 0.135, 0.20),
            # Monetario Plus: params GBM stimati (storico: CAGR ~1,1% vol ~1,5%)
            "Monetario":   (0.0025, 0.012, 0.015, 0.80),
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
        "livelli": {
            "Quadro": 2183.09, "I": 1966.54, "II": 1701.04, "III": 1453.94,
            "IV": 1257.46, "V": 1136.07, "VI": 1019.94, "VII": 873.22,
        },
        "scatti_valore_livello": {
            "Quadro": 30.0, "I": 27.0, "II": 25.0, "III": 22.0,
            "IV": 20.0, "V": 18.0, "VI": 16.0, "VII": 15.0,
        },
        "scatto_valore": 20.0,
        "scatto_ogni_anni": 3,
        "scatti_max": 5,
        "comparti": {
            "Conservativo":  (0.0050, 0.0133, 0.0281, 0.60),
            "Sviluppo":  (0.0045, 0.0241, 0.0503, 0.40),
            "Dinamico":  (0.0045, 0.0636, 0.0669, 0.25),
            "Crescita":  (0.0045, 0.0460, 0.0541, 0.15),
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
        "livelli": {
            "Quadro": 2986.95, "I": 2507.20, "II": 2236.65, "III": 1985.15,
            "IV": 1785.00, "V": 1662.00, "VI": 1543.05, "VII": 1399.35,
        },
        "scatti_valore_livello": {
            "Quadro": 26.0, "I": 25.0, "II": 23.0, "III": 22.0,
            "IV": 21.5, "V": 21.0, "VI": 20.5, "VII": 20.0,
        },
        "scatto_valore": 22.0,
        "scatto_ogni_anni": 3,
        "scatti_max": 10,
        "comparti": {
            "Conservativo":  (0.0050, 0.0133, 0.0281, 0.60),
            "Sviluppo":  (0.0045, 0.0241, 0.0503, 0.40),
            "Dinamico":  (0.0045, 0.0636, 0.0669, 0.25),
            "Crescita":  (0.0045, 0.0460, 0.0541, 0.15),
        },
    },
}

# ---------------------------------------------------------------------------
# STORICO RENDIMENTI DEI COMPARTI — caricato dai due CSV (cometa.csv e fonte.csv)
# ---------------------------------------------------------------------------
@st.cache_data
def carica_quote_storiche():
    quote = {}
    percorsi_trovati = []

    # 1. Carica i dati di COMETA
    path_cometa = os.path.join("data", "cometa.csv")
    if not os.path.exists(path_cometa): path_cometa = "cometa.csv" # fallback
    
    if os.path.exists(path_cometa):
        percorsi_trovati.append(path_cometa)
        df_c = pd.read_csv(path_cometa)
        for _, row in df_c.iterrows():
            y, m = int(row['anno']), int(row['mese'])
            for comp in ["Garantito", "Bilanciato", "Azionario", "Monetario"]:
                if comp in df_c.columns and pd.notna(row[comp]):
                    quote.setdefault(("Cometa", comp), {})[(y, m)] = float(row[comp])

    # 2. Carica i dati di FON.TE
    path_fonte = os.path.join("data", "fonte.csv")
    if not os.path.exists(path_fonte): path_fonte = "fonte.csv" # fallback
    
    if os.path.exists(path_fonte):
        percorsi_trovati.append(path_fonte)
        df_f = pd.read_csv(path_fonte)
        for _, row in df_f.iterrows():
            y, m = int(row['anno']), int(row['mese'])
            for comp in ["Conservativo", "Sviluppo", "Dinamico", "Crescita"]:
                if comp in df_f.columns and pd.notna(row[comp]):
                    quote.setdefault(("Fon.Te", comp), {})[(y, m)] = float(row[comp])

    if not percorsi_trovati:
        return {}, {}, None

    # Trasforma le quote in rendimenti percentuali (mensili e annuali)
    mensile, annuale = {}, {}
    for (fondo, comp), serie in quote.items():
        chiavi = sorted(serie)
        rend_m = [round(serie[chiavi[i]] / serie[chiavi[i-1]] - 1, 6)
                  for i in range(1, len(chiavi))]
        mensile.setdefault(fondo, {})[comp] = rend_m

        anni_dic = sorted({y for (y, m) in serie if m == 12})
        rend_a = []
        for y in anni_dic:
            if (y, 12) in serie and (y - 1, 12) in serie:
                rend_a.append(round(serie[(y, 12)] / serie[(y - 1, 12)] - 1, 5))
        annuale.setdefault(fondo, {})[comp] = rend_a

    return mensile, annuale, percorsi_trovati

STORICO_MENSILE, STORICO_ANNUALE, _PERCORSI = carica_quote_storiche()

if not _PERCORSI:
    st.error(
        "**File dati storici non trovati.** Assicurati che i file `cometa.csv` e "
        "`fonte.csv` si trovino all'interno della cartella `data/` su GitHub."
    )
    st.stop()

def annuale_disponibile(fondo: str, comparto: str, min_anni: int = 5) -> bool:
    serie = STORICO_ANNUALE.get(fondo, {}).get(comparto, [])
    return len(serie) >= min_anni

def mensile_disponibile(fondo: str, comparto: str, min_mesi: int = 24) -> bool:
    serie = STORICO_MENSILE.get(fondo, {}).get(comparto, [])
    return len(serie) >= min_mesi

# ---------------------------------------------------------------------------
# COEFFICIENTI DI CRESCITA per tipo lavoratore (solo Operaio / Impiegato)
# ---------------------------------------------------------------------------
COEFF_LAVORATORE = {
    "Operaio":   0.88,
    "Impiegato": 1.08,
}

# ---------------------------------------------------------------------------
# CATALOGO ETF PREDEFINITI — ticker Yahoo Finance (SOLO accumulazione UCITS)
# ---------------------------------------------------------------------------
# Catalogo curato per contenere solo ETF/ETC UCITS ad ACCUMULAZIONE (i proventi
# vengono reinvestiti, coerente con un PAC di lungo periodo). I ticker noti come
# "a distribuzione" sono stati rimossi dal catalogo e finiscono nella lista
# ETF_FLAG piu' sotto, che alimenta il controllo automatico.
CATALOGO_ETF = {
    "Azionario Globale": {
        "iShares Core MSCI World Acc (SWDA.MI)": "SWDA.MI",
        "Vanguard FTSE All-World Acc (VWCE.DE)": "VWCE.DE",
        "Xtrackers MSCI World Acc (XDWD.MI)": "XDWD.MI",
        "iShares MSCI ACWI Acc (SSAC.MI)": "SSAC.MI",
    },
    "Azionario USA": {
        "iShares Core S&P 500 Acc (CSSPX.MI)": "CSSPX.MI",
        "Xtrackers S&P 500 Acc (XSPX.MI)": "XSPX.MI",
        "Invesco Nasdaq-100 Acc (EQAC.MI)": "EQAC.MI",
    },
    "Azionario Europa": {
        "Xtrackers Euro Stoxx 50 Acc (XESC.MI)": "XESC.MI",
        "iShares Core MSCI EMU Acc (CEBL.MI)": "CEBL.MI",
    },
    "Azionario Mercati Emergenti": {
        "iShares Core MSCI EM IMI Acc (EIMI.MI)": "EIMI.MI",
        "Xtrackers MSCI Emerging Markets Acc (XMME.MI)": "XMME.MI",
    },
    "Obbligazionario": {
        "iShares Core Global Aggregate Bond EUR-H Acc (AGGH.MI)": "AGGH.MI",
        "Xtrackers Global Government Bond EUR-H Acc (XG7S.MI)": "XG7S.MI",
    },
    "Oro e Materie Prime": {
        "iShares Physical Gold ETC (SGLN.MI)": "SGLN.MI",
        "Invesco Physical Gold ETC (SGLD.MI)": "SGLD.MI",
        "WisdomTree Broad Commodities Acc (WCOA.MI)": "WCOA.MI",
    },
    "Immobiliare (REIT)": {
        "Xtrackers FTSE EPRA/NAREIT Global Acc (XREA.MI)": "XREA.MI",
    },
}
# Mappa inversa ticker -> nome leggibile, utile per la legenda finale
TICKER_TO_NOME = {t: nome for cat in CATALOGO_ETF.values() for nome, t in cat.items()}
# Insieme dei ticker "certificati" ad accumulazione UCITS dal catalogo
WHITELIST_ACC_UCITS = set(TICKER_TO_NOME.keys())

# Ticker noti come NON ad accumulazione (a distribuzione) o da verificare.
# Usati per avvisare l'utente se li inserisce a mano.
ETF_FLAG = {
    "EQQQ.MI": "a DISTRIBUZIONE — la versione ad accumulo è EQAC.MI (o SB.. classi acc)",
    "EXSA.MI": "a DISTRIBUZIONE (iShares STOXX Europe 600, dist)",
    "IWDP.MI": "a DISTRIBUZIONE (Property *Yield*)",
    "IBGX.MI": "a DISTRIBUZIONE (iShares Euro Gov Bond 3-5y, dist)",
    "IEBC.MI": "a DISTRIBUZIONE (iShares Euro Corporate Bond, dist)",
    "EMU.MI":  "DA VERIFICARE (esistono classi dist e acc con ticker vicini)",
    "IWRD.MI": "a DISTRIBUZIONE (versione acc: SWDA.MI)",
    "VWRL.MI": "a DISTRIBUZIONE (versione acc: VWCE.DE)",
}

def classifica_ticker(ticker: str):
    """
    Ritorna (stato, nota) sullo stato di accumulazione/UCITS di un ticker.
    stato ∈ {"ok", "warn", "sconosciuto"}.
    - "ok": presente nel catalogo curato (accumulazione UCITS).
    - "warn": presente in ETF_FLAG (distribuente o da verificare).
    - "sconosciuto": non classificabile automaticamente -> l'utente deve
      verificarne dist/acc e status UCITS sulla scheda (KID/factsheet).
    Nota: Yahoo Finance NON espone in modo affidabile il flag dist/acc, quindi
    la verifica automatica si basa su una whitelist curata, non sui dati Yahoo.
    """
    t = ticker.strip().upper()
    if t in WHITELIST_ACC_UCITS:
        return "ok", "accumulazione UCITS (da catalogo curato)"
    if t in ETF_FLAG:
        return "warn", ETF_FLAG[t]
    return "sconosciuto", ("non in whitelist: verifica sul KID che sia ad "
                           "accumulazione e UCITS prima di usarlo")

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

scatto_valore_livello = preset.get("scatti_valore_livello", {}).get(
    livello, preset["scatto_valore"]
)
comparti_base = list(preset["comparti"].keys())

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
    help="Montante già accumulato se sei iscritto da tempo.",
)
capitale_iniziale_pac = st.sidebar.number_input(
    "Capitale già presente nel PAC (€)", min_value=0, value=0, step=1000,
    help="Montante ETF già accumulato, se il PAC è già avviato da tempo.",
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
    help="Adeguamento applicato ogni anno anche senza promozioni (~1,5–2,5% storico).",
) / 100

# --- Orizzonte spostato in alto: serve alle sezioni carriera/CCNL/disoccup. ---
durata = st.sidebar.slider("Anni di investimento", 1, 40, 25)

st.sidebar.markdown("**Passaggi di livello (promozioni pianificate)**")
usa_passaggi_livello = st.sidebar.checkbox(
    "Pianifica cambi di livello/mansione durante la carriera", value=False,
    help="Indica TU in quali anni futuri passerai a un livello superiore. Il "
         "nuovo minimo tabellare sostituisce la base da quell'anno; sopra continua "
         "la crescita simulata (scatti stocastici + inflazione).",
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
    passaggi_livello.sort(key=lambda x: x[0])

# --- NUOVO: Cambio CCNL / fondo durante la carriera --------------------------
st.sidebar.markdown("**Cambio CCNL / fondo (cambio settore)**")
usa_cambio_ccnl = st.sidebar.checkbox(
    "Pianifica uno o più cambi di CCNL durante la carriera", value=False,
    help="Simula un cambio di settore/contratto: da un certo anno cambiano "
         "contributi, TFR, costi, comparto e minimi tabellari (nuovo fondo).",
)
cambi_ccnl = []  # lista di (anno_da, ccnl_name, livello, comparto)
if usa_cambio_ccnl:
    n_cambi = st.sidebar.number_input(
        "Numero di cambi CCNL pianificati", min_value=1, max_value=6,
        value=1, step=1, key="n_cambi_ccnl",
    )
    for i in range(int(n_cambi)):
        anno_c = st.sidebar.number_input(
            f"Cambio #{i+1} — anno", min_value=1, max_value=40,
            value=min(10 * (i + 1), 40), step=1, key=f"anno_ccnl_{i}",
        )
        ccnl_new = st.sidebar.selectbox(
            f"Cambio #{i+1} — nuovo CCNL", list(CCNL_PRESET.keys()),
            key=f"ccnl_new_{i}",
        )
        preset_new = CCNL_PRESET[ccnl_new]
        liv_new = st.sidebar.selectbox(
            f"Cambio #{i+1} — livello", list(preset_new["livelli"].keys()),
            key=f"liv_ccnl_{i}",
        )
        _cn = list(preset_new["comparti"].keys())
        comp_new = st.sidebar.selectbox(
            f"Cambio #{i+1} — comparto", _cn,
            index=_cn.index("Azionario") if "Azionario" in _cn else len(_cn) - 1,
            key=f"comp_ccnl_{i}",
        )
        cambi_ccnl.append((int(anno_c), ccnl_new, liv_new, comp_new))
    cambi_ccnl.sort(key=lambda x: x[0])

# --- NUOVO: Periodi di disoccupazione ----------------------------------------
st.sidebar.markdown("**Periodi di disoccupazione**")
usa_disoccupazione = st.sidebar.checkbox(
    "Inserisci periodi senza reddito", value=False,
    help="Negli anni indicati: nessun contributo (TFR, azienda, tuo, PAC) e "
         "RAL a zero. I capitali già accumulati continuano comunque a rendere.",
)
anni_disoccupato = set()
if usa_disoccupazione:
    anni_disoccupato = set(st.sidebar.multiselect(
        "Anni di disoccupazione", list(range(1, durata + 1)),
        help="Anno 1 = primo anno di simulazione.",
    ))

st.sidebar.header("3. Fondo")
_idx_comp = comparti_base.index("Azionario") if "Azionario" in comparti_base else len(comparti_base) - 1
comparto = st.sidebar.selectbox("Comparto d'investimento", comparti_base, index=_idx_comp)
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

st.sidebar.header("4. Performance simulata (Fondo)")
metodo_resampling = st.sidebar.radio(
    "Metodo di resampling del fondo",
    ["Block-bootstrap mensile", "Bootstrap annuale"],
    index=0,
    help="I rendimenti del fondo vengono SEMPRE dal ricampionamento dello storico "
         "reale del comparto (nessun GBM). Il block-bootstrap mensile ricampiona "
         "blocchi di 12 mesi consecutivi (più dati, preserva la sequenza); il "
         "bootstrap annuale ricampiona direttamente i rendimenti di ogni anno.",
)
usa_mensile = metodo_resampling.startswith("Block")
block_mesi = 12
if usa_mensile:
    block_mesi = st.sidebar.number_input(
        "Lunghezza blocco (mesi)", min_value=3, max_value=24, value=12, step=1,
        help="Dimensione del blocco contiguo ricampionato. 12 = un anno intero.",
    )

st.sidebar.caption("Banda P10–P90 mostrata su tutte le curve (200 scenari).")
percentile_perf = st.sidebar.slider(
    "Percentile della linea centrale", 5, 95, 50, 5,
    help="P5 = scenario molto sfortunato · P50 = mediano · P95 = molto fortunato. "
         "La banda P10–P90 attorno resta sempre visibile.",
)

st.sidebar.header("5. PAC (ETF)")
versamento_pac = st.sidebar.number_input("Versamento PAC Annuo (€)", min_value=0, value=3445, step=100)

modo_pac = st.sidebar.radio(
    "Modalità PAC",
    ["Semplice (parametri manuali)", "Portafoglio ticker (dati storici)"],
    index=0,
    help="Con i ticker, rendimenti/volatilità/correlazioni vengono stimati dallo "
         "storico Yahoo Finance e la simulazione usa asset correlati via Cholesky.",
)
usa_portafoglio = modo_pac.startswith("Portafoglio")

rend_medio_pac, vol_pac = 0.07, 0.15   # fallback
tickers_input = pesi_input = ""
anni_storico, override_rend, rend_override_val = 10, False, None

if usa_portafoglio:
    st.sidebar.markdown("**Catalogo ETF predefiniti (solo accumulazione UCITS)**")
    st.sidebar.caption(
        "Seleziona uno o più ETF dalla legenda, oppure aggiungine a mano. "
        "I ticker manuali NON in whitelist vengono segnalati (dist/acc/UCITS)."
    )

    selezione_catalogo = {}
    for categoria, etfs in CATALOGO_ETF.items():
        scelti = st.sidebar.multiselect(categoria, list(etfs.keys()), key=f"cat_{categoria}")
        for nome in scelti:
            selezione_catalogo[etfs[nome]] = nome

    tickers_manuali_str = st.sidebar.text_input(
        "Aggiungi ticker manuale (separati da virgola, opzionale)", value="",
        help="Per ETF non presenti nel catalogo. Verifica che siano ad accumulo UCITS.",
    )
    tickers_manuali = [t.strip().upper() for t in tickers_manuali_str.split(",") if t.strip()]

    tickers_scelti = list(selezione_catalogo.keys())
    for t in tickers_manuali:
        if t not in tickers_scelti:
            tickers_scelti.append(t)

    # --- CONTROLLO ACCUMULAZIONE / UCITS sui ticker scelti ---
    avvisi_ticker = []
    for t in tickers_scelti:
        stato, nota = classifica_ticker(t)
        if stato == "warn":
            avvisi_ticker.append(f"⚠️ **{t}**: {nota}")
        elif stato == "sconosciuto":
            avvisi_ticker.append(f"❓ **{t}**: {nota}")
    if avvisi_ticker:
        st.sidebar.warning(
            "Controllo accumulazione/UCITS:\n\n" + "\n\n".join(avvisi_ticker)
        )

    if len(tickers_scelti) == 0:
        st.sidebar.warning("Nessun ticker selezionato: scegline almeno uno.")

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
            st.sidebar.caption(f"Somma pesi: {somma_pesi:.1f}% — normalizzata a 100%.")
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
        "Correggi a mano il rendimento atteso", value=True,
        help="Consigliato: il rendimento medio storico è un cattivo predittore "
             "del futuro. Volatilità e correlazioni restano quelle storiche.",
    )
    if override_rend:
        rend_override_val = st.sidebar.slider(
            "Rendimento atteso portafoglio (%)", 1.0, 12.0, 6.0, 0.1) / 100
else:
    rend_medio_pac = st.sidebar.slider("Rendimento medio atteso PAC (%)", 1.0, 12.0, 7.0, 0.1) / 100
    vol_pac        = st.sidebar.slider("Volatilità PAC (%)", 5.0, 25.0, 15.0, 0.5) / 100

ter_pac          = st.sidebar.number_input("TER PAC (%)", value=0.20, step=0.01) / 100
tassa_uscita_pac = st.sidebar.slider("Tassazione Plusvalenze PAC (%)", 0, 26, 26)

st.sidebar.header("6. TFR in Azienda")
rend_tfr  = st.sidebar.slider("Rendimento Annuo TFR in Azienda (%)", 0.0, 7.0, 2.5, 0.1,
                              help="Rivalutazione legale: 1,5% + 75% inflazione")/100
tassa_tfr = st.sidebar.slider("Tassazione TFR Uscita (%)", 23, 43, 27)

st.sidebar.header("7. Uscita dal fondo")
anni_gia_iscritto = st.sidebar.number_input(
    "Anni di adesione già maturati al fondo", min_value=0, max_value=40, value=0, step=1,
    help="Servono per l'aliquota di uscita agevolata (sconto dopo il 15° anno)",
)
motivo_uscita = st.sidebar.selectbox(
    "Motivo di uscita dal fondo",
    [
        "Prestazione pensionistica / causali agevolate (9–15%)",
        "Riscatto/anticipazione ordinaria (23%)",
    ],
    index=0,
)
uscita_ordinaria = motivo_uscita.startswith("Riscatto")
usa_entrambi = st.sidebar.checkbox("Uso sia Fondo che PAC (somma senza TFR)", value=True)


# ---------------------------------------------------------------------------
# IRPEF
# ---------------------------------------------------------------------------
LIMITE_DEDUCIBILITA = 5164.57

def aliquota_marginale(imponibile: float) -> float:
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


# ---------------------------------------------------------------------------
# ALIQUOTA DI USCITA DEL FONDO PENSIONE
# ---------------------------------------------------------------------------
def aliquota_uscita_fondo(anni_adesione_totali: int, ordinaria: bool = False) -> float:
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
            base_anno = max(0.0, crescita_base + rng.normal(0, 0.004))
            molt *= (1.0 + base_anno)
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
# GENERAZIONE TRAIETTORIE DI RENDIMENTO (GBM)
# ---------------------------------------------------------------------------
@st.cache_data
def genera_rendimenti_gbm(rend_medio: float, vol: float, durata: int,
                          n: int = 200, seed: int = 7):
    rng = np.random.default_rng(seed)
    sigma = np.sqrt(np.log(1 + (vol**2) / ((1 + rend_medio)**2)))
    mu = np.log(1 + rend_medio) - 0.5 * sigma**2
    shocks = rng.normal(mu, sigma, size=(n, durata))
    rendimenti = np.exp(shocks) - 1.0
    return rendimenti


# ---------------------------------------------------------------------------
# BRANCH SPERIMENTALE: BOOTSTRAP STORICO DEI RENDIMENTI DI COMPARTO
# ---------------------------------------------------------------------------
@st.cache_data
def genera_rendimenti_bootstrap(serie_storica: tuple, durata: int,
                                n: int = 200, seed: int = 21):
    """
    Ricampiona (bootstrap iid, con reinserimento) i rendimenti annui storici
    REALI del comparto per costruire n traiettorie lunghe `durata`. A differenza
    del GBM non assume una distribuzione: usa direttamente la distribuzione
    empirica degli anni osservati (code, asimmetrie e crash inclusi).

    `serie_storica` è una tupla di rendimenti annui in forma decimale.
    Ritorna una matrice (n x durata). Solleva ValueError se la serie è vuota.
    """
    serie = np.array(serie_storica, dtype=float)
    if serie.size == 0:
        raise ValueError("Serie storica del comparto vuota.")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, serie.size, size=(n, durata))
    return serie[idx]


@st.cache_data
def genera_rendimenti_block_bootstrap(serie_mensile: tuple, durata: int,
                                      block: int = 12, n: int = 200, seed: int = 33):
    """
    BLOCK-BOOTSTRAP MENSILE. Ricampiona blocchi CONTIGUI di `block` mesi dai
    rendimenti mensili storici reali del comparto (bootstrap circolare, con
    wrap-around), li concatena fino a coprire `durata` anni, poi compone ogni
    finestra di 12 mesi in un rendimento annuo.

    Rispetto al bootstrap annuale iid, preserva la struttura temporale interna
    (autocorrelazione, sequenze di mesi buoni/cattivi) e sfrutta MOLTE più
    osservazioni: es. un comparto con 5 soli anni ma 72 mesi diventa utilizzabile.

    Ritorna una matrice (n x durata) di rendimenti annui.
    """
    serie = np.array(serie_mensile, dtype=float)
    m = serie.size
    if m < block:
        raise ValueError(f"Servono almeno {block} mesi, disponibili {m}.")
    rng = np.random.default_rng(seed)
    mesi_tot = durata * 12
    out = np.empty((n, durata))
    n_blocchi = int(np.ceil(mesi_tot / block))
    for s in range(n):
        start = rng.integers(0, m, size=n_blocchi)
        path = np.concatenate([serie[(st + np.arange(block)) % m] for st in start])[:mesi_tot]
        out[s] = np.prod(1 + path.reshape(durata, 12), axis=1) - 1
    return out


def rendimento_netto_comparto(r, ter, quota_ts):
    """
    Rende netto annuo a livello di comparto, coerente col motore del montante:
    tassa 20%/12,5% (media pesata sulla quota in titoli di Stato) applicata al
    rendimento, poi TER. Vale anche per r<0 (credito d'imposta implicito).
    """
    aliq = 0.20 * (1 - quota_ts) + 0.125 * quota_ts
    r = np.asarray(r, dtype=float)
    return (1 + r * (1 - aliq)) * (1 - ter) - 1


def seleziona_traiettoria_per_percentile(rendimenti: np.ndarray, percentile: int):
    montanti = np.prod(1 + rendimenti, axis=1)
    ordine = np.argsort(montanti)
    idx = int(round((percentile / 100) * (len(ordine) - 1)))
    return rendimenti[ordine[idx]]


# ---------------------------------------------------------------------------
# PORTAFOGLIO A TICKER: download storico, stima parametri, Cholesky
# ---------------------------------------------------------------------------
def parse_ticker_pesi(tickers_str: str, pesi_str: str):
    tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
    pesi_raw = [p.strip() for p in pesi_str.split(",") if p.strip()]
    if len(tickers) == 0:
        raise ValueError("Inserisci almeno un ticker.")
    if len(pesi_raw) != len(tickers):
        raise ValueError(f"Hai {len(tickers)} ticker ma {len(pesi_raw)} pesi.")
    pesi = np.array([float(p) for p in pesi_raw])
    if pesi.sum() <= 0:
        raise ValueError("La somma dei pesi deve essere positiva.")
    pesi = pesi / pesi.sum()
    return tickers, pesi


@st.cache_data(show_spinner=False)
def scarica_prezzi_mensili(tickers: tuple, anni: int):
    import yfinance as yf
    import pandas as pd
    from datetime import date
    from dateutil.relativedelta import relativedelta

    end = date.today()
    start = end - relativedelta(years=anni)

    serie = {}
    for t in tickers:
        data = yf.download(t, start=start.isoformat(), end=end.isoformat(),
                           progress=False, auto_adjust=False, actions=False)
        if data is None or data.empty:
            raise ValueError(f"Nessun dato scaricato per '{t}'. Verifica il ticker su Yahoo.")
       if "Adj Close" in data.columns:
            col_data = data["Adj Close"]
        elif "Close" in data.columns:
            col_data = data["Close"]
        else:
            col_data = data.iloc[:, 0]
        if isinstance(col_data, pd.DataFrame):
            col_data = col_data.iloc[:, 0]
        serie[t] = col_data.resample("ME").last()

    df = pd.DataFrame(serie).dropna()
    if len(df) < 24:
        raise ValueError(
            f"Storico comune troppo corto ({len(df)} mesi): riduci gli anni o "
            f"verifica i ticker."
        )
    return df


def stima_parametri_portafoglio(prezzi_df: pd.DataFrame, pesi: np.ndarray):
    rend_mensili = prezzi_df.pct_change().dropna()
    media_mensile = rend_mensili.mean().values
    cov_mensile = rend_mensili.cov().values
    corr = rend_mensili.corr().values
    rend_annuo_asset = (1 + media_mensile) ** 12 - 1
    vol_annua_asset = rend_mensili.std().values * np.sqrt(12)
    rend_portafoglio = float(np.dot(pesi, rend_annuo_asset))
    vol_portafoglio = float(np.sqrt(pesi @ (cov_mensile * 12) @ pesi))
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
    rng = np.random.default_rng(seed)
    n_asset = len(pesi)
    mesi_tot = durata_anni * 12
    drift = media_mensile.copy()
    if rend_override is not None:
        rend_attuale = float(np.dot(pesi, (1 + drift) ** 12 - 1))
        fattore_corr = np.log(1 + rend_override) / np.log(1 + rend_attuale) \
            if rend_attuale > -0.99 and rend_attuale != 0 else 1.0
        drift = drift * fattore_corr

    traiettorie_annue = np.zeros((n, durata_anni))
    for s in range(n):
        z = rng.standard_normal((mesi_tot, n_asset))
        shock_mensili = z @ cholesky_mensile.T
        rend_mensili_asset = drift + shock_mensili
        rend_mensile_portafoglio = rend_mensili_asset @ pesi
        rmp = rend_mensile_portafoglio.reshape(durata_anni, 12)
        rend_annuo = np.prod(1 + rmp, axis=1) - 1
        traiettorie_annue[s] = rend_annuo
    return traiettorie_annue


# ---------------------------------------------------------------------------
# COSTRUZIONE DELLO SCHEDULE ANNO-PER-ANNO (livello, CCNL, comparto, disoccup.)
# ---------------------------------------------------------------------------
def costruisci_schedule(durata, ccnl_start, livello_start, comparto_start,
                        eta, anni_pregressi_scatti, superminimo_annuo,
                        premio_annuo, crescita_base, passaggi_livello,
                        cambi_ccnl, anni_disoccupato):
    """
    Ritorna una lista lunga `durata`. Ogni elemento descrive il CCNL/livello/
    comparto ATTIVO in quell'anno e i parametri contributivi derivati, così che
    il motore possa gestire cambi di livello, cambi di CCNL e disoccupazione
    semplicemente leggendo lo schedule.
    """
    # eventi (anno_da, tipo, payload) applicati cumulativamente
    eventi = []
    for anno_da, liv in passaggi_livello:
        eventi.append((anno_da, "livello", liv))
    for anno_da, ccnl_n, liv_n, comp_n in cambi_ccnl:
        eventi.append((anno_da, "ccnl", (ccnl_n, liv_n, comp_n)))
    eventi.sort(key=lambda x: x[0])

    sched = []
    for a in range(durata):
        anno = a + 1
        ccnl_att, liv_att, comp_att = ccnl_start, livello_start, comparto_start
        for anno_da, tipo, payload in eventi:
            if anno_da <= anno:
                if tipo == "livello":
                    liv_att = payload
                else:
                    ccnl_att, liv_att, comp_att = payload
        preset_a = CCNL_PRESET[ccnl_att]
        # comparto di ripiego se il nome non esiste nel nuovo fondo
        if comp_att not in preset_a["comparti"]:
            comp_att = list(preset_a["comparti"].keys())[-1]

        mens_a = preset_a["mensilita"]
        minimo_mensile_a = preset_a["livelli"][liv_att]
        minimo_annuo_a = minimo_mensile_a * mens_a
        scatto_val_liv_a = preset_a.get("scatti_valore_livello", {}).get(
            liv_att, preset_a["scatto_valore"])
        scatto_annuo_a = scatto_val_liv_a * mens_a
        freq_a = preset_a["scatto_ogni_anni"]
        max_a = preset_a["scatti_max"]

        eta_corrente = eta + a
        u35 = eta_corrente < 35
        ca_pct_a = preset_a["contrib_azienda_u35_pct"] if u35 else preset_a["contrib_azienda_pct"]
        lav_pct_a = preset_a["contrib_lav_pct"]
        tfr_pct_a = preset_a["tfr_pct"]

        ter_f_a, rend_a, vol_a, quota_ts_a = preset_a["comparti"][comp_att]
        costo_fisso_a = preset_a["costo_fisso"]

        # base contributiva teorica = minimo + scatti maturati, rivalutata
        anni_servizio = anni_pregressi_scatti * freq_a + anno
        scatti_maturati = min(max_a, anni_servizio // freq_a)
        base_teorica = minimo_annuo_a + scatti_maturati * scatto_annuo_a
        base_contrib_a = base_teorica * ((1 + crescita_base) ** a)

        # base RAL (anno 1 equivalente del segmento), scalata poi dalla carriera
        ral_base_eff_a = (minimo_annuo_a + anni_pregressi_scatti * scatto_annuo_a
                          + superminimo_annuo + premio_annuo)

        occupato = anno not in anni_disoccupato

        sched.append({
            "anno": anno,
            "ccnl": ccnl_att, "livello": liv_att, "comparto": comp_att,
            "fondo": preset_a["fondo"], "comparto_key": (preset_a["fondo"], comp_att),
            "mensilita": mens_a,
            "ca_pct": ca_pct_a, "lav_pct": lav_pct_a, "tfr_pct": tfr_pct_a,
            "ter_f": ter_f_a, "costo_fisso_f": costo_fisso_a, "quota_ts": quota_ts_a,
            "rend_medio": rend_a, "vol": vol_a,
            "base_contrib": base_contrib_a if occupato else 0.0,
            "ral_base_eff": ral_base_eff_a,
            "occupato": occupato,
        })
    return sched


# ---------------------------------------------------------------------------
# MOTORE DI SIMULAZIONE DEL CAPITALE (schedule-driven)
# ---------------------------------------------------------------------------
def simula_capitale(fattori, rend_fondo_annui, rend_pac_annui, sched, scal) -> pd.DataFrame:
    """
    Simula anno per anno fondo, PAC e TFR usando lo schedule (che incapsula
    livello/CCNL/comparto/disoccupazione anno per anno). `rend_fondo_annui` e
    `rend_pac_annui` sono due traiettorie annue (già coerenti con lo schedule
    dei comparti per il fondo).
    """
    ral_override = scal["ral_override"]
    ral_manuale = scal["ral_manuale"]
    vol_extra = scal["vers_vol_extra"]
    vp0 = scal["vp"]
    ter_p = scal["ter_p"]
    tp = scal["tp"] / 100
    rt = scal["rt"]
    tt = scal["tt"] / 100
    anni_pregressi = scal["anni_pregressi"]
    uscita_ord = scal["uscita_ordinaria"]

    cap_fondo = float(scal.get("cap_iniziale_fondo", 0.0))
    cap_pac = float(scal.get("cap_iniziale_pac", 0.0))
    versato_pac_cum = float(scal.get("cap_iniziale_pac", 0.0))
    cap_tfr = 0.0
    rows = []

    for a, f in enumerate(fattori):
        s = sched[a]
        anno = a + 1
        occupato = s["occupato"]

        # RAL: override manuale (se attivo) solo mentre si è occupati
        if occupato:
            ral_curr = ral_manuale * f if ral_override else s["ral_base_eff"] * f
        else:
            ral_curr = 0.0

        base_contrib = s["base_contrib"]  # già 0 se disoccupato
        aliq_rend_fondo = 0.20 * (1 - s["quota_ts"]) + 0.125 * s["quota_ts"]

        tfr_curr = ral_curr * s["tfr_pct"] if occupato else 0.0
        ca_curr = base_contrib * s["ca_pct"]
        vol_min = base_contrib * s["lav_pct"]
        vf_curr = vol_min + (vol_extra if occupato else 0.0)
        vp_curr = (vp0 * f) if occupato else 0.0

        # Deduzione IRPEF (solo se occupato e c'è reddito)
        if occupato and (vf_curr + ca_curr) > 0:
            deducibile = min(vf_curr + ca_curr, LIMITE_DEDUCIBILITA)
            aliq_marg = aliquota_marginale(ral_curr)
            quota_lav = vf_curr / (vf_curr + ca_curr)
            risparmio_anno = deducibile * aliq_marg * quota_lav
        else:
            risparmio_anno = 0.0

        # --- FONDO ---
        cap_fondo += vf_curr + tfr_curr + ca_curr
        rend_lordo = cap_fondo * rend_fondo_annui[a]
        rend_netto = rend_lordo * (1 - aliq_rend_fondo)
        cap_fondo += rend_netto
        cap_fondo *= (1 - s["ter_f"])
        cap_fondo = max(0.0, cap_fondo - s["costo_fisso_f"])

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
        netto_fondo = cap_fondo * (1 - aliq_uscita)
        plusval_pac = max(0.0, cap_pac - versato_pac_cum)
        netto_pac = cap_pac - plusval_pac * tp
        netto_tfr = cap_tfr * (1 - tt)

        rows.append({
            "Anno": anno,
            "CCNL": s["ccnl"], "Livello": s["livello"], "Comparto": s["comparto"],
            "Occupato": "Sì" if occupato else "No",
            "RAL (€)": ral_curr,
            "Contrib. Min. CCNL (€)": vol_min,
            "Vers. Volontario (€)": (vol_extra if occupato else 0.0),
            "TFR al Fondo (€)": tfr_curr,
            "Contrib. Aziendale (€)": ca_curr,
            "Risparmio IRPEF (€)": risparmio_anno,
            "PAC annuo (€)": vp_curr,
            "Aliq. uscita fondo (%)": aliq_uscita * 100,
            "Fondo Netto (€)": netto_fondo,
            "PAC + TFR Netto (€)": netto_pac + netto_tfr,
            "PAC Netto (€)": netto_pac,
            "Fondo + PAC Netto (€)": netto_fondo + netto_pac,
        })
    return pd.DataFrame(rows)


def calcola_bande(fattori, rend_fondo_mat, rend_pac_mat, sched, scal, n_band=200):
    """
    Esegue il motore su n_band scenari di RENDIMENTO (carriera fissata alla
    mediana) e restituisce P10/P50/P90 anno-per-anno per ogni curva. È qui che
    nasce la banda GBM 10–90 richiesta su TUTTE le curve (Fondo, solo PAC,
    PAC+TFR, Fondo+PAC).
    """
    curve = ["Fondo Netto (€)", "PAC Netto (€)", "PAC + TFR Netto (€)", "Fondo + PAC Netto (€)"]
    acc = {c: [] for c in curve}
    m = min(n_band, rend_fondo_mat.shape[0], rend_pac_mat.shape[0])
    for i in range(m):
        d = simula_capitale(fattori, rend_fondo_mat[i], rend_pac_mat[i], sched, scal)
        for c in curve:
            acc[c].append(d[c].tolist())
    bande = {}
    for c in curve:
        arr = np.array(acc[c])
        bande[c] = {
            "p10": np.percentile(arr, 10, axis=0),
            "p50": np.percentile(arr, 50, axis=0),
            "p90": np.percentile(arr, 90, axis=0),
        }
    return bande


# ---------------------------------------------------------------------------
# ESECUZIONE
# ---------------------------------------------------------------------------
scatti_valore_annuo = anni_anzianita_pregressi * scatto_valore_livello * mensilita
base_contrib_iniziale = minimo_annuo + scatti_valore_annuo
superminimo_annuo = superminimo_mensile * mensilita
ral_auto = base_contrib_iniziale + superminimo_annuo + premio_produzione_annuo
ral_override = ral_manuale > 0
ral = ral_manuale if ral_override else ral_auto

coeff_totale = COEFF_LAVORATORE[tipo_lavoratore]
scenari = genera_scenari(profilo_crescita, coeff_totale, crescita_base, n=1000)

# --- Schedule anno-per-anno ---
sched = costruisci_schedule(
    durata, ccnl_scelto, livello, comparto, eta, anni_anzianita_pregressi,
    superminimo_annuo, premio_produzione_annuo, crescita_base,
    passaggi_livello if usa_passaggi_livello else [],
    cambi_ccnl if usa_cambio_ccnl else [],
    anni_disoccupato,
)

N_BAND = 200

# --- Traiettorie di rendimento del FONDO (per comparto, poi spliced) ---
# Ogni comparto attivo nello schedule genera una propria matrice (n x durata);
# la matrice finale prende, colonna per colonna (anno per anno), i rendimenti
# del comparto attivo in quell'anno. Così un cambio CCNL/comparto a metà
# carriera cambia davvero il motore di rendimento del fondo.
comparto_keys = sorted({s["comparto_key"] for s in sched})
avvisi_corti = []       # comparti con storico annuale troppo corto
mancanti = []           # comparti senza dati per il metodo scelto (GBM rimosso)
mat_per_comparto = {}
for ki, key in enumerate(comparto_keys):
    fondo_k, comp_k = key
    # seed decorrelato per comparto (evita traiettorie identiche tra comparti
    # in caso di cambio CCNL/comparto a metà carriera)
    if usa_mensile:
        if mensile_disponibile(fondo_k, comp_k):
            serie = tuple(STORICO_MENSILE[fondo_k][comp_k])
            mat_per_comparto[key] = genera_rendimenti_block_bootstrap(
                serie, durata, block=int(block_mesi), n=N_BAND, seed=33 + ki)
        else:
            mancanti.append(f"{fondo_k} · {comp_k} (serie mensile)")
    else:
        if annuale_disponibile(fondo_k, comp_k):
            serie = tuple(STORICO_ANNUALE[fondo_k][comp_k])
            if len(serie) < 8:
                avvisi_corti.append(f"{fondo_k} · {comp_k} ({len(serie)} anni)")
            mat_per_comparto[key] = genera_rendimenti_bootstrap(serie, durata, n=N_BAND, seed=21 + ki)
        else:
            mancanti.append(f"{fondo_k} · {comp_k} (serie annuale)")

if mancanti:
    st.error(
        "**Dati storici mancanti** per: " + ", ".join(mancanti) + ".\n\n"
        "Il GBM è stato rimosso dal fondo: i rendimenti provengono solo dal "
        "resampling dello storico reale. Popola `STORICO_MENSILE` / "
        "`STORICO_ANNUALE` per questi comparti (o scegli un CCNL/comparto già "
        "coperto, es. Cometa) per continuare."
    )
    st.stop()

rend_fondo_mat = np.empty((N_BAND, durata))
for a, s in enumerate(sched):
    rend_fondo_mat[:, a] = mat_per_comparto[s["comparto_key"]][:, a]

# --- PAC: GBM parametrico / portafoglio ticker ---
portafoglio_info = None
errore_portafoglio = None
if usa_portafoglio:
    if not tickers_input.strip():
        errore_portafoglio = "Nessun ticker selezionato: usa il catalogo o inseriscine uno."
        rend_pac_mat = genera_rendimenti_gbm(0.07, 0.15, durata, n=N_BAND, seed=11)
    else:
        try:
            tickers, pesi = parse_ticker_pesi(tickers_input, pesi_input)
            prezzi_df = scarica_prezzi_mensili(tuple(tickers), anni_storico)
            portafoglio_info = stima_parametri_portafoglio(prezzi_df, pesi)
            rend_override_eff = rend_override_val if override_rend else None
            rend_pac_mat = genera_rendimenti_portafoglio_gbm(
                portafoglio_info["media_mensile"], portafoglio_info["cholesky_mensile"],
                pesi, durata, rend_override=rend_override_eff, n=N_BAND, seed=13,
            )
        except Exception as e:
            errore_portafoglio = str(e)
            rend_pac_mat = genera_rendimenti_gbm(0.07, 0.15, durata, n=N_BAND, seed=11)
else:
    rend_pac_mat = genera_rendimenti_gbm(rend_medio_pac, vol_pac, durata, n=N_BAND, seed=11)

# --- Traiettorie centrali (per la tabella e la linea centrale) ---
rend_fondo_sel = seleziona_traiettoria_per_percentile(rend_fondo_mat, percentile_perf)
rend_pac_sel = seleziona_traiettoria_per_percentile(rend_pac_mat, percentile_perf)

# --- Parametri scalari (non variano con lo schedule) ---
scal = dict(
    ral_override=ral_override, ral_manuale=ral_manuale,
    vers_vol_extra=vers_vol_extra, vp=versamento_pac,
    ter_p=ter_pac, tp=tassa_uscita_pac, rt=rend_tfr, tt=tassa_tfr,
    anni_pregressi=anni_gia_iscritto, uscita_ordinaria=uscita_ordinaria,
    cap_iniziale_fondo=capitale_iniziale_fondo,
    cap_iniziale_pac=capitale_iniziale_pac,
)

fattori_mediani = [float(np.percentile([s[a] for s in scenari], 50)) for a in range(durata)]
df_main = simula_capitale(fattori_mediani, rend_fondo_sel, rend_pac_sel, sched, scal)

# --- Bande GBM P10–P90 su tutte le curve (carriera fissa alla mediana) ---
bande = calcola_bande(fattori_mediani, rend_fondo_mat, rend_pac_mat, sched, scal, n_band=N_BAND)
anni = list(range(1, durata + 1))


# ---------------------------------------------------------------------------
# INTESTAZIONE
# ---------------------------------------------------------------------------
motore_txt = (f"Block-bootstrap mensile (blocco {int(block_mesi)} mesi)"
              if usa_mensile else "Bootstrap annuale")
st.info(
    f"**Profilo:** {tipo_lavoratore} · {ccnl_scelto} · livello {livello} · comparto {comparto}  \n"
    f"Coefficiente crescita ×{coeff_totale:.2f} · crescita di base "
    f"{crescita_base*100:.1f}%/anno · rendimenti fondo: **{motore_txt}** (storico reale)  \n"
    f"Linea centrale **P{percentile_perf}** · banda **P10–P90** su tutte le curve "
    f"({N_BAND} scenari)  \n"
    f"*Valori nominali (includono l'inflazione, coerentemente con contributi e montante).*"
)

if (not usa_mensile) and avvisi_corti:
    st.caption(
        "ℹ️ Storico REALE ma corto (bootstrap fragile, poche osservazioni): "
        + ", ".join(avvisi_corti)
        + ". Con serie brevi la banda P10–P90 dipende da pochi anni; il block-"
          "bootstrap mensile (opzionale) sfrutterebbe più dati."
    )

if usa_cambio_ccnl and cambi_ccnl:
    st.caption(
        "🔁 **Cambi CCNL pianificati:** partenza da **" + ccnl_scelto + "** → "
        + " → ".join([f"anno {a}: **{c}** ({l}, {comp})" for a, c, l, comp in cambi_ccnl])
    )
if usa_disoccupazione and anni_disoccupato:
    st.caption(
        "⏸️ **Anni di disoccupazione:** "
        + ", ".join(str(x) for x in sorted(anni_disoccupato))
        + " — nessun contributo, i capitali continuano a rendere."
    )

# --- Composizione della RAL iniziale ---
st.subheader("🧱 Composizione della RAL (Anno 1)")
if ral_override:
    rc1, rc2, rc3 = st.columns(3)
    rc1.metric("RAL inserita a mano", f"€ {ral:,.0f}")
    rc2.metric("Base contributiva fondo", f"€ {base_contrib_iniziale:,.0f}")
    rc3.metric("RAL auto (confronto)", f"€ {ral_auto:,.0f}")
else:
    rc1, rc2, rc3, rc4 = st.columns(4)
    rc1.metric("Minimo tabellare", f"€ {minimo_annuo:,.0f}")
    rc2.metric("Scatti anzianità", f"€ {scatti_valore_annuo:,.0f}")
    rc3.metric("Superminimo + premio", f"€ {superminimo_annuo + premio_produzione_annuo:,.0f}")
    rc4.metric("RAL totale", f"€ {ral:,.0f}")

st.caption(
    f"Il contributo aziendale ({contrib_az_pct*100:.2f}%) e il tuo minimo "
    f"({preset['contrib_lav_pct']*100:.2f}%) si calcolano sulla base contributiva "
    f"(minimi + scatti), non su superminimo/premio. Il TFR "
    f"({preset['tfr_pct']*100:.2f}%) è sull'intera retribuzione."
)
st.divider()


# ---------------------------------------------------------------------------
# SEZIONE COSTI DEL FONDO
# ---------------------------------------------------------------------------
st.subheader(f"💰 Struttura dei Costi — {preset['fondo']} ({comparto})")
cc1, cc2, cc3, cc4 = st.columns(4)
cc1.metric("Costo iniziale (una tantum)", f"€ {preset['costo_iniziale']:,.2f}")
cc2.metric("Costo fisso annuo", f"€ {preset['costo_fisso']:,.0f}")
cc3.metric("TER (gestione annua)", f"{ter_fondo*100:.2f}%")
aliq_rend = 0.20 * (1 - quota_ts) + 0.125 * quota_ts
cc4.metric("Tassa sui rendimenti/anno", f"{aliq_rend*100:.1f}%")

cap_medio = df_main["Fondo Netto (€)"].mean()
ter_totale_stimato = ter_fondo * cap_medio * durata
costo_fisso_totale = preset["costo_fisso"] * durata + preset["costo_iniziale"]

with st.expander("📖 Come leggere i costi del fondo"):
    st.markdown(f"""
Il fondo pensione ha **quattro tipi di costo**, tutti inclusi nella simulazione:

1. **Costo iniziale** — €{preset['costo_iniziale']:.2f} una tantum all'iscrizione.
2. **Costo fisso annuo** — €{preset['costo_fisso']:.0f}/anno. Su {durata} anni: ~€{costo_fisso_totale:,.0f}.
3. **TER** — {ter_fondo*100:.2f}%/anno del comparto *{comparto}*; è il costo che pesa
   di più nel lungo periodo (stima ~€{ter_totale_stimato:,.0f} sull'orizzonte).
4. **Tassa sui rendimenti** — 20% ordinario, 12,5% sulla quota in titoli di Stato;
   aliquota effettiva **{aliq_rend*100:.1f}%** per *{comparto}*.
""")
st.divider()


# ---------------------------------------------------------------------------
# RENDIMENTO NETTO PER ANNO DEL COMPARTO SCELTO
# ---------------------------------------------------------------------------
st.subheader(f"📗 Rendimento netto per anno — {comparto} ({preset['fondo']})")
st.caption("Netto = dopo tassa 20%/12,5% sui rendimenti e TER del comparto, "
           "coerente col motore del montante. A sinistra lo storico reale, a "
           "destra la previsione dal resampling.")

ANNO_FINE_STORICO = 2025  # tutte le serie quote arrivano a fine 2025
fondo_sel = preset["fondo"]
serie_ann_sel = STORICO_ANNUALE.get(fondo_sel, {}).get(comparto, [])

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("**Storico reale (anno per anno)**")
    if serie_ann_sel:
        anni_lbl = list(range(ANNO_FINE_STORICO - len(serie_ann_sel) + 1, ANNO_FINE_STORICO + 1))
        netti_sel = rendimento_netto_comparto(serie_ann_sel, ter_fondo, quota_ts)
        df_stor = pd.DataFrame({
            "Anno": anni_lbl,
            "Lordo (%)": [r * 100 for r in serie_ann_sel],
            "Netto (%)": [float(r) * 100 for r in netti_sel],
        })
        st.dataframe(
            df_stor.style.format({"Lordo (%)": "{:+.2f}", "Netto (%)": "{:+.2f}"}),
            use_container_width=True, hide_index=True, height=300,
        )
        cagr_l = float(np.prod([1 + r for r in serie_ann_sel])) ** (1 / len(serie_ann_sel)) - 1
        cagr_n = float(np.prod([1 + float(r) for r in netti_sel])) ** (1 / len(netti_sel)) - 1
        s1, s2, s3 = st.columns(3)
        s1.metric("CAGR lordo", f"{cagr_l*100:.2f}%")
        s2.metric("CAGR netto", f"{cagr_n*100:.2f}%")
        s3.metric("Peggiore (netto)", f"{min(netti_sel)*100:+.1f}%")
        if len(serie_ann_sel) < 8:
            st.caption(f"⚠️ Solo {len(serie_ann_sel)} anni disponibili: statistiche indicative.")
    else:
        st.info("Storico annuale non disponibile per questo comparto.")

with col_b:
    st.markdown(f"**Previsione resampling** ({motore_txt})")
    key_sel = (fondo_sel, comparto)
    if key_sel in mat_per_comparto:
        net_mat = rendimento_netto_comparto(mat_per_comparto[key_sel], ter_fondo, quota_ts)
        df_prev = pd.DataFrame({
            "Anno": list(range(1, durata + 1)),
            "P10 netto (%)": np.percentile(net_mat, 10, axis=0) * 100,
            "P50 netto (%)": np.percentile(net_mat, 50, axis=0) * 100,
            "P90 netto (%)": np.percentile(net_mat, 90, axis=0) * 100,
        })
        st.dataframe(
            df_prev.style.format({c: "{:+.2f}" for c in df_prev.columns if c != "Anno"}),
            use_container_width=True, hide_index=True, height=300,
        )
        st.caption(f"Rendimento netto annuo mediano simulato: "
                   f"**{np.median(net_mat)*100:+.2f}%** (su tutti anni e scenari).")
    else:
        st.info("Comparto non attivo all'anno 1 (cambio CCNL immediato?).")

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
tc2.metric("Aliquota uscita applicata", f"{aliq_uscita_finale*100:.1f}%")
irpef_equiv = aliquota_marginale(df_main["RAL (€)"].iloc[-1]) * 100
tc3.metric("IRPEF ordinaria (confronto)", f"{irpef_equiv:.0f}%")

if uscita_ordinaria:
    st.warning(
        f"Riscatto/anticipazione ordinaria: ritenuta **23%**. Con uscita agevolata "
        f"pagheresti **{aliq_agevolata*100:.1f}%** — differenza di circa "
        f"**€ {df_main['Fondo Netto (€)'].iloc[-1] * (0.23 - aliq_agevolata) / (1 - 0.23):,.0f}** "
        f"sul montante finale netto."
    )
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
m1.metric("Costo netto fondo/mese", f"€ {costo_netto_fondo_anno1/mensilita:,.0f}")
m2.metric("Costo PAC/mese", f"€ {versamento_pac/mensilita:,.0f}")
m3.metric("Totale investito/mese", f"€ {(costo_netto_fondo_anno1 + versamento_pac)/mensilita:,.0f}")
m4.metric("Contributo azienda (gratis)/anno", f"€ {ca_anno1:,.0f}")
st.divider()


# ---------------------------------------------------------------------------
# SEZIONE PORTAFOGLIO A TICKER (se attivo)
# ---------------------------------------------------------------------------
if usa_portafoglio:
    st.subheader("📈 Portafoglio PAC a Ticker")
    if not tickers_input.strip():
        st.warning("Nessun ticker selezionato. Uso GBM di fallback (7% / 15%).")
    elif errore_portafoglio:
        st.error(f"Impossibile scaricare/stimare il portafoglio: {errore_portafoglio}. "
                 f"Uso GBM di fallback (7% / 15%).")
    else:
        pi = portafoglio_info
        # Ricontrollo accumulazione/UCITS sui ticker effettivamente usati
        note_acc = []
        for t in pi["tickers"]:
            stato, nota = classifica_ticker(t)
            if stato != "ok":
                note_acc.append(f"{'⚠️' if stato=='warn' else '❓'} **{t}** — {nota}")
        if note_acc:
            st.warning("Verifica accumulazione/UCITS:\n\n" + "\n\n".join(note_acc))

        pc1, pc2, pc3 = st.columns(3)
        pc1.metric("Rendimento storico annuo (composto)", f"{pi['rend_portafoglio']*100:.2f}%")
        pc2.metric("Volatilità storica annua", f"{pi['vol_portafoglio']*100:.2f}%")
        pc3.metric("Asset nel portafoglio", f"{len(pi['tickers'])}")

        if override_rend:
            st.info(f"Rendimento atteso corretto a mano a {rend_override_val*100:.1f}% "
                    f"(volatilità/correlazioni restano storiche).")

        nomi_leggibili = [TICKER_TO_NOME.get(t, t) for t in pi["tickers"]]
        df_asset = pd.DataFrame({
            "Nome": nomi_leggibili, "Ticker": pi["tickers"],
            "Peso (%)": (pesi * 100).round(1),
            "Rend. annuo storico (%)": (pi["rend_annuo_asset"] * 100).round(2),
            "Volatilità annua (%)": (pi["vol_annua_asset"] * 100).round(2),
        })
        st.dataframe(df_asset, use_container_width=True, hide_index=True)

        with st.expander("🔗 Matrice di correlazione (sui rendimenti mensili)"):
            df_corr = pd.DataFrame(pi["corr"], index=pi["tickers"], columns=pi["tickers"])
            st.dataframe(df_corr, use_container_width=True)

        st.caption("⚠️ Volatilità/correlazioni storiche sono stime ragionevoli; il "
                   "rendimento medio storico molto meno. Meglio correggerlo a mano.")
    st.divider()


# ---------------------------------------------------------------------------
# KPI + GRAFICO
# ---------------------------------------------------------------------------
st.subheader(f"📊 Andamento Capitale Netto — linea P{percentile_perf} · banda P10–P90")
st.caption("Linea = percentile scelto (carriera mediana). Banda = P10–P90 sulla "
           "variabilità dei RENDIMENTI ({} scenari).".format(N_BAND))

last = df_main.iloc[-1]
b_fondo = bande["Fondo Netto (€)"]
b_pac = bande["PAC Netto (€)"]
b_pactfr = bande["PAC + TFR Netto (€)"]
b_fpac = bande["Fondo + PAC Netto (€)"]

cols = st.columns(4 if usa_entrambi else 3)
cols[0].metric("Fondo Netto", f"€ {last['Fondo Netto (€)']:,.0f}",
               help=f"P10: € {b_fondo['p10'][-1]:,.0f} — P90: € {b_fondo['p90'][-1]:,.0f}")
cols[1].metric("PAC + TFR Netto", f"€ {last['PAC + TFR Netto (€)']:,.0f}",
               help=f"P10: € {b_pactfr['p10'][-1]:,.0f} — P90: € {b_pactfr['p90'][-1]:,.0f}")
cols[2].metric("RAL Finale", f"€ {last['RAL (€)']:,.0f}",
               help=f"× {last['RAL (€)']/ral:.2f} vs partenza" if ral else "")
if usa_entrambi:
    cols[3].metric("Fondo + PAC (senza TFR)", f"€ {last['Fondo + PAC Netto (€)']:,.0f}",
                   help=f"P10: € {b_fpac['p10'][-1]:,.0f} — P90: € {b_fpac['p90'][-1]:,.0f}")

fig = go.Figure()

def aggiungi_banda(b, colore_fill, nome):
    fig.add_trace(go.Scatter(
        x=anni + anni[::-1],
        y=list(b["p90"]) + list(b["p10"])[::-1],
        fill="toself", fillcolor=colore_fill,
        line=dict(color="rgba(0,0,0,0)"), name=nome, hoverinfo="skip",
        showlegend=True,
    ))

# Bande P10–P90 su tutte le curve principali
aggiungi_banda(b_fondo,  "rgba(42,120,214,0.12)", "Fondo P10–P90")
aggiungi_banda(b_pactfr, "rgba(27,175,122,0.12)", "PAC+TFR P10–P90")
aggiungi_banda(b_pac,    "rgba(155,89,182,0.10)", "Solo PAC P10–P90")
if usa_entrambi:
    aggiungi_banda(b_fpac, "rgba(237,161,0,0.10)", "Fondo+PAC P10–P90")

# Linee centrali (percentile scelto)
fig.add_trace(go.Scatter(x=anni, y=df_main["Fondo Netto (€)"], name="Fondo Pensione",
                         line=dict(color="#2a78d6", width=3)))
fig.add_trace(go.Scatter(x=anni, y=df_main["PAC + TFR Netto (€)"], name="PAC + TFR",
                         line=dict(color="#1baf7a", width=3)))
fig.add_trace(go.Scatter(x=anni, y=df_main["PAC Netto (€)"], name="Solo PAC",
                         line=dict(color="#9b59b6", width=2, dash="dash")))
if usa_entrambi:
    fig.add_trace(go.Scatter(x=anni, y=df_main["Fondo + PAC Netto (€)"],
                             name="Fondo + PAC (senza TFR)",
                             line=dict(color="#eda100", width=3, dash="dot")))

fig.update_layout(xaxis_title="Anno", yaxis_title="Capitale Netto (€)",
                  yaxis_tickformat="€,.0f", hovermode="x unified",
                  legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                  height=460)
st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# TABELLA ANNO PER ANNO
# ---------------------------------------------------------------------------
st.subheader("📋 Dettaglio Anno per Anno")
st.caption("Montanti = linea centrale P{}. Contributi e RAL crescono con carriera/inflazione.".format(percentile_perf))

cols_show = ["Anno", "CCNL", "Livello", "Comparto", "Occupato", "RAL (€)",
             "Contrib. Min. CCNL (€)", "Vers. Volontario (€)", "TFR al Fondo (€)",
             "Contrib. Aziendale (€)", "Risparmio IRPEF (€)", "PAC annuo (€)",
             "Aliq. uscita fondo (%)", "Fondo Netto (€)", "PAC + TFR Netto (€)", "PAC Netto (€)"]
if usa_entrambi:
    cols_show.append("Fondo + PAC Netto (€)")

fmt = {c: "€ {:,.0f}" for c in cols_show
       if c not in ("Anno", "CCNL", "Livello", "Comparto", "Occupato", "Aliq. uscita fondo (%)")}
fmt["Aliq. uscita fondo (%)"] = "{:.1f}%"
st.dataframe(df_main[cols_show].style.format(fmt), use_container_width=True, height=420)

st.caption(
    "⚠️ Stima illustrativa. Crescita salariale su dati ISTAT; contributi CCNL "
    "Cometa/Fon.Te; costi/comparti da schede COVIP; rendimenti simulati con GBM o "
    "bootstrap storico. La banda P10–P90 riflette l'incertezza dei rendimenti, non "
    "quella di carriera. Non è consulenza finanziaria o previdenziale."
)
