# tests/test_ai_analyzer.py
import logging
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import KPIResult
from app.services.ai_analyzer import (
    _build_fallback,
    _build_prompt,
    _extract_json,
    generate_analysis,
)
from app.services.data_processor import process_csv
from app.services.financial_calculator import calculate_kpis

logger = logging.getLogger(__name__)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def csv_file_path():
    """Return path to the test CSV file"""
    possible_paths = [
        Path(__file__).parent.parent / "test_2024.csv",
        Path(__file__).parent.parent.parent / "test_2024.csv",
        Path.cwd() / "test_2024.csv",
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return possible_paths[0]


@pytest.fixture
def sample_kpis():
    """Minimal KPIResult built from hardcoded data"""
    return KPIResult(
        annee=2024,
        ca_mensuel={
            "Janvier": 90_000,
            "Fevrier": 95_000,
            "Mars": 130_000,
            "Avril": 110_000,
            "Mai": 105_000,
            "Juin": 100_000,
            "Juillet": 80_000,
            "Aout": 75_000,
            "Septembre": 100_000,
            "Octobre": 105_000,
            "Novembre": 110_000,
            "Decembre": 100_000,
        },
        ca_annuel=1_200_000,
        ca_moyenne_mensuelle=100_000,
        charges_mensuelles={
            "Janvier": 78_000,
            "Fevrier": 80_000,
            "Mars": 85_000,
            "Avril": 82_000,
            "Mai": 81_000,
            "Juin": 80_000,
            "Juillet": 75_000,
            "Aout": 74_000,
            "Septembre": 80_000,
            "Octobre": 82_000,
            "Novembre": 83_000,
            "Decembre": 100_000,
        },
        charges_annuelles=980_000,
        charges_par_categorie={
            "Achats (60xxx)": 250_000,
            "Services ext. (61xxx)": 120_000,
            "Autres services (62xxx)": 80_000,
            "Personnel (63xxx)": 441_000,
            "Impôts & taxes (64xxx)": 30_000,
            "Charges financières (65xxx)": 59_000,
            "Amortissements (68xxx)": 0,
        },
        resultat_exploitation_mensuel={
            "Janvier": 12_000,
            "Fevrier": 15_000,
            "Mars": 45_000,
            "Avril": 28_000,
            "Mai": 24_000,
            "Juin": 20_000,
            "Juillet": 5_000,
            "Aout": 1_000,
            "Septembre": 20_000,
            "Octobre": 23_000,
            "Novembre": 27_000,
            "Decembre": 0,
        },
        resultat_exploitation_annuel=220_000,
        marge_brute_mensuelle={
            "Janvier": 13.3,
            "Fevrier": 15.8,
            "Mars": 34.6,
            "Avril": 25.5,
            "Mai": 22.9,
            "Juin": 20.0,
            "Juillet": 6.3,
            "Aout": 1.3,
            "Septembre": 20.0,
            "Octobre": 21.9,
            "Novembre": 24.5,
            "Decembre": 0.0,
        },
        marge_brute_annuelle=18.33,
        evolution_ca_mm={
            "Fevrier": 5.6,
            "Mars": 36.8,
            "Avril": -15.4,
            "Mai": -4.5,
            "Juin": -4.8,
            "Juillet": -20.0,
            "Aout": -6.3,
            "Septembre": 33.3,
            "Octobre": 5.0,
            "Novembre": 4.8,
            "Decembre": -9.1,
        },
        evolution_charges_mm={
            "Fevrier": 2.6,
            "Mars": 6.3,
            "Avril": -3.5,
            "Mai": -1.2,
            "Juin": -1.2,
            "Juillet": -6.3,
            "Aout": -1.3,
            "Septembre": 8.1,
            "Octobre": 2.5,
            "Novembre": 1.2,
            "Decembre": 20.5,
        },
        mois_plus_fort="Mars",
        mois_plus_faible="Aout",
        charges_personnel_pourcentage=45.0,
        anomalies_detectees=[],
    )


@pytest.fixture
def mock_gemini_response():
    """Valid JSON response simulating Gemini output"""
    return {
        "resume": "L'exercice 2024 affiche un CA de 1 200 000 TND et un résultat positif.",
        "tendances": "Le mois de mars est le plus fort avec +36.8%. Aout est le plus faible.",
        "recommandations": "1. Optimiser la trésorerie.\n2. Réduire les achats.\n3. Planifier la saisonnalité.",
    }


# ── Tests unitaires ───────────────────────────────────────────────────────────


class TestBuildPrompt:
    """Tests for _build_prompt helper"""

    def test_prompt_contains_year(self, sample_kpis):
        prompt = _build_prompt(sample_kpis)
        assert "2024" in prompt

    def test_prompt_contains_ca_annuel(self, sample_kpis):
        prompt = _build_prompt(sample_kpis)
        assert "1,200,000" in prompt

    def test_prompt_contains_all_sections(self, sample_kpis):
        prompt = _build_prompt(sample_kpis)
        assert "INDICATEURS ANNUELS" in prompt
        assert "EVOLUTION MENSUELLE DU CA" in prompt
        assert "EVOLUTION MENSUELLE DES CHARGES" in prompt
        assert "RESULTAT D'EXPLOITATION MENSUEL" in prompt
        assert "REPARTITION DES CHARGES PAR CATEGORIE" in prompt
        assert "CONTEXTE TUNISIEN" in prompt
        assert "MISSION" in prompt

    def test_prompt_requests_json_only(self, sample_kpis):
        prompt = _build_prompt(sample_kpis)
        assert "JSON uniquement" in prompt
        assert "resume" in prompt
        assert "tendances" in prompt
        assert "recommandations" in prompt

    def test_prompt_contains_months(self, sample_kpis):
        prompt = _build_prompt(sample_kpis)
        assert "Mars" in prompt
        assert "Aout" in prompt


class TestExtractJson:
    """Tests for _extract_json helper"""

    def test_clean_json(self):
        raw = '{"resume": "ok", "tendances": "ok", "recommandations": "ok"}'
        result = _extract_json(raw)
        assert result["resume"] == "ok"

    def test_json_with_markdown_fence(self):
        raw = '```json\n{"resume": "ok", "tendances": "ok", "recommandations": "ok"}\n```'
        result = _extract_json(raw)
        assert result["resume"] == "ok"

    def test_json_with_generic_fence(self):
        raw = '```\n{"resume": "ok", "tendances": "ok", "recommandations": "ok"}\n```'
        result = _extract_json(raw)
        assert result["resume"] == "ok"

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            _extract_json("not valid json")

    def test_all_keys_present(self):
        raw = '{"resume": "a", "tendances": "b", "recommandations": "c"}'
        result = _extract_json(raw)
        assert set(result.keys()) == {"resume", "tendances", "recommandations"}


class TestBuildFallback:
    """Tests for _build_fallback helper"""

    def test_fallback_is_marked(self, sample_kpis):
        result = _build_fallback(sample_kpis)
        assert result.is_fallback is True
        assert result.used_model == "fallback"

    def test_fallback_contains_kpi_values(self, sample_kpis):
        result = _build_fallback(sample_kpis)
        assert "1,200,000" in result.resume
        assert "220,000" in result.resume
        assert "18.3" in result.resume

    def test_fallback_beneficiaire(self, sample_kpis):
        result = _build_fallback(sample_kpis)
        assert "beneficiaire" in result.resume

    def test_fallback_deficitaire(self, sample_kpis):
        sample_kpis.resultat_exploitation_annuel = -50_000
        result = _build_fallback(sample_kpis)
        assert "deficitaire" in result.resume

    def test_fallback_has_generated_at(self, sample_kpis):
        result = _build_fallback(sample_kpis)
        assert result.generated_at is not None
        assert isinstance(result.generated_at, datetime)


# ── Tests avec mock Gemini ────────────────────────────────────────────────────


class TestGenerateAnalysisMocked:
    """Tests for generate_analysis with mocked Gemini API"""

    @pytest.mark.asyncio
    async def test_successful_analysis(self, sample_kpis, mock_gemini_response):
        """Gemini returns valid JSON → AIAnalysis with is_fallback=False"""
        import json

        mock_response = MagicMock()
        mock_response.text = json.dumps(mock_gemini_response)

        with patch("app.services.ai_analyzer.client") as mock_client:
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            result = await generate_analysis(sample_kpis)

        assert result.is_fallback is False
        assert result.resume == mock_gemini_response["resume"]
        assert result.tendances == mock_gemini_response["tendances"]
        assert result.recommandations == mock_gemini_response["recommandations"]

    @pytest.mark.asyncio
    async def test_empty_response_triggers_fallback(self, sample_kpis):
        """Empty Gemini response → fallback"""
        mock_response = MagicMock()
        mock_response.text = ""

        with patch("app.services.ai_analyzer.client") as mock_client:
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            result = await generate_analysis(sample_kpis)

        assert result.is_fallback is True

    @pytest.mark.asyncio
    async def test_invalid_json_triggers_fallback(self, sample_kpis):
        """Invalid JSON from Gemini → fallback"""
        mock_response = MagicMock()
        mock_response.text = "Ce n'est pas du JSON valide"

        with patch("app.services.ai_analyzer.client") as mock_client:
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            result = await generate_analysis(sample_kpis)

        assert result.is_fallback is True

    @pytest.mark.asyncio
    async def test_missing_keys_triggers_fallback(self, sample_kpis):
        """JSON missing required keys → fallback"""
        mock_response = MagicMock()
        mock_response.text = '{"resume": "ok"}'  # missing tendances + recommandations

        with patch("app.services.ai_analyzer.client") as mock_client:
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            result = await generate_analysis(sample_kpis)

        assert result.is_fallback is True

    @pytest.mark.asyncio
    async def test_api_error_triggers_fallback(self, sample_kpis):
        """Gemini API error → fallback"""

        with patch("app.services.ai_analyzer.client") as mock_client:
            mock_client.aio.models.generate_content = AsyncMock(
                side_effect=Exception("API unavailable")
            )
            result = await generate_analysis(sample_kpis)

        assert result.is_fallback is True

    @pytest.mark.asyncio
    async def test_result_has_generated_at(self, sample_kpis, mock_gemini_response):
        """Result always has a generated_at timestamp"""
        import json

        mock_response = MagicMock()
        mock_response.text = json.dumps(mock_gemini_response)

        with patch("app.services.ai_analyzer.client") as mock_client:
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            result = await generate_analysis(sample_kpis)

        assert result.generated_at is not None
        assert isinstance(result.generated_at, datetime)

    @pytest.mark.asyncio
    async def test_markdown_wrapped_json(self, sample_kpis, mock_gemini_response):
        """Gemini wraps JSON in markdown fences → still parsed correctly"""
        import json

        mock_response = MagicMock()
        mock_response.text = f"```json\n{json.dumps(mock_gemini_response)}\n```"

        with patch("app.services.ai_analyzer.client") as mock_client:
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            result = await generate_analysis(sample_kpis)

        assert result.is_fallback is False
        assert result.resume == mock_gemini_response["resume"]


# ── Test d'intégration avec vrai fichier CSV + vrai Gemini ────────────────────


@pytest.mark.live_ai
class TestGenerateAnalysisIntegration:
    """Full pipeline test: CSV → KPIs → Gemini (real API call)"""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_real_csv(self, csv_file_path):
        """End-to-end test with real CSV file and real Gemini call"""
        if not csv_file_path.exists():
            pytest.skip(f"CSV file not found: {csv_file_path}")

        # 1. Parse CSV
        financial_data = process_csv(str(csv_file_path))
        assert financial_data is not None

        # 2. Calculate KPIs
        kpis = await calculate_kpis(financial_data)
        assert kpis.ca_annuel > 0

        # 3. Generate AI analysis
        result = await generate_analysis(kpis)

        # Assertions
        assert result is not None
        assert result.is_fallback is False
        assert result.used_model != "fallback"
        assert len(result.resume) > 50
        assert len(result.tendances) > 50
        assert len(result.recommandations) > 50
        assert result.generated_at is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
