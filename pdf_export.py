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

# Formattatori condivisi (alias interni per non toccare le chiamate esistenti)
from formatters import fmt_eur as _fmt_eur
from formatters import fmt_pct as _fmt_pct
from formatters import fmt_data as _fmt_data


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
# TEMA DARK (navy + oro) — replica i colori del software
# ==========================================================

# Palette di brand (identica a streamlit_app.py / config.toml)
_D_NAVY = colors.HexColor("#1A2744")       # fondo pagina
_D_NAVY_CARD = colors.HexColor("#243459")  # riga tabella (pari)
_D_NAVY_CARD2 = colors.HexColor("#2C3E63")  # riga tabella (dispari)
_D_ORO = colors.HexColor("#C9A96A")        # accenti / intestazioni
_D_CREMA = colors.HexColor("#ECE7DA")      # testo corpo
_D_BLU = colors.HexColor("#6E8FC7")        # chirografario
_D_GRID = colors.HexColor("#3C4C6E")       # linee griglia
_D_CAPTION = colors.HexColor("#A9B4C9")    # testo tenue


def _stili_dark():
    base = getSampleStyleSheet()
    return {
        "titolo": ParagraphStyle(
            "TitoloD", parent=base["Heading1"], fontSize=18,
            textColor=_D_ORO, spaceAfter=4, alignment=1,
        ),
        "sottotitolo": ParagraphStyle(
            "SottoD", parent=base["Normal"], fontSize=10,
            textColor=_D_CREMA, spaceAfter=12, alignment=1,
        ),
        "h2": ParagraphStyle(
            "H2D", parent=base["Heading2"], fontSize=14,
            textColor=_D_ORO, spaceBefore=12, spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "H3D", parent=base["Heading3"], fontSize=11,
            textColor=_D_CREMA, spaceBefore=8, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "BodyD", parent=base["Normal"], fontSize=10,
            leading=14, spaceAfter=4, textColor=_D_CREMA,
        ),
        "caption": ParagraphStyle(
            "CaptionD", parent=base["Normal"], fontSize=8,
            textColor=_D_CAPTION, leading=10, spaceAfter=2,
        ),
        "info_box": ParagraphStyle(
            "InfoBoxD", parent=base["Normal"], fontSize=9,
            backColor=_D_NAVY_CARD, textColor=_D_CREMA,
            borderColor=_D_ORO, borderWidth=1,
            borderPadding=8, leading=12, spaceAfter=8,
        ),
        "warn_box": ParagraphStyle(
            "WarnBoxD", parent=base["Normal"], fontSize=9,
            backColor=colors.HexColor("#3A2E1A"), textColor=_D_CREMA,
            borderColor=_D_ORO, borderWidth=1,
            borderPadding=8, leading=13, spaceAfter=8,
        ),
    }


def _stile_tabella_dark(evidenzia_ultima: bool = False):
    ts = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _D_ORO),
        ("TEXTCOLOR", (0, 0), (-1, 0), _D_NAVY),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TEXTCOLOR", (0, 1), (-1, -1), _D_CREMA),
        ("GRID", (0, 0), (-1, -1), 0.5, _D_GRID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_D_NAVY_CARD, _D_NAVY_CARD2]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ])
    if evidenzia_ultima:
        # riga totale: fondo oro tenue + testo oro in grassetto
        ts.add("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#33405E"))
        ts.add("TEXTCOLOR", (0, -1), (-1, -1), _D_ORO)
        ts.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
        ts.add("LINEABOVE", (0, -1), (-1, -1), 1.2, _D_ORO)
    return ts


def _sfondo_navy(canvas, doc):
    """Dipinge il fondo navy su tutta la pagina (tema dark)."""
    canvas.saveState()
    canvas.setFillColor(_D_NAVY)
    w, h = doc.pagesize
    canvas.rect(0, 0, w, h, stroke=0, fill=1)
    # sottile filetto oro in alto come richiamo del brand
    canvas.setFillColor(_D_ORO)
    canvas.rect(0, h - 6, w, 6, stroke=0, fill=1)
    canvas.restoreState()


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


