# ---------------------------------------------------------------------------
# PAC AVANZATO — modello a 2 asset (Azionario / Obbligazionario)
# ---------------------------------------------------------------------------
# Modulo autonomo, stesso pattern di backtest/ui.py: espone
#     render_pac_avanzato(ctx)
# da chiamare in un tab dell'app principale. NON tocca il motore esistente.
#
# PRINCIPIO GUIDA: nessun parametro di rendimento/rischio e' inventato o
# lasciato a uno slider manuale. Sia il bootstrap che il GBM-Cholesky
# stimano mu/sigma/rho dagli STESSI dati storici scaricati da Yahoo Finance
# per il portafoglio ticker gia' configurato nella sidebar del PAC (sezione
# "5. PAC (ETF)" > "Portafoglio ticker"). L'utente sceglie solo la
# METODOLOGIA di ricampionamento (bootstrap vs parametrico), mai i numeri.
#
# Caratteristiche:
# - Richiede il portafoglio a ticker configurato in sidebar (stessa fonte
#   dati di tutto il resto dell'app). Se non e' presente, il tab spiega come
#   attivarlo e si ferma: NIENTE fallback su assunzioni parametriche a mano.
# - I ticker vengono classificati Azionario/Obbligazionario (preselezione
#   automatica in base al nome, correggibile) e da li' si costruiscono due
#   serie mensili aggregate (equal-weight) usate per stimare mu, sigma, rho.
# - Motore Monte Carlo SELEZIONABILE:
#     a) Block-bootstrap storico congiunto (blocco in mesi selezionabile,
#        ricampiona le due serie con gli STESSI indici -> preserva la
#        correlazione empirica azionario/obbligazionario)
#     b) GBM multivariato con decomposizione di CHOLESKY sulla matrice di
#        correlazione, parametri mu/sigma/rho STIMATI dai dati (stile
#        MARKOWITZ: sigma_p^2 = we^2*se^2 + wb^2*sb^2 + 2*we*wb*rho*se*sb).
#        E' disponibile un correttivo OPZIONALE (spento di default) solo sul
#        rendimento atteso — mai su volatilita'/correlazione — perche' la
#        media storica e' un cattivo stimatore del rendimento futuro, mentre
#        vol/correlazione sono stime molto piu' robuste: stesso principio
#        gia' usato altrove nell'app per il PAC a ticker.
# - MEAN REVERSION (solo GBM): richiamo tipo Ornstein-Uhlenbeck del
#   log-rendimento cumulato verso il trend di lungo periodo (kappa/anno).
# - DERISKING (glidepath lineare): quota azionaria da w_iniziale a w_finale
#   tra due anni scelti; il ribilanciamento insegue il target corrente.
# - RIBILANCIAMENTO ogni N mesi (selezionabile) in base al VALORE delle
#   quote: vende il bucket sovrappesato, tassa la plusvalenza realizzata
#   (pro-quota sul costo medio), applica il costo di transazione e
#   reinveste il netto nell'altro bucket.
# - COSTI ETF all'ACQUISTO da input (fisso EUR/ordine + % sull'ordine) e
#   TER annuo da input: se non impostati valgono 0.
# - IMPOSTA DI BOLLO 0,2%/anno sul controvalore (applicata pro-rata mensile,
#   disattivabile).
# - DECUMULO: prelievo mensile lordo (opz. indicizzato all'inflazione) per
#   N anni dopo l'accumulo, con tassazione della plusvalenza pro-quota e
#   probabilita' di successo (capitale mai esaurito).
# - DEFLAZIONE del montante: tutte le curve anche in EURO REALI (potere
#   d'acquisto di oggi) con inflazione da input.
# ---------------------------------------------------------------------------

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ---------------------------------------------------------------------------
# GENERATORI DI RENDIMENTI MENSILI (n scenari x mesi x 2 asset)
# ---------------------------------------------------------------------------
def genera_gbm_cholesky(mu_e, sig_e, mu_b, sig_b, rho, mesi, n, seed, kappa=0.0):
    """
    GBM lognormale mensile a 2 asset con shock correlati via Cholesky sulla
    matrice di correlazione (Markowitz: la covarianza e' rho*se*sb) e mean
    reversion opzionale (kappa per anno, 0 = GBM puro).

    Mean reversion: sul log-prezzo cumulato X_t di ciascun asset,
        r_t = mu_log + (kappa/12) * (mu_log * t - X_t) + shock_t
    cioe' un richiamo verso il trend deterministico di lungo periodo: dopo
    una serie di anni sopra-trend il drift si abbassa, e viceversa.
    """
    rng = np.random.default_rng(seed)
    mu = np.array([mu_e, mu_b], dtype=float)
    sig = np.array([sig_e, sig_b], dtype=float)

    mu_m = (1.0 + mu) ** (1.0 / 12.0) - 1.0
    sig_m = sig / np.sqrt(12.0)

    # parametri lognormali coerenti con media/vol aritmetiche mensili
    sigma_log = np.sqrt(np.log(1.0 + (sig_m ** 2) / (1.0 + mu_m) ** 2))
    mu_log = np.log(1.0 + mu_m) - 0.5 * sigma_log ** 2

    corr = np.array([[1.0, rho], [rho, 1.0]])
    L = np.linalg.cholesky(corr + np.eye(2) * 1e-12)

    k_m = float(kappa) / 12.0
    out = np.empty((n, mesi, 2))
    X = np.zeros((n, 2))  # log-rendimento cumulato per asset
    for t in range(mesi):
        z = rng.standard_normal((n, 2)) @ L.T          # normali correlate
        shock = z * sigma_log                            # scala log-vol
        drift = mu_log + k_m * (mu_log * t - X)          # mean reversion
        r_log = drift + shock
        X += r_log
        out[:, t, :] = np.exp(r_log) - 1.0
    return out


