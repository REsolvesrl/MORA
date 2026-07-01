import os
import streamlit as st
from datetime import date

from autofill import estrai_testo_da_pdf, extract_data_from_legal_text
from ui_common import mappa_autofill_a_widget, ETICHETTE_CAMPI
import tab_auditing
import tab_spese
import tab_npl

from calcoli import (
    METODO_TRIENNIO_ESATTO,
    METODO_TRIENNIO_SOLARE,
)

# --- Applica autofill_pending PRIMA che i widget siano renderizzati ---
# (deve girare nel main, prima che la sidebar e i tab creino i widget)
if "autofill_pending" in st.session_state:
    dati_da_applicare = st.session_state.pop("autofill_pending")
    campi_compilati = []
    for widget_key, valore in dati_da_applicare.items():
        st.session_state[widget_key] = valore
        campi_compilati.append(ETICHETTE_CAMPI.get(widget_key, widget_key))
    st.session_state["autofill_ultimi_campi"] = campi_compilati


# ==========================================================
# 7. INTERFACCIA STREAMLIT
# ==========================================================

# --- Asset di branding (guardia: se manca il file, si prosegue senza) ---
LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo_resolve.png")
_ha_logo = os.path.exists(LOGO_PATH)

st.set_page_config(
    page_title="Resolve — Interessi di Mora ex art. 2855 c.c.",
    page_icon=LOGO_PATH if _ha_logo else "⚖️",
    layout="wide",
)

# Logo Resolve in alto nella sidebar (nativo Streamlit)
if _ha_logo:
    st.logo(LOGO_PATH, icon_image=LOGO_PATH, size="large")

# ---- Palette di brand (dark navy + oro dal logo Resolve) ----
NAVY = "#1A2744"
NAVY_CARD = "#243459"
ORO = "#C9A96A"
ORO_SCURO = "#B08F4F"
CREMA = "#ECE7DA"

# ---- Stile dark: tab, titoli serif, accenti oro ----
st.markdown(f"""
    <style>
    /* Logo più grande in cima alla sidebar */
    img[data-testid="stLogo"] {{
        height: 4.2rem;
        max-height: 4.2rem;
    }}
    /* Titoli in serif per echeggiare il wordmark REsolve */
    h1, h2, h3 {{
        font-family: Georgia, 'Times New Roman', serif !important;
        color: {CREMA};
        letter-spacing: 0.2px;
    }}
    /* Tab più grandi con scheda attiva in oro */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 12px;
    }}
    .stTabs [data-baseweb="tab"] {{
        height: 55px;
        padding: 0px 28px;
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(201, 169, 106, 0.30);
        border-radius: 10px 10px 0px 0px;
        font-size: 18px;
        font-weight: 600;
        color: inherit;
    }}
    .stTabs [data-baseweb="tab"]:hover {{
        background-color: rgba(201, 169, 106, 0.20);
        color: inherit;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: {ORO};
        color: {NAVY} !important;
        border: 1px solid {ORO};
    }}
    /* Bottoni primari / download in oro con testo navy */
    .stButton > button[kind="primary"], .stDownloadButton > button {{
        background-color: {ORO};
        border: 1px solid {ORO};
        color: {NAVY};
        font-weight: 600;
    }}
    .stButton > button[kind="primary"]:hover, .stDownloadButton > button:hover {{
        background-color: {ORO_SCURO};
        border-color: {ORO_SCURO};
        color: {NAVY};
    }}
    </style>
""", unsafe_allow_html=True)

st.title("Interessi di Mora — Ipotecario / Chirografario")
st.caption("Strumento di supporto Resolve S.r.l. · Verificare sempre i risultati. "
           "Interesse semplice (art. 1283 c.c.).")

