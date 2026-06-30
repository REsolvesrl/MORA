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

def _sezione_header(stili):
    el = [
        Paragraph("⚖️ Report Interessi di Mora – Art. 2855 c.c.", stili["titolo"]),
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


def _sezione_footer(stili):
    return [
        Spacer(1, 12),
        Paragraph(
            "Documento generato da MORA – strumento di supporto al calcolo "
            "degli interessi di mora ex art. 2855 c.c. I risultati devono "
            "essere verificati da un professionista. Il presente documento "
            "è cifrato: la copia del testo e la modifica sono disabilitate.",
            stili["caption"]
        ),
    ]


# ==========================================================
# API PUBBLICA
# ==========================================================

def genera_report_pdf(report_data: dict, password: str = "") -> bytes:
    """
    Genera il report PDF e ritorna i bytes.

    Restrizioni applicate: no copia, no modifica, no annotazioni.
    La stampa resta consentita.

    Se `password` è non vuota, diventa la user password (apertura).
    La owner password è sempre impostata internamente per impedire la
    rimozione delle restrizioni con strumenti standard.
    """
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
        title="Report MORA – Interessi di mora ex art. 2855 c.c.",
        author="MORA / Resolve S.r.l.",
        encrypt=enc,
    )

    stili = _stili()
    elementi = []
    elementi += _sezione_header(stili)
    elementi += _sezione_input(stili, report_data)
    elementi += _sezione_riepilogo(stili, report_data)
    elementi += _sezione_didattica_triennio(stili, report_data)
    elementi += _sezione_divisione_2855(stili, report_data)
    elementi.append(PageBreak())
    elementi += _sezione_fase1(stili, report_data)
    elementi += _sezione_fase2(stili, report_data)
    elementi += _sezione_fase3(stili, report_data)
    elementi += _sezione_gbv(stili, report_data)
    elementi += _sezione_footer(stili)

    doc.build(elementi)
    return buf.getvalue()