def _sezione_scomposizione_rate(stili, d):
    """Tabella di scomposizione rata per rata (Fase 1 pre-decadenza).

    Due varianti:
    - Senza piano di ammortamento: importo intero per rata + verifica
      via giacenza media.
    - Con piano (anti-anatocismo): mostra anche quota interessi (messa
      da parte) e quota capitale (base di calcolo della mora) + nota
      legale ex art. 1283 c.c.
    """
    fase1 = (
        d["calcolo"]["risultato"]["dettaglio"]
         .get("FASE_1_rate", {})
    )
    rate_bk = fase1.get("rate_breakdown", [])
    if not rate_bk:
        return []

    inp = d["input"]
    usa_piano = fase1.get("usa_piano_ammortamento", False)

    if usa_piano:
        rows = [["# piano", "Data scad.", "Rata totale",
                 "Q. interessi", "Q. capitale", "gg mora", "Interesse"]]
        for br in rate_bk:
            rows.append([
                str(br["num_rata_piano"]),
                _fmt_data(br["data_scadenza"]),
                _fmt_eur(br["importo_rata_originale"]),
                _fmt_eur(br["quota_interessi"]),
                _fmt_eur(br["quota_capitale"]),
                str(br["giorni_mora"]),
                _fmt_eur(br["interesse_maturato"]),
            ])
        somma_rate = sum(br["importo_rata_originale"] for br in rate_bk)
        somma_qi = sum(br["quota_interessi"] for br in rate_bk)
        somma_qc = sum(br["quota_capitale"] for br in rate_bk)
        somma_gg = sum(br["giorni_mora"] for br in rate_bk)
        somma_int = sum(br["interesse_maturato"] for br in rate_bk)
        rows.append([
            "TOT", "—", _fmt_eur(somma_rate),
            _fmt_eur(somma_qi), _fmt_eur(somma_qc),
            str(somma_gg), _fmt_eur(somma_int),
        ])
        tbl = Table(rows, colWidths=[12 * mm, 22 * mm, 25 * mm,
                                     25 * mm, 25 * mm, 15 * mm, 25 * mm])
        style = _stile_tabella_base()
        style.add("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fff3e0"))
        style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
        style.add("FONTSIZE", (0, 0), (-1, -1), 7)
        tbl.setStyle(style)
        intro = (
            "🛡️ <b>Calcolo anti-anatocismo attivo (art. 1283 c.c.).</b><br/>"
            "Il software itera rata per rata: per ciascuna rata insoluta "
            "estratta dal piano di ammortamento, applica il tasso di mora "
            "<b>esclusivamente sulla Quota Capitale</b> (non sull'intera "
            "rata), per i giorni esatti di ritardo. La Quota Interessi è "
            "tracciata a parte e va sommata al debito finale senza produrre "
            "ulteriore mora."
        )
        nota_legale = (
            "<b>Nota:</b> Al fine di evitare l'anatocismo, gli interessi di "
            "mora sulle rate scadute sono stati calcolati esclusivamente "
            "sulla Quota Capitale delle stesse, ricavata dal piano di "
            "ammortamento."
        )
        return [
            PageBreak(),
            Paragraph("5b. Scomposizione rata per rata (Fase 1)", stili["h2"]),
            Paragraph(intro, stili["body"]),
            Spacer(1, 4),
            tbl,
            Spacer(1, 4),
            Paragraph(nota_legale, stili["caption"]),
        ]

    # ----- Variante senza piano: comportamento storico + giacenza media -----
    rows = [["#", "Data scadenza", "Importo", "Giorni mora", "Interesse"]]
    for br in rate_bk:
        rows.append([
            str(br["i"]),
            _fmt_data(br["data_scadenza"]),
            _fmt_eur(br["importo_rata_originale"]),
            str(br["giorni_mora"]),
            _fmt_eur(br["interesse_maturato"]),
        ])
    somma_gg = sum(br["giorni_mora"] for br in rate_bk)
    somma_int = sum(br["interesse_maturato"] for br in rate_bk)
    capitale_totale = inp["importo_rata"] * len(rate_bk)
    rows.append([
        "TOT", "—", _fmt_eur(capitale_totale),
        str(somma_gg), _fmt_eur(somma_int),
    ])
    tbl = Table(rows, colWidths=[12 * mm, 30 * mm, 35 * mm, 28 * mm, 35 * mm])
    style = _stile_tabella_base()
    style.add("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fff3e0"))
    style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
    style.add("FONTSIZE", (0, 0), (-1, -1), 8)
    tbl.setStyle(style)

    gg_medi = somma_gg / len(rate_bk)
    giacenza_media = capitale_totale * inp["tasso_mora"] * gg_medi / 365
    nota_giacenza = (
        f"Verifica equivalente — giacenza media: giorni medi di ritardo = "
        f"<b>{gg_medi:.1f}</b> (~{gg_medi/30:.1f} mesi). Capitale totale × "
        f"Tasso × Giorni medi / 365 = {_fmt_eur(capitale_totale)} × "
        f"{_fmt_pct(inp['tasso_mora'])} × {gg_medi:.1f} / 365 = "
        f"<b>{_fmt_eur(giacenza_media)}</b> (coincide con la somma rata "
        f"per rata)."
    )
    return [
        PageBreak(),
        Paragraph("5b. Scomposizione rata per rata (Fase 1)", stili["h2"]),
        Paragraph(
            "Il software <b>itera rata per rata</b>: per ciascuna applica il "
            "tasso di mora sull'importo della <i>singola</i> rata, per i "
            "<i>giorni esatti</i> di ritardo (dalla scadenza della rata alla "
            "data di decadenza). La somma dei contributi è matematicamente "
            "equivalente alla formula della <i>giacenza media</i>.",
            stili["body"]
        ),
        Spacer(1, 4),
        tbl,
        Spacer(1, 4),
        Paragraph(nota_giacenza, stili["caption"]),
    ]


