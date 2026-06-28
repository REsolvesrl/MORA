import streamlit as st
from datetime import date
from dateutil.relativedelta import relativedelta

TASSI_LEGALI = {
    2005: 0.0250, 2006: 0.0250, 2007: 0.0250, 2008: 0.0300, 2009: 0.0300,
    2010: 0.0100, 2011: 0.0150, 2012: 0.0250, 2013: 0.0250, 2014: 0.0100,
    2015: 0.0050, 2016: 0.0020, 2017: 0.0010, 2018: 0.0030, 2019: 0.0080,
    2020: 0.0005, 2021: 0.0001, 2022: 0.0125, 2023: 0.0500, 2024: 0.0250,
    2025: 0.0200, 2026: 0.0160,
}
TASSO_LEGALE_DEFAULT = 0.0160

FREQUENZA_MESI = {
    "Mensile": 1,
    "Trimestrale": 3,
    "Semestrale": 6,
}

def giorni_tra(d1, d2):
    return (d2 - d1).days

def interesse_semplice(capitale, tasso_annuo, giorni, base_anno=365):
    if giorni <= 0 or capitale <= 0:
        return 0.0
    return capitale * tasso_annuo * (giorni / base_anno)

def tasso_legale_per_anno(anno):
    return TASSI_LEGALI.get(anno, TASSO_LEGALE_DEFAULT)

def interesse_legale_pro_rata(capitale, data_inizio, data_fine):
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
    mesi = FREQUENZA_MESI[frequenza]
    rate = []
    cursore = data_prima_rata
    while cursore < data_limite:
        rate.append({"importo": importo_rata, "data_scadenza": cursore})
        cursore = cursore + relativedelta(months=mesi)
    return rate

def calcola_triennio(data_stipula, data_pignoramento):
    anni_trascorsi = data_pignoramento.year - data_stipula.year
    inizio_annata_corrente = data_stipula + relativedelta(years=anni_trascorsi)
    if inizio_annata_corrente > data_pignoramento:
        inizio_annata_corrente -= relativedelta(years=1)
    fine_annata_corrente = inizio_annata_corrente + relativedelta(years=1)
    inizio_triennio = inizio_annata_corrente - relativedelta(years=2)
    return inizio_triennio, inizio_annata_corrente, fine_annata_corrente

def ripartisci_credito(capitale, tasso_mora, data_inizio_mora,
                       data_stipula, data_pignoramento, data_fine):
    inizio_triennio, inizio_annata_pign, fine_annata_pign = calcola_triennio(
        data_stipula, data_pignoramento
    )
    risultato = {"ipotecario": 0.0, "chirografario": 0.0, "dettaglio": {}}
    if data_inizio_mora < inizio_triennio:
        fine_pre = min(inizio_triennio, data_fine)
        gg = giorni_tra(data_inizio_mora, fine_pre)
        int_pre = interesse_semplice(capitale, tasso_mora, gg)
        risultato["chirografario"] += int_pre
        risultato["dettaglio"]["pre_triennio_chiro"] = int_pre
    inizio_t = max(data_inizio_mora, inizio_triennio)
    fine_t = min(fine_annata_pign, data_fine)
    if fine_t > inizio_t:
        gg = giorni_tra(inizio_t, fine_t)
        int_triennio = interesse_semplice(capitale, tasso_mora, gg)
        risultato["ipotecario"] += int_triennio
        risultato["dettaglio"]["triennio_ipo_mora"] = int_triennio
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
    totale["ipotecario"] += parziale["ipotecario"]
    totale["chirografario"] += parziale["chirografario"]
    totale["dettaglio"][chiave_dettaglio] = parziale["dettaglio"]
    d = parziale["dettaglio"]
    totale["voci_2855"]["pre_chiro"]    += d.get("pre_triennio_chiro", 0.0)
    totale["voci_2855"]["triennio_ipo"] += d.get("triennio_ipo_mora", 0.0)
    totale["voci_2855"]["post_ipo"]     += d.get("post_ipo_legale", 0.0)
    totale["voci_2855"]["post_chiro"]   += d.get("post_chiro_diff", 0.0)
    return totale

