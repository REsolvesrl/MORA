"""
Logica pura di calcolo per MORA.

Tutte le funzioni in questo modulo sono indipendenti da Streamlit
e possono essere importate / testate in isolamento.
"""

from datetime import date
from dateutil.relativedelta import relativedelta

# ==========================================================
# 1. TABELLE DI CONFIGURAZIONE
# ==========================================================

# Tassi legali ex art. 1284 c.c. (variano ogni 1° gennaio)
TASSI_LEGALI = {
    2005: 0.0250, 2006: 0.0250, 2007: 0.0250, 2008: 0.0300, 2009: 0.0300,
    2010: 0.0100, 2011: 0.0150, 2012: 0.0250, 2013: 0.0250, 2014: 0.0100,
    2015: 0.0050, 2016: 0.0020, 2017: 0.0010, 2018: 0.0030, 2019: 0.0080,
    2020: 0.0005, 2021: 0.0001, 2022: 0.0125, 2023: 0.0500, 2024: 0.0250,
    2025: 0.0200, 2026: 0.0160,
}
TASSO_LEGALE_DEFAULT = 0.0160  # fallback per anni non in tabella

# Mappa frequenza -> mesi da sommare
FREQUENZA_MESI = {
    "Mensile": 1,
    "Trimestrale": 3,
    "Semestrale": 6,
}

# Parametri forfettari spese esecutive (modificabili)
SPESE_IMMOBILIARE = {
    "spese_vive": 800.0,        # CU, trascrizioni, note
    "ctu": 3500.0,              # consulenza tecnica d'ufficio (aggiornato)
    "custode_delegato": 4000.0, # o 3% del valore se maggiore
    "perc_custode": 0.03,
    "pubblicita": 1500.0,       # pubblicità sul PVP (aggiornato)
    "spese_legali_nostre": 2600.0,
}
SPESE_MOBILIARE = {
    "spese_vive": 150.0,
    "ufficiale_legali": 500.0,
    "spese_legali_nostre": 2600.0,
}

# Costi di acquisizione credito NPL (modificabili)
COSTI_ACQUISIZIONE = {
    "fronting": 8000.0,
    "notaio": 2000.0,
    "servicer": 5000.0,
    "advisors": 10000.0,
}

# ----------------------------------------------------------
# Parametri per il calcolo dei compensi professionali
# (Custode giudiziario e Delegato alla vendita)
# ----------------------------------------------------------

# Aliquote fiscali comuni ai due compensi
SPESE_GENERALI_PERC = 0.10       # spese generali forfettarie
CASSA_PREVIDENZA_PERC = 0.04     # cassa di previdenza (su compenso + spese gen.)
IVA_PERC = 0.22                  # IVA

# --- Custode giudiziario (D.M. 80/2009), scaglioni CUMULATIVI ---
# (limite_superiore, aliquota) — l'ultimo scaglione ha limite infinito.
SCAGLIONI_CUSTODE = [
    (25000.0, 0.03),        # fino a 25.000 €: 3%
    (100000.0, 0.015),      # da 25.001 a 100.000 €: 1,5%
    (500000.0, 0.01),       # da 100.001 a 500.000 €: 1%
    (float("inf"), 0.003),  # oltre 500.000 €: 0,3%
]
MAGGIORAZIONE_CUSTODE_DEFAULT = 0.20  # indennità liberazione / difficoltà

# --- Delegato alla vendita (D.M. 227/2015), compenso PER FASE ---
# Il compenso è un importo fisso per ciascuna delle 4 fasi, che dipende
# dallo scaglione in cui ricade il prezzo di aggiudicazione.
FASI_DELEGATO = [
    "Attività preliminari",
    "Aggiudicazione/assegnazione",
    "Trasferimento proprietà",
    "Distribuzione",
]

# ==========================================================
# 2. FUNZIONI DI UTILITÀ TEMPORALE
# ==========================================================

def giorni_tra(d1, d2):
    """Numero di giorni tra due date."""
    return (d2 - d1).days

