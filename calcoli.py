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


def e_bisestile(anno):
    """True se l'anno è bisestile (regola gregoriana)."""
    return anno % 4 == 0 and (anno % 100 != 0 or anno % 400 == 0)


def interesse_periodo(capitale, tasso, data_inizio, data_fine, anno_civile=True):
    """
    Interesse semplice al `tasso` dato su [data_inizio, data_fine).

    - anno_civile=True  → "Anno Civile": il periodo viene spezzato ad ogni
      1° gennaio e ciascun segmento è diviso per i giorni effettivi dell'anno
      (366 per i bisestili, 365 altrimenti). È la convenzione dei conteggi
      professionali reali.
    - anno_civile=False → divisore fisso 365 su tutto il periodo
      ("anno commerciale").
    """
    if data_fine <= data_inizio or capitale <= 0 or tasso == 0:
        return 0.0
    if not anno_civile:
        return interesse_semplice(
            capitale, tasso, giorni_tra(data_inizio, data_fine), 365
        )
    totale = 0.0
    cursore = data_inizio
    while cursore < data_fine:
        prossimo_capodanno = date(cursore.year + 1, 1, 1)
        fine_segmento = min(prossimo_capodanno, data_fine)
        gg = giorni_tra(cursore, fine_segmento)
        base = 366 if e_bisestile(cursore.year) else 365
        totale += interesse_semplice(capitale, tasso, gg, base)
        cursore = fine_segmento
    return totale


def tasso_legale_per_anno(anno):
    """Restituisce il tasso legale vigente in un dato anno."""
    return TASSI_LEGALI.get(anno, TASSO_LEGALE_DEFAULT)