def genera_bootstrap_congiunto(serie_e, serie_b, mesi, n, block, seed):
    """
    Block-bootstrap CONGIUNTO: pesca blocchi contigui di `block` mesi con gli
    stessi indici da entrambe le serie storiche (gia' allineate), quindi la
    correlazione empirica azionario/obbligazionario e' preservata per
    costruzione. Nessun wrap-around (come il motore del fondo).
    """
    se = np.asarray(serie_e, dtype=float)
    sb = np.asarray(serie_b, dtype=float)
    m = min(se.size, sb.size)
    se, sb = se[-m:], sb[-m:]
    if m < block:
        raise ValueError(f"Servono almeno {block} mesi comuni, disponibili {m}.")
    rng = np.random.default_rng(seed)
    n_blocchi = int(np.ceil(mesi / block))
    out = np.empty((n, mesi, 2))
    for s in range(n):
        start = rng.integers(0, m - block + 1, size=n_blocchi)
        pe = np.concatenate([se[i:i + block] for i in start])[:mesi]
        pb = np.concatenate([sb[i:i + block] for i in start])[:mesi]
        out[s, :, 0] = pe
        out[s, :, 1] = pb
    return out


# ---------------------------------------------------------------------------
# GLIDEPATH DI DERISKING
# ---------------------------------------------------------------------------
def glidepath_mensile(mesi_tot, w_start, w_end, anno_inizio, anno_fine):
    """Quota azionaria target mese per mese: costante, poi rampa lineare, poi costante."""
    w = np.full(mesi_tot, w_start, dtype=float)
    m0 = max(0, (anno_inizio - 1) * 12)
    m1 = max(m0 + 1, anno_fine * 12)
    m1 = min(m1, mesi_tot)
    if m0 < mesi_tot and w_end != w_start:
        rampa = np.linspace(w_start, w_end, max(2, m1 - m0))
        w[m0:m0 + len(rampa)] = rampa[:max(0, mesi_tot - m0)]
        if m1 < mesi_tot:
            w[m1:] = w_end
    return np.clip(w, 0.0, 1.0)