def calcola_mora_unificato(importo_rata, data_prima_rata, frequenza,
                           capitale_residuo, tasso_mora,
                           data_decadenza_effettiva,
                           data_stipula, data_pignoramento, data_fine):
    totale = {
        "ipotecario": 0.0,
        "chirografario": 0.0,
        "dettaglio": {},
        "voci_2855": {
            "pre_chiro": 0.0,
            "triennio_ipo": 0.0,
            "post_ipo": 0.0,
            "post_chiro": 0.0,
        },
    }
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
            data_fine=data_fine
        )
        totale["ipotecario"] += rip["ipotecario"]
        totale["chirografario"] += rip["chirografario"]
        d = rip["dettaglio"]
        totale["voci_2855"]["pre_chiro"]    += d.get("pre_triennio_chiro", 0.0)
        totale["voci_2855"]["triennio_ipo"] += d.get("triennio_ipo_mora", 0.0)
        totale["voci_2855"]["post_ipo"]     += d.get("post_ipo_legale", 0.0)
        totale["voci_2855"]["post_chiro"]   += d.get("post_chiro_diff", 0.0)
        dettaglio_fase1["rate"][
            f"rata_{i+1}_({rata['data_scadenza'].strftime('%d/%m/%Y')})"
        ] = rip["dettaglio"]
    totale["dettaglio"]["FASE_1_rate"] = dettaglio_fase1
    rip_fase2 = ripartisci_credito(
        capitale=capitale_residuo,
        tasso_mora=tasso_mora,
        data_inizio_mora=data_decadenza_effettiva,
        data_stipula=data_stipula,
        data_pignoramento=data_pignoramento,
        data_fine=data_fine
    )
    totale = _accumula(totale, rip_fase2, "FASE_2_capitale_residuo")
    return totale


# ==========================================================
# UI STREAMLIT
# ==========================================================
st.set_page_config(page_title="Calcolo Interessi di Mora", page_icon="⚖️")
st.title("⚖️ Calcolo Interessi di Mora – Piano Rateale")
st.caption("_Ex Art. 2855 c.c. — Ripartizione Ipotecario / Chirografario_")

with st.sidebar:
    st.header("Parametri")
    tasso_mora = st.number_input("Tasso di mora (% annuo)", min_value=0.0, value=8.0, step=0.5) / 100
    data_stipula = st.date_input("Data stipula mutuo", value=date(2018,6,15))
    data_pignoramento = st.date_input("Data pignoramento", value=date(2023,9,10))
    data_fine = st.date_input("Data fine calcolo", value=date.today())

    st.divider()
    st.subheader("🎯 Evento Decadenza dal beneficio del termine")
    evento = st.radio(
        "Seleziona il caso:",
        ["CASO A – Lettera DBT", "CASO B – Notifica Precetto"],
        index=0
    )
    is_caso_A = (evento == "CASO A – Lettera DBT")

st.divider()
st.subheader("Dati del piano e del credito")

c1, c2, c3 = st.columns(3)
with c1:
    importo_rata = st.number_input("Importo rata (€)", min_value=0.0, value=800.0, step=50.0)
with c2:
    data_prima_rata = st.date_input("Data prima rata", value=date(2021,3,1))
with c3:
    frequenza = st.selectbox("Frequenza", list(FREQUENZA_MESI.keys()), index=0)

c4, c5 = st.columns(2)
with c4:
    capitale_residuo = st.number_input(
        "Capitale residuo (€)",
        min_value=0.0, value=100000.0, step=1000.0,
        help="Capitale residuo del mutuo alla data di decadenza."
    )

