# app/models/schemas.py
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --- API-facing schemas ---
class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UploadResponse(BaseModel):
    task_id: str = Field(..., description="Unique task identifier")
    status: TaskStatus = Field(..., description="Current task status")
    message: str = Field(..., description="Human-readable message")


class TaskStatusResponse(BaseModel):
    task_id: str = Field(..., description="Unique task identifier")
    status: TaskStatus = Field(..., description="Current task status")
    progress: int = Field(..., ge=0, le=100, description="Progress percentage (0-100)")
    error: Optional[str] = Field(None, description="Error message if failed")


class DownloadResponse(BaseModel):
    report_id: str = Field(..., description="Unique report identifier")
    filename: str = Field(..., description="Generated PDF filename")
    created_at: datetime = Field(..., description="Report creation timestamp")


# --- Internal data schemas ---


class MonthlyEntry(BaseModel):
    compte: str = Field(..., description="Account number")
    libelle: str = Field(..., description="Account description")
    nature: str = Field(..., description="Account nature (Produit/Charge)")
    montants: Dict[str, float] = Field(..., description="Monthly amounts (Janvier: value, etc.)")
    total: float = Field(..., description="Total annual amount")


class FinancialData(BaseModel):
    annee: int = Field(..., description="Accounting year")
    entrees: List[MonthlyEntry] = Field(..., description="List of accounting entries")
    produits: List[MonthlyEntry] = Field(..., description="Filtered products entries")
    charges: List[MonthlyEntry] = Field(..., description="Filtered charges entries")
    mois_disponibles: List[str] = Field(..., description="Available months in data")
    warnings: List[str] = Field(default_factory=list)


class AnomalyRecord(BaseModel):
    month: str = Field(..., description="Month of the anomaly")
    previous_month: str = Field(..., description="Previous month for comparison")
    compte: str = Field(..., description="Account number")
    libelle: str = Field(..., description="Account description")
    variation_pct: float = Field(..., description="Variation percentage compared to previous month")


class KPIResult(BaseModel):
    annee: int = Field(..., description="Accounting year")

    # Chiffre d'affaires
    ca_mensuel: Dict[str, float] = Field(..., description="Monthly revenue")
    ca_annuel: float = Field(..., description="Annual revenue")
    ca_moyenne_mensuelle: float = Field(..., description="Average monthly revenue")

    # Charges
    charges_mensuelles: Dict[str, float] = Field(..., description="Monthly expenses")
    charges_annuelles: float = Field(..., description="Annual expenses")
    charges_par_categorie: Dict[str, float] = Field(..., description="Expenses by category")

    # Résultat d'exploitation
    resultat_exploitation_mensuel: Dict[str, float] = Field(
        ..., description="Monthly operating result"
    )
    resultat_exploitation_annuel: float = Field(..., description="Annual operating result")

    # Marges
    marge_brute_mensuelle: Dict[str, float] = Field(..., description="Monthly gross margin")
    marge_brute_annuelle: float = Field(..., description="Annual gross margin")

    # Évolutions
    evolution_ca_mm: Dict[str, float] = Field(
        ..., description="Month-over-month revenue growth (%)"
    )
    evolution_charges_mm: Dict[str, float] = Field(
        ..., description="Month-over-month expenses growth (%)"
    )

    # Statistiques
    mois_plus_fort: str = Field(..., description="Month with highest revenue")
    mois_plus_faible: str = Field(..., description="Month with lowest revenue")
    charges_personnel_pourcentage: float = Field(
        ..., description="Personnel expenses as % of total expenses"
    )

    # Anomalies
    anomalies_detectees: List[AnomalyRecord] = Field(
        ..., description="Detected anomalies (e.g., unusual variations)"
    )

    # Métadonnées
    date_calcul: datetime = Field(default_factory=datetime.now, description="Calculation timestamp")


class AIAnalysis(BaseModel):
    resume: str = Field(min_length=1, max_length=6000)
    tendances: str = Field(min_length=1, max_length=8000)
    recommandations: str = Field(min_length=1, max_length=8000)
    generated_at: datetime
    used_model: str
    is_fallback: bool = False


# --- Task record ---


class TaskRecord(BaseModel):
    task_id: str
    status: TaskStatus
    progress: int = 0
    error: Optional[str] = None
    report_path: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    filename: str = ""
    year: int = 2024
    use_ai: bool = False
    csv_path: Optional[str] = None
    baseline: Optional[Dict[str, Any]] = None


class ReportSummary(BaseModel):
    task_id: str
    filename: str
    year: int
    status: TaskStatus
    progress: int
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ReportList(BaseModel):
    items: List[ReportSummary]
    total: int


class ReportDetail(ReportSummary):
    result: Optional[Dict[str, Any]] = None