# ---------------------------------------------------------------------------
# MOTORE DI SIMULAZIONE (vettorizzato sugli scenari, loop sui mesi)
# ---------------------------------------------------------------------------
def simula_pac_avanzato(paths, p):
    """
    paths: (n, mesi_tot, 2) rendimenti mensili [azionario, obbligazionario].
    p: dict di parametri (vedi render). Ritorna dict con storie e statistiche.

    Contabilita' per scenario (array shape (n,)):
      Ve/Vb  valore di mercato dei due bucket
      Be/Bb  costo fiscale (basis) dei due bucket, per la plusvalenza pro-quota
    """
    n, mesi_tot, _ = paths.shape
    mesi_acc = p["mesi_acc"]

    Ve = np.full(n, p["cap_iniziale"] * p["w_target"][0])
    Vb = np.full(n, p["cap_iniziale"] * (1.0 - p["w_target"][0]))
    Be, Bb = Ve.copy(), Vb.copy()

    tasse_cum = np.zeros(n)
    costi_cum = np.zeros(n)      # costi acquisto + transazione ribilanciamento
    bollo_cum = np.zeros(n)
    prelievi_netti_cum = np.zeros(n)
    fallito = np.zeros(n, dtype=bool)   # capitale esaurito in decumulo

    storia = np.empty((n, mesi_tot))
    ter_m = 1.0 - (1.0 - p["ter"]) ** (1.0 / 12.0)
    bollo_m = p["bollo_pct"] / 12.0

    def _vendi(V, B, importo, aliq):
        """Vende `importo` dal bucket (V,B): ritorna (netto, tassa) e aggiorna basis pro-quota."""
        importo = np.minimum(importo, V)
        with np.errstate(divide="ignore", invalid="ignore"):
            gain_frac = np.where(V > 0, np.clip((V - B) / V, 0.0, 1.0), 0.0)
        tassa = importo * gain_frac * aliq
        quota = np.where(V > 0, importo / np.maximum(V, 1e-12), 0.0)
        B *= (1.0 - quota)
        V -= importo
        return V, B, importo - tassa, tassa

    for t in range(mesi_tot):
        we = p["w_target"][t]
        in_acc = t < mesi_acc

        # 1) VERSAMENTO mensile (solo accumulo), al netto dei costi d'acquisto
        if in_acc:
            rata = p["rata_mensile"][t]
            if rata > 0:
                costo = p["costo_fisso_ordine"] + rata * p["costo_pct_ordine"]
                netto = max(0.0, rata - costo)
                costi_cum += (rata - netto)
                Ve += netto * we
                Vb += netto * (1.0 - we)
                Be += netto * we
                Bb += netto * (1.0 - we)

        # 2) RENDIMENTO di mercato del mese
        Ve *= (1.0 + paths[:, t, 0])
        Vb *= (1.0 + paths[:, t, 1])
        Ve = np.maximum(Ve, 0.0)
        Vb = np.maximum(Vb, 0.0)

        # 3) TER (se > 0) — costo ricorrente scaricato sul valore
        if ter_m > 0:
            Ve *= (1.0 - ter_m)
            Vb *= (1.0 - ter_m)

        # 4) IMPOSTA DI BOLLO 0,2%/anno pro-rata mensile sul controvalore
        if bollo_m > 0:
            tot = Ve + Vb
            imposta = tot * bollo_m
            bollo_cum += imposta
            with np.errstate(divide="ignore", invalid="ignore"):
                fe = np.where(tot > 0, Ve / np.maximum(tot, 1e-12), 0.0)
            Ve -= imposta * fe
            Vb -= imposta * (1.0 - fe)

        # 5) RIBILANCIAMENTO ogni N mesi, in base al VALORE delle quote
        if p["reb_attivo"] and ((t + 1) % p["reb_ogni_mesi"] == 0):
            tot = Ve + Vb
            target_e = tot * we
            delta = Ve - target_e     # >0: azionario sovrappesato
            # scostamento minimo opzionale per non ribilanciare per spiccioli
            attiva = np.abs(delta) > tot * p["reb_soglia"]
            # vendo azionario -> compro obbligazionario
            m1 = attiva & (delta > 0)
            if m1.any():
                imp = np.where(m1, delta, 0.0)
                Ve, Be, netto, tassa = _vendi(Ve, Be, imp, p["aliq_e"])
                c = netto * p["costo_trans_pct"]
                tasse_cum += tassa
                costi_cum += c
                Vb += netto - c
                Bb += netto - c
            # vendo obbligazionario -> compro azionario
            m2 = attiva & (delta < 0)
            if m2.any():
                imp = np.where(m2, -delta, 0.0)
                Vb, Bb, netto, tassa = _vendi(Vb, Bb, imp, p["aliq_b"])
                c = netto * p["costo_trans_pct"]
                tasse_cum += tassa
                costi_cum += c
                Ve += netto - c
                Be += netto - c

        # 6) DECUMULO: prelievo mensile lordo, pro-quota dai due bucket
        if not in_acc and p["decumulo"]:
            w_lordo = p["prelievo_mensile"][t - mesi_acc]
            tot = Ve + Vb
            vivo = (tot > 0) & ~fallito
            richiesta = np.where(vivo, np.minimum(w_lordo, tot), 0.0)
            fallito |= vivo & (tot < w_lordo)   # non copre il prelievo pieno
            with np.errstate(divide="ignore", invalid="ignore"):
                fe = np.where(tot > 0, Ve / np.maximum(tot, 1e-12), 0.0)
            Ve, Be, net_e, tax_e = _vendi(Ve, Be, richiesta * fe, p["aliq_e"])
            Vb, Bb, net_b, tax_b = _vendi(Vb, Bb, richiesta * (1.0 - fe), p["aliq_b"])
            tasse_cum += tax_e + tax_b
            prelievi_netti_cum += net_e + net_b

        storia[:, t] = Ve + Vb

    return {
        "storia": storia,
        "tasse_cum": tasse_cum,
        "costi_cum": costi_cum,
        "bollo_cum": bollo_cum,
        "prelievi_netti_cum": prelievi_netti_cum,
        "fallito": fallito,
    }


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def render_pac_avanzato(ctx):
    st.subheader("🧪 PAC avanzato — 2 asset, derisking, ribilanciamento, decumulo")
    st.caption(
        "Modello a due asset (Azionario/Obbligazionario) con covarianza alla "
        "Markowitz, motore Monte Carlo selezionabile (bootstrap storico o "
        "GBM-Cholesky con mean reversion), glidepath di derisking, "
        "ribilanciamento periodico sul valore delle quote (con tasse sul "
        "realizzato), bollo 0,2%, costi ETF opzionali e fase di decumulo. "
        "Curve anche deflazionate (euro reali). Non e' consulenza finanziaria."
    )

    durata = int(ctx["durata"])
    vp_serie = list(ctx.get("vp_serie") or [0.0] * durata)
    cap_iniziale = float(ctx.get("cap_iniziale_pac", 0.0))
    seed = int(st.session_state.get("master_seed", 33))

    # --- Precondizione: serve il portafoglio ticker gia' scaricato da Yahoo --
    # Nessun fallback parametrico "inventato": se manca, il tab si ferma qui.
    # Distinguo due casi ben diversi, così non nascondo il vero problema:
    #   a) il portafoglio ticker non e' stato configurato -> spiego come farlo
    #   b) e' configurato ma il download da Yahoo e' fallito (rete, rate
    #      limit, ticker non valido, storico comune troppo corto...) -> mostro
    #      l'errore VERO invece del generico "configuralo"
    errore_download = ctx.get("portafoglio_errore")
    usa_portafoglio_ctx = ctx.get("usa_portafoglio", False)
    stima = classifica_e_stima(ctx)
    if stima is None:
        if usa_portafoglio_ctx and errore_download:
            st.error(
                f"⚠️ Il portafoglio ticker è configurato ma il download dei "
                f"prezzi da Yahoo Finance è fallito: **{errore_download}**\n\n"
                f"Cause tipiche: nessuna connessione in uscita consentita "
                f"dall'ambiente di deploy, limite di richieste di Yahoo "
                f"raggiunto (riprova tra qualche minuto), un ticker scritto "
                f"male, o storico comune tra i ticker scelti troppo corto "
                f"(serve almeno un paio d'anni di mesi in comune). Controlla "
                f"anche la sezione **'📈 Portafoglio PAC a Ticker'** più in "
                f"alto nella pagina principale, che mostra lo stesso errore."
            )
        elif usa_portafoglio_ctx:
            st.warning(
                "⚠️ Il portafoglio ticker risulta configurato ma non ancora "
                "elaborato: aspetta il ricalcolo della pagina principale (a "
                "volte serve un secondo giro dopo aver cambiato i ticker), "
                "poi torna su questo tab."
            )
        else:
            st.warning(
                "⚠️ Questo modulo calcola TUTTI i parametri (rendimento, "
                "volatilità, correlazione) dai prezzi reali di Yahoo Finance — "
                "non propone assunzioni manuali. Configura prima il portafoglio "
                "in sidebar: **5. PAC (ETF)** → modalità **'Portafoglio ticker "
                "(dati storici)'**, seleziona almeno un ETF azionario e uno "
                "obbligazionario (es. dal catalogo, categoria 'Obbligazionario'), "
                "poi torna su questo tab."
            )
        return

    serie_e, serie_b = stima["serie_e"], stima["serie_b"]
    mu_e, sig_e, mu_b, sig_b, rho = (stima["mu_e"], stima["sig_e"],
                                     stima["mu_b"], stima["sig_b"], stima["rho"])

    st.caption(
        f"📊 Parametri stimati da **{stima['n_mesi']} mesi** di storico Yahoo — "
        f"azionario: {', '.join(stima['tickers_azionari'])} · "
        f"obbligazionario: {', '.join(stima['tickers_obblig'])}"
    )
    e1, e2, e3, e4, e5 = st.columns(5)
    e1.metric("μ Azionario", f"{mu_e*100:+.2f}%")
    e2.metric("σ Azionario", f"{sig_e*100:.2f}%")
    e3.metric("μ Obbligaz.", f"{mu_b*100:+.2f}%")
    e4.metric("σ Obbligaz.", f"{sig_b*100:.2f}%")
    e5.metric("ρ (correlazione)", f"{rho:+.2f}")

    c1, c2, c3 = st.columns(3)

    # --- Motore Monte Carlo -------------------------------------------------
    with c1:
        st.markdown("**Motore Monte Carlo**")
        motore = st.radio(
            "Generatore dei rendimenti", 
            ["GBM multivariato (Cholesky)", "Block-bootstrap storico"],
            key="pav_motore",
            help="**GBM-Cholesky**: genera rendimenti CASUALI da mu/sigma/rho "
                 "stimati sopra (assume che i rendimenti seguano una "
                 "distribuzione log-normale). **Block-bootstrap**: invece di "
                 "generare numeri, RIPESCA a blocchi mesi realmente accaduti "
                 "dallo storico Yahoo — non assume nessuna distribuzione "
                 "teorica, ma è limitato ai pattern già visti in passato "
                 "(es. non genera mai un crollo peggiore del peggiore "
                 "storico).",
        )
        usa_bootstrap = motore.startswith("Block")
        n_scen = st.slider(
            "Numero scenari", 200, 2000, 500, 100, key="pav_n",
            help="Quante traiettorie Monte Carlo simulare. Più scenari = "
                 "stime P10/P50/P90 più stabili ma calcolo più lento. 500 è "
                 "un buon compromesso; alza a 1500-2000 per un risultato "
                 "finale più preciso.",
        )
        if usa_bootstrap:
            block = st.number_input(
                "Lunghezza blocco (mesi)", 3, 36, 12, 1, key="pav_block",
                help="Periodo del blocco contiguo ricampionato dallo storico. "
                     "Le due serie sono pescate con gli STESSI indici: la "
                     "correlazione azionario/obbligazionario e' preservata.",
            )
            kappa = 0.0
        else:
            kappa = st.slider(
                "Mean reversion κ (per anno)", 0.0, 0.5, 0.10, 0.01, key="pav_kappa",
                help="0 = GBM puro. Valori > 0 richiamano il log-rendimento "
                     "cumulato verso il trend di lungo periodo (stile O-U): "
                     "riduce la probabilita' di scenari estremi persistenti.",
            )

    # --- Correttivo opzionale (solo sul rendimento atteso, spento di default) -
    with c2:
        st.markdown("**Correttivo (opzionale)**")
        if usa_bootstrap:
            st.caption(
                "Non disponibile col motore Block-bootstrap: lì i rendimenti "
                "sono ripescati direttamente dallo storico, non c'è un "
                "parametro mu da correggere. Passa a 'GBM multivariato' per "
                "usarlo."
            )
            override_on = False
        else:
            st.caption(
                "Spento di default: uso i valori stimati sopra. La media "
                "storica e' un cattivo stimatore del rendimento futuro — se "
                "vuoi puoi correggerla a mano, ma volatilità e correlazione "
                "restano SEMPRE quelle stimate dai dati (stesso principio "
                "del PAC a ticker)."
            )
            override_on = st.checkbox(
                "Correggi a mano il rendimento atteso", value=False, key="pav_override",
                help="Attivalo solo se hai una view specifica sul futuro (es. "
                     "'mi aspetto meno crescita azionaria dei prossimi anni "
                     "rispetto agli ultimi X anni di storico'). Cambia SOLO il "
                     "centro (mu) della distribuzione simulata: la forma della "
                     "dispersione (sigma, rho) resta quella osservata nei dati.",
            )
            if override_on:
                mu_e = st.slider(
                    "Rend. atteso Azionario corretto (%)", 0.0, 12.0,
                    round(mu_e * 100, 1), 0.1, key="pav_mue_ov",
                    help="Sostituisce il mu azionario stimato sopra in TUTTI "
                         "gli scenari generati da qui in poi.",
                ) / 100
                mu_b = st.slider(
                    "Rend. atteso Obbligaz. corretto (%)", 0.0, 8.0,
                    round(mu_b * 100, 1), 0.1, key="pav_mub_ov",
                    help="Come sopra, ma per il bucket obbligazionario.",
                ) / 100

    # --- Allocazione, derisking, ribilanciamento -----------------------------
    with c3:
        st.markdown("**Allocazione & derisking**")
        st.caption(
            "Qui NON stimo nulla dai dati: quanto rischio prendere è una "
            "scelta di policy personale, non un fatto statistico. Il "
            "**derisking** (o *glidepath*) è la prassi di ridurre "
            "gradualmente la quota azionaria mano a mano che ci si avvicina "
            "al momento di iniziare a prelevare, per limitare il "
            "*sequence-of-returns risk*: un crollo di mercato proprio negli "
            "ultimi anni di accumulo/primi di decumulo costringe a vendere "
            "quote a prezzi bassi, un danno che il tempo poi non recupera "
            "più (a differenza di un crollo a inizio carriera, che il PAC "
            "assorbe comprando a sconto per anni)."
        )
        eta_rif = st.number_input(
            "Età attuale (opzionale, solo per il suggerimento sotto)",
            0, 100, 0, 1, key="pav_eta",
            help="Se la imposti, sotto vedi cosa suggerirebbe la regola "
                 "pratica 'quota obbligazionaria ≈ età' (una convenzione "
                 "diffusa in finanza personale, non una legge: è un punto "
                 "di partenza da adattare alla tua tolleranza al rischio).",
        )
        if eta_rif > 0:
            sugg_w0 = max(0.0, min(1.0, 1 - eta_rif / 100))
            sugg_w1 = max(0.0, min(1.0, 1 - (eta_rif + durata) / 100))
            st.caption(
                f"💡 Regola pratica 'quota obbligazionaria ≈ età': oggi "
                f"suggerirebbe **{sugg_w0*100:.0f}%** azionario, a fine "
                f"accumulo (tra {durata} anni, età {eta_rif+durata}) "
                f"**{sugg_w1*100:.0f}%** azionario. Puoi impostare questi "
                f"valori sotto o ignorarli."
            )
        w0 = st.slider(
            "Quota azionaria iniziale (%)", 0, 100, 80, 5, key="pav_w0",
            help="Allocazione azionaria a inizio simulazione. Più alta = più "
                 "crescita attesa nel lungo periodo ma oscillazioni più "
                 "ampie anno per anno. 80% è un valore tipico per un "
                 "orizzonte lungo (accumulo appena iniziato).",
        ) / 100
        w1 = st.slider(
            "Quota azionaria finale (%)", 0, 100, 40, 5, key="pav_w1",
            help="Allocazione azionaria raggiunta alla fine della rampa (e "
                 "mantenuta per tutto l'eventuale decumulo). Più bassa = "
                 "meno crescita attesa ma meno rischio di dover vendere in "
                 "perdita quando inizi a prelevare. 40% è un livello "
                 "prudenziale tipico in prossimità della pensione.",
        ) / 100
        a0 = st.number_input(
            "Derisking: dall'anno", 1, durata, max(1, durata - 10), key="pav_a0",
            help="Anno di simulazione in cui INIZIA la riduzione graduale "
                 "della quota azionaria (1 = subito, primo anno).",
        )
        a1 = st.number_input(
            "Derisking: fino all'anno", int(a0), durata, durata, key="pav_a1",
            help="Anno in cui la rampa TERMINA: da qui la quota resta fissa "
                 "al valore finale impostato sopra, anche durante il "
                 "decumulo. Deve essere ≥ dell'anno di inizio.",
        )
        _w_preview = glidepath_mensile(durata * 12, w0, w1, int(a0), int(a1))
        _fig_glide = go.Figure()
        _fig_glide.add_trace(go.Scatter(
            x=list(np.arange(1, durata * 12 + 1) / 12.0), y=_w_preview * 100,
            line=dict(color="#2a78d6", width=3), name="Quota azionaria",
            fill="tozeroy", fillcolor="rgba(42,120,214,0.10)",
        ))
        _fig_glide.update_layout(
            height=180, margin=dict(l=10, r=10, t=10, b=30),
            xaxis_title="Anni", yaxis_title="% azionario",
            yaxis_range=[0, 100], showlegend=False,
        )
        st.plotly_chart(_fig_glide, use_container_width=True,
                        config={"displayModeBar": False})

    d1, d2, d3 = st.columns(3)

    with d1:
        st.markdown("**Ribilanciamento**")
        reb_attivo = st.checkbox(
            "Ribilancia periodicamente", True, key="pav_reb",
            help="Se attivo, ogni N mesi riporta i pesi azionario/"
                 "obbligazionario al target del glidepath, vendendo il "
                 "bucket sovrappesato. Se disattivo, il portafoglio 'deriva' "
                 "liberamente in base a come si muovono i mercati (nessuna "
                 "vendita, nessuna tassa sul realizzato in fase di "
                 "accumulo).",
        )
        reb_ogni = st.number_input(
            "Ogni quanti mesi", 1, 60, 12, 1, key="pav_rebm",
            help="Riporta i pesi al target del glidepath in base al valore "
                 "corrente delle quote.", disabled=not reb_attivo,
        )
        reb_soglia = st.slider(
            "Soglia minima di scostamento (%)", 0.0, 10.0, 1.0, 0.5, key="pav_rebsoglia",
            help="Non ribilancia se lo scostamento dal target e' sotto questa "
                 "% del portafoglio (evita micro-vendite tassate).",
            disabled=not reb_attivo,
        ) / 100
        costo_trans = st.number_input(
            "Costo transazione ribilanciamento (%)", 0.0, 2.0, 0.0, 0.05,
            key="pav_ctrans", help="Se non impostato vale 0.",
        ) / 100

    with d2:
        st.markdown("**Costi & fisco**")
        ter = st.number_input(
            "TER ETF (%/anno)", 0.0, 2.0, 0.0, 0.01, key="pav_ter",
            help="Costo ricorrente degli ETF. Default 0: se il rendimento che "
                 "usi e' gia' netto di TER (es. stimato dai prezzi), lascialo a 0 "
                 "per non contarlo due volte.",
        ) / 100
        costo_fisso_ord = st.number_input(
            "Costo d'acquisto fisso (€/ordine)", 0.0, 50.0, 0.0, 0.5, key="pav_cfix",
            help="Commissione fissa del broker su ogni rata mensile. Default 0.",
        )
        costo_pct_ord = st.number_input(
            "Costo d'acquisto (%/ordine)", 0.0, 2.0, 0.0, 0.05, key="pav_cpct",
            help="Commissione percentuale su ogni rata mensile. Default 0.",
        ) / 100
        bollo_on = st.checkbox(
            "Imposta di bollo 0,2%/anno", True, key="pav_bollo",
            help="Imposta di bollo italiana sui prodotti finanziari (0,2% "
                 "annuo sul controvalore del portafoglio, applicata qui "
                 "pro-rata ogni mese). Si applica a conti titoli/ETF; "
                 "disattivala solo se sai che nel tuo caso non si applica.",
        )
        aliq = st.slider(
            "Aliquota plusvalenze (%)", 0, 26, 26, key="pav_aliq",
            help="Aliquota ordinaria italiana sulle plusvalenze da ETF "
                 "armonizzati: 26%. Si applica solo alla PARTE di plusvalenza "
                 "quando vendi (ribilanciamento o prelievo in decumulo), non "
                 "sull'intero importo venduto.",
        )
        bond_125 = st.checkbox(
            "12,5% sul bucket obbligazionario", False, key="pav_b125",
            help="Approssimazione: tratta l'obbligazionario come titoli di "
                 "Stato/white list (aliquota ridotta). La quota esatta va "
                 "verificata sulla documentazione fiscale dello strumento.",
        )

    with d3:
        st.markdown("**Decumulo & inflazione**")
        decumulo = st.checkbox(
            "Aggiungi fase di decumulo", True, key="pav_dec",
            help="Se attivo, dopo gli anni di accumulo il PAC entra in una "
                 "fase di prelievo mensile: niente più versamenti, si vende "
                 "invece per generare una rendita. Se disattivo, la "
                 "simulazione si ferma alla fine dell'accumulo (solo "
                 "montante finale, nessun prelievo).",
        )
        anni_dec = st.number_input(
            "Anni di decumulo", 1, 40, 25, 1, key="pav_decanni",
            disabled=not decumulo,
            help="Durata della fase di prelievo, es. dagli anni di pensione "
                 "fino all'aspettativa di vita attesa. Più lunga = prelievo "
                 "totale maggiore da coprire, quindi probabilità di "
                 "successo più bassa a parità di montante.",
        )
        prelievo0 = st.number_input(
            "Prelievo mensile LORDO (€)", 0.0, 20000.0, 1500.0, 50.0,
            key="pav_prel", disabled=not decumulo,
            help="Prelievo prima della tassa sulla plusvalenza incorporata "
                 "(pro-quota sul costo medio). Il netto percepito e' riportato "
                 "nei risultati.",
        )
        prelievo_indicizzato = st.checkbox(
            "Indicizza il prelievo all'inflazione", True, key="pav_previdx",
            disabled=not decumulo,
        )
        inflazione = st.slider(
            "Inflazione per la deflazione (%)", 0.0, 5.0, 2.0, 0.1, key="pav_infl",
            help="Usata per esprimere il montante in euro REALI (potere "
                 "d'acquisto di oggi) e per indicizzare il prelievo.",
        ) / 100

    # -------------------------------------------------------------------------
    # COSTRUZIONE E SIMULAZIONE
    # -------------------------------------------------------------------------
    mesi_acc = durata * 12
    mesi_dec = (int(anni_dec) * 12) if decumulo else 0
    mesi_tot = mesi_acc + mesi_dec

    w_target = glidepath_mensile(mesi_tot, w0, w1, int(a0), int(a1))
    if mesi_dec:
        w_target[mesi_acc:] = w1   # in decumulo resta l'allocazione finale

    rata_mensile = np.repeat(np.asarray(vp_serie, dtype=float) / 12.0, 12)[:mesi_acc]

    if decumulo and mesi_dec:
        idx = np.arange(mesi_dec)
        fattore = (1 + inflazione) ** ((mesi_acc + idx) / 12.0) if prelievo_indicizzato else 1.0
        prelievo_serie = prelievo0 * (fattore if np.ndim(fattore) else np.ones(mesi_dec))
    else:
        prelievo_serie = np.zeros(0)

    try:
        if usa_bootstrap:
            paths = genera_bootstrap_congiunto(serie_e, serie_b, mesi_tot,
                                               n_scen, int(block), seed + 500)
        else:
            paths = genera_gbm_cholesky(mu_e, sig_e, mu_b, sig_b, rho,
                                        mesi_tot, n_scen, seed + 500, kappa=kappa)
    except ValueError as e:
        st.error(f"Impossibile generare gli scenari: {e}")
        return

    p = dict(
        mesi_acc=mesi_acc, cap_iniziale=cap_iniziale, w_target=w_target,
        rata_mensile=rata_mensile,
        reb_attivo=reb_attivo, reb_ogni_mesi=int(reb_ogni), reb_soglia=reb_soglia,
        costo_trans_pct=costo_trans, ter=ter,
        costo_fisso_ordine=costo_fisso_ord, costo_pct_ordine=costo_pct_ord,
        bollo_pct=0.002 if bollo_on else 0.0,
        aliq_e=aliq / 100.0, aliq_b=(0.125 if bond_125 else aliq / 100.0),
        decumulo=bool(decumulo and mesi_dec), prelievo_mensile=prelievo_serie,
    )
    res = simula_pac_avanzato(paths, p)

    # -------------------------------------------------------------------------
    # RISULTATI
    # -------------------------------------------------------------------------
    storia = res["storia"]
    mesi_x = np.arange(1, mesi_tot + 1) / 12.0
    defl = (1 + inflazione) ** (-mesi_x)     # deflatore (euro reali di oggi)

    p10 = np.percentile(storia, 10, axis=0)
    p50 = np.percentile(storia, 50, axis=0)
    p90 = np.percentile(storia, 90, axis=0)
    p50_reale = p50 * defl

    fine_acc = mesi_acc - 1
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Fine accumulo — P50 nominale", f"€ {p50[fine_acc]:,.0f}",
              help=f"P10 € {p10[fine_acc]:,.0f} · P90 € {p90[fine_acc]:,.0f}")
    k2.metric("Fine accumulo — P50 reale", f"€ {p50_reale[fine_acc]:,.0f}",
              help="Deflazionato: potere d'acquisto di oggi.")
    if p["decumulo"]:
        successo = 100.0 * (1.0 - res["fallito"].mean())
        k3.metric("Prob. successo decumulo", f"{successo:.1f}%",
                  help="Quota di scenari in cui il capitale copre TUTTI i "
                       "prelievi fino alla fine del decumulo.")
        k4.metric("Prelievi netti totali (P50)",
                  f"€ {np.median(res['prelievi_netti_cum']):,.0f}")
    else:
        k3.metric("Tasse ribilanciamento (P50)", f"€ {np.median(res['tasse_cum']):,.0f}")
        k4.metric("Bollo cumulato (P50)", f"€ {np.median(res['bollo_cum']):,.0f}")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(mesi_x) + list(mesi_x[::-1]), y=list(p90) + list(p10[::-1]),
        fill="toself", fillcolor="rgba(155,89,182,0.12)",
        line=dict(color="rgba(0,0,0,0)"), name="P10–P90", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(x=mesi_x, y=p50, name="P50 nominale",
                             line=dict(color="#9b59b6", width=3)))
    fig.add_trace(go.Scatter(x=mesi_x, y=p50_reale, name="P50 reale (deflazionato)",
                             line=dict(color="#2a78d6", width=2, dash="dash")))
    if p["decumulo"]:
        fig.add_vline(x=durata, line_dash="dot", line_color="#888",
                      annotation_text="fine accumulo / inizio decumulo")
    fig.update_layout(xaxis_title="Anni", yaxis_title="Montante PAC (€)",
                      yaxis_tickformat="€,.0f", hovermode="x unified", height=440,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig, use_container_width=True)

    # Tabella costi/tasse cumulati mediani
    df_sintesi = pd.DataFrame({
        "Voce": ["Tasse su ribilanciamento/prelievi", "Imposta di bollo",
                 "Costi acquisto + transazione"],
        "Cumulato P50 (€)": [np.median(res["tasse_cum"]),
                             np.median(res["bollo_cum"]),
                             np.median(res["costi_cum"])],
    })
    st.dataframe(df_sintesi.style.format({"Cumulato P50 (€)": "€ {:,.0f}"}),
                 use_container_width=True, hide_index=True)
    st.caption(
        "La banda P10–P90 riflette solo l'incertezza dei rendimenti simulati. "
        "Le tasse sul realizzato usano la plusvalenza pro-quota sul costo "
        "medio: e' un'approssimazione del regime fiscale reale (che ragiona "
        "per lotti/minusvalenze compensabili). Stima illustrativa, non "
        "consulenza fiscale o finanziaria."
    )


