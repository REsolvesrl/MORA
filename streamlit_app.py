import streamlit as st
from datetime import date
from dateutil.relativedelta import relativedelta

# ==========================================================
# 1. TABELLE DI CONFIGURAZIONE
# ==========================================================

# Tassi legali ex art. 1284 c.c. (variano ogni 1° gennaio)
TASSI_LEGALI = {
    2005: 0.0250, 2006: 0.0250, 2007: 0.0250, 2008: 0.0300, 2009: 0.0300,
    2010: 0.0100, 2011: 0.0150, 2012: 0.0250, 2013: 0.0250, 2014: 0.0100,
    2015: 0.0050, 2016: 0.0020, 2017: 0.0010, 2018: 0.0030, 2019: 0.0080,
    2020: 0.0005, 2021: 0.0001, 2022: 0.0125, 2023: 0.0500, 2024: 0.0250,
    2025: 0.0200, 2026: 0.0160,
}
TASSO_LEGALE_DEFAULT = 0.0160  # fallback per anni non in tabella

# Mappa frequenza -> mesi da sommare
FREQUENZA_MESI = {
    "Mensile": 1,
    "Trimestrale": 3,
    "Semestrale": 6,
}

# Parametri forfettari spese esecutive (modificabili)
SPESE_IMMOBILIARE = {
    "spese_vive": 800.0,        # CU, trascrizioni, note
    "ctu": 3500.0,              # consulenza tecnica d'ufficio (aggiornato)
    "custode_delegato": 4000.0, # o 3% del valore se maggiore
    "perc_custode": 0.03,
    "pubblicita": 1500.0,       # pubblicità sul PVP (aggiornato)
    "spese_legali_nostre": 2600.0,  # NUOVA VOCE
}
SPESE_MOBILIARE = {
    "spese_vive": 150.0,
    "ufficiale_legali": 500.0,
    "spese_legali_nostre": 2600.0,  # NUOVA VOCE
}

# Costi di acquisizione credito NPL (modificabili)
COSTI_ACQUISIZIONE = {
    "fronting": 8000.0,
    "notaio": 2000.0,
    "servicer": 5000.0,
    "advisors": 10000.0,
}

# ==========================================================
# 2. FUNZIONI DI UTILITÀ TEMPORALE
# ==========================================================

def giorni_tra(d1, d2):
    """Numero di giorni tra due date."""
    return (d2 - d1).days

def interesse_semplice(capitale, tasso_annuo, giorni, base_anno=365):
    """
    Calcolo interesse SEMPLICE (no anatocismo - art. 1283 c.c.).
    Formula: C * i * (gg / base)
    """
    if giorni <= 0 or capitale <= 0:
        return 0.0
    return capitale * tasso_annuo * (giorni / base_anno)

def tasso_legale_per_anno(anno):
    """Restituisce il tasso legale vigente in un dato anno."""
    return TASSI_LEGALI.get(anno, TASSO_LEGALE_DEFAULT)

def interesse_legale_pro_rata(capitale, data_inizio, data_fine):
    """
    Calcola interessi al tasso legale spezzando il periodo
    ad ogni 1° gennaio (pro-rata temporis).
    """
    totale = 0.0
    cursore = data_inizio
    while cursore < data_fine:
        prossimo_capodanno = date(cursore.year + 1, 1, 1)
        fine_segmento = min(prossimo_capodanno, data_fine)
        gg = giorni_tra(cursore, fine_segmento)
        tasso = tasso_legale_per_anno(cursore.year)
        totale += interesse_semplice(capitale, tasso, gg)
        cursore = fine_segmento
    return totale

def genera_rate_scadute(importo_rata, data_prima_rata, frequenza, data_limite):
    """
    Auto-genera le date delle rate scadute partendo dalla prima rata
    e sommando i mesi (in base alla frequenza), fermandosi alla data_limite
    (= Data Decadenza Effettiva). Il numero di rate è calcolato in automatico.
    """
    mesi = FREQUENZA_MESI[frequenza]
    rate = []
    cursore = data_prima_rata
    while cursore < data_limite:
        rate.append({"importo": importo_rata, "data_scadenza": cursore})
        cursore = cursore + relativedelta(months=mesi)
    return rate

# ==========================================================
# 3. CALCOLO ANNATE IPOTECARIE (Art. 2855 c.c.)
# ==========================================================