with c5:
    if is_caso_A:
        data_decadenza_effettiva = st.date_input(
            "📅 Data Lettera DBT (decadenza)",
            value=date(2022,1,20),
            help="Data in cui il debitore ha ricevuto la lettera di decadenza "
                 "dal beneficio del termine."
        )
    else:
        data_decadenza_effettiva = st.date_input(
            "📅 Data Notifica Precetto (decadenza)",
            value=date(2023,2,1),
            help="Data di notificazione dell'atto di precetto che determina "
                 "la decadenza dal beneficio del termine."
        )

# ---- 🏦 GBV dichiarato dal creditore ----
gbv_dichiarato = st.number_input(
    "🏦 GBV Dichiarato dal Creditore (Atto di Precetto / Insinuazione) (€)",
    min_value=0.0, value=0.0, step=500.0,
    help="Importo COMPLESSIVO richiesto dal creditore: capitale + interessi di mora + spese."
)

# ---- Voci secondarie (nascoste per non appesantire la vista) ----
with st.expander("➕ Aggiungi Spese Legali / Altro"):
    spese_legali = st.number_input(
        "⚖️ Spese legali / procedurali (€)",
        min_value=0.0, value=0.0, step=100.0,
        help="Spese di precetto, notifica, procedura esecutiva richieste in atto."
    )
    quota_capitale_rate = st.number_input(
        "🏠 Quota capitale rate scadute (€)",
        min_value=0.0, value=0.0, step=100.0,
        help="Eventuale quota capitale contenuta nelle rate insolute ante decadenza, "
             "da sommare al capitale residuo. Lasciare 0 se gia ricompresa nel capitale residuo."
    )

st.divider()

