# MORA — Calcolo Interessi di Mora (Ipotecario / Chirografario)

Web app per il calcolo degli interessi di mora su mutui in default, con divisione automatica tra quota **ipotecaria** e **chirografaria** secondo la tripartizione ex **art. 2855 c.c.**

App live: **<https://interessimora.streamlit.app/>**

## A cosa serve

Strumento di supporto per advisor, servicer NPL e legali che devono:

- **Auditare il GBV** dichiarato da una banca cedente, verificandone la congruità rispetto al calcolo "alla pari" alla data di attualizzazione.
- **Stimare le spese** di una procedura esecutiva (immobiliare, mobiliare, presso terzi) in prededuzione ex art. 2770 c.c.
- **Costruire un'offerta target** per l'acquisto di un credito NPL, con waterfall trasparente dal GBV all'offerta, e metriche di redditività (ROE, IRR annualizzato).

Il calcolo applica **interesse semplice** (no anatocismo, art. 1283 c.c.) e gestisce automaticamente:

- Tassi legali storici ex art. 1284 c.c. dal 2005 in poi, con pro-rata su ogni 1° gennaio.
- Triennio ipotecario centrato sull'annata del pignoramento.
- Generazione automatica delle rate insolute dalla prima rata fino alla decadenza (DBT o precetto).

> **Disclaimer:** strumento di supporto. Verificare sempre i risultati con il foro competente. Valori forfettari (spese esecutive, costi di acquisizione) sono indicativi e modificabili dall'interfaccia.

## Tab dell'applicazione

| Tab | Funzione |
|-----|----------|
| 📊 **Auditing e Check GBV** | Due modalità: **Sofferenza / Estratto conto ex art. 50 TUB** (credito già cristallizzato, replica i conteggi professionali e offre la variante da contestazione senza anatocismo) e **Rate insolute** (genera le rate dal piano e calcola la mora rata per rata). Entrambe dividono tra ipotecario e chirografario ex art. 2855 e confrontano col GBV dichiarato |
| 🔮 **Previsione Spese Esecutive** | Stima dei costi futuri di pignoramento (CTU, custode, pubblicità, legali) |
| 🤝 **Acquisto Credito e DPO** | Waterfall NPL dal GBV all'offerta target, con ROE e IRR annualizzato |

## Esecuzione in locale

Richiede **Python 3.9+**.

```bash
# 1. Clona il repository
git clone https://github.com/REsolvesrl/MORA.git
cd MORA

# 2. (Consigliato) crea un virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3. Installa le dipendenze
pip install -r requirements.txt

# 4. Avvia l'app
streamlit run streamlit_app.py
```

L'app si aprirà automaticamente nel browser su `http://localhost:8501`.

## Esecuzione test

I test coprono la logica di calcolo in `calcoli.py` (interesse semplice, interesse legale pro-rata, triennio ipotecario, ripartizione ex art. 2855 c.c., motore unificato, spese esecutive).

```bash
# Installa pytest (in aggiunta alle dipendenze runtime)
pip install -r requirements-dev.txt

# Esegui la suite
pytest
```

## Dipendenze

