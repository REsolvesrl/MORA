import streamlit as st
from datetime import date
import plotly.graph_objects as go

from calcoli import (
    TASSI_LEGALI,
    TASSO_LEGALE_DEFAULT,
    FREQUENZA_MESI,
    SPESE_IMMOBILIARE,
    SPESE_MOBILIARE,
    COSTI_ACQUISIZIONE,
    calcola_triennio,
    calcola_mora_unificato,
)

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
    data_fine = st.date_input("Data fine calcolo (Attualizzazione desiderata)", value=date.today(),
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
                 "'alla pari', evitando falsi allarmi di anatocismo."
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
            "data_stipula": data_stipula,
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
        col1.metric("🏛️ Credito IPOTECARIO", f"€ {risultato['ipotecario']:,.2f}")
        col2.metric("📄 Credito CHIROGRAFARIO", f"€ {risultato['chirografario']:,.2f}")

        totale_gen = risultato['ipotecario'] + risultato['chirografario']
        st.metric("💰 TOTALE interessi di mora", f"€ {totale_gen:,.2f}")

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
                    f"- **Fase 1:** Mora calcolata rata per rata, "
                    f"dalla scadenza di ciascuna rata fino alla **decadenza** "
                    f"({data_decadenza_effettiva.strftime('%d/%m/%Y')}).\n"
                    f"- **N° rate scadute:** {n_rate}\n"
                    f"- **Quota capitale rate scadute:** "
                    f"€ {base_rate_scadute:,.2f}\n"
                    f"- **Tasso di mora:** {tasso_mora*100:.2f}% (pattuito)\n"
                    f"- **Convenzione giorni:** /365\n"
                    f"- **Interessi rate scadute → 🅰️ = € {fase1_interessi:,.2f}**"
                )
                with st.expander("📋 Dettaglio rata per rata"):
                    for chiave_rata, dettaglio_rata in fase1_rate_dict.items():
                        ipot_r, chiro_r = _voci_rata(dettaglio_rata)
                        tot_r = ipot_r + chiro_r
                        st.markdown(
                            f"- **{chiave_rata}:** "
                            f"ipotecario € {ipot_r:,.2f} + "
                            f"chirografario € {chiro_r:,.2f}"
                            f" (totale € {tot_r:,.2f})"
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
                    f"fino a oggi ({data_fine.strftime('%d/%m/%Y')}).\n"
                    f"- **Capitale residuo:** € {capitale_residuo:,.2f}\n"
                    f"- **Tasso di mora:** {tasso_mora*100:.2f}% (pattuito)\n"
                    f"- **Giorni (decadenza → oggi):** {gg_fase2}\n"
                    f"- **Convenzione giorni:** /365\n"
                    f"- **Interessi capitale residuo → 🅱️ = € {fase2_interessi:,.2f}**"
                )

            st.divider()
            st.markdown(
                f"### ✅ Verifica quadratura\n\n"
                f"🅰️ Interessi rate scadute   **€ {fase1_interessi:,.2f}**\n"
                f"🅱️ Interessi capitale residuo **€ {fase2_interessi:,.2f}**\n"
                f"─────────────────────────────────\n"
                f"💰 TOTALE interessi di mora   **€ {totale_gen:,.2f}**"
            )
            scarto_f = abs(fase1_interessi + fase2_interessi - totale_gen)
            if scarto_f > 0.01:
                st.error(f"⚠️ Scarto di quadratura: € {scarto_f:,.2f}")
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
            st.caption(
                "Il GBV dichiarato viene paragonato al "
                "nostro calcolo congelato alla **stessa data di attualizzazione** "
                f"(**{data_attualizzazione_gbv.strftime('%d/%m/%Y')}**), non a oggi."
            )
            interessi_totali = risultato_gbv["ipotecario"] + risultato_gbv["chirografario"]
            capitale_totale = capitale_residuo
            totale_calcolato = capitale_totale + interessi_totali + spese_legali

            a1, a2, a3 = st.columns(3)
            a1.metric("🏦 Quota capitale residua mutuo", f"€ {capitale_totale:,.2f}")
            a2.metric("⚖️ Spese legali sostenute", f"€ {spese_legali:,.2f}")
            a3.metric("📈 Interessi reali (calcolati dal software) rispetto all'ultima data di attualizzazione GBV", f"€ {interessi_totali:,.2f}")

            b1, b2, b3 = st.columns(3)
            b1.metric("🧮 TOTALE CALCOLATO (Capitale + Interessi + Spese Legali)", f"€ {totale_calcolato:,.2f}")
            b2.metric("📑 GBV DICHIARATO + Spese Legali", f"€ {(gbv_dichiarato + spese_legali):,.2f}")

            delta = (gbv_dichiarato + spese_legali) - totale_calcolato
            b3.metric("📐 DELTA", f"€ {delta:,.2f}", delta_color="inverse")

            SOGLIA = 10.0
            if delta > SOGLIA:
                st.error(
                    f"🚨 **Anomalia:** il GBV dichiarato supera il totale calcolato "
                    f"di € {delta:,.2f}. Possibile **anatocismo**, **estensione "
                    f"ipotecaria indebita**, **tassi di mora non dovuti** o **spese "
                    f"non documentate**. Verificare le voci in contestazione."
                )
            elif delta < -SOGLIA:
                st.warning(
                    f"ℹ️ Il totale calcolato supera il GBV dichiarato di "
                    f"€ {abs(delta):,.2f}. Pretesa creditoria prudenziale "
                    f"(a favore del debitore). Verificare comunque i dati."
                )
            else:
                st.success(
                    f"✅ **GBV congruo:** importi allineati "
                    f"(scarto € {abs(delta):,.2f} entro la soglia di € {SOGLIA:,.2f})."
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
                "Interessi anteriori al triennio: **degradano interamente a "
                "chirografario**, pur restando al tasso di mora.\n\n"
                f"📄 Chirografario (mora):\n\n"
                f"### € {v['pre_chiro']:,.2f}"
            )

        with fase2:
            st.success(
                "**🟢 FASE 2 – TRIENNIO**\n"
                "Annata in corso + 2 precedenti: **garanzia ipotecaria piena** "
                "al tasso di mora pattuito.\n\n"
                f"🏛️ Ipotecario (mora):\n\n"
                f"### € {v['triennio_ipo']:,.2f}"
            )

        with fase3:
            st.warning(
                "**🟠 FASE 3 – POST-TRIENNIO**\n\n"
                "Dopo l'annata del pignoramento la garanzia **degrada**: "
                "resta ipotecaria solo la quota al **tasso legale**, "
                "l'eccedenza diventa chirografaria.\n\n"
                f"🏛️ Ipotecario (legale): **€ {v['post_ipo']:,.2f}**\n\n"
                f"📄 Chirografario (eccedenza): **€ {v['post_chiro']:,.2f}**"
            )

        somma_voci = v['pre_chiro'] + v['triennio_ipo'] + v['post_ipo'] + v['post_chiro']
        scarto = abs(somma_voci - totale_gen)
        if scarto > 0.01:
            st.error(f"⚠️ Scarto di quadratura: € {scarto:,.2f} — verificare la logica.")
        else:
            st.caption("✅ Quadratura verificata: la somma delle 3 fasi coincide col totale.")


        # ==========================================================
        # 📋 DETTAGLIO CALCOLI ART. 2855 c.c. (TRASPARENZA)
        # ==========================================================
        det = risultato["dettaglio"]
        v = risultato["voci_2855"]

        # --- Ricostruzione parametri esatti di ciascuna fase ---
        inizio_triennio, _, fine_annata_pign = calcola_triennio(
            data_stipula, data_pignoramento
        )

        # ---------- FASE 2 (Triennio) ----------
        gg_triennio = (fine_annata_pign - inizio_triennio).days  # durata esatta triennio

        # ---------- FASE 3 (Post-Triennio) ----------
        gg_post = (data_fine - fine_annata_pign).days
        if gg_post < 0:
            gg_post = 0
        tasso_legale_attuale = TASSI_LEGALI.get(data_fine.year, TASSO_LEGALE_DEFAULT)
        post_ipo = v["post_ipo"]
        post_chiro = v["post_chiro"]

        with st.expander("🔍 Dettaglio calcoli Art. 2855 c.c."):
            st.markdown("## 📐 Matematica della Tripartizione ex Art. 2855 c.c.")

            # --- Quadratura ---
            somma_voci = v["pre_chiro"] + v["triennio_ipo"] + v["post_ipo"] + v["post_chiro"]
            quadratura_ok = abs(somma_voci - totale_gen) <= 0.01

            st.markdown(f"""
            **Dati di contesto**
            - Mutuo stipulato il: **{data_stipula.strftime('%d/%m/%Y')}**
            - Pignoramento il: **{data_pignoramento.strftime('%d/%m/%Y')}**
            - Data fine calcolo: **{data_fine.strftime('%d/%m/%Y')}**
            - Capitale residuo: **€ {capitale_residuo:,.2f}**
            - Tasso di mora pattuito: **{(tasso_mora*100):.2f}%**
            - Divisore giorni: **365** (anno civile)
            - Tasso legale anno {data_fine.year}: **{(tasso_legale_attuale*100):.2f}%**

            ---
            """)

            st.markdown("### 🔵 FASE 1 — PRE-TRIENNIO (Chirografario)")

            st.markdown(f"""
            **Periodo:** data prima rata scaduta → **{inizio_triennio.strftime('%d/%m/%Y')}** (inizio triennio)

            **Capitale di riferimento:** singola rata insoluta (importo: **€ {importo_rata:,.2f}**)

            **Tasso applicato:** {(tasso_mora*100):.2f}% (tasso di mora pattuito)

            **Formula:**  
            `Capitale × Tasso × Giorni / 365`

            Poiché gli interessi anteriori al triennio **degradano a chirografario**, la loro quota
            viene separata e mostrata come **chirografario pre-triennio**.

            **Risultato FASE 1:**  
            🅰️ Quota chirografaria calcolata su tutte le rate insolute: **€ {v['pre_chiro']:,.2f}**
            """)

            st.markdown("---")
            st.markdown("### 🟢 FASE 2 — TRIENNIO (Ipotecario)")

            st.markdown(f"""
            **Inizio triennio:** **{inizio_triennio.strftime('%d/%m/%Y')}**  
            *(annata pignoramento – 2 anni: decorrendo dal giorno/mese di stipula)*

            **Fine triennio / Annata pignoramento:** **{fine_annata_pign.strftime('%d/%m/%Y')}**  
            *(annata in corso al pignoramento)*

            **Giorni del triennio:** `{gg_triennio}` giorni (durata esatta 3 annate)

            **Capitale di riferimento:**
            - Per le **rate scadute**: singola rata insoluta (**€ {importo_rata:,.2f}**)
            - Per il **capitale residuo**: **€ {capitale_residuo:,.2f}**

            **Tasso applicato:** {(tasso_mora*100):.2f}% (tasso di mora pattuito — pieno)

            **Formula:**  
            `Capitale × {(tasso_mora*100):.2f}% × {gg_triennio} / 365`

            **Risultato FASE 2:**  
            🅱️ Quota ipotecaria (mora piena sul triennio): **€ {v['triennio_ipo']:,.2f}**
            """)

            st.markdown("---")
            st.markdown("### 🟠 FASE 3 — POST-TRIENNIO (Ipotecario al legale + Chirografario eccedenza)")

            st.markdown(f"""
            **Periodo:** **{fine_annata_pign.strftime('%d/%m/%Y')}** (fine annata pignoramento) → **{data_fine.strftime('%d/%m/%Y')}**

            **Giorni fase 3:** `{gg_post}` giorni

            Dopo l'annata del pignoramento la garanzia ipotecaria **degrada**: la legge (art. 2855 c.c.)
            riconosce la sola quota al **tasso legale** come ipotecaria; l'eccedenza (differenza tra
            mora pattuita e tasso legale) diventa chirografaria.

            **Quota A — Ipotecaria (tasso legale pro-rata):**

            `Capitale × {(tasso_legale_attuale*100):.2f}% × {gg_post} / 365`

            | Voce | Importo |
            |------|--------:|
            | Quota ipotecaria (legale) | **€ {post_ipo:,.2f}** |

            **Quota B — Chirografaria (eccedenza mora – legale):**

            `Capitale × [{(tasso_mora*100):.2f}% − {(tasso_legale_attuale*100):.2f}%] × {gg_post} / 365`

            = `Capitale × {(tasso_mora - tasso_legale_attuale)*100:.2f}% × {gg_post} / 365`

            | Voce | Importo |
            |------|--------:|
            | Quota chirografaria (eccedenza) | **€ {post_chiro:,.2f}** |
            """)

            st.markdown("---")
            st.markdown("### ✅ Quadratura")

            st.markdown(f"""
            | Fase | Voci | Importo |
            |:-----|:-----|--------:|
            | 🔵 Pre-triennio | Chirografario | € {v['pre_chiro']:,.2f} |
            | 🟢 Triennio | Ipotecario (mora) | € {v['triennio_ipo']:,.2f} |
            | 🟠 Post-triennio | Ipotecario (legale) | € {v['post_ipo']:,.2f} |
            | 🟠 Post-triennio | Chirografario (eccedenza) | € {v['post_chiro']:,.2f} |
            | **TOTALE INTERESSI** | | **€ {somma_voci:,.2f}** |

            | Controllo | |
            |:----------|-|
            | Totale interessi da calcolo | € {totale_gen:,.2f} |
            | Somma 4 voci art. 2855 | € {somma_voci:,.2f} |
            | Scarto | € {abs(somma_voci - totale_gen):,.2f} |
            | {"✅ Quadratura OK" if quadratura_ok else "⚠️ Verificare"} | |
            """)

        n_rate = risultato["dettaglio"]["FASE_1_rate"]["numero_rate_generate"]
        st.info(f"🔢 Rate insolute auto-generate (prima rata → decadenza): **{n_rate}**")

        with st.expander("🔍 Dettaglio calcolo (dati grezzi)"):
            st.json(risultato['dettaglio'])

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
            help=f"Forfait: € {custode_forfait:,.2f} | 3% del valore: "
                 f"€ {custode_pct:,.2f} | Default: € {custode_default:,.2f}"
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

    st.divider()
    st.metric("💸 TOTALE SPESE ESECUTIVE STIMATE", f"€ {totale_spese:,.2f}")

    st.info(
        f"⚠️ **Attenzione:** proseguendo con la procedura, il debito aumenterà di "
        f"circa **€ {totale_spese:,.2f}**, riducendo il ricavato netto della vendita. "
        f"Questi costi sono in **prededuzione** (art. 2770 c.c.) e vengono soddisfatti "
        f"con priorità sul ricavato, prima ancora del creditore ipotecario."
    )

    if tipo_procedura == "Pignoramento Immobiliare" and valore_bene > 0:
        incidenza = (totale_spese / valore_bene) * 100
        st.caption(f"📉 Incidenza delle spese sul valore del bene: **{incidenza:.1f}%**")

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
    r1.metric("🏦 GBV Partenza", f"€ {gbv_base:,.2f}", help=f"Fonte: {fonte_gbv}")
    r2.metric("💸 Spese Procedura (Tab 2)", f"€ {spese_procedura:,.2f}")
    r3.metric("📐 Debito Reale Calcolato", f"€ {debito:,.2f}",
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

    st.caption(f"💼 Costi Acquisizione: **€ {costi_acquisizione:,.2f}** | "
               f"📋 Totale Spese Fisse (procedura + acquisizione): **€ {totale_spese_fisse:,.2f}**")

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
    w1.metric("🏦 GBV Partenza", f"€ {gbv_base:,.2f}")
    w2.metric("− Totale Spese Fisse", f"€ {totale_spese_fisse:,.2f}",
              help="Spese procedura + costi di acquisizione (sopra)")
    w3.metric("= Base Netta pre-sconto", f"€ {base_netta:,.2f}")
    w4.metric("− Sconto trattativa (%)", f"{margine*100:.0f}%")

    st.divider()

    delta_pct_gbv = ((offerta_target / gbv_base) * 100) if gbv_base > 0 else 0
    st.metric(
        "🎯 OFFERTA TARGET (Servicer)",
        f"€ {offerta_target:,.2f}",
        delta=f"{delta_pct_gbv:.1f}% del GBV",
        delta_color="normal"
    )

    # --- Messaggi di stato ---
    if offerta_target <= 0:
        st.error(
            f"🚨 **Offerta target negativa o nulla (€ {offerta_target:,.2f}).** "
            f"Le spese fisse (€ {totale_spese_fisse:,.2f}) superano o eguagliano il GBV "
            f"(€ {gbv_base:,.2f}). L'operazione NPL **non è sostenibile** con questi "
            f"parametri. Rivedere: (a) soglia di ribasso, (b) costi di acquisizione, "
            f"(c) stima del GBV."
        )
    elif offerta_target >= gbv_base:
        st.warning(
            f"⚠️ **Offerta target >= GBV (€ {offerta_target:,.2f}).** "
            f"Questo scenario è **non realistico**: nessun investitore NPL "
            f"acquista un credito senza sconto. Verificare le spese fisse "
            f"o ricalcolare il GBV."
        )
    else:
        st.success(
            f"✅ **Operazione sostenibile.** Offerta target: "
            f"**€ {offerta_target:,.2f}** ({(1-margine)*100:.0f}% del GBV, "
            f"margine investitore: {margine*100:.0f}%). "
            f"Base netta disponibile: € {base_netta:,.2f}."
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
    cu1.metric("💶 Utile Lordo (su GBV)", f"€ {utile_lordo:,.2f}",
               help="Base Netta − Offerta Target = margine generato sul GBV dichiarato.")
    cu2.metric("➕ Utile da Interessi Maturati", f"€ {utile_interessi_maturati:,.2f}",
               help="Debito Reale Calcolato (Tab 1, a oggi) − GBV di partenza. "
                    "Valore nominale: il debito reale è già attualizzato a oggi, "
                    "quindi non si riattualizza. Può essere negativo se il GBV "
                    "dichiarato supera il debito ricostruito.")
    cu3.metric("= Utile Totale", f"€ {utile_totale:,.2f}")

    if utile_interessi_maturati < 0:
        st.warning(
            f"⚠️ **Delta interessi negativo (€ {utile_interessi_maturati:,.2f}).** "
            f"Il GBV di partenza (€ {gbv_base:,.2f}) supera il Debito Reale "
            f"Calcolato (€ {debito:,.2f}). Verificare la pretesa della cedente "
            f"o la data di attualizzazione del Tab 1. Il valore è comunque "
            f"computato per intero (riduce l'Utile Totale)."
        )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🎯 Offerta Target", f"€ {offerta_target:,.2f}")
    m2.metric("💶 Utile Totale", f"€ {utile_totale:,.2f}",
              help="Utile Lordo + Utile da Interessi Maturati")
    m3.metric("📊 ROE", f"{roe*100:.2f}%",
              help="Return on Equity = Utile Totale / Capitale Investito Totale")
    m4.metric("📈 IRR Annualizzato", f"{irr_annuale*100:.2f}%",
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
            "Offerta: € %{x:,.0f}<br>"
            "Utile Lordo: € %{y:,.0f}<br>"
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
            "Offerta: € %{x:,.0f}<br>"
            "Utile: € %{y:,.0f}<br>"
            f"ROE: {roe*100:.2f}%<extra></extra>"
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
              f"€ {offerta_target:,.0f}<br>"
              f"<b>ROE Atteso: {roe*100:.2f}%</b>"),
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
        xaxis=dict(tickformat=",.0f", tickprefix="€ "),
        yaxis=dict(tickformat=",.0f", tickprefix="€ "),
        hovermode="closest",
        template="plotly_white",
        height=480,
        margin=dict(l=20, r=20, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
    )

    st.plotly_chart(fig, use_container_width=True)
