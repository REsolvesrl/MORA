"""
Magic Autofill: estrazione automatica dei dati da PDF legali (contratti
di mutuo, lettere DBT, atti di precetto) per compilare i campi dell'UI.

Due strategie:
- LLM (Anthropic Claude Haiku) se la chiave API è disponibile:
  massima precisione, gestisce documenti "casinari".
- Fallback regex/euristica: precisione ridotta, funziona su testi
  puliti con formulazioni standard.

Sicurezza: nella modalità LLM, il testo dei PDF viene inviato al server
Anthropic. La UI deve avvisare l'utente in modo esplicito.
"""

from datetime import date, datetime
import io
import json
import os
import re


# ==========================================================
# 1) ESTRAZIONE TESTO DAI PDF
# ==========================================================

# Soglia minima di caratteri per considerare "riuscita" l'estrazione
# di pdfplumber (sotto la soglia scatta il fallback OCR).
_MIN_CHAR_PLUMBER = 100


def estrai_testo_con_ocr(pdf_bytes, lingua="ita+eng", dpi=300):
    """
    OCR di un PDF scansionato: converte ogni pagina in immagine
    (pdf2image + poppler) e riconosce il testo con Tesseract.

    Solleva RuntimeError con messaggio utile se Tesseract o poppler
    non sono installati sul sistema (Streamlit Cloud richiede
    packages.txt).
    """
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except ImportError as e:
        raise RuntimeError(
            "Librerie OCR non installate. Aggiungi 'pytesseract' e "
            "'pdf2image' a requirements.txt."
        ) from e

    try:
        immagini = convert_from_bytes(pdf_bytes, dpi=dpi)
    except Exception as e:
        raise RuntimeError(
            "Impossibile convertire il PDF in immagini. "
            "Su Streamlit Cloud verifica che 'poppler-utils' sia in "
            f"packages.txt. Dettaglio: {e}"
        )

    testo_pagine = []
    for immagine in immagini:
        try:
            t = pytesseract.image_to_string(immagine, lang=lingua)
        except pytesseract.TesseractNotFoundError as e:
            raise RuntimeError(
                "Motore Tesseract non installato sul sistema. "
                "Su Streamlit Cloud aggiungi 'tesseract-ocr' e "
                "'tesseract-ocr-ita' a packages.txt."
            ) from e
        except Exception as e:
            # Se una pagina fallisce, continuo con le altre
            print(f"[autofill/ocr] Pagina fallita: {e}")
            continue
        if t and t.strip():
            testo_pagine.append(t)

    return "\n\n".join(testo_pagine)


def estrai_testo_da_pdf(file_obj, ocr_fallback=True):
    """
    Estrae il testo di un PDF.

    Strategia:
      1) Prima tenta con pdfplumber (veloce, funziona su PDF vettoriali).
      2) Se pdfplumber restituisce poco/nessun testo (< _MIN_CHAR_PLUMBER)
         e ocr_fallback=True, fa fallback su OCR Tesseract.

    Ritorna una tupla `(testo, metodo)`:
      - metodo = "vettoriale" (estratto da pdfplumber)
      - metodo = "ocr"        (estratto da Tesseract)
      - metodo = "vuoto"      (nessun testo estraibile, OCR non disponibile)
      - metodo = "errore_ocr" (l'OCR ha fallito, dettaglio in testo)
    """
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError(
            "pdfplumber non installato. Aggiungilo a requirements.txt."
        )
    raw = file_obj.read() if hasattr(file_obj, "read") else file_obj
    if not raw:
        return "", "vuoto"

    # --- Tentativo 1: pdfplumber (veloce) ---
    testo_plumber = ""
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            parti = []
            for pagina in pdf.pages:
                t = pagina.extract_text() or ""
                if t.strip():
                    parti.append(t)
            testo_plumber = "\n\n".join(parti)
    except Exception as e:
        print(f"[autofill] pdfplumber ha fallito: {e}")

    if len(testo_plumber.strip()) >= _MIN_CHAR_PLUMBER:
        return testo_plumber, "vettoriale"

    if not ocr_fallback:
        return testo_plumber, ("vuoto" if not testo_plumber.strip() else "vettoriale")

    # --- Tentativo 2: OCR Tesseract ---
    try:
        testo_ocr = estrai_testo_con_ocr(raw)
        if testo_ocr.strip():
            return testo_ocr, "ocr"
        return testo_plumber, "vuoto"
    except RuntimeError as e:
        # OCR non disponibile o fallito: ritorno quel poco che avevo + errore
        return testo_plumber or str(e), "errore_ocr"


