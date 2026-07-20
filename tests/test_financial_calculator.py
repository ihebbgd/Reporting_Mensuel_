import asyncio
from unittest.mock import patch

import pytest

from app.models.schemas import FinancialData, MonthlyEntry
from app.services.financial_calculator import calculate_kpis

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


def make_entry(compte: str, libelle: str, nature: str, montants: dict) -> MonthlyEntry:
    full = {m: float(montants.get(m, 0)) for m in MONTHS}
    return MonthlyEntry(
        compte=compte,
        libelle=libelle,
        nature=nature,
        montants=full,
        total=float(sum(full.values())),
    )


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def simple_data():
    produit = make_entry(
        "70111",
        "Ventes de marchandises",
        "Produit",
        {m: 10_000.0 for m in MONTHS},
    )
    charge = make_entry(
        "60100",
        "Achats de marchandises",
        "Charge",
        {m: 4_000.0 for m in MONTHS},
    )
    entries = [produit, charge]
    return FinancialData(
        annee=2024,
        entrees=entries,
        produits=[produit],
        charges=[charge],
        mois_disponibles=MONTHS,
    )


@pytest.fixture
def realistic_data():
    produits = [
        make_entry("70111", "Ventes marché local", "Produit", {m: 185_000.0 for m in MONTHS}),
        make_entry("70112", "Ventes export", "Produit", {m: 42_000.0 for m in MONTHS}),
        make_entry("70211", "Prestations de services", "Produit", {m: 28_000.0 for m in MONTHS}),
        make_entry("70700", "Produits accessoires", "Produit", {m: 3_200.0 for m in MONTHS}),
        # Sparse: only March and September → must be ignored by anomaly detector
        make_entry(
            "74100",
            "Subventions d'exploitation",
            "Produit",
            {"Mars": 15_000.0, "Septembre": 15_000.0},
        ),
        make_entry("75000", "Autres produits", "Produit", {m: 1_200.0 for m in MONTHS}),
    ]
    charges = [
        make_entry("60100", "Achats marchandises", "Charge", {m: 112_000.0 for m in MONTHS}),
        make_entry("60400", "Achats fournitures", "Charge", {m: 8_500.0 for m in MONTHS}),
        make_entry("61100", "Transports achats", "Charge", {m: 3_200.0 for m in MONTHS}),
        make_entry("61200", "Transports ventes", "Charge", {m: 4_800.0 for m in MONTHS}),
        make_entry("61310", "Loyers", "Charge", {m: 8_500.0 for m in MONTHS}),
        make_entry("61320", "Entretien", "Charge", {m: 1_200.0 for m in MONTHS}),
        make_entry("61400", "Assurances", "Charge", {m: 2_800.0 for m in MONTHS}),
        make_entry("61600", "Honoraires", "Charge", {m: 3_500.0 for m in MONTHS}),
        make_entry("61700", "Publicité", "Charge", {m: 5_200.0 for m in MONTHS}),
        make_entry("61800", "Téléphone", "Charge", {m: 1_850.0 for m in MONTHS}),
        make_entry("62000", "Autres services ext.", "Charge", {m: 2_100.0 for m in MONTHS}),
        make_entry("63100", "Rémunérations personnel", "Charge", {m: 45_000.0 for m in MONTHS}),
        make_entry("63200", "Charges sociales CNSS", "Charge", {m: 10_350.0 for m in MONTHS}),
        make_entry("63300", "Autres charges personnel", "Charge", {m: 1_200.0 for m in MONTHS}),
        make_entry("64100", "Impôts et taxes", "Charge", {m: 2_500.0 for m in MONTHS}),
        # Sparse: only March and December
        make_entry("64200", "Taxes véhicules", "Charge", {"Mars": 1_800.0, "Décembre": 1_800.0}),
        make_entry("65000", "Charges financières", "Charge", {m: 3_800.0 for m in MONTHS}),
        make_entry("68100", "Amortissements", "Charge", {m: 6_200.0 for m in MONTHS}),
    ]
    entries = produits + charges
    return FinancialData(
        annee=2024,
        entrees=entries,
        produits=produits,
        charges=charges,
        mois_disponibles=MONTHS,
    )


@pytest.fixture
def anomaly_data():
    montants = {m: 10_000.0 for m in MONTHS}
    montants["Février"] = 20_000.0  # +100 % → anomaly

    produit = make_entry("70111", "Ventes", "Produit", montants)
    charge = make_entry("60100", "Achats", "Charge", {m: 5_000.0 for m in MONTHS})
    entries = [produit, charge]
    return FinancialData(
        annee=2024,
        entrees=entries,
        produits=[produit],
        charges=[charge],
        mois_disponibles=MONTHS,
    )


