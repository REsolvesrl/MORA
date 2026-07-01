"""Test della logica di calcolo in calcoli.py."""

from datetime import date

import pytest

from calcoli import (
    TASSI_LEGALI,
    TASSO_LEGALE_DEFAULT,
    calcola_mora_unificato,
    calcola_triennio,
    estrai_rate_insolute_da_piano,
    genera_piano_ammortamento,
    genera_rate_scadute,
    giorni_tra,
    interesse_legale_pro_rata,
    interesse_semplice,
    ripartisci_credito,
    stima_spese_esecutive,
    tasso_legale_per_anno,
)


# ==========================================================
# Utilità temporali
# ==========================================================

class TestGiorniTra:
    def test_un_giorno(self):
        assert giorni_tra(date(2024, 1, 1), date(2024, 1, 2)) == 1

    def test_anno_bisestile(self):
        assert giorni_tra(date(2024, 1, 1), date(2025, 1, 1)) == 366

    def test_anno_non_bisestile(self):
        assert giorni_tra(date(2023, 1, 1), date(2024, 1, 1)) == 365

    def test_stessa_data(self):
        assert giorni_tra(date(2024, 6, 15), date(2024, 6, 15)) == 0


class TestInteresseSemplice:
    def test_un_anno_intero(self):
        # 1000 € al 10% per 365 giorni = 100 €
        assert interesse_semplice(1000, 0.10, 365) == pytest.approx(100.0)

    def test_sei_mesi(self):
        # 1000 € al 5% per 180 giorni = 1000 * 0.05 * 180/365
        assert interesse_semplice(1000, 0.05, 180) == pytest.approx(
            1000 * 0.05 * 180 / 365
        )

    def test_giorni_zero(self):
        assert interesse_semplice(1000, 0.10, 0) == 0.0

    def test_giorni_negativi(self):
        assert interesse_semplice(1000, 0.10, -5) == 0.0

    def test_capitale_zero(self):
        assert interesse_semplice(0, 0.10, 100) == 0.0

    def test_capitale_negativo(self):
        assert interesse_semplice(-100, 0.10, 100) == 0.0

    def test_base_anno_personalizzata(self):
        # base 360 invece di 365
        assert interesse_semplice(1000, 0.10, 360, base_anno=360) == pytest.approx(100.0)


class TestTassoLegalePerAnno:
    def test_anno_in_tabella(self):
        assert tasso_legale_per_anno(2024) == TASSI_LEGALI[2024]
        assert tasso_legale_per_anno(2026) == TASSI_LEGALI[2026]

    def test_anno_fuori_tabella_passato(self):
        assert tasso_legale_per_anno(1990) == TASSO_LEGALE_DEFAULT

    def test_anno_fuori_tabella_futuro(self):
        assert tasso_legale_per_anno(2050) == TASSO_LEGALE_DEFAULT


