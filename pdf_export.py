"""
Generazione del report PDF per MORA.

Espone genera_report_pdf(report_data, password='') -> bytes.

Il PDF è cifrato con AES-128 e applica restrizioni:
- canCopy=0   (no copia / estrazione testo)
- canModify=0 (no modifica)
- canAnnotate=0
- canPrint=1  (stampa consentita)

Se l'utente fornisce una password non vuota, questa diventa la password di
apertura del documento. La owner password è sempre impostata per impedire
la rimozione delle restrizioni.
"""

from datetime import date, datetime
from io import BytesIO

from reportlab.lib import colors, pdfencrypt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether,
)


# ==========================================================
# FORMATTATORI (duplicati locali da streamlit_app per disaccoppiamento)
# ==========================================================

def _fmt_eur(x, decimali=2):
    s = f"{x:,.{decimali}f}"
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{s} €"


def _fmt_pct(x, decimali=2):
    s = f"{x * 100:.{decimali}f}"
    return f"{s.replace('.', ',')}%"


def _fmt_data(d):
    if isinstance(d, (date, datetime)):
        return d.strftime("%d/%m/%Y")
    return str(d)


# ==========================================================
# STILI
# ==========================================================

def _stili():
    base = getSampleStyleSheet()
    stili = {
        "titolo": ParagraphStyle(
            "Titolo", parent=base["Heading1"], fontSize=18,
            textColor=colors.HexColor("#1a1a1a"),
            spaceAfter=4, alignment=1,  # center
        ),
        "sottotitolo": ParagraphStyle(
            "Sottotitolo", parent=base["Normal"], fontSize=10,
            textColor=colors.HexColor("#666666"),
            spaceAfter=12, alignment=1,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontSize=14,
            textColor=colors.HexColor("#ff4b4b"),
            spaceBefore=12, spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "H3", parent=base["Heading3"], fontSize=11,
            textColor=colors.HexColor("#1a1a1a"),
            spaceBefore=8, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"], fontSize=10,
            leading=14, spaceAfter=4,
        ),
        "caption": ParagraphStyle(
            "Caption", parent=base["Normal"], fontSize=8,
            textColor=colors.HexColor("#888888"),
            leading=10, spaceAfter=2,
        ),
        "info_box": ParagraphStyle(
            "InfoBox", parent=base["Normal"], fontSize=9,
            backColor=colors.HexColor("#e8f4fd"),
            borderColor=colors.HexColor("#1f77b4"), borderWidth=1,
            borderPadding=8, leading=12, spaceAfter=8,
        ),
    }
    return stili


def _stile_tabella_base():
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ff4b4b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f8f8f8")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ])


# ==========================================================
# SEZIONI DEL REPORT
# ==========================================================

def _sezione_header(stili, titolo="⚖️ Report Interessi di Mora – Art. 2855 c.c."):
    el = [
        Paragraph(titolo, stili["titolo"]),
        Paragraph(
            f"Generato il {datetime.now().strftime('%d/%m/%Y alle %H:%M')} – "
            "Resolve S.r.l.",
            stili["sottotitolo"]
        ),
    ]
    return el


def _sezione_input(stili, d):
    inp = d["input"]
    caso_label = "CASO A – Lettera DBT" if inp["is_caso_A"] else "CASO B – Notifica Precetto"
    atto = "Lettera DBT" if inp["is_caso_A"] else "Notifica Precetto"

    rows = [
        ["Parametro", "Valore"],
        ["Modalità", caso_label],
        ["Tasso di mora pattuito", _fmt_pct(inp["tasso_mora"])],
        ["Data stipula mutuo", _fmt_data(inp["data_stipula"])],
        ["Data pignoramento", _fmt_data(inp["data_pignoramento"])],
        ["Data di aggiudicazione (fine calcolo)", _fmt_data(inp["data_fine"])],
        ["Data scadenza prima rata insoluta", _fmt_data(inp["data_prima_rata"])],
        ["Frequenza rate", inp["frequenza"]],
        ["Importo singola rata", _fmt_eur(inp["importo_rata"])],
        ["Capitale residuo all'ultima rata pagata", _fmt_eur(inp["capitale_residuo"])],
        [f"Data {atto} (decadenza effettiva)", _fmt_data(inp["data_decadenza_effettiva"])],
        ["Spese legali sostenute", _fmt_eur(inp["spese_legali"])],
    ]
    tbl = Table(rows, colWidths=[90 * mm, 80 * mm])
    tbl.setStyle(_stile_tabella_base())
    return [Paragraph("1. Dati di input", stili["h2"]), tbl, Spacer(1, 8)]