# ==========================================================
# 2) SCHEMA DI OUTPUT
# ==========================================================

# Chiavi restituite dall'estrazione. None se non trovato.
SCHEMA_CHIAVI = [
    "capitale_originario",         # float €
    "data_erogazione",             # date
    "durata_anni",                 # int
    "tan",                         # float (0.045 = 4,5%)
    "data_stipula",                # date
    "tasso_mora",                  # float (0.08 = 8%)
    "data_pignoramento",           # date
    "data_prima_rata_insoluta",    # date
    "frequenza_rate",              # "Mensile" | "Trimestrale" | "Semestrale"
    "importo_rata",                # float €
    "capitale_residuo",            # float €
    "data_decadenza_effettiva",    # date (DBT o Precetto)
    "is_caso_A",                   # bool: True = DBT, False = Precetto
    "gbv_dichiarato",              # float € (opz.)
    "data_attualizzazione_gbv",    # date (opz.)
]


def _dict_vuoto():
    return {k: None for k in SCHEMA_CHIAVI}


def _to_date(s):
    """Parsing sicuro di una data ISO ('YYYY-MM-DD'). Ritorna None se invalida."""
    if not s:
        return None
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    if isinstance(s, datetime):
        return s.date()
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _to_float(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace("€", "").strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _normalizza_output(d):
    """Assicura che tutte le chiavi siano presenti e con tipi corretti."""
    out = _dict_vuoto()
    if not isinstance(d, dict):
        return out
    for k in SCHEMA_CHIAVI:
        v = d.get(k)
        if k.startswith("data_"):
            out[k] = _to_date(v)
        elif k == "durata_anni":
            try:
                out[k] = int(v) if v is not None else None
            except (ValueError, TypeError):
                out[k] = None
        elif k == "frequenza_rate":
            if isinstance(v, str) and v.strip().capitalize() in (
                "Mensile", "Trimestrale", "Semestrale"
            ):
                out[k] = v.strip().capitalize()
            else:
                out[k] = None
        elif k == "is_caso_A":
            out[k] = bool(v) if v is not None else None
        else:
            out[k] = _to_float(v)
    return out


# ==========================================================
# 3) ESTRAZIONE VIA CLAUDE (Anthropic API)
# ==========================================================

_PROMPT_SISTEMA = (
    "Sei un assistente specializzato nell'analisi di documenti legali e "
    "bancari italiani (contratti di mutuo, lettere di decadenza dal "
    "beneficio del termine, atti di precetto). Il tuo compito è estrarre "
    "dati strutturati dal testo fornito e restituirli in formato JSON.\n\n"
    "IMPORTANTI REGOLE:\n"
    "- Rispondi SOLO con un oggetto JSON, nessun altro testo prima o dopo.\n"
    "- Se un dato non è chiaramente presente nel testo, usa null.\n"
    "- Le date devono essere in formato ISO 'YYYY-MM-DD'.\n"
    "- I tassi percentuali devono essere numeri decimali (es. 8.00 = 0.08).\n"
    "- Gli importi devono essere numeri float senza simboli/separatori.\n"
    "- La frequenza rate deve essere una tra 'Mensile', 'Trimestrale', "
    "'Semestrale'.\n"
    "- Distingui il TAN del mutuo dal tasso di mora (di solito diverso).\n"
    "- Per is_caso_A: True se il testo parla principalmente di Lettera DBT "
    "(decadenza dal beneficio del termine), False se di Atto di Precetto."
)


def _prompt_utente(testo):
    return (
        "Analizza il seguente testo estratto da uno o più documenti legali "
        "(mutuo, DBT, precetto) e restituisci un JSON con queste chiavi:\n\n"
        "- capitale_originario (importo del mutuo erogato)\n"
        "- data_erogazione (data di erogazione del mutuo)\n"
        "- durata_anni (durata totale del mutuo in anni)\n"
        "- tan (Tasso Annuo Nominale del mutuo, decimale)\n"
        "- data_stipula (data del contratto di mutuo)\n"
        "- tasso_mora (tasso di mora annuo, decimale)\n"
        "- data_pignoramento (data del pignoramento, se presente)\n"
        "- data_prima_rata_insoluta (data della prima rata non pagata)\n"
        "- frequenza_rate ('Mensile' | 'Trimestrale' | 'Semestrale')\n"
        "- importo_rata (importo di una singola rata)\n"
        "- capitale_residuo (capitale residuo alla data di decadenza)\n"
        "- data_decadenza_effettiva (data DBT o data notifica precetto)\n"
        "- is_caso_A (true se DBT, false se precetto)\n"
        "- gbv_dichiarato (importo totale richiesto dalla cedente)\n"
        "- data_attualizzazione_gbv (data a cui il creditore ha "
        "conteggiato gli interessi nel GBV)\n\n"
        "TESTO DA ANALIZZARE:\n"
        f"---\n{testo}\n---\n\n"
        "Restituisci SOLO il JSON, senza spiegazioni."
    )


def _estrai_via_claude(testo, api_key):
    """Chiama Claude Haiku e ritorna il dict estratto."""
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        system=_PROMPT_SISTEMA,
        messages=[{"role": "user", "content": _prompt_utente(testo)}],
    )
    contenuto = ""
    for blocco in msg.content:
        if getattr(blocco, "type", None) == "text":
            contenuto += blocco.text
    # Il modello a volte include codeblock ```json ... ```: pulisco
    contenuto = contenuto.strip()
    if contenuto.startswith("```"):
        contenuto = re.sub(r"^```(?:json)?\s*", "", contenuto)
        contenuto = re.sub(r"\s*```$", "", contenuto)
    return json.loads(contenuto)