def interesse_semplice(capitale, tasso_annuo, giorni, base_anno=365):
    """
    Calcolo interesse SEMPLICE (no anatocismo - art. 1283 c.c.).
    Formula: C * i * (gg / base)
    """
    if giorni <= 0 or capitale <= 0:
        return 0.0
    return capitale * tasso_annuo * (giorni / base_anno)

def tasso_legale_per_anno(anno):
    """Restituisce il tasso legale vigente in un dato anno."""
    return TASSI_LEGALI.get(anno, TASSO_LEGALE_DEFAULT)

def interesse_legale_pro_rata(capitale, data_inizio, data_fine):
    """
    Calcola interessi al tasso legale ex art. 1284 c.c. spezzando il periodo
    ad ogni 1° gennaio (pro-rata temporis), perché il tasso legale cambia
    ad ogni cambio d'anno solare.

    Restituisce una tupla `(totale, segmenti)` dove `segmenti` è una lista
    di dict, uno per anno solare attraversato, con le chiavi:
        - "inizio":   date di inizio del segmento
        - "fine":     date di fine del segmento (esclusa)
        - "giorni":   numero di giorni del segmento
        - "tasso":    tasso legale dell'anno (decimale, es. 0.025)
        - "interesse": interesse maturato nel segmento (€)
    """
    totale = 0.0
    segmenti = []
    cursore = data_inizio
    while cursore < data_fine:
        prossimo_capodanno = date(cursore.year + 1, 1, 1)
        fine_segmento = min(prossimo_capodanno, data_fine)
        gg = giorni_tra(cursore, fine_segmento)
        tasso = tasso_legale_per_anno(cursore.year)
        interesse = interesse_semplice(capitale, tasso, gg)
        segmenti.append({
            "inizio": cursore,
            "fine": fine_segmento,
            "giorni": gg,
            "tasso": tasso,
            "interesse": interesse,
        })
        totale += interesse
        cursore = fine_segmento
    return totale, segmenti

def genera_rate_scadute(importo_rata, data_prima_rata, frequenza, data_limite):
    """
    Auto-genera le date delle rate scadute partendo dalla prima rata
    e sommando i mesi (in base alla frequenza), fermandosi alla data_limite
    (= Data Decadenza Effettiva). Il numero di rate è calcolato in automatico.
    """
    mesi = FREQUENZA_MESI[frequenza]
    rate = []
    cursore = data_prima_rata
    while cursore < data_limite:
        rate.append({"importo": importo_rata, "data_scadenza": cursore})
        cursore = cursore + relativedelta(months=mesi)
    return rate


# Numero di periodi annui per ciascuna frequenza (per calcolo TAN periodale)
PERIODI_ANNUI = {
    "Mensile": 12,
    "Trimestrale": 4,
    "Semestrale": 2,
}