class TestInteresseLegaleProRata:
    def test_dentro_singolo_anno(self):
        # 1000 € dal 1/2/2024 al 1/3/2024 (29 giorni, anno 2024 bisestile)
        # tasso 2024 = 0.0250. Anno civile (default) → divisore 366.
        atteso = 1000 * 0.0250 * 29 / 366
        totale, segmenti = interesse_legale_pro_rata(
            1000, date(2024, 2, 1), date(2024, 3, 1)
        )
        assert totale == pytest.approx(atteso)
        assert len(segmenti) == 1
        assert segmenti[0]["inizio"] == date(2024, 2, 1)
        assert segmenti[0]["fine"] == date(2024, 3, 1)
        assert segmenti[0]["giorni"] == 29
        assert segmenti[0]["tasso"] == 0.0250
        assert segmenti[0]["base"] == 366
        assert segmenti[0]["interesse"] == pytest.approx(atteso)

    def test_anno_civile_false_usa_365(self):
        # Con anno_civile=False il divisore resta 365 anche nel bisestile
        atteso = 1000 * 0.0250 * 29 / 365
        totale, segmenti = interesse_legale_pro_rata(
            1000, date(2024, 2, 1), date(2024, 3, 1), anno_civile=False
        )
        assert totale == pytest.approx(atteso)
        assert segmenti[0]["base"] == 365

    def test_a_cavallo_di_capodanno(self):
        # 1000 € dal 1/7/2024 al 1/7/2025
        # 2024 (0.0250, bisestile /366) 184 gg + 2025 (0.0200, /365) 181 gg
        atteso = 1000 * 0.0250 * 184 / 366 + 1000 * 0.0200 * 181 / 365
        totale, segmenti = interesse_legale_pro_rata(
            1000, date(2024, 7, 1), date(2025, 7, 1)
        )
        assert totale == pytest.approx(atteso)
        assert len(segmenti) == 2
        # Primo segmento: 2024 (bisestile → base 366)
        assert segmenti[0]["inizio"] == date(2024, 7, 1)
        assert segmenti[0]["fine"] == date(2025, 1, 1)
        assert segmenti[0]["giorni"] == 184
        assert segmenti[0]["tasso"] == 0.0250
        assert segmenti[0]["base"] == 366
        # Secondo segmento: 2025 (base 365)
        assert segmenti[1]["inizio"] == date(2025, 1, 1)
        assert segmenti[1]["fine"] == date(2025, 7, 1)
        assert segmenti[1]["giorni"] == 181
        assert segmenti[1]["tasso"] == 0.0200
        assert segmenti[1]["base"] == 365

    def test_tre_anni_solari(self):
        # 1000 € dal 15/06/2024 al 30/06/2026 (data_fine ESCLUSA)
        # 2024 (0.0250, /366): 15/06 → 01/01/2025 = 200 gg
        # 2025 (0.0200, /365): 01/01 → 01/01/2026 = 365 gg
        # 2026 (0.0160, /365): 01/01 → 30/06/2026 = 180 gg (esclude il 30/06)
        totale, segmenti = interesse_legale_pro_rata(
            1000, date(2024, 6, 15), date(2026, 6, 30)
        )
        assert len(segmenti) == 3
        assert segmenti[0]["giorni"] == 200
        assert segmenti[0]["tasso"] == 0.0250
        assert segmenti[0]["base"] == 366
        assert segmenti[1]["giorni"] == 365
        assert segmenti[1]["tasso"] == 0.0200
        assert segmenti[1]["base"] == 365
        assert segmenti[2]["giorni"] == 180
        assert segmenti[2]["tasso"] == 0.0160
        atteso = (
            1000 * 0.0250 * 200 / 366
            + 1000 * 0.0200 * 365 / 365
            + 1000 * 0.0160 * 180 / 365
        )
        assert totale == pytest.approx(atteso)

    def test_data_fine_uguale_inizio(self):
        totale, segmenti = interesse_legale_pro_rata(
            1000, date(2024, 1, 1), date(2024, 1, 1)
        )
        assert totale == 0.0
        assert segmenti == []


# ==========================================================
# Generazione rate
# ==========================================================

class TestGeneraRateScadute:
    def test_mensile(self):
        rate = genera_rate_scadute(100, date(2024, 1, 1), "Mensile", date(2024, 4, 1))
        assert len(rate) == 3
        assert [r["data_scadenza"] for r in rate] == [
            date(2024, 1, 1), date(2024, 2, 1), date(2024, 3, 1)
        ]

    def test_trimestrale(self):
        rate = genera_rate_scadute(100, date(2024, 1, 1), "Trimestrale", date(2024, 12, 1))
        assert len(rate) == 4
        assert [r["data_scadenza"] for r in rate] == [
            date(2024, 1, 1), date(2024, 4, 1), date(2024, 7, 1), date(2024, 10, 1)
        ]

    def test_semestrale(self):
        rate = genera_rate_scadute(100, date(2024, 1, 1), "Semestrale", date(2025, 1, 1))
        assert len(rate) == 2
        assert [r["data_scadenza"] for r in rate] == [
            date(2024, 1, 1), date(2024, 7, 1)
        ]

    def test_data_limite_prima_della_prima_rata(self):
        rate = genera_rate_scadute(100, date(2024, 6, 1), "Mensile", date(2024, 1, 1))
        assert rate == []

    def test_importo_riportato_correttamente(self):
        rate = genera_rate_scadute(500, date(2024, 1, 1), "Mensile", date(2024, 3, 1))
        assert all(r["importo"] == 500 for r in rate)


# ==========================================================
# Calcolo del triennio garantito (3 anni a ritroso dal pignoramento)
# ==========================================================