def _sezione_riepilogo(stili, d):
    risultato = d["calcolo"]["risultato"]
    totale_gen = d["calcolo"]["totale_gen"]
    rows = [
        ["Voce", "Importo"],
        ["🏛️  Credito IPOTECARIO", _fmt_eur(risultato["ipotecario"])],
        ["📄  Credito CHIROGRAFARIO", _fmt_eur(risultato["chirografario"])],
        ["💰  TOTALE interessi di mora", _fmt_eur(totale_gen)],
    ]
    tbl = Table(rows, colWidths=[110 * mm, 60 * mm])
    style = _stile_tabella_base()
    style.add("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fff3e0"))
    style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
    tbl.setStyle(style)
    return [Paragraph("2. Riepilogo importi", stili["h2"]), tbl, Spacer(1, 8)]


def _sezione_didattica_triennio(stili, d):
    tr = d["triennio"]
    testo = (
        "<b>Perché il triennio ipotecario (Fase 2) inizia esattamente il "
        f"{_fmt_data(tr['inizio_triennio'])}?</b><br/><br/>"
        "Perché, secondo la prassi prevalente nei calcoli esecutivi in base "
        "all'<b>Art. 2855 c.c.</b>, il triennio garantito copre <b>esattamente "
        "i 3 anni antecedenti alla data del pignoramento</b>. Tutto il "
        "periodo precedente a questa data <b>non gode del privilegio "
        "ipotecario</b> e finisce nella <b>Fase 1 (Chirografo)</b>."
    )
    return [
        Paragraph("3. Spiegazione didattica", stili["h2"]),
        Paragraph(testo, stili["info_box"]),
        Spacer(1, 8),
    ]


def _sezione_divisione_2855(stili, d):
    v = d["calcolo"]["risultato"]["voci_2855"]
    totale = d["calcolo"]["totale_gen"]
    somma = v["pre_chiro"] + v["triennio_ipo"] + v["post_ipo"] + v["post_chiro"]

    rows = [
        ["Fase", "Voce", "Importo"],
        ["🔵 Pre-triennio", "Chirografario (mora)", _fmt_eur(v["pre_chiro"])],
        ["🟢 Triennio", "Ipotecario (mora)", _fmt_eur(v["triennio_ipo"])],
        ["🟠 Post-triennio", "Ipotecario (legale)", _fmt_eur(v["post_ipo"])],
        ["🟠 Post-triennio", "Chirografario (eccedenza)", _fmt_eur(v["post_chiro"])],
        ["", "TOTALE INTERESSI", _fmt_eur(somma)],
    ]
    tbl = Table(rows, colWidths=[45 * mm, 80 * mm, 45 * mm])
    style = _stile_tabella_base()
    style.add("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fff3e0"))
    style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
    tbl.setStyle(style)

    quadratura = (
        f"✅ Quadratura verificata: somma 4 voci = {_fmt_eur(somma)} "
        f"vs totale interessi = {_fmt_eur(totale)} (scarto: "
        f"{_fmt_eur(abs(somma - totale))})"
        if abs(somma - totale) <= 0.01
        else f"⚠️ Scarto di quadratura: {_fmt_eur(abs(somma - totale))}"
    )
    return [
        Paragraph("4. Divisione ex Art. 2855 c.c.", stili["h2"]),
        tbl,
        Paragraph(quadratura, stili["caption"]),
        Spacer(1, 8),
    ]


