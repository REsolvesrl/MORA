"""Tab 3 — Acquisto Credito (NPL) e Stralcio."""

from datetime import date

import streamlit as st
import plotly.graph_objects as go

from calcoli import COSTI_ACQUISIZIONE
from pdf_export import genera_report_pdf_npl
from formatters import fmt_eur, fmt_pct


def render(ctx):
    pdf_password = ctx["pdf_password"]

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

    # Stato delle dipendenze (guida passo-passo)
    stato_t1 = "✅ completato" if debito > 0 else "⬜ da fare"
    stato_t2 = "✅ completato" if spese_procedura > 0 else "⬜ da fare"
    st.caption(
        f"Dipendenze: **Tab 1 (Auditing)** {stato_t1}  ·  "
        f"**Tab 2 (Spese Esecutive)** {stato_t2}"
    )

    if gbv_base <= 0:
        st.info(
            "⚠️ **Dati non ancora disponibili.**\n\n"
            "1. Vai nel **Tab 1 (Auditing)**, compila i dati e premi "
            "**Calcola** (così ottieni il debito).\n"
            "2. Vai nel **Tab 2 (Previsione Spese Esecutive)** e imposta le voci.\n\n"
            "Poi torna qui: i valori si popoleranno automaticamente."
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

    st.plotly_chart(fig, width="stretch")

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