def calcola_triennio(data_stipula, data_pignoramento):
    """
    Individua l'annata ipotecaria in corso al pignoramento.
    Le annate decorrono dal giorno/mese di stipula.
    """
    anni_trascorsi = data_pignoramento.year - data_stipula.year
    inizio_annata_corrente = data_stipula + relativedelta(years=anni_trascorsi)
    if inizio_annata_corrente > data_pignoramento:
        inizio_annata_corrente -= relativedelta(years=1)

    fine_annata_corrente = inizio_annata_corrente + relativedelta(years=1)
    inizio_triennio = inizio_annata_corrente - relativedelta(years=2)

    return inizio_triennio, inizio_annata_corrente, fine_annata_corrente

# ==========================================================
# 4. RIPARTIZIONE IPOTECARIO / CHIROGRAFARIO (Art. 2855 c.c.)
#    >>> CUORE UNICO DEL CALCOLO <<<
# ==========================================================

def ripartisci_credito(capitale, tasso_mora, data_inizio_mora,
                       data_stipula, data_pignoramento, data_fine):
    """
    Filtro Art. 2855 c.c. applicato a una "voce" di interessi (rata o capitale).
    Divide gli interessi in:
    - PRE-TRIENNIO: chirografario @ tasso mora
    - TRIENNIO: ipotecario @ tasso mora
    - POST-TRIENNIO: ipotecario @ tasso legale + chirografario (differenza)
    """
    inizio_triennio, inizio_annata_pign, fine_annata_pign = calcola_triennio(
        data_stipula, data_pignoramento
    )

    risultato = {"ipotecario": 0.0, "chirografario": 0.0, "dettaglio": {}}

    # --- PRE-TRIENNIO (chirografario @ mora) ---
    if data_inizio_mora < inizio_triennio:
        fine_pre = min(inizio_triennio, data_fine)
        gg = giorni_tra(data_inizio_mora, fine_pre)
        int_pre = interesse_semplice(capitale, tasso_mora, gg)
        risultato["chirografario"] += int_pre
        risultato["dettaglio"]["pre_triennio_chiro"] = int_pre

    # --- TRIENNIO (ipotecario @ mora) ---
    inizio_t = max(data_inizio_mora, inizio_triennio)
    fine_t = min(fine_annata_pign, data_fine)
    if fine_t > inizio_t:
        gg = giorni_tra(inizio_t, fine_t)
        int_triennio = interesse_semplice(capitale, tasso_mora, gg)
        risultato["ipotecario"] += int_triennio
        risultato["dettaglio"]["triennio_ipo_mora"] = int_triennio

    # --- POST-TRIENNIO (ipotecario @ legale, chiro = differenza) ---
    inizio_post = max(data_inizio_mora, fine_annata_pign)
    if data_fine > inizio_post:
        int_legale = interesse_legale_pro_rata(capitale, inizio_post, data_fine)
        gg = giorni_tra(inizio_post, data_fine)
        int_mora_post = interesse_semplice(capitale, tasso_mora, gg)

        risultato["ipotecario"] += int_legale
        risultato["chirografario"] += (int_mora_post - int_legale)
        risultato["dettaglio"]["post_ipo_legale"] = int_legale
        risultato["dettaglio"]["post_chiro_diff"] = int_mora_post - int_legale

    return risultato

def _accumula(totale, parziale, chiave_dettaglio):
    """Helper: somma un risultato parziale nel totale e registra il dettaglio.
    Accumula inoltre le 4 voci della tripartizione ex art. 2855 c.c."""
    totale["ipotecario"] += parziale["ipotecario"]
    totale["chirografario"] += parziale["chirografario"]
    totale["dettaglio"][chiave_dettaglio] = parziale["dettaglio"]

    # --- Accumulo voci Art. 2855 c.c. ---
    d = parziale["dettaglio"]
    totale["voci_2855"]["pre_chiro"]    += d.get("pre_triennio_chiro", 0.0)
    totale["voci_2855"]["triennio_ipo"] += d.get("triennio_ipo_mora", 0.0)
    totale["voci_2855"]["post_ipo"]     += d.get("post_ipo_legale", 0.0)
    totale["voci_2855"]["post_chiro"]   += d.get("post_chiro_diff", 0.0)
    return totale

# ==========================================================
# 5. MOTORE UNIFICATO DI CALCOLO (CASO A e CASO B insieme)
# ==========================================================