# ==========================================================
# 4) FALLBACK REGEX / EURISTICO
# ==========================================================

# Pattern base
_DATA_IT = r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})"
_IMPORTO = r"(?:€\s*)?([\d]{1,3}(?:[\.\s]\d{3})*(?:,\d{2})?)"
_PCT = r"(\d+(?:[.,]\d+)?)\s*%"


def _parse_data_it(match):
    """Da un match _DATA_IT ritorna date o None."""
    try:
        g, m, a = int(match.group(1)), int(match.group(2)), match.group(3)
        a = int(a)
        if a < 100:
            a += 2000 if a < 50 else 1900
        return date(a, m, g)
    except Exception:
        return None


def _cerca_data_vicino(testo, keyword, finestra=200):
    """Cerca la prima data italiana entro N caratteri dopo la keyword."""
    m_kw = re.search(keyword, testo, re.IGNORECASE)
    if not m_kw:
        return None
    inizio = m_kw.end()
    fine = min(len(testo), inizio + finestra)
    contesto = testo[inizio:fine]
    m_data = re.search(_DATA_IT, contesto)
    return _parse_data_it(m_data) if m_data else None


def _cerca_importo_vicino(testo, keyword, finestra=200):
    """Cerca un importo entro `finestra` caratteri intorno (dopo O prima)
    della keyword. Tipicamente la keyword segue l'importo negli atti di
    precetto ('€ 145.230,50 (GBV)'), quindi cerchiamo su entrambi i lati.
    """
    m_kw = re.search(keyword, testo, re.IGNORECASE)
    if not m_kw:
        return None
    # Prima cerca dopo
    dopo = testo[m_kw.end():m_kw.end() + finestra]
    m_imp = re.search(_IMPORTO, dopo)
    # Filtro: scarta match troppo corti (es. "15" da "15/06/2018") se
    # non c'è né virgola decimale né separatore migliaia
    if m_imp and ("," in m_imp.group(1) or "." in m_imp.group(1)
                  or len(m_imp.group(1)) >= 4):
        return _to_float(m_imp.group(1))
    # Fallback: cerca prima
    inizio_finestra = max(0, m_kw.start() - finestra)
    prima = testo[inizio_finestra:m_kw.start()]
    m_prima = re.findall(_IMPORTO, prima)
    if m_prima:
        # Prendo l'importo più vicino alla keyword (l'ultimo trovato)
        candidato = m_prima[-1]
        if ("," in candidato or "." in candidato or len(candidato) >= 4):
            return _to_float(candidato)
    return _to_float(m_imp.group(1)) if m_imp else None


def _cerca_pct_vicino(testo, keyword, finestra=200):
    m_kw = re.search(keyword, testo, re.IGNORECASE)
    if not m_kw:
        return None
    contesto = testo[m_kw.end():m_kw.end() + finestra]
    m_pct = re.search(_PCT, contesto)
    if not m_pct:
        return None
    valore = _to_float(m_pct.group(1))
    return valore / 100 if valore else None


