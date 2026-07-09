"""Tab 1 — Auditing e Check GBV."""

from datetime import date

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from calcoli import (
    FREQUENZA_MESI,
    calcola_triennio,
    calcola_mora_unificato,
    calcola_credito_sofferenza,
    estrai_rate_insolute_da_piano,
    genera_piano_ammortamento,
    METODO_TRIENNIO_SOLARE,
    BASE_CAPITALE_INTERESSI,
    BASE_SOLO_CAPITALE,
    TASSO_TRIENNIO_LEGALE,
    TASSO_TRIENNIO_CONVENZIONALE,
    TASSO_TRIENNIO_MORA,
)
from piano_io import carica_piano_da_file
from pdf_export import genera_report_pdf
from formatters import fmt_eur, fmt_pct
from ui_common import valori_esempio


def render(ctx):
    tasso_mora = ctx["tasso_mora"]
    data_stipula = ctx["data_stipula"]
    data_pignoramento = ctx["data_pignoramento"]
    data_fine = ctx["data_fine"]
    caso = ctx["caso"]
    is_caso_A = ctx["is_caso_A"]
    metodo_triennio = ctx["metodo_triennio"]
    anno_civile = ctx["anno_civile"]
    pdf_password = ctx["pdf_password"]

    # --- Scelta della modalità di calcolo del credito ---
    modalita_credito = st.radio(
        "Modalità di calcolo del credito",
        options=[
            "📉 Rate insolute (mutuo in ammortamento)",
            "🏦 Sofferenza / Estratto conto ex art. 50 TUB",
        ],
        index=0,
        horizontal=True,
        key="t1_modalita_credito",
        help=(
            "**Rate insolute:** genera le rate dal piano e calcola la mora "
            "rata per rata (mutuo ancora in ammortamento).\n\n"
            "**Sofferenza / Estratto conto:** credito già 'cristallizzato' "
            "da estratto conto ex art. 50 TUB (posizione a sofferenza), "
            "come nei conteggi professionali. Riproduce quel metodo e offre "
            "la versione 'da contestazione' senza anatocismo."
        ),
    )
    if modalita_credito.startswith("🏦"):
        _render_sofferenza(ctx)
        return

    intro_col, ex_col = st.columns([3, 1])
    with intro_col:
        st.subheader("📋 Dati del piano e del credito")
    with ex_col:
        if st.button("📋 Carica esempio", help="Precompila un caso "
                     "realistico completo per capire come funziona l'app."):
            st.session_state["autofill_pending"] = valori_esempio()
            st.session_state["mostra_risultati"] = True
            st.toast("Esempio caricato: premi 'Calcola' o guarda i risultati.",
                     icon="📋")
            st.rerun()

    c1, c2, c3 = st.columns(3)
    importo_rata = c1.number_input(
        "Importo singola rata (€)",
        min_value=0.0,
        value=800.0,
        step=50.0,
        help="Inserire l'intero importo della rata scaduta (Quota Capitale + Quota Interessi)",
        key="t1_importo_rata",
    )
    data_prima_rata = c2.date_input(
        "Data scadenza PRIMA rata insoluta",
        value=date(2021, 3, 1), format="DD/MM/YYYY",
        key="t1_data_prima_rata",
    )
    frequenza = c3.selectbox(
        "Frequenza rate",
        options=list(FREQUENZA_MESI.keys()), index=0,
        key="t1_frequenza",
    )

    c4, c5 = st.columns(2)
    capitale_residuo = c4.number_input(
        "Capitale Residuo all'ultima rata pagata (€)",
        min_value=0.0,
        value=100000.0,
        step=1000.0,
        help="Intero capitale esigibile alla data di decadenza/precetto. "
             "Su questo importo decorre la mora dalla decadenza in poi. "
             "Le rate insolute pre-decadenza contribuiscono SOLO con i loro interessi. "
             "Verificare piano di ammortamento.",
        key="t1_capitale_residuo",
    )

    # ---- Campo Data decadenza / precetto (key unica, label dinamica) ----
    # Default: se non c'è già un valore in session_state, usa quello adatto al caso
    if "t1_data_decadenza" not in st.session_state:
        st.session_state["t1_data_decadenza"] = (
            date(2022, 1, 20) if is_caso_A else date(2023, 2, 1)
        )
    if is_caso_A:
        data_decadenza_effettiva = c5.date_input(
            "📩 Data Lettera DBT",
            format="DD/MM/YYYY",
            help="Data della comunicazione di decadenza dal beneficio del termine.",
            key="t1_data_decadenza",
        )
    else:
        data_decadenza_effettiva = c5.date_input(
            "📜 Data Notifica Precetto",
            format="DD/MM/YYYY",
            help="In assenza di DBT, la decadenza decorre dalla notifica del precetto.",
            key="t1_data_decadenza",
        )

    # ---- GBV dichiarato + voci secondarie ----
    gbv_dichiarato = st.number_input(
        "🏦 GBV Dichiarato dalla Cedente (€)",
        min_value=0.0,
        value=0.0,
        step=1000.0,
        help="Importo complessivo (Gross Book Value) richiesto dalla banca/cedente. "
             "Funziona sia per CASO A (Lettera DBT) sia per CASO B (Notifica Precetto). "
             "Lascia 0 per saltare il check di congruità.",
        key="t1_gbv",
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
        if "t1_data_att_gbv" not in st.session_state:
            st.session_state["t1_data_att_gbv"] = default_attualizzazione
        data_attualizzazione_gbv = st.date_input(
            "📅 Data del conteggio del creditore (attualizzazione del GBV)",
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
            ),
            key="t1_data_att_gbv",
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

    # ==========================================================
    # 📈 TASSO DI MORA VARIABILE NEL TEMPO (opzionale)
    # ==========================================================
    # Se attivo, sostituisce il tasso fisso della sidebar con uno
    # scadenzario data→tasso (utile per mutui a tasso Euribor-indicizzato,
    # es. conteggi tipo BASSOTTI/Triple A).
    tasso_mora_calcolo = tasso_mora   # default: scalare dalla sidebar
    usa_tasso_variabile = False
    with st.expander("📈 Tasso di mora variabile nel tempo (opzionale)"):
        usa_tasso_variabile = st.checkbox(
            "Attiva scadenzario tassi di mora (sostituisce il tasso fisso "
            "della sidebar)",
            value=False,
            help="Per mutui a tasso variabile (Euribor + spread): inserisci "
                 "una riga per ogni variazione. Ogni tasso vale dalla sua "
                 "data 'Da' fino alla data 'Da' della riga successiva.",
        )
        if usa_tasso_variabile:
            st.caption(
                "Compila la tabella: **Da** = data di decorrenza del tasso, "
                "**Tasso mora (%)** = tasso annuo in quel periodo. "
                "Le righe vengono ordinate automaticamente per data."
            )
            default_sched = pd.DataFrame([
                {"Da": date(2022, 1, 1), "Tasso mora (%)": 6.45},
                {"Da": date(2023, 1, 1), "Tasso mora (%)": 8.66},
                {"Da": date(2024, 1, 1), "Tasso mora (%)": 10.36},
            ])
            sched_edit = st.data_editor(
                default_sched,
                num_rows="dynamic",
                width="stretch",
                column_config={
                    "Da": st.column_config.DateColumn(
                        "Da", format="DD/MM/YYYY", required=True
                    ),
                    "Tasso mora (%)": st.column_config.NumberColumn(
                        "Tasso mora (%)", min_value=0.0, max_value=30.0,
                        step=0.01, format="%.4f", required=True
                    ),
                },
                key="t1_scadenzario_mora",
            )
            # Costruisco lo scadenzario per il motore (tasso in decimale)
            scad = []
            for _, riga in sched_edit.iterrows():
                d = riga["Da"]
                tasso = riga["Tasso mora (%)"]
                if pd.isna(d) or pd.isna(tasso):
                    continue
                if hasattr(d, "date"):
                    d = d.date()
                scad.append({"da": d, "tasso": float(tasso) / 100.0})
            if scad:
                tasso_mora_calcolo = scad
                st.success(
                    f"✅ Scadenzario attivo con **{len(scad)} fasce** di tasso. "
                    "Verrà usato al posto del tasso fisso della sidebar."
                )
            else:
                st.warning(
                    "⚠️ Scadenzario vuoto o incompleto: verrà usato il tasso "
                    "fisso della sidebar."
                )

    # ==========================================================
    # 📐 PIANO DI AMMORTAMENTO (anti-anatocismo)
    # ==========================================================
    st.divider()
    st.markdown("### 📐 Piano di Ammortamento (anti-anatocismo)")
    modalita_piano = st.radio(
        "Come vuoi gestire il piano di ammortamento?",
        options=[
            "🚫 Non usare un piano (mora sull'intera rata)",
            "🧮 Ricostruzione algoritmica (alla francese)",
            "📤 Carica piano reale da file (CSV / Excel)",
        ],
        index=0,
        help=(
            "**Non usare:** mora calcolata sull'intero importo della rata "
            "(comportamento storico).\n\n"
            "**Ricostruzione algoritmica:** il software ricostruisce il "
            "piano alla francese dai parametri del mutuo (capitale, TAN, "
            "durata).\n\n"
            "**Carica da file:** il software legge il piano REALE della "
            "banca (CSV o Excel). Massima precisione: evita lievi "
            "differenze rispetto al piano teorico."
        ),
    )

    piano_ammortamento = None

    # ---------- MODO B: Ricostruzione algoritmica ----------
    if modalita_piano.startswith("🧮"):
        if "t1_data_erogazione" not in st.session_state:
            st.session_state["t1_data_erogazione"] = data_stipula
        m1, m2, m3 = st.columns(3)
        capitale_originario = m1.number_input(
            "💶 Capitale Originario Erogato (€)",
            min_value=0.0, value=200000.0, step=1000.0,
            help="Importo del mutuo come da contratto / atto notarile.",
            key="t1_capitale_originario",
        )
        data_erogazione = m2.date_input(
            "📅 Data di Erogazione (inizio mutuo)",
            format="DD/MM/YYYY",
            help="Di norma coincide con la Data di stipula. Modificare se "
                 "l'erogazione è avvenuta in data diversa.",
            key="t1_data_erogazione",
        )
        durata_anni = m3.number_input(
            "⏳ Durata del mutuo (anni)",
            min_value=1, max_value=50, value=20, step=1,
            key="t1_durata_anni",
        )
        m4, m5 = st.columns(2)
        tan = m4.number_input(
            "📊 TAN del mutuo (%)",
            min_value=0.0, max_value=20.0, value=4.50, step=0.05,
            help="Tasso Annuo Nominale del mutuo originario (diverso dal "
                 "tasso di mora). Sarà usato per calcolare la rata costante "
                 "e la ripartizione capitale/interessi rata per rata.",
            key="t1_tan",
        ) / 100
        freq_piano = m5.selectbox(
            "Frequenza rate (piano di ammortamento)",
            options=list(FREQUENZA_MESI.keys()), index=0,
            help="Di norma uguale alla 'Frequenza rate' del piano "
                 "originario. Modificare se diversa.",
            key="t1_freq_piano",
        )

        try:
            piano_ammortamento = genera_piano_ammortamento(
                capitale=capitale_originario, tan=tan,
                durata_mesi=int(durata_anni * 12),
                frequenza=freq_piano,
                data_erogazione=data_erogazione,
            )
            st.success(
                f"✅ Piano generato: **{len(piano_ammortamento)} rate**, "
                f"rata costante (escluso ultimo aggiustamento) di "
                f"**{fmt_eur(piano_ammortamento[0]['importo_rata'])}**. "
                f"Somma quote capitale = "
                f"{fmt_eur(sum(r['quota_capitale'] for r in piano_ammortamento))} "
                f"(= capitale erogato ✅)."
            )
        except Exception as e:
            st.error(f"⛔ Generazione piano fallita: {e}")
            piano_ammortamento = None

    # ---------- MODO C: Caricamento da file ----------
    elif modalita_piano.startswith("📤"):
        st.info(
            "📌 **Formati supportati:** PDF, CSV, Excel (.xlsx).\n\n"
            "- **PDF**: estrazione automatica delle tabelle. Funziona con "
            "PDF *vettoriali* generati dal gestionale della banca "
            "(la maggior parte). Non funziona con PDF *scansionati* "
            "(servirebbe OCR): in quel caso esporta in CSV/Excel.\n"
            "- **CSV / Excel**: lettura diretta, massima precisione.\n\n"
            "**Colonne attese** (case-insensitive, riconosce sinonimi "
            "comuni): `Data Scadenza`, `Quota Capitale`, `Quota Interessi`. "
            "Opzionali: `Capitale Residuo`, `Num Rata`."
        )
        file_piano = st.file_uploader(
            "📎 Carica il piano di ammortamento",
            type=["pdf", "csv", "xlsx", "xls"],
            help="Formato consigliato: PDF della banca o esportazione "
                 "CSV/Excel. Per i PDF scansionati esporta in CSV/Excel.",
        )
        if file_piano is not None:
            try:
                piano_ammortamento = carica_piano_da_file(file_piano)
                somma_qc = sum(r["quota_capitale"] for r in piano_ammortamento)
                st.success(
                    f"✅ Piano caricato dal file **{file_piano.name}**: "
                    f"**{len(piano_ammortamento)} rate**. "
                    f"Somma Quote Capitale = **{fmt_eur(somma_qc)}**."
                )
            except ValueError as e:
                st.error(f"⛔ {e}")
                piano_ammortamento = None
            except Exception as e:
                st.error(f"⛔ Errore imprevisto durante il caricamento: {e}")
                piano_ammortamento = None

    # ---------- Pannello comune: anteprima piano + rate insolute ----------
    if piano_ammortamento is not None:
        rate_insolute = estrai_rate_insolute_da_piano(
            piano_ammortamento, data_prima_rata, data_decadenza_effettiva,
        )
        if rate_insolute:
            st.caption(
                f"🔎 **{len(rate_insolute)} rate insolute** intercettate nel "
                f"periodo {data_prima_rata.strftime('%d/%m/%Y')} → "
                f"{data_decadenza_effettiva.strftime('%d/%m/%Y')}: dalla "
                f"rata #{rate_insolute[0]['num_rata']} alla "
                f"#{rate_insolute[-1]['num_rata']} del piano."
            )
        else:
            st.warning(
                "⚠️ Nessuna rata del piano cade nell'intervallo prima rata "
                "insoluta → decadenza. Verifica le date del mutuo e/o della "
                "prima rata insoluta."
            )

        with st.expander("📊 Visualizza Piano di Ammortamento"):
            ids_insolute = {ri["num_rata"] for ri in rate_insolute}
            df_piano = pd.DataFrame([
                {
                    "Num_Rata": r["num_rata"],
                    "Data_Scadenza": r["data_scadenza"].strftime("%d/%m/%Y"),
                    "Quota_Interessi": r["quota_interessi"],
                    "Quota_Capitale": r["quota_capitale"],
                    "Importo_Rata": r["importo_rata"],
                    "Capitale_Residuo": r["capitale_residuo"],
                    "Insoluta": "🔴" if r["num_rata"] in ids_insolute else "",
                }
                for r in piano_ammortamento
            ])
            st.dataframe(
                df_piano,
                width="stretch", hide_index=True,
                column_config={
                    "Quota_Interessi": st.column_config.NumberColumn(
                        "Quota Interessi (€)", format="%.2f"
                    ),
                    "Quota_Capitale": st.column_config.NumberColumn(
                        "Quota Capitale (€)", format="%.2f"
                    ),
                    "Importo_Rata": st.column_config.NumberColumn(
                        "Importo Rata (€)", format="%.2f"
                    ),
                    "Capitale_Residuo": st.column_config.NumberColumn(
                        "Capitale Residuo (€)", format="%.2f"
                    ),
                },
            )
            st.caption(
                "🔴 = rata insoluta intercettata (Fase 1). La mora verrà "
                "calcolata solo sulla Quota Capitale di queste rate."
            )

    st.divider()

    # Il bottone rivela i risultati; da lì in poi si ricalcolano ad ogni
    # interazione (reattivo) senza sparire. Il calcolo è ~0,2ms e il PDF
    # ~18ms, quindi nessun lag percepibile.
    if st.button("🧮 Calcola interessi di mora", type="primary"):
        st.session_state["mostra_risultati"] = True

    # --- Controlli di coerenza temporale (non bloccano gli altri tab) ---
    _dati_validi = True
    if st.session_state.get("mostra_risultati"):
        if data_decadenza_effettiva < data_prima_rata:
            st.error("⛔ La data di decadenza è precedente alla prima rata insoluta. "
                     "Verificare le date.")
            _dati_validi = False
        elif data_fine < data_decadenza_effettiva:
            st.error("⛔ La data finale di calcolo è precedente alla decadenza. "
                     "Verificare le date.")
            _dati_validi = False
        if data_pignoramento < data_decadenza_effettiva:
            st.warning("⚠️ Il pignoramento risulta precedente alla decadenza: "
                       "di norma è successivo. Verificare.")

    if st.session_state.get("mostra_risultati") and _dati_validi:

        etichetta = "CASO A (Lettera DBT)" if is_caso_A else "CASO B (Notifica Precetto)"
        st.subheader(f"Modalità: {etichetta}")
        st.caption(f"Data Decadenza Effettiva utilizzata: "
                   f"**{data_decadenza_effettiva.strftime('%d/%m/%Y')}**")

        # --- PARAMETRI COMUNI (condivisi da entrambi i giri) ---
        # tasso_mora_calcolo è lo scalare della sidebar oppure lo
        # scadenzario (se il tasso variabile è attivo).
        params_comuni = {
            "importo_rata": importo_rata,
            "data_prima_rata": data_prima_rata,
            "frequenza": frequenza,
            "capitale_residuo": capitale_residuo,
            "tasso_mora": tasso_mora_calcolo,
            "data_decadenza_effettiva": data_decadenza_effettiva,
            "data_pignoramento": data_pignoramento,
        }
        if usa_tasso_variabile and isinstance(tasso_mora_calcolo, list):
            st.caption(
                f"📈 **Tasso di mora variabile** attivo: "
                f"{len(tasso_mora_calcolo)} fasce di tasso "
                f"(dal {min(s['da'] for s in tasso_mora_calcolo).strftime('%d/%m/%Y')})."
            )

        # --- GIRO B (Calcolo Attuale): stima del debito a oggi / data_fine ---
        st.caption("⏳ **Giro B** — Debito attuale aggiornato alla data di fine "
                   "calcolo per orientamento negoziale.")
        risultato = calcola_mora_unificato(
            **params_comuni, data_fine=data_fine,
            piano_ammortamento=piano_ammortamento,
            metodo_triennio=metodo_triennio,
            anno_civile=anno_civile,
        )

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
                    **params_comuni, data_fine=data_attualizzazione_gbv,
                    piano_ammortamento=piano_ammortamento,
                    metodo_triennio=metodo_triennio,
                    anno_civile=anno_civile,
                )

        # --- Metriche totali generali (in card con bordo) ---
        totale_gen = risultato['ipotecario'] + risultato['chirografario']
        with st.container(border=True):
            col1, col2, col3 = st.columns(3)
            col1.metric("🏛️ Credito IPOTECARIO", f"{fmt_eur(risultato['ipotecario'])}")
            col2.metric("📄 Credito CHIROGRAFARIO", f"{fmt_eur(risultato['chirografario'])}")
            col3.metric("💰 TOTALE interessi di mora", f"{fmt_eur(totale_gen)}")

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

                fase1_info = det.get("FASE_1_rate", {})
                f1_usa_piano = fase1_info.get("usa_piano_ammortamento", False)
                f1_quote_int_messe_da_parte = fase1_info.get(
                    "quote_interessi_messe_da_parte", 0.0
                )

                if f1_usa_piano:
                    st.success(
                        "🛡️ **Calcolo anti-anatocismo attivo (art. 1283 c.c.).** "
                        "La mora di Fase 1 è calcolata **esclusivamente sulla "
                        "Quota Capitale** estratta dal piano di ammortamento "
                        "ricostruito. La Quota Interessi delle rate insolute "
                        f"(totale {fmt_eur(f1_quote_int_messe_da_parte)}) "
                        "è messa da parte: viene sommata al debito finale "
                        "senza produrre ulteriore mora."
                    )
                else:
                    st.info(
                        "ℹ️ **Perché questo importo può sembrare 'basso'?**\n\n"
                        "Le rate maturano interessi in modo **progressivo**: "
                        "la rata più vecchia accumula tutti i giorni di "
                        "ritardo, quella più recente solo pochi giorni. Il "
                        "software **non applica il tasso sull'intero monte "
                        "rate per tutto il periodo**: itera rata per rata e "
                        "somma i contributi (equivalente alla formula della "
                        "*giacenza media*)."
                    )

                # --- Tabella di scomposizione rata per rata ---
                rate_bk = fase1_info.get("rate_breakdown", [])
                if rate_bk:
                    titolo_exp = (
                        "📋 Scomposizione rata per rata "
                        "(quota capitale + giorni esatti di mora)"
                        if f1_usa_piano
                        else "📋 Scomposizione rata per rata "
                             "(giorni esatti di mora + interesse maturato)"
                    )
                    with st.expander(titolo_exp):
                        if f1_usa_piano:
                            righe = [
                                "| # piano | Data scadenza | Rata totale | "
                                "Quota interessi *(messa da parte)* | "
                                "Quota capitale *(base mora)* | "
                                "Giorni mora | Interesse maturato |",
                                "|---:|:---:|---:|---:|---:|---:|---:|",
                            ]
                            for br in rate_bk:
                                righe.append(
                                    f"| {br['num_rata_piano']} | "
                                    f"{br['data_scadenza'].strftime('%d/%m/%Y')} | "
                                    f"{fmt_eur(br['importo_rata_originale'])} | "
                                    f"{fmt_eur(br['quota_interessi'])} | "
                                    f"{fmt_eur(br['quota_capitale'])} | "
                                    f"{br['giorni_mora']} | "
                                    f"{fmt_eur(br['interesse_maturato'])} |"
                                )
                            somma_qc = sum(br["quota_capitale"] for br in rate_bk)
                            somma_qi = sum(br["quota_interessi"] for br in rate_bk)
                            somma_rate = sum(
                                br["importo_rata_originale"] for br in rate_bk
                            )
                            somma_gg = sum(br["giorni_mora"] for br in rate_bk)
                            somma_int = sum(
                                br["interesse_maturato"] for br in rate_bk
                            )
                            righe.append(
                                f"| **TOT** | — | "
                                f"**{fmt_eur(somma_rate)}** | "
                                f"**{fmt_eur(somma_qi)}** | "
                                f"**{fmt_eur(somma_qc)}** | "
                                f"**{somma_gg}** | "
                                f"**{fmt_eur(somma_int)}** |"
                            )
                            st.markdown("\n".join(righe))
                            st.caption(
                                "📌 **Nota:** al fine di evitare l'anatocismo, "
                                "gli interessi di mora sulle rate scadute "
                                "sono stati calcolati **esclusivamente sulla "
                                "Quota Capitale** delle stesse, ricavata "
                                "dal piano di ammortamento."
                            )
                        else:
                            righe = [
                                "| # | Data scadenza | Importo | "
                                "Giorni mora | Interesse maturato |",
                                "|---:|:---:|---:|---:|---:|",
                            ]
                            for br in rate_bk:
                                righe.append(
                                    f"| {br['i']} | "
                                    f"{br['data_scadenza'].strftime('%d/%m/%Y')} | "
                                    f"{fmt_eur(br['importo_rata_originale'])} | "
                                    f"{br['giorni_mora']} | "
                                    f"{fmt_eur(br['interesse_maturato'])} |"
                                )
                            somma_gg = sum(br["giorni_mora"] for br in rate_bk)
                            somma_int = sum(
                                br["interesse_maturato"] for br in rate_bk
                            )
                            righe.append(
                                f"| **TOTALE** | — | "
                                f"**{fmt_eur(base_rate_scadute)}** | "
                                f"**{somma_gg}** | "
                                f"**{fmt_eur(somma_int)}** |"
                            )
                            st.markdown("\n".join(righe))
                            gg_medi = somma_gg / len(rate_bk)
                            giacenza_media = (
                                base_rate_scadute * tasso_mora * gg_medi / 365
                            )
                            st.caption(
                                f"✅ **Verifica equivalente — giacenza media:** "
                                f"giorni medi di ritardo = "
                                f"**{gg_medi:.1f}** (~{gg_medi/30:.1f} mesi). "
                                f"Applicando la formula `Capitale totale × "
                                f"Tasso × Giorni medi / 365`: "
                                f"{fmt_eur(base_rate_scadute)} × "
                                f"{fmt_pct(tasso_mora)} × {gg_medi:.1f} / 365 "
                                f"= **{fmt_eur(giacenza_media)}** "
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

        # ---- Grafici brandizzati (dark): donut ipo/chiro + barra 4 voci ----
        # Palette scelta per risaltare sul fondo navy scuro:
        #  - IPOTECARIO → toni ORO   - CHIROGRAFARIO → toni AZZURRO
        _CREMA = "#ECE7DA"
        _ORO = "#C9A96A"          # oro (ipotecario)
        _ORO_CHIARO = "#E6D3A6"   # oro chiaro (ipotecario, 2ª voce)
        _BLU = "#6E8FC7"          # azzurro (chirografario)
        _BLU_CHIARO = "#9DB4DD"   # azzurro chiaro (chirografario, 2ª voce)

        g1, g2 = st.columns([1, 1.3])

        with g1:
            fig_donut = go.Figure(go.Pie(
                labels=["Ipotecario", "Chirografario"],
                values=[risultato["ipotecario"], risultato["chirografario"]],
                hole=0.62,
                marker=dict(colors=[_ORO, _BLU],
                            line=dict(color="#1A2744", width=2)),
                textinfo="percent",
                textfont=dict(size=15, color="#FFFFFF"),
                hovertemplate="%{label}: %{value:,.0f} €<extra></extra>",
                sort=False,
            ))
            fig_donut.update_layout(
                title=dict(text="Ipotecario vs Chirografario", font=dict(size=15)),
                separators=",.",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=_CREMA),
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=-0.15,
                            xanchor="center", x=0.5),
                height=300, margin=dict(l=10, r=10, t=45, b=10),
                annotations=[dict(
                    text=f"<b>{fmt_eur(totale_gen, 0)}</b>",
                    x=0.5, y=0.5, font=dict(size=15, color=_CREMA),
                    showarrow=False,
                )],
            )
            st.plotly_chart(fig_donut, width="stretch")

        with g2:
            fig_bar = go.Figure()
            _voci_bar = [
                ("Pre-triennio · chiro", v["pre_chiro"], _BLU_CHIARO),
                ("Triennio · ipo (mora)", v["triennio_ipo"], _ORO),
                ("Post · ipo (legale)", v["post_ipo"], _ORO_CHIARO),
                ("Post · chiro (eccedenza)", v["post_chiro"], _BLU),
            ]
            for nome, val, col in _voci_bar:
                fig_bar.add_trace(go.Bar(
                    y=["Composizione"], x=[val], name=nome, orientation="h",
                    marker=dict(color=col,
                                line=dict(color="#1A2744", width=1.5)),
                    hovertemplate=f"{nome}: %{{x:,.0f}} €<extra></extra>",
                ))
            fig_bar.update_layout(
                title=dict(text="Composizione delle 4 voci", font=dict(size=15)),
                barmode="stack",
                separators=",.",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=_CREMA),
                xaxis=dict(tickformat=",.0f", ticksuffix=" €", showgrid=False,
                           color=_CREMA),
                yaxis=dict(showticklabels=False),
                legend=dict(orientation="h", yanchor="bottom", y=-0.4,
                            xanchor="center", x=0.5, font=dict(size=11)),
                height=300, margin=dict(l=10, r=10, t=45, b=10),
            )
            st.plotly_chart(fig_bar, width="stretch")

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
            desc_triennio = (
                "Interessi maturati nell'**annata in corso al pignoramento "
                "più le 2 precedenti (anno solare)**"
                if metodo_triennio == METODO_TRIENNIO_SOLARE
                else "Interessi maturati nei **3 anni esatti che precedono "
                     "il pignoramento**"
            )
            st.success(
                "**🟢 FASE 2 – TRIENNIO**\n\n"
                f"{desc_triennio}: **garanzia ipotecaria piena** "
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

        # --- Confini del triennio (in base al metodo selezionato) ---
        inizio_triennio, fine_triennio = calcola_triennio(
            data_pignoramento, metodo_triennio, data_aggiudicazione=data_fine
        )
        gg_triennio = (fine_triennio - inizio_triennio).days

        # --- Fase 3 (post-triennio): dalla fine del triennio a data_fine ---
        gg_post = max((data_fine - fine_triennio).days, 0)

        # Spaccato anno per anno del tasso legale (calcolato sul capitale
        # residuo, contributo dominante della Fase 3).
        segmenti_legale = (
            det.get("FASE_2_capitale_residuo", {})
               .get("post_segmenti_legale", [])
        )

        with st.expander("🔍 Dettaglio calcoli Art. 2855 c.c."):
            st.markdown("## 📐 Matematica della Tripartizione ex Art. 2855 c.c.")

            if usa_tasso_variabile and isinstance(tasso_mora_calcolo, list):
                st.warning(
                    "📈 **Tasso di mora variabile attivo.** Nelle formule "
                    "seguenti compare il tasso della sidebar solo come "
                    "riferimento: il calcolo effettivo usa lo scadenzario "
                    "a fasce (i totali mostrati restano corretti)."
                )

            # --- Box didattico: perché il triennio inizia in quella data ---
            if metodo_triennio == METODO_TRIENNIO_SOLARE:
                spiegazione_metodo = (
                    f"Perché, con il metodo **Anno solare** (prassi dei "
                    f"conteggi professionali), il triennio garantito copre "
                    f"l'**annata in corso al pignoramento più le 2 precedenti**, "
                    f"con inizio al **1° gennaio** ({inizio_triennio.strftime('%d/%m/%Y')})."
                )
            else:
                spiegazione_metodo = (
                    f"Perché, con il metodo **3 anni esatti**, il triennio "
                    f"garantito copre **esattamente i 3 anni antecedenti alla "
                    f"data del pignoramento**."
                )
            st.info(
                f"**Perché il triennio ipotecario (Fase 2) inizia "
                f"il {inizio_triennio.strftime('%d/%m/%Y')} se la prima rata "
                f"insoluta è scaduta prima?**\n\n"
                f"{spiegazione_metodo}\n\n"
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

            if metodo_triennio == METODO_TRIENNIO_SOLARE:
                nota_inizio = "*(1° gennaio dell'annata in corso − 2 anni)*"
                nota_fine = "*(fine annata in corso, troncata all'aggiudicazione)*"
            else:
                nota_inizio = "*(data pignoramento − 3 anni esatti)*"
                nota_fine = "*(coincide con la data del pignoramento)*"

            st.markdown(f"""
            **Inizio triennio:** **{inizio_triennio.strftime('%d/%m/%Y')}**
            {nota_inizio}

            **Fine triennio:** **{fine_triennio.strftime('%d/%m/%Y')}**
            {nota_fine}

            **Giorni del triennio:** `{gg_triennio}` giorni

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
                "piano_ammortamento": piano_ammortamento,
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


def _render_sofferenza(ctx):
    """Modalità 'Sofferenza / Estratto conto ex art. 50 TUB'.

    Credito cristallizzato: replica i conteggi professionali (Triple A /
    doValue) e offre la variante 'da contestazione' (senza anatocismo).
    """
    pdf_password = ctx["pdf_password"]
    _NAVY, _ORO, _BLU, _CREMA = "#1A2744", "#C9A96A", "#6E8FC7", "#ECE7DA"

    st.subheader("🏦 Credito da Sofferenza / Estratto conto ex art. 50 TUB")
    st.caption(
        "Il credito è 'fotografato' dall'estratto conto (posizione a "
        "sofferenza): niente generazione di rate. Riproduce il metodo dei "
        "conteggi professionali e permette la versione da contestazione."
    )

    st.markdown("#### 💶 Voci cristallizzate (dall'estratto conto)")
    c1, c2 = st.columns(2)
    sorte = c1.number_input(
        "Sorte capitale (€)", min_value=0.0, value=95059.96, step=1000.0,
        help="Capitale puro residuo, epurato da interessi.")
    quota_int = c2.number_input(
        "Quota interessi rate insolute / rateo (€)", min_value=0.0,
        value=12163.06, step=100.0,
        help="Interessi contenuti nelle rate insolute, congelati alla "
             "sofferenza (voce chirografaria).")
    c3, c4 = st.columns(2)
    ante_soff = c3.number_input(
        "Interessi ante sofferenza (€)", min_value=0.0, value=1511.36,
        step=100.0, help="Interessi maturati prima della sofferenza "
        "(voce chirografaria congelata).")
    spese = c4.number_input(
        "Spese come da precetto (€)", min_value=0.0, value=1442.08,
        step=100.0, help="Grado ipotecario ex art. 2855 c.c.")

    st.markdown("#### 📅 Date")
    d1, d2 = st.columns(2)
    data_decorrenza = d1.date_input(
        "Decorrenza interessi", value=date(2021, 11, 1), format="DD/MM/YYYY",
        help="Inizio del calcolo interessi (di norma il giorno dopo la fine "
             "dell'estratto conto).")
    data_precetto = d2.date_input(
        "Data conteggio precetto (cambio tasso)", value=date(2025, 10, 4),
        format="DD/MM/YYYY",
        help="Fino a questa data si applica il tasso legale; da qui in poi "
             "il convenzionale.")
    d3, d4 = st.columns(2)
    data_pign = d3.date_input(
        "Data pignoramento", value=date(2026, 2, 2), format="DD/MM/YYYY",
        help="Determina l'annata del triennio (anno solare).")
    data_agg = d4.date_input(
        "Data aggiudicazione (fine conteggio)", value=date(2026, 12, 31),
        format="DD/MM/YYYY")

    st.markdown("#### 📊 Tassi e opzioni di calcolo")
    t1, t2 = st.columns(2)
    tasso_conv = t1.number_input(
        "Tasso convenzionale (%)", min_value=0.0, value=5.55, step=0.05,
        help="TAN del mutuo, applicato dal precetto in poi.") / 100
    tasso_mora_v = t2.number_input(
        "Tasso di mora (%)", min_value=0.0, value=7.55, step=0.05,
        help="TAN + spread. Usato solo se scegli la mora sul triennio.") / 100

    o1, o2 = st.columns(2)
    base_lbl = o1.radio(
        "Base degli interessi legali",
        options=["Capitale + interessi (prassi conteggi)",
                 "Solo capitale (contestazione, no anatocismo)"],
        index=0,
        help="I conteggi reali girano il legale su capitale + interessi "
             "scaduti (anatocismo). La versione 'solo capitale' è quella "
             "difendibile in opposizione.")
    base_legale = (BASE_CAPITALE_INTERESSI if base_lbl.startswith("Capitale +")
                   else BASE_SOLO_CAPITALE)

    tasso_tri_lbl = o2.radio(
        "Tasso del triennio (fino al precetto)",
        options=["Legale (come i conteggi reali)",
                 "Convenzionale", "Mora"],
        index=0,
        help="Nel triennio ex art. 2855 la norma consentirebbe il tasso "
             "pattuito; i conteggi reali usano il legale (prudente).")
    tasso_triennio = (TASSO_TRIENNIO_LEGALE if tasso_tri_lbl.startswith("Legale")
                      else (TASSO_TRIENNIO_CONVENZIONALE
                            if tasso_tri_lbl.startswith("Conv")
                            else TASSO_TRIENNIO_MORA))

    anno_civile = st.checkbox(
        "Anno civile (366 nei bisestili)", value=True,
        help="I conteggi reali usano l'anno civile (366 per il 2024). "
             "Togli la spunta per il divisore fisso 365.")

    st.divider()
    if st.button("🧮 Calcola credito", type="primary"):
        st.session_state["mostra_sofferenza"] = True

    if not st.session_state.get("mostra_sofferenza"):
        return

    if not (data_decorrenza < data_precetto <= data_agg):
        st.error("⛔ Verifica le date: devono essere decorrenza < precetto ≤ aggiudicazione.")
        return

    r = calcola_credito_sofferenza(
        sorte_capitale=sorte, quota_interessi_congelata=quota_int,
        interessi_ante_sofferenza=ante_soff, spese=spese,
        data_decorrenza=data_decorrenza, data_precetto=data_precetto,
        data_pignoramento=data_pign, data_aggiudicazione=data_agg,
        tasso_convenzionale=tasso_conv, tasso_mora=tasso_mora_v,
        base_legale=base_legale, tasso_triennio=tasso_triennio,
        anno_civile=anno_civile,
    )
    ipo, chiro = r["ipotecario"], r["chirografario"]

    with st.container(border=True):
        m1, m2, m3 = st.columns(3)
        m1.metric("🏛️ Credito IPOTECARIO", fmt_eur(ipo["totale"]))
        m2.metric("📄 Credito CHIROGRAFARIO", fmt_eur(chiro["totale"]))
        m3.metric("💰 TOTALE credito", fmt_eur(r["totale_credito"]))
    st.caption(f"Triennio (anno solare): dal **{r['inizio_triennio'].strftime('%d/%m/%Y')}** "
               f"(annata del pignoramento + 2 precedenti).")

    fig = go.Figure(go.Pie(
        labels=["Ipotecario", "Chirografario"],
        values=[ipo["totale"], chiro["totale"]], hole=0.62, sort=False,
        marker=dict(colors=[_ORO, _BLU], line=dict(color=_NAVY, width=2)),
        textinfo="percent", textfont=dict(color="#FFFFFF", size=15),
        hovertemplate="%{label}: %{value:,.0f} €<extra></extra>",
    ))
    fig.update_layout(
        separators=",.", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(color=_CREMA),
        height=280, margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"),
        annotations=[dict(text=f"<b>{fmt_eur(r['totale_credito'], 0)}</b>",
                          x=0.5, y=0.5, showarrow=False,
                          font=dict(size=14, color=_CREMA))],
    )
    st.plotly_chart(fig, width="stretch")

    with st.expander("🔍 Dettaglio delle voci", expanded=True):
        righe = ["| Voce | Grado | Importo |", "|:--|:--:|--:|"]
        righe.append(f"| Spese come da precetto | 🏛️ ipo | {fmt_eur(ipo['spese'])} |")
        righe.append(f"| Sorte capitale | 🏛️ ipo | {fmt_eur(ipo['sorte'])} |")
        for p in r["periodi"]:
            ico = "🏛️ ipo" if p["grado"] == "ipotecario" else "📄 chiro"
            righe.append(
                f"| {p['nome']} · {p['da'].strftime('%d/%m/%y')}→"
                f"{p['a'].strftime('%d/%m/%y')} ({p['tasso_desc']}) | {ico} "
                f"| {fmt_eur(p['importo'])} |")
        righe.append(f"| Quota interessi rate insolute (congelata) | 📄 chiro "
                     f"| {fmt_eur(chiro['quota_interessi_congelata'])} |")
        righe.append(f"| Interessi ante sofferenza (congelata) | 📄 chiro "
                     f"| {fmt_eur(chiro['interessi_ante_sofferenza'])} |")
        righe.append(f"| **TOTALE** | | **{fmt_eur(r['totale_credito'])}** |")
        st.markdown("\n".join(righe))

    ca = r["confronto_anatocismo"]
    if ca["extra"] > 0.01:
        st.warning(
            f"⚖️ **Punto di contestazione — anatocismo (art. 1283 c.c.):** "
            f"gli interessi legali sono calcolati sulla base "
            f"**capitale + interessi scaduti** ({fmt_eur(ca['legale_capitale_interessi'])}). "
            f"Sulla sola **quota capitale** sarebbero "
            f"{fmt_eur(ca['legale_solo_capitale'])}: differenza contestabile "
            f"di **{fmt_eur(ca['extra'])}**. Seleziona *'Solo capitale'* per "
            f"la versione da opposizione."
        )
    else:
        st.success(
            "✅ Base *solo capitale* attiva: nessun anatocismo sugli interessi "
            "legali (versione da contestazione)."
        )