class TestCalcolaTriennio:
    def test_esempio_da_specifica(self):
        # Esempio dato dall'utente: pignoramento 16/12/2021
        # → triennio 16/12/2018 → 16/12/2021
        inizio_t, fine_t = calcola_triennio(date(2021, 12, 16))
        assert inizio_t == date(2018, 12, 16)
        assert fine_t == date(2021, 12, 16)

    def test_caso_default_app(self):
        # Pignoramento 10/09/2023 → triennio 10/09/2020 → 10/09/2023
        inizio_t, fine_t = calcola_triennio(date(2023, 9, 10))
        assert inizio_t == date(2020, 9, 10)
        assert fine_t == date(2023, 9, 10)

    def test_durata_in_giorni_senza_bisestile(self):
        # Triennio 01/03/2017 → 01/03/2020 attraversa solo il 29/02/2020,
        # ma in modo che il computo (years=3) includa 1 anno bisestile
        # → 365 + 365 + 366 = 1096 giorni
        inizio_t, fine_t = calcola_triennio(date(2020, 3, 1))
        assert (fine_t - inizio_t).days == 1096

    def test_durata_in_giorni_con_bisestile(self):
        # Triennio 01/01/2021 → 01/01/2024 attraversa 29/02/2024? No,
        # il 29/02/2024 è dentro il 2024 ma il triennio finisce all'1/1/2024
        # → 365 (2021) + 365 (2022) + 365 (2023) = 1095 giorni
        inizio_t, fine_t = calcola_triennio(date(2024, 1, 1))
        assert (fine_t - inizio_t).days == 1095

    def test_durata_sempre_1095_o_1096(self):
        # Su qualunque data il triennio dura 1095 o 1096 giorni
        for d in [date(2020, 5, 1), date(2025, 2, 28), date(2024, 7, 15),
                  date(2023, 12, 31), date(2022, 3, 1)]:
            inizio_t, fine_t = calcola_triennio(d)
            assert (fine_t - inizio_t).days in (1095, 1096), (
                f"Durata fuori range per {d}: {(fine_t - inizio_t).days}"
            )


# ==========================================================
# Ripartizione ipotecario / chirografario
# ==========================================================

