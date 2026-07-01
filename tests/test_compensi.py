"""Test dei compensi professionali (Custode D.M. 80/2009, Delegato D.M. 227/2015)."""

import pytest

from calcoli import (
    calcola_compenso_custode,
    calcola_compenso_delegato,
    _applica_spese_cassa_iva,
)


class TestApplicaSpeseCassaIva:
    def test_ordine_e_importi(self):
        # Su un compenso netto di 6.000 €:
        # + 10% spese gen = 600 → 6.600
        # + 4% cassa su 6.600 = 264 → imponibile 6.864
        # + 22% IVA su 6.864 = 1.510,08 → totale 8.374,08
        r = _applica_spese_cassa_iva(6000.0)
        assert r["spese_generali"] == pytest.approx(600.0)
        assert r["cassa"] == pytest.approx(264.0)
        assert r["imponibile"] == pytest.approx(6864.0)
        assert r["iva"] == pytest.approx(1510.08)
        assert r["totale"] == pytest.approx(8374.08)


class TestCompensoDelegato:
    def test_benchmark_pdf_200k(self):
        """Benchmark ufficiale D.M. 227/2015: 200.000 € → 8.374,08 € totale."""
        r = calcola_compenso_delegato(200000.0)
        assert r["compenso_fase"] == 1500.0
        assert r["compenso_netto"] == pytest.approx(6000.0)
        assert r["spese_generali"] == pytest.approx(600.0)
        assert r["cassa"] == pytest.approx(264.0)
        assert r["imponibile"] == pytest.approx(6864.0)
        assert r["iva"] == pytest.approx(1510.08)
        assert r["totale"] == pytest.approx(8374.08)

    def test_scaglione_primo_sotto_100k(self):
        r = calcola_compenso_delegato(80000.0)
        assert r["compenso_fase"] == 1000.0
        assert r["compenso_netto"] == pytest.approx(4000.0)

    def test_scaglione_terzo_sopra_500k(self):
        r = calcola_compenso_delegato(700000.0)
        assert r["compenso_fase"] == 2000.0
        assert r["compenso_netto"] == pytest.approx(8000.0)

    def test_soglia_esatta_100k(self):
        # A esattamente 100.000 € siamo ancora nel primo scaglione
        r = calcola_compenso_delegato(100000.0)
        assert r["compenso_fase"] == 1000.0

    def test_soglia_appena_sopra_100k(self):
        r = calcola_compenso_delegato(100000.01)
        assert r["compenso_fase"] == 1500.0

    def test_soglia_esatta_500k(self):
        r = calcola_compenso_delegato(500000.0)
        assert r["compenso_fase"] == 1500.0

    def test_quattro_fasi_presenti(self):
        r = calcola_compenso_delegato(200000.0)
        assert len(r["fasi"]) == 4
        assert all(f["importo"] == 1500.0 for f in r["fasi"])


class TestCompensoCustode:
    def test_scaglioni_cumulativi_200k(self):
        # 25.000 × 3% = 750
        # 75.000 × 1,5% = 1.125
        # 100.000 × 1% = 1.000
        # Totale scaglioni = 2.875
        r = calcola_compenso_custode(200000.0)
        assert r["compenso_scaglioni"] == pytest.approx(2875.0)

    def test_maggiorazione_20pct_default(self):
        r = calcola_compenso_custode(200000.0)
        # 2.875 × 20% = 575 → compenso netto 3.450
        assert r["maggiorazione_importo"] == pytest.approx(575.0)
        assert r["compenso_netto"] == pytest.approx(3450.0)

    def test_totale_200k(self):
        # compenso netto 3.450
        # + 10% spese gen = 345 → 3.795
        # + 4% cassa = 151,80 → imponibile 3.946,80
        # + 22% IVA = 868,296 → totale 4.815,096
        r = calcola_compenso_custode(200000.0)
        assert r["imponibile"] == pytest.approx(3946.80)
        assert r["totale"] == pytest.approx(4815.096, abs=0.01)

    def test_solo_primo_scaglione(self):
        # 20.000 € → tutto nel primo scaglione al 3% = 600
        r = calcola_compenso_custode(20000.0)
        assert r["compenso_scaglioni"] == pytest.approx(600.0)
        assert len(r["scaglioni"]) == 1

    def test_scaglione_oltre_500k(self):
        # 25.000×3% + 75.000×1,5% + 400.000×1% + 100.000×0,3%
        # = 750 + 1.125 + 4.000 + 300 = 6.175
        r = calcola_compenso_custode(600000.0)
        assert r["compenso_scaglioni"] == pytest.approx(6175.0)
        assert len(r["scaglioni"]) == 4

    def test_maggiorazione_personalizzata(self):
        # Con maggiorazione a 0 il compenso netto = compenso scaglioni
        r = calcola_compenso_custode(200000.0, maggiorazione=0.0)
        assert r["compenso_netto"] == pytest.approx(r["compenso_scaglioni"])

    def test_breakdown_scaglioni_struttura(self):
        r = calcola_compenso_custode(200000.0)
        assert len(r["scaglioni"]) == 3
        primo = r["scaglioni"][0]
        assert primo["da"] == 0.0
        assert primo["a"] == 25000.0
        assert primo["aliquota"] == 0.03
        assert primo["importo"] == pytest.approx(750.0)