# ---------------------------------------------------------------------------
# SERIE STORICHE E PARAMETRI STIMATI DAL PORTAFOGLIO TICKER (Yahoo Finance)
# ---------------------------------------------------------------------------
def classifica_e_stima(ctx):
    """
    Unica fonte di verita' per ENTRAMBI i motori Monte Carlo: nessun numero
    e' inventato, tutto arriva dal portafoglio ticker gia' scaricato da
    Yahoo Finance in sidebar (ctx["portafoglio_info"]["prezzi_df"]).

    1) L'utente classifica i ticker in Azionario/Obbligazionario (preseleziona
       automaticamente in base al nome, es. "bond"/"obblig"/"government").
    2) Le due serie mensili di classe sono le medie equal-weight dei
       rendimenti mensili dei ticker di ciascun bucket.
    3) Da queste due serie si stimano mu, sigma (annualizzati) e rho
       (correlazione), esattamente come stima_parametri_portafoglio fa per
       il PAC "Semplice" — stessa metodologia, stessa fonte dati.

    Ritorna un dict con serie_e, serie_b (mensili, per il bootstrap) e
    mu_e, sig_e, mu_b, sig_b, rho, n_mesi (per il GBM-Cholesky), oppure
    None se il portafoglio ticker non e' disponibile/valido — in quel caso
    il chiamante deve fermarsi, NON deve inventare parametri di ripiego.
    """
    pi = ctx.get("portafoglio_info")
    if pi is None or "prezzi_df" not in pi:
        return None

    prezzi = pi["prezzi_df"]
    rend = prezzi.pct_change().dropna()
    tickers = list(rend.columns)
    nomi = ctx.get("ticker_to_nome", {})
    etichette = [f"{t} — {nomi.get(t, t)}" for t in tickers]
    default_bond = [e for e, t in zip(etichette, tickers)
                    if any(k in nomi.get(t, "").lower()
                           for k in ("bond", "obblig", "aggregate", "government"))]
    sel = st.multiselect(
        "Ticker OBBLIGAZIONARI del tuo portafoglio (gli altri contano come "
        "azionari)", etichette, default=default_bond, key="pav_bondsel",
        help="Preselezione automatica in base al nome dello strumento. "
             "Correggi se necessario: la classificazione determina le due "
             "serie usate per stimare mu/sigma/rho, per ENTRAMBI i motori.",
    )
    bond_idx = [etichette.index(e) for e in sel]
    eq_idx = [i for i in range(len(tickers)) if i not in bond_idx]
    if not eq_idx or not bond_idx:
        st.warning("⚠️ Servono ALMENO un ticker azionario e uno obbligazionario "
                   "nel portafoglio per il modello a 2 asset.")
        return None

    serie_e = rend.iloc[:, eq_idx].mean(axis=1).values
    serie_b = rend.iloc[:, bond_idx].mean(axis=1).values
    m = min(len(serie_e), len(serie_b))
    serie_e, serie_b = serie_e[-m:], serie_b[-m:]

    mu_e = float((1.0 + serie_e.mean()) ** 12 - 1.0)
    mu_b = float((1.0 + serie_b.mean()) ** 12 - 1.0)
    sig_e = float(serie_e.std(ddof=1) * np.sqrt(12.0))
    sig_b = float(serie_b.std(ddof=1) * np.sqrt(12.0))
    rho = float(np.corrcoef(serie_e, serie_b)[0, 1])

    return {
        "serie_e": serie_e, "serie_b": serie_b, "n_mesi": m,
        "mu_e": mu_e, "sig_e": sig_e, "mu_b": mu_b, "sig_b": sig_b, "rho": rho,
        "tickers_azionari": [tickers[i] for i in eq_idx],
        "tickers_obblig": [tickers[i] for i in bond_idx],
    }