class TestRipartisciCredito:
    # Setup comune: pignoramento 10/09/2023 → triennio 10/09/2020 → 10/09/2023
    DATA_PIGN = date(2023, 9, 10)

    def test_solo_post_triennio(self):
        # data_inizio_mora dopo il pignoramento → solo Fase 3
        r = ripartisci_credito(
            capitale=10000,
            tasso_mora=0.10,
            data_inizio_mora=date(2024, 7, 1),
            data_pignoramento=self.DATA_PIGN,
            data_fine=date(2025, 3, 1),
        )
        assert "pre_triennio_chiro" not in r["dettaglio"]
        assert "triennio_ipo_mora" not in r["dettaglio"]
        assert "post_ipo_legale" in r["dettaglio"]
        assert "post_chiro_diff" in r["dettaglio"]
        assert "post_segmenti_legale" in r["dettaglio"]
        # Lo spaccato deve coprire 2024 (parziale) e 2025 (parziale)
        segmenti = r["dettaglio"]["post_segmenti_legale"]
        assert len(segmenti) == 2
        assert segmenti[0]["tasso"] == 0.0250  # 2024
        assert segmenti[1]["tasso"] == 0.0200  # 2025
        assert r["ipotecario"] > 0
        assert r["chirografario"] > 0

    def test_solo_triennio(self):
        # data_inizio_mora dentro il triennio, data_fine dentro il triennio
        # → tutto Fase 2 (ipotecario @ mora)
        r = ripartisci_credito(
            capitale=10000,
            tasso_mora=0.10,
            data_inizio_mora=date(2022, 1, 1),
            data_pignoramento=self.DATA_PIGN,
            data_fine=date(2023, 6, 1),
        )
        assert "pre_triennio_chiro" not in r["dettaglio"]
        assert "triennio_ipo_mora" in r["dettaglio"]
        assert "post_ipo_legale" not in r["dettaglio"]
        # Tutto ipotecario @ tasso mora
        assert r["chirografario"] == pytest.approx(0.0)
        assert r["ipotecario"] > 0

    def test_solo_pre_triennio(self):
        # data_inizio_mora e data_fine entrambe PRIMA del triennio
        # (triennio inizia 10/09/2020) → tutto Fase 1 (chirografario @ mora)
        r = ripartisci_credito(
            capitale=10000,
            tasso_mora=0.10,
            data_inizio_mora=date(2018, 1, 1),
            data_pignoramento=self.DATA_PIGN,
            data_fine=date(2019, 1, 1),
        )
        assert "pre_triennio_chiro" in r["dettaglio"]
        assert "triennio_ipo_mora" not in r["dettaglio"]
        assert "post_ipo_legale" not in r["dettaglio"]
        assert r["ipotecario"] == pytest.approx(0.0)
        assert r["chirografario"] > 0

    def test_attraversa_tutte_le_fasi(self):
        # data_inizio_mora ben prima del triennio, data_fine ben dopo il pignoramento
        # → presenti tutte e tre le fasi
        r = ripartisci_credito(
            capitale=10000,
            tasso_mora=0.10,
            data_inizio_mora=date(2018, 1, 1),
            data_pignoramento=self.DATA_PIGN,
            data_fine=date(2026, 6, 30),
        )
        assert "pre_triennio_chiro" in r["dettaglio"]
        assert "triennio_ipo_mora" in r["dettaglio"]
        assert "post_ipo_legale" in r["dettaglio"]
        assert "post_segmenti_legale" in r["dettaglio"]

    def test_confini_esatti_triennio(self):
        # Pignoramento 16/12/2021 → triennio 16/12/2018 → 16/12/2021
        # data_inizio_mora = 16/12/2018 (giorno esatto inizio triennio)
        # data_fine = 16/12/2021 (giorno esatto fine triennio)
        # → tutto Fase 2, nessun pre, nessun post
        # anno_civile=False per confrontare con la formula 365 fissa semplice.
        r = ripartisci_credito(
            capitale=10000,
            tasso_mora=0.10,
            data_inizio_mora=date(2018, 12, 16),
            data_pignoramento=date(2021, 12, 16),
            data_fine=date(2021, 12, 16),
            anno_civile=False,
        )
        assert "pre_triennio_chiro" not in r["dettaglio"]
        assert "triennio_ipo_mora" in r["dettaglio"]
        assert "post_ipo_legale" not in r["dettaglio"]
        # Triennio = 1096 giorni (include 29/02/2020)
        gg_attesi = 1096
        atteso = interesse_semplice(10000, 0.10, gg_attesi)
        assert r["ipotecario"] == pytest.approx(atteso)

    def test_quadratura_totale(self):
        # La somma di ipotecario + chirografario deve coincidere con la mora
        # complessiva a tasso pieno sull'intero periodo.
        # anno_civile=False per confronto diretto con interesse_semplice (365).
        capitale = 10000
        tasso_mora = 0.08
        data_inizio = date(2020, 1, 1)
        data_fine = date(2025, 1, 1)
        r = ripartisci_credito(
            capitale=capitale,
            tasso_mora=tasso_mora,
            data_inizio_mora=data_inizio,
            data_pignoramento=self.DATA_PIGN,
            data_fine=data_fine,
            anno_civile=False,
        )
        gg = giorni_tra(data_inizio, data_fine)
        mora_piena = interesse_semplice(capitale, tasso_mora, gg)
        assert r["ipotecario"] + r["chirografario"] == pytest.approx(mora_piena, rel=1e-9)


# ==========================================================
# Motore unificato
# ==========================================================

class TestCalcolaMoraUnificato:
    def _chiama_default(self):
        # Stessi valori di default dell'app (Tab 1)
        return calcola_mora_unificato(
            importo_rata=800.0,
            data_prima_rata=date(2021, 3, 1),
            frequenza="Mensile",
            capitale_residuo=100000.0,
            tasso_mora=0.08,
            data_decadenza_effettiva=date(2022, 1, 20),
            data_pignoramento=date(2023, 9, 10),
            data_fine=date(2026, 6, 30),
        )

    def test_struttura_output(self):
        r = self._chiama_default()
        assert set(r.keys()) == {"ipotecario", "chirografario", "dettaglio", "voci_2855"}
        assert set(r["voci_2855"].keys()) == {
            "pre_chiro", "triennio_ipo", "post_ipo", "post_chiro"
        }

    def test_quadratura_voci_2855(self):
        r = self._chiama_default()
        somma = sum(r["voci_2855"].values())
        assert somma == pytest.approx(r["ipotecario"] + r["chirografario"], rel=1e-9)

    def test_numero_rate_generate(self):
        # Dal 1/3/2021 al 20/1/2022 mensile = 11 rate (mar, apr, ..., gen)
        r = self._chiama_default()
        assert r["dettaglio"]["FASE_1_rate"]["numero_rate_generate"] == 11

    def test_totali_positivi(self):
        r = self._chiama_default()
        assert r["ipotecario"] > 0
        assert r["chirografario"] > 0


