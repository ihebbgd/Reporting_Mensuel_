import logging
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from app.services.data_processor import (
    DataProcessingError,
    clean_amount,
    detect_separator,
    extract_year_from_filename,
    process_csv,
)

logger = logging.getLogger(__name__)


class TestDataProcessor:
    """Test suite for data_processor module"""

    @pytest.fixture
    def csv_file_path(self):
        """Versioned synthetic data, independent of private local files."""
        return Path(__file__).parent.parent / "examples" / "demo_2024.csv"

    @pytest.fixture
    def sample_csv_content(self):
        """Sample CSV content for testing"""
        return """Compte;Libellé;Nature;Janvier;Février;Mars;Avril;Mai;Juin;Juillet;Août;Septembre;Octobre;Novembre;Décembre;Total
70111;Ventes de marchandises;Produit;100;200;150;180;220;190;160;120;200;250;280;300;2350
60100;Achats de marchandises;Charge;50;60;75;80;100;90;70;60;90;100;110;120;1005"""

    def test_process_csv_with_real_file(self, csv_file_path):
        """Test processing the real CSV file"""
        if not csv_file_path.exists():
            pytest.skip(f"CSV file not found: {csv_file_path}")

        data = process_csv(str(csv_file_path))

        # Assertions
        assert data is not None
        assert data.annee == 2024
        assert len(data.entrees) == 5
        assert len(data.produits) == 1
        assert len(data.charges) == 4
        assert len(data.mois_disponibles) == 12
        assert data.mois_disponibles[0] == "Janvier"
        assert data.mois_disponibles[-1] == "Décembre"

    def test_process_csv_structure(self, csv_file_path):
        """Test the structure of processed data"""
        if not csv_file_path.exists():
            pytest.skip(f"CSV file not found: {csv_file_path}")

        data = process_csv(str(csv_file_path))

        # Check first product
        first_product = data.produits[0]
        assert first_product.compte == "70100"
        assert first_product.nature.lower() == "produit"
        assert "Janvier" in first_product.montants
        assert first_product.total > 0

    def test_process_csv_total_validation(self, csv_file_path):
        """Test that totals match monthly sum for each entry"""
        if not csv_file_path.exists():
            pytest.skip(f"CSV file not found: {csv_file_path}")

        data = process_csv(str(csv_file_path))

        for entry in data.entrees:
            calculated_total = sum(entry.montants.values())
            # Allow small rounding differences
            assert abs(calculated_total - entry.total) < 1.0, (
                f"Total mismatch for {entry.compte}: {entry.total} vs {calculated_total}"
            )

    def test_process_csv_file_not_found(self):
        """Test processing non-existent file"""
        with pytest.raises(DataProcessingError) as exc_info:
            process_csv("/nonexistent/path/file.csv")
        assert "introuvable" in str(exc_info.value)

    def test_detect_separator_semicolon(self):
        """Test separator detection with semicolon"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Compte;Libellé;Nature;Janvier;Février;Mars;Avril;Mai;Juin;Juillet;Août;Septembre;Octobre;Novembre;Décembre;Total\n"
            )
            f.flush()
            temp_path = Path(f.name)

        try:
            separator = detect_separator(temp_path)
            assert separator == ";"
        finally:
            temp_path.unlink()

    def test_clean_amount_with_spaces(self):
        """Test cleaning amounts with spaces"""
        assert clean_amount("1 000") == 1000.0
        assert clean_amount("  100  ") == 100.0

    def test_clean_amount_with_comma(self):
        """Test cleaning amounts with French comma format"""
        assert clean_amount("1 000,50") == 1000.5
        assert clean_amount("100,50") == 100.5

    def test_clean_amount_empty(self):
        """Test cleaning empty amounts"""
        assert clean_amount("") == 0.0
        assert clean_amount(None) == 0.0

    def test_clean_amount_invalid(self):
        """Test cleaning invalid amounts"""
        for amount in ("invalid", "abc123"):
            with pytest.raises(DataProcessingError):
                clean_amount(amount)

    def test_extract_year_from_filename(self):
        """Test year extraction from filename"""
        assert extract_year_from_filename("test_2024.csv") == 2024
        assert extract_year_from_filename("report_2023.csv") == 2023
        assert extract_year_from_filename("data_2000.txt") == 2000

    def test_extract_year_no_year_found(self):
        """Test year extraction when no year is found"""
        assert extract_year_from_filename("report.csv") == datetime.now().year - 1  # Default

    def test_produits_vs_charges_separation(self, csv_file_path):
        """Test correct separation of products and charges"""
        if not csv_file_path.exists():
            pytest.skip(f"CSV file not found: {csv_file_path}")

        data = process_csv(str(csv_file_path))

        # All produits should have nature "Produit"
        for entry in data.produits:
            assert entry.nature.lower() == "produit"

        # All charges should have nature "Charge"
        for entry in data.charges:
            assert entry.nature.lower() == "charge"

        # Sum should equal total entries
        assert len(data.produits) + len(data.charges) == len(data.entrees)

    def test_montants_dict_keys(self, csv_file_path):
        """Test that all entries have 12 months in montants dict"""
        if not csv_file_path.exists():
            pytest.skip(f"CSV file not found: {csv_file_path}")

        data = process_csv(str(csv_file_path))
        expected_months = [
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

        for entry in data.entrees:
            assert len(entry.montants) == 12
            for month in expected_months:
                assert month in entry.montants
                assert isinstance(entry.montants[month], float)

    def test_all_amounts_are_floats(self, csv_file_path):
        """Test that all monetary values are floats"""
        if not csv_file_path.exists():
            pytest.skip(f"CSV file not found: {csv_file_path}")

        data = process_csv(str(csv_file_path))

        for entry in data.entrees:
            assert isinstance(entry.total, float)
            for month, amount in entry.montants.items():
                assert isinstance(amount, float)

    def test_sample_data_processing(self, sample_csv_content):
        """Test processing sample CSV data"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(sample_csv_content)
            f.flush()
            temp_path = Path(f.name)

        try:
            data = process_csv(str(temp_path))

            # Should have 2 entries
            assert len(data.entrees) == 2
            assert len(data.produits) == 1
            assert len(data.charges) == 1

            # Check product entry
            product = data.produits[0]
            assert product.compte == "70111"
            assert product.montants["Janvier"] == 100.0
            assert product.montants["Février"] == 200.0

            # Check charge entry
            charge = data.charges[0]
            assert charge.compte == "60100"
            assert charge.montants["Janvier"] == 50.0

        finally:
            temp_path.unlink()

    def test_data_consistency(self, csv_file_path):
        """Test overall data consistency"""
        if not csv_file_path.exists():
            pytest.skip(f"CSV file not found: {csv_file_path}")

        data = process_csv(str(csv_file_path))

        # Check consistency
        assert data.annee > 0
        assert len(data.entrees) > 0
        assert len(data.produits) >= 0
        assert len(data.charges) >= 0
        assert len(data.mois_disponibles) == 12

        # All entries should be in either produits or charges
        accounted_entries = len(data.produits) + len(data.charges)
        assert accounted_entries == len(data.entrees)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