def _sezione_fase1(stili, d):
    inp = d["input"]
    v = d["calcolo"]["risultato"]["voci_2855"]
    tr = d["triennio"]
    testo = (
        f"<b>Periodo:</b> dalla prima rata scaduta "
        f"({_fmt_data(inp['data_prima_rata'])}) "
        f"fino all'inizio del triennio ({_fmt_data(tr['inizio_triennio'])}, "
        f"cioè data pignoramento − 3 anni).<br/>"
        f"<b>Capitale di riferimento:</b> singola rata insoluta "
        f"({_fmt_eur(inp['importo_rata'])}).<br/>"
        f"<b>Tasso applicato:</b> {_fmt_pct(inp['tasso_mora'])} "
        f"(tasso di mora pattuito).<br/>"
        f"<b>Formula:</b> Capitale × Tasso × Giorni / 365<br/><br/>"
        f"Poiché gli interessi anteriori al triennio <b>degradano a "
        f"chirografario</b>, la loro quota viene separata.<br/><br/>"
        f"<b>Risultato Fase 1 (chirografario):</b> "
        f"<b>{_fmt_eur(v['pre_chiro'])}</b>"
    )
    return [
        Paragraph("5. Fase 1 — Pre-triennio (chirografario)", stili["h2"]),
        Paragraph(testo, stili["body"]),
        Spacer(1, 6),
    ]


def _sezione_fase2(stili, d):
    inp = d["input"]
    v = d["calcolo"]["risultato"]["voci_2855"]
    tr = d["triennio"]
    nota_bisestile = (
        "include un 29 febbraio" if tr["gg_triennio"] == 1096
        else "nessun 29 febbraio nel periodo"
    )
    testo = (
        f"<b>Inizio triennio:</b> {_fmt_data(tr['inizio_triennio'])} "
        f"(data pignoramento − 3 anni esatti).<br/>"
        f"<b>Fine triennio:</b> {_fmt_data(tr['fine_triennio'])} "
        f"(coincide con la data del pignoramento).<br/>"
        f"<b>Giorni del triennio:</b> {tr['gg_triennio']} "
        f"({nota_bisestile}).<br/><br/>"
        f"<b>Capitale di riferimento:</b><br/>"
        f"&nbsp;&nbsp;• Per le rate scadute: singola rata "
        f"({_fmt_eur(inp['importo_rata'])})<br/>"
        f"&nbsp;&nbsp;• Per il capitale residuo: "
        f"{_fmt_eur(inp['capitale_residuo'])}<br/>"
        f"<b>Tasso applicato:</b> {_fmt_pct(inp['tasso_mora'])} "
        f"(tasso di mora pattuito — pieno).<br/>"
        f"<b>Formula:</b> Capitale × {_fmt_pct(inp['tasso_mora'])} × "
        f"{tr['gg_triennio']} / 365<br/><br/>"
        f"<b>Risultato Fase 2 (ipotecario al tasso di mora):</b> "
        f"<b>{_fmt_eur(v['triennio_ipo'])}</b>"
    )
    return [
        Paragraph("6. Fase 2 — Triennio (ipotecario al tasso di mora)", stili["h2"]),
        Paragraph(testo, stili["body"]),
        Spacer(1, 6),
    ]