- [streamlit](https://streamlit.io/) — framework UI
- [plotly](https://plotly.com/python/) — grafici di sensibilità
- [python-dateutil](https://dateutil.readthedocs.io/) — aritmetica su date (rate ricorrenti, annate ipotecarie)

## Struttura del progetto

```
MORA/
├── streamlit_app.py      # Regista: config, tema, sidebar, cancello di accesso, tab
├── calcoli.py            # Motore di calcolo (art. 2855, tassi legali, sofferenza)
├── tab_auditing.py       # Tab 1 — Auditing e Check GBV (+ modalità Sofferenza)
├── tab_spese.py          # Tab 2 — Previsione spese esecutive
├── tab_npl.py            # Tab 3 — Acquisto credito NPL e DPO
├── pdf_export.py         # Report PDF cifrati (tema chiaro + tema dark)
├── autofill.py           # Estrazione dati dai PDF legali (Claude + fallback regex)
├── piano_io.py           # Import piani di ammortamento (CSV/Excel/PDF)
├── formatters.py         # Formattazione euro/percentuali/date all'italiana
├── ui_common.py          # Helper condivisi tra i tab
├── tests/                # Suite pytest (motore di calcolo + replica conteggi reali)
├── assets/               # Logo Resolve
├── .streamlit/           # Tema dark navy + oro
├── requirements.txt      # Dipendenze Python
├── packages.txt          # Pacchetti di sistema per Streamlit Cloud (OCR)
├── Dockerfile            # Immagine per Render / VPS (installa Tesseract + Poppler)
├── render.yaml           # Blueprint del servizio web su Render
└── README.md
```

## Accesso protetto

L'app supporta una **password unica di accesso**. Il cancello si attiva **solo se**
la variabile `APP_PASSWORD` è configurata; altrimenti l'app resta ad accesso libero.

| Dove gira | Come impostarla |
|---|---|
| Streamlit Cloud | *Settings → Secrets*: `APP_PASSWORD = "…"` |
| Render / Docker | Variabile d'ambiente `APP_PASSWORD` |
| In locale | `set APP_PASSWORD=…` (Windows) / `export APP_PASSWORD=…` (macOS, Linux) |

La stessa logica vale per `ANTHROPIC_API_KEY`, che abilita l'autofill dei PDF via
Claude. Senza chiave, l'autofill ricade sul parser regex.

> ⚠️ La password non va **mai** scritta nel repository.

## Deploy su dominio proprio (es. `interessi.resolvesrl.com`)

### Perché non basta l'hosting condiviso

Streamlit **non è un sito statico**: è un processo Python che deve restare sempre
attivo e parlare col browser via WebSocket. Di conseguenza:

- **Hosting condiviso** (Hostinger Premium / Illimitato / Cloud Startup, Aruba, ecc.):
  ❌ non può ospitarla — niente `root`, niente processi persistenti.
- **Streamlit Community Cloud**: ✅ gratis, ma ❌ **non supporta domini personalizzati**
  (solo sottodomini `*.streamlit.app`).
- **Render / Railway / Fly.io / VPS**: ✅ dominio custom + HTTPS.

Il dominio resta registrato dove volete (es. Hostinger): serve solo un record DNS.

### Procedura (Render)

1. **Render** → *Sign in with GitHub* → autorizza il repo `REsolvesrl/MORA`.
2. *New +* → **Blueprint** → seleziona il repo, branch `main`. Render legge
   `render.yaml` e crea il servizio `mora-resolve`. Primo build ≈ 5-10 min
   (compila l'immagine Docker con Tesseract).
3. *Environment* → aggiungi `APP_PASSWORD` (e, se serve, `ANTHROPIC_API_KEY`).
4. *Settings → Custom Domains* → aggiungi `interessi.resolvesrl.com`.
   Render restituisce un target CNAME (es. `mora-resolve.onrender.com`).
5. Nel pannello del registrar (**Hostinger → hPanel → Domini → Zona DNS**) crea:

   | Tipo | Nome | Punta a |
   |---|---|---|
   | `CNAME` | `interessi` | *(il target fornito da Render)* |

   ⚠️ **Non** creare `interessi` come "sottodominio/sito web" nel pannello hosting:
   genererebbe un record A verso Hostinger, in conflitto col CNAME.
6. Torna su Render → *Verify*. La propagazione DNS richiede da 10 minuti a qualche
   ora. Il certificato HTTPS (Let's Encrypt) è emesso automaticamente.

### Aggiornamenti

`autoDeploy: true` in `render.yaml`: **ogni push su `main` ridistribuisce l'app**,
esattamente come su Streamlit Cloud. Il build Docker impiega ~3-5 minuti.

### Piani

| Piano Render | Costo | Nota |
|---|---|---|
| Free | 0 € | Si spegne dopo 15 min di inattività: primo accesso ≈ 1 min di attesa |
| Starter | ~7 $/mese | Sempre attivo — consigliato per uso con clienti |

## Licenza

Progetto interno [Resolve S.r.l.](mailto:info@resolvesrl.com)
