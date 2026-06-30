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


def carica_piano_da_file(uploaded_file):
    """
    Riceve un file-like (es. da st.file_uploader) e ritorna il piano
    normalizzato. Riconosce CSV (.csv) ed Excel (.xlsx, .xls).
    Per i PDF restituisce un errore esplicito.
    """
    name = (getattr(uploaded_file, "name", "") or "").lower()
    if name.endswith(".pdf"):
        raise ValueError(
            "Estrazione automatica da PDF non supportata in questa versione. "
            "Esporta il piano di ammortamento in CSV o Excel dalla tua banca "
            "per garantire la massima precisione."
        )
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
        "Formato file non supportato. Carica CSV, Excel (.xlsx) o "
        "esporta da PDF e ricarica come CSV/Excel."
    )
