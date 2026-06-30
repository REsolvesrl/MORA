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
| 📊 **Auditing e Check GBV** | Calcola gli interessi di mora rata per rata + sul capitale residuo, divide tra ipotecario e chirografario, confronta col GBV dichiarato |
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

## Dipendenze

- [streamlit](https://streamlit.io/) — framework UI
- [plotly](https://plotly.com/python/) — grafici di sensibilità
- [python-dateutil](https://dateutil.readthedocs.io/) — aritmetica su date (rate ricorrenti, annate ipotecarie)

## Struttura del progetto

```
MORA/
├── streamlit_app.py     # Applicazione (UI + logica di calcolo)
├── requirements.txt     # Dipendenze Python
├── .gitignore
└── README.md
```

## Licenza

Progetto interno [Resolve S.r.l.](mailto:info@resolvesrl.com)