def _sezione_fase3(stili, d):
    inp = d["input"]
    v = d["calcolo"]["risultato"]["voci_2855"]
    tr = d["triennio"]
    segmenti = tr.get("segmenti_legale") or []

    elementi = [
        Paragraph(
            "7. Fase 3 — Post-triennio (ipotecario al legale + chirografario eccedenza)",
            stili["h2"]
        ),
        Paragraph(
            f"<b>Periodo:</b> {_fmt_data(tr['fine_triennio'])} (pignoramento) "
            f"→ {_fmt_data(inp['data_fine'])} (aggiudicazione).<br/>"
            f"<b>Giorni Fase 3:</b> {tr['gg_post']}.<br/><br/>"
            f"Dopo il pignoramento la garanzia ipotecaria degrada: la legge "
            f"riconosce la sola quota al <b>tasso legale</b> come ipotecaria; "
            f"l'eccedenza (mora − legale) diventa chirografaria.<br/><br/>"
            f"⚠️ Il tasso legale <b>cambia ogni 1° gennaio</b>. Il calcolo è "
            f"pro-rata temporis, spezzato ad ogni cambio d'anno solare.",
            stili["body"]
        ),
        Spacer(1, 4),
    ]

    if segmenti:
        elementi.append(Paragraph(
            f"<b>Spaccato del tasso legale anno per anno</b> "
            f"(calcolato sul capitale residuo {_fmt_eur(inp['capitale_residuo'])}):",
            stili["body"]
        ))
        rows = [["Periodo", "Giorni", "Tasso legale", "Interesse"]]
        for seg in segmenti:
            periodo = (
                f"{_fmt_data(seg['inizio'])} → {_fmt_data(seg['fine'])}"
            )
            rows.append([
                periodo,
                str(seg["giorni"]),
                _fmt_pct(seg["tasso"]),
                _fmt_eur(seg["interesse"]),
            ])
        totale_seg = sum(s["interesse"] for s in segmenti)
        rows.append([
            "TOTALE Quota A (capitale residuo)",
            str(tr["gg_post"]),
            "",
            _fmt_eur(totale_seg),
        ])
        tbl = Table(rows, colWidths=[60 * mm, 25 * mm, 30 * mm, 35 * mm])
        style = _stile_tabella_base()
        style.add("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fff3e0"))
        style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
        tbl.setStyle(style)
        elementi.append(tbl)
        elementi.append(Spacer(1, 6))

    riepilogo_fase3 = [
        ["Voce", "Importo"],
        ["🏛️ TOTALE Quota A — Ipotecaria (legale)", _fmt_eur(v["post_ipo"])],
        ["📄 TOTALE Quota B — Chirografaria (eccedenza)", _fmt_eur(v["post_chiro"])],
    ]
    tbl2 = Table(riepilogo_fase3, colWidths=[110 * mm, 60 * mm])
    tbl2.setStyle(_stile_tabella_base())
    elementi.append(tbl2)
    elementi.append(Spacer(1, 8))
    return elementi


def _sezione_gbv(stili, d):
    gbv = d.get("gbv")
    if not gbv or gbv.get("risultato_gbv") is None:
        return []

    risultato_gbv = gbv["risultato_gbv"]
    interessi = risultato_gbv["ipotecario"] + risultato_gbv["chirografario"]
    capitale = d["input"]["capitale_residuo"]
    spese = d["input"]["spese_legali"]
    totale_calc = capitale + interessi + spese
    gbv_dich = gbv["gbv_dichiarato"]
    gbv_plus_spese = gbv_dich + spese
    delta = gbv_plus_spese - totale_calc

    SOGLIA = 10.0
    if delta > SOGLIA:
        esito = (
            f"🚨 ANOMALIA: il GBV dichiarato supera il totale calcolato di "
            f"{_fmt_eur(delta)}. Possibile anatocismo, estensione ipotecaria "
            f"indebita, tassi non dovuti o spese non documentate."
        )
        col_esito = colors.HexColor("#ffe6e6")
    elif delta < -SOGLIA:
        esito = (
            f"ℹ️ Il totale calcolato supera il GBV dichiarato di "
            f"{_fmt_eur(abs(delta))}. Pretesa creditoria prudenziale."
        )
        col_esito = colors.HexColor("#fff8e1")
    else:
        esito = (
            f"✅ GBV congruo: importi allineati (scarto {_fmt_eur(abs(delta))} "
            f"entro la soglia di {_fmt_eur(SOGLIA)})."
        )
        col_esito = colors.HexColor("#e8f5e9")

    rows = [
        ["Voce", "Importo"],
        ["Quota capitale residua mutuo", _fmt_eur(capitale)],
        ["Spese legali sostenute", _fmt_eur(spese)],
        [
            f"Interessi reali al {_fmt_data(gbv['data_attualizzazione_gbv'])}",
            _fmt_eur(interessi),
        ],
        ["TOTALE CALCOLATO (Capitale + Interessi + Spese)", _fmt_eur(totale_calc)],
        ["GBV DICHIARATO + Spese Legali", _fmt_eur(gbv_plus_spese)],
        ["DELTA (Dichiarato − Calcolato)", _fmt_eur(delta)],
    ]
    tbl = Table(rows, colWidths=[110 * mm, 60 * mm])
    style = _stile_tabella_base()
    style.add("BACKGROUND", (0, -1), (-1, -1), col_esito)
    style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
    style.add("BACKGROUND", (0, -3), (-1, -3), colors.HexColor("#f0f0f0"))
    style.add("FONTNAME", (0, -3), (-1, -3), "Helvetica-Bold")
    tbl.setStyle(style)

    return [
        PageBreak(),
        Paragraph("8. Check GBV dichiarato dal creditore", stili["h2"]),
        Paragraph(
            f"Il GBV dichiarato viene paragonato al nostro calcolo "
            f"<b>congelato alla data del conteggio del creditore</b> "
            f"(<b>{_fmt_data(gbv['data_attualizzazione_gbv'])}</b>), non "
            f"alla data di aggiudicazione, per evitare falsi positivi.",
            stili["caption"]
        ),
        tbl,
        Spacer(1, 6),
        Paragraph(esito, stili["body"]),
    ]


