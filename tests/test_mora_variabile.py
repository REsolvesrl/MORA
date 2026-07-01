"""Test del tasso di mora variabile (scadenzario)."""

from datetime import date

import pytest

from calcoli import (
    mora_su_periodo,
    interesse_semplice,
    interesse_periodo,
    interesse_legale_pro_rata,
    e_bisestile,
    ripartisci_credito,
    calcola_mora_unificato,
    _normalizza_scadenzario_mora,
    _tasso_mora_alla_data,
    METODO_TRIENNIO_SOLARE,
)


class TestAnnoCivile:
    def test_e_bisestile(self):
        assert e_bisestile(2024) is True
        assert e_bisestile(2023) is False
        assert e_bisestile(2000) is True    # divisibile per 400
        assert e_bisestile(1900) is False   # divisibile per 100 non 400

    def test_interesse_periodo_bisestile_usa_366(self):
        # 2024 bisestile: divisore 366 con anno_civile=True
        r = interesse_periodo(10000, 0.05, date(2024, 1, 1), date(2024, 2, 1))
        assert r == pytest.approx(10000 * 0.05 * 31 / 366)

    def test_interesse_periodo_365_fisso(self):
        r = interesse_periodo(10000, 0.05, date(2024, 1, 1), date(2024, 2, 1),
                              anno_civile=False)
        assert r == pytest.approx(10000 * 0.05 * 31 / 365)

    def test_verifica_riga_bassotti_29feb2024(self):
        # BASSOTTI: 29/02/2024, 29 giorni al 2,50% legale, capitale 372.535,85
        # Anno civile (366) → 737,95 (il conteggio ufficiale)
        C = 372535.85
        r = interesse_periodo(C, 0.025, date(2024, 2, 1), date(2024, 3, 1))
        assert r == pytest.approx(737.95, abs=0.01)

    def test_legale_pro_rata_bisestile_default_366(self):
        # Un anno bisestile pieno al tasso legale → interesse = C*tasso
        # (366/366 = 1) indipendentemente dal divisore
        tot, seg = interesse_legale_pro_rata(
            10000, date(2024, 1, 1), date(2025, 1, 1)
        )
        assert seg[0]["base"] == 366
        assert seg[0]["giorni"] == 366


class TestNormalizzaScadenzario:
    def test_scalare_diventa_lista(self):
        s = _normalizza_scadenzario_mora(0.08)
        assert len(s) == 1
        assert s[0][1] == 0.08

    def test_lista_ordinata(self):
        s = _normalizza_scadenzario_mora([
            {"da": date(2023, 1, 1), "tasso": 0.09},
            {"da": date(2022, 1, 1), "tasso": 0.06},
        ])
        assert s[0][0] == date(2022, 1, 1)
        assert s[1][0] == date(2023, 1, 1)

    def test_lista_vuota_errore(self):
        with pytest.raises(ValueError):
            _normalizza_scadenzario_mora([])


class TestTassoAllaData:
    def test_tasso_corrente(self):
        s = _normalizza_scadenzario_mora([
            {"da": date(2022, 1, 1), "tasso": 0.06},
            {"da": date(2023, 1, 1), "tasso": 0.09},
        ])
        assert _tasso_mora_alla_data(s, date(2022, 6, 1)) == 0.06
        assert _tasso_mora_alla_data(s, date(2023, 6, 1)) == 0.09
        # Prima della prima voce → prima voce
        assert _tasso_mora_alla_data(s, date(2020, 1, 1)) == 0.06


class TestMoraSuPeriodo:
    def test_scalare_uguale_interesse_semplice(self):
        r = mora_su_periodo(10000, 0.08, date(2023, 1, 1), date(2024, 1, 1))
        atteso = interesse_semplice(10000, 0.08, 365)
        assert r == pytest.approx(atteso)

    def test_split_a_cambio_tasso(self):
        # 6% dal 01/01, 9% dal 01/07/2023, periodo 01/01/2023 → 01/01/2024
        scad = [
            {"da": date(2023, 1, 1), "tasso": 0.06},
            {"da": date(2023, 7, 1), "tasso": 0.09},
        ]
        r = mora_su_periodo(10000, scad, date(2023, 1, 1), date(2024, 1, 1))
        gg1 = (date(2023, 7, 1) - date(2023, 1, 1)).days  # 181
        gg2 = (date(2024, 1, 1) - date(2023, 7, 1)).days  # 184
        atteso = (interesse_semplice(10000, 0.06, gg1)
                  + interesse_semplice(10000, 0.09, gg2))
        assert r == pytest.approx(atteso)

    def test_periodo_nullo(self):
        assert mora_su_periodo(10000, 0.08, date(2023, 1, 1), date(2023, 1, 1)) == 0.0

    def test_verifica_riga_bassotti_gen2022(self):
        # BASSOTTI: gennaio 2022, mora 6,45%, capitale 372.535,85, 31 giorni
        # Ultralegale (mora - legale 1,25%) = 1.645,28
        C = 372535.85
        mora = mora_su_periodo(C, 0.0645, date(2022, 1, 1), date(2022, 2, 1))
        legale = interesse_semplice(C, 0.0125, 31)
        assert (mora - legale) == pytest.approx(1645.28, abs=0.01)


class TestScadenzarioNelMotore:
    def test_scalare_vs_scadenzario_singolo_equivalenti(self):
        # Uno scadenzario con un solo tasso deve dare lo stesso di uno scalare
        common = dict(
            importo_rata=800.0, data_prima_rata=date(2021, 3, 1),
            frequenza="Mensile", capitale_residuo=100000.0,
            data_decadenza_effettiva=date(2022, 1, 20),
            data_pignoramento=date(2023, 9, 10), data_fine=date(2026, 6, 30),
        )
        r_scalare = calcola_mora_unificato(**common, tasso_mora=0.08)
        r_sched = calcola_mora_unificato(
            **common, tasso_mora=[{"da": date(2000, 1, 1), "tasso": 0.08}]
        )
        assert r_scalare["ipotecario"] == pytest.approx(r_sched["ipotecario"])
        assert r_scalare["chirografario"] == pytest.approx(r_sched["chirografario"])

    def test_scadenzario_variabile_nel_motore(self):
        # Con tasso crescente, l'interesse totale deve superare quello al
        # tasso minimo e restare sotto quello al tasso massimo
        common = dict(
            importo_rata=0.0, data_prima_rata=date(2021, 3, 1),
            frequenza="Mensile", capitale_residuo=100000.0,
            data_decadenza_effettiva=date(2022, 1, 20),
            data_pignoramento=date(2023, 9, 10), data_fine=date(2025, 1, 1),
        )
        sched = [
            {"da": date(2022, 1, 1), "tasso": 0.06},
            {"da": date(2024, 1, 1), "tasso": 0.10},
        ]
        r_var = calcola_mora_unificato(**common, tasso_mora=sched)
        r_min = calcola_mora_unificato(**common, tasso_mora=0.06)
        r_max = calcola_mora_unificato(**common, tasso_mora=0.10)
        tot_var = r_var["ipotecario"] + r_var["chirografario"]
        tot_min = r_min["ipotecario"] + r_min["chirografario"]
        tot_max = r_max["ipotecario"] + r_max["chirografario"]
        assert tot_min < tot_var < tot_max