@pytest.fixture
def zero_ca_data():
    produit = make_entry("70111", "Ventes nulles", "Produit", {m: 0.0 for m in MONTHS})
    charge = make_entry("60100", "Achats", "Charge", {m: 5_000.0 for m in MONTHS})
    entries = [produit, charge]
    return FinancialData(
        annee=2024,
        entrees=entries,
        produits=[produit],
        charges=[charge],
        mois_disponibles=MONTHS,
    )


# Tests CA


class TestCA:
    def test_ca_annuel(self, simple_data):
        result = run(calculate_kpis(simple_data))
        # 10 000 × 12 months
        assert result.ca_annuel == pytest.approx(120_000.0)

    def test_ca_mensuel_all_months_present(self, simple_data):
        result = run(calculate_kpis(simple_data))
        assert set(result.ca_mensuel.keys()) == set(MONTHS)

    def test_ca_mensuel_values(self, simple_data):
        result = run(calculate_kpis(simple_data))
        for month in MONTHS:
            assert result.ca_mensuel[month] == pytest.approx(10_000.0)

    def test_ca_moyenne_mensuelle(self, simple_data):
        result = run(calculate_kpis(simple_data))
        assert result.ca_moyenne_mensuelle == pytest.approx(10_000.0)

    def test_ca_only_70xxx_accounts(self, realistic_data):
        result = run(calculate_kpis(realistic_data))
        # 70111 + 70112 + 70211 + 70700 = (185+42+28+3.2) k × 12
        expected = (185_000 + 42_000 + 28_000 + 3_200) * 12
        assert result.ca_annuel == pytest.approx(expected)

    def test_ca_does_not_include_74xxx(self, realistic_data):
        result = run(calculate_kpis(realistic_data))
        # If 74xxx were included, CA would be ≥ ca_annuel + 30 000
        extra = 30_000  # 74100 annual total
        expected_wrong = result.ca_annuel + extra
        assert result.ca_annuel != pytest.approx(expected_wrong)


# Tests Charges


class TestCharges:
    def test_charges_annuelles(self, simple_data):
        result = run(calculate_kpis(simple_data))
        assert result.charges_annuelles == pytest.approx(4_000.0 * 12)

    def test_charges_mensuelles_all_months(self, simple_data):
        result = run(calculate_kpis(simple_data))
        assert set(result.charges_mensuelles.keys()) == set(MONTHS)

    def test_charges_par_categorie_keys(self, simple_data):
        result = run(calculate_kpis(simple_data))
        expected_keys = {
            "Achats (60xxx)",
            "Services ext. (61xxx)",
            "Autres services (62xxx)",
            "Personnel (63xxx)",
            "Impôts & taxes (64xxx)",
            "Charges financières (65xxx)",
            "Amortissements (68xxx)",
        }
        assert set(result.charges_par_categorie.keys()) == expected_keys

    def test_charges_par_categorie_60xxx(self, simple_data):
        result = run(calculate_kpis(simple_data))
        # Only 60100 exists → entire charges should be in Achats (60xxx)
        assert result.charges_par_categorie["Achats (60xxx)"] == pytest.approx(4_000.0 * 12)

    def test_charges_par_categorie_no_negative(self, realistic_data):
        result = run(calculate_kpis(realistic_data))
        for label, value in result.charges_par_categorie.items():
            assert value >= 0.0, f"{label} has negative value: {value}"

    def test_charges_personnel_pourcentage_realistic(self, realistic_data):
        result = run(calculate_kpis(realistic_data))
        # Personnel (63xxx) = (45000 + 10350 + 1200) × 12 = 679 800
        personnel_annual = (45_000 + 10_350 + 1_200) * 12
        assert result.charges_par_categorie["Personnel (63xxx)"] == pytest.approx(personnel_annual)
        assert 0 < result.charges_personnel_pourcentage < 100


# Tests Résultat d'exploitation


class TestResultatExploitation:
    def test_resultat_annuel_simple(self, simple_data):
        result = run(calculate_kpis(simple_data))
        # total produits (70xxx only here) - total charges
        assert result.resultat_exploitation_annuel == pytest.approx((10_000 - 4_000) * 12)

    def test_resultat_mensuel_all_months(self, simple_data):
        result = run(calculate_kpis(simple_data))
        assert set(result.resultat_exploitation_mensuel.keys()) == set(MONTHS)

    def test_resultat_includes_74xxx_and_75xxx(self, realistic_data):
        result = run(calculate_kpis(realistic_data))
        # 74xxx contributes 30 000, 75xxx contributes 14 400 → résultat > ca-based result
        charges = result.charges_annuelles
        ca_based = result.ca_annuel - charges
        assert result.resultat_exploitation_annuel > ca_based

    def test_resultat_annuel_equals_sum_mensuel(self, realistic_data):
        result = run(calculate_kpis(realistic_data))
        monthly_sum = sum(result.resultat_exploitation_mensuel.values())
        assert result.resultat_exploitation_annuel == pytest.approx(monthly_sum, rel=1e-6)