def _sezione_footer(stili, nota=None):
    default = (
        "Documento generato da MORA – strumento di supporto al calcolo "
        "degli interessi di mora ex art. 2855 c.c. I risultati devono "
        "essere verificati da un professionista. Il presente documento "
        "è cifrato: la copia del testo e la modifica sono disabilitate."
    )
    return [
        Spacer(1, 12),
        Paragraph(nota or default, stili["caption"]),
    ]


# ==========================================================
# BUILDER COMUNE (encryption + header + footer + build)
# ==========================================================

def _build_pdf(titolo_doc: str, titolo_header: str,
               sezioni_corpo: list, password: str = "",
               nota_footer: str = None) -> bytes:
    """Compone un PDF (header + sezioni + footer), lo cifra, ritorna bytes."""
    enc = pdfencrypt.StandardEncryption(
        userPassword=password or "",
        ownerPassword="mora-owner-resolve-2026",
        canPrint=1,
        canModify=0,
        canCopy=0,
        canAnnotate=0,
        strength=128,
    )
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=titolo_doc,
        author="MORA / Resolve S.r.l.",
        encrypt=enc,
    )
    stili = _stili()
    elementi = []
    elementi += _sezione_header(stili, titolo_header)
    elementi += sezioni_corpo
    elementi += _sezione_footer(stili, nota_footer)
    doc.build(elementi)
    return buf.getvalue()


# ==========================================================
# API PUBBLICA – Tab 1 (Auditing e Check GBV)
# ==========================================================

def genera_report_pdf(report_data: dict, password: str = "") -> bytes:
    """Report del Tab 1: ricostruzione del calcolo degli interessi di mora."""
    stili = _stili()
    corpo = []
    corpo += _sezione_input(stili, report_data)
    corpo += _sezione_riepilogo(stili, report_data)
    corpo += _sezione_didattica_triennio(stili, report_data)
    corpo += _sezione_divisione_2855(stili, report_data)
    corpo.append(PageBreak())
    corpo += _sezione_fase1(stili, report_data)
    corpo += _sezione_fase2(stili, report_data)
    corpo += _sezione_fase3(stili, report_data)
    corpo += _sezione_gbv(stili, report_data)
    return _build_pdf(
        titolo_doc="Report MORA – Interessi di mora ex art. 2855 c.c.",
        titolo_header="⚖️ Report Interessi di Mora – Art. 2855 c.c.",
        sezioni_corpo=corpo,
        password=password,
    )


# ==========================================================
# API PUBBLICA – Tab 2 (Previsione Spese Esecutive)
# ==========================================================

