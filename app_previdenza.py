import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os
import csv
import json

# ---------------------------------------------------------------------------
# CONFIGURAZIONE PAGINA
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Simulatore Previdenziale Pro", layout="wide")
st.title("🚀 Confronto Previdenziale: Fondo vs PAC + TFR")

# --- Gestione del Seed per ricalcolo casuale ---
if "master_seed" not in st.session_state:
    st.session_state.master_seed = 33

# ---------------------------------------------------------------------------
# DATI CCNL / FONDI NEGOZIALI — un file JSON per CCNL (data/ccnl/)
# ---------------------------------------------------------------------------
# Ogni CCNL/fondo negoziale vive in un proprio file JSON sotto data/ccnl/.
# Aggiungere un nuovo CCNL = copiare data/ccnl/_template.json, compilarlo e
# salvarlo con un nuovo nome: NON serve toccare questo script. I file che
# iniziano con "_" (come _template.json) vengono ignorati dal loader.
#
# Schema di ciascun file (vedi _template.json per la versione commentata):
#   nome, fondo, contrib_lav_pct, contrib_azienda_pct, contrib_azienda_u35_pct,
#   tfr_pct, costo_iniziale, costo_fisso, mensilita, livelli {},
#   scatti_valore_livello {}, scatto_ogni_anni,
#   scatti_max, comparti [lista di nomi]
#
# IMPORTANTE:
# - "fondo" deve combaciare col nome del CSV storico in data/<fondo>.csv
#   (es. fondo="Cometa" -> data/cometa.csv), altrimenti il resampling
#   storico non trova le serie.
# - I nomi in "comparti" devono combaciare ESATTAMENTE con le colonne del
#   CSV storico di quel fondo. Il rendimento non è un parametro qui: il
#   motore usa SEMPRE lo storico reale della quota (ricampionato dal CSV),
#   mai un'assunzione parametrica.
CARTELLA_CCNL_CANDIDATE = [
    "data/ccnl",
    "ccnl",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ccnl"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "ccnl"),
]

def _trova_cartella_ccnl():
    for cartella in CARTELLA_CCNL_CANDIDATE:
        if os.path.isdir(cartella):
            return cartella
    return None