def genera_piano_ammortamento(capitale, tan, durata_mesi, frequenza,
                               data_erogazione):
    """
    Genera il piano di ammortamento alla francese (rata costante).

    Parametri:
        capitale         : capitale originario erogato (€)
        tan              : Tasso Annuo Nominale (decimale, es. 0.045 per 4,5%)
        durata_mesi      : durata totale del mutuo in mesi
        frequenza        : "Mensile" | "Trimestrale" | "Semestrale"
        data_erogazione  : data di inizio del mutuo (la prima rata scadrà
                           dopo un periodo, secondo la frequenza)

    Ritorna una lista di dict, uno per rata, con le chiavi:
        num_rata, data_scadenza, quota_interessi, quota_capitale,
        importo_rata, capitale_residuo.

    Regola matematica (alla francese, interessi posticipati):
        i = TAN / periodi_annui
        R = C * i / (1 - (1+i)^-n)
        Quota_interessi[k] = capitale_residuo[k-1] * i
        Quota_capitale[k]  = R - Quota_interessi[k]
        Capitale_residuo[k] = capitale_residuo[k-1] - Quota_capitale[k]

    L'ultimo capitale residuo viene azzerato (eventuali residui da
    arrotondamenti vengono assorbiti nell'ultima quota capitale).
    """
    if frequenza not in PERIODI_ANNUI:
        raise ValueError(f"Frequenza non gestita: {frequenza}")
    periodi_annui = PERIODI_ANNUI[frequenza]
    mesi_per_periodo = FREQUENZA_MESI[frequenza]
    n = int(durata_mesi // mesi_per_periodo)
    if n <= 0:
        raise ValueError("Durata del mutuo troppo breve per la frequenza scelta.")

    i = tan / periodi_annui
    if i == 0:
        rata_costante = capitale / n
    else:
        rata_costante = capitale * i / (1 - (1 + i) ** (-n))

    piano = []
    residuo = capitale
    for k in range(1, n + 1):
        quota_interessi = residuo * i
        quota_capitale = rata_costante - quota_interessi
        if k == n:
            # Forza l'azzeramento dell'ultimo capitale residuo:
            # quota_capitale prende quello che resta, importo_rata si adegua.
            quota_capitale = residuo
            importo_rata = quota_capitale + quota_interessi
        else:
            importo_rata = rata_costante
        residuo_dopo = residuo - quota_capitale
        data_scadenza = data_erogazione + relativedelta(months=k * mesi_per_periodo)
        piano.append({
            "num_rata": k,
            "data_scadenza": data_scadenza,
            "quota_interessi": quota_interessi,
            "quota_capitale": quota_capitale,
            "importo_rata": importo_rata,
            "capitale_residuo": max(residuo_dopo, 0.0),
        })
        residuo = residuo_dopo
    return piano


def estrai_rate_insolute_da_piano(piano, data_prima_rata_insoluta, data_limite):
    """
    Filtra il piano restituendo le rate che ricadono nel periodo
    [data_prima_rata_insoluta, data_limite). Sono le rate insolute della
    Fase 1 (pre-decadenza/precetto).

    Il matching è strict: la prima rata insoluta corrisponde alla rata
    del piano con data_scadenza >= data_prima_rata_insoluta.
    """
    return [
        r for r in piano
        if data_prima_rata_insoluta <= r["data_scadenza"] < data_limite
    ]

# ==========================================================
# 3. CALCOLO DEL TRIENNIO GARANTITO (Art. 2855 c.c.)
# ==========================================================

def calcola_triennio(data_pignoramento):
    """
    Triennio garantito ex art. 2855 c.c.: i **3 anni esatti che precedono
    la data del pignoramento**.

    Esempi:
      - pignoramento 16/12/2021 → triennio 16/12/2018 → 16/12/2021
      - pignoramento 10/09/2023 → triennio 10/09/2020 → 10/09/2023

    Restituisce `(inizio_triennio, fine_triennio)` dove
    `fine_triennio` coincide con la data del pignoramento e
    `inizio_triennio = data_pignoramento - 3 anni`.

    Durata in giorni: 1095 (anno comune) o 1096 (se il periodo
    attraversa un 29 febbraio).
    """
    inizio_triennio = data_pignoramento - relativedelta(years=3)
    fine_triennio = data_pignoramento
    return inizio_triennio, fine_triennio

# ==========================================================
# 4. RIPARTIZIONE IPOTECARIO / CHIROGRAFARIO (Art. 2855 c.c.)
#    >>> CUORE UNICO DEL CALCOLO <<<
# ==========================================================

def ripartisci_credito(capitale, tasso_mora, data_inizio_mora,
                       data_pignoramento, data_fine):
    """
    Filtro Art. 2855 c.c. applicato a una "voce" di interessi (rata o capitale).

    Divide gli interessi in tre fasi rispetto al **triennio garantito**
    (= i 3 anni esatti che precedono il pignoramento):

    - FASE 1 — PRE-TRIENNIO: interessi anteriori a (pignoramento − 3 anni).
      Degradano interamente a chirografario, pur restando al tasso di mora.
    - FASE 2 — TRIENNIO: interessi maturati nei 3 anni precedenti il
      pignoramento. Ipotecari al tasso di mora pattuito.
    - FASE 3 — POST-TRIENNIO: interessi maturati dopo il pignoramento.
      La quota al tasso legale resta ipotecaria; l'eccedenza (mora − legale)
      diventa chirografaria. Il tasso legale è applicato pro-rata anno per anno.
    """
    inizio_triennio, fine_triennio = calcola_triennio(data_pignoramento)

    risultato = {"ipotecario": 0.0, "chirografario": 0.0, "dettaglio": {}}

    # --- FASE 1 — PRE-TRIENNIO (chirografario @ mora) ---
    if data_inizio_mora < inizio_triennio:
        fine_pre = min(inizio_triennio, data_fine)
        gg = giorni_tra(data_inizio_mora, fine_pre)
        int_pre = interesse_semplice(capitale, tasso_mora, gg)
        risultato["chirografario"] += int_pre
        risultato["dettaglio"]["pre_triennio_chiro"] = int_pre

    # --- FASE 2 — TRIENNIO (ipotecario @ mora) ---
    inizio_t = max(data_inizio_mora, inizio_triennio)
    fine_t = min(fine_triennio, data_fine)
    if fine_t > inizio_t:
        gg = giorni_tra(inizio_t, fine_t)
        int_triennio = interesse_semplice(capitale, tasso_mora, gg)
        risultato["ipotecario"] += int_triennio
        risultato["dettaglio"]["triennio_ipo_mora"] = int_triennio

    # --- FASE 3 — POST-TRIENNIO (ipotecario @ legale, chiro = mora − legale) ---
    inizio_post = max(data_inizio_mora, fine_triennio)
    if data_fine > inizio_post:
        int_legale, segmenti_legale = interesse_legale_pro_rata(
            capitale, inizio_post, data_fine
        )
        gg = giorni_tra(inizio_post, data_fine)
        int_mora_post = interesse_semplice(capitale, tasso_mora, gg)

        risultato["ipotecario"] += int_legale
        risultato["chirografario"] += (int_mora_post - int_legale)
        risultato["dettaglio"]["post_ipo_legale"] = int_legale
        risultato["dettaglio"]["post_chiro_diff"] = int_mora_post - int_legale
        risultato["dettaglio"]["post_segmenti_legale"] = segmenti_legale

    return risultato

def _accumula(totale, parziale, chiave_dettaglio):
    """Helper: somma un risultato parziale nel totale e registra il dettaglio.
    Accumula inoltre le 4 voci della tripartizione ex art. 2855 c.c."""
    totale["ipotecario"] += parziale["ipotecario"]
    totale["chirografario"] += parziale["chirografario"]
    totale["dettaglio"][chiave_dettaglio] = parziale["dettaglio"]

    # --- Accumulo voci Art. 2855 c.c. ---
    d = parziale["dettaglio"]
    totale["voci_2855"]["pre_chiro"]    += d.get("pre_triennio_chiro", 0.0)
    totale["voci_2855"]["triennio_ipo"] += d.get("triennio_ipo_mora", 0.0)
    totale["voci_2855"]["post_ipo"]     += d.get("post_ipo_legale", 0.0)
    totale["voci_2855"]["post_chiro"]   += d.get("post_chiro_diff", 0.0)
    return totale

# ==========================================================
# 5. MOTORE UNIFICATO DI CALCOLO (CASO A e CASO B insieme)
# ==========================================================

def calcola_mora_unificato(importo_rata, data_prima_rata, frequenza,
                           capitale_residuo, tasso_mora,
                           data_decadenza_effettiva,
                           data_pignoramento, data_fine,
                           piano_ammortamento=None):
    """
    MOTORE UNICO valido sia per CASO A (Lettera DBT) che CASO B (Precetto).
    L'unica differenza tra i due casi è 'data_decadenza_effettiva':
        - CASO A -> Data Lettera DBT
        - CASO B -> Data Notifica Precetto

    PARTE RATE: da 'data_prima_rata' a 'data_decadenza_effettiva'.
        Mora su ogni singola rata, dalla sua scadenza fino alla decadenza.
    PARTE CAPITALE: da 'data_decadenza_effettiva' a 'data_fine'.
        Mora sull'INTERO capitale residuo.

    Entrambe le parti passano per il filtro Art. 2855 c.c., che le ripartisce
    nelle 3 fasi (pre-triennio, triennio, post-triennio) rispetto al
    triennio garantito (3 anni a ritroso dal pignoramento).

    Parametro `piano_ammortamento` (opzionale):
        Se fornito (lista di dict da `genera_piano_ammortamento`), la Fase 1
        usa la **quota_capitale** di ciascuna rata insoluta come capitale di
        riferimento per il calcolo della mora, NON l'importo_rata intero.
        Questo evita l'anatocismo ex art. 1283 c.c.: gli interessi di mora
        si applicano solo sulla quota capitale; la quota interessi della
        singola rata viene tracciata a parte (non produce ulteriore mora).
    """
    totale = {
        "ipotecario": 0.0,
        "chirografario": 0.0,
        "dettaglio": {},
        # --- Contatore tripartizione Art. 2855 c.c. ---
        "voci_2855": {
            "pre_chiro": 0.0,
            "triennio_ipo": 0.0,
            "post_ipo": 0.0,
            "post_chiro": 0.0,
        },
    }

    # ---------- FASE 1: rate scadute fino alla decadenza ----------
    # Se è passato un piano di ammortamento, prendo le rate insolute da lì
    # (con quote interessi/capitale separate). Altrimenti genero rate
    # uniformi con importo_rata intero (comportamento storico).
    usa_piano = piano_ammortamento is not None
    if usa_piano:
        rate_insolute_piano = estrai_rate_insolute_da_piano(
            piano_ammortamento, data_prima_rata, data_decadenza_effettiva
        )
        rate_scadute = [
            {
                "importo": r["quota_capitale"],   # mora SOLO sulla quota capitale
                "data_scadenza": r["data_scadenza"],
                "quota_capitale": r["quota_capitale"],
                "quota_interessi": r["quota_interessi"],
                "importo_rata_originale": r["importo_rata"],
                "num_rata_piano": r["num_rata"],
            }
            for r in rate_insolute_piano
        ]
    else:
        rate_scadute = [
            {
                "importo": r["importo"],
                "data_scadenza": r["data_scadenza"],
                "quota_capitale": r["importo"],          # mora sull'intera rata
                "quota_interessi": 0.0,
                "importo_rata_originale": r["importo"],
                "num_rata_piano": None,
            }
            for r in genera_rate_scadute(
                importo_rata, data_prima_rata, frequenza, data_decadenza_effettiva
            )
        ]

    dettaglio_fase1 = {
        "numero_rate_generate": len(rate_scadute),
        "rate": {},
        # rate_breakdown: lista strutturata per il rendering tabellare.
        # Ogni elemento contiene la singola rata con i giorni esatti di mora
        # e l'interesse maturato (somma ipotecario + chirografario di Fase 1).
        "rate_breakdown": [],
        # Flag e quote interessi messe da parte (no anatocismo)
        "usa_piano_ammortamento": usa_piano,
        "quote_interessi_messe_da_parte": 0.0,
    }

    for i, rata in enumerate(rate_scadute):
        rip = ripartisci_credito(
            capitale=rata["importo"],   # = quota_capitale se usa_piano, altrimenti rata intera
            tasso_mora=tasso_mora,
            data_inizio_mora=rata["data_scadenza"],
            data_pignoramento=data_pignoramento,
            data_fine=data_decadenza_effettiva   # <-- la rata corre fino alla decadenza
        )
        totale["ipotecario"] += rip["ipotecario"]
        totale["chirografario"] += rip["chirografario"]

        # --- Accumulo voci Art. 2855 c.c. anche per ogni rata ---
        d = rip["dettaglio"]
        totale["voci_2855"]["pre_chiro"]    += d.get("pre_triennio_chiro", 0.0)
        totale["voci_2855"]["triennio_ipo"] += d.get("triennio_ipo_mora", 0.0)
        totale["voci_2855"]["post_ipo"]     += d.get("post_ipo_legale", 0.0)
        totale["voci_2855"]["post_chiro"]   += d.get("post_chiro_diff", 0.0)

        dettaglio_fase1["rate"][
            f"rata_{i+1}_({rata['data_scadenza'].strftime('%d/%m/%Y')})"
        ] = rip["dettaglio"]

        # --- Breakdown rata per rata: giorni esatti + interesse maturato ---
        giorni_mora_rata = giorni_tra(rata["data_scadenza"], data_decadenza_effettiva)
        interesse_rata = rip["ipotecario"] + rip["chirografario"]
        dettaglio_fase1["rate_breakdown"].append({
            "i": i + 1,
            "data_scadenza": rata["data_scadenza"],
            "importo_rata_originale": rata["importo_rata_originale"],
            "quota_capitale": rata["quota_capitale"],
            "quota_interessi": rata["quota_interessi"],
            "capitale_su_cui_si_calcola_mora": rata["importo"],
            "giorni_mora": giorni_mora_rata,
            "interesse_maturato": interesse_rata,
            "num_rata_piano": rata["num_rata_piano"],
        })
        dettaglio_fase1["quote_interessi_messe_da_parte"] += rata["quota_interessi"]

    totale["dettaglio"]["FASE_1_rate"] = dettaglio_fase1

    # ---------- PARTE CAPITALE: intero capitale residuo dalla decadenza ----------
    rip_capitale = ripartisci_credito(
        capitale=capitale_residuo,
        tasso_mora=tasso_mora,
        data_inizio_mora=data_decadenza_effettiva,  # <-- parte dalla decadenza
        data_pignoramento=data_pignoramento,
        data_fine=data_fine
    )
    totale = _accumula(totale, rip_capitale, "FASE_2_capitale_residuo")

    return totale

# ==========================================================
# 6. LOGICA SPESE ESECUTIVE (PREVISIONE COSTI FUTURI)
# ==========================================================

def stima_spese_esecutive(tipo_procedura, valore_bene):
    """
    Stima forfettaria dei costi di una procedura esecutiva.
    Ritorna un dizionario con le singole voci e il totale.
    Valori indicativi: verificare sempre col foro competente.
    """
    voci = {}

    if tipo_procedura == "Pignoramento Immobiliare":
        p = SPESE_IMMOBILIARE
        custode = max(p["custode_delegato"], valore_bene * p["perc_custode"])
        voci = {
            "Spese vive (CU, trascrizioni, note)": p["spese_vive"],
            "CTU (perizia di stima)": p["ctu"],
            "Custode / Professionista delegato": custode,
            "Pubblicità (PVP)": p["pubblicita"],
            "Nostre spese legali": p["spese_legali_nostre"],
        }
    else:  # Mobiliare / Presso Terzi
        p = SPESE_MOBILIARE
        voci = {
            "Spese vive (notifica, bolli)": p["spese_vive"],
            "Ufficiale Giudiziario / Legali": p["ufficiale_legali"],
            "Nostre spese legali": p["spese_legali_nostre"],
        }

    totale = sum(voci.values())
    return voci, totale


# ==========================================================
# 6b. COMPENSI PROFESSIONALI (Custode e Delegato alla vendita)
# ==========================================================

def _applica_spese_cassa_iva(compenso_netto):
    """
    Applica a un compenso netto professionale, nell'ordine:
      + 10% spese generali forfettarie
      +  4% cassa di previdenza (su compenso + spese generali)
      + 22% IVA (sull'imponibile = compenso + spese gen. + cassa)

    Ritorna un dict con le singole voci e il totale documento.
    """
    spese_generali = compenso_netto * SPESE_GENERALI_PERC
    imponibile_pre_cassa = compenso_netto + spese_generali
    cassa = imponibile_pre_cassa * CASSA_PREVIDENZA_PERC
    imponibile = imponibile_pre_cassa + cassa
    iva = imponibile * IVA_PERC
    totale = imponibile + iva
    return {
        "spese_generali": spese_generali,
        "cassa": cassa,
        "imponibile": imponibile,
        "iva": iva,
        "totale": totale,
    }


def calcola_compenso_custode(valore_aggiudicazione,
                             maggiorazione=MAGGIORAZIONE_CUSTODE_DEFAULT):
    """
    Compenso del Custode giudiziario ex D.M. 80/2009.

    Scaglioni CUMULATIVI sul valore di aggiudicazione:
      - fino a 25.000 €:            3%
      - da 25.001 a 100.000 €:      1,5%
      - da 100.001 a 500.000 €:     1%
      - oltre 500.000 €:            0,3%

    Poi:
      + maggiorazione (default 20%) per indennità di liberazione /
        difficoltà eccezionali, applicata al compenso a scaglioni;
      + 10% spese generali, + 4% cassa, + 22% IVA (via helper comune).

    Ritorna un dict con il breakdown completo (per l'expander a schermo).
    """
    scaglioni_dett = []
    compenso_scaglioni = 0.0
    limite_prec = 0.0
    for limite, aliquota in SCAGLIONI_CUSTODE:
        if valore_aggiudicazione <= limite_prec:
            break
        base_scaglione = min(valore_aggiudicazione, limite) - limite_prec
        if base_scaglione > 0:
            importo = base_scaglione * aliquota
            compenso_scaglioni += importo
            scaglioni_dett.append({
                "da": limite_prec,
                "a": limite,
                "base": base_scaglione,
                "aliquota": aliquota,
                "importo": importo,
            })
        limite_prec = limite

    maggiorazione_importo = compenso_scaglioni * maggiorazione
    compenso_netto = compenso_scaglioni + maggiorazione_importo
    fisco = _applica_spese_cassa_iva(compenso_netto)

    return {
        "valore_aggiudicazione": valore_aggiudicazione,
        "scaglioni": scaglioni_dett,
        "compenso_scaglioni": compenso_scaglioni,
        "maggiorazione_perc": maggiorazione,
        "maggiorazione_importo": maggiorazione_importo,
        "compenso_netto": compenso_netto,
        **fisco,
    }


def _compenso_fase_delegato(valore_aggiudicazione):
    """Importo per singola fase ex D.M. 227/2015 in base allo scaglione."""
    if valore_aggiudicazione <= 100000.0:
        return 1000.0
    elif valore_aggiudicazione <= 500000.0:
        return 1500.0
    else:
        return 2000.0


def calcola_compenso_delegato(valore_aggiudicazione):
    """
    Compenso del Delegato alla vendita ex D.M. 227/2015 (beni immobili).

    Il compenso si articola in 4 fasi (attività preliminari, aggiudicazione,
    trasferimento, distribuzione). Ogni fase vale un importo fisso a seconda
    dello scaglione del prezzo di aggiudicazione:
      - fino a 100.000 €:        1.000 € / fase  (4.000 € totali)
      - da 100.001 a 500.000 €:  1.500 € / fase  (6.000 € totali)
      - oltre 500.000 €:         2.000 € / fase  (8.000 € totali)

    Poi: + 10% spese generali, + 4% cassa, + 22% IVA (helper comune).

    Benchmark D.M. 227/2015 (allegato di riferimento): valore 200.000 € →
    compenso tabellare 6.000 €, totale documento 8.374,08 €.

    Ritorna un dict con il breakdown completo (per l'expander a schermo).
    """
    compenso_fase = _compenso_fase_delegato(valore_aggiudicazione)
    fasi_dett = [
        {"nome": nome, "importo": compenso_fase} for nome in FASI_DELEGATO
    ]
    compenso_netto = compenso_fase * len(FASI_DELEGATO)
    fisco = _applica_spese_cassa_iva(compenso_netto)

    return {
        "valore_aggiudicazione": valore_aggiudicazione,
        "compenso_fase": compenso_fase,
        "fasi": fasi_dett,
        "compenso_netto": compenso_netto,
        **fisco,
    }