# ==========================================================
# Piano di ammortamento (alla francese)
# ==========================================================

class TestGeneraPianoAmmortamento:
    def test_numero_rate_mensile(self):
        # 240 mesi mensili → 240 rate
        piano = genera_piano_ammortamento(
            capitale=100000, tan=0.04, durata_mesi=240,
            frequenza="Mensile", data_erogazione=date(2018, 6, 15),
        )
        assert len(piano) == 240

    def test_numero_rate_trimestrale(self):
        # 240 mesi trimestrali → 80 rate
        piano = genera_piano_ammortamento(
            capitale=100000, tan=0.04, durata_mesi=240,
            frequenza="Trimestrale", data_erogazione=date(2018, 6, 15),
        )
        assert len(piano) == 80

    def test_somma_quote_capitale_uguale_a_capitale_erogato(self):
        # Invariante fondamentale dell'ammortamento alla francese
        piano = genera_piano_ammortamento(
            capitale=100000, tan=0.04, durata_mesi=240,
            frequenza="Mensile", data_erogazione=date(2018, 6, 15),
        )
        somma_qc = sum(r["quota_capitale"] for r in piano)
        assert somma_qc == pytest.approx(100000.0, abs=0.01)

    def test_capitale_residuo_ultima_rata_zero(self):
        piano = genera_piano_ammortamento(
            capitale=50000, tan=0.05, durata_mesi=120,
            frequenza="Mensile", data_erogazione=date(2020, 1, 1),
        )
        assert piano[-1]["capitale_residuo"] == pytest.approx(0.0, abs=0.01)

    def test_quota_capitale_cresce_quota_interessi_decresce(self):
        # Caratteristica dell'ammortamento alla francese
        piano = genera_piano_ammortamento(
            capitale=100000, tan=0.04, durata_mesi=240,
            frequenza="Mensile", data_erogazione=date(2020, 1, 1),
        )
        # Confronto prima e ultima rata pre-aggiustamento
        assert piano[0]["quota_capitale"] < piano[-2]["quota_capitale"]
        assert piano[0]["quota_interessi"] > piano[-2]["quota_interessi"]

    def test_prima_rata_scade_dopo_un_periodo(self):
        piano = genera_piano_ammortamento(
            capitale=100000, tan=0.04, durata_mesi=12,
            frequenza="Mensile", data_erogazione=date(2020, 1, 1),
        )
        # Mensile: prima rata = 1/2/2020
        assert piano[0]["data_scadenza"] == date(2020, 2, 1)
        # Ultima rata = 1/1/2021
        assert piano[-1]["data_scadenza"] == date(2021, 1, 1)

    def test_tan_zero_rata_costante_uguale_capitale_su_n(self):
        piano = genera_piano_ammortamento(
            capitale=12000, tan=0.0, durata_mesi=12,
            frequenza="Mensile", data_erogazione=date(2020, 1, 1),
        )
        for r in piano:
            assert r["quota_interessi"] == pytest.approx(0.0)
            assert r["quota_capitale"] == pytest.approx(1000.0, abs=0.01)


class TestEstraiRateInsoluteDaPiano:
    def test_filtro_per_periodo(self):
        piano = genera_piano_ammortamento(
            capitale=100000, tan=0.04, durata_mesi=24,
            frequenza="Mensile", data_erogazione=date(2020, 1, 1),
        )
        # rate da 1/3/2021 a 1/1/2022 (mensili) = 11 rate
        insolute = estrai_rate_insolute_da_piano(
            piano, date(2021, 3, 1), date(2022, 1, 20)
        )
        assert len(insolute) == 11
        assert insolute[0]["data_scadenza"] == date(2021, 3, 1)
        assert insolute[-1]["data_scadenza"] == date(2022, 1, 1)

    def test_periodo_vuoto(self):
        piano = genera_piano_ammortamento(
            capitale=100000, tan=0.04, durata_mesi=24,
            frequenza="Mensile", data_erogazione=date(2020, 1, 1),
        )
        # finestra che non interseca alcuna rata
        insolute = estrai_rate_insolute_da_piano(
            piano, date(2025, 1, 1), date(2025, 12, 1)
        )
        assert insolute == []