def genera_report_pdf_spese(report_data: dict, password: str = "") -> bytes:
    """Report del Tab 2: stima dei costi di una procedura esecutiva.

    report_data deve contenere:
      - tipo_procedura (str)
      - valore_bene (float)
      - voci (dict ordinato: nome_voce -> importo)
      - totale_spese (float)
      - incidenza_pct (float | None): incidenza % sul valore del bene
    """
    stili = _stili()
    corpo = []

    rows_input = [
        ["Parametro", "Valore"],
        ["Tipo di procedura", report_data["tipo_procedura"]],
        ["Valore stimato dell'immobile / bene", _fmt_eur(report_data["valore_bene"])],
    ]
    tbl_input = Table(rows_input, colWidths=[90 * mm, 80 * mm])
    tbl_input.setStyle(_stile_tabella_base())
    corpo += [
        Paragraph("1. Dati di input", stili["h2"]),
        tbl_input,
        Spacer(1, 8),
    ]

    rows_voci = [["Voce di spesa", "Importo"]]
    for nome, importo in report_data["voci"].items():
        rows_voci.append([nome, _fmt_eur(importo)])
    rows_voci.append(["TOTALE SPESE ESECUTIVE STIMATE", _fmt_eur(report_data["totale_spese"])])
    tbl_voci = Table(rows_voci, colWidths=[110 * mm, 60 * mm])
    style_voci = _stile_tabella_base()
    style_voci.add("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fff3e0"))
    style_voci.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
    tbl_voci.setStyle(style_voci)
    corpo += [
        Paragraph("2. Voci di spesa", stili["h2"]),
        tbl_voci,
        Spacer(1, 8),
    ]

    nota_prededuz = (
        "⚠️ Attenzione: proseguendo con la procedura, il debito aumenterà di "
        f"circa {_fmt_eur(report_data['totale_spese'])}, riducendo il "
        "ricavato netto della vendita. Questi costi sono in prededuzione "
        "(art. 2770 c.c.) e vengono soddisfatti con priorità sul ricavato, "
        "prima ancora del creditore ipotecario."
    )
    corpo += [
        Paragraph("3. Note e considerazioni", stili["h2"]),
        Paragraph(nota_prededuz, stili["body"]),
    ]
    if report_data.get("incidenza_pct") is not None:
        corpo += [
            Spacer(1, 4),
            Paragraph(
                f"📉 Incidenza delle spese sul valore del bene: "
                f"<b>{_fmt_pct(report_data['incidenza_pct'] / 100, decimali=1)}</b>",
                stili["body"]
            ),
        ]

    return _build_pdf(
        titolo_doc="Report MORA – Previsione Spese Esecutive",
        titolo_header="🔮 Report Previsione Spese Esecutive",
        sezioni_corpo=corpo,
        password=password,
    )


# ==========================================================
# API PUBBLICA – Tab 3 (Acquisto Credito NPL e DPO)
# ==========================================================

