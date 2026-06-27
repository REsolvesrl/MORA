import streamlit as st
from datetime import date

# Tabella dei tassi legali per anno (DA AGGIORNARE!)
TASSI_LEGALI = {
    2020: 0.05, 2021: 0.01, 2022: 0.0125,
    2023: 0.05, 2024: 0.025, 2025: 0.02, 2026: 0.02
}

def calcola_mora(capitale, tasso_mora, data_inizio, data_pign, data_vendita, tasso_in_nota):
    dettaglio = []
    ipotecario = 0.0
    chirografario = 0.0

    # FASE A - Triennio ipotecario "pieno" (2 anni + anno in corso prima del pignoramento)
    inizio_triennio = date(data_pign.year - 2, 1, 1)
    if inizio_triennio < data_inizio:
        inizio_triennio = data_inizio

    giorni_a = (data_pign - inizio_triennio).days
    int_a = capitale * tasso_mora * giorni_a / 365
    if tasso_in_nota:
        ipotecario += int_a
        dettaglio.append((f"Triennio ante-pignoramento ({inizio_triennio} → {data_pign})", "IPOTECARIO", round(int_a, 2)))
    else:
        chirografario += int_a
        dettaglio.append((f"Triennio ante-pignoramento (no nota) ({inizio_triennio} → {data_pign})", "CHIROGRAFARIO", round(int_a, 2)))

    # FASE B - Periodo ante-triennio (eventuale, sempre chirografario)
    if data_inizio < inizio_triennio:
        giorni_b = (inizio_triennio - data_inizio).days
        int_b = capitale * tasso_mora * giorni_b / 365
        chirografario += int_b
        dettaglio.append((f"Periodo ante-triennio ({data_inizio} → {inizio_triennio})", "CHIROGRAFARIO", round(int_b, 2)))

    # FASE C - Post-pignoramento al tasso legale (ipotecario)
    int_c = 0.0
    anno = data_pign.year
    data_corr = data_pign
    while data_corr < data_vendita:
        fine_anno = date(anno, 12, 31)
        data_fine = min(fine_anno, data_vendita)
        giorni = (data_fine - data_corr).days
        tasso_leg = TASSI_LEGALI.get(anno, 0.02)
        int_c += capitale * tasso_leg * giorni / 365
        data_corr = date(anno + 1, 1, 1)
        anno += 1
    ipotecario += int_c
    dettaglio.append((f"Post-pignoramento al tasso legale ({data_pign} → {data_vendita})", "IPOTECARIO", round(int_c, 2)))

    return {"ipotecario": ipotecario, "chirografario": chirografario, "dettaglio": dettaglio}


# ---------- INTERFACCIA ----------
st.title("📊 Calcolatore Interessi di Mora")
st.write("Inserisci i dati del mutuo per calcolare la quota ipotecaria e chirografaria.")

capitale = st.number_input("Capitale in mora (€)", value=100000.0)
tasso_mora = st.number_input("Tasso di mora (%)", value=6.5) / 100
data_inizio_mora = st.date_input("Data inizio mora", value=date(2020, 1, 1))
data_pignoramento = st.date_input("Data pignoramento", value=date(2022, 6, 1))
data_vendita = st.date_input("Data vendita/decreto", value=date(2026, 6, 1))
tasso_in_nota = st.checkbox("Tasso di mora presente in nota di iscrizione?", value=True)

if st.button("Calcola"):
    risultato = calcola_mora(capitale, tasso_mora, data_inizio_mora,
                             data_pignoramento, data_vendita, tasso_in_nota)

    st.subheader("Risultati")
    st.metric("Totale IPOTECARIO", f"€ {round(risultato['ipotecario'], 2)}")
    st.metric("Totale CHIROGRAFARIO", f"€ {round(risultato['chirografario'], 2)}")

    st.write("**Dettaglio:**")
    for descr, tipo, importo in risultato["dettaglio"]:
        st.write(f"- {descr} → **[{tipo}]** € {importo}")