# ---- Sidebar: parametri comuni ----
with st.sidebar:

    # Logo Resolve grande in cima alla sidebar (controllo pieno sulla dimensione)
    if _ha_logo:
        st.image(LOGO_PATH, width="stretch")

    # ==========================================================
    # ✨ MAGIC AUTOFILL — Estrazione automatica dai PDF legali
    # ==========================================================
    with st.expander("✨ Magic Autofill (Precetto / Mutuo / DBT)", expanded=False):
        st.caption(
            "Carica i documenti in PDF: il software estrarrà "
            "automaticamente **capitale**, **tassi**, **date** e li "
            "userà come default nei campi qui sotto.\n\n"
            "✅ Supporta anche **PDF scansionati** tramite OCR (Tesseract). "
            "L'OCR è più lento (15-60 sec per PDF): abbi pazienza."
        )
        pdf_docs = st.file_uploader(
            "Carica Documenti (Precetto, Mutuo, DBT) per Autocompilazione",
            type=["pdf"],
            accept_multiple_files=True,
            key="autofill_uploader",
        )
        # Info privacy sul metodo di estrazione
        has_llm_key = False
        try:
            has_llm_key = "ANTHROPIC_API_KEY" in st.secrets
        except Exception:
            pass
        if not has_llm_key:
            import os as _os
            has_llm_key = bool(_os.environ.get("ANTHROPIC_API_KEY"))
        if has_llm_key:
            st.caption(
                "🤖 Modalità **LLM Anthropic (Claude Haiku)** attiva. "
                "⚠️ Il testo dei PDF verrà inviato ai server Anthropic per "
                "l'estrazione. Non caricare dati che non vuoi condividere."
            )
        else:
            st.caption(
                "🔧 Modalità **regex fallback** (nessuna API key configurata). "
                "Precisione ridotta: funziona su documenti con formulazioni "
                "standard. Per massima precisione configura "
                "`ANTHROPIC_API_KEY` in Streamlit secrets."
            )

        if st.button("🔍 Analizza e Compila", disabled=not pdf_docs):
            testi = []
            metodi_usati = {}   # nome_file -> metodo
            with st.status("Elaboro i PDF...", expanded=True) as status:
                for f in pdf_docs:
                    st.write(f"📄 {f.name}: leggo con pdfplumber...")
                    try:
                        t, metodo = estrai_testo_da_pdf(f, ocr_fallback=True)
                        metodi_usati[f.name] = metodo
                        if metodo == "ocr":
                            st.write(
                                f"   ↳ PDF scansionato: passo all'**OCR** "
                                f"(può richiedere 15-60 sec)."
                            )
                        elif metodo == "vettoriale":
                            st.write(f"   ↳ ✅ Testo estratto ({len(t)} caratteri).")
                        elif metodo == "errore_ocr":
                            st.write(
                                f"   ↳ ⚠️ OCR non disponibile o fallito: "
                                f"{t[:200]}"
                            )
                            t = ""
                        else:
                            st.write("   ↳ ⚠️ Nessun testo estratto.")
                        if t and t.strip():
                            testi.append(f"### DOCUMENTO: {f.name}\n{t}")
                    except Exception as e:
                        st.write(f"   ↳ ⛔ Errore lettura: {e}")
                        metodi_usati[f.name] = "errore"
                status.update(label="Lettura PDF completata", state="complete")
            testo_completo = "\n\n".join(testi)

            if not testo_completo.strip():
                if any(m == "errore_ocr" for m in metodi_usati.values()):
                    st.error(
                        "⛔ **OCR non disponibile**. I PDF sono scansionati "
                        "e servirebbe Tesseract per leggerli. Su Streamlit "
                        "Cloud verifica che `packages.txt` contenga: "
                        "`tesseract-ocr`, `tesseract-ocr-ita`, "
                        "`poppler-utils`, e riavvia l'app."
                    )
                else:
                    st.error(
                        "⛔ Nessun testo estratto dai PDF forniti."
                    )
            else:
                with st.spinner("Estraggo i dati con l'AI..."):
                    try:
                        secrets_obj = None
                        try:
                            secrets_obj = st.secrets
                        except Exception:
                            pass
                        dati_estratti, modalita = extract_data_from_legal_text(
                            testo_completo, streamlit_secrets=secrets_obj,
                        )
                    except Exception as e:
                        st.error(f"⛔ Estrazione fallita: {e}")
                        dati_estratti, modalita = {}, "errore"

                if dati_estratti:
                    widget_updates = mappa_autofill_a_widget(dati_estratti)
                    non_trovati = [
                        k for k, v in dati_estratti.items() if v is None
                    ]
                    if widget_updates:
                        st.session_state["autofill_pending"] = widget_updates
                        st.success(
                            f"✅ **{len(widget_updates)} campi** compilati "
                            f"(modalità: `{modalita}`). Aggiorno l'interfaccia…"
                        )
                        st.toast(
                            f"Autofill: {len(widget_updates)} campi "
                            "compilati",
                            icon="✨",
                        )
                        st.rerun()
                    else:
                        st.warning(
                            "⚠️ Nessun campo estraibile dai documenti. "
                            "Compila manualmente."
                        )

    # --- Feedback post-autofill ---
    if "autofill_ultimi_campi" in st.session_state:
        campi = st.session_state.pop("autofill_ultimi_campi")
        st.success(
            "🎯 **Campi compilati automaticamente:**\n\n"
            + "\n".join(f"- {c}" for c in campi)
            + "\n\nVerifica i valori e correggi manualmente se necessario."
        )

    st.header("Parametri generali")
    tasso_mora = st.number_input(
        "Tasso di mora (%)", min_value=0.0, value=8.0, step=0.1,
        key="sb_tasso_mora",
    ) / 100

    st.divider()
    st.subheader("Date comuni")
    data_stipula = st.date_input(
        "Data stipula mutuo",
        value=date(2018, 6, 15),
        min_value=date(2000, 1, 1),
        format="DD/MM/YYYY",
        key="sb_data_stipula",
    )
    data_pignoramento = st.date_input(
        "Data pignoramento", value=date(2023, 9, 10),
        format="DD/MM/YYYY",
        key="sb_data_pignoramento",
    )
    data_fine = st.date_input(
        "Data di aggiudicazione (attualizzazione desiderata)",
        value=date.today(), format="DD/MM/YYYY",
        key="sb_data_fine",
    )

    st.divider()
    st.subheader("Evento di decadenza")
    caso = st.radio(
        "Quale atto ha generato la decadenza dal beneficio del termine?",
        options=["CASO A – Lettera DBT", "CASO B – Notifica Precetto"],
        index=0,
        key="sb_caso",
    )
    is_caso_A = caso.startswith("CASO A")

    st.divider()
    st.subheader("Metodo del triennio (Art. 2855 c.c.)")
    metodo_label = st.radio(
        "Come si delimita il triennio garantito?",
        options=[
            "Anno solare (prassi conteggi reali)",
            "3 anni esatti a ritroso",
        ],
        index=0,
        key="sb_metodo_triennio",
        help=(
            "**Anno solare:** il triennio copre l'annata (anno solare) in "
            "corso al pignoramento più le 2 precedenti, con inizio al 1° "
            "gennaio. È il criterio usato dai conteggi professionali reali "
            "(doValue, Triple A, ecc.).\n\n"
            "**3 anni esatti:** il triennio copre esattamente i 3 anni "
            "(1095/1096 giorni) che precedono la data del pignoramento."
        ),
    )
    metodo_triennio = (
        METODO_TRIENNIO_SOLARE
        if metodo_label.startswith("Anno solare")
        else METODO_TRIENNIO_ESATTO
    )

    st.divider()
    st.subheader("Base di calcolo giorni")
    base_giorni_label = st.radio(
        "Divisore per il calcolo degli interessi",
        options=[
            "Anno civile (365 / 366 bisestili)",
            "Anno commerciale (365 fisso)",
        ],
        index=0,
        key="sb_base_giorni",
        help=(
            "**Anno civile:** ogni segmento è diviso per i giorni effettivi "
            "dell'anno (366 nei bisestili come il 2024). È la convenzione dei "
            "conteggi professionali reali (doValue, Triple A).\n\n"
            "**Anno commerciale:** divisore sempre 365. Più semplice, ma non "
            "replica esattamente gli anni bisestili."
        ),
    )
    anno_civile = base_giorni_label.startswith("Anno civile")

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