@st.cache_data
def carica_ccnl_preset():
    """
    Legge tutti i *.json in data/ccnl/ (esclusi quelli che iniziano con "_",
    come _template.json) e costruisce il dizionario CCNL_PRESET.

    preset["comparti"] è una semplice LISTA di nomi comparto (es. ["Garantito",
    "Bilanciato", "Azionario"]). Il rendimento non è più un parametro del
    CCNL: il motore usa sempre il rendimento storico reale della quota
    (ricampionato da data/<fondo>.csv), quindi qui basta sapere quali nomi di
    comparto esistono e devono combaciare con le colonne di quel CSV.

    Ritorna (preset_dict, cartella_usata, errori). errori è una lista di
    messaggi per file malformati o campi mancanti (il file viene saltato,
    non blocca gli altri).
    """
    cartella = _trova_cartella_ccnl()
    if cartella is None:
        return {}, None, []

    campi_obbligatori = [
        "nome", "fondo", "contrib_lav_pct", "contrib_azienda_pct",
        "contrib_azienda_u35_pct", "tfr_pct", "costo_iniziale", "costo_fisso",
        "mensilita", "livelli", "scatto_ogni_anni", "scatti_max", "comparti",
    ]

    preset, errori = {}, []
    for fname in sorted(os.listdir(cartella)):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        fpath = os.path.join(cartella, fname)
        try:
            with open(fpath, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except Exception as e:
            errori.append(f"{fname}: JSON non valido ({e})")
            continue

        mancanti = [c for c in campi_obbligatori if c not in cfg]
        if mancanti:
            errori.append(f"{fname}: campi mancanti {mancanti}")
            continue

        comparti_raw = cfg["comparti"]
        if isinstance(comparti_raw, dict):
            # Compatibilità con il vecchio schema (dict di parametri per
            # comparto): basta il nome, i parametri numerici sono ignorati.
            lista_comparti = list(comparti_raw.keys())
        elif isinstance(comparti_raw, list):
            lista_comparti = list(comparti_raw)
        else:
            errori.append(f"{fname}: 'comparti' deve essere una lista di nomi")
            continue
        if not lista_comparti:
            errori.append(f"{fname}: 'comparti' è vuoto")
            continue

        nome = cfg["nome"]
        scatti_liv = cfg.get("scatti_valore_livello", {})
        livelli_senza_scatto = [l for l in cfg["livelli"] if l not in scatti_liv]
        if livelli_senza_scatto:
            errori.append(
                f"{fname}: livelli senza scatto specifico: {livelli_senza_scatto}. "
                f"Aggiungi tutti i livelli in 'scatti_valore_livello'."
            )
            continue

        preset[nome] = {
            "fondo": cfg["fondo"],
            "contrib_lav_pct": cfg["contrib_lav_pct"],
            "contrib_azienda_pct": cfg["contrib_azienda_pct"],
            "contrib_azienda_u35_pct": cfg["contrib_azienda_u35_pct"],
            "tfr_pct": cfg["tfr_pct"],
            "costo_iniziale": cfg["costo_iniziale"],
            "costo_fisso": cfg["costo_fisso"],
            "mensilita": cfg["mensilita"],
            "livelli": cfg["livelli"],
            "scatti_valore_livello": scatti_liv,
            "scatto_ogni_anni": cfg["scatto_ogni_anni"],
            "scatti_max": cfg["scatti_max"],
            "comparti": lista_comparti,
        }

    return preset, cartella, errori

CCNL_PRESET, _CARTELLA_CCNL, _ERRORI_CCNL = carica_ccnl_preset()

if not CCNL_PRESET:
    st.error(
        "**Nessun preset CCNL trovato.** Cercato in: "
        + ", ".join(f"`{c}`" for c in CARTELLA_CCNL_CANDIDATE) +
        ". Metti almeno un file .json (vedi data/ccnl/_template.json) nella "
        "cartella data/ccnl/ accanto allo script e ricarica la pagina."
    )
    st.stop()

if _ERRORI_CCNL:
    st.warning(
        "⚠️ Alcuni file CCNL in `" + str(_CARTELLA_CCNL) + "` sono stati "
        "ignorati per errori:\n\n" + "\n\n".join(f"- {e}" for e in _ERRORI_CCNL)
    )


# ---------------------------------------------------------------------------
# STORICO RENDIMENTI DEI COMPARTI — un CSV per fondo (data/)
# ---------------------------------------------------------------------------
# Un file per fondo, un comparto per colonna: facile da aprire, aggiornare
# (nuova riga in fondo con le quote del mese) e versionare in git. Formato:
#
#   anno,mese,Garantito,Bilanciato,Azionario,Monetario     <- data/cometa.csv
#   2025,12,10.446,21.686,25.686,15.276
#
#   anno,mese,Conservativo,Sviluppo,Dinamico,Crescita      <- data/fonte.csv
#   2025,12,13.408,21.945,24.976,20.301
#
# Celle vuote sono ammesse (comparto nato più tardi): quel mese viene ignorato
# per quel comparto. Fondo nuovo = nuovo CSV + una riga in FILE_STORICO_PER_FONDO.
FILE_STORICO_PER_FONDO = {
    "Cometa": "cometa.csv",
    "Fon.Te": "fonte.csv",
}
CARTELLE_DATI_CANDIDATE = [
    "data",
    ".",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
    os.path.dirname(os.path.abspath(__file__)),
]

def _trova_file_fondo(nome_file: str):
    for cartella in CARTELLE_DATI_CANDIDATE:
        candidato = os.path.join(cartella, nome_file)
        if os.path.isfile(candidato):
            return candidato
    return None

@st.cache_data
def carica_quote_storiche():
    """
    Legge un CSV largo per fondo (anno, mese, <comparto1>, <comparto2>, ...) e
    lo trasforma in strutture calcolate a runtime (nessun dato hard-coded):
    - STORICO_MENSILE[fondo][comparto] -> rendimenti mensili (ordine cronologico)
    - STORICO_ANNUALE[fondo][comparto] -> rendimenti annui Dic->Dic
    - STORICO_MENSILE_ANNI / STORICO_ANNUALE_ANNI: stesse chiavi, con l'ANNO
      corrispondente a ciascuna osservazione (stessa lunghezza, stesso ordine).
      Servono per poter tagliare lo storico da un anno di inizio scelto
      dall'utente (es. per escludere il rimbalzo post-2008), mantenendo
      l'allineamento tra rendimento e anno.

    Ritorna (mensile, annuale, mensile_anni, annuale_anni, percorsi_trovati, fondi_mancanti).
    """
    mensile, annuale = {}, {}
    mensile_anni, annuale_anni = {}, {}
    percorsi_trovati, fondi_mancanti = {}, []

    for fondo, nome_file in FILE_STORICO_PER_FONDO.items():
        percorso = _trova_file_fondo(nome_file)
        if percorso is None:
            fondi_mancanti.append((fondo, nome_file))
            continue
        percorsi_trovati[fondo] = percorso

        with open(percorso, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            comparti = [c for c in reader.fieldnames if c not in ("anno", "mese")]
            quote = {c: {} for c in comparti}
            for row in reader:
                anno = int(row["anno"]); mese = int(row["mese"])
                for c in comparti:
                    v = (row.get(c) or "").strip()
                    if v != "":
                        quote[c][(anno, mese)] = float(v)

        for comp, serie in quote.items():
            if len(serie) < 2:
                continue
            chiavi = sorted(serie)
            rend_m = [round(serie[chiavi[i]] / serie[chiavi[i-1]] - 1, 6)
                      for i in range(1, len(chiavi))]
            mensile.setdefault(fondo, {})[comp] = rend_m
            # anno del mese di ARRIVO di ciascun rendimento mensile
            mensile_anni.setdefault(fondo, {})[comp] = [chiavi[i][0] for i in range(1, len(chiavi))]

            anni_dic = sorted({y for (y, m) in serie if m == 12})
            rend_a, anni_lista = [], []
            for y in anni_dic:
                if (y, 12) in serie and (y - 1, 12) in serie:
                    rend_a.append(round(serie[(y, 12)] / serie[(y - 1, 12)] - 1, 5))
                    anni_lista.append(y)
            annuale.setdefault(fondo, {})[comp] = rend_a
            annuale_anni.setdefault(fondo, {})[comp] = anni_lista

    return mensile, annuale, mensile_anni, annuale_anni, percorsi_trovati, fondi_mancanti

(STORICO_MENSILE, STORICO_ANNUALE, STORICO_MENSILE_ANNI, STORICO_ANNUALE_ANNI,
 _PERCORSI_TROVATI, _FONDI_MANCANTI) = carica_quote_storiche()

if _FONDI_MANCANTI:
    dettagli = "\n".join(
        f"- **{fondo}**: cercato `{nome_file}` in `data/` e nella cartella dello script"
        for fondo, nome_file in _FONDI_MANCANTI
    )
    st.error(
        "**File dati storici mancanti per uno o più fondi:**\n\n" + dettagli +
        "\n\nMetti i CSV (`cometa.csv`, `fonte.csv`) in una cartella `data/` "
        "accanto allo script e ricarica la pagina."
    )
    st.stop()

def mensile_disponibile(fondo: str, comparto: str, min_mesi: int = 24) -> bool:
    serie = STORICO_MENSILE.get(fondo, {}).get(comparto, [])
    return len(serie) >= min_mesi


def filtra_storico_da_anno(serie: list, anni: list, anno_inizio: int) -> list:
    """
    Mantiene solo le osservazioni di `serie` con anno >= anno_inizio, usando
    `anni` (stessa lunghezza) come etichetta di riferimento. Usata per
    mitigare il bias da "punto di partenza" nelle serie storiche brevi (es.
    un fondo nato subito prima di una crisi mostra un primo rimbalzo enorme
    che gonfia il CAGR se lo storico usato parte da lì). Se anno_inizio è
    <= al primo anno disponibile, la serie non viene toccata.
    """
    if not serie:
        return serie
    return [r for r, y in zip(serie, anni) if y >= anno_inizio]


# Limiti globali per lo slider "anno di inizio storico": min = l'anno più
# vecchio disponibile in assoluto tra tutti i fondi/comparti caricati; max =
# lasciamo margine di almeno 5 anni all'ultima serie più corta, per evitare
# di azzerare per errore lo storico di un comparto.
_anni_min_per_serie = [min(anni) for fo in STORICO_ANNUALE_ANNI.values() for anni in fo.values() if anni]
_anni_max_per_serie = [max(anni) for fo in STORICO_ANNUALE_ANNI.values() for anni in fo.values() if anni]
ANNO_STORICO_MIN_GLOBALE = min(_anni_min_per_serie) if _anni_min_per_serie else 2000
ANNO_STORICO_MAX_GLOBALE = (max(_anni_max_per_serie) - 5) if _anni_max_per_serie else 2020

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

# ---------------------------------------------------------------------------
# QUOTA "TITOLI DI STATO/WHITE LIST" PER TICKER (tassazione PAC differenziata)
# ---------------------------------------------------------------------------
# In Italia i proventi/plusvalenze di fondi e ETF armonizzati godono di
# un'aliquota ridotta al 12,5% sulla quota "riferibile" a titoli di Stato
# italiani e di paesi white list, invece del 26% ordinario (D.L. 351/2001 e
# successive interpretazioni). La percentuale ESATTA va però certificata
# periodicamente dall'emittente del fondo (di norma nella documentazione
# fiscale annuale, non ricavabile in modo affidabile dai soli prezzi Yahoo).
# Questa mappa fornisce SOLO una stima grezza (0-1) per i pochi ticker del
# catalogo dove la composizione è inequivocabile (es. un fondo di soli titoli
# di Stato = 1.0). Per fondi obbligazionari misti (governativi+corporate) o
# ticker manuali, la quota va impostata a mano dall'utente: non è stimabile
# con sicurezza qui. Azionario, oro, REIT = 0 (nessuna componente governativa).
QUOTA_TITOLI_STATO_TICKER = {
    "XG7S.MI": 1.00,   # Xtrackers Global Government Bond: solo titoli di Stato
    # AGGH.MI (Global Aggregate Bond) è MISTO governativo+corporate+cartolarizzato:
    # non assegno una quota automatica, va impostata a mano se lo usi.
}

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
    return "sconosciuto", ("non in whitelist: può essere un ETF non catalogato "
                           "o un'AZIONE SINGOLA. Le azioni singole sono ammesse "
                           "ma hanno volatilità molto più alta di un ETF "
                           "diversificato e possono compromettere l'analisi "
                           "(la stima storica di rendimento/rischio su un solo "
                           "titolo è poco affidabile). Se è un ETF, verifica "
                           "sul KID che sia ad accumulazione e UCITS.")

# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
st.sidebar.header("1. Contratto e Inquadramento")
ccnl_scelto = st.sidebar.selectbox("CCNL", list(CCNL_PRESET.keys()), index=0)
preset = CCNL_PRESET[ccnl_scelto]
mensilita = preset["mensilita"]
st.sidebar.caption(f"Fondo negoziale associato: **{preset['fondo']}**")

livello = st.sidebar.selectbox("Livello di inquadramento", list(preset["livelli"].keys()))
minimo_mensile = preset["livelli"][livello]
minimo_annuo = minimo_mensile * mensilita

scatto_valore_livello = preset["scatti_valore_livello"][livello]
comparti_base = list(preset["comparti"])

st.sidebar.caption(
    f"Minimo tabellare **{livello}**: {minimo_mensile:,.0f} €/mese × {mensilita} "
    f"mensilità = **{minimo_annuo:,.0f} €/anno**"
)
# --- Pulsante Ricalcolo ---
if st.sidebar.button("🎲 Ricalcola Scenari Casuali"):
    st.session_state.master_seed = int(np.random.randint(0, 100000))
    
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
        _cn = list(preset_new["comparti"])
        comp_new = st.sidebar.selectbox(
            f"Cambio #{i+1} — comparto", _cn,
            index=_cn.index("Azionario") if "Azionario" in _cn else len(_cn) - 1,
            key=f"comp_ccnl_{i}",
        )
        cambi_ccnl.append((int(anno_c), ccnl_new, liv_new, comp_new))
    cambi_ccnl.sort(key=lambda x: x[0])

    st.sidebar.markdown("**Contributi del datore al cambio fondo**")
    mantieni_contributi_azienda = st.sidebar.checkbox(
        "Mantieni nel nuovo fondo i contributi già versati dal VECCHIO datore",
        value=True,
        help="⚠️ Punto normativo NON del tutto pacifico. La posizione "
             "individuale nei fondi pensione negoziali è in linea generale "
             "portabile (TFR + contributi lavoratore + contributi azienda "
             "seguono il lavoratore), ma la legge lascia margini di "
             "interpretazione su casi specifici legati al cambio di fondo di "
             "categoria. Attiva questa casella per simulare lo scenario in "
             "cui l'intero montante (compresa la quota versata dal datore) "
             "si trasferisce col cambio di lavoro/CCNL; disattivala per "
             "simulare lo scenario prudenziale in cui SOLO la quota versata "
             "dal datore resta 'congelata' nel vecchio fondo/non si trasferisce "
             "(TFR e contributi tuoi restano comunque tuoi in entrambi i casi). "
             "Non sono un consulente legale: verifica sempre lo statuto del "
             "fondo specifico.",
    )
else:
    mantieni_contributi_azienda = True  # nessun cambio CCNL pianificato: irrilevante

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

under35 = eta < 35
contrib_az_pct = preset["contrib_azienda_u35_pct"] if under35 else preset["contrib_azienda_pct"]

st.sidebar.caption(
    f"**{preset['fondo']} · {comparto}** — datore {contrib_az_pct*100:.2f}% "
    f"(sui minimi+scatti) · tu min {preset['contrib_lav_pct']*100:.2f}% · "
    f"TFR {preset['tfr_pct']*100:.2f}%. Il rendimento del comparto viene dallo "
    f"storico reale della quota (già netto di tasse e costi di gestione), non "
    f"da un'assunzione parametrica."
)

vers_vol_extra = st.sidebar.number_input(
    "Versamento volontario AGGIUNTIVO annuo (€)", min_value=0, value=1000, step=100,
    help="Oltre al contributo minimo previsto dal CCNL. Deducibile dall'IRPEF. "
         "Resta FISSO nel tempo a meno di variazioni pianificate qui sotto.",
)
usa_variazioni_vol_extra = st.sidebar.checkbox(
    "Pianifica variazioni di questo versamento nel tempo", value=False,
    key="usa_var_vol_extra",
    help="Es.: dall'anno 6 alzi a 1500€, dall'anno 12 abbassi a 800€. Tra una "
         "variazione e l'altra l'importo resta fisso (nessuno scaling con la carriera).",
)
variazioni_vol_extra = []
if usa_variazioni_vol_extra:
    n_var_ve = st.sidebar.number_input(
        "Numero di variazioni", min_value=1, max_value=10, value=1, step=1,
        key="n_var_vol_extra",
    )
    for i in range(int(n_var_ve)):
        vc1, vc2 = st.sidebar.columns(2)
        anno_v = vc1.number_input(
            f"Var. #{i+1} — dall'anno", min_value=1, max_value=40,
            value=min(6 * (i + 1), 40), step=1, key=f"anno_var_ve_{i}",
        )
        importo_v = vc2.number_input(
            f"Var. #{i+1} — nuovo importo (€/anno)", min_value=0,
            value=1000, step=100, key=f"importo_var_ve_{i}",
        )
        variazioni_vol_extra.append((int(anno_v), float(importo_v)))

st.sidebar.header("4. Performance simulata (Fondo)")
st.sidebar.caption(
    "I rendimenti del fondo vengono SEMPRE dal ricampionamento (block-"
    "bootstrap) dello storico mensile reale della quota del comparto — mai "
    "da un'assunzione parametrica. Usa tutti i mesi disponibili (non solo i "
    "rendimenti di fine anno), il che dà stime più solide anche per i "
    "comparti con storico breve."
)
usa_mensile = True  # unico metodo disponibile: block-bootstrap mensile
block_mesi = st.sidebar.number_input(
    "Lunghezza blocco (mesi)", min_value=3, max_value=24, value=12, step=1,
    help="Dimensione del blocco contiguo ricampionato dallo storico mensile "
         "reale. 12 = un anno intero (preserva stagionalità e sequenze "
         "annuali); valori più piccoli mescolano più liberamente i mesi.",
)

st.sidebar.markdown("**Orizzonte storico usato per il resampling**")
anno_inizio_storico = st.sidebar.slider(
    "Escludi gli anni precedenti a...", ANNO_STORICO_MIN_GLOBALE, ANNO_STORICO_MAX_GLOBALE,
    ANNO_STORICO_MIN_GLOBALE, 1,
    help="Taglia via dallo storico usato per il resampling tutti gli anni "
         "precedenti a quello scelto. Utile per mitigare il bias da 'punto di "
         "partenza': un comparto nato subito prima di una crisi (es. 2008) "
         "mostra spesso un primo rimbalzo enorme che gonfia il rendimento "
         "medio storico se lo si include. Il valore di default (il più "
         "vecchio disponibile) NON esclude nulla, cioè usa tutta la storia "
         "disponibile per ciascun comparto, come comportamento originale. "
         "Se un comparto parte già dopo l'anno scelto, resta invariato.",
)
if anno_inizio_storico > ANNO_STORICO_MIN_GLOBALE:
    st.sidebar.caption(
        f"ℹ️ Storico troncato: verranno usate solo le osservazioni dal "
        f"{anno_inizio_storico} in poi, per ogni comparto che ha dati "
        f"precedenti a quell'anno."
    )

st.sidebar.caption("Banda P10–P90 mostrata su tutte le curve (200 scenari).")
percentile_perf = st.sidebar.slider(
    "Percentile della linea centrale", 5, 95, 50, 5,
    help="P5 = scenario molto sfortunato · P50 = mediano · P95 = molto fortunato. "
         "La banda P10–P90 attorno resta sempre visibile.",
)

st.sidebar.header("5. PAC (ETF)")
versamento_pac = st.sidebar.number_input(
    "Versamento PAC Annuo (€)", min_value=0, value=3445, step=100,
    help="Resta FISSO nel tempo (nessuno scaling con la carriera) a meno di "
         "variazioni pianificate qui sotto.",
)
usa_variazioni_pac = st.sidebar.checkbox(
    "Pianifica variazioni del versamento PAC nel tempo", value=False,
    key="usa_var_pac",
    help="Es.: dall'anno 6 alzi a 5000€, dall'anno 12 abbassi a 2000€. Tra una "
         "variazione e l'altra l'importo resta fisso.",
)
variazioni_pac = []
if usa_variazioni_pac:
    n_var_pac = st.sidebar.number_input(
        "Numero di variazioni", min_value=1, max_value=10, value=1, step=1,
        key="n_var_pac",
    )
    for i in range(int(n_var_pac)):
        vc1, vc2 = st.sidebar.columns(2)
        anno_v = vc1.number_input(
            f"Var. #{i+1} — dall'anno", min_value=1, max_value=40,
            value=min(6 * (i + 1), 40), step=1, key=f"anno_var_pac_{i}",
        )
        importo_v = vc2.number_input(
            f"Var. #{i+1} — nuovo importo (€/anno)", min_value=0,
            value=3445, step=100, key=f"importo_var_pac_{i}",
        )
        variazioni_pac.append((int(anno_v), float(importo_v)))

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
quota_ts_auto = 0.0
ticker_bond_non_stimabili = []

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
        help="Per ETF non in catalogo o AZIONI SINGOLE (es. AAPL, ENI.MI). "
             "Le azioni sono ammesse ma molto più volatili di un ETF: l'app "
             "ti avviserà. Per gli ETF verifica che siano ad accumulo UCITS.",
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

    # Stima automatica della quota "titoli di Stato/white list" del
    # portafoglio, pesata sui ticker con composizione inequivocabile (vedi
    # QUOTA_TITOLI_STATO_TICKER). Per ticker obbligazionari misti o non
    # catalogati la quota non è stimabile e resta a 0 finché non la imposti
    # tu a mano nella sezione tassazione qui sotto.
    quota_ts_auto = 0.0
    ticker_bond_non_stimabili = []
    ticker_obbligazionari = set(CATALOGO_ETF.get("Obbligazionario", {}).values())
    if tickers_scelti and somma_pesi > 0:
        for t in tickers_scelti:
            peso_norm = pesi_dict[t] / somma_pesi
            quota_ts_auto += peso_norm * QUOTA_TITOLI_STATO_TICKER.get(t, 0.0)
            if t in ticker_obbligazionari and t not in QUOTA_TITOLI_STATO_TICKER:
                ticker_bond_non_stimabili.append(t)

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

st.sidebar.markdown("**Componente obbligazionaria — tassazione differenziata**")
usa_tassazione_ts_pac = st.sidebar.checkbox(
    "Applica aliquota ridotta (12,5%) sulla quota in titoli di Stato", value=False,
    help="In Italia i proventi/plusvalenze di fondi ed ETF armonizzati godono "
         "di un'aliquota ridotta al 12,5% (anziché il 26% ordinario) sulla "
         "quota riferibile a titoli di Stato italiani e di paesi white list. "
         "⚠️ La percentuale ESATTA deve essere certificata dall'emittente del "
         "fondo (documentazione fiscale annuale): questo è un modello "
         "SEMPLIFICATO che applica un'aliquota media pesata, non un calcolo "
         "fiscale definitivo. Non sono un consulente fiscale: verifica sempre "
         "con la documentazione ufficiale del tuo strumento.",
)
if usa_tassazione_ts_pac:
    default_quota = round(quota_ts_auto * 100, 1) if usa_portafoglio else 0.0
    quota_ts_pac_pct = st.sidebar.slider(
        "Quota del PAC in titoli di Stato/white list (%)", 0.0, 100.0,
        default_quota, 1.0,
        help="Se usi il portafoglio a ticker, è pre-impostata stimando i soli "
             "ETF di titoli di Stato puri riconosciuti automaticamente "
             "(es. Xtrackers Global Government Bond). Per fondi obbligazionari "
             "MISTI (es. Global Aggregate Bond, che include anche corporate) "
             "o ticker manuali, correggi tu il valore in base al KID/factsheet.",
    )
    if usa_portafoglio and ticker_bond_non_stimabili:
        st.sidebar.caption(
            "ℹ️ Nel portafoglio hai " + ", ".join(ticker_bond_non_stimabili) +
            ": è un obbligazionario MISTO (governativo+corporate), la quota "
            "titoli di Stato non è stimata automaticamente per questo ticker "
            "— il valore sopra la considera 0% a meno che tu non la corregga."
        )
    quota_ts_pac = quota_ts_pac_pct / 100
else:
    quota_ts_pac = 0.0

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
# GENERAZIONE TRAIETTORIE DI RENDIMENTO — TUTTE MENSILI (n x durata*12)
# ---------------------------------------------------------------------------
# Il motore del montante ora lavora MESE PER MESE: i versamenti vengono
# spalmati su 12 rate e ogni rata rende solo per i mesi residui. Tutti i
# generatori quindi restituiscono matrici di rendimenti MENSILI.

@st.cache_data
def genera_rendimenti_gbm(rend_medio: float, vol: float, durata: int,
                          n: int = 200, seed: int = 7):
    """
    GBM lognormale MENSILE. `rend_medio` e `vol` restano parametri ANNUI
    (come esposti in sidebar); vengono convertiti in parametri mensili
    (media geometrica mensile, vol/sqrt(12)). Ritorna (n x durata*12).
    """
    rng = np.random.default_rng(seed)
    rend_m = (1 + rend_medio) ** (1 / 12) - 1
    vol_m = vol / np.sqrt(12)
    sigma = np.sqrt(np.log(1 + (vol_m**2) / ((1 + rend_m)**2)))
    mu = np.log(1 + rend_m) - 0.5 * sigma**2
    shocks = rng.normal(mu, sigma, size=(n, durata * 12))
    return np.exp(shocks) - 1.0



@st.cache_data
def genera_rendimenti_block_bootstrap(serie_mensile: tuple, durata: int,
                                      block: int = 12, n: int = 200, seed: int = 33):
    """
    BLOCK-BOOTSTRAP MENSILE (Moving Block). Ricampiona blocchi CONTIGUI 
    di `block` mesi dai rendimenti mensili storici reali del comparto 
    (senza wrap-around) e li concatena fino a coprire `durata` anni.
    """
    serie = np.array(serie_mensile, dtype=float)
    m = serie.size
    
    # Se lo storico è più corto del blocco richiesto, non possiamo pescare
    if m < block:
        raise ValueError(f"Servono almeno {block} mesi, disponibili {m}.")
        
    rng = np.random.default_rng(seed)
    mesi_tot = durata * 12
    out = np.empty((n, mesi_tot))
    n_blocchi = int(np.ceil(mesi_tot / block))
    
    for s in range(n):
        # MODIFICA 1: L'indice di partenza casuale deve fermarsi in modo che 
        # l'ultimo blocco pescabile non superi la lunghezza totale dell'array (m).
        # rng.integers(low, high) esclude 'high', quindi usiamo m - block + 1.
        start = rng.integers(0, m - block + 1, size=n_blocchi)
        
        # MODIFICA 2: Usiamo un semplice slicing [inizio : fine] invece 
        # dell'operatore modulo (%), evitando così di unire artificialmente 
        # l'ultimo mese storico col primo.
        path = np.concatenate([serie[st : st + block] for st in start])[:mesi_tot]
        
        out[s] = path
        
    return out


def mensili_ad_annui(mat_mensile: np.ndarray) -> np.ndarray:
    """Compone una matrice di rendimenti mensili (n x anni*12) in annui (n x anni)."""
    n, mesi = mat_mensile.shape
    anni = mesi // 12
    return np.prod(1 + mat_mensile[:, :anni * 12].reshape(n, anni, 12), axis=2) - 1


def rendimento_netto_pac(r, ter_p):
    """
    Rendimento netto annuo del PAC al netto del solo TER: a differenza del
    fondo, il PAC in Italia NON tassa il rendimento anno per anno — la
    plusvalenza è tassata (26%, o aliquota impostata) solo in uscita/vendita.
    Questo "netto" è quindi un netto di SOLI COSTI ricorrenti, non di imposta;
    l'imposta sulla plusvalenza è mostrata separatamente come valore a scadenza.
    """
    r = np.asarray(r, dtype=float)
    return (1 + r) * (1 - ter_p) - 1


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
    """
    Scarica i prezzi mensili AGGIUSTATI (dividendi + split reinvestiti nel
    prezzo, come farebbe l'Adj Close storico di Yahoo). Fondamentale per
    qualunque strumento che stacca dividendi (azioni singole, ETF/ETC a
    distribuzione): senza aggiustamento, ogni stacco appare come un calo di
    prezzo fittizio, che SOTTOSTIMA il rendimento e SOVRASTIMA la volatilità.
    Per gli ETF ad accumulazione del catalogo curato non cambia nulla (non
    distribuiscono), ma è necessario per i ticker manuali (azioni, ETF a
    distribuzione) che l'app ammette esplicitamente.
    """
    import yfinance as yf
    import pandas as pd
    from datetime import date
    from dateutil.relativedelta import relativedelta

    end = date.today()
    start = end - relativedelta(years=anni)

    serie = {}
    for t in tickers:
        data = yf.download(t, start=start.isoformat(), end=end.isoformat(),
                           progress=False, auto_adjust=True, actions=False)
        if data is None or data.empty:
            raise ValueError(f"Nessun dato scaricato per '{t}'. Verifica il ticker su Yahoo.")
        # Con auto_adjust=True, "Close" È il prezzo aggiustato (equivalente al
        # vecchio "Adj Close"): dividendi e split già incorporati nel prezzo.
        if "Close" in data.columns:
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
    # Serie storica REALE del portafoglio pesato (mese per mese), usata per
    # mostrare il rendimento netto per anno "storico" nella tabella PAC.
    rend_mensili_pesato = (rend_mensili.values @ pesi)
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
        "rend_mensili_pesato": rend_mensili_pesato,
    }


@st.cache_data(show_spinner=False)
def genera_rendimenti_portafoglio_gbm(media_mensile, cholesky_mensile, pesi,
                                      durata_anni: int, rend_override=None,
                                      n: int = 200, seed: int = 13):
    """
    Traiettorie MENSILI del portafoglio (n x durata*12) con shock correlati
    (Cholesky). Se rend_override è dato, il drift viene TRASLATO (non scalato)
    di una costante uguale per tutti gli asset, così da centrare il rendimento
    atteso del portafoglio sull'override senza mai invertire il segno dei
    singoli asset (bug del vecchio approccio moltiplicativo quando lo storico
    era negativo).
    """
    rng = np.random.default_rng(seed)
    n_asset = len(pesi)
    mesi_tot = durata_anni * 12
    drift = media_mensile.copy()
    if rend_override is not None:
        target_m = (1 + rend_override) ** (1 / 12) - 1        # drift mensile obiettivo (portafoglio)
        attuale_m = float(np.dot(pesi, drift))                 # drift mensile attuale (portafoglio)
        drift = drift + (target_m - attuale_m)                 # shift additivo uniforme

    traiettorie = np.zeros((n, mesi_tot))
    for s in range(n):
        z = rng.standard_normal((mesi_tot, n_asset))
        shock_mensili = z @ cholesky_mensile.T
        rend_mensili_asset = drift + shock_mensili
        traiettorie[s] = rend_mensili_asset @ pesi
    return traiettorie


# ---------------------------------------------------------------------------
# COSTRUZIONE DELLO SCHEDULE ANNO-PER-ANNO (livello, CCNL, comparto, disoccup.)
# ---------------------------------------------------------------------------
def costruisci_serie_a_gradini(durata: int, base: float, variazioni: list) -> list:
    """
    Costruisce una serie annua (lunga `durata`) che parte da `base` e cambia
    a GRADINI negli anni indicati in `variazioni` (lista di (anno_da, nuovo_importo)).
    Usata per versamenti (PAC, volontario fondo) che l'utente vuole tenere
    fissi ma modulare nel tempo: es. base=1000, variazioni=[(6, 1500), (12, 800)]
    => 1000€ per gli anni 1-5, 1500€ dagli anni 6-11, 800€ dall'anno 12 in poi.
    """
    eventi = sorted(variazioni, key=lambda x: x[0])
    serie = []
    corrente = base
    idx_evento = 0
    for a in range(durata):
        anno = a + 1
        while idx_evento < len(eventi) and eventi[idx_evento][0] <= anno:
            corrente = eventi[idx_evento][1]
            idx_evento += 1
        serie.append(corrente)
    return serie


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
        anno_ultimo_cambio_ccnl = 0   # 0 = nessun cambio (si parte dal CCNL iniziale)
        for anno_da, tipo, payload in eventi:
            if anno_da <= anno:
                if tipo == "livello":
                    liv_att = payload
                else:
                    ccnl_att, liv_att, comp_att = payload
                    anno_ultimo_cambio_ccnl = anno_da
        preset_a = CCNL_PRESET[ccnl_att]
        # comparto di ripiego se il nome non esiste nel nuovo fondo
        if comp_att not in preset_a["comparti"]:
            comp_att = preset_a["comparti"][-1]

        mens_a = preset_a["mensilita"]
        minimo_mensile_a = preset_a["livelli"][liv_att]
        minimo_annuo_a = minimo_mensile_a * mens_a
        scatto_val_liv_a = preset_a["scatti_valore_livello"][liv_att]
        scatto_annuo_a = scatto_val_liv_a * mens_a
        freq_a = preset_a["scatto_ogni_anni"]
        max_a = preset_a["scatti_max"]

        eta_corrente = eta + a
        u35 = eta_corrente < 35
        ca_pct_a = preset_a["contrib_azienda_u35_pct"] if u35 else preset_a["contrib_azienda_pct"]
        lav_pct_a = preset_a["contrib_lav_pct"]
        tfr_pct_a = preset_a["tfr_pct"]
        costo_fisso_a = preset_a["costo_fisso"]

        # --- SCATTI DI ANZIANITÀ ---
        # Regola: gli scatti maturano nel rapporto di lavoro corrente. Un
        # CAMBIO DI CCNL (cambio azienda/settore) azzera l'anzianità: gli
        # scatti pregressi e quelli maturati prima del cambio SI PERDONO e si
        # ricomincia a maturare da zero nel nuovo contratto. I passaggi di
        # LIVELLO (promozione interna) invece NON azzerano nulla.
        # Il totale è sempre limitato a scatti_max del CCNL corrente: se parti
        # con 2 pregressi su max 5, potrai maturarne al più altri 3.
        if anno_ultimo_cambio_ccnl == 0:
            # nessun cambio: pregressi + anzianità simulata
            anni_servizio = anni_pregressi_scatti * freq_a + anno
        else:
            # anzianità solo dall'anno del cambio in poi (pregressi persi)
            anni_servizio = anno - anno_ultimo_cambio_ccnl + 1
        scatti_maturati = min(max_a, anni_servizio // freq_a)
        base_teorica = minimo_annuo_a + scatti_maturati * scatto_annuo_a
        base_contrib_a = base_teorica * ((1 + crescita_base) ** a)

        # base RAL (anno 1 equivalente del segmento), scalata poi dalla carriera.
        # Dopo un cambio CCNL gli scatti pregressi spariscono anche dalla RAL.
        scatti_in_ral = anni_pregressi_scatti if anno_ultimo_cambio_ccnl == 0 else 0
        ral_base_eff_a = (minimo_annuo_a + scatti_in_ral * scatto_annuo_a
                          + superminimo_annuo + premio_annuo)

        occupato = anno not in anni_disoccupato

        sched.append({
            "anno": anno,
            "ccnl": ccnl_att, "livello": liv_att, "comparto": comp_att,
            "fondo": preset_a["fondo"], "comparto_key": (preset_a["fondo"], comp_att),
            "mensilita": mens_a,
            "ca_pct": ca_pct_a, "lav_pct": lav_pct_a, "tfr_pct": tfr_pct_a,
            "costo_fisso_f": costo_fisso_a,
            "base_contrib": base_contrib_a if occupato else 0.0,
            "ral_base_eff": ral_base_eff_a,
            "scatti": scatti_maturati,
            "occupato": occupato,
            "cambio_ccnl_qui": (anno_ultimo_cambio_ccnl == anno),
        })
    return sched


# ---------------------------------------------------------------------------
# MOTORE DI SIMULAZIONE DEL CAPITALE (schedule-driven)
# ---------------------------------------------------------------------------
def simula_capitale(fattori, rend_fondo_mensili, rend_pac_mensili, sched, scal,
                    vol_extra_serie, vp_serie) -> pd.DataFrame:
    """
    Simula il montante MESE PER MESE. `rend_fondo_mensili` e `rend_pac_mensili`
    sono traiettorie di rendimenti mensili lunghe durata*12 (già coerenti con
    lo schedule dei comparti per il fondo). I versamenti annui vengono divisi
    in 12 rate: ogni rata rende solo per i mesi residui — coerente con un PAC
    e con i contributi mensili reali al fondo (fix della sovrastima da
    versamento "tutto a gennaio").

    `vol_extra_serie` e `vp_serie` sono liste lunghe `durata`: il versamento
    volontario del fondo e quello del PAC per ciascun anno. Restano FISSI in
    euro nominali (nessuno scaling automatico con la crescita di carriera);
    possono però cambiare a gradini se l'utente ha pianificato variazioni.
    """
    ral_override = scal["ral_override"]
    ral_manuale = scal["ral_manuale"]
    ter_p = scal["ter_p"]
    tp = scal["tp"] / 100
    quota_ts_pac = scal.get("quota_ts_pac", 0.0)
    # Aliquota effettiva sulla plusvalenza PAC: 12,5% sulla quota in titoli di
    # Stato/white list, aliquota ordinaria (tp) sul resto. Se quota_ts_pac=0
    # (default) equivale esattamente al vecchio comportamento (tp flat).
    tp_eff = tp * (1 - quota_ts_pac) + 0.125 * quota_ts_pac
    rt = scal["rt"]
    tt = scal["tt"] / 100
    anni_pregressi = scal["anni_pregressi"]
    uscita_ord = scal["uscita_ordinaria"]

    cap_fondo = float(scal.get("cap_iniziale_fondo", 0.0))
    cap_pac = float(scal.get("cap_iniziale_pac", 0.0))
    versato_pac_cum = float(scal.get("cap_iniziale_pac", 0.0))
    cap_tfr = 0.0
    mantieni_contributi_azienda = scal.get("mantieni_contributi_azienda", True)
    # Ledger "ombra": segue SOLO la quota del fondo derivata dai contributi
    # del datore (capitale + rendimento/TER maturati su quella quota), senza
    # intaccare cap_fondo. Serve unicamente per poter sottrarre esattamente
    # quella quota da cap_fondo se, a un cambio di CCNL, l'utente ha scelto
    # di NON trattenerla (vedi opzione in sidebar).
    cap_fondo_azienda_ombra = 0.0
    rows = []

    for a, f in enumerate(fattori):
        s = sched[a]
        anno = a + 1
        occupato = s["occupato"]

        # Cambio CCNL in questo anno: se l'utente ha scelto di NON trattenere
        # i contributi già versati dal VECCHIO datore, li sottraiamo dal
        # montante del fondo (con il loro rendimento/TER maturato) prima di
        # applicare i contributi di quest'anno. TFR e contributi del
        # lavoratore restano sempre intatti in entrambi gli scenari.
        if s["cambio_ccnl_qui"] and not mantieni_contributi_azienda:
            cap_fondo = max(0.0, cap_fondo - cap_fondo_azienda_ombra)
            cap_fondo_azienda_ombra = 0.0

        # RAL: override manuale (se attivo) solo mentre si è occupati
        if occupato:
            ral_curr = ral_manuale * f if ral_override else s["ral_base_eff"] * f
        else:
            ral_curr = 0.0

        base_contrib = s["base_contrib"]  # già 0 se disoccupato

        # Importi ANNUI (per la tabella e l'IRPEF)
        tfr_curr = ral_curr * s["tfr_pct"] if occupato else 0.0
        ca_curr = base_contrib * s["ca_pct"]
        vol_min = base_contrib * s["lav_pct"]
        vf_curr = vol_min + (vol_extra_serie[a] if occupato else 0.0)
        vp_curr = vp_serie[a] if occupato else 0.0

        # Deduzione IRPEF (solo se occupato e c'è reddito)
        if occupato and (vf_curr + ca_curr) > 0:
            deducibile = min(vf_curr + ca_curr, LIMITE_DEDUCIBILITA)
            aliq_marg = aliquota_marginale(ral_curr)
            quota_lav = vf_curr / (vf_curr + ca_curr)
            risparmio_anno = deducibile * aliq_marg * quota_lav
        else:
            risparmio_anno = 0.0

        # --- CICLO MENSILE: versamenti in 12 rate, rendimento mese per mese ---
        # Ogni rata prende solo il rendimento dei mesi RESIDUI dell'anno (fix
        # della vecchia versione che dava un anno intero di rendimento a tutto
        # il versamento annuo). Rivalutazione TFR convertita in mensile.
        #
        # NB: il rendimento del fondo (rend_fondo_mensili) viene dal
        # RICAMPIONAMENTO della quota storica reale del comparto. La quota
        # pubblicata da un fondo pensione negoziale è GIÀ AL NETTO sia
        # dell'imposta sostitutiva annua 20%/12,5% (che il fondo versa
        # direttamente, non l'iscritto) sia dei costi di gestione finanziaria
        # (il fondo li scarica sulla quota, come il NAV di un fondo comune è
        # già al netto del proprio TER). Applicare QUI un'altra tassa/TER sul
        # rendimento ricampionato sarebbe un doppio conteggio: il rendimento
        # storico va quindi usato COSÌ COM'È. L'unico costo aggiuntivo reale,
        # non incluso nella quota, è il costo fisso amministrativo annuo in
        # euro (costo_fisso_f), applicato una volta l'anno più sotto.
        rata_fondo = (vf_curr + tfr_curr + ca_curr) / 12.0
        rata_azienda = ca_curr / 12.0
        rata_pac = vp_curr / 12.0
        rata_tfr = tfr_curr / 12.0
        ter_p_m = 1 - (1 - ter_p) ** (1 / 12)
        rt_m = (1 + rt) ** (1 / 12) - 1

        for mese in range(12):
            r_f = rend_fondo_mensili[a * 12 + mese]
            r_p = rend_pac_mensili[a * 12 + mese]

            # FONDO: versamento a inizio mese, rendimento della quota GIÀ NETTO
            cap_fondo += rata_fondo
            cap_fondo += cap_fondo * r_f

            # Ledger ombra quota-datore: stessa dinamica (stesso comparto),
            # non tocca cap_fondo — serve solo a sapere quanto vale la quota
            # datore nel momento di un eventuale cambio CCNL.
            cap_fondo_azienda_ombra += rata_azienda
            cap_fondo_azienda_ombra += cap_fondo_azienda_ombra * r_f

            # PAC: versamento a inizio mese, rendimento, TER (qui sì dovuto:
            # un ETF non è pre-tassato come i fondi pensione negoziali)
            versato_pac_cum += rata_pac
            cap_pac += rata_pac
            cap_pac *= (1 + r_p) * (1 - ter_p_m)

            # TFR in azienda: accantonamento mensile + rivalutazione mensile
            cap_tfr += rata_tfr
            cap_tfr *= (1 + rt_m)

        # Costo fisso amministrativo del fondo: una volta l'anno
        cap_fondo = max(0.0, cap_fondo - s["costo_fisso_f"])

        # --- Valori netti a uscita ---
        anni_adesione = anni_pregressi + anno
        aliq_uscita = aliquota_uscita_fondo(anni_adesione, ordinaria=uscita_ord)
        netto_fondo = cap_fondo * (1 - aliq_uscita)
        plusval_pac = max(0.0, cap_pac - versato_pac_cum)
        netto_pac = cap_pac - plusval_pac * tp_eff
        netto_tfr = cap_tfr * (1 - tt)

        rows.append({
            "Anno": anno,
            "CCNL": s["ccnl"], "Livello": s["livello"], "Comparto": s["comparto"],
            "Scatti": s["scatti"],
            "Occupato": "Sì" if occupato else "No",
            "RAL (€)": ral_curr,
            "Contrib. Min. CCNL (€)": vol_min,
            "Vers. Volontario (€)": (vol_extra_serie[a] if occupato else 0.0),
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


def calcola_bande(fattori, rend_fondo_mat, rend_pac_mat, sched, scal,
                  vol_extra_serie, vp_serie, n_band=200):
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
        d = simula_capitale(fattori, rend_fondo_mat[i], rend_pac_mat[i], sched, scal,
                            vol_extra_serie, vp_serie)
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
avvisi_corti = []       # comparti con storico mensile relativamente breve
mancanti = []           # comparti senza dati sufficienti per il resampling
mat_per_comparto = {}
SOGLIA_MESI_CORTI = 60  # meno di 5 anni di mesi: banda P10-P90 poco robusta
for ki, key in enumerate(comparto_keys):
    fondo_k, comp_k = key
    # seed decorrelato per comparto (evita traiettorie identiche tra comparti
    # in caso di cambio CCNL/comparto a metà carriera)
    if mensile_disponibile(fondo_k, comp_k):
        serie_full = STORICO_MENSILE[fondo_k][comp_k]
        anni_full = STORICO_MENSILE_ANNI[fondo_k][comp_k]
        serie = tuple(filtra_storico_da_anno(serie_full, anni_full, anno_inizio_storico))
        if len(serie) < SOGLIA_MESI_CORTI:
            avvisi_corti.append(f"{fondo_k} · {comp_k} ({len(serie)} mesi)")
        try:
            mat_per_comparto[key] = genera_rendimenti_block_bootstrap(
                serie, durata, block=int(block_mesi), n=N_BAND, seed=st.session_state.master_seed + ki)
        except ValueError as e:
            mancanti.append(f"{fondo_k} · {comp_k} (serie mensile troppo corta dopo il "
                            f"taglio all'anno {anno_inizio_storico}: {e})")
    else:
        mancanti.append(f"{fondo_k} · {comp_k} (serie mensile)")

if mancanti:
    st.error(
        "**Dati storici mancanti o insufficienti** per: " + "; ".join(mancanti) + ".\n\n"
        "I rendimenti provengono solo dal resampling dello storico reale. Se "
        "hai tagliato l'orizzonte storico (sezione '4. Performance simulata'), "
        "prova ad abbassare l'anno di inizio, oppure abbassa la lunghezza del "
        "blocco, oppure scegli un CCNL/comparto già coperto (es. Cometa)."
    )
    st.stop()

rend_fondo_mat = np.empty((N_BAND, durata * 12))
for a, s in enumerate(sched):
    rend_fondo_mat[:, a * 12:(a + 1) * 12] = \
        mat_per_comparto[s["comparto_key"]][:, a * 12:(a + 1) * 12]

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

# --- Versamenti FISSI ma modulabili a gradini nel tempo ---
vol_extra_serie = costruisci_serie_a_gradini(durata, vers_vol_extra, variazioni_vol_extra)
vp_serie = costruisci_serie_a_gradini(durata, versamento_pac, variazioni_pac)

# --- Parametri scalari (non variano con lo schedule) ---
scal = dict(
    ral_override=ral_override, ral_manuale=ral_manuale,
    ter_p=ter_pac, tp=tassa_uscita_pac, quota_ts_pac=quota_ts_pac,
    rt=rend_tfr, tt=tassa_tfr,
    anni_pregressi=anni_gia_iscritto, uscita_ordinaria=uscita_ordinaria,
    cap_iniziale_fondo=capitale_iniziale_fondo,
    cap_iniziale_pac=capitale_iniziale_pac,
    mantieni_contributi_azienda=mantieni_contributi_azienda,
)

fattori_mediani = [float(np.percentile([s[a] for s in scenari], 50)) for a in range(durata)]
df_main = simula_capitale(fattori_mediani, rend_fondo_sel, rend_pac_sel, sched, scal,
                          vol_extra_serie, vp_serie)

# --- Bande GBM P10–P90 su tutte le curve (carriera fissa alla mediana) ---
bande = calcola_bande(fattori_mediani, rend_fondo_mat, rend_pac_mat, sched, scal,
                      vol_extra_serie, vp_serie, n_band=N_BAND)
anni = list(range(1, durata + 1))


# ---------------------------------------------------------------------------
# INTESTAZIONE
# ---------------------------------------------------------------------------
motore_txt = f"Block-bootstrap mensile (blocco {int(block_mesi)} mesi)"
st.info(
    f"**Profilo:** {tipo_lavoratore} · {ccnl_scelto} · livello {livello} · comparto {comparto}  \n"
    f"Coefficiente crescita ×{coeff_totale:.2f} · crescita di base "
    f"{crescita_base*100:.1f}%/anno · rendimenti fondo: **{motore_txt}** (storico reale)  \n"
    f"Linea centrale **P{percentile_perf}** · banda **P10–P90** su tutte le curve "
    f"({N_BAND} scenari)  \n"
    f"*Valori nominali (includono l'inflazione, coerentemente con contributi e montante).*"
)

if avvisi_corti:
    st.caption(
        "ℹ️ Storico REALE ma relativamente breve (meno di 5 anni di mesi): "
        + ", ".join(avvisi_corti)
        + ". La banda P10–P90 per questi comparti dipende da un numero limitato "
          "di osservazioni sottostanti: trattala con più cautela."
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
cc1, cc2 = st.columns(2)
cc1.metric("Costo iniziale (una tantum)", f"€ {preset['costo_iniziale']:,.2f}")
cc2.metric("Costo fisso annuo", f"€ {preset['costo_fisso']:,.0f}")

costo_fisso_totale = preset["costo_fisso"] * durata + preset["costo_iniziale"]

with st.expander("📖 Come leggere i costi del fondo"):
    st.markdown(f"""
Il fondo pensione ha **due costi separati**, entrambi inclusi nella simulazione:

1. **Costo iniziale** — €{preset['costo_iniziale']:.2f} una tantum all'iscrizione.
2. **Costo fisso annuo** — €{preset['costo_fisso']:.0f}/anno di spese amministrative
   sulla posizione individuale. Su {durata} anni: ~€{costo_fisso_totale:,.0f}.

**Costi di gestione finanziaria e tassazione annua NON compaiono qui separatamente:**
il rendimento storico usato per la simulazione è quello della **quota reale**
pubblicata dal fondo per il comparto *{comparto}*, che è **già al netto**
dell'imposta sostitutiva annua (20% ordinario, 12,5% sulla quota in titoli di
Stato — pagata dal fondo stesso, non dall'iscritto) e dei costi di gestione
finanziaria (il TER è già scaricato sulla quota, come il NAV di un fondo
comune è già al netto delle proprie commissioni). Applicare un'ulteriore
deduzione qui sarebbe un doppio conteggio: la simulazione usa quindi il
rendimento storico così com'è, più i due costi sopra che restano a carico
della posizione individuale.
""")
st.divider()


# ---------------------------------------------------------------------------
# RENDIMENTO PER ANNO DEL COMPARTO SCELTO
# ---------------------------------------------------------------------------
st.subheader(f"📗 Rendimento per anno — {comparto} ({preset['fondo']})")
st.caption("Rendimento della quota reale del comparto: già al netto di tasse "
           "e costi di gestione finanziaria (li paga/scarica il fondo stesso "
           "sulla quota). A sinistra lo storico reale (con lo stesso taglio "
           "di orizzonte impostato in sidebar, se attivo), a destra la "
           "previsione dal resampling. Il costo fisso amministrativo annuo "
           "in euro resta comunque a parte, applicato sulla posizione "
           "individuale (vedi tabella anno-per-anno più sotto).")

fondo_sel = preset["fondo"]
serie_ann_full = STORICO_ANNUALE.get(fondo_sel, {}).get(comparto, [])
anni_ann_full = STORICO_ANNUALE_ANNI.get(fondo_sel, {}).get(comparto, [])
serie_ann_sel = filtra_storico_da_anno(serie_ann_full, anni_ann_full, anno_inizio_storico)
anni_lbl = [y for y in anni_ann_full if y >= anno_inizio_storico]

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("**Storico reale (anno per anno)**")
    if serie_ann_sel:
        df_stor = pd.DataFrame({
            "Anno": anni_lbl,
            "Rendimento (%)": [r * 100 for r in serie_ann_sel],
        })
        st.dataframe(
            df_stor.style.format({"Rendimento (%)": "{:+.2f}"}),
            use_container_width=True, hide_index=True, height=300,
        )
        cagr_l = float(np.prod([1 + r for r in serie_ann_sel])) ** (1 / len(serie_ann_sel)) - 1
        s1, s2 = st.columns(2)
        s1.metric("CAGR", f"{cagr_l*100:.2f}%")
        s2.metric("Anno peggiore", f"{min(serie_ann_sel)*100:+.1f}%")
        if len(serie_ann_sel) < 8:
            st.caption(f"⚠️ Solo {len(serie_ann_sel)} anni disponibili: statistiche indicative.")
        if anno_inizio_storico > ANNO_STORICO_MIN_GLOBALE and len(serie_ann_sel) < len(serie_ann_full):
            st.caption(f"✂️ Storico tagliato: {len(serie_ann_full) - len(serie_ann_sel)} "
                       f"anni esclusi (prima del {anno_inizio_storico}).")
    else:
        st.info("Storico annuale non disponibile per questo comparto (o azzerato dal taglio impostato).")

with col_b:
    st.markdown(f"**Previsione resampling** ({motore_txt})")
    key_sel = (fondo_sel, comparto)
    if key_sel in mat_per_comparto:
        mat_annua = mensili_ad_annui(mat_per_comparto[key_sel])
        df_prev = pd.DataFrame({
            "Anno": list(range(1, durata + 1)),
            "P10 (%)": np.percentile(mat_annua, 10, axis=0) * 100,
            "P50 (%)": np.percentile(mat_annua, 50, axis=0) * 100,
            "P90 (%)": np.percentile(mat_annua, 90, axis=0) * 100,
        })
        st.dataframe(
            df_prev.style.format({c: "{:+.2f}" for c in df_prev.columns if c != "Anno"}),
            use_container_width=True, hide_index=True, height=300,
        )
        st.caption(f"Rendimento annuo mediano simulato: "
                   f"**{np.median(mat_annua)*100:+.2f}%** (su tutti anni e scenari).")
    else:
        st.info("Comparto non attivo all'anno 1 (cambio CCNL immediato?).")

st.divider()


# ---------------------------------------------------------------------------
# RENDIMENTO NETTO PER ANNO DEL PAC
# ---------------------------------------------------------------------------
st.subheader("📘 Rendimento netto per anno — PAC")
st.caption(
    "Netto = dopo TER. A differenza del fondo, il PAC in Italia NON tassa il "
    "rendimento anno per anno: la plusvalenza si tassa solo in uscita/vendita "
    "(vedi tabella anno per anno per il valore netto finale). A sinistra lo "
    "storico reale (solo se hai scelto il portafoglio a ticker), a destra la "
    "previsione simulata."
)
if usa_tassazione_ts_pac and quota_ts_pac > 0:
    tp_eff_display = tassa_uscita_pac * (1 - quota_ts_pac) + 12.5 * quota_ts_pac
    st.info(
        f"🏛️ Tassazione differenziata attiva: **{quota_ts_pac*100:.0f}%** del PAC "
        f"considerato titoli di Stato/white list (12,5%), il resto a "
        f"{tassa_uscita_pac}%. **Aliquota effettiva sulla plusvalenza: "
        f"{tp_eff_display:.2f}%** (usata nella tabella anno-per-anno per il "
        f"valore netto a uscita). Ricorda: è una stima semplificata, non un "
        f"calcolo fiscale certificato."
    )

col_c, col_d = st.columns(2)

with col_c:
    st.markdown("**Storico reale del portafoglio (anno per anno)**")
    if usa_portafoglio and portafoglio_info is not None and not errore_portafoglio:
        rmp = portafoglio_info["rend_mensili_pesato"]
        n_anni_storico_pac = len(rmp) // 12
        if n_anni_storico_pac >= 1:
            blocchi = rmp[:n_anni_storico_pac * 12].reshape(n_anni_storico_pac, 12)
            annuali_storici = np.prod(1 + blocchi, axis=1) - 1
            netti_storici = rendimento_netto_pac(annuali_storici, ter_pac)
            df_stor_pac = pd.DataFrame({
                "Periodo (blocco 12 mesi)": list(range(1, n_anni_storico_pac + 1)),
                "Lordo (%)": annuali_storici * 100,
                "Netto TER (%)": np.asarray(netti_storici) * 100,
            })
            st.dataframe(
                df_stor_pac.style.format({"Lordo (%)": "{:+.2f}", "Netto TER (%)": "{:+.2f}"}),
                use_container_width=True, hide_index=True, height=300,
            )
            cagr_l_pac = float(np.prod(1 + annuali_storici)) ** (1 / n_anni_storico_pac) - 1
            cagr_n_pac = float(np.prod(1 + netti_storici)) ** (1 / n_anni_storico_pac) - 1
            sp1, sp2, sp3 = st.columns(3)
            sp1.metric("CAGR lordo", f"{cagr_l_pac*100:.2f}%")
            sp2.metric("CAGR netto TER", f"{cagr_n_pac*100:.2f}%")
            sp3.metric("Peggiore (netto)", f"{min(netti_storici)*100:+.1f}%")
            st.caption("Blocchi di 12 mesi consecutivi dall'inizio dello storico "
                       "scaricato (non anni solari): il blocco 1 è il più vecchio.")
        else:
            st.info("Meno di 12 mesi di storico: non è possibile comporre un anno.")
    else:
        st.info(
            "Storico reale non disponibile in modalità PAC 'Semplice' (solo "
            "assunzione parametrica GBM) oppure portafoglio non caricato/errato."
        )

with col_d:
    st.markdown("**Previsione simulata**")
    net_mat_pac = rendimento_netto_pac(mensili_ad_annui(rend_pac_mat), ter_pac)
    df_prev_pac = pd.DataFrame({
        "Anno": list(range(1, durata + 1)),
        "P10 netto (%)": np.percentile(net_mat_pac, 10, axis=0) * 100,
        "P50 netto (%)": np.percentile(net_mat_pac, 50, axis=0) * 100,
        "P90 netto (%)": np.percentile(net_mat_pac, 90, axis=0) * 100,
    })
    st.dataframe(
        df_prev_pac.style.format({c: "{:+.2f}" for c in df_prev_pac.columns if c != "Anno"}),
        use_container_width=True, hide_index=True, height=300,
    )
    st.caption(f"Rendimento netto annuo mediano simulato: "
               f"**{np.median(net_mat_pac)*100:+.2f}%** (su tutti anni e scenari).")

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
pac_anno1 = r0["PAC annuo (€)"]
costo_netto_fondo_anno1 = max(0.0, vers_vol_anno1 - risparmio_anno1)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Costo netto fondo/mese", f"€ {costo_netto_fondo_anno1/mensilita:,.0f}")
m2.metric("Costo PAC/mese", f"€ {pac_anno1/12:,.0f}")
m3.metric("Totale investito/mese", f"€ {(costo_netto_fondo_anno1/mensilita + pac_anno1/12):,.0f}")
m4.metric("Contributo azienda (gratis)/anno", f"€ {ca_anno1:,.0f}")
if (usa_variazioni_vol_extra and variazioni_vol_extra) or (usa_variazioni_pac and variazioni_pac):
    st.caption("ℹ️ Hai pianificato variazioni dei versamenti nel tempo: questi "
               "importi valgono solo per l'Anno 1, guarda la tabella anno per "
               "anno per gli anni successivi.")
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

        # Avviso basato sui DATI: asset con volatilità annua alta (tipico di
        # azioni singole) rendono la stima storica poco affidabile e allargano
        # molto la banda P10-P90.
        SOGLIA_VOL_ALTA = 0.25
        vol_alte = [
            f"**{t}** ({v*100:.0f}%/anno)"
            for t, v in zip(pi["tickers"], pi["vol_annua_asset"])
            if v > SOGLIA_VOL_ALTA
        ]
        if vol_alte:
            st.warning(
                "🎢 **Alta volatilità rilevata** per: " + ", ".join(vol_alte) +
                f" (soglia {SOGLIA_VOL_ALTA*100:.0f}%). Tipico di azioni singole "
                "o ETF settoriali/leva: rendimento e rischio stimati da un solo "
                "titolo sono poco affidabili e possono compromettere l'analisi "
                "di lungo periodo. Considera un peso ridotto o un ETF "
                "diversificato, e valuta con prudenza la banda P10–P90."
            )

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

cols_show = ["Anno", "CCNL", "Livello", "Comparto", "Scatti", "Occupato", "RAL (€)",
             "Contrib. Min. CCNL (€)", "Vers. Volontario (€)", "TFR al Fondo (€)",
             "Contrib. Aziendale (€)", "Risparmio IRPEF (€)", "PAC annuo (€)",
             "Aliq. uscita fondo (%)", "Fondo Netto (€)", "PAC + TFR Netto (€)", "PAC Netto (€)"]
if usa_entrambi:
    cols_show.append("Fondo + PAC Netto (€)")

fmt = {c: "€ {:,.0f}" for c in cols_show
       if c not in ("Anno", "CCNL", "Livello", "Comparto", "Scatti", "Occupato", "Aliq. uscita fondo (%)")}
fmt["Aliq. uscita fondo (%)"] = "{:.1f}%"
st.dataframe(df_main[cols_show].style.format(fmt), use_container_width=True, height=420)

st.caption(
    "⚠️ Stima illustrativa. Crescita salariale su dati ISTAT; contributi CCNL "
    "Cometa/Fon.Te; rendimenti del fondo dal ricampionamento (block-bootstrap) "
    "dello storico reale della quota, già al netto di tasse e costi di "
    "gestione; PAC simulato con GBM (parametrico o da portafoglio ticker). La "
    "banda P10–P90 riflette l'incertezza dei rendimenti, non quella di "
    "carriera. Non è consulenza finanziaria o previdenziale."
)