if st.button("🧮 Calcola interessi di mora", type="primary"):

    # --- Coerenza date ---
    if data_decadenza_effettiva <= data_prima_rata:
        st.error("❌ La data di decadenza deve essere posteriore alla prima rata.")
    elif data_fine <= data_decadenza_effettiva:
        st.error("❌ La data fine calcolo deve essere posteriore alla decadenza.")
    elif data_pignoramento < data_stipula:
        st.error("❌ La data di pignoramento non può essere anteriore alla stipula.")
    else:
        etichetta = "Lettera DBT" if is_caso_A else "Notifica Precetto"
        st.success(f"✅ Caso '{etichetta}' — decadenza: {data_decadenza_effettiva.strftime('%d/%m/%Y')}")

        st.subheader("📊 Risultato")
        risultato = calcola_mora_unificato(
            importo_rata, data_prima_rata, frequenza,
            capitale_residuo, tasso_mora,
            data_decadenza_effettiva,
            data_stipula, data_pignoramento, data_fine
        )

        tot_ipo = risultato["ipotecario"]
        tot_chiro = risultato["chirografario"]
        totale_gen = tot_ipo + tot_chiro

        col1, col2, col3 = st.columns(3)
        col1.metric("🏦 Ipotecario (gravame triennale)", f"€ {tot_ipo:,.2f}")
        col2.metric("📄 Chirografario (fuori triennio)", f"€ {tot_chiro:,.2f}")
        col3.metric("💰 TOTALE interessi di mora", f"€ {totale_gen:,.2f}")

    # ==========================================================
    # 🔎 CHECK GBV (AUDITING A COMPONENTI)
    # ==========================================================
    if gbv_dichiarato > 0:
        st.divider()
        st.subheader("🔎 Check GBV (Auditing a componenti)")

        capitale_totale  = capitale_residuo + quota_capitale_rate
        interessi_totali = totale_gen
        totale_calcolato = capitale_totale + interessi_totali + spese_legali
        delta = gbv_dichiarato - totale_calcolato
        SOGLIA = 10.0

        b1, b2, b3 = st.columns(3)
        b1.metric("🏦 Capitale", f"€ {capitale_totale:,.2f}")
        b2.metric("⚖️ Spese Legali", f"€ {spese_legali:,.2f}")
        b3.metric("📈 Interessi (ex Art. 2855)", f"€ {interessi_totali:,.2f}")

        t1, t2, t3 = st.columns(3)
        t1.metric("🧮 TOTALE CALCOLATO", f"€ {totale_calcolato:,.2f}")
        t2.metric("📑 GBV DICHIARATO", f"€ {gbv_dichiarato:,.2f}")
        t3.metric("📐 DELTA", f"€ {delta:,.2f}",
                  delta=f"{delta:,.2f} €", delta_color="inverse")

        if delta > SOGLIA:
            st.error(
                f"🚨 **Anomalia rilevata:** Il GBV dichiarato supera di "
                f"**€ {delta:,.2f}** il credito ricostruito voce per voce "
                "(capitale + interessi ex Art. 2855 + spese).\n\n"
                "Verificare possibile **anatocismo**, **errata estensione ipotecaria**, "
                "**tassi di mora non dovuti** o **spese non documentate**."
            )
        elif delta < -SOGLIA:
            st.warning(
                f"ℹ️ Il totale calcolato risulta **superiore** al GBV dichiarato di "
                f"€ {abs(delta):,.2f}. Pretesa creditoria prudenziale "
                "(a favore del debitore). Verificare comunque i dati inseriti."
            )
        else:
            st.success(
                f"✅ **GBV congruo:** importi allineati "
                f"(scarto € {abs(delta):,.2f} entro la soglia di € {SOGLIA:,.2f})."
            )

        # SPACCATO VISIVO TRIPARTIZIONE
        st.divider()
        st.subheader("🧩 Spaccato visivo – art. 2855")

        v = risultato["voci_2855"]
        f1, f2, f3 = st.columns(3)

        with f1:
            st.info(
                f"**FASE 1 – Rate ante decadenza**\n\n"
                f"Pre-triennio chirografario: **€ {v['pre_chiro']:,.2f}**\n\n"
                f"Solo interessi: quota parte della singola rata maturata dal giorno "
                f"di scadenza fino alla data di decadenza.\n\n"
                f"Quota capitale già inclusa nel capitale residuo (Fase 2)."
            )
        with f2:
            st.success(
                f"**FASE 2 – Capitale residuo**\n\n"
                f"Triennio ipotecario (mora piena): **€ {v['triennio_ipo']:,.2f}**\n\n"
                f"Post-triennio a tasso legale: **€ {v['post_ipo']:,.2f}**\n\n"
                f"Capitale: **€ {capitale_residuo:,.2f}**"
            )
        with f3:
            st.warning(
                f"**FASE 3 – Post-pignoramento**\n\n"
                f"Solo interessi chirografari: **€ {v['post_chiro']:,.2f}**\n\n"
                f"Oltre il triennio dal pignoramento il credito ipotecario "
                f"cessa di maturare interessi (art. 2855 c.c.).\n\n"
                f"Residui interessi continuano al tasso legale (non computato in GBV)."
            )

        # --- Quadratura di controllo ---
        st.divider()
        riconciliazione = v["pre_chiro"] + v["triennio_ipo"] + v["post_ipo"] + v["post_chiro"]
        quadratura = abs(riconciliazione - totale_gen)
        st.info(
            f"**Quadratura di controllo**\n\n"
            f"Somma delle 4 voci art. 2855: **€ {riconciliazione:,.2f}**\n"
            f"Totale generale calcolato: **€ {totale_gen:,.2f}**\n"
            f"Differenza: **€ {quadratura:,.6f}**"
        )
        if quadratura < 0.01:
            st.success("✅ La quadratura è perfetta (differenza < 1 centesimo).")
        else:
            st.warning("⚠️ Differenza superiore a 1 centesimo: verificare la logica.")

        # --- Riepilogo rate auto-generate ---
        dettaglio_fase1 = risultato["dettaglio"].get("FASE_1_rate", {})
        with st.expander("📋 Dettaglio rate (generazione automatica)"):
            st.write(f"Numero rate generate: **{dettaglio_fase1.get('numero_rate_generate', 0)}**")
            for k, v_rata in dettaglio_fase1.get("rate", {}).items():
                st.write(f"  {k}: {v_rata}")

        with st.expander("🔬 Dettaglio tecnico completo (JSON)"):
            st.json(risultato["dettaglio"])