# --- Contesto condiviso: valori della sidebar passati ai moduli dei tab ---
ctx = {
    "tasso_mora": tasso_mora,
    "data_stipula": data_stipula,
    "data_pignoramento": data_pignoramento,
    "data_fine": data_fine,
    "caso": caso,
    "is_caso_A": is_caso_A,
    "metodo_triennio": metodo_triennio,
    "anno_civile": anno_civile,
    "pdf_password": pdf_password,
}

# ==========================================================
# BARRA DI STATO / GUIDA (ordine consigliato d'uso)
# ==========================================================
_ok1 = st.session_state.get("debito_totale", 0.0) > 0
_ok2 = st.session_state.get("spese_future", 0.0) > 0
_ico1 = "✅" if _ok1 else "1️⃣"
_ico2 = "✅" if _ok2 else "2️⃣"
_ico3 = "✅" if (_ok1 and _ok2) else "3️⃣"
st.caption(
    f"**Percorso consigliato:**  {_ico1} Auditing (calcola il debito)  →  "
    f"{_ico2} Spese Esecutive  →  {_ico3} Acquisto NPL "
    f"(usa i dati dei primi due)."
)

# ==========================================================
# TAB PRINCIPALI
# ==========================================================
tab1, tab2, tab3 = st.tabs([
    f"{'✅' if _ok1 else '📊'} Auditing e Check GBV",
    f"{'✅' if _ok2 else '🔮'} Previsione Spese Esecutive",
    "🤝 Acquisto Credito e DPO",
])

# ----------------------------------------------------------
# TAB 1 — AUDITING E CHECK GBV
# ----------------------------------------------------------
with tab1:
    tab_auditing.render(ctx)

# ----------------------------------------------------------
# TAB 2 — PREVISIONE SPESE ESECUTIVE (consulenza strategica)
# ----------------------------------------------------------
with tab2:
    tab_spese.render(ctx)

# ----------------------------------------------------------
# TAB 3 — ACQUISTO CREDITO NPL E STRALCIO
# ----------------------------------------------------------
with tab3:
    tab_npl.render(ctx)
