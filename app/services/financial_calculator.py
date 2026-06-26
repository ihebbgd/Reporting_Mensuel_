import asyncio
import logging

from app.config import settings
from app.models.schemas import AnomalyRecord, FinancialData, KPIResult

logger = logging.getLogger(__name__)


CHARGE_CATEGORIES = {
    "Achats (60xxx)": "60",
    "Services ext. (61xxx)": "61",
    "Autres services (62xxx)": "62",
    "Personnel (63xxx)": "63",
    "Impôts & taxes (64xxx)": "64",
    "Charges financières (65xxx)": "65",
    "Amortissements (68xxx)": "68",
}


def _by_prefix(entries: list, prefix: str) -> list:
    return [e for e in entries if e.compte.startswith(prefix)]


def _safe_pct(numerator: float, denominator: float) -> float:
    return (numerator / denominator * 100) if denominator != 0 else 0.0


def _safe_evolution(current: float, previous: float) -> float:
    return ((current - previous) / previous * 100) if previous != 0 else 0.0


# (anomalies) supposé pour éviter les faux positifs sur les comptes très irréguliers ou saisonniers


def _is_sparse(entry, months: list[str], min_active: int) -> bool:
    active = sum(1 for m in months if entry.montants.get(m, 0) != 0)
    return active < min_active


async def calculate_kpis(data: FinancialData, config=None) -> KPIResult:
    return await asyncio.to_thread(_calculate_kpis, data, config or settings)


def _calculate_kpis(data: FinancialData, config) -> KPIResult:

    logger.info(f"Calculating KPIs for year {data.annee}")

    months = data.mois_disponibles
    if not months:
        raise ValueError("Aucun mois disponible.")

    ca_mensuel: dict[str, float] = {
        m: sum(e.montants.get(m, 0) for e in _by_prefix(data.produits, "70")) for m in months
    }
    ca_annuel = sum(ca_mensuel.values())
    ca_moyenne_mensuelle = ca_annuel / len(months) if months else 0.0

    total_produits_mensuel: dict[str, float] = {
        m: sum(e.montants.get(m, 0) for e in data.produits) for m in months
    }
    total_produits_annuel = sum(total_produits_mensuel.values())

    charges_mensuelles: dict[str, float] = {
        m: sum(e.montants.get(m, 0) for e in data.charges) for m in months
    }
    charges_annuelles = sum(charges_mensuelles.values())

    logger.info(
        f"CA={ca_annuel:,.0f} | "
        f"Total produits={total_produits_annuel:,.0f} | "
        f"Charges={charges_annuelles:,.0f}"
    )

    resultat_exploitation_mensuel: dict[str, float] = {
        m: total_produits_mensuel[m] - charges_mensuelles[m] for m in months
    }
    resultat_exploitation_annuel = total_produits_annuel - charges_annuelles

    achats_60_mensuel: dict[str, float] = {
        m: sum(e.montants.get(m, 0) for e in _by_prefix(data.charges, "60")) for m in months
    }
    achats_60_annuel = sum(e.total for e in _by_prefix(data.charges, "60"))

    marge_brute_mensuelle: dict[str, float] = {
        m: _safe_pct(ca_mensuel[m] - achats_60_mensuel[m], ca_mensuel[m]) for m in months
    }
    marge_brute_annuelle = _safe_pct(ca_annuel - achats_60_annuel, ca_annuel)

    charges_personnel = sum(e.total for e in _by_prefix(data.charges, "63"))
    charges_personnel_pourcentage = _safe_pct(charges_personnel, charges_annuelles)

    evolution_ca_mm: dict[str, float] = {
        months[i]: _safe_evolution(ca_mensuel[months[i]], ca_mensuel[months[i - 1]])
        for i in range(1, len(months))
    }

    evolution_charges_mm: dict[str, float] = {
        months[i]: _safe_evolution(charges_mensuelles[months[i]], charges_mensuelles[months[i - 1]])
        for i in range(1, len(months))
    }

    mois_plus_fort = max(ca_mensuel, key=ca_mensuel.get)
    mois_plus_faible = min(ca_mensuel, key=ca_mensuel.get)

    charges_par_categorie: dict[str, float] = {
        label: sum(e.total for e in _by_prefix(data.charges, prefix))
        for label, prefix in CHARGE_CATEGORIES.items()
    }

    # supposé logique anomalies
    # fama 2 variables fel config

    anomalies_detectees: list[AnomalyRecord] = []
    threshold = config.anomaly_threshold_pct
    min_active = config.anomaly_min_active_months

    for entry in data.produits + data.charges:
        if _is_sparse(entry, months, min_active):
            logger.debug(f"Skipping sparse account {entry.compte} ({entry.libelle})")
            continue

        for i in range(1, len(months)):
            prev_val = entry.montants.get(months[i - 1], 0)
            curr_val = entry.montants.get(months[i], 0)

            if prev_val == 0:
                continue

            variation = (curr_val - prev_val) / abs(prev_val) * 100

            if abs(variation) >= threshold:
                anomalies_detectees.append(
                    AnomalyRecord(
                        month=months[i],
                        previous_month=months[i - 1],
                        compte=entry.compte,
                        libelle=entry.libelle,
                        variation_pct=round(variation, 2),
                    )
                )

    logger.info(f"Detected {len(anomalies_detectees)} anomalies")

    return KPIResult(
        annee=data.annee,
        ca_mensuel=ca_mensuel,
        ca_annuel=round(ca_annuel, 2),
        ca_moyenne_mensuelle=round(ca_moyenne_mensuelle, 2),
        charges_mensuelles=charges_mensuelles,
        charges_annuelles=round(charges_annuelles, 2),
        charges_par_categorie=charges_par_categorie,
        resultat_exploitation_mensuel=resultat_exploitation_mensuel,
        resultat_exploitation_annuel=round(resultat_exploitation_annuel, 2),
        marge_brute_mensuelle=marge_brute_mensuelle,
        marge_brute_annuelle=round(marge_brute_annuelle, 2),
        evolution_ca_mm=evolution_ca_mm,
        evolution_charges_mm=evolution_charges_mm,
        mois_plus_fort=mois_plus_fort,
        mois_plus_faible=mois_plus_faible,
        charges_personnel_pourcentage=round(charges_personnel_pourcentage, 2),
        anomalies_detectees=anomalies_detectees,
        # date_calcul prend valeur par defaut datetime.now fel schemas
    )
