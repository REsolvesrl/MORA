"""Test della modalità Sofferenza / Estratto conto ex art. 50 TUB.

Replica il conteggio ufficiale Triple A della posizione CAPECE / TODISCO.
Tutte le voci combaciano al centesimo tranne il triennio-legale pre-precetto,
che ha un residuo di ~4 € dovuto all'arrotondamento riga-per-riga del
redattore del conteggio (metodo non divulgato).
"""

from datetime import date

import pytest

from calcoli import (
    calcola_credito_sofferenza,
    BASE_CAPITALE_INTERESSI,
    BASE_SOLO_CAPITALE,
    TASSO_TRIENNIO_LEGALE,
    TASSO_TRIENNIO_MORA,
)


def _capece(**override):
    p = dict(
        sorte_capitale=95059.96,
        quota_interessi_congelata=12163.06,
        interessi_ante_sofferenza=1511.36,
        spese=1442.08,
        data_decorrenza=date(2021, 11, 1),
        data_precetto=date(2025, 10, 4),
        data_pignoramento=date(2026, 2, 2),
        data_aggiudicazione=date(2026, 12, 31),
        tasso_convenzionale=0.0555,
        tasso_mora=0.0755,
        anno_civile=True,
        base_legale=BASE_CAPITALE_INTERESSI,
    )
    p.update(override)
    return calcola_credito_sofferenza(**p)


class TestReplicaCapece:
    def test_inizio_triennio_anno_solare(self):
        r = _capece()
        assert r["inizio_triennio"] == date(2024, 1, 1)

    def test_pre_triennio_legale_esatto(self):
        # 01/11/2021 -> 01/01/2024 al legale su 107.223,02 = 6.703,23
        r = _capece()
        assert r["chirografario"]["pre_triennio_legale"] == pytest.approx(6703.23, abs=0.01)

    def test_convenzionale_esatto_31_12(self):
        # Tabella A 5,55% su 95.059,96 fino al 31/12/2026 = 6.547,81
        r = _capece()
        assert r["ipotecario"]["triennio_post_precetto"] == pytest.approx(6547.81, abs=0.02)

    def test_convenzionale_esatto_31_07(self):
        r = _capece(data_aggiudicazione=date(2026, 7, 31))
        assert r["ipotecario"]["triennio_post_precetto"] == pytest.approx(4336.30, abs=0.02)

    def test_voci_congelate(self):
        r = _capece()
        assert r["chirografario"]["quota_interessi_congelata"] == 12163.06
        assert r["chirografario"]["interessi_ante_sofferenza"] == 1511.36

    def test_totale_chirografo_esatto(self):
        r = _capece()
        assert r["chirografario"]["totale"] == pytest.approx(20377.65, abs=0.01)

    def test_triennio_legale_pre_precetto_vicino(self):
        # Residuo ~4 € da arrotondamento mensile del redattore (4.298,37)
        r = _capece()
        assert r["ipotecario"]["triennio_pre_precetto"] == pytest.approx(4298.37, abs=5.0)

    def test_totale_credito_entro_residuo(self):
        # 127.725,87 con residuo < 5 € (solo dal triennio-legale)
        r = _capece()
        assert r["totale_credito"] == pytest.approx(127725.87, abs=5.0)

    def test_somma_intimata(self):
        # Con aggiudicazione = precetto la somma intimata è quella del precetto.
        # Qui verifichiamo la componibilità: sorte+congelate+legali+spese.
        r = _capece()
        # somma intimata calcolata internamente (fino al precetto)
        assert r["somma_intimata"] == pytest.approx(121178.06, abs=5.0)


class TestLeveContestazione:
    def test_base_solo_capitale_riduce_credito(self):
        r_prassi = _capece(base_legale=BASE_CAPITALE_INTERESSI)
        r_conte = _capece(base_legale=BASE_SOLO_CAPITALE)
        # la variante ortodossa (solo capitale) costa meno
        assert r_conte["totale_credito"] < r_prassi["totale_credito"]

    def test_extra_anatocismo_quantificato(self):
        # differenza legale(cap+int) - legale(solo cap) ~ 1.248 €
        r = _capece()
        assert r["confronto_anatocismo"]["extra"] == pytest.approx(1248.42, abs=1.0)

    def test_tasso_triennio_mora_aumenta_ipotecario(self):
        r_legale = _capece(tasso_triennio=TASSO_TRIENNIO_LEGALE)
        r_mora = _capece(tasso_triennio=TASSO_TRIENNIO_MORA)
        # con la mora sul triennio pre-precetto l'ipotecario cresce
        assert r_mora["ipotecario"]["triennio_pre_precetto"] > r_legale["ipotecario"]["triennio_pre_precetto"]


class TestQuadratura:
    def test_ipo_piu_chiro_uguale_totale(self):
        r = _capece()
        somma = r["ipotecario"]["totale"] + r["chirografario"]["totale"]
        assert somma == pytest.approx(r["totale_credito"], abs=0.01)