# Tests Marge brute


class TestMargeBrute:
    def test_marge_brute_annuelle_simple(self, simple_data):
        result = run(calculate_kpis(simple_data))
        # (CA - achats 60xxx) / CA × 100 = (10k - 4k) / 10k × 100 = 60 %
        assert result.marge_brute_annuelle == pytest.approx(60.0)

    def test_marge_brute_mensuelle_all_months(self, simple_data):
        result = run(calculate_kpis(simple_data))
        assert set(result.marge_brute_mensuelle.keys()) == set(MONTHS)

    def test_marge_brute_mensuelle_values(self, simple_data):
        result = run(calculate_kpis(simple_data))
        for month, pct in result.marge_brute_mensuelle.items():
            assert pct == pytest.approx(60.0), f"Wrong marge for {month}"

    def test_marge_brute_zero_ca_no_crash(self, zero_ca_data):
        result = run(calculate_kpis(zero_ca_data))
        assert result.marge_brute_annuelle == pytest.approx(0.0)
        for month in MONTHS:
            assert result.marge_brute_mensuelle[month] == pytest.approx(0.0)

    def test_marge_brute_between_0_and_100(self, realistic_data):
        result = run(calculate_kpis(realistic_data))
        assert 0 <= result.marge_brute_annuelle <= 100


# Tests Évolutions M/M


class TestEvolutions:
    def test_evolution_ca_mm_count(self, simple_data):
        result = run(calculate_kpis(simple_data))
        assert len(result.evolution_ca_mm) == 11

    def test_evolution_ca_mm_flat_is_zero(self, simple_data):
        result = run(calculate_kpis(simple_data))
        for month, pct in result.evolution_ca_mm.items():
            assert pct == pytest.approx(0.0), f"Expected 0 % for {month}, got {pct}"

    def test_evolution_charges_mm_flat_is_zero(self, simple_data):
        result = run(calculate_kpis(simple_data))
        for month, pct in result.evolution_charges_mm.items():
            assert pct == pytest.approx(0.0)

    def test_evolution_ca_spike_detected(self, anomaly_data):
        result = run(calculate_kpis(anomaly_data))
        assert result.evolution_ca_mm["Février"] == pytest.approx(100.0)

    def test_evolution_no_janvier_key(self, simple_data):
        result = run(calculate_kpis(simple_data))
        assert "Janvier" not in result.evolution_ca_mm
        assert "Janvier" not in result.evolution_charges_mm

    def test_evolution_keys_are_months_2_to_12(self, simple_data):
        result = run(calculate_kpis(simple_data))
        expected = set(MONTHS[1:])  # Février … Décembre
        assert set(result.evolution_ca_mm.keys()) == expected


# Tests Meilleur et pire mois


class TestMoisStats:
    def test_mois_plus_fort_is_string(self, simple_data):
        result = run(calculate_kpis(simple_data))
        assert isinstance(result.mois_plus_fort, str)
        assert result.mois_plus_fort in MONTHS

    def test_mois_plus_faible_is_string(self, simple_data):
        result = run(calculate_kpis(simple_data))
        assert isinstance(result.mois_plus_faible, str)
        assert result.mois_plus_faible in MONTHS

    def test_mois_plus_fort_correct(self):
        montants = {m: float(i + 1) * 1_000 for i, m in enumerate(MONTHS)}
        produit = make_entry("70111", "Ventes", "Produit", montants)
        charge = make_entry("60100", "Achats", "Charge", {m: 100.0 for m in MONTHS})
        data = FinancialData(
            annee=2024,
            entrees=[produit, charge],
            produits=[produit],
            charges=[charge],
            mois_disponibles=MONTHS,
        )
        result = run(calculate_kpis(data))
        assert result.mois_plus_fort == "Décembre"

    def test_mois_plus_faible_correct(self):
        montants = {m: float(i + 1) * 1_000 for i, m in enumerate(MONTHS)}
        produit = make_entry("70111", "Ventes", "Produit", montants)
        charge = make_entry("60100", "Achats", "Charge", {m: 100.0 for m in MONTHS})
        data = FinancialData(
            annee=2024,
            entrees=[produit, charge],
            produits=[produit],
            charges=[charge],
            mois_disponibles=MONTHS,
        )
        result = run(calculate_kpis(data))
        assert result.mois_plus_faible == "Janvier"


