import streamlit as st
from datetime import date
from dateutil.relativedelta import relativedelta

# ==========================================================
# 1. TABELLE DI CONFIGURAZIONE
# ==========================================================

# Tassi legali ex art. 1284 c.c. (variano ogni 1° gennaio)
TASSI_LEGALI = {
    2005: 0.0250,   # 2,50%
    2006: 0.0250,   # 2,50%
    2007: 0.0250,   # 2,50%
    2008: 0.0300,   # 3,00%
    2009: 0.0300,   # 3,00%
    2010: 0.0100,   # 1,00%
    2011: 0.0150,   # 1,50%
    2012: 0.0250,   # 2,50%
    2013: 0.0250,   # 2,50%
    2014: 0.0100,   # 1,00%
    2015: 0.0050,   # 0,50%
    2016: 0.0020,   # 0,20%
    2017: 0.0010,   # 0,10%
    2018: 0.0030,   # 0,30%
    2019: 0.0080,   # 0,80%
    2020: 0.0005,   # 0,05%
    2021: 0.0001,   # 0,01%
    2022: 0.0125,   # 1,25%
    2023: 0.0500,   # 5,00%
    2024: 0.0250,   # 2,50%
    2025: 0.0200,   # 2,00%
    2026: 0.0160,   # 1,60%
}
TASSO_LEGALE_DEFAULT = 0.0160  # fallback per anni non in tabella


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
# 4. RIPARTIZIONE IPOTECARIO / CHIROGRAFARIO
# ==========================================================

def ripartisci_credito(capitale, tasso_mora, data_inizio_mora,
                       data_stipula, data_pignoramento, data_fine):
    """
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


# ==========================================================
# 5. DOPPIO BINARIO DBT
# ==========================================================

def calcola_caso_A(capitale_residuo, tasso_mora, data_dbt, data_stipula,
                   data_pignoramento, data_fine):
    """CASO A: lettera DBT inviata. Mora su INTERO capitale residuo dalla data DBT."""
    return ripartisci_credito(
        capitale=capitale_residuo,
        tasso_mora=tasso_mora,
        data_inizio_mora=data_dbt,
        data_stipula=data_stipula,
        data_pignoramento=data_pignoramento,
        data_fine=data_fine
    )


def calcola_caso_B(rate_scadute, tasso_mora, tasso_corrispettivo,
                   capitale_a_scadere, data_stipula, data_pignoramento,
                   data_fine):
    """
    CASO B: nessuna lettera DBT, piano ancora in vigore.
    - rate_scadute: lista di dict {"importo": x, "data_scadenza": date}
    - capitale_a_scadere: solo interessi corrispettivi (no mora)
    """
    totale = {"ipotecario": 0.0, "chirografario": 0.0, "dettaglio": {}}

    for i, rata in enumerate(rate_scadute):
        rip = ripartisci_credito(
            capitale=rata["importo"],
            tasso_mora=tasso_mora,
            data_inizio_mora=rata["data_scadenza"],
            data_stipula=data_stipula,
            data_pignoramento=data_pignoramento,
            data_fine=data_fine
        )
        totale["ipotecario"] += rip["ipotecario"]
        totale["chirografario"] += rip["chirografario"]
        totale["dettaglio"][f"rata_{i+1}"] = rip["dettaglio"]

    int_corrisp = interesse_semplice(
        capitale_a_scadere, tasso_corrispettivo,
        giorni_tra(data_pignoramento, data_fine)
    )
    totale["ipotecario"] += int_corrisp
    totale["dettaglio"]["corrispettivi_a_scadere"] = int_corrisp

    return totale


# ==========================================================
# 6. INTERFACCIA STREAMLIT
# ==========================================================

st.set_page_config(page_title="Calcolo Interessi di Mora", layout="wide")
st.title("⚖️ Calcolo Interessi di Mora – Ipotecario / Chirografario")
st.caption("Strumento di supporto. Verificare sempre i risultati. Interesse semplice (art. 1283 c.c.).")

with st.sidebar:
    st.header("Parametri generali")
    capitale = st.number_input("Capitale residuo (€)", min_value=0.0, value=100000.0, step=1000.0)
    tasso_mora = st.number_input("Tasso di mora (%)", min_value=0.0, value=8.0, step=0.1) / 100
    tasso_corr = st.number_input(
        "Tasso corrispettivo / TAN (%)",
        min_value=0.0, value=4.0, step=0.1,
        help="Inserire il TAN da contratto, NON il TAEG."
    ) / 100

    st.divider()
    data_stipula = st.date_input("Data stipula mutuo", value=date(2018, 6, 15))
    data_pignoramento = st.date_input("Data pignoramento", value=date(2023, 9, 10))
    data_dbt = st.date_input("Data Decadenza Beneficio Termine (DBT)", value=date(2022, 1, 20))
    data_fine = st.date_input("Data fine calcolo (Decreto Trasf.)", value=date.today())

    st.divider()
    ha_lettera_DBT = st.checkbox("È stata inviata la lettera di DBT?", value=True)

st.divider()

if st.button("🧮 Calcola interessi di mora", type="primary"):

    if ha_lettera_DBT:
        st.subheader("Modalità: CASO A (Lettera DBT inviata)")
        risultato = calcola_caso_A(
            capitale, tasso_mora, data_dbt, data_stipula,
            data_pignoramento, data_fine
        )
    else:
        st.subheader("Modalità: CASO B (Piano ancora in vigore)")
        st.info("⚠️ Inserire le rate scadute (interfaccia da collegare).")
        rate_scadute = []  # TODO: input dinamico rate
        risultato = calcola_caso_B(
            rate_scadute, tasso_mora, tasso_corr,
            capitale, data_stipula, data_pignoramento, data_fine
        )

    col1, col2 = st.columns(2)
    col1.metric("🏛️ Credito IPOTECARIO", f"€ {risultato['ipotecario']:,.2f}")
    col2.metric("📄 Credito CHIROGRAFARIO", f"€ {risultato['chirografario']:,.2f}")

    totale = risultato['ipotecario'] + risultato['chirografario']
    st.metric("💰 TOTALE interessi di mora", f"€ {totale:,.2f}")

    with st.expander("🔍 Dettaglio calcolo"):
        st.json(risultato['dettaglio'])
