"""
Caricamento e normalizzazione di un piano di ammortamento da file esterno
(CSV o Excel). Restituisce una lista di dict nello stesso formato di
`calcoli.genera_piano_ammortamento`, così le funzioni a valle
(`estrai_rate_insolute_da_piano`, `calcola_mora_unificato`) restano invariate.
"""

from datetime import date, datetime
import io
import re
import unicodedata

import pandas as pd


# ==========================================================
# MAPPATURA NOMI COLONNA (riconoscimento flessibile)
# ==========================================================

def _normalizza_nome(s):
    """Lowercase + rimozione accenti + strip + collapse spazi/underscore."""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[._\-]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


# Mappa nome_normalizzato -> nome_standard
ALIASES = {
    # data_scadenza
    "data scadenza": "data_scadenza",
    "scadenza": "data_scadenza",
    "data": "data_scadenza",
    "data rata": "data_scadenza",
    "data pagamento": "data_scadenza",
    # quota_capitale
    "quota capitale": "quota_capitale",
    "q capitale": "quota_capitale",
    "qc": "quota_capitale",
    "capitale": "quota_capitale",
    "quota cap": "quota_capitale",
    # quota_interessi
    "quota interessi": "quota_interessi",
    "q interessi": "quota_interessi",
    "qi": "quota_interessi",
    "interessi": "quota_interessi",
    "quota int": "quota_interessi",
    # capitale_residuo
    "capitale residuo": "capitale_residuo",
    "residuo": "capitale_residuo",
    "debito residuo": "capitale_residuo",
    # importo_rata
    "importo rata": "importo_rata",
    "rata": "importo_rata",
    "rata totale": "importo_rata",
    "importo": "importo_rata",
    # num_rata
    "num rata": "num_rata",
    "n rata": "num_rata",
    "numero rata": "num_rata",
    "n": "num_rata",
    "numero": "num_rata",
}


def _mappa_colonne(df):
    """Restituisce un nuovo DataFrame con i nomi standard riconosciuti."""
    mapping = {}
    for col in df.columns:
        norm = _normalizza_nome(col)
        std = ALIASES.get(norm)
        if std and std not in mapping.values():
            mapping[col] = std
    return df.rename(columns=mapping)


# ==========================================================
# PARSER PRINCIPALE
# ==========================================================

