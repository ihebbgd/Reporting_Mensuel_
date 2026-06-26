from app.models.schemas import KPIResult


def compare_exercises(current: KPIResult, previous: KPIResult) -> dict:
    if current.annee != previous.annee + 1:
        raise ValueError("Choisir deux exercices consécutifs, du plus ancien au plus récent.")
    indicators = {}
    for key in (
        "ca_annuel",
        "charges_annuelles",
        "resultat_exploitation_annuel",
        "marge_brute_annuelle",
    ):
        before, after = getattr(previous, key), getattr(current, key)
        indicators[key] = {
            "previous": before,
            "current": after,
            "difference": round(after - before, 2),
            "variation_pct": round((after - before) / abs(before) * 100, 2) if before else None,
        }
    return {
        "previous_year": previous.annee,
        "current_year": current.annee,
        "indicators": indicators,
    }