def _estrai_via_regex(testo):
    """Fallback best-effort. Precisione limitata: cerca pattern comuni."""
    out = _dict_vuoto()

    # capitale
    out["capitale_originario"] = _cerca_importo_vicino(
        testo, r"(?:capitale\s+(?:originario|erogato|mutuato)|somma\s+mutuata)"
    )
    out["capitale_residuo"] = _cerca_importo_vicino(
        testo, r"capitale\s+residuo"
    )
    out["importo_rata"] = _cerca_importo_vicino(
        testo, r"(?:importo\s+della?\s+rata|rata\s+mensile|canone)"
    )
    out["gbv_dichiarato"] = _cerca_importo_vicino(
        testo, r"(?:gross\s+book\s+value|GBV|totale\s+dovuto|somma\s+intimata)"
    )

    # tassi
    out["tan"] = _cerca_pct_vicino(
        testo, r"(?:tasso\s+annuo\s+nominale|TAN)"
    )
    out["tasso_mora"] = _cerca_pct_vicino(
        testo, r"(?:tasso\s+di\s+mora|interessi\s+moratori|mora)"
    )

    # date
    out["data_erogazione"] = _cerca_data_vicino(
        testo, r"(?:data\s+di\s+erogazione|erogazione\s+del\s+mutuo)"
    )
    out["data_stipula"] = _cerca_data_vicino(
        testo, r"(?:stipulato|data\s+(?:di\s+)?stipul[ao]|del\s+contratto)"
    )
    out["data_pignoramento"] = _cerca_data_vicino(
        testo, r"pignoramento"
    )
    out["data_prima_rata_insoluta"] = _cerca_data_vicino(
        testo, r"(?:prima\s+rata\s+(?:insoluta|non\s+pagata|scaduta)"
              r"|dal\s+\d)"
    )
    out["data_decadenza_effettiva"] = _cerca_data_vicino(
        testo, r"(?:decadenza\s+dal\s+beneficio|beneficio\s+del\s+termine"
              r"|notific(?:a|ato)\s+.*?precett|atto\s+di\s+precetto)"
    )
    out["data_attualizzazione_gbv"] = _cerca_data_vicino(
        testo, r"(?:conteggiat[oi]\s+al|calcolati\s+al|attualizzat[oi]\s+al)"
    )

    # durata
    m_dur = re.search(
        r"durata\s+(?:di\s+)?(\d{1,3})\s+(?:ann[io]|mesi)",
        testo, re.IGNORECASE,
    )
    if m_dur:
        anni_o_mesi = int(m_dur.group(1))
        # Se la parola è "mesi", converto
        if re.search(r"mesi", m_dur.group(0), re.IGNORECASE):
            out["durata_anni"] = anni_o_mesi // 12
        else:
            out["durata_anni"] = anni_o_mesi

    # frequenza
    if re.search(r"rate?\s+mensil", testo, re.IGNORECASE):
        out["frequenza_rate"] = "Mensile"
    elif re.search(r"rate?\s+trimestral", testo, re.IGNORECASE):
        out["frequenza_rate"] = "Trimestrale"
    elif re.search(r"rate?\s+semestral", testo, re.IGNORECASE):
        out["frequenza_rate"] = "Semestrale"

    # is_caso_A: euristica basata sulla presenza di parole chiave
    ha_dbt = bool(re.search(
        r"(?:decadenza\s+dal\s+beneficio\s+del\s+termine|DBT)",
        testo, re.IGNORECASE
    ))
    ha_precetto = bool(re.search(r"atto\s+di\s+precetto", testo, re.IGNORECASE))
    if ha_dbt and not ha_precetto:
        out["is_caso_A"] = True
    elif ha_precetto and not ha_dbt:
        out["is_caso_A"] = False
    # Se entrambi o nessuno → None (l'utente sceglie manualmente)

    return out


# ==========================================================
# 5) API PUBBLICA
# ==========================================================

def _leggi_api_key(nome, streamlit_secrets=None):
    """Cerca la key prima in st.secrets, poi in os.environ."""
    if streamlit_secrets is not None:
        try:
            if nome in streamlit_secrets:
                return streamlit_secrets[nome]
        except Exception:
            pass
    return os.environ.get(nome)


def extract_data_from_legal_text(testo, streamlit_secrets=None):
    """
    Estrae i dati dal testo. Usa Claude Haiku se disponibile, altrimenti
    fallback regex.

    Ritorna:
      (dati_dict, modalita_usata) dove modalita_usata è
      "llm-anthropic" oppure "regex-fallback".
    """
    testo = (testo or "").strip()
    if not testo:
        return _dict_vuoto(), "regex-fallback"

    api_key = _leggi_api_key("ANTHROPIC_API_KEY", streamlit_secrets)
    if api_key:
        try:
            grezzo = _estrai_via_claude(testo, api_key)
            return _normalizza_output(grezzo), "llm-anthropic"
        except Exception as e:
            # Fallback silenzioso al regex se l'LLM fallisce
            print(f"[autofill] Chiamata LLM fallita, fallback regex: {e}")

    grezzo = _estrai_via_regex(testo)
    return _normalizza_output(grezzo), "regex-fallback"
