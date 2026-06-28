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

# Parametri forfettari spese esecutive immobiliari (modificabili)
SPESE_IMMOBILIARE = {
    "spese_vive": 800.0,        # CU, trascrizioni, note
    "ctu": 3500.0,              # consulenza tecnica d'ufficio
    "custode_delegato": 4000.0, # o 3% del valore se maggiore
    "perc_custode": 0.03,
    "pubblicita": 1500.0,       # pubblicità sul PVP
    "spese_legali_nostre": 2600.0,
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
# 4. RIPARTIZIONE CREDITO EX ART. 2855 c.c.
# ==========================================================

def ripartisci_credito(capitale, tasso_mora, data_inizio_mora,
                       data_stipula, data_pignoramento, data_fine):
    """
    Ripartisce gli interessi di mora di un dato capitale tra
    IPOTECARIO e CHIROGRAFARIO secondo le 3 fasi dell'art. 2855 c.c.:
      - PRE-TRIENNIO : tutto chirografario (al tasso di mora)
      - TRIENNIO     : ipotecario pieno (al tasso di mora)
      - POST-TRIENNIO: ipotecario al tasso legale, eccedenza chirografaria
    """
    risultato = {"ipotecario": 0.0, "chirografario": 0.0, "dettaglio": {}}

    inizio_triennio, _, fine_annata_pign = calcola_triennio(
        data_stipula, data_pignoramento
    )

    # --- PRE-TRIENNIO (chirografario @ mora) ---
    inizio_pre = data_inizio_mora
    fine_pre = min(inizio_triennio, data_fine)
    if fine_pre > inizio_pre:
        gg = giorni_tra(inizio_pre, fine_pre)
        int_pre = interesse_semplice(capitale, tasso_mora, gg)
        risultato["chirografario"] += int_pre
        risultato["dettaglio"]["pre_chiro_mora"] = int_pre

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

def _accumula_voci_2855(totale, rip):
    """Helper: accumula le 4 voci della tripartizione ex art. 2855 c.c."""
    d = rip["dettaglio"]
    totale["voci_2855"]["pre_chiro"] += d.get("pre_chiro_mora", 0.0)
    totale["voci_2855"]["triennio_ipo"] += d.get("triennio_ipo_mora", 0.0)
    totale["voci_2855"]["post_ipo"] += d.get("post_ipo_legale", 0.0)
    totale["voci_2855"]["post_chiro"] += d.get("post_chiro_diff", 0.0)

# ==========================================================
# 5. CALCOLO UNIFICATO (2 FASI)
# ==========================================================

def calcola_mora_unificato(importo_rata, data_prima_rata, frequenza,
                           capitale_residuo, tasso_mora,
                           data_decadenza_effettiva, data_stipula,
                           data_pignoramento, data_fine):
    """
    FASE 1: ogni rata insoluta matura mora dalla scadenza fino alla decadenza.
    FASE 2: il capitale residuo matura mora dalla decadenza fino a data_fine.
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
            data_fine=data_decadenza_effettiva
        )
        totale["ipotecario"] += rip["ipotecario"]
        totale["chirografario"] += rip["chirografario"]
        _accumula_voci_2855(totale, rip)
        dettaglio_fase1["rate"][f"rata_{i+1}"] = {
            "data_scadenza": rata["data_scadenza"].strftime("%d/%m/%Y"),
            "importo": rata["importo"],
            "ipotecario": rip["ipotecario"],
            "chirografario": rip["chirografario"],
            "dettaglio": rip["dettaglio"],
        }

    totale["dettaglio"]["FASE_1_rate"] = dettaglio_fase1

    # ---------- FASE 2: capitale residuo dalla decadenza a data_fine ----------
    rip_cap = ripartisci_credito(
        capitale=capitale_residuo,
        tasso_mora=tasso_mora,
        data_inizio_mora=data_decadenza_effettiva,
        data_stipula=data_stipula,
        data_pignoramento=data_pignoramento,
        data_fine=data_fine
    )
    totale["ipotecario"] += rip_cap["ipotecario"]
    totale["chirografario"] += rip_cap["chirografario"]
    _accumula_voci_2855(totale, rip_cap)
    totale["dettaglio"]["FASE_2_capitale"] = {
        "capitale_residuo": capitale_residuo,
        "ipotecario": rip_cap["ipotecario"],
        "chirografario": rip_cap["chirografario"],
        "dettaglio": rip_cap["dettaglio"],
    }

    return totale

# ==========================================================
# 6. STIMA SPESE ESECUTIVE (solo IMMOBILIARE)
# ==========================================================

def stima_spese_esecutive(valore_bene):
    """
    Stima forfettaria dei costi di una procedura esecutiva immobiliare.
    Ritorna un dizionario con le singole voci e il totale.
    Valori indicativi: verificare sempre col foro competente.
    """
    p = SPESE_IMMOBILIARE
    custode = max(p["custode_delegato"], valore_bene * p["perc_custode"])
    voci = {
        "Spese vive (CU, trascrizioni, note)": p["spese_vive"],
        "CTU (perizia di stima)": p["ctu"],
        "Custode / Professionista delegato": custode,
        "Pubblicità (PVP)": p["pubblicita"],
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
    tasso_mora_fisso = st.number_input(
        "Tasso di mora (%)",
        min_value=0.0, value=8.0, step=0.1,
        help="Tasso di mora contrattuale fisso, applicato per tutti gli anni."
    ) / 100

tab1, tab2, tab3 = st.tabs([
    "🔍 1. Auditing Credito",
    "🔮 2. Previsione Spese Esecutive",
    "💼 3. Negoziazione NPL",
])

# ----------------------------------------------------------
# TAB 1 — AUDITING DEL CREDITO
# ----------------------------------------------------------
with tab1:
    st.subheader("📋 Dati del rapporto di credito")

    c1, c2, c3 = st.columns(3)
    data_stipula = c1.date_input(
        "📝 Data Stipula Mutuo", value=date(2015, 6, 1), format="DD/MM/YYYY",
        help="Data dell'atto di mutuo (decorrenza annate ipotecarie)."
    )
    data_pignoramento = c2.date_input(
        "🔨 Data Pignoramento", value=date(2023, 6, 1), format="DD/MM/YYYY",
        help="Data di trascrizione del pignoramento."
    )
    data_fine = c3.date_input(
        "📆 Data Finale Calcolo (oggi)", value=date.today(), format="DD/MM/YYYY",
        help="Data fino a cui calcolare il debito reale (negoziazione)."
    )

    c4, c5 = st.columns(2)
    capitale_residuo = c4.number_input(
        "💶 Capitale Residuo (€)", min_value=0.0, value=100000.0, step=1000.0,
        help="Capitale residuo alla data di decadenza."
    )

    is_caso_A = st.toggle(
        "📩 È presente la Lettera di Decadenza dal Beneficio del Termine (DBT)?",
        value=False,
        help="Se attivo (CASO A) usa la data DBT. Se spento (CASO B) usa la notifica del precetto."
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

    st.divider()
    st.subheader("📅 Piano rate insolute")

    r1, r2, r3 = st.columns(3)
    importo_rata = r1.number_input(
        "💸 Importo Rata (€)", min_value=0.0, value=1200.0, step=50.0
    )
    data_prima_rata = r2.date_input(
        "📅 Data Prima Rata Non Pagata", value=date(2021, 6, 1), format="DD/MM/YYYY"
    )
    frequenza = r3.selectbox(
        "🔁 Frequenza Rate", options=list(FREQUENZA_MESI.keys()), index=0
    )

    st.divider()

    # ---- GBV dichiarato + voci secondarie ----
    gbv_dichiarato = st.number_input(
        "🏦 GBV Dichiarato dal Creditore (€)",
        min_value=0.0,
        value=0.0,
        step=1000.0,
        help="Importo complessivo (Gross Book Value) richiesto dalla banca/cessionario. "
             "Lascia 0 per saltare il check di congruità."
    )

    # 🆕 Data di attualizzazione GBV (solo se GBV > 0)
    data_attualizzazione_gbv = None
    if gbv_dichiarato > 0:
        data_attualizzazione_gbv = st.date_input(
            "📅 Data di attualizzazione del GBV (Atto di Precetto / Insinuazione)",
            value=date(2023, 2, 1),
            format="DD/MM/YYYY",
            help="Data alla quale il creditore ha calcolato il GBV dichiarato. "
                 "Serve per il confronto 'mele con mele'."
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
        st.info(f"📌 Modalità di calcolo selezionata: **{etichetta}**")

        # ==================================================
        # FUNZIONE INTERNA DI CALCOLO (riutilizzabile)
        # ==================================================
        def esegui_calcolo(data_finale_calcolo):
            """Esegue il calcolo degli interessi di mora fino alla data indicata.
            Ritorna un dict con capitale, interessi e dettaglio per anno."""
            dettaglio_anni = []
            interessi_totali = 0.0

            anno_corrente = data_decadenza_effettiva.year
            anno_finale = data_finale_calcolo.year

        for anno in range(anno_corrente, anno_finale + 1):
            # Tasso di mora contrattuale fisso (uguale per tutti gli anni)
            tasso_legale = TASSI_LEGALI.get(anno, TASSO_LEGALE_DEFAULT)
            tasso_mora = tasso_mora_fisso

                # Intervallo di calcolo dentro l'anno
                inizio = max(data_decadenza_effettiva, date(anno, 1, 1))
                fine = min(data_finale_calcolo, date(anno, 12, 31))

                if fine < inizio:
                    continue

                giorni = (fine - inizio).days + 1
                giorni_anno = 366 if (anno % 4 == 0 and (anno % 100 != 0 or anno % 400 == 0)) else 365

                interessi_anno = capitale_residuo * tasso_mora * giorni / giorni_anno
                interessi_totali += interessi_anno

                dettaglio_anni.append({
                    "anno": anno,
                    "giorni": giorni,
                    "tasso_legale": tasso_legale,
                    "tasso_mora": tasso_mora,
                    "interessi": interessi_anno,
                })

            return {
                "capitale": capitale_residuo,
                "interessi": interessi_totali,
                "totale": capitale_residuo + interessi_totali,
                "dettaglio": dettaglio_anni,
            }

        # ==================================================
        # GIRO 1 — CHECK GBV (alla data di attualizzazione)
        # ==================================================
        risultato_gbv = None
        if gbv_dichiarato > 0 and data_attualizzazione_gbv is not None:
            risultato_gbv = esegui_calcolo(data_attualizzazione_gbv)

        # ==================================================
        # GIRO 2 — CALCOLO ATTUALE (alla data finale scelta)
        # ==================================================
        risultato = esegui_calcolo(data_fine)

        # ==================================================
        # METRICHE PRINCIPALI
        # ==================================================
        st.subheader("📊 Risultato del calcolo")
        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Capitale residuo", f"€ {risultato['capitale']:,.2f}")
        col2.metric("📈 Interessi di mora", f"€ {risultato['interessi']:,.2f}")
        col3.metric("🧾 Totale dovuto", f"€ {risultato['totale']:,.2f}")

        # ==================================================
        # CHECK GBV — CONFRONTO "MELE CON MELE"
        # ==================================================
        if risultato_gbv is not None:
            st.divider()
            st.subheader("🔍 Check di congruità del GBV dichiarato")

            totale_nostro_gbv = risultato_gbv["totale"]
            delta = gbv_dichiarato - totale_nostro_gbv
            perc_scostamento = (delta / totale_nostro_gbv * 100) if totale_nostro_gbv > 0 else 0.0

            c1, c2, c3 = st.columns(3)
            c1.metric("🏦 GBV Dichiarato", f"€ {gbv_dichiarato:,.2f}")
            c2.metric("🧮 Nostro calcolo (stessa data)", f"€ {totale_nostro_gbv:,.2f}")
            c3.metric("📐 Scostamento", f"€ {delta:,.2f}", f"{perc_scostamento:+.1f}%")

            if abs(perc_scostamento) <= 5:
                st.success("✅ GBV CONGRUO: scostamento entro il 5%. Il dichiarato è in linea col calcolo.")
            elif perc_scostamento > 5:
                st.warning(f"⚠️ GBV GONFIATO: il creditore chiede € {delta:,.2f} in più "
                           f"({perc_scostamento:+.1f}%) rispetto al calcolo analitico.")
            else:
                st.info(f"ℹ️ GBV PRUDENTE: il dichiarato è inferiore al calcolo di € {abs(delta):,.2f} "
                        f"({perc_scostamento:.1f}%).")

        # ==================================================
        # SPACCATO ART. 2855 c.c. (collocazione ipotecaria)
        # ==================================================
        st.divider()
        st.subheader("⚖️ Spaccato collocazione ipotecaria (Art. 2855 c.c.)")
        st.caption("L'ipoteca garantisce il capitale, gli interessi dell'anno in corso "
                   "e dei due anni precedenti al pignoramento, più gli interessi successivi "
                   "al tasso legale fino alla vendita.")

        anno_pign = data_pignoramento.year
        # Interessi nel "triennio protetto" (anno pign + 2 precedenti) restano a tasso mora
        interessi_privilegiati = 0.0
        interessi_chirografari = 0.0
        for riga in risultato["dettaglio"]:
            if riga["anno"] >= (anno_pign - 2):
                interessi_privilegiati += riga["interessi"]
            else:
                interessi_chirografari += riga["interessi"]

        ipotecario = risultato["capitale"] + interessi_privilegiati
        chirografario = interessi_chirografari

        cc1, cc2 = st.columns(2)
        cc1.metric("🛡️ Credito IPOTECARIO (privilegiato)", f"€ {ipotecario:,.2f}")
        cc2.metric("📉 Credito CHIROGRAFARIO (degradato)", f"€ {chirografario:,.2f}")

        risultato["ipotecario"] = ipotecario
        risultato["chirografario"] = chirografario

        # ==================================================
        # QUADRATURA CONTABILE
        # ==================================================
        totale_gen = risultato["ipotecario"] + risultato["chirografario"]
        st.divider()
        st.subheader("✅ Quadratura contabile")
        if abs(totale_gen - risultato["totale"]) < 0.01:
            st.success(f"✅ Quadratura OK: Ipotecario + Chirografario = € {totale_gen:,.2f} "
                       f"= Totale dovuto.")
        else:
            st.error(f"⛔ Errore di quadratura: somma spaccato € {totale_gen:,.2f} "
                     f"≠ totale € {risultato['totale']:,.2f}")

        # ==================================================
        # DETTAGLIO ANNUALE (EXPANDER)
        # ==================================================
        with st.expander("📅 Mostra dettaglio interessi anno per anno"):
            st.dataframe(
                [
                    {
                        "Anno": r["anno"],
                        "Giorni": r["giorni"],
                        "Tasso Legale": f"{r['tasso_legale']*100:.2f}%",
                        "Tasso Mora": f"{r['tasso_mora']*100:.2f}%",
                        "Interessi €": round(r["interessi"], 2),
                    }
                    for r in risultato["dettaglio"]
                ],
                use_container_width=True,
            )

# ==========================================================
# TAB 2 — STIMA SPESE ESECUTIVE IMMOBILIARI
# ==========================================================
with tab2:
    st.header("🏠 Stima Spese della Procedura Esecutiva Immobiliare")
    st.caption("Voci forfettarie da anticipare nel pignoramento immobiliare. "
               "Modificabili secondo il caso concreto.")

    valore_immobile = st.number_input(
        "🏡 Valore di perizia dell'immobile (€)",
        min_value=0.0, value=100000.0, step=5000.0,
        help="Valore base d'asta / stima CTU. Serve per calcolare il compenso del custode."
    )

    st.divider()
    st.subheader("💸 Voci di spesa")

    spese_vive = st.number_input("📄 Spese vive (CU, trascrizioni, note)", 
                                  min_value=0.0, value=SPESE_IMMOBILIARE["spese_vive"], step=100.0)
    ctu = st.number_input("👷 Compenso CTU (perito)", 
                          min_value=0.0, value=SPESE_IMMOBILIARE["ctu"], step=100.0)
    pubblicita = st.number_input("📢 Pubblicità sul PVP", 
                                 min_value=0.0, value=SPESE_IMMOBILIARE["pubblicita"], step=100.0)
    spese_legali = st.number_input("⚖️ Spese legali di procedura", 
                                   min_value=0.0, value=SPESE_IMMOBILIARE["spese_legali_nostre"], step=100.0)

    # Custode delegato: max tra forfait e % del valore
    custode_forfait = SPESE_IMMOBILIARE["custode_delegato"]
    custode_perc = valore_immobile * SPESE_IMMOBILIARE["perc_custode"]
    custode_delegato = max(custode_forfait, custode_perc)
    st.number_input("🔑 Custode/Delegato alla vendita (calcolato)", 
                    min_value=0.0, value=custode_delegato, step=100.0, disabled=True,
                    help=f"Max tra forfait € {custode_forfait:,.0f} e "
                         f"{SPESE_IMMOBILIARE['perc_custode']*100:.0f}% del valore "
                         f"(€ {custode_perc:,.0f})")

    st.divider()
    totale_spese_esec = spese_vive + ctu + pubblicita + spese_legali + custode_delegato
    st.metric("🧾 TOTALE SPESE ESECUTIVE STIMATE", f"€ {totale_spese_esec:,.2f}")

    st.info("ℹ️ Queste spese sono prededucibili ex art. 2770 c.c. e vengono "
            "recuperate con priorità sul ricavato dell'asta.")

# ==========================================================
# TAB 3 — BUSINESS PLAN ACQUISIZIONE NPL
# ==========================================================
with tab3:
    st.header("📈 Business Plan Acquisizione Credito NPL")
    st.caption("Analisi di convenienza per l'acquisto del credito deteriorato. "
               "Calcola il prezzo massimo d'acquisto per ottenere il rendimento target.")

    # Recupero dati dai tab precedenti (con fallback)
    try:
        gbv_recuperabile = risultato["totale"]
    except (NameError, KeyError):
        gbv_recuperabile = st.number_input(
            "💰 GBV / Credito recuperabile (€)",
            min_value=0.0, value=150000.0, step=5000.0,
            help="Esegui prima il calcolo nel Tab 1 oppure inseriscilo qui manualmente."
        )

    try:
        spese_procedura = totale_spese_esec
    except NameError:
        spese_procedura = 0.0

    st.divider()
    st.subheader("🎯 Parametri di investimento")

    col1, col2 = st.columns(2)
    with col1:
        prob_recupero = st.slider(
            "📊 Probabilità di recupero (%)", 
            min_value=0, max_value=100, value=70, step=5,
            help="Stima prudenziale della quota di GBV effettivamente incassabile."
        ) / 100.0

        tempo_recupero = st.number_input(
            "⏱️ Tempo stimato di recupero (anni)", 
            min_value=0.5, max_value=15.0, value=4.0, step=0.5
        )

    with col2:
        rendimento_target = st.slider(
            "🎯 Rendimento annuo target (IRR %)", 
            min_value=0, max_value=50, value=15, step=1,
            help="Tasso di rendimento annuo desiderato sull'investimento."
        ) / 100.0

    st.divider()
    st.subheader("💼 Costi di acquisizione")

    fronting = st.number_input("🏦 Fronting", min_value=0.0, 
                               value=COSTI_ACQUISIZIONE["fronting"], step=500.0)
    notaio = st.number_input("📜 Notaio", min_value=0.0, 
                             value=COSTI_ACQUISIZIONE["notaio"], step=500.0)
    servicer = st.number_input("🛠️ Servicer", min_value=0.0, 
                               value=COSTI_ACQUISIZIONE["servicer"], step=500.0)
    advisors = st.number_input("👔 Advisors", min_value=0.0, 
                               value=COSTI_ACQUISIZIONE["advisors"], step=500.0)

    costi_acquisizione_tot = fronting + notaio + servicer + advisors

    st.divider()
    st.subheader("📐 Risultato dell'analisi")

    # Incasso atteso = GBV * probabilità di recupero
    incasso_atteso = gbv_recuperabile * prob_recupero
    # Incasso netto = incasso atteso - spese procedura
    incasso_netto = incasso_atteso - spese_procedura
    # Valore attuale scontato al rendimento target
    valore_attuale = incasso_netto / ((1 + rendimento_target) ** tempo_recupero)
    # Prezzo massimo d'acquisto = valore attuale - costi di acquisizione
    prezzo_max_acquisto = valore_attuale - costi_acquisizione_tot

    m1, m2, m3 = st.columns(3)
    m1.metric("💵 Incasso atteso (lordo)", f"€ {incasso_atteso:,.2f}")
    m2.metric("🧾 Incasso netto spese", f"€ {incasso_netto:,.2f}")
    m3.metric("⏳ Valore attuale scontato", f"€ {valore_attuale:,.2f}")

    st.divider()

    # ==================================================
    # WATERFALL DI CONVENIENZA
    # ==================================================
    st.subheader("💧 Waterfall di convenienza")
    st.markdown(f"""
    | Voce | Importo |
    |------|--------:|
    | 🏦 GBV / Credito recuperabile | € {gbv_recuperabile:,.2f} |
    | 📊 × Probabilità recupero ({prob_recupero*100:.0f}%) | € {incasso_atteso:,.2f} |
    | ➖ Spese procedura esecutiva | € {spese_procedura:,.2f} |
    | 🧾 = Incasso netto | € {incasso_netto:,.2f} |
    | ⏳ ÷ Sconto finanziario ({rendimento_target*100:.0f}% × {tempo_recupero} anni) | € {valore_attuale:,.2f} |
    | 💼 ➖ Costi di acquisizione | € {costi_acquisizione_tot:,.2f} |
    | **🎯 = PREZZO MASSIMO D'ACQUISTO** | **€ {prezzo_max_acquisto:,.2f}** |
    """)

    if prezzo_max_acquisto > 0:
        perc_su_gbv = (prezzo_max_acquisto / gbv_recuperabile * 100) if gbv_recuperabile > 0 else 0
        st.success(f"✅ Prezzo massimo d'acquisto: **€ {prezzo_max_acquisto:,.2f}** "
                   f"({perc_su_gbv:.1f}% del GBV) per ottenere un IRR del {rendimento_target*100:.0f}%.")
    else:
        st.error(f"⛔ Investimento NON conveniente: a queste condizioni il prezzo massimo "
                 f"sarebbe negativo (€ {prezzo_max_acquisto:,.2f}). "
                 f"Rivedere probabilità di recupero, tempi o rendimento target.")

# ==========================================================
# FOOTER
# ==========================================================
st.divider()
st.caption("⚠️ Strumento di supporto all'analisi. I calcoli sono indicativi e verificare sempre tassi, date e voci di spesa nel caso concreto.")