def carica_piano_da_dataframe(df):
    """
    Normalizza un DataFrame in lista di dict.

    Richiesti: data_scadenza + (quota_capitale OR quota_interessi).
    Se manca importo_rata viene calcolato come quota_capitale + quota_interessi.
    Se manca capitale_residuo viene calcolato a partire dalla somma cumulativa
    delle quote capitale (assumendo che la prima rata abbia residuo = somma
    totale delle quote capitale).
    Se manca num_rata viene assegnato in sequenza.

    Solleva ValueError con messaggio utente-friendly per dati non conformi.
    """
    if df is None or df.empty:
        raise ValueError("Il file è vuoto.")

    df = _mappa_colonne(df)

    if "data_scadenza" not in df.columns:
        raise ValueError(
            "Colonna 'Data Scadenza' non trovata. "
            "Rinomina nel file la colonna delle date di scadenza in 'Data Scadenza'."
        )
    if "quota_capitale" not in df.columns and "quota_interessi" not in df.columns:
        raise ValueError(
            "Servono almeno 'Quota Capitale' e/o 'Quota Interessi'. "
            "Verifica i nomi delle colonne nel file."
        )

    # --- Parsing date (formato italiano dd/mm/yyyy come default) ---
    try:
        df["data_scadenza"] = pd.to_datetime(
            df["data_scadenza"], dayfirst=True, errors="raise"
        ).dt.date
    except Exception as e:
        raise ValueError(
            "Impossibile interpretare le date di scadenza. "
            "Usa il formato gg/mm/aaaa. Dettaglio: " + str(e)
        )

    # --- Parsing numerici ---
    # Strategia: se la stringa contiene una virgola, è formato italiano
    # (punto=migliaia, virgola=decimali). Altrimenti formato Python/US
    # (punto=decimali, niente migliaia). Così "1.234,56" → 1234.56 ma
    # "800.0" → 800.0.
    def _to_float(x):
        if pd.isna(x):
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).replace("€", "").strip()
        if not s:
            return None
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None

    for col in ("quota_capitale", "quota_interessi",
                "capitale_residuo", "importo_rata"):
        if col in df.columns:
            df[col] = df[col].map(_to_float)

    # --- Default per colonne mancanti ---
    if "quota_capitale" not in df.columns:
        df["quota_capitale"] = 0.0
    if "quota_interessi" not in df.columns:
        df["quota_interessi"] = 0.0
    df["quota_capitale"] = df["quota_capitale"].fillna(0.0)
    df["quota_interessi"] = df["quota_interessi"].fillna(0.0)

    if "importo_rata" not in df.columns or df["importo_rata"].isna().any():
        df["importo_rata"] = df["quota_capitale"] + df["quota_interessi"]

    if "capitale_residuo" not in df.columns:
        somma_qc = df["quota_capitale"].sum()
        residui = []
        rimanente = somma_qc
        for qc in df["quota_capitale"]:
            rimanente -= qc
            residui.append(max(rimanente, 0.0))
        df["capitale_residuo"] = residui

    if "num_rata" not in df.columns:
        df["num_rata"] = range(1, len(df) + 1)
    else:
        df["num_rata"] = pd.to_numeric(df["num_rata"], errors="coerce").fillna(
            pd.Series(range(1, len(df) + 1))
        ).astype(int)

    # --- Ordino per data crescente (best-effort) ---
    df = df.sort_values("data_scadenza").reset_index(drop=True)

    piano = []
    for _, r in df.iterrows():
        piano.append({
            "num_rata": int(r["num_rata"]),
            "data_scadenza": r["data_scadenza"],
            "quota_interessi": float(r["quota_interessi"]),
            "quota_capitale": float(r["quota_capitale"]),
            "importo_rata": float(r["importo_rata"]),
            "capitale_residuo": float(r["capitale_residuo"]),
        })
    return piano


def _riconosci_header(header_row):
    """
    Da una lista di stringhe (intestazione di una tabella PDF) restituisce
    un dict {indice_colonna: nome_standard} per le colonne riconosciute.
    Ritorna {} se non c'è nessun match.
    """
    risultato = {}
    for idx, cell in enumerate(header_row or []):
        if cell is None:
            continue
        # PDF spesso ha header su 2 righe ("Quota\nCapitale"): collasso \n
        cell_clean = re.sub(r"\s+", " ", str(cell)).strip()
        norm = _normalizza_nome(cell_clean)
        std = ALIASES.get(norm)
        if std and std not in risultato.values():
            risultato[idx] = std
    return risultato


