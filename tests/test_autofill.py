"""Test del modulo autofill (fallback regex e schema)."""

from datetime import date

import pytest

from autofill import (
    SCHEMA_CHIAVI,
    _dict_vuoto,
    _estrai_via_regex,
    _normalizza_output,
    extract_data_from_legal_text,
)


class TestSchema:
    def test_schema_ha_tutte_le_chiavi(self):
        d = _dict_vuoto()
        assert set(d.keys()) == set(SCHEMA_CHIAVI)
        for v in d.values():
            assert v is None

    def test_normalizza_output_riempie_chiavi_mancanti(self):
        parziale = {"tasso_mora": 0.08, "capitale_originario": 200000.0}
        norm = _normalizza_output(parziale)
        assert set(norm.keys()) == set(SCHEMA_CHIAVI)
        assert norm["tasso_mora"] == 0.08
        assert norm["capitale_originario"] == 200000.0
        assert norm["data_stipula"] is None

    def test_normalizza_output_parsing_date_iso(self):
        d = _normalizza_output({"data_stipula": "2018-06-15"})
        assert d["data_stipula"] == date(2018, 6, 15)

    def test_normalizza_output_data_invalida_diventa_none(self):
        d = _normalizza_output({"data_stipula": "non è una data"})
        assert d["data_stipula"] is None

    def test_normalizza_output_frequenza_solo_valori_ammessi(self):
        assert _normalizza_output({"frequenza_rate": "Mensile"})["frequenza_rate"] == "Mensile"
        assert _normalizza_output({"frequenza_rate": "mensile"})["frequenza_rate"] == "Mensile"
        assert _normalizza_output({"frequenza_rate": "settimanale"})["frequenza_rate"] is None

    def test_normalizza_output_dict_non_dict(self):
        d = _normalizza_output(None)
        assert set(d.keys()) == set(SCHEMA_CHIAVI)
        d = _normalizza_output("stringa")
        assert set(d.keys()) == set(SCHEMA_CHIAVI)


class TestRegexFallback:
    def test_estrae_data_pignoramento(self):
        testo = (
            "Con atto di pignoramento del 16/12/2021, notificato al debitore..."
        )
        r = _estrai_via_regex(testo)
        assert r["data_pignoramento"] == date(2021, 12, 16)

    def test_estrae_capitale_originario(self):
        testo = "Capitale originario € 200.000,00 erogato in data..."
        r = _estrai_via_regex(testo)
        assert r["capitale_originario"] == pytest.approx(200000.0)

    def test_estrae_tasso_mora(self):
        testo = "Il tasso di mora è pattuito nella misura del 8,50% annuo."
        r = _estrai_via_regex(testo)
        assert r["tasso_mora"] == pytest.approx(0.085)

    def test_estrae_tan(self):
        testo = "Tasso Annuo Nominale (TAN) del 4,50% ..."
        r = _estrai_via_regex(testo)
        assert r["tan"] == pytest.approx(0.045)

    def test_frequenza_mensile(self):
        r = _estrai_via_regex("Rate mensili di importo...")
        assert r["frequenza_rate"] == "Mensile"

    def test_frequenza_trimestrale(self):
        r = _estrai_via_regex("Rimborso in rate trimestrali costanti...")
        assert r["frequenza_rate"] == "Trimestrale"

    def test_riconosce_dbt(self):
        testo = "...comunicazione di decadenza dal beneficio del termine..."
        r = _estrai_via_regex(testo)
        assert r["is_caso_A"] is True

    def test_riconosce_precetto(self):
        testo = "Con atto di precetto notificato..."
        r = _estrai_via_regex(testo)
        assert r["is_caso_A"] is False

    def test_testo_vuoto_ritorna_none_ovunque(self):
        r = _estrai_via_regex("")
        for v in r.values():
            assert v is None


class TestApiPubblica:
    def test_extract_senza_key_usa_regex(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        testo = "Atto di pignoramento del 15/06/2023, tasso di mora 8,00%."
        dati, modalita = extract_data_from_legal_text(testo)
        assert modalita == "regex-fallback"
        assert dati["data_pignoramento"] == date(2023, 6, 15)
        assert dati["tasso_mora"] == pytest.approx(0.08)

    def test_extract_testo_vuoto_ritorna_dict_vuoto(self):
        dati, modalita = extract_data_from_legal_text("")
        assert dati == _dict_vuoto()

    def test_extract_ritorna_tutte_le_chiavi_schema(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        dati, _ = extract_data_from_legal_text("testo senza dati significativi")
        assert set(dati.keys()) == set(SCHEMA_CHIAVI)
