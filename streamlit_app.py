import streamlit as st
from datetime import date
import plotly.graph_objects as go

from calcoli import (
    FREQUENZA_MESI,
    SPESE_IMMOBILIARE,
    SPESE_MOBILIARE,
    COSTI_ACQUISIZIONE,
    calcola_triennio,
    calcola_mora_unificato,
)
from pdf_export import (
    genera_report_pdf,
    genera_report_pdf_spese,
    genera_report_pdf_npl,
)

# ==========================================================
# FORMATTAZIONE NUMERICA IN STILE ITALIANO
# ==========================================================
# I calcoli interni usano sempre float puri (precisione massima).
# Queste funzioni sono usate solo per il rendering a schermo.

def fmt_eur(x, decimali=2):
    """Formatta un float come importo in euro stile italiano: '1.234,56 €'.

    Esempio: 1234.56 -> '1.234,56 €' ; 150000.5 -> '150.000,50 €'.
    """
    s = f"{x:,.{decimali}f}"                     # '1,234.56' (stile US)
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{s} €"


def fmt_pct(x, decimali=2):
    """Formatta una frazione decimale come percentuale italiana: 0.085 -> '8,50%'."""
    s = f"{x * 100:.{decimali}f}"
    return f"{s.replace('.', ',')}%"

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
                                 min_value=date(2000, 1, 1),
                                 format="DD/MM/YYYY")
    data_pignoramento = st.date_input("Data pignoramento", value=date(2023, 9, 10),
                                      format="DD/MM/YYYY")
    data_fine = st.date_input("Data di aggiudicazione (attualizzazione desiderata)", value=date.today(),
                              format="DD/MM/YYYY")

    st.divider()
    st.subheader("Evento di decadenza")
    caso = st.radio(
        "Quale atto ha generato la decadenza dal beneficio del termine?",
        options=["CASO A – Lettera DBT", "CASO B – Notifica Precetto"],
        index=0,
    )
    is_caso_A = caso.startswith("CASO A")

    st.divider()
    st.subheader("📄 Esportazione PDF")
    pdf_password = st.text_input(
        "Password apertura PDF (opzionale)",
        value="",
        type="password",
        help=(
            "Se inserisci una password, il PDF richiederà questa password per "
            "essere aperto. Se lasci vuoto, il PDF si aprirà liberamente. "
            "In entrambi i casi, copia del testo e modifica del documento "
            "sono sempre disabilitate."
        ),
    )

