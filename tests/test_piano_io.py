"""Test del parser piano_io.carica_piano_da_dataframe."""

from datetime import date
import io

import pandas as pd
import pytest

from piano_io import carica_piano_da_dataframe, carica_piano_da_file


def _df_standard():
    return pd.DataFrame({
        "Data Scadenza": ["01/02/2020", "01/03/2020", "01/04/2020"],
        "Quota Capitale": [800.0, 805.0, 810.0],
        "Quota Interessi": [300.0, 295.0, 290.0],
    })


class TestCaricaPianoDaDataframe:
    def test_caso_base_3_rate(self):
        piano = carica_piano_da_dataframe(_df_standard())
        assert len(piano) == 3
        assert piano[0]["data_scadenza"] == date(2020, 2, 1)
        assert piano[0]["quota_capitale"] == 800.0
        assert piano[0]["quota_interessi"] == 300.0

    def test_importo_rata_calcolato_se_mancante(self):
        piano = carica_piano_da_dataframe(_df_standard())
        # importo_rata = QC + QI = 800 + 300 = 1100
        assert piano[0]["importo_rata"] == 1100.0
        assert piano[1]["importo_rata"] == 1100.0
        assert piano[2]["importo_rata"] == 1100.0

    def test_capitale_residuo_calcolato_se_mancante(self):
        piano = carica_piano_da_dataframe(_df_standard())
        # Somma QC = 2415; dopo rata 1 → 1615; dopo rata 2 → 810; dopo rata 3 → 0
        assert piano[0]["capitale_residuo"] == pytest.approx(1615.0)
        assert piano[1]["capitale_residuo"] == pytest.approx(810.0)
        assert piano[2]["capitale_residuo"] == pytest.approx(0.0)

    def test_num_rata_auto(self):
        piano = carica_piano_da_dataframe(_df_standard())
        assert [r["num_rata"] for r in piano] == [1, 2, 3]

    def test_riconoscimento_colonne_case_insensitive(self):
        df = pd.DataFrame({
            "DATA_SCADENZA": ["01/02/2020", "01/03/2020"],
            "quota capitale": [800.0, 805.0],
            "Q. Interessi": [300.0, 295.0],
        })
        piano = carica_piano_da_dataframe(df)
        assert len(piano) == 2
        assert piano[0]["quota_capitale"] == 800.0
        assert piano[0]["quota_interessi"] == 300.0

    def test_riconoscimento_colonne_accentate(self):
        df = pd.DataFrame({
            "Scadenza": ["01/02/2020"],
            "Capitale": [800.0],
            "Interessi": [300.0],
        })
        piano = carica_piano_da_dataframe(df)
        assert piano[0]["quota_capitale"] == 800.0
        assert piano[0]["quota_interessi"] == 300.0

    def test_capitale_residuo_se_fornito_viene_usato(self):
        df = _df_standard()
        df["Capitale Residuo"] = [50000.0, 40000.0, 30000.0]
        piano = carica_piano_da_dataframe(df)
        assert piano[0]["capitale_residuo"] == 50000.0
        assert piano[2]["capitale_residuo"] == 30000.0

    def test_ordinamento_per_data(self):
        df = pd.DataFrame({
            "Data Scadenza": ["01/04/2020", "01/02/2020", "01/03/2020"],
            "Quota Capitale": [810.0, 800.0, 805.0],
            "Quota Interessi": [290.0, 300.0, 295.0],
        })
        piano = carica_piano_da_dataframe(df)
        assert piano[0]["data_scadenza"] == date(2020, 2, 1)
        assert piano[-1]["data_scadenza"] == date(2020, 4, 1)

    def test_parser_numerico_formato_italiano(self):
        # Numeri con punto migliaia e virgola decimali (formato italiano)
        df = pd.DataFrame({
            "Data Scadenza": ["01/02/2020"],
            "Quota Capitale": ["1.234,56"],
            "Quota Interessi": ["234,12"],
        })
        piano = carica_piano_da_dataframe(df)
        assert piano[0]["quota_capitale"] == pytest.approx(1234.56)
        assert piano[0]["quota_interessi"] == pytest.approx(234.12)

    def test_errore_dataframe_vuoto(self):
        with pytest.raises(ValueError, match="vuoto"):
            carica_piano_da_dataframe(pd.DataFrame())

    def test_errore_data_mancante(self):
        df = pd.DataFrame({"Quota Capitale": [100], "Quota Interessi": [10]})
        with pytest.raises(ValueError, match="Data Scadenza"):
            carica_piano_da_dataframe(df)

    def test_errore_quote_mancanti(self):
        df = pd.DataFrame({"Data Scadenza": ["01/02/2020"]})
        with pytest.raises(ValueError, match="Quota Capitale"):
            carica_piano_da_dataframe(df)

    def test_errore_date_non_parseable(self):
        df = pd.DataFrame({
            "Data Scadenza": ["data sbagliata"],
            "Quota Capitale": [100],
            "Quota Interessi": [10],
        })
        with pytest.raises(ValueError, match="date"):
            carica_piano_da_dataframe(df)


class TestCaricaPianoDaFile:
    def _fake_upload(self, name, content_bytes):
        class _FakeUpload:
            def __init__(self, name, content):
                self.name = name
                self._content = content
            def read(self):
                return self._content
            def seek(self, _):
                pass
        return _FakeUpload(name, content_bytes)

    def test_csv_punto_e_virgola(self):
        csv = b"Data Scadenza;Quota Capitale;Quota Interessi\n01/02/2020;800;300\n"
        piano = carica_piano_da_file(self._fake_upload("piano.csv", csv))
        assert len(piano) == 1
        assert piano[0]["quota_capitale"] == 800.0

    def test_csv_virgola(self):
        csv = b"Data Scadenza,Quota Capitale,Quota Interessi\n01/02/2020,800,300\n"
        piano = carica_piano_da_file(self._fake_upload("piano.csv", csv))
        assert len(piano) == 1

    def test_pdf_rifiutato_con_messaggio(self):
        with pytest.raises(ValueError, match="PDF"):
            carica_piano_da_file(self._fake_upload("piano.pdf", b"%PDF-1.4"))

    def test_formato_non_supportato(self):
        with pytest.raises(ValueError, match="Formato"):
            carica_piano_da_file(self._fake_upload("piano.txt", b"qualsiasi"))