def carica_piano_da_pdf(file_obj):
    """
    Estrae il piano di ammortamento da un file PDF "vettoriale" (cioè
    generato dal gestionale della banca, non scansionato).

    Strategia:
      1) Apre il PDF con pdfplumber.
      2) Per ogni pagina estrae le tabelle (page.extract_tables()).
      3) Riconosce la prima riga di ogni tabella come intestazione e
         verifica che contenga le colonne richieste (data + almeno una
         tra quota_capitale/quota_interessi).
      4) Concatena le righe dati di tutte le tabelle riconosciute.
      5) Passa il DataFrame al parser comune.

    Solleva ValueError in caso di PDF scansionato, layout non tabellare
    o impossibilità di riconoscere colonne note.
    """
    try:
        import pdfplumber
    except ImportError as e:
        raise ValueError(
            "Libreria pdfplumber non installata. "
            "Aggiungi 'pdfplumber' a requirements.txt."
        ) from e

    raw = file_obj.read() if hasattr(file_obj, "read") else file_obj
    if not raw:
        raise ValueError("Il PDF è vuoto.")

    righe_raccolte = []
    nomi_colonne_standard = None

    try:
        pdf_ctx = pdfplumber.open(io.BytesIO(raw))
    except Exception as e:
        raise ValueError(
            f"Impossibile aprire il PDF (file corrotto o non valido): {e}"
        )

    with pdf_ctx as pdf:
        for pagina in pdf.pages:
            tabelle = pagina.extract_tables() or []
            for tabella in tabelle:
                if not tabella or len(tabella) < 2:
                    continue
                header = tabella[0]
                mapping = _riconosci_header(header)
                # Servono almeno data + (capitale o interessi)
                cols = set(mapping.values())
                if "data_scadenza" not in cols:
                    continue
                if "quota_capitale" not in cols and "quota_interessi" not in cols:
                    continue
                # Memorizzo i nomi standard nell'ordine
                indici_ordinati = sorted(mapping.keys())
                nomi_colonne_standard = [mapping[i] for i in indici_ordinati]
                # Aggiungo le righe dati (salto la prima = header)
                for riga in tabella[1:]:
                    if riga is None:
                        continue
                    # Salta righe di header ripetuto (matching > 50% nomi colonna)
                    norm_celle = [
                        _normalizza_nome(c) if c else ""
                        for c in riga
                    ]
                    matches = sum(1 for nc in norm_celle if nc in ALIASES)
                    if matches >= max(2, len(mapping) // 2):
                        continue
                    valori = [
                        riga[i] if i < len(riga) else None
                        for i in indici_ordinati
                    ]
                    # Salta righe vuote / totali
                    if all(v is None or str(v).strip() == "" for v in valori):
                        continue
                    righe_raccolte.append(valori)

    if not righe_raccolte or not nomi_colonne_standard:
        raise ValueError(
            "Nessuna tabella riconoscibile trovata nel PDF. "
            "Verifica che il PDF NON sia una scansione (servirebbe OCR) "
            "e che le intestazioni delle colonne includano almeno "
            "'Data Scadenza' e 'Quota Capitale' (o 'Quota Interessi'). "
            "In alternativa, esporta il piano in CSV/Excel dalla banca."
        )

    df = pd.DataFrame(righe_raccolte, columns=nomi_colonne_standard)
    # Filtro righe in cui data_scadenza non è interpretabile (footer/note)
    df["data_scadenza"] = df["data_scadenza"].astype(str).str.strip()
    df = df[df["data_scadenza"].str.match(
        r"^\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}$", na=False
    )].reset_index(drop=True)
    if df.empty:
        raise ValueError(
            "Tabelle trovate ma nessuna riga con date valide. "
            "Verifica il formato del PDF (atteso: dd/mm/yyyy)."
        )
    return carica_piano_da_dataframe(df)


def carica_piano_da_file(uploaded_file):
    """
    Riceve un file-like (es. da st.file_uploader) e ritorna il piano
    normalizzato. Riconosce CSV (.csv), Excel (.xlsx, .xls), PDF (.pdf).
    """
    name = (getattr(uploaded_file, "name", "") or "").lower()
    if name.endswith(".pdf"):
        return carica_piano_da_pdf(uploaded_file)
    if name.endswith(".csv"):
        # Provo prima ';' (separatore italiano), poi ','
        raw = uploaded_file.read()
        for sep in (";", ","):
            try:
                df = pd.read_csv(io.BytesIO(raw), sep=sep)
                if df.shape[1] >= 2:
                    return carica_piano_da_dataframe(df)
            except Exception:
                continue
        raise ValueError(
            "Impossibile leggere il CSV. Verifica il separatore "
            "(punto e virgola o virgola) e l'intestazione delle colonne."
        )
    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
        return carica_piano_da_dataframe(df)
    raise ValueError(
        "Formato file non supportato. Carica PDF, CSV o Excel (.xlsx)."
    )