# ==========================================================
# Integrazione: calcola_mora_unificato con piano
# ==========================================================

class TestMoraConPianoAmmortamento:
    """
    Verifica che, passando il piano, la mora di Fase 1 venga calcolata
    SOLO sulla quota capitale (anti-anatocismo art. 1283 c.c.) e che
    sia strettamente inferiore al calcolo sull'intera rata.
    """
    def test_mora_su_quota_capitale_minore_che_su_rata_intera(self):
        piano = genera_piano_ammortamento(
            capitale=100000, tan=0.04, durata_mesi=240,
            frequenza="Mensile", data_erogazione=date(2018, 6, 15),
        )
        common = dict(
            importo_rata=800.0,
            data_prima_rata=date(2021, 3, 1),
            frequenza="Mensile",
            capitale_residuo=0.0,  # isola la Fase 1
            tasso_mora=0.08,
            data_decadenza_effettiva=date(2022, 1, 20),
            data_pignoramento=date(2023, 9, 10),
            data_fine=date(2022, 1, 20),
        )
        r_senza = calcola_mora_unificato(**common, piano_ammortamento=None)
        r_con = calcola_mora_unificato(**common, piano_ammortamento=piano)
        totale_senza = r_senza["ipotecario"] + r_senza["chirografario"]
        totale_con = r_con["ipotecario"] + r_con["chirografario"]
        # La mora calcolata sulla sola quota capitale deve essere minore
        # (la quota capitale di un mutuo alla francese all'inizio è < importo rata)
        assert totale_con < totale_senza
        assert totale_con > 0

    def test_quote_interessi_tracciate(self):
        piano = genera_piano_ammortamento(
            capitale=100000, tan=0.04, durata_mesi=240,
            frequenza="Mensile", data_erogazione=date(2018, 6, 15),
        )
        r = calcola_mora_unificato(
            importo_rata=800.0,
            data_prima_rata=date(2021, 3, 1),
            frequenza="Mensile",
            capitale_residuo=0.0,
            tasso_mora=0.08,
            data_decadenza_effettiva=date(2022, 1, 20),
            data_pignoramento=date(2023, 9, 10),
            data_fine=date(2022, 1, 20),
            piano_ammortamento=piano,
        )
        fase1 = r["dettaglio"]["FASE_1_rate"]
        assert fase1["usa_piano_ammortamento"] is True
        # Le quote interessi tracciate devono essere > 0 (mutuo @ 4% TAN)
        assert fase1["quote_interessi_messe_da_parte"] > 0
        # Il breakdown deve contenere i campi nuovi
        primo = fase1["rate_breakdown"][0]
        assert "quota_capitale" in primo
        assert "quota_interessi" in primo
        assert "num_rata_piano" in primo
        assert primo["num_rata_piano"] is not None


# ==========================================================
# Stima spese esecutive
# ==========================================================

class TestStimaSpeseEsecutive:
    def test_immobiliare_custode_forfait(self):
        # Valore basso → forfait 4000 batte 3% del valore
        voci, totale = stima_spese_esecutive("Pignoramento Immobiliare", valore_bene=100000)
        assert voci["Custode / Professionista delegato"] == 4000.0
        # 800 + 3500 + 4000 + 1500 + 2600
        assert totale == pytest.approx(12400.0)

    def test_immobiliare_custode_percentuale(self):
        # Valore alto → 3% batte il forfait
        voci, totale = stima_spese_esecutive("Pignoramento Immobiliare", valore_bene=200000)
        assert voci["Custode / Professionista delegato"] == pytest.approx(6000.0)
        # 800 + 3500 + 6000 + 1500 + 2600
        assert totale == pytest.approx(14400.0)

    def test_mobiliare(self):
        voci, totale = stima_spese_esecutive("Pignoramento Mobiliare", valore_bene=10000)
        # 150 + 500 + 2600
        assert totale == pytest.approx(3250.0)
        assert "CTU (perizia di stima)" not in voci

    def test_presso_terzi_usa_stessa_logica_mobiliare(self):
        voci_m, _ = stima_spese_esecutive("Pignoramento Mobiliare", valore_bene=0)
        voci_t, _ = stima_spese_esecutive("Pignoramento Presso Terzi", valore_bene=0)
        assert voci_m == voci_t