def _sezione_piano_ammortamento(stili, d):
    """Sezione opzionale: piano di ammortamento ricostruito.

    Mostrata solo se il chiamante passa report_data['piano_ammortamento']
    (lista di dict dalla funzione genera_piano_ammortamento). Per piani
    lunghi (>50 rate), mostra la prima e l'ultima rata + tutte le rate
    insolute, per non rendere il PDF eccessivamente voluminoso.
    """
    piano = d.get("piano_ammortamento")
    if not piano:
        return []

    insolute_ids = {r["num_rata_piano"] for r in (
        d["calcolo"]["risultato"]["dettaglio"]
         .get("FASE_1_rate", {}).get("rate_breakdown", [])
        if d["calcolo"]["risultato"]["dettaglio"]
         .get("FASE_1_rate", {}).get("usa_piano_ammortamento", False)
        else []
    )}

    # Filtro intelligente per piani molto lunghi
    if len(piano) > 50 and insolute_ids:
        ids_da_mostrare = set([1, len(piano)]) | insolute_ids
        # estensione 2 rate prima/dopo le insolute per contesto
        for ri in list(insolute_ids):
            ids_da_mostrare.update({ri - 1, ri - 2, ri + 1, ri + 2})
        ids_da_mostrare = {i for i in ids_da_mostrare if 1 <= i <= len(piano)}
        rate_da_mostrare = [
            r for r in piano if r["num_rata"] in ids_da_mostrare
        ]
        nota_filtro = (
            f"Mostriamo le rate insolute (evidenziate) + 2 rate di contesto "
            f"prima/dopo + prima e ultima del piano. Piano completo: "
            f"{len(piano)} rate."
        )
    else:
        rate_da_mostrare = piano
        nota_filtro = f"Piano completo: {len(piano)} rate."

    rows = [["#", "Scadenza", "Q. Int.", "Q. Cap.", "Rata", "Cap. residuo", "Ins."]]
    for r in rate_da_mostrare:
        is_ins = r["num_rata"] in insolute_ids
        rows.append([
            str(r["num_rata"]),
            _fmt_data(r["data_scadenza"]),
            _fmt_eur(r["quota_interessi"]),
            _fmt_eur(r["quota_capitale"]),
            _fmt_eur(r["importo_rata"]),
            _fmt_eur(r["capitale_residuo"]),
            "X" if is_ins else "",
        ])
    tbl = Table(rows, colWidths=[12 * mm, 22 * mm, 25 * mm,
                                 25 * mm, 25 * mm, 30 * mm, 10 * mm])
    style = _stile_tabella_base()
    style.add("FONTSIZE", (0, 0), (-1, -1), 7)
    # Evidenzia le rate insolute con sfondo rosato
    for idx, r in enumerate(rate_da_mostrare, start=1):
        if r["num_rata"] in insolute_ids:
            style.add("BACKGROUND", (0, idx), (-1, idx),
                      colors.HexColor("#ffe6e6"))
    tbl.setStyle(style)

    return [
        PageBreak(),
        Paragraph(
            "9. Piano di Ammortamento Ricostruito",
            stili["h2"]
        ),
        Paragraph(
            "Piano di ammortamento alla francese ricostruito dai parametri "
            "del mutuo originario. Le righe con <b>X</b> (sfondo rosato) "
            "sono le rate insolute intercettate nel periodo "
            "<i>prima rata insoluta → decadenza</i>, su cui è stata "
            "calcolata la mora di Fase 1 (sola Quota Capitale).",
            stili["body"]
        ),
        Spacer(1, 4),
        tbl,
        Spacer(1, 4),
        Paragraph(nota_filtro, stili["caption"]),
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
               nota_footer: str = None, stili: dict = None,
               on_page=None) -> bytes:
    """Compone un PDF (header + sezioni + footer), lo cifra, ritorna bytes.

    stili: dizionario di stili (default = tema chiaro _stili()).
    on_page: callback opzionale (canvas, doc) per disegnare lo sfondo pagina
             (usato dal tema dark per il fondo navy).
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
        title=titolo_doc,
        author="MORA / Resolve S.r.l.",
        encrypt=enc,
    )
    stili = stili or _stili()
    elementi = []
    elementi += _sezione_header(stili, titolo_header)
    elementi += sezioni_corpo
    elementi += _sezione_footer(stili, nota_footer)
    if on_page is not None:
        doc.build(elementi, onFirstPage=on_page, onLaterPages=on_page)
    else:
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
    corpo += _sezione_scomposizione_rate(stili, report_data)
    corpo += _sezione_gbv(stili, report_data)
    corpo += _sezione_piano_ammortamento(stili, report_data)
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


# ==========================================================
# API PUBBLICA – Sofferenza / Estratto conto ex art. 50 TUB (TEMA DARK)
# ==========================================================

def genera_report_pdf_sofferenza(report_data: dict, password: str = "") -> bytes:
    """Report della modalità 'Sofferenza / Estratto conto ex art. 50 TUB'.

    Usa il TEMA DARK (navy + oro) per riprodurre i colori del software.

    report_data deve contenere:
      - input (dict): sorte, quota_int, ante_soff, spese,
        data_decorrenza, data_precetto, data_pignoramento,
        data_aggiudicazione, tasso_convenzionale, tasso_mora,
        tasso_pre_desc, tasso_post_desc, base_desc, anno_civile
      - risultato (dict): output di calcola_credito_sofferenza
    """
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    stili = _stili_dark()
    inp = report_data["input"]
    r = report_data["risultato"]
    ipo, chiro = r["ipotecario"], r["chirografario"]

    cell = ParagraphStyle(
        "CellSoffD", parent=getSampleStyleSheet()["Normal"],
        fontSize=8.5, leading=11, textColor=_D_CREMA,
    )

    corpo = []

    # --- 1. Dati di input (voci cristallizzate + date + tassi) ---
    rows_in = [
        ["Parametro", "Valore"],
        ["Sorte capitale (puro)", _fmt_eur(inp["sorte"])],
        ["Quota interessi rate insolute / rateo", _fmt_eur(inp["quota_int"])],
        ["Interessi ante sofferenza", _fmt_eur(inp["ante_soff"])],
        ["Spese come da precetto", _fmt_eur(inp["spese"])],
        ["Decorrenza interessi", _fmt_data(inp["data_decorrenza"])],
        ["Data conteggio precetto (cambio tasso)", _fmt_data(inp["data_precetto"])],
        ["Data pignoramento", _fmt_data(inp["data_pignoramento"])],
        ["Data di aggiudicazione (fine conteggio)", _fmt_data(inp["data_aggiudicazione"])],
        ["Tasso convenzionale / mutuo", _fmt_pct(inp["tasso_convenzionale"])],
        ["Tasso di mora", _fmt_pct(inp["tasso_mora"])],
        ["Tasso PRIMA del precetto", inp["tasso_pre_desc"]],
        ["Tasso DOPO il precetto", inp["tasso_post_desc"]],
        ["Base interessi legali", inp["base_desc"]],
        ["Base giorni", "Anno civile (366 bisestili)" if inp["anno_civile"]
         else "Anno commerciale (365 fisso)"],
    ]
    tbl_in = Table(rows_in, colWidths=[100 * mm, 74 * mm])
    tbl_in.setStyle(_stile_tabella_dark())
    corpo += [
        Paragraph("1. Dati di input (estratto conto a sofferenza)", stili["h2"]),
        tbl_in, Spacer(1, 8),
    ]

    # --- 2. Riepilogo importi (ipo / chiro / totale) ---
    rows_rip = [
        ["Voce", "Importo"],
        ["🏛️  Credito IPOTECARIO", _fmt_eur(ipo["totale"])],
        ["📄  Credito CHIROGRAFARIO", _fmt_eur(chiro["totale"])],
        ["💰  TOTALE del credito", _fmt_eur(r["totale_credito"])],
    ]
    tbl_rip = Table(rows_rip, colWidths=[110 * mm, 64 * mm])
    tbl_rip.setStyle(_stile_tabella_dark(evidenzia_ultima=True))
    corpo += [
        Paragraph("2. Riepilogo del credito", stili["h2"]),
        tbl_rip,
        Paragraph(
            f"Triennio ex art. 2855 c.c. (anno solare): decorre dal "
            f"{_fmt_data(r['inizio_triennio'])} (annata del pignoramento + 2 "
            f"precedenti). Somma intimata a precetto: {_fmt_eur(r['somma_intimata'])}.",
            stili["caption"]
        ),
        Spacer(1, 8),
    ]

    # --- 3. Divisione ex art. 2855 c.c. (periodi calcolati) ---
    rows_per = [["Periodo", "Grado", "Importo"]]
    for p in r["periodi"]:
        grado = "🏛️ ipotecario" if p["grado"] == "ipotecario" else "📄 chirografario"
        desc = (f"<b>{p['nome']}</b><br/>{_fmt_data(p['da'])} → "
                f"{_fmt_data(p['a'])} · {p['tasso_desc']}")
        rows_per.append([Paragraph(desc, cell), grado, _fmt_eur(p["importo"])])
    somma_periodi = sum(p["importo"] for p in r["periodi"])
    rows_per.append(["Totale interessi calcolati", "", _fmt_eur(somma_periodi)])
    tbl_per = Table(rows_per, colWidths=[104 * mm, 34 * mm, 36 * mm])
    tbl_per.setStyle(_stile_tabella_dark(evidenzia_ultima=True))
    corpo += [
        Paragraph("3. Divisione ex art. 2855 c.c. (interessi calcolati)", stili["h2"]),
        tbl_per,
        Paragraph(
            "Pre-triennio → chirografo; triennio garantito → ipotecario; "
            "post-triennio → ipotecario al solo tasso legale + eccedenza "
            "chirografaria (presente solo se l'aggiudicazione cade oltre "
            "l'annata del pignoramento).",
            stili["caption"]
        ),
        Spacer(1, 8),
    ]

    # --- 4. Voci cristallizzate da estratto conto ex art. 50 TUB ---
    rows_ec = [
        ["Voce (grado)", "Importo"],
        ["Sorte capitale — 🏛️ ipotecario", _fmt_eur(ipo["sorte"])],
        ["Spese come da precetto — 🏛️ ipotecario", _fmt_eur(ipo["spese"])],
        ["Quota interessi rate insolute — 📄 chirografario",
         _fmt_eur(chiro["quota_interessi_congelata"])],
        ["Interessi ante sofferenza — 📄 chirografario",
         _fmt_eur(chiro["interessi_ante_sofferenza"])],
    ]
    tbl_ec = Table(rows_ec, colWidths=[124 * mm, 50 * mm])
    tbl_ec.setStyle(_stile_tabella_dark())
    corpo += [
        Paragraph("4. Voci congelate da estratto conto ex art. 50 TUB", stili["h2"]),
        tbl_ec, Spacer(1, 8),
    ]

    # --- 5. Nota anatocismo (leva di contestazione) ---
    ca = r["confronto_anatocismo"]
    if ca["extra"] > 0.01:
        nota = (
            f"⚖️ <b>Punto di contestazione — anatocismo (art. 1283 c.c.).</b><br/>"
            f"Gli interessi legali sono calcolati sulla base "
            f"<b>capitale + interessi scaduti</b> "
            f"({_fmt_eur(ca['legale_capitale_interessi'])}). Sulla sola quota "
            f"capitale sarebbero {_fmt_eur(ca['legale_solo_capitale'])}: "
            f"differenza contestabile di <b>{_fmt_eur(ca['extra'])}</b>."
        )
        corpo += [
            Paragraph("5. Leva di contestazione", stili["h2"]),
            Paragraph(nota, stili["warn_box"]),
        ]

    return _build_pdf(
        titolo_doc="Report MORA – Sofferenza / Estratto conto ex art. 50 TUB",
        titolo_header="🏦 Report Credito da Sofferenza – Art. 2855 c.c.",
        sezioni_corpo=corpo,
        password=password,
        stili=stili,
        on_page=_sfondo_navy,
        nota_footer=(
            "Documento generato da MORA (Resolve S.r.l.) — modalità Sofferenza / "
            "Estratto conto ex art. 50 TUB. Credito cristallizzato secondo la "
            "prassi dei conteggi professionali. I risultati vanno verificati da "
            "un professionista. Il PDF è cifrato: copia e modifica disabilitate."
        ),
    )