def calcola_mora_unificato(importo_rata, data_prima_rata, frequenza,
                           capitale_residuo, tasso_mora,
                           data_decadenza_effettiva,
                           data_stipula, data_pignoramento, data_fine):
    """
    MOTORE UNICO valido sia per CASO A (Lettera DBT) che CASO B (Precetto).
    L'unica differenza tra i due casi è 'data_decadenza_effettiva':
        - CASO A -> Data Lettera DBT
        - CASO B -> Data Notifica Precetto

    FASE 1 (Rate): da 'data_prima_rata' a 'data_decadenza_effettiva'.
        Mora su ogni singola rata, dalla sua scadenza fino alla decadenza.
    FASE 2 (Capitale): da 'data_decadenza_effettiva' a 'data_fine'.
        Mora sull'INTERO capitale residuo.

    Entrambe le fasi passano per il filtro Art. 2855 c.c.
    """
    totale = {
        "ipotecario": 0.0,
        "chirografario": 0.0,
        "dettaglio": {},
        # --- Contatore tripartizione Art. 2855 c.c. ---
        "voci_2855": {
            "pre_chiro": 0.0,
            "triennio_ipo": 0.0,
            "post_ipo": 0.0,
            "post_chiro": 0.0,
        },
    }

    # ---------- FASE 1: rate scadute fino alla decadenza ----------
    rate_scadute = genera_rate_scadute(
        importo_rata, data_prima_rata, frequenza, data_decadenza_effettiva
    )

    dettaglio_fase1 = {
        "numero_rate_generate": len(rate_scadute),
        "rate": {}
    }

    for i, rata in enumerate(rate_scadute):
        rip = ripartisci_credito(
            capitale=rata["importo"],
            tasso_mora=tasso_mora,
            data_inizio_mora=rata["data_scadenza"],
            data_stipula=data_stipula,
            data_pignoramento=data_pignoramento,
            data_fine=data_decadenza_effettiva   # <-- la rata corre fino alla decadenza
        )
        totale["ipotecario"] += rip["ipotecario"]
        totale["chirografario"] += rip["chirografario"]

        # --- Accumulo voci Art. 2855 c.c. anche per ogni rata ---
        d = rip["dettaglio"]
        totale["voci_2855"]["pre_chiro"]    += d.get("pre_triennio_chiro", 0.0)
        totale["voci_2855"]["triennio_ipo"] += d.get("triennio_ipo_mora", 0.0)
        totale["voci_2855"]["post_ipo"]     += d.get("post_ipo_legale", 0.0)
        totale["voci_2855"]["post_chiro"]   += d.get("post_chiro_diff", 0.0)

        dettaglio_fase1["rate"][
            f"rata_{i+1}_({rata['data_scadenza'].strftime('%d/%m/%Y')})"
        ] = rip["dettaglio"]

    totale["dettaglio"]["FASE_1_rate"] = dettaglio_fase1

    # ---------- FASE 2: intero capitale residuo dalla decadenza ----------
    rip_fase2 = ripartisci_credito(
        capitale=capitale_residuo,
        tasso_mora=tasso_mora,
        data_inizio_mora=data_decadenza_effettiva,  # <-- parte dalla decadenza
        data_stipula=data_stipula,
        data_pignoramento=data_pignoramento,
        data_fine=data_fine
    )
    totale = _accumula(totale, rip_fase2, "FASE_2_capitale_residuo")

    return totale

# ==========================================================
# 6. LOGICA SPESE ESECUTIVE (PREVISIONE COSTI FUTURI)
# ==========================================================

def stima_spese_esecutive(tipo_procedura, valore_bene):
    """
    Stima forfettaria dei costi di una procedura esecutiva.
    Ritorna un dizionario con le singole voci e il totale.
    Valori indicativi: verificare sempre col foro competente.
    """
    voci = {}

    if tipo_procedura == "Pignoramento Immobiliare":
        p = SPESE_IMMOBILIARE
        custode = max(p["custode_delegato"], valore_bene * p["perc_custode"])
        voci = {
            "Spese vive (CU, trascrizioni, note)": p["spese_vive"],
            "CTU (perizia di stima)": p["ctu"],
            "Custode / Professionista delegato": custode,
            "Pubblicità (PVP)": p["pubblicita"],
            "Nostre spese legali": p["spese_legali_nostre"],
        }
    else:  # Mobiliare / Presso Terzi
        p = SPESE_MOBILIARE
        voci = {
            "Spese vive (notifica, bolli)": p["spese_vive"],
            "Ufficiale Giudiziario / Legali": p["ufficiale_legali"],
            "Nostre spese legali": p["spese_legali_nostre"],
        }

    totale = sum(voci.values())
    return voci, totale

