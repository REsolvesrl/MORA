"""Test del metodo triennio 'solare' (annata anno solare) e verifiche
di regressione contro conteggi professionali reali (RIPA / doValue)."""

from datetime import date

import pytest

from calcoli import (
    calcola_triennio,
    calcola_mora_unificato,
    ripartisci_credito,
    interesse_semplice,
    METODO_TRIENNIO_ESATTO,
    METODO_TRIENNIO_SOLARE,
)


class TestCalcolaTriennioSolare:
    def test_ripa_confini(self):
        # doValue RIPA: pignoramento 13/02/2025, aggiudicazione 25/02/2025
        # → triennio 01/01/2023 → 25/02/2025 (annate 2023-2024-2025)
        inizio, fine = calcola_triennio(
            date(2025, 2, 13), METODO_TRIENNIO_SOLARE,
            data_aggiudicazione=date(2025, 2, 25),
        )
        assert inizio == date(2023, 1, 1)
        assert fine == date(2025, 2, 25)

    def test_bassotti_confini(self):
        # Triple A BASSOTTI: pignoramento 31/12/2021, aggiudicazione 29/02/2024
        # → annate 2019-2020-2021: inizio 01/01/2019, fine annata = 01/01/2022
        inizio, fine = calcola_triennio(
            date(2021, 12, 31), METODO_TRIENNIO_SOLARE,
            data_aggiudicazione=date(2024, 2, 29),
        )
        assert inizio == date(2019, 1, 1)
        assert fine == date(2022, 1, 1)

    def test_inizio_sempre_primo_gennaio(self):
        for d in [date(2023, 6, 15), date(2024, 1, 1), date(2025, 12, 31)]:
            inizio, _ = calcola_triennio(
                d, METODO_TRIENNIO_SOLARE, data_aggiudicazione=d,
            )
            assert inizio == date(d.year - 2, 1, 1)

    def test_fine_troncata_ad_aggiudicazione(self):
        # Se l'aggiudicazione è dentro l'annata in corso, la fine è l'aggiudicazione
        inizio, fine = calcola_triennio(
            date(2025, 3, 1), METODO_TRIENNIO_SOLARE,
            data_aggiudicazione=date(2025, 6, 30),
        )
        assert fine == date(2025, 6, 30)

    def test_senza_aggiudicazione_usa_fine_annata(self):
        inizio, fine = calcola_triennio(
            date(2025, 3, 1), METODO_TRIENNIO_SOLARE,
        )
        assert fine == date(2026, 1, 1)

    def test_esatto_default_invariato(self):
        # Backward compat: metodo di default resta "esatto"
        inizio, fine = calcola_triennio(date(2023, 9, 10))
        assert inizio == date(2020, 9, 10)
        assert fine == date(2023, 9, 10)


class TestRegressioneRIPA:
    """Verifica al centesimo contro il conteggio doValue RIPA ROBERTO."""

    C = 378187.45
    TASSO = 0.057
    PIGN = date(2025, 2, 13)
    AGG = date(2025, 2, 25)

    def test_pre_triennio_match_conteggio(self):
        # PUNTO 4 doValue: 01/05/2022 → inizio triennio (01/01/2023) = 14.469,56
        r = ripartisci_credito(
            capitale=self.C, tasso_mora=self.TASSO,
            data_inizio_mora=date(2022, 5, 1),
            data_pignoramento=self.PIGN,
            data_fine=self.AGG,
            metodo_triennio=METODO_TRIENNIO_SOLARE,
            data_aggiudicazione=self.AGG,
        )
        # Il pre-triennio (chirografo) deve valere 14.469,56 (245 giorni)
        assert r["dettaglio"]["pre_triennio_chiro"] == pytest.approx(14469.56, abs=0.01)

    def test_eccedenza_un_giorno(self):
        # 1 giorno di eccedenza mora-legale su capitale pieno (post-triennio)
        # doValue punto 5: 38,34. Verifico la matematica pura.
        from calcoli import tasso_legale_per_anno
        mora_1gg = interesse_semplice(self.C, self.TASSO, 1)
        legale_1gg = interesse_semplice(self.C, tasso_legale_per_anno(2025), 1)
        assert mora_1gg == pytest.approx(59.06, abs=0.01)
        assert (mora_1gg - legale_1gg) == pytest.approx(38.34, abs=0.01)


class TestMetodoSolareVsEsatto:
    def test_metodi_danno_risultati_diversi(self):
        # Sugli stessi input, i due metodi devono in generale differire
        common = dict(
            importo_rata=800.0, data_prima_rata=date(2021, 3, 1),
            frequenza="Mensile", capitale_residuo=100000.0, tasso_mora=0.08,
            data_decadenza_effettiva=date(2022, 1, 20),
            data_pignoramento=date(2023, 9, 10), data_fine=date(2026, 6, 30),
        )
        r_esatto = calcola_mora_unificato(**common, metodo_triennio=METODO_TRIENNIO_ESATTO)
        r_solare = calcola_mora_unificato(**common, metodo_triennio=METODO_TRIENNIO_SOLARE)
        tot_e = r_esatto["ipotecario"] + r_esatto["chirografario"]
        tot_s = r_solare["ipotecario"] + r_solare["chirografario"]
        # Il totale interessi (mora piena sull'intero arco) è identico:
        # cambia solo la RIPARTIZIONE ipotecario/chirografario tra i metodi
        assert tot_e == pytest.approx(tot_s, rel=1e-9)
        # ma la quota ipotecaria cambia
        assert r_esatto["ipotecario"] != pytest.approx(r_solare["ipotecario"])

    def test_default_e_esatto(self):
        common = dict(
            importo_rata=800.0, data_prima_rata=date(2021, 3, 1),
            frequenza="Mensile", capitale_residuo=100000.0, tasso_mora=0.08,
            data_decadenza_effettiva=date(2022, 1, 20),
            data_pignoramento=date(2023, 9, 10), data_fine=date(2026, 6, 30),
        )
        r_default = calcola_mora_unificato(**common)
        r_esatto = calcola_mora_unificato(**common, metodo_triennio=METODO_TRIENNIO_ESATTO)
        assert r_default["ipotecario"] == pytest.approx(r_esatto["ipotecario"])
