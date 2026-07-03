import asyncio
import json
import logging
from datetime import UTC, datetime

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.config import settings
from app.models.schemas import AIAnalysis, KPIResult

logger = logging.getLogger(__name__)

client = None  # Optional injected client; real clients are opened only on explicit AI requests.

MAX_RETRIES = 3
RETRY_DELAY = 2


def _build_prompt(kpis: KPIResult) -> str:

    ca_lines = "\n".join(
        f"  {month:<12}: {value:>10,.0f} TND"
        f"  ({kpis.evolution_ca_mm.get(month, 0):>+.1f}% vs mois precedent)"
        for month, value in kpis.ca_mensuel.items()
    )

    charges_lines = "\n".join(
        f"  {month:<12}: {value:>10,.0f} TND"
        f"  ({kpis.evolution_charges_mm.get(month, 0):>+.1f}% vs mois precedent)"
        for month, value in kpis.charges_mensuelles.items()
    )

    breakdown_lines = "\n".join(
        f"  {label:<35}: {value:>10,.0f} TND"
        for label, value in kpis.charges_par_categorie.items()
        if value > 0
    )

    resultat_lines = "\n".join(
        f"  {month:<12}: {value:>+10,.0f} TND"
        for month, value in kpis.resultat_exploitation_mensuel.items()
    )

    prompt = (
        f"Tu es un expert-comptable senior specialise dans les PME tunisiennes.\n"
        f"Analyse les donnees financieres de l'exercice {kpis.annee}.\n\n"
        f"INDICATEURS ANNUELS\n"
        f"Chiffre d'affaires (70xxx) : {kpis.ca_annuel:>12,.0f} TND\n"
        f"CA moyen mensuel           : {kpis.ca_moyenne_mensuelle:>12,.0f} TND\n"
        f"Total charges              : {kpis.charges_annuelles:>12,.0f} TND\n"
        f"Resultat d'exploitation    : {kpis.resultat_exploitation_annuel:>+12,.0f} TND\n"
        f"Marge brute                : {kpis.marge_brute_annuelle:>12,.2f}%\n"
        f"Charges de personnel       : {kpis.charges_personnel_pourcentage:>12,.2f}% des charges\n"
        f"Meilleur mois (CA)         : {kpis.mois_plus_fort}\n"
        f"Mois le plus faible (CA)   : {kpis.mois_plus_faible}\n\n"
        f"EVOLUTION MENSUELLE DU CA\n"
        f"{ca_lines}\n\n"
        f"EVOLUTION MENSUELLE DES CHARGES\n"
        f"{charges_lines}\n\n"
        f"RESULTAT D'EXPLOITATION MENSUEL\n"
        f"{resultat_lines}\n\n"
        f"REPARTITION DES CHARGES PAR CATEGORIE\n"
        f"{breakdown_lines}\n\n"
        f"CONTEXTE TUNISIEN\n"
        f"- Une hausse des remunerations (63xxx) en decembre correspond a la prime\n"
        f"  de fin d'annee possible, a verifier selon la convention applicable.\n"
        f"  Ne presume aucune cause ni obligation sans piece justificative.\n"
        f"- La saisonnalite est une hypothese a confirmer selon le secteur.\n"
        f"- Les subventions (74xxx) peuvent etre ponctuelles et non recurrentes.\n\n"
        f"MISSION\n"
        f"1. Identifie les variations mensuelles significatives dans le CA et les charges.\n"
        f"2. Distingue la saisonnalite normale des vraies anomalies.\n"
        f"3. Genere une analyse professionnelle complete, a valider par un comptable.\n"
        f"4. Ne cree aucun chiffre absent des indicateurs. Separe faits et hypotheses.\n\n"
        f"Reponds UNIQUEMENT avec un objet JSON valide contenant exactement ces 3 cles:\n"
        f"{{\n"
        f'  "resume": "Synthese globale de l\'exercice {kpis.annee} (150-200 mots). '
        f'Chiffres cles: CA, resultat, marge brute. Ton professionnel.",\n'
        f'  "tendances": "Analyse des tendances mensuelles et variations significatives '
        f"(200-250 mots). Cite les mois et chiffres precis. "
        f'Distingue saisonnalite normale vs anomalie reelle.",\n'
        f'  "recommandations": "3 a 5 recommandations concretes numerotees en texte simple, '
        f"separees par des sauts de ligne. Valeur de type string uniquement, pas un tableau JSON. "
        f'Adaptees a une PME tunisienne (200-250 mots)."\n'
        f"}}\n\n"
        f"JSON uniquement. Aucun texte avant ou apres. Aucun bloc markdown."
    )

    return prompt


# Fallback (au cas ou makhdemch)