# ==========================================================
# TAB PRINCIPALI
# ==========================================================
tab1, tab2, tab3 = st.tabs([
    "📊 Auditing e Check GBV",
    "🔮 Previsione Spese Esecutive",
    "🤝 Acquisto Credito e DPO",
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
        "Capitale Residuo all'ultima rata pagata (€)",
        min_value=0.0,
        value=100000.0,
        step=1000.0,
        help="Intero capitale esigibile alla data di decadenza/precetto. "
             "Su questo importo decorre la mora dalla decadenza in poi. "
             "Le rate insolute pre-decadenza contribuiscono SOLO con i loro interessi. "
             "Verificare piano di ammortamento."
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
        "🏦 GBV Dichiarato dalla Cedente (€)",
        min_value=0.0,
        value=0.0,
        step=1000.0,
        help="Importo complessivo (Gross Book Value) richiesto dalla banca/cedente. "
             "Funziona sia per CASO A (Lettera DBT) sia per CASO B (Notifica Precetto). "
             "Lascia 0 per saltare il check di congruità."
    )

    # 🆕 Data di attualizzazione del GBV (appare solo se GBV > 0)
    # Disponibile per entrambi i casi (A e B): disaccoppia la data del
    # conteggio del creditore dalla "Data di aggiudicazione" finale.
    if gbv_dichiarato > 0:
        # Default sensato in base al caso:
        # - CASO A: poco dopo la DBT (lascio 06/11/2022 come riferimento storico).
        # - CASO B: data del precetto (il creditore di norma conteggia al precetto).
        default_attualizzazione = (
            date(2022, 11, 6) if is_caso_A else data_decadenza_effettiva
        )
        atto_nome = "Lettera DBT" if is_caso_A else "Notifica Precetto"
        data_attualizzazione_gbv = st.date_input(
            "📅 Data del conteggio del creditore (attualizzazione del GBV)",
            value=default_attualizzazione,
            format="DD/MM/YYYY",
            help=(
                "⚠️ FONDAMENTALE: data fino a cui il creditore ha conteggiato "
                "gli interessi nel GBV dichiarato.\n\n"
                f"Per il **{caso}**, di norma coincide con la data della "
                f"**{atto_nome}** o con una data successiva indicata nel "
                "conteggio allegato dalla cedente.\n\n"
                "Il check di congruità userà QUESTA data per un confronto "
                "'alla pari' col nostro calcolo, evitando falsi positivi "
                "dovuti al disallineamento temporale tra il GBV dichiarato "
                "e la data di aggiudicazione finale."
            )
        )
    else:
        data_attualizzazione_gbv = None

    # 🔗 Salvo il GBV per il Tab 3 (NPL)
    st.session_state["gbv_dichiarato"] = gbv_dichiarato

    with st.expander("➕ Aggiungi Spese Legali / Altro"):
        spese_legali = st.number_input(
            "⚖️ Spese legali sostenute dal creditore / procedurali (€)",
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

        # --- PARAMETRI COMUNI (condivisi da entrambi i giri) ---
        params_comuni = {
            "importo_rata": importo_rata,
            "data_prima_rata": data_prima_rata,
            "frequenza": frequenza,
            "capitale_residuo": capitale_residuo,
            "tasso_mora": tasso_mora,
            "data_decadenza_effettiva": data_decadenza_effettiva,
            "data_pignoramento": data_pignoramento,
        }

        # --- GIRO B (Calcolo Attuale): stima del debito a oggi / data_fine ---
        st.caption("⏳ **Giro B** — Debito attuale aggiornato alla data di fine "
                   "calcolo per orientamento negoziale.")
        risultato = calcola_mora_unificato(**params_comuni, data_fine=data_fine)

        # --- GIRO A (Check GBV): calcolo congelato alla data di attualizzazione ---
        risultato_gbv = None
        if gbv_dichiarato > 0 and data_attualizzazione_gbv is not None:
            if data_attualizzazione_gbv < data_decadenza_effettiva:
                st.error(
                    f"⛔ La data di attualizzazione GBV "
                    f"({data_attualizzazione_gbv.strftime('%d/%m/%Y')}) è "
                    f"precedente alla decadenza effettiva "
                    f"({data_decadenza_effettiva.strftime('%d/%m/%Y')}). "
                    "Verificare."
                )
            else:
                st.caption(
                    "🔒 **Giro A** — Calcolo 'congelato' alla data di "
                    "attualizzazione del GBV per confronto contabile "
                    "'alla pari'."
                )
                risultato_gbv = calcola_mora_unificato(
                    **params_comuni, data_fine=data_attualizzazione_gbv
                )

        # --- Metriche totali generali ---
        col1, col2 = st.columns(2)
        col1.metric("🏛️ Credito IPOTECARIO", f"{fmt_eur(risultato['ipotecario'])}")
        col2.metric("📄 Credito CHIROGRAFARIO", f"{fmt_eur(risultato['chirografario'])}")

        totale_gen = risultato['ipotecario'] + risultato['chirografario']
        st.metric("💰 TOTALE interessi di mora", f"{fmt_eur(totale_gen)}")

        # ==========================================================
        # 📊 DETTAGLIO DEL CALCOLO INTERESSI (didattico — FASE 1 + FASE 2)
        # ==========================================================
        det = risultato["dettaglio"]

        # --- Ricostruzione fase1 / fase2 dai dati disponibili ---
        # FASE 1: somma degli interessi rata per rata (chiavi ipotecario/chirografario
        #         vivono nei dict delle singole rate dentro dettaglio["FASE_1_rate"]["rate"])
        fase1_rate_dict = det.get("FASE_1_rate", {}).get("rate", {})
        def _voci_rata(dr):
            ipot = dr.get("triennio_ipo_mora", 0.0) + dr.get("post_ipo_legale", 0.0)
            chiro = dr.get("pre_triennio_chiro", 0.0) + dr.get("post_chiro_diff", 0.0)
            return ipot, chiro

        fase1_interessi = sum(
            sum(_voci_rata(r))
            for r in fase1_rate_dict.values()
        )
        n_rate = det.get("FASE_1_rate", {}).get("numero_rate_generate", 0)

        # FASE 2: direttamente dai totali già calcolati (ipotecario + chirografario
        #         complessivi, sottratti i contributi accumulati nella fase 1)
        fase2_interessi = totale_gen - fase1_interessi

        with st.expander("📊 Dettaglio Calcolo Interessi"):
            st.markdown("### 🔢 Come vengono calcolati gli interessi di mora")
            st.caption(
                "Il calcolo è articolato in **due fasi distinte**, ciascuna "
                "con formula esplicita. La somma delle due restituisce il "
                "totale interessi di mora."
            )
            st.divider()

            f1_col, f2_col = st.columns(2)

            with f1_col:
                st.markdown("#### 🅰️ Interessi sulle Rate Scadute")
                st.markdown(
                    "**Formula:**  "
                    "`Quota capitale rata × Tasso di mora × Giorni di ritardo / 365`"
                )
                base_rate_scadute = n_rate * importo_rata
                st.markdown(
                    f"- **Fase 1:** Mora calcolata **rata per rata**, "
                    f"dalla scadenza di ciascuna rata fino alla **decadenza** "
                    f"({data_decadenza_effettiva.strftime('%d/%m/%Y')}).\n"
                    f"- **N° rate scadute:** {n_rate}\n"
                    f"- **Quota capitale rate scadute:** "
                    f"{fmt_eur(base_rate_scadute)}\n"
                    f"- **Tasso di mora:** {fmt_pct(tasso_mora)} (pattuito)\n"
                    f"- **Convenzione giorni:** /365\n"
                    f"- **Interessi rate scadute → 🅰️ = {fmt_eur(fase1_interessi)}**"
                )

                st.info(
                    "ℹ️ **Perché questo importo può sembrare 'basso'?**\n\n"
                    "Le rate maturano interessi in modo **progressivo**: la "
                    "rata più vecchia accumula tutti i giorni di ritardo, "
                    "quella più recente solo pochi giorni. Il software "
                    "**non applica il tasso sull'intero monte rate per "
                    "tutto il periodo**: itera rata per rata e somma i "
                    "contributi (equivalente alla formula della "
                    "*giacenza media*)."
                )

                # --- Tabella di scomposizione rata per rata ---
                rate_bk = det.get("FASE_1_rate", {}).get("rate_breakdown", [])
                if rate_bk:
                    with st.expander(
                        "📋 Scomposizione rata per rata "
                        "(giorni esatti di mora + interesse maturato)"
                    ):
                        righe = [
                            "| # | Data scadenza | Importo | Giorni mora | Interesse maturato |",
                            "|---:|:---:|---:|---:|---:|",
                        ]
                        for br in rate_bk:
                            righe.append(
                                f"| {br['i']} | "
                                f"{br['data_scadenza'].strftime('%d/%m/%Y')} | "
                                f"{fmt_eur(br['importo_rata'])} | "
                                f"{br['giorni_mora']} | "
                                f"{fmt_eur(br['interesse_maturato'])} |"
                            )
                        somma_gg = sum(br["giorni_mora"] for br in rate_bk)
                        somma_int = sum(br["interesse_maturato"] for br in rate_bk)
                        righe.append(
                            f"| **TOTALE** | — | "
                            f"**{fmt_eur(base_rate_scadute)}** | "
                            f"**{somma_gg}** | "
                            f"**{fmt_eur(somma_int)}** |"
                        )
                        st.markdown("\n".join(righe))

                        # Verifica didattica: equivalenza con la giacenza media
                        gg_medi = somma_gg / len(rate_bk)
                        giacenza_media = (
                            base_rate_scadute * tasso_mora * gg_medi / 365
                        )
                        st.caption(
                            f"✅ **Verifica equivalente — giacenza media:** "
                            f"giorni medi di ritardo = "
                            f"**{gg_medi:.1f}** (~{gg_medi/30:.1f} mesi). "
                            f"Applicando la formula `Capitale totale × Tasso "
                            f"× Giorni medi / 365`: "
                            f"{fmt_eur(base_rate_scadute)} × "
                            f"{fmt_pct(tasso_mora)} × {gg_medi:.1f} / 365 = "
                            f"**{fmt_eur(giacenza_media)}** "
                            f"(coincide con la somma rata-per-rata)."
                        )

            with f2_col:
                st.markdown("#### 🅱️ Interessi sul Capitale Residuo")
                st.markdown(
                    "**Formula:**  "
                    "`Capitale residuo × Tasso di mora × Giorni dalla decadenza / 365`"
                )
                gg_fase2 = (data_fine - data_decadenza_effettiva).days
                st.markdown(
                    f"- **Fase 2:** Mora calcolata sull'**intero capitale residuo** "
                    f"dalla **decadenza** ({data_decadenza_effettiva.strftime('%d/%m/%Y')}) "
                    f"fino alla **data di aggiudicazione** ({data_fine.strftime('%d/%m/%Y')}).\n"
                    f"- **Capitale residuo:** {fmt_eur(capitale_residuo)}\n"
                    f"- **Tasso di mora:** {fmt_pct(tasso_mora)} (pattuito)\n"
                    f"- **Giorni (decadenza → oggi):** {gg_fase2}\n"
                    f"- **Convenzione giorni:** /365\n"
                    f"- **Interessi capitale residuo → 🅱️ = {fmt_eur(fase2_interessi)}**"
                )

            st.divider()
            st.markdown(
                f"### ✅ Verifica quadratura\n\n"
                f"🅰️ Interessi rate scadute   **{fmt_eur(fase1_interessi)}**\n"
                f"🅱️ Interessi capitale residuo **{fmt_eur(fase2_interessi)}**\n"
                f"─────────────────────────────────\n"
                f"💰 TOTALE interessi di mora   **{fmt_eur(totale_gen)}**"
            )
            scarto_f = abs(fase1_interessi + fase2_interessi - totale_gen)
            if scarto_f > 0.01:
                st.error(f"⚠️ Scarto di quadratura: {fmt_eur(scarto_f)}")
            else:
                st.caption("✅ Quadratura verificata: 🅰️ + 🅱️ = 💰")

        # --- Salvo i totali per il Tab 3 (NPL) ---
        debito_totale = capitale_residuo + totale_gen + spese_legali
        st.session_state["debito_totale"] = debito_totale
        st.session_state["debito_dettaglio"] = {
            "capitale": capitale_residuo,
            "interessi": totale_gen,
            "spese_legali": spese_legali,
            "ipotecario": risultato["ipotecario"],
            "chirografario": risultato["chirografario"],
        }

        # ==========================================================
        # 🔎 CHECK GBV DICHIARATO DAL CREDITORE
        # ==========================================================
        if gbv_dichiarato > 0 and risultato_gbv is not None:
            st.divider()
            st.subheader("🔎 Check GBV dichiarato dal creditore")
            atto_label = "Lettera DBT" if is_caso_A else "Notifica Precetto"
            st.caption(
                f"Modalità: **{caso}** — Il GBV dichiarato viene paragonato al "
                f"nostro calcolo **congelato alla data del conteggio del "
                f"creditore** (**{data_attualizzazione_gbv.strftime('%d/%m/%Y')}**), "
                f"non alla data di aggiudicazione. Così evitiamo i falsi "
                f"positivi del check disaccoppiando la data del conteggio "
                f"(tipicamente legata alla {atto_label}) "
                f"dall'attualizzazione finale."
            )
            interessi_totali = risultato_gbv["ipotecario"] + risultato_gbv["chirografario"]
            capitale_totale = capitale_residuo
            totale_calcolato = capitale_totale + interessi_totali + spese_legali

            a1, a2, a3 = st.columns(3)
            a1.metric("🏦 Quota capitale residua mutuo", f"{fmt_eur(capitale_totale)}")
            a2.metric("⚖️ Spese legali sostenute", f"{fmt_eur(spese_legali)}")
            a3.metric("📈 Interessi reali (calcolati dal software) rispetto all'ultima data di attualizzazione GBV", f"{fmt_eur(interessi_totali)}")

            b1, b2, b3 = st.columns(3)
            b1.metric("🧮 TOTALE CALCOLATO (Capitale + Interessi + Spese Legali)", f"{fmt_eur(totale_calcolato)}")
            b2.metric("📑 GBV DICHIARATO + Spese Legali", f"{fmt_eur((gbv_dichiarato + spese_legali))}")

            delta = (gbv_dichiarato + spese_legali) - totale_calcolato
            b3.metric("📐 DELTA", f"{fmt_eur(delta)}", delta_color="inverse")

            SOGLIA = 10.0
            if delta > SOGLIA:
                st.error(
                    f"🚨 **Anomalia:** il GBV dichiarato supera il totale calcolato "
                    f"di {fmt_eur(delta)}. Possibile **anatocismo**, **estensione "
                    f"ipotecaria indebita**, **tassi di mora non dovuti** o **spese "
                    f"non documentate**. Verificare le voci in contestazione."
                )
            elif delta < -SOGLIA:
                st.warning(
                    f"ℹ️ Il totale calcolato supera il GBV dichiarato di "
                    f"{fmt_eur(abs(delta))}. Pretesa creditoria prudenziale "
                    f"(a favore del debitore). Verificare comunque i dati."
                )
            else:
                st.success(
                    f"✅ **GBV congruo:** importi allineati "
                    f"(scarto {fmt_eur(abs(delta))} entro la soglia di {fmt_eur(SOGLIA)})."
                )

        # ==========================================================
        # 📊 SPACCATO VISIVO TRIPARTIZIONE EX ART. 2855 c.c.
        # ==========================================================
        st.divider()
        st.subheader("📊 Divisione ex Art. 2855 c.c.")

        v = risultato["voci_2855"]
        fase1, fase2, fase3 = st.columns(3)

        with fase1:
            st.info(
                "**🔵 FASE 1 – PRE-TRIENNIO**\n\n"
                "Interessi maturati **prima dei 3 anni antecedenti il "
                "pignoramento**: degradano interamente a **chirografario**, "
                "pur restando al tasso di mora.\n\n"
                f"📄 Chirografario (mora):\n\n"
                f"### {fmt_eur(v['pre_chiro'])}"
            )

        with fase2:
            st.success(
                "**🟢 FASE 2 – TRIENNIO**\n\n"
                "Interessi maturati nei **3 anni esatti che precedono "
                "il pignoramento**: **garanzia ipotecaria piena** "
                "al tasso di mora pattuito.\n\n"
                f"🏛️ Ipotecario (mora):\n\n"
                f"### {fmt_eur(v['triennio_ipo'])}"
            )

        with fase3:
            st.warning(
                "**🟠 FASE 3 – POST-TRIENNIO**\n\n"
                "Interessi maturati **dopo il pignoramento**: la garanzia "
                "ipotecaria **degrada**, resta ipotecaria solo la quota al "
                "**tasso legale** (cambia ogni 1° gennaio), l'eccedenza "
                "diventa chirografaria.\n\n"
                f"🏛️ Ipotecario (legale): **{fmt_eur(v['post_ipo'])}**\n\n"
                f"📄 Chirografario (eccedenza): **{fmt_eur(v['post_chiro'])}**"
            )

        somma_voci = v['pre_chiro'] + v['triennio_ipo'] + v['post_ipo'] + v['post_chiro']
        scarto = abs(somma_voci - totale_gen)
        if scarto > 0.01:
            st.error(f"⚠️ Scarto di quadratura: {fmt_eur(scarto)} — verificare la logica.")
        else:
            st.caption("✅ Quadratura verificata: la somma delle 3 fasi coincide col totale.")


        # ==========================================================
        # 📋 DETTAGLIO CALCOLI ART. 2855 c.c. (TRASPARENZA)
        # ==========================================================
        det = risultato["dettaglio"]
        v = risultato["voci_2855"]

        # --- Confini esatti del triennio (3 anni a ritroso dal pignoramento) ---
        inizio_triennio, fine_triennio = calcola_triennio(data_pignoramento)
        gg_triennio = (fine_triennio - inizio_triennio).days  # 1095 o 1096

        # --- Fase 3 (post-triennio): dal pignoramento a data_fine ---
        gg_post = max((data_fine - fine_triennio).days, 0)

        # Spaccato anno per anno del tasso legale (calcolato sul capitale
        # residuo, contributo dominante della Fase 3).
        segmenti_legale = (
            det.get("FASE_2_capitale_residuo", {})
               .get("post_segmenti_legale", [])
        )

        with st.expander("🔍 Dettaglio calcoli Art. 2855 c.c."):
            st.markdown("## 📐 Matematica della Tripartizione ex Art. 2855 c.c.")

            # --- Box didattico: perché il triennio inizia esattamente DATA-3 ANNI ---
            st.info(
                f"**Perché il triennio ipotecario (Fase 2) inizia esattamente "
                f"il {inizio_triennio.strftime('%d/%m/%Y')} se la prima rata "
                f"insoluta è scaduta prima?**\n\n"
                f"Perché, secondo la prassi prevalente nei calcoli esecutivi "
                f"in base all'**Art. 2855 c.c.**, il triennio garantito copre "
                f"**esattamente i 3 anni antecedenti alla data del pignoramento**.\n\n"
                f"Tutto il periodo precedente a questa data **non gode del "
                f"privilegio ipotecario** e finisce nella **Fase 1 (Chirografo)**."
            )

            # --- Quadratura ---
            somma_voci = v["pre_chiro"] + v["triennio_ipo"] + v["post_ipo"] + v["post_chiro"]
            quadratura_ok = abs(somma_voci - totale_gen) <= 0.01

            st.markdown(f"""
            **Dati di contesto**
            - Mutuo stipulato il: **{data_stipula.strftime('%d/%m/%Y')}** *(dato informativo)*
            - Pignoramento il: **{data_pignoramento.strftime('%d/%m/%Y')}**
            - Data di aggiudicazione (fine calcolo): **{data_fine.strftime('%d/%m/%Y')}**
            - Capitale residuo: **{fmt_eur(capitale_residuo)}**
            - Tasso di mora pattuito: **{fmt_pct(tasso_mora)}**
            - Divisore giorni: **365** (anno civile)

            ---
            """)

            st.markdown("### 🔵 FASE 1 — PRE-TRIENNIO (Chirografario)")

            st.markdown(f"""
            **Periodo:** data prima rata scaduta → **{inizio_triennio.strftime('%d/%m/%Y')}** *(inizio triennio = pignoramento − 3 anni)*

            **Capitale di riferimento:** singola rata insoluta (importo: **{fmt_eur(importo_rata)}**)

            **Tasso applicato:** {fmt_pct(tasso_mora)} (tasso di mora pattuito)

            **Formula:**
            `Capitale × Tasso × Giorni / 365`

            Poiché gli interessi anteriori al triennio **degradano a chirografario**, la loro quota
            viene separata e mostrata come **chirografario pre-triennio**.

            **Risultato FASE 1:**
            🅰️ Quota chirografaria calcolata su tutte le rate insolute: **{fmt_eur(v['pre_chiro'])}**
            """)

            st.markdown("---")
            st.markdown("### 🟢 FASE 2 — TRIENNIO (Ipotecario)")

            st.markdown(f"""
            **Inizio triennio:** **{inizio_triennio.strftime('%d/%m/%Y')}**
            *(data pignoramento − 3 anni esatti)*

            **Fine triennio:** **{fine_triennio.strftime('%d/%m/%Y')}**
            *(coincide con la data del pignoramento)*

            **Giorni del triennio:** `{gg_triennio}` giorni
            *({"1096 = include un 29 febbraio" if gg_triennio == 1096 else "1095 = nessun 29 febbraio nel periodo"})*

            **Capitale di riferimento:**
            - Per le **rate scadute**: singola rata insoluta (**{fmt_eur(importo_rata)}**)
            - Per il **capitale residuo**: **{fmt_eur(capitale_residuo)}**

            **Tasso applicato:** {fmt_pct(tasso_mora)} (tasso di mora pattuito — pieno)

            **Formula:**
            `Capitale × {fmt_pct(tasso_mora)} × {gg_triennio} / 365`

            **Risultato FASE 2:**
            🅱️ Quota ipotecaria (mora piena sul triennio): **{fmt_eur(v['triennio_ipo'])}**
            """)

            st.markdown("---")
            st.markdown("### 🟠 FASE 3 — POST-TRIENNIO (Ipotecario al legale + Chirografario eccedenza)")

            st.markdown(f"""
            **Periodo:** **{fine_triennio.strftime('%d/%m/%Y')}** *(pignoramento)* → **{data_fine.strftime('%d/%m/%Y')}** *(aggiudicazione)*

            **Giorni fase 3:** `{gg_post}` giorni

            Dopo il pignoramento la garanzia ipotecaria **degrada**: la legge (art. 2855 c.c.)
            riconosce la sola quota al **tasso legale** come ipotecaria; l'eccedenza
            (mora pattuita − legale) diventa chirografaria.

            **⚠️ Attenzione:** il tasso legale **cambia ogni 1° gennaio**.
            Il calcolo è quindi **pro-rata temporis** spezzando il periodo ad ogni
            cambio d'anno solare.
            """)

            # --- Spaccato Fase 3 anno per anno ---
            if segmenti_legale:
                st.markdown(
                    f"**Quota A — Ipotecaria (tasso legale, calcolata sul "
                    f"capitale residuo {fmt_eur(capitale_residuo)}):**"
                )

                righe = ["| Periodo | Giorni | Tasso legale | Interesse |",
                         "|:--------|------:|------:|--------:|"]
                for seg in segmenti_legale:
                    periodo = (
                        f"Dal {seg['inizio'].strftime('%d/%m/%Y')} "
                        f"al {seg['fine'].strftime('%d/%m/%Y')}"
                    )
                    righe.append(
                        f"| {periodo} | {seg['giorni']} | "
                        f"{fmt_pct(seg['tasso'])} | "
                        f"{fmt_eur(seg['interesse'])} |"
                    )
                tot_segmenti = sum(s["interesse"] for s in segmenti_legale)
                righe.append(
                    f"| **TOTALE Quota A (capitale residuo)** | "
                    f"**{gg_post}** | | **{fmt_eur(tot_segmenti)}** |"
                )
                st.markdown("\n".join(righe))

                st.caption(
                    "ℹ️ Lo spaccato sopra è calcolato sul **capitale residuo** "
                    "(contributo dominante della Fase 3). Nel totale "
                    f"ipotecario legale ({fmt_eur(v['post_ipo'])}) sono inclusi "
                    "anche eventuali contributi residui delle singole rate "
                    "che si estendono oltre il pignoramento (se la decadenza "
                    "è posteriore al pignoramento)."
                )
            else:
                st.caption(
                    "Nessun periodo post-triennio per il capitale residuo "
                    "(la data di aggiudicazione coincide o precede il pignoramento)."
                )

            st.markdown(f"""

            **Quota B — Chirografaria (eccedenza mora − legale):**

            Sullo stesso periodo della Quota A, applicando la differenza
            (tasso mora − tasso legale) giorno per giorno.

            | Voce | Importo |
            |------|--------:|
            | 🏛️ TOTALE Quota A — Ipotecaria (legale) | **{fmt_eur(v['post_ipo'])}** |
            | 📄 TOTALE Quota B — Chirografaria (eccedenza) | **{fmt_eur(v['post_chiro'])}** |
            """)

            st.markdown("---")
            st.markdown("### ✅ Quadratura")

            st.markdown(f"""
            | Fase | Voci | Importo |
            |:-----|:-----|--------:|
            | 🔵 Pre-triennio | Chirografario | {fmt_eur(v['pre_chiro'])} |
            | 🟢 Triennio | Ipotecario (mora) | {fmt_eur(v['triennio_ipo'])} |
            | 🟠 Post-triennio | Ipotecario (legale) | {fmt_eur(v['post_ipo'])} |
            | 🟠 Post-triennio | Chirografario (eccedenza) | {fmt_eur(v['post_chiro'])} |
            | **TOTALE INTERESSI** | | **{fmt_eur(somma_voci)}** |

            | Controllo | |
            |:----------|-|
            | Totale interessi da calcolo | {fmt_eur(totale_gen)} |
            | Somma 4 voci art. 2855 | {fmt_eur(somma_voci)} |
            | Scarto | {fmt_eur(abs(somma_voci - totale_gen))} |
            | {"✅ Quadratura OK" if quadratura_ok else "⚠️ Verificare"} | |
            """)

        n_rate = risultato["dettaglio"]["FASE_1_rate"]["numero_rate_generate"]
        st.info(f"🔢 Rate insolute auto-generate (prima rata → decadenza): **{n_rate}**")

        with st.expander("🔍 Dettaglio calcolo (dati grezzi)"):
            st.json(risultato['dettaglio'])

        # ==========================================================
        # 📄 GENERAZIONE PDF (in memoria) → salvataggio in session_state
        # ==========================================================
        try:
            segmenti_legale = (
                risultato["dettaglio"]
                .get("FASE_2_capitale_residuo", {})
                .get("post_segmenti_legale", [])
            )
            report_data = {
                "input": {
                    "tasso_mora": tasso_mora,
                    "data_stipula": data_stipula,
                    "data_pignoramento": data_pignoramento,
                    "data_fine": data_fine,
                    "data_prima_rata": data_prima_rata,
                    "frequenza": frequenza,
                    "importo_rata": importo_rata,
                    "capitale_residuo": capitale_residuo,
                    "data_decadenza_effettiva": data_decadenza_effettiva,
                    "is_caso_A": is_caso_A,
                    "spese_legali": spese_legali,
                },
                "calcolo": {
                    "risultato": risultato,
                    "totale_gen": totale_gen,
                    "fase1_interessi": fase1_interessi,
                    "fase2_interessi": fase2_interessi,
                    "n_rate": n_rate,
                },
                "triennio": {
                    "inizio_triennio": inizio_triennio,
                    "fine_triennio": fine_triennio,
                    "gg_triennio": gg_triennio,
                    "gg_post": gg_post,
                    "segmenti_legale": segmenti_legale,
                },
                "gbv": (
                    {
                        "gbv_dichiarato": gbv_dichiarato,
                        "data_attualizzazione_gbv": data_attualizzazione_gbv,
                        "risultato_gbv": risultato_gbv,
                    }
                    if gbv_dichiarato > 0 and risultato_gbv is not None
                    else None
                ),
            }
            pdf_bytes = genera_report_pdf(report_data, password=pdf_password)
            st.session_state["pdf_report_bytes"] = pdf_bytes
            st.session_state["pdf_report_protetto_da_pwd"] = bool(pdf_password)
        except Exception as e:
            st.warning(
                f"⚠️ Generazione PDF non riuscita: {e}. "
                "I calcoli a schermo restano validi."
            )
            st.session_state.pop("pdf_report_bytes", None)

    # --- Download PDF (vive fuori dal blocco del button per persistere ai rerun) ---
    if "pdf_report_bytes" in st.session_state:
        st.divider()
        nome_file = (
            f"Report_MORA_{date.today().strftime('%Y-%m-%d')}.pdf"
        )
        protetto = st.session_state.get("pdf_report_protetto_da_pwd", False)
        if protetto:
            st.caption(
                "🔒 PDF cifrato con la password inserita in sidebar. "
                "Copia del testo e modifica disabilitate."
            )
        else:
            st.caption(
                "🔒 PDF senza password di apertura, ma con copia del testo "
                "e modifica disabilitate."
            )
        st.download_button(
            label="📄 Esporta Report in PDF",
            data=st.session_state["pdf_report_bytes"],
            file_name=nome_file,
            mime="application/pdf",
            type="primary",
        )

# ----------------------------------------------------------
# TAB 2 — PREVISIONE SPESE ESECUTIVE (consulenza strategica)
# ----------------------------------------------------------
with tab2:
    st.subheader("🔮 Stima dei costi di una procedura esecutiva")
    st.caption("Proiezione forfettaria dei costi futuri se il creditore prosegue "
               "con l'esecuzione. Valori indicativi: verificare col foro competente.")

    p1, p2 = st.columns(2)
    tipo_procedura = p1.selectbox(
        "Tipo di procedura",
        options=["Pignoramento Immobiliare", "Pignoramento Mobiliare", "Pignoramento Presso Terzi"],
        index=0,
    )
    valore_bene = p2.number_input(
        "Valore stimato dell'immobile / bene (€)",
        min_value=0.0,
        value=120000.0,
        step=5000.0,
        help="Valore di mercato/perizia. Per l'immobiliare incide sul compenso "
             "del custode/delegato (maggiore tra forfait e 3%)."
    )

    # Salvo valore_bene per il Tab 3
    st.session_state["valore_bene"] = valore_bene

    st.divider()

    # ============================================================
    # VOCI MODIFICABILI — Immobiliare
    # ============================================================
    if tipo_procedura == "Pignoramento Immobiliare":
        st.markdown("#### 📑 Voci modificabili – *Pignoramento Immobiliare*")

        r1, r2 = st.columns(2)
        spese_vive_val = r1.number_input(
            "Spese vive (CU = Contributo Unificato, trascrizioni, ecc.)",
            min_value=0.0, value=float(SPESE_IMMOBILIARE["spese_vive"]),
            step=50.0, format="%.2f"
        )
        ctu_val = r2.number_input(
            "CTU (perizia di stima)",
            min_value=0.0, value=float(SPESE_IMMOBILIARE["ctu"]),
            step=50.0, format="%.2f"
        )

        r3, r4 = st.columns(2)
        custode_forfait = SPESE_IMMOBILIARE["custode_delegato"]
        custode_pct = valore_bene * SPESE_IMMOBILIARE["perc_custode"]
        custode_default = max(custode_forfait, custode_pct)

        custode_val = r3.number_input(
            "Custode / Professionista delegato",
            min_value=0.0, value=float(custode_default),
            step=50.0, format="%.2f",
            help=f"Forfait: {fmt_eur(custode_forfait)} | 3% del valore: "
                 f"{fmt_eur(custode_pct)} | Default: {fmt_eur(custode_default)}"
        )
        pubblicita_val = r4.number_input(
            "Pubblicità asta (PVP)",
            min_value=0.0, value=float(SPESE_IMMOBILIARE["pubblicita"]),
            step=50.0, format="%.2f"
        )

        r5, r6 = st.columns(2)
        spese_legali_nostre_val = r5.number_input(
            "Nostre spese legali",
            min_value=0.0, value=float(SPESE_IMMOBILIARE["spese_legali_nostre"]),
            step=50.0, format="%.2f"
        )

        # Placeholder per allineamento grafico
        r6.markdown("&nbsp;")

        totale_spese = spese_vive_val + ctu_val + custode_val + pubblicita_val + spese_legali_nostre_val
        st.session_state["spese_future"] = totale_spese

        voci_spese = {
            "Spese vive (CU, trascrizioni, ecc.)": spese_vive_val,
            "CTU (perizia di stima)": ctu_val,
            "Custode / Professionista delegato": custode_val,
            "Pubblicità asta (PVP)": pubblicita_val,
            "Nostre spese legali": spese_legali_nostre_val,
        }

    # ============================================================
    # VOCI MODIFICABILI — Mobiliare / Presso Terzi
    # ============================================================
    else:
        st.markdown("#### 📑 Voci modificabili – *Pignoramento Mobiliare / Presso Terzi*")

        r1, r2 = st.columns(2)
        spese_vive_val = r1.number_input(
            "Spese vive (notifica, bolli)",
            min_value=0.0, value=float(SPESE_MOBILIARE["spese_vive"]),
            step=50.0, format="%.2f"
        )
        uff_legali_val = r2.number_input(
            "Ufficiale Giudiziario / Legali",
            min_value=0.0, value=float(SPESE_MOBILIARE["ufficiale_legali"]),
            step=50.0, format="%.2f"
        )

        r3, r4 = st.columns(2)
        spese_legali_nostre_val = r3.number_input(
            "Nostre spese legali",
            min_value=0.0, value=float(SPESE_MOBILIARE["spese_legali_nostre"]),
            step=50.0, format="%.2f"
        )
        r4.markdown("&nbsp;")

        totale_spese = spese_vive_val + uff_legali_val + spese_legali_nostre_val
        st.session_state["spese_future"] = totale_spese

        voci_spese = {
            "Spese vive (notifica, bolli)": spese_vive_val,
            "Ufficiale Giudiziario / Legali": uff_legali_val,
            "Nostre spese legali": spese_legali_nostre_val,
        }

    st.divider()
    st.metric("💸 TOTALE SPESE ESECUTIVE STIMATE", f"{fmt_eur(totale_spese)}")

    st.info(
        f"⚠️ **Attenzione:** proseguendo con la procedura, il debito aumenterà di "
        f"circa **{fmt_eur(totale_spese)}**, riducendo il ricavato netto della vendita. "
        f"Questi costi sono in **prededuzione** (art. 2770 c.c.) e vengono soddisfatti "
        f"con priorità sul ricavato, prima ancora del creditore ipotecario."
    )

    incidenza_pct = None
    if tipo_procedura == "Pignoramento Immobiliare" and valore_bene > 0:
        incidenza_pct = (totale_spese / valore_bene) * 100
        st.caption(f"📉 Incidenza delle spese sul valore del bene: **{fmt_pct(incidenza_pct/100, decimali=1)}**")

    # ==========================================================
    # 📄 EXPORT PDF — Spese Esecutive
    # ==========================================================
    try:
        report_spese = {
            "tipo_procedura": tipo_procedura,
            "valore_bene": valore_bene,
            "voci": voci_spese,
            "totale_spese": totale_spese,
            "incidenza_pct": incidenza_pct,
        }
        st.session_state["pdf_spese_bytes"] = genera_report_pdf_spese(
            report_spese, password=pdf_password
        )
        st.session_state["pdf_spese_protetto_da_pwd"] = bool(pdf_password)
    except Exception as e:
        st.warning(f"⚠️ Generazione PDF Spese non riuscita: {e}.")
        st.session_state.pop("pdf_spese_bytes", None)

    if "pdf_spese_bytes" in st.session_state:
        st.divider()
        protetto = st.session_state.get("pdf_spese_protetto_da_pwd", False)
        st.caption(
            "🔒 PDF cifrato con la password della sidebar. Copia/modifica disabilitate."
            if protetto
            else "🔒 PDF senza password di apertura, ma con copia/modifica disabilitate."
        )
        st.download_button(
            label="📄 Esporta Spese Esecutive in PDF",
            data=st.session_state["pdf_spese_bytes"],
            file_name=f"Report_MORA_Spese_{date.today().strftime('%Y-%m-%d')}.pdf",
            mime="application/pdf",
            type="primary",
            key="dl_spese",
        )

# ----------------------------------------------------------
# TAB 3 — ACQUISTO CREDITO NPL E STRALCIO
# ----------------------------------------------------------
with tab3:
    st.subheader("🤝 Acquisto Credito (NPL) e Stralcio")
    st.caption("Logica waterfall per l'investitore che acquista credito deteriorato. "
               "Simula l'offerta target partendo dal GBV.")

    # --- Recupero dati dagli altri tab ---
    debito = st.session_state.get("debito_totale", 0.0)
    spese_procedura = st.session_state.get("spese_future", 0.0)
    gbv_dichiarato = st.session_state.get("gbv_dichiarato", 0.0)

    # --- GBV base: usiamo il GBV DICHIARATO dalla cedente (la pretesa) ---
    # Se non è stato inserito (0), fallback sul debito calcolato a oggi (Tab 1).
    if gbv_dichiarato > 0:
        gbv_base = gbv_dichiarato
        fonte_gbv = "GBV dichiarato dalla cedente (Tab 1)"
    else:
        gbv_base = debito
        fonte_gbv = "Debito calcolato a oggi (Tab 1) — nessun GBV dichiarato inserito"

    if gbv_base <= 0:
        st.info(
            "⚠️ **Dati non disponibili.** "
            "Esegui prima il **Tab 1 (Auditing)** e poi il "
            "**Tab 2 (Previsione Spese Esecutive)** per popolare "
            "le variabili di calcolo."
        )
        st.stop()

    r1, r2, r3 = st.columns(3)
    r1.metric("🏦 GBV Partenza", f"{fmt_eur(gbv_base)}", help=f"Fonte: {fonte_gbv}")
    r2.metric("💸 Spese Procedura (Tab 2)", f"{fmt_eur(spese_procedura)}")
    r3.metric("📐 Debito Reale Calcolato", f"{fmt_eur(debito)}",
              help="Ricostruzione millimetrica del Tab 1 (capitale + interessi mora + spese legali). "
                   "Termine di confronto con la pretesa della cedente.")

    st.divider()

    # ============================================================
    # SEZIONE: COSTI DI ACQUISIZIONE CREDITO (modificabili)
    # ============================================================
    st.markdown("#### 💼 Costi di Acquisizione Credito")

    a1, a2, a3, a4 = st.columns(4)
    fronting_val = a1.number_input(
        "Fronting (€)",
        min_value=0.0, value=float(COSTI_ACQUISIZIONE["fronting"]),
        step=100.0, format="%.2f",
        help="Corrispettivo per l'apertura della linea di credito / garanzia."
    )
    notaio_val = a2.number_input(
        "Notaio (€)",
        min_value=0.0, value=float(COSTI_ACQUISIZIONE["notaio"]),
        step=100.0, format="%.2f",
        help="Formalizzazione dell'atto di cessione del credito."
    )
    servicer_val = a3.number_input(
        "Gestore credito (€)",
        min_value=0.0, value=float(COSTI_ACQUISIZIONE["servicer"]),
        step=100.0, format="%.2f",
        help="Compenso del servicer per la gestione del credito acquistato."
    )
    advisors_val = a4.number_input(
        "Advisors (€)",
        min_value=0.0, value=float(COSTI_ACQUISIZIONE["advisors"]),
        step=100.0, format="%.2f",
        help="Consulenza legale, due diligence e supporto tecnico."
    )

    costi_acquisizione = fronting_val + notaio_val + servicer_val + advisors_val
    totale_spese_fisse = spese_procedura + costi_acquisizione

    st.caption(f"💼 Costi Acquisizione: **{fmt_eur(costi_acquisizione)}** | "
               f"📋 Totale Spese Fisse (procedura + acquisizione): **{fmt_eur(totale_spese_fisse)}**")

    st.divider()

    # ============================================================
    # SLIDER MARGINE DI TRATTATIVA
    # ============================================================
    st.markdown("#### 🎯 Margine di Trattativa / Sconto")
    margine = st.slider(
        "Margine di trattativa / sconto (%)",
        min_value=0, max_value=60, value=20, step=1,
        help="Percentuale di sconto applicata alla base netta per ottenere "
             "l'offerta target. Default 20% (soglia indicativa NPL)."
    ) / 100.0

    # ============================================================
    # Durata stimata operazione (per IRR annualizzato)
    # ============================================================
    durata_mesi = st.number_input(
        "⏱ Durata stimata operazione (mesi)",
        min_value=1, max_value=120, value=18, step=1,
    )

    # ============================================================
    # WATERFALL NPL
    # ============================================================
    base_netta = gbv_base - totale_spese_fisse
    importo_margine = base_netta * margine
    offerta_target = base_netta * (1 - margine)

    st.markdown("#### 📊 Waterfall – Dal GBV all'Offerta Target")

    w1, w2, w3, w4 = st.columns(4)
    w1.metric("🏦 GBV Partenza", f"{fmt_eur(gbv_base)}")
    w2.metric("− Totale Spese Fisse", f"{fmt_eur(totale_spese_fisse)}",
              help="Spese procedura + costi di acquisizione (sopra)")
    w3.metric("= Base Netta pre-sconto", f"{fmt_eur(base_netta)}")
    w4.metric("− Sconto trattativa (%)", fmt_pct(margine, decimali=0))

    st.divider()

    delta_pct_gbv = (offerta_target / gbv_base) if gbv_base > 0 else 0
    st.metric(
        "🎯 OFFERTA TARGET (Servicer)",
        f"{fmt_eur(offerta_target)}",
        delta=f"{fmt_pct(delta_pct_gbv, decimali=1)} del GBV",
        delta_color="normal"
    )

    # --- Messaggi di stato ---
    if offerta_target <= 0:
        st.error(
            f"🚨 **Offerta target negativa o nulla ({fmt_eur(offerta_target)}).** "
            f"Le spese fisse ({fmt_eur(totale_spese_fisse)}) superano o eguagliano il GBV "
            f"({fmt_eur(gbv_base)}). L'operazione NPL **non è sostenibile** con questi "
            f"parametri. Rivedere: (a) soglia di ribasso, (b) costi di acquisizione, "
            f"(c) stima del GBV."
        )
    elif offerta_target >= gbv_base:
        st.warning(
            f"⚠️ **Offerta target >= GBV ({fmt_eur(offerta_target)}).** "
            f"Questo scenario è **non realistico**: nessun investitore NPL "
            f"acquista un credito senza sconto. Verificare le spese fisse "
            f"o ricalcolare il GBV."
        )
    else:
        st.success(
            f"✅ **Operazione sostenibile.** Offerta target: "
            f"**{fmt_eur(offerta_target)}** ({fmt_pct(1-margine, decimali=0)} del GBV, "
            f"margine investitore: {fmt_pct(margine, decimali=0)}). "
            f"Base netta disponibile: {fmt_eur(base_netta)}."
        )

 # ============================================================
    # METRICHE NPL PER INVESTITORI
    # ============================================================
    st.markdown("#### 📐 Metriche Finanziarie – Investitori NPL")

    # Capitale Investito Totale = Offerta Target + Totale Spese Fisse
    capitale_investito = offerta_target + totale_spese_fisse

    # 1) Utile Lordo = margine in Euro generato sull'operazione (sul GBV)
    utile_lordo = base_netta - offerta_target  # = importo_margine

    # 2) Utile da Interessi Maturati (DELTA NOMINALE, già a oggi)
    #    Debito Reale Calcolato (Tab 1) è già attualizzato a oggi
    #    → nessuna riattualizzazione. 1A: mostrato anche se negativo.
    utile_interessi_maturati = debito - gbv_base

    # 3) Utile Totale
    utile_totale = utile_lordo + utile_interessi_maturati

    # ROE = Utile Totale / Capitale Investito Totale
    roe = utile_totale / capitale_investito if capitale_investito > 0 else 0

    # IRR annualizzato — il delta interessi è incassato A FINE PROCEDURA
    # rendimento di periodo = Utile Totale / Capitale, poi annualizzato sui mesi
    irr_annuale = ((1 + roe) ** (12 / durata_mesi) - 1) if durata_mesi > 0 else 0

    # --- Waterfall esplicito della composizione dell'utile ---
    st.markdown("##### 🧮 Composizione dell'Utile")
    cu1, cu2, cu3 = st.columns(3)
    cu1.metric("💶 Utile Lordo (su GBV)", f"{fmt_eur(utile_lordo)}",
               help="Base Netta − Offerta Target = margine generato sul GBV dichiarato.")
    cu2.metric("➕ Utile da Interessi Maturati", f"{fmt_eur(utile_interessi_maturati)}",
               help="Debito Reale Calcolato (Tab 1, a oggi) − GBV di partenza. "
                    "Valore nominale: il debito reale è già attualizzato a oggi, "
                    "quindi non si riattualizza. Può essere negativo se il GBV "
                    "dichiarato supera il debito ricostruito.")
    cu3.metric("= Utile Totale", f"{fmt_eur(utile_totale)}")

    if utile_interessi_maturati < 0:
        st.warning(
            f"⚠️ **Delta interessi negativo ({fmt_eur(utile_interessi_maturati)}).** "
            f"Il GBV di partenza ({fmt_eur(gbv_base)}) supera il Debito Reale "
            f"Calcolato ({fmt_eur(debito)}). Verificare la pretesa della cedente "
            f"o la data di attualizzazione del Tab 1. Il valore è comunque "
            f"computato per intero (riduce l'Utile Totale)."
        )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🎯 Offerta Target", f"{fmt_eur(offerta_target)}")
    m2.metric("💶 Utile Totale", f"{fmt_eur(utile_totale)}",
              help="Utile Lordo + Utile da Interessi Maturati")
    m3.metric("📊 ROE", fmt_pct(roe),
              help="Return on Equity = Utile Totale / Capitale Investito Totale")
    m4.metric("📈 IRR Annualizzato", fmt_pct(irr_annuale),
              help=f"Rendimento annualizzato su {durata_mesi} mesi. "
                   f"Il delta interessi è incassato a fine procedura.")
    
    # ============================================================
    # GRAFICO DI SENSIBILITÀ – Offerta vs Utile Lordo & ROE
    # ============================================================
    st.divider()
    st.markdown("##### 📈 Analisi di Sensibilità: Offerta → Utile & ROE")

    # Range di simulazione: sconto dal 10% al 60% sulla Base Netta
    sconti = [s / 100.0 for s in range(10, 61)]
    offerte_sim = [base_netta * (1 - s) for s in sconti]
    utili_sim = [base_netta * s for s in sconti]  # utile = base_netta * margine

    # ROE per ogni scenario simulato
    roe_sim = []
    for off, ut in zip(offerte_sim, utili_sim):
        cap_inv = off + totale_spese_fisse
        roe_sim.append((ut / cap_inv * 100) if cap_inv > 0 else 0)

    fig = go.Figure()

    # Curva Utile Lordo vs Offerta
    fig.add_trace(go.Scatter(
        x=offerte_sim,
        y=utili_sim,
        mode="lines",
        name="Utile Lordo",
        line=dict(color="#1f77b4", width=3),
        customdata=roe_sim,
        hovertemplate=(
            "Offerta: %{x:,.0f} €<br>"
            "Utile Lordo: %{y:,.0f} €<br>"
            "ROE: %{customdata:.2f}%<extra></extra>"
        ),
    ))

    # Marker vistoso sullo scenario "Offerta Target" attuale
    fig.add_trace(go.Scatter(
        x=[offerta_target],
        y=[utile_lordo],
        mode="markers",
        name="Offerta Target",
        marker=dict(color="#ff4b4b", size=16, symbol="star",
                    line=dict(color="white", width=1.5)),
        hovertemplate=(
            "🎯 OFFERTA TARGET<br>"
            "Offerta: %{x:,.0f} €<br>"
            "Utile: %{y:,.0f} €<br>"
            f"ROE: {fmt_pct(roe)}<extra></extra>"
        ),
    ))

    # Linee tratteggiate di proiezione sugli assi
    fig.add_shape(type="line", x0=offerta_target, x1=offerta_target,
                  y0=0, y1=utile_lordo,
                  line=dict(color="#ff4b4b", width=1.5, dash="dash"))
    fig.add_shape(type="line", x0=0, x1=offerta_target,
                  y0=utile_lordo, y1=utile_lordo,
                  line=dict(color="#ff4b4b", width=1.5, dash="dash"))

    # Annotation con il ROE atteso collegata al punto target
    fig.add_annotation(
        x=offerta_target, y=utile_lordo,
        text=(f"<b>🎯 Offerta Target</b><br>"
              f"{fmt_eur(offerta_target, 0)}<br>"
              f"<b>ROE Atteso: {fmt_pct(roe)}</b>"),
        showarrow=True, arrowhead=2, arrowsize=1.2, arrowwidth=2,
        arrowcolor="#ff4b4b",
        ax=60, ay=-60,
        bgcolor="rgba(255,75,75,0.12)",
        bordercolor="#ff4b4b", borderwidth=1.5, borderpad=8,
        font=dict(size=13, color="#ff4b4b"),
    )

    fig.update_layout(
        title="Sensibilità Utile Lordo all'Importo dell'Offerta",
        xaxis_title="Importo Offerta (€)",
        yaxis_title="Utile Lordo (€)",
        # separators: 1° char = separatore decimali, 2° char = separatore migliaia
        # ",." → 1.234,56 (formato italiano)
        separators=",.",
        xaxis=dict(tickformat=",.0f", ticksuffix=" €"),
        yaxis=dict(tickformat=",.0f", ticksuffix=" €"),
        hovermode="closest",
        template="plotly_white",
        height=480,
        margin=dict(l=20, r=20, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
    )

    st.plotly_chart(fig, use_container_width=True)

    # ==========================================================
    # 📄 EXPORT PDF — Acquisto Credito NPL
    # ==========================================================
    try:
        report_npl = {
            "gbv_base": gbv_base,
            "fonte_gbv": fonte_gbv,
            "spese_procedura": spese_procedura,
            "costi_acquisizione": costi_acquisizione,
            "totale_spese_fisse": totale_spese_fisse,
            "voci_costi_acq": {
                "fronting": fronting_val,
                "notaio": notaio_val,
                "servicer": servicer_val,
                "advisors": advisors_val,
            },
            "debito_reale_calcolato": debito,
            "margine": margine,
            "durata_mesi": durata_mesi,
            "base_netta": base_netta,
            "importo_margine": importo_margine,
            "offerta_target": offerta_target,
            "utile_lordo": utile_lordo,
            "utile_interessi_maturati": utile_interessi_maturati,
            "utile_totale": utile_totale,
            "capitale_investito": capitale_investito,
            "roe": roe,
            "irr_annuale": irr_annuale,
        }
        st.session_state["pdf_npl_bytes"] = genera_report_pdf_npl(
            report_npl, password=pdf_password
        )
        st.session_state["pdf_npl_protetto_da_pwd"] = bool(pdf_password)
    except Exception as e:
        st.warning(f"⚠️ Generazione PDF NPL non riuscita: {e}.")
        st.session_state.pop("pdf_npl_bytes", None)

    if "pdf_npl_bytes" in st.session_state:
        st.divider()
        protetto = st.session_state.get("pdf_npl_protetto_da_pwd", False)
        st.caption(
            "🔒 PDF cifrato con la password della sidebar. Copia/modifica disabilitate."
            if protetto
            else "🔒 PDF senza password di apertura, ma con copia/modifica disabilitate."
        )
        st.download_button(
            label="📄 Esporta Analisi NPL in PDF",
            data=st.session_state["pdf_npl_bytes"],
            file_name=f"Report_MORA_NPL_{date.today().strftime('%Y-%m-%d')}.pdf",
            mime="application/pdf",
            type="primary",
            key="dl_npl",
        )