def interesse_legale_pro_rata(capitale, data_inizio, data_fine, anno_civile=True):
    """
    Calcola interessi al tasso legale ex art. 1284 c.c. spezzando il periodo
    ad ogni 1° gennaio (pro-rata temporis), perché il tasso legale cambia
    ad ogni cambio d'anno solare.

    `anno_civile`:
      - True  → divisore per segmento = giorni effettivi dell'anno
        (366 per i bisestili, 365 altrimenti).
      - False → divisore fisso 365.

    Restituisce una tupla `(totale, segmenti)` dove `segmenti` è una lista
    di dict, uno per anno solare attraversato, con le chiavi:
        - "inizio":   date di inizio del segmento
        - "fine":     date di fine del segmento (esclusa)
        - "giorni":   numero di giorni del segmento
        - "tasso":    tasso legale dell'anno (decimale, es. 0.025)
        - "base":     divisore usato (365 o 366)
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
        base = 366 if (anno_civile and e_bisestile(cursore.year)) else 365
        interesse = interesse_semplice(capitale, tasso, gg, base)
        segmenti.append({
            "inizio": cursore,
            "fine": fine_segmento,
            "giorni": gg,
            "tasso": tasso,
            "base": base,
            "interesse": interesse,
        })
        totale += interesse
        cursore = fine_segmento
    return totale, segmenti


# ----------------------------------------------------------
# Tasso di mora: scalare OPPURE scadenzario (tasso variabile)
# ----------------------------------------------------------

def _normalizza_scadenzario_mora(tasso_mora):
    """
    Normalizza il tasso di mora in una lista ordinata di tuple (da, tasso).

    Accetta:
      - un numero (float/int): tasso costante → [(date.min, tasso)]
      - una lista di dict {"da": date, "tasso": float}: scadenzario.
        Ogni voce vale dalla sua data 'da' (inclusa) fino alla 'da' della
        voce successiva (esclusa). Per le date anteriori alla prima voce
        si applica il tasso della prima voce.
    """
    if isinstance(tasso_mora, (int, float)):
        return [(date.min, float(tasso_mora))]
    voci = [(v["da"], float(v["tasso"])) for v in tasso_mora]
    if not voci:
        raise ValueError("Scadenzario tassi di mora vuoto.")
    voci.sort(key=lambda x: x[0])
    return voci


def _tasso_mora_alla_data(scadenzario, d):
    """Tasso vigente alla data d (ultima voce con 'da' <= d)."""
    tasso = scadenzario[0][1]
    for da, t in scadenzario:
        if da <= d:
            tasso = t
        else:
            break
    return tasso


def mora_su_periodo(capitale, tasso_mora, data_inizio, data_fine, anno_civile=True):
    """
    Interesse di mora su [data_inizio, data_fine), con `tasso_mora` che può
    essere uno scalare (tasso fisso) o uno scadenzario (tasso variabile).

    Il periodo viene spezzato ad ogni data di cambio tasso; ogni segmento è
    calcolato con `interesse_periodo`, che applica la convenzione del
    divisore:
      - anno_civile=True  → 365/366 (366 per i bisestili);
      - anno_civile=False → 365 fisso.

    Con un tasso scalare e anno_civile=False il risultato è identico a
    `interesse_semplice(capitale, tasso_mora, giorni)`.
    """
    if data_fine <= data_inizio or capitale <= 0:
        return 0.0
    scad = _normalizza_scadenzario_mora(tasso_mora)
    # Confini di cambio tasso strettamente interni al periodo
    confini = sorted({da for da, _ in scad if data_inizio < da < data_fine})
    punti = [data_inizio] + confini + [data_fine]
    totale = 0.0
    for i in range(len(punti) - 1):
        a, b = punti[i], punti[i + 1]
        tasso = _tasso_mora_alla_data(scad, a)
        totale += interesse_periodo(capitale, tasso, a, b, anno_civile)
    return totale

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

METODO_TRIENNIO_ESATTO = "esatto"
METODO_TRIENNIO_SOLARE = "solare"


def calcola_triennio(data_pignoramento, metodo=METODO_TRIENNIO_ESATTO,
                     data_aggiudicazione=None):
    """
    Triennio garantito ex art. 2855 c.c. Sono disponibili due metodi.

    metodo="esatto" (default):
        I **3 anni esatti che precedono la data del pignoramento**.
        - pignoramento 16/12/2021 → 16/12/2018 → 16/12/2021
        - inizio = pignoramento − 3 anni, fine = pignoramento.
        Durata 1095/1096 giorni.

    metodo="solare":
        L'**annata (anno solare) in corso al pignoramento più le 2 annate
        precedenti**, come nella prassi dei conteggi professionali
        (doValue, Triple A, ecc.).
        - inizio = 01/01 dell'anno (anno_pignoramento − 2).
        - fine = fine dell'annata in corso (01/01 dell'anno successivo al
          pignoramento), troncata alla data di aggiudicazione se questa
          è anteriore.
        Esempi:
          - pignoramento 13/02/2025, aggiudic. 25/02/2025 →
            triennio 01/01/2023 → 25/02/2025 (annate 2023-2024-2025).
          - pignoramento 31/12/2021, aggiudic. 29/02/2024 →
            triennio 01/01/2019 → 01/01/2022 (annate 2019-2020-2021),
            poi post-triennio al tasso legale fino all'aggiudicazione.

    Restituisce `(inizio_triennio, fine_triennio)`.
    """
    if metodo == METODO_TRIENNIO_SOLARE:
        inizio_triennio = date(data_pignoramento.year - 2, 1, 1)
        fine_annata_in_corso = date(data_pignoramento.year + 1, 1, 1)
        if data_aggiudicazione is not None:
            fine_triennio = min(fine_annata_in_corso, data_aggiudicazione)
        else:
            fine_triennio = fine_annata_in_corso
        return inizio_triennio, fine_triennio

    # --- metodo "esatto" (default) ---
    inizio_triennio = data_pignoramento - relativedelta(years=3)
    fine_triennio = data_pignoramento
    return inizio_triennio, fine_triennio

# ==========================================================
# 4. RIPARTIZIONE IPOTECARIO / CHIROGRAFARIO (Art. 2855 c.c.)
#    >>> CUORE UNICO DEL CALCOLO <<<
# ==========================================================

def ripartisci_credito(capitale, tasso_mora, data_inizio_mora,
                       data_pignoramento, data_fine,
                       metodo_triennio=METODO_TRIENNIO_ESATTO,
                       data_aggiudicazione=None, anno_civile=True):
    """
    Filtro Art. 2855 c.c. applicato a una "voce" di interessi (rata o capitale).

    Divide gli interessi in tre fasi rispetto al **triennio garantito**
    (vedi calcola_triennio per i due metodi disponibili):

    - FASE 1 — PRE-TRIENNIO: interessi anteriori all'inizio del triennio.
      Degradano interamente a chirografario, pur restando al tasso di mora.
    - FASE 2 — TRIENNIO: interessi maturati nel triennio garantito.
      Ipotecari al tasso di mora pattuito.
    - FASE 3 — POST-TRIENNIO: interessi maturati dopo la fine del triennio.
      La quota al tasso legale resta ipotecaria; l'eccedenza (mora − legale)
      diventa chirografaria. Il tasso legale è applicato pro-rata anno per anno.

    `metodo_triennio` seleziona il criterio del triennio (vedi calcola_triennio).
    `data_aggiudicazione` è usata dal metodo "solare" per troncare la fine del
    triennio; se None, si usa `data_fine`.
    `anno_civile` seleziona il divisore giorni (True = 365/366, False = 365).
    """
    if data_aggiudicazione is None:
        data_aggiudicazione = data_fine
    inizio_triennio, fine_triennio = calcola_triennio(
        data_pignoramento, metodo_triennio, data_aggiudicazione
    )

    risultato = {"ipotecario": 0.0, "chirografario": 0.0, "dettaglio": {}}

    # --- FASE 1 — PRE-TRIENNIO (chirografario @ mora) ---
    if data_inizio_mora < inizio_triennio:
        fine_pre = min(inizio_triennio, data_fine)
        int_pre = mora_su_periodo(capitale, tasso_mora, data_inizio_mora,
                                  fine_pre, anno_civile)
        risultato["chirografario"] += int_pre
        risultato["dettaglio"]["pre_triennio_chiro"] = int_pre

    # --- FASE 2 — TRIENNIO (ipotecario @ mora) ---
    inizio_t = max(data_inizio_mora, inizio_triennio)
    fine_t = min(fine_triennio, data_fine)
    if fine_t > inizio_t:
        int_triennio = mora_su_periodo(capitale, tasso_mora, inizio_t,
                                       fine_t, anno_civile)
        risultato["ipotecario"] += int_triennio
        risultato["dettaglio"]["triennio_ipo_mora"] = int_triennio

    # --- FASE 3 — POST-TRIENNIO (ipotecario @ legale, chiro = mora − legale) ---
    inizio_post = max(data_inizio_mora, fine_triennio)
    if data_fine > inizio_post:
        int_legale, segmenti_legale = interesse_legale_pro_rata(
            capitale, inizio_post, data_fine, anno_civile
        )
        int_mora_post = mora_su_periodo(capitale, tasso_mora, inizio_post,
                                        data_fine, anno_civile)

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
                           piano_ammortamento=None,
                           metodo_triennio=METODO_TRIENNIO_ESATTO,
                           anno_civile=True):
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
            data_fine=data_decadenza_effettiva,   # <-- la rata corre fino alla decadenza
            metodo_triennio=metodo_triennio,
            data_aggiudicazione=data_fine,        # aggiudicazione globale per i confini triennio
            anno_civile=anno_civile,
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
        data_fine=data_fine,
        metodo_triennio=metodo_triennio,
        data_aggiudicazione=data_fine,
        anno_civile=anno_civile,
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


# ==========================================================
# 7. MODALITÀ SOFFERENZA / ESTRATTO CONTO ex art. 50 TUB
#    (credito cristallizzato, stile conteggi Triple A / doValue)
# ==========================================================

# Leva 1 — base su cui girano gli interessi legali (pre-triennio + triennio
# fino al precetto):
BASE_SOLO_CAPITALE = "solo_capitale"          # ortodossa (per contestazione)
BASE_CAPITALE_INTERESSI = "capitale_interessi"  # replica prassi (anatocismo)

# Leva 2 — tasso applicato al triennio PRIMA del precetto:
TASSO_TRIENNIO_LEGALE = "legale"              # come i conteggi reali (prudente)
TASSO_TRIENNIO_CONVENZIONALE = "convenzionale"
TASSO_TRIENNIO_MORA = "mora"


def calcola_credito_sofferenza(
    sorte_capitale,
    quota_interessi_congelata,
    interessi_ante_sofferenza,
    spese,
    data_decorrenza,
    data_precetto,
    data_pignoramento,
    data_aggiudicazione,
    tasso_convenzionale,
    tasso_mora=None,
    base_legale=BASE_CAPITALE_INTERESSI,
    tasso_triennio=TASSO_TRIENNIO_LEGALE,
    anno_civile=False,
):
    """
    Ripartizione ex art. 2855 c.c. di un credito CRISTALLIZZATO da estratto
    conto ex art. 50 TUB (posizione a sofferenza), secondo la logica dei
    conteggi professionali (Triple A / doValue).

    A differenza di `calcola_mora_unificato` (che genera le rate), qui il
    credito è "fotografato": capitale puro + voci interessi congelate.

    Struttura temporale (triennio ANNO SOLARE dell'anno del pignoramento):

        decorrenza ──► 01/01(annata-2) ──► precetto ──► aggiudicazione
        │  PRE-TRIENNIO  │    TRIENNIO pre-precetto │ TRIENNIO post-precetto │
        │  legale/CHIRO  │    tasso_triennio/IPO    │  convenzionale/IPO     │

    Voci congelate (sempre CHIROGRAFO): quota_interessi_congelata +
    interessi_ante_sofferenza. Spese: grado ipotecario (art. 2855).

    Leve:
      - base_legale: base degli interessi al tasso legale
        ("solo_capitale" = ortodossa | "capitale_interessi" = prassi Triple A).
      - tasso_triennio: tasso del triennio PRIMA del precetto
        ("legale" | "convenzionale" | "mora").

    Ritorna un dict con la ripartizione ipotecario/chirografario, il dettaglio
    dei periodi e il confronto anatocismo (differenza tra le due basi).
    """
    annata_pign = data_pignoramento.year
    inizio_triennio = date(annata_pign - 2, 1, 1)

    base_leg = sorte_capitale + quota_interessi_congelata \
        if base_legale == BASE_CAPITALE_INTERESSI else sorte_capitale

    periodi = []

    # --- PERIODO A: pre-triennio (chirografo), tasso LEGALE su base_leg ---
    fine_pre = min(inizio_triennio, data_precetto)
    int_pre_chiro = 0.0
    if data_decorrenza < fine_pre:
        int_pre_chiro, seg = interesse_legale_pro_rata(
            base_leg, data_decorrenza, fine_pre, anno_civile
        )
        periodi.append({
            "nome": "Pre-triennio (legale, chirografo)",
            "da": data_decorrenza, "a": fine_pre, "base": base_leg,
            "tasso_desc": "legale variabile", "importo": int_pre_chiro,
            "grado": "chirografario", "segmenti": seg,
        })

    # --- PERIODO B: triennio PRIMA del precetto (ipotecario) ---
    inizio_b = max(inizio_triennio, data_decorrenza)
    fine_b = min(data_precetto, data_aggiudicazione)
    int_triennio_pre = 0.0
    if fine_b > inizio_b:
        if tasso_triennio == TASSO_TRIENNIO_LEGALE:
            int_triennio_pre, seg_b = interesse_legale_pro_rata(
                base_leg, inizio_b, fine_b, anno_civile
            )
            desc_b = "legale variabile"
            base_b = base_leg
        else:
            tasso_b = (tasso_convenzionale
                       if tasso_triennio == TASSO_TRIENNIO_CONVENZIONALE
                       else (tasso_mora or tasso_convenzionale))
            int_triennio_pre = interesse_periodo(
                sorte_capitale, tasso_b, inizio_b, fine_b, anno_civile
            )
            tipo_b = ("convenzionale" if tasso_triennio == TASSO_TRIENNIO_CONVENZIONALE
                      else "mora")
            desc_b = f"{tipo_b} {tasso_b*100:.2f}%"
            base_b = sorte_capitale
            seg_b = None
        periodi.append({
            "nome": "Triennio pre-precetto (ipotecario)",
            "da": inizio_b, "a": fine_b, "base": base_b,
            "tasso_desc": desc_b, "importo": int_triennio_pre,
            "grado": "ipotecario", "segmenti": seg_b,
        })

    # --- PERIODO C: triennio DOPO il precetto (ipotecario), convenzionale ---
    inizio_c = max(data_precetto, data_decorrenza)
    int_triennio_post = 0.0
    if data_aggiudicazione > inizio_c:
        int_triennio_post = interesse_periodo(
            sorte_capitale, tasso_convenzionale, inizio_c,
            data_aggiudicazione, anno_civile
        )
        periodi.append({
            "nome": "Triennio post-precetto (ipotecario)",
            "da": inizio_c, "a": data_aggiudicazione, "base": sorte_capitale,
            "tasso_desc": f"convenzionale {tasso_convenzionale*100:.2f}%",
            "importo": int_triennio_post, "grado": "ipotecario",
            "segmenti": None,
        })

    # --- Aggregazione ---
    ipo = {
        "sorte": sorte_capitale,
        "spese": spese,
        "triennio_legale": int_triennio_pre if tasso_triennio == TASSO_TRIENNIO_LEGALE else 0.0,
        "triennio_pre_precetto": int_triennio_pre,
        "triennio_post_precetto": int_triennio_post,
    }
    ipo["totale"] = (sorte_capitale + spese + int_triennio_pre + int_triennio_post)

    chiro = {
        "pre_triennio_legale": int_pre_chiro,
        "quota_interessi_congelata": quota_interessi_congelata,
        "interessi_ante_sofferenza": interessi_ante_sofferenza,
    }
    chiro["totale"] = (int_pre_chiro + quota_interessi_congelata
                       + interessi_ante_sofferenza)

    totale_credito = ipo["totale"] + chiro["totale"]

    # --- Confronto anatocismo: legale su capitale+interessi vs solo capitale ---
    def _legale_periodo(base):
        tot = 0.0
        if data_decorrenza < fine_pre:
            tot += interesse_legale_pro_rata(base, data_decorrenza, fine_pre, anno_civile)[0]
        if tasso_triennio == TASSO_TRIENNIO_LEGALE and fine_b > inizio_b:
            tot += interesse_legale_pro_rata(base, inizio_b, fine_b, anno_civile)[0]
        return tot

    legale_con_interessi = _legale_periodo(sorte_capitale + quota_interessi_congelata)
    legale_solo_capitale = _legale_periodo(sorte_capitale)
    extra_anatocismo = legale_con_interessi - legale_solo_capitale

    return {
        "ipotecario": ipo,
        "chirografario": chiro,
        "totale_credito": totale_credito,
        "somma_intimata": (sorte_capitale + quota_interessi_congelata
                           + interessi_ante_sofferenza + int_pre_chiro
                           + int_triennio_pre + spese),
        "inizio_triennio": inizio_triennio,
        "periodi": periodi,
        "confronto_anatocismo": {
            "legale_capitale_interessi": legale_con_interessi,
            "legale_solo_capitale": legale_solo_capitale,
            "extra": extra_anatocismo,
            "base_usata": base_legale,
        },
    }
