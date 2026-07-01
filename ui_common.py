"""
Helper condivisi tra i moduli UI (sidebar + tab).

- mappa_autofill_a_widget: converte i dati estratti dall'autofill nelle
  key concrete dei widget Streamlit (con eventuali conversioni).
- ETICHETTE_CAMPI: nomi user-friendly dei campi per il feedback.
- valori_esempio: caso realistico per il pulsante "Carica esempio".
"""

from datetime import date


def mappa_autofill_a_widget(dati_estratti):
    """Da dict dell'autofill → dict {widget_key: valore_pronto_per_widget}."""
    out = {}
    d = dati_estratti or {}

    if d.get("tasso_mora") is not None:
        out["sb_tasso_mora"] = float(d["tasso_mora"]) * 100
    if d.get("data_stipula") is not None:
        out["sb_data_stipula"] = d["data_stipula"]
    if d.get("data_pignoramento") is not None:
        out["sb_data_pignoramento"] = d["data_pignoramento"]

    if d.get("importo_rata") is not None:
        out["t1_importo_rata"] = float(d["importo_rata"])
    if d.get("data_prima_rata_insoluta") is not None:
        out["t1_data_prima_rata"] = d["data_prima_rata_insoluta"]
    if d.get("frequenza_rate") is not None:
        out["t1_frequenza"] = d["frequenza_rate"]
    if d.get("capitale_residuo") is not None:
        out["t1_capitale_residuo"] = float(d["capitale_residuo"])
    if d.get("data_decadenza_effettiva") is not None:
        out["t1_data_decadenza"] = d["data_decadenza_effettiva"]
    if d.get("is_caso_A") is not None:
        out["sb_caso"] = (
            "CASO A – Lettera DBT" if d["is_caso_A"]
            else "CASO B – Notifica Precetto"
        )
    if d.get("gbv_dichiarato") is not None:
        out["t1_gbv"] = float(d["gbv_dichiarato"])
    if d.get("data_attualizzazione_gbv") is not None:
        out["t1_data_att_gbv"] = d["data_attualizzazione_gbv"]

    # Sezione piano di ammortamento (ricostruzione algoritmica)
    if d.get("capitale_originario") is not None:
        out["t1_capitale_originario"] = float(d["capitale_originario"])
    if d.get("data_erogazione") is not None:
        out["t1_data_erogazione"] = d["data_erogazione"]
    if d.get("durata_anni") is not None:
        out["t1_durata_anni"] = int(d["durata_anni"])
    if d.get("tan") is not None:
        out["t1_tan"] = float(d["tan"]) * 100

    return out


# Etichette user-friendly per il feedback UI
ETICHETTE_CAMPI = {
    "sb_tasso_mora": "Tasso di mora",
    "sb_data_stipula": "Data stipula mutuo",
    "sb_data_pignoramento": "Data pignoramento",
    "sb_caso": "Modalità (Caso A/B)",
    "t1_importo_rata": "Importo rata",
    "t1_data_prima_rata": "Data prima rata insoluta",
    "t1_frequenza": "Frequenza rate",
    "t1_capitale_residuo": "Capitale residuo",
    "t1_data_decadenza": "Data decadenza / precetto",
    "t1_gbv": "GBV dichiarato",
    "t1_data_att_gbv": "Data attualizzazione GBV",
    "t1_capitale_originario": "Capitale originario erogato",
    "t1_data_erogazione": "Data erogazione mutuo",
    "t1_durata_anni": "Durata mutuo (anni)",
    "t1_tan": "TAN mutuo",
}


def valori_esempio():
    """Caso realistico e coerente per la demo (precompila i campi principali)."""
    return {
        "sb_tasso_mora": 5.70,
        "sb_data_stipula": date(2018, 6, 15),
        "sb_data_pignoramento": date(2023, 9, 10),
        "sb_data_fine": date(2024, 6, 30),
        "sb_caso": "CASO A – Lettera DBT",
        "sb_metodo_triennio": "Anno solare (prassi conteggi reali)",
        "t1_importo_rata": 800.0,
        "t1_data_prima_rata": date(2021, 3, 1),
        "t1_frequenza": "Mensile",
        "t1_capitale_residuo": 100000.0,
        "t1_data_decadenza": date(2022, 1, 20),
        "t1_gbv": 0.0,
    }
