"""Strict accounting import. Invalid cells never become zero silently."""

import csv
import math
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.models.schemas import FinancialData, MonthlyEntry

MONTHS = [
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
]
COLUMNS = ["Compte", "Libellé", "Nature", *MONTHS, "Total"]


class DataProcessingError(ValueError):
    """An actionable validation error suitable for the import screen."""


def detect_separator(file_path: Path, encoding: str = "utf-8-sig") -> str:
    with file_path.open(encoding=encoding, newline="") as stream:
        sample = stream.read(8192)
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
    except csv.Error:
        return ";"


def validate_columns(df) -> None:
    columns = list(df.columns) if hasattr(df, "columns") else list(df)
    missing = [name for name in COLUMNS if name not in columns]
    if missing:
        raise DataProcessingError(f"Colonnes manquantes : {', '.join(missing)}")
    if len(columns) != len(set(columns)):
        raise DataProcessingError("Les noms de colonnes doivent être uniques.")


def clean_amount(value) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    text = re.sub(r"\s", "", str(value))
    if not text:
        return 0.0
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        amount = Decimal(text)
        if not amount.is_finite() or abs(amount) > Decimal("1000000000000"):
            raise InvalidOperation
        return float(amount)
    except (InvalidOperation, ValueError):
        raise DataProcessingError("Montant invalide ou hors limites.") from None


def extract_year_from_filename(filename: str) -> int:
    match = re.search(r"(?:^|[_ -])((?:19|20)\d{2})(?=[_. -]|$)", filename)
    return int(match.group(1)) if match else datetime.now().year - 1


def process_csv(
    file_path: str, year: int | None = None, encoding: str = "utf-8-sig", max_rows: int = 20000
) -> FinancialData:
    path = Path(file_path)
    if not path.is_file():
        raise DataProcessingError("Fichier CSV introuvable.")
    entries, warnings = [], []
    try:
        separator = detect_separator(path, encoding)
        with path.open(encoding=encoding, newline="") as stream:
            reader = csv.DictReader(stream, delimiter=separator, strict=True)
            headers = reader.fieldnames or []
            validate_columns(headers)
            for number, row in enumerate(reader, start=2):
                if len(entries) >= max_rows:
                    raise DataProcessingError(f"Maximum de {max_rows} lignes dépassé.")
                if None in row or any(value is None for value in row.values()):
                    raise DataProcessingError(f"Ligne {number} : nombre de cellules incorrect.")
                account, label = row["Compte"].strip(), row["Libellé"].strip()
                nature = row["Nature"].strip().capitalize()
                if not re.fullmatch(r"\d{2,12}", account) or not label or len(label) > 200:
                    raise DataProcessingError(f"Ligne {number} : compte ou libellé invalide.")
                if nature not in ("Produit", "Charge"):
                    raise DataProcessingError(
                        f"Ligne {number} : Nature doit être Produit ou Charge."
                    )
                if not account.startswith("7" if nature == "Produit" else "6"):
                    raise DataProcessingError(
                        f"Ligne {number} : compte incompatible avec la nature."
                    )
                amounts = {}
                for column in [*MONTHS, "Total"]:
                    if not row[column].strip() and len(warnings) < 100:
                        warnings.append(
                            f"Ligne {number}, {column} : cellule vide interprétée comme zéro."
                        )
                    try:
                        amounts[column] = clean_amount(row[column])
                    except DataProcessingError as exc:
                        raise DataProcessingError(f"Ligne {number}, {column} : {exc}") from None
                total = sum(Decimal(str(amounts[m])) for m in MONTHS)
                declared_total = Decimal(str(amounts["Total"]))
                if abs(total - declared_total) > Decimal("0.01") and len(warnings) < 100:
                    warnings.append(
                        f"Ligne {number} : Total déclaré ({declared_total}) différent de la "
                        f"somme des mois ({total}) — corrigé automatiquement."
                    )
                entries.append(
                    MonthlyEntry(
                        compte=account,
                        libelle=label,
                        nature=nature,
                        montants={m: amounts[m] for m in MONTHS},
                        total=float(total),
                    )
                )
    except (UnicodeError, csv.Error):
        raise DataProcessingError(
            "CSV illisible : vérifier l'encodage et les guillemets."
        ) from None
    if not entries:
        raise DataProcessingError("Le CSV ne contient aucune ligne comptable.")
    return FinancialData(
        annee=year if year is not None else extract_year_from_filename(path.name),
        entrees=entries,
        produits=[e for e in entries if e.nature == "Produit"],
        charges=[e for e in entries if e.nature == "Charge"],
        mois_disponibles=MONTHS.copy(),
        warnings=warnings,
    )