def _build_fallback(kpis: KPIResult) -> AIAnalysis:

    signe = "beneficiaire" if kpis.resultat_exploitation_annuel >= 0 else "deficitaire"

    return AIAnalysis(
        resume=(
            f"L'exercice {kpis.annee} affiche un chiffre d'affaires de "
            f"{kpis.ca_annuel:,.0f} TND pour un resultat d'exploitation "
            f"{signe} de {kpis.resultat_exploitation_annuel:+,.0f} TND. "
            f"La marge brute s'etablit a {kpis.marge_brute_annuelle:.1f}%. "
            f"Le meilleur mois est {kpis.mois_plus_fort} "
            f"et le plus faible {kpis.mois_plus_faible}. "
            f"L'analyse IA detaillee n'a pas pu etre generee."
        ),
        tendances=(
            f"Le CA moyen mensuel est de {kpis.ca_moyenne_mensuelle:,.0f} TND. "
            f"Les charges de personnel representent "
            f"{kpis.charges_personnel_pourcentage:.1f}% "
            f"du total des charges ({kpis.charges_annuelles:,.0f} TND). "
            f"Une analyse manuelle des evolutions mensuelles est recommandee."
        ),
        recommandations=(
            "1. Relancer l'analyse IA pour obtenir des recommandations personnalisees.\n"
            "2. Consulter un expert-comptable pour l'interpretation des tendances.\n"
            "3. Comparer les resultats avec l'exercice precedent."
        ),
        generated_at=datetime.now(UTC),
        used_model="fallback",
        is_fallback=True,
    )


def _extract_json(raw: str) -> dict:

    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()

    return json.loads(text)


async def generate_analysis(kpis: KPIResult, config=None, enabled: bool = True) -> AIAnalysis:
    config = config or settings
    if not enabled:
        result = _build_fallback(kpis)
        result.used_model = "local"
        result.resume = result.resume.replace(
            "L'analyse IA detaillee n'a pas pu etre generee.",
            "Synthese automatique des indicateurs.",
        )
        result.recommandations = (
            "Verifier les alertes et rapprocher les montants des pieces comptables."
        )
        return result
    active_client = client
    owned = active_client is None
    if owned:
        if not config.gemini_api_key or config.gemini_api_key == "gemini_key":
            return _build_fallback(kpis)
        active_client = genai.Client(
            api_key=config.gemini_api_key,
            http_options=types.HttpOptions(timeout=int(config.llm_timeout_seconds * 1000)),
        )
    try:
        return await _generate_with_client(kpis, active_client, config)
    finally:
        if owned:
            await active_client.aio.aclose()


async def _generate_with_client(kpis: KPIResult, active_client, config) -> AIAnalysis:

    logger.info(f"Generating AI analysis for year {kpis.annee} via {config.llm_model}")

    prompt = _build_prompt(kpis)
    last_exception = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Gemini attempt {attempt}/{MAX_RETRIES}")

            response = await asyncio.wait_for(
                active_client.aio.models.generate_content(
                    model=config.llm_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        response_mime_type="application/json",
                        response_schema={
                            "type": "object",
                            "required": ["resume", "tendances", "recommandations"],
                            "properties": {
                                k: {"type": "string"}
                                for k in ("resume", "tendances", "recommandations")
                            },
                        },
                    ),
                ),
                timeout=config.llm_timeout_seconds,
            )

            raw: str = response.text or ""

            if not raw or not raw.strip():
                raise ValueError("Gemini returned empty content")

            parsed: dict = _extract_json(raw)
            if not isinstance(parsed, dict):
                raise ValueError("Gemini response must be an object")

            for key in ("resume", "tendances", "recommandations"):
                if isinstance(parsed.get(key), list):
                    parsed[key] = "\n".join(parsed[key])

            missing_keys = {"resume", "tendances", "recommandations"} - set(parsed.keys())
            if missing_keys:
                raise ValueError(f"Gemini response missing keys: {missing_keys}")

            logger.info(f"AI analysis generated successfully (attempt {attempt})")

            return AIAnalysis(
                resume=parsed["resume"],
                tendances=parsed["tendances"],
                recommandations=parsed["recommandations"],
                generated_at=datetime.now(UTC),
                used_model=config.llm_model,
                is_fallback=False,
            )

        except genai_errors.APIError as e:
            logger.warning("Gemini API failure (attempt %s)", attempt)
            last_exception = e

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Attempt {attempt}/{MAX_RETRIES} - Parsing error: {e}")
            last_exception = e

        except Exception as e:
            logger.warning("Gemini unavailable: %s (attempt %s)", type(e).__name__, attempt)
            last_exception = e

        if attempt < MAX_RETRIES:
            logger.info(f"Retrying in {RETRY_DELAY}s...")
            await asyncio.sleep(RETRY_DELAY)

    logger.error("AI fallback after %s attempts (%s)", MAX_RETRIES, type(last_exception).__name__)
    return _build_fallback(kpis)