def genera_report_pdf_npl(report_data: dict, password: str = "") -> bytes:
    """Report del Tab 3: simulazione acquisto credito NPL.

    report_data deve contenere:
      - gbv_base, fonte_gbv (str)
      - spese_procedura, costi_acquisizione, totale_spese_fisse
      - voci_costi_acq (dict: fronting/notaio/servicer/advisors)
      - debito_reale_calcolato
      - margine (frazione), durata_mesi
      - base_netta, importo_margine, offerta_target
      - utile_lordo, utile_interessi_maturati, utile_totale
      - capitale_investito, roe, irr_annuale
    """
    stili = _stili()
    corpo = []

    rows_gbv = [
        ["Parametro", "Valore"],
        [f"GBV di partenza ({report_data['fonte_gbv']})", _fmt_eur(report_data["gbv_base"])],
        ["Spese Procedura (Tab 2)", _fmt_eur(report_data["spese_procedura"])],
        ["Debito Reale Calcolato (Tab 1)", _fmt_eur(report_data["debito_reale_calcolato"])],
        ["Margine di trattativa / sconto", _fmt_pct(report_data["margine"], decimali=0)],
        ["Durata stimata operazione", f"{report_data['durata_mesi']} mesi"],
    ]
    tbl_gbv = Table(rows_gbv, colWidths=[110 * mm, 60 * mm])
    tbl_gbv.setStyle(_stile_tabella_base())
    corpo += [
        Paragraph("1. Dati di input", stili["h2"]),
        tbl_gbv,
        Spacer(1, 8),
    ]

    voci = report_data["voci_costi_acq"]
    rows_acq = [
        ["Voce", "Importo"],
        ["Fronting", _fmt_eur(voci["fronting"])],
        ["Notaio", _fmt_eur(voci["notaio"])],
        ["Gestore credito (Servicer)", _fmt_eur(voci["servicer"])],
        ["Advisors", _fmt_eur(voci["advisors"])],
        ["TOTALE Costi Acquisizione", _fmt_eur(report_data["costi_acquisizione"])],
        ["TOTALE Spese Fisse (Procedura + Acquisizione)", _fmt_eur(report_data["totale_spese_fisse"])],
    ]
    tbl_acq = Table(rows_acq, colWidths=[110 * mm, 60 * mm])
    style_acq = _stile_tabella_base()
    style_acq.add("BACKGROUND", (0, -2), (-1, -1), colors.HexColor("#f0f0f0"))
    style_acq.add("FONTNAME", (0, -2), (-1, -1), "Helvetica-Bold")
    tbl_acq.setStyle(style_acq)
    corpo += [
        Paragraph("2. Costi di acquisizione del credito", stili["h2"]),
        tbl_acq,
        Spacer(1, 8),
    ]

    rows_wf = [
        ["Voce", "Importo"],
        ["GBV di Partenza", _fmt_eur(report_data["gbv_base"])],
        ["− Totale Spese Fisse", _fmt_eur(report_data["totale_spese_fisse"])],
        ["= Base Netta pre-sconto", _fmt_eur(report_data["base_netta"])],
        [f"− Sconto trattativa ({_fmt_pct(report_data['margine'], decimali=0)})",
         _fmt_eur(report_data["importo_margine"])],
        ["🎯 OFFERTA TARGET (Servicer)", _fmt_eur(report_data["offerta_target"])],
    ]
    tbl_wf = Table(rows_wf, colWidths=[110 * mm, 60 * mm])
    style_wf = _stile_tabella_base()
    style_wf.add("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fff3e0"))
    style_wf.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
    tbl_wf.setStyle(style_wf)
    corpo += [
        Paragraph("3. Waterfall — Dal GBV all'Offerta Target", stili["h2"]),
        tbl_wf,
        Spacer(1, 8),
    ]

    rows_utile = [
        ["Voce", "Importo"],
        ["Utile Lordo (su GBV)", _fmt_eur(report_data["utile_lordo"])],
        ["+ Utile da Interessi Maturati", _fmt_eur(report_data["utile_interessi_maturati"])],
        ["= Utile Totale", _fmt_eur(report_data["utile_totale"])],
        ["Capitale Investito Totale", _fmt_eur(report_data["capitale_investito"])],
    ]
    tbl_utile = Table(rows_utile, colWidths=[110 * mm, 60 * mm])
    style_utile = _stile_tabella_base()
    style_utile.add("BACKGROUND", (0, -2), (-1, -2), colors.HexColor("#fff3e0"))
    style_utile.add("FONTNAME", (0, -2), (-1, -2), "Helvetica-Bold")
    tbl_utile.setStyle(style_utile)
    corpo += [
        Paragraph("4. Composizione dell'Utile", stili["h2"]),
        tbl_utile,
        Spacer(1, 8),
    ]

    rows_metr = [
        ["Metrica", "Valore"],
        ["ROE (Return on Equity)", _fmt_pct(report_data["roe"])],
        [f"IRR Annualizzato (su {report_data['durata_mesi']} mesi)",
         _fmt_pct(report_data["irr_annuale"])],
    ]
    tbl_metr = Table(rows_metr, colWidths=[110 * mm, 60 * mm])
    tbl_metr.setStyle(_stile_tabella_base())
    corpo += [
        Paragraph("5. Metriche finanziarie", stili["h2"]),
        tbl_metr,
    ]

    return _build_pdf(
        titolo_doc="Report MORA – Acquisto Credito NPL",
        titolo_header="🤝 Report Acquisto Credito NPL e DPO",
        sezioni_corpo=corpo,
        password=password,
    )
