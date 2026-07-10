"""Tab 2 — Previsione Spese Esecutive."""

from datetime import date

import streamlit as st

from calcoli import (
    SPESE_IMMOBILIARE,
    SPESE_MOBILIARE,
    calcola_compenso_custode,
    calcola_compenso_delegato,
)
from pdf_export import genera_report_pdf_spese
from formatters import fmt_eur, fmt_pct


def render(ctx):
    pdf_password = ctx["pdf_password"]

    st.subheader("🔮 Stima dei costi di una procedura esecutiva")
    st.caption("Proiezione forfettaria dei costi futuri se il creditore prosegue "
               "con l'esecuzione. Valori indicativi: verificare col foro competente.")

    p1, p2 = st.columns(2)
    tipo_procedura = p1.selectbox(
        "Tipo di procedura",
        options=["Pignoramento Immobiliare", "Pignoramento Mobiliare", "Pignoramento Presso Terzi"],
        index=0,
        key="t2_tipo_procedura",
    )
    valore_bene = p2.number_input(
        "Valore stimato dell'immobile / bene (€)",
        min_value=0.0,
        value=120000.0,
        step=5000.0,
        key="t2_valore_bene",
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
            step=50.0, format="%.2f", key="t2_spese_vive"
        )
        ctu_val = r2.number_input(
            "CTU (perizia di stima)",
            min_value=0.0, value=float(SPESE_IMMOBILIARE["ctu"]),
            step=50.0, format="%.2f", key="t2_ctu"
        )

        pubblicita_val = st.number_input(
            "Pubblicità asta (PVP)",
            min_value=0.0, value=float(SPESE_IMMOBILIARE["pubblicita"]),
            step=50.0, format="%.2f", key="t2_pubblicita"
        )

        spese_legali_nostre_val = st.number_input(
            "Nostre spese legali",
            min_value=0.0, value=float(SPESE_IMMOBILIARE["spese_legali_nostre"]),
            step=50.0, format="%.2f", key="t2_legali_nostre"
        )

        # ============================================================
        # COMPENSI PROFESSIONALI CALCOLATI (Custode + Delegato)
        # ============================================================
        st.markdown("#### ⚖️ Compensi professionali (calcolo automatico)")
        st.caption(
            "Calcolati automaticamente sul **valore di aggiudicazione** "
            f"(= valore stimato del bene: **{fmt_eur(valore_bene)}**) "
            "secondo il D.M. 80/2009 (Custode) e il D.M. 227/2015 "
            "(Delegato). Puoi sovrascrivere i valori manualmente."
        )

        # Calcolo automatico (IVA e oneri inclusi = totale documento)
        det_custode = calcola_compenso_custode(valore_bene)
        det_delegato = calcola_compenso_delegato(valore_bene)
        custode_auto = det_custode["totale"]
        delegato_auto = det_delegato["totale"]

        rc1, rc2 = st.columns(2)
        custode_val = rc1.number_input(
            "Compenso Custode Stimato (IVA e oneri incl.)",
            min_value=0.0, value=float(round(custode_auto, 2)),
            step=50.0, format="%.2f",
            help="Calcolo automatico ex D.M. 80/2009 (scaglioni + 20% "
                 "maggiorazione + 10% spese generali + 4% cassa + 22% IVA). "
                 "Modificabile."
        )
        delegato_val = rc2.number_input(
            "Compenso Delegato Stimato (IVA e oneri incl.)",
            min_value=0.0, value=float(round(delegato_auto, 2)),
            step=50.0, format="%.2f",
            help="Calcolo automatico ex D.M. 227/2015 (4 fasi + 10% spese "
                 "generali + 4% cassa + 22% IVA). Modificabile."
        )

        with st.expander(
            "🔍 Dettaglio Calcolo Compensi (D.M. 80/2009 e D.M. 227/2015)"
        ):
            # ---- CUSTODE ----
            st.markdown("##### 👤 Compenso Custode giudiziario — D.M. 80/2009")
            righe_c = [
                "| Scaglione | Base | Aliquota | Importo |",
                "|:----------|-----:|:--------:|--------:|",
            ]
            for sc in det_custode["scaglioni"]:
                a_label = (
                    "∞" if sc["a"] == float("inf") else fmt_eur(sc["a"])
                )
                righe_c.append(
                    f"| da {fmt_eur(sc['da'])} a {a_label} | "
                    f"{fmt_eur(sc['base'])} | "
                    f"{fmt_pct(sc['aliquota'])} | "
                    f"{fmt_eur(sc['importo'])} |"
                )
            st.markdown("\n".join(righe_c))
            st.markdown(
                f"- Compenso a scaglioni: **{fmt_eur(det_custode['compenso_scaglioni'])}**\n"
                f"- Maggiorazione {fmt_pct(det_custode['maggiorazione_perc'], 0)} "
                f"(indennità liberazione / difficoltà): "
                f"**+ {fmt_eur(det_custode['maggiorazione_importo'])}**\n"
                f"- Compenso netto: **{fmt_eur(det_custode['compenso_netto'])}**\n"
                f"- Spese generali (10%): + {fmt_eur(det_custode['spese_generali'])}\n"
                f"- Cassa previdenza (4%): + {fmt_eur(det_custode['cassa'])}\n"
                f"- Imponibile: **{fmt_eur(det_custode['imponibile'])}**\n"
                f"- IVA (22%): + {fmt_eur(det_custode['iva'])}\n"
                f"- **TOTALE Custode: {fmt_eur(det_custode['totale'])}**"
            )

            st.divider()

            # ---- DELEGATO ----
            st.markdown("##### 🏛️ Compenso Delegato alla vendita — D.M. 227/2015")
            st.markdown(
                f"Scaglione di valore → **{fmt_eur(det_delegato['compenso_fase'])} "
                f"per fase** (4 fasi):"
            )
            righe_d = [
                "| Fase | Compenso |",
                "|:-----|--------:|",
            ]
            for fase in det_delegato["fasi"]:
                righe_d.append(f"| {fase['nome']} | {fmt_eur(fase['importo'])} |")
            righe_d.append(
                f"| **Totale tabellare** | **{fmt_eur(det_delegato['compenso_netto'])}** |"
            )
            st.markdown("\n".join(righe_d))
            st.markdown(
                f"- Compenso tabellare: **{fmt_eur(det_delegato['compenso_netto'])}**\n"
                f"- Spese generali (10%): + {fmt_eur(det_delegato['spese_generali'])}\n"
                f"- Cassa previdenza (4%): + {fmt_eur(det_delegato['cassa'])}\n"
                f"- Imponibile: **{fmt_eur(det_delegato['imponibile'])}**\n"
                f"- IVA (22%): + {fmt_eur(det_delegato['iva'])}\n"
                f"- **TOTALE Delegato: {fmt_eur(det_delegato['totale'])}**"
            )
            st.caption(
                "ℹ️ I compensi sono stime basate sul valore di aggiudicazione. "
                "La liquidazione finale spetta al Giudice dell'esecuzione, "
                "che può aumentare o ridurre gli importi entro i limiti di legge."
            )

        totale_spese = (
            spese_vive_val + ctu_val + custode_val + delegato_val
            + pubblicita_val + spese_legali_nostre_val
        )
        st.session_state["spese_future"] = totale_spese

        voci_spese = {
            "Spese vive (CU, trascrizioni, ecc.)": spese_vive_val,
            "CTU (perizia di stima)": ctu_val,
            "Compenso Custode (D.M. 80/2009)": custode_val,
            "Compenso Delegato (D.M. 227/2015)": delegato_val,
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
            step=50.0, format="%.2f", key="t2_spese_vive_mob"
        )
        uff_legali_val = r2.number_input(
            "Ufficiale Giudiziario / Legali",
            min_value=0.0, value=float(SPESE_MOBILIARE["ufficiale_legali"]),
            step=50.0, format="%.2f", key="t2_uff_legali"
        )

        r3, r4 = st.columns(2)
        spese_legali_nostre_val = r3.number_input(
            "Nostre spese legali",
            min_value=0.0, value=float(SPESE_MOBILIARE["spese_legali_nostre"]),
            step=50.0, format="%.2f", key="t2_legali_nostre_mob"
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