# ==========================================================
# 7. INTERFACCIA STREAMLIT
# ==========================================================

st.set_page_config(page_title="Calcolo Interessi di Mora", layout="wide")

# ---- Stile: tab più grandi e visibili (dark/light mode compatibili) ----
st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 55px;
        padding: 0px 28px;
        background-color: rgba(128, 128, 128, 0.15);
        border: 1px solid rgba(128, 128, 128, 0.4);
        border-radius: 10px 10px 0px 0px;
        font-size: 18px;
        font-weight: 600;
        color: inherit;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background-color: rgba(255, 75, 75, 0.25);
        color: inherit;
    }
    .stTabs [aria-selected="true"] {
        background-color: #ff4b4b;
        color: white !important;
        border: 1px solid #ff4b4b;
    }
    </style>
""", unsafe_allow_html=True)

st.title("⚖️ Calcolo Interessi di Mora – Ipotecario / Chirografario")
st.caption("Strumento di supporto. Verificare sempre i risultati. Interesse semplice (art. 1283 c.c.).")

# ---- Sidebar: parametri comuni ----
with st.sidebar:
    st.header("Parametri generali")
    tasso_mora = st.number_input("Tasso di mora (%)", min_value=0.0, value=8.0, step=0.1) / 100

    st.divider()
    st.subheader("Date comuni")
    data_stipula = st.date_input("Data stipula mutuo", value=date(2018, 6, 15),
                                 format="DD/MM/YYYY")
    data_pignoramento = st.date_input("Data pignoramento", value=date(2023, 9, 10),
                                      format="DD/MM/YYYY")
    data_fine = st.date_input("Data fine calcolo (Decreto Trasf.)", value=date.today(),
                              format="DD/MM/YYYY")

    st.divider()
    st.subheader("Evento di decadenza")
    caso = st.radio(
        "Quale atto ha generato la decadenza dal beneficio del termine?",
        options=["CASO A – Lettera DBT", "CASO B – Notifica Precetto"],
        index=0,
    )
    is_caso_A = caso.startswith("CASO A")

# ==========================================================
# TAB PRINCIPALI
# ==========================================================
tab1, tab2, tab3 = st.tabs([
    "📊 Auditing e Check GBV",
    "🔮 Previsione Spese Esecutive",
    "🤝 Acquisto Credito (NPL) e Stralcio",
])

# ----------------------------------------------------------
# TAB 1 — AUDITING E CHECK GBV
# ----------------------------------------------------------
with tab1:
    st.subheader("📋 Dati del piano e del credito")
    c1, c2, c3 = st.columns(3)
    importo_rata = c1.number_input(
        "Importo singola rata (€)",
        min_value=0.0,
        value=800.0,
        step=50.0,
        help="Inserire l'intero importo della rata scaduta (Quota Capitale + Quota Interessi)"
    )
    data_prima_rata = c2.date_input("Data scadenza PRIMA rata insoluta",
                                    value=date(2021, 3, 1),
                                    format="DD/MM/YYYY")
    frequenza = c3.selectbox("Frequenza rate",
                             options=list(FREQUENZA_MESI.keys()), index=0)

    c4, c5 = st.columns(2)
    capitale_residuo = c4.number_input(
        "Capitale Residuo cristallizzato (€)",
        min_value=0.0,
        value=100000.0,
        step=1000.0,
        help="Intero capitale esigibile alla data di decadenza/precetto. "
             "Su questo importo decorre la mora dalla decadenza in poi. "
             "Le rate insolute pre-decadenza contribuiscono SOLO con i loro interessi."
    )

    # ---- Campo dinamico in base al caso ----
    if is_caso_A:
        data_decadenza_effettiva = c5.date_input(
            "📩 Data Lettera DBT",
            value=date(2022, 1, 20),
            format="DD/MM/YYYY",
            help="Data della comunicazione di decadenza dal beneficio del termine."
        )
    else:
        data_decadenza_effettiva = c5.date_input(
            "📜 Data Notifica Precetto",
            value=date(2023, 2, 1),
            format="DD/MM/YYYY",
            help="In assenza di DBT, la decadenza decorre dalla notifica del precetto."
        )

      # ---- GBV dichiarato + voci secondarie ----
    gbv_dichiarato = st.number_input(
        "🏦 GBV Dichiarato dal Creditore (€)",
        min_value=0.0,
        value=0.0,
        step=1000.0,
        help="Importo complessivo (Gross Book Value) richiesto dalla banca/cessionario. "
             "Lascia 0 per saltare il check di congruità."
    )

    # 🆕 Data di attualizzazione del GBV (appare solo se GBV > 0)
    if gbv_dichiarato > 0:
        data_attualizzazione_gbv = st.date_input(
            "📅 Data di attualizzazione del GBV",
            value=date(2022, 11, 6),
            format="DD/MM/YYYY",
            help="⚠️ FONDAMENTALE: data fino a cui il creditore ha conteggiato gli "
                 "interessi nel GBV dichiarato (spesso anteriore al precetto!). "
                 "Il check di congruità userà QUESTA data per un confronto "
                 "'mele con mele', evitando falsi allarmi di anatocismo."
        )
    else:
        data_attualizzazione_gbv = None

    # 🔗 Salvo il GBV per il Tab 3 (NPL)
    st.session_state["gbv_dichiarato"] = gbv_dichiarato

    with st.expander("➕ Aggiungi Spese Legali / Altro"):
        spese_legali = st.number_input(
            "⚖️ Spese legali / procedurali (€)",
            min_value=0.0, value=0.0, step=100.0,
            help="Spese di precetto, notifica, procedura esecutiva richieste in atto."
        )

    st.divider()

    if st.button("🧮 Calcola interessi di mora", type="primary"):

        # --- Controlli di coerenza temporale ---
        if data_decadenza_effettiva < data_prima_rata:
            st.error("⛔ La data di decadenza è precedente alla prima rata insoluta. "
                     "Verificare le date.")
            st.stop()
        if data_fine < data_decadenza_effettiva:
            st.error("⛔ La data finale di calcolo è precedente alla decadenza. "
                     "Verificare le date.")
            st.stop()
        if data_pignoramento < data_decadenza_effettiva:
            st.warning("⚠️ Il pignoramento risulta precedente alla decadenza: "
                       "di norma è successivo. Verificare.")

        etichetta = "CASO A (Lettera DBT)" if is_caso_A else "CASO B (Notifica Precetto)"
        st.subheader(f"Modalità: {etichetta}")
        st.caption(f"Data Decadenza Effettiva utilizzata: "
                   f"**{data_decadenza_effettiva.strftime('%d/%m/%Y')}**")

        # ==========================================================
        # 🔄 DOPPIO CALCOLO: Giro A (Check GBV) + Giro B (Attuale)
        # ==========================================================

        # --- Parametri comuni ai due giri (tutto tranne data_fine) ---
        params_comuni = dict(
            importo_rata=importo_rata,
            data_prima_rata=data_prima_rata,
            frequenza=frequenza,
            capitale_residuo=capitale_residuo,
            tasso_mora=tasso_mora,
            data_decadenza_effettiva=data_decadenza_effettiva,
            data_stipula=data_stipula,
            data_pignoramento=data_pignoramento,
        )

        # --- GIRO B (CALCOLO ATTUALE): fino a data_fine (es. oggi) ---
        # Alimenta le metriche principali e il Tab 3 (negoziazione).
        risultato = calcola_mora_unificato(**params_comuni, data_fine=data_fine)

        # --- GIRO A (CHECK GBV): fino alla data di attualizzazione del creditore ---
        # Gira SOLO se è stato dichiarato un GBV, per il confronto "mele con mele".
        if gbv_dichiarato > 0 and data_attualizzazione_gbv is not None:
            # Coerenza: la data di attualizzazione non può precedere la decadenza
            if data_attualizzazione_gbv < data_decadenza_effettiva:
                st.error("⛔ La *Data di attualizzazione GBV* è precedente alla "
                         "decadenza. Impossibile eseguire il check contabile.")
                risultato_gbv = None
            else:
                risultato_gbv = calcola_mora_unificato(
                    **params_comuni, data_fine=data_attualizzazione_gbv
                )
        else:
            risultato_gbv = None

        # --