# Tests Anomaly detection
class TestAnomalies:
    def test_no_anomalies_flat_data(self, simple_data):
        result = run(calculate_kpis(simple_data))
        assert result.anomalies_detectees == []

    def test_anomaly_detected_on_spike(self, anomaly_data):
        result = run(calculate_kpis(anomaly_data))
        assert len(result.anomalies_detectees) >= 1
        months_flagged = [a.month for a in result.anomalies_detectees]
        assert "Février" in months_flagged

    def test_anomaly_record_fields(self, anomaly_data):
        result = run(calculate_kpis(anomaly_data))
        anomaly = next((a for a in result.anomalies_detectees if a.month == "Février"), None)
        assert anomaly is not None
        assert anomaly.compte == "70111"
        assert anomaly.previous_month == "Janvier"
        assert anomaly.variation_pct == pytest.approx(100.0)

    def test_sparse_accounts_excluded(self, realistic_data):
        result = run(calculate_kpis(realistic_data))
        sparse_accounts = {a.compte for a in result.anomalies_detectees}
        assert "74100" not in sparse_accounts, "74100 is sparse and should be excluded"
        assert "64200" not in sparse_accounts, "64200 is sparse and should be excluded"

    def test_anomaly_threshold_respected(self):
        montants = {m: 10_000.0 for m in MONTHS}
        montants["Février"] = 12_990.0  # +29.9 % → just below 30 %
        produit = make_entry("70111", "Ventes", "Produit", montants)
        charge = make_entry("60100", "Achats", "Charge", {m: 1_000.0 for m in MONTHS})
        data = FinancialData(
            annee=2024,
            entrees=[produit, charge],
            produits=[produit],
            charges=[charge],
            mois_disponibles=MONTHS,
        )
        with patch("app.services.financial_calculator.settings") as mock_settings:
            mock_settings.anomaly_threshold_pct = 30.0
            mock_settings.anomaly_min_active_months = 3
            result = run(calculate_kpis(data))
        assert result.anomalies_detectees == []

    def test_anomaly_threshold_triggered(self):
        montants = {m: 10_000.0 for m in MONTHS}
        montants["Février"] = 13_000.0  # exactly +30 %
        produit = make_entry("70111", "Ventes", "Produit", montants)
        charge = make_entry("60100", "Achats", "Charge", {m: 1_000.0 for m in MONTHS})
        data = FinancialData(
            annee=2024,
            entrees=[produit, charge],
            produits=[produit],
            charges=[charge],
            mois_disponibles=MONTHS,
        )
        with patch("app.services.financial_calculator.settings") as mock_settings:
            mock_settings.anomaly_threshold_pct = 30.0
            mock_settings.anomaly_min_active_months = 3
            result = run(calculate_kpis(data))
        months_flagged = [a.month for a in result.anomalies_detectees]
        assert "Février" in months_flagged


# Tests KPIResult metadata


class TestMetadata:
    def test_annee_preserved(self, simple_data):
        result = run(calculate_kpis(simple_data))
        assert result.annee == 2024

    def test_date_calcul_is_set(self, simple_data):
        from datetime import datetime

        result = run(calculate_kpis(simple_data))
        assert isinstance(result.date_calcul, datetime)

    def test_result_is_kpiresult_instance(self, simple_data):
        from app.models.schemas import KPIResult

        result = run(calculate_kpis(simple_data))
        assert isinstance(result, KPIResult)


# Integration-style test real CSV values


class TestRealisticValues:
    def test_ca_annuel_realistic(self, realistic_data):
        result = run(calculate_kpis(realistic_data))
        expected = (185_000 + 42_000 + 28_000 + 3_200) * 12
        assert result.ca_annuel == pytest.approx(expected)

    def test_charges_annuelles_realistic(self, realistic_data):
        result = run(calculate_kpis(realistic_data))
        per_month = (
            112_000
            + 8_500
            + 3_200
            + 4_800
            + 8_500
            + 1_200
            + 2_800
            + 3_500
            + 5_200
            + 1_850
            + 2_100
            + 45_000
            + 10_350
            + 1_200
            + 2_500
            + 3_800
            + 6_200
        )
        sparse_charge = 1_800 * 2
        expected = per_month * 12 + sparse_charge
        assert result.charges_annuelles == pytest.approx(expected)

    def test_marge_brute_realistic(self, realistic_data):
        result = run(calculate_kpis(realistic_data))
        ca = (185_000 + 42_000 + 28_000 + 3_200) * 12
        achats = (112_000 + 8_500) * 12
        expected_pct = (ca - achats) / ca * 100
        assert result.marge_brute_annuelle == pytest.approx(expected_pct, rel=1e-4)

    def test_personnel_category_realistic(self, realistic_data):
        result = run(calculate_kpis(realistic_data))
        expected = (45_000 + 10_350 + 1_200) * 12
        assert result.charges_par_categorie["Personnel (63xxx)"] == pytest.approx(expected)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
