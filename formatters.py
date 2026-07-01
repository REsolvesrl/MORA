"""
Formattazione numerica in stile italiano — modulo condiviso.

I calcoli interni usano sempre float puri (massima precisione).
Queste funzioni sono usate solo per il rendering a schermo / su PDF.
"""

from datetime import date, datetime


def fmt_eur(x, decimali=2):
    """Formatta un float come importo in euro stile italiano: '1.234,56 €'.

    Esempi: 1234.56 -> '1.234,56 €' ; 150000.5 -> '150.000,50 €'.
    """
    s = f"{x:,.{decimali}f}"                     # '1,234.56' (stile US)
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{s} €"


def fmt_pct(x, decimali=2):
    """Formatta una frazione decimale come percentuale italiana: 0.085 -> '8,50%'."""
    s = f"{x * 100:.{decimali}f}"
    return f"{s.replace('.', ',')}%"


def fmt_data(d):
    """Formatta una data come gg/mm/aaaa. Passa attraverso stringhe/None."""
    if isinstance(d, (date, datetime)):
        return d.strftime("%d/%m/%Y")
    return str(d) if d is not None else ""
