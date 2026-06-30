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

    def test_pdf_invalido_rifiutato(self):
        # PDF "rotto" (solo magic header, niente tabelle) → ValueError
        with pytest.raises(ValueError):
            carica_piano_da_file(self._fake_upload("piano.pdf", b"%PDF-1.4\n"))

    def test_formato_non_supportato(self):
        with pytest.raises(ValueError, match="Formato"):
            carica_piano_da_file(self._fake_upload("piano.txt", b"qualsiasi"))


class TestCaricaPianoDaPdf:
    """Test del parser PDF tramite generazione on-the-fly con reportlab."""

    def _genera_pdf_piano(self, n_rate=12, multi_pagina=False):
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, PageBreak,
        )
        from reportlab.lib import colors

        header = ["Num. Rata", "Data Scadenza", "Quota Capitale",
                  "Quota Interessi", "Capitale Residuo"]
        righe_tot = []
        residuo = 200000.0
        for i in range(1, n_rate + 1):
            qc = 500 + i * 5
            qi = 700 - i * 5
            residuo -= qc
            righe_tot.append([
                str(i),
                f"01/{((i - 1) % 12) + 1:02d}/{2020 + (i - 1) // 12}",
                f"{qc:.2f}", f"{qi:.2f}", f"{residuo:.2f}",
            ])
        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4)
        elementi = []
        stride = 10 if multi_pagina else n_rate
        for start in range(0, n_rate, stride):
            blocco = [header] + righe_tot[start:start + stride]
            tbl = Table(blocco)
            tbl.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ]))
            elementi.append(tbl)
            if multi_pagina and start + stride < n_rate:
                elementi.append(PageBreak())
        doc.build(elementi)
        return buf.getvalue()

    def _fake(self, name, data):
        class _F:
            def __init__(self, n, d):
                self.name = n
                self._d = d
            def read(self):
                return self._d
        return _F(name, data)

    def test_pdf_singola_pagina(self):
        from piano_io import carica_piano_da_pdf
        pdf_bytes = self._genera_pdf_piano(n_rate=12)
        piano = carica_piano_da_pdf(self._fake("piano.pdf", pdf_bytes))
        assert len(piano) == 12
        assert piano[0]["quota_capitale"] == 505.0
        assert piano[-1]["quota_capitale"] == 560.0

    def test_pdf_multi_pagina_con_header_ripetuto(self):
        from piano_io import carica_piano_da_pdf
        pdf_bytes = self._genera_pdf_piano(n_rate=30, multi_pagina=True)
        piano = carica_piano_da_pdf(self._fake("piano.pdf", pdf_bytes))
        assert len(piano) == 30
        # Verifica continuità numeri rata
        assert [r["num_rata"] for r in piano] == list(range(1, 31))

    def test_pdf_senza_tabelle_riconoscibili(self):
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
        from piano_io import carica_piano_da_pdf

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4)
        doc.build([Paragraph("Solo testo, niente tabella.",
                             getSampleStyleSheet()["Normal"])])
        with pytest.raises(ValueError, match="tabella"):
            carica_piano_da_pdf(self._fake("nientab.pdf", buf.getvalue()))
