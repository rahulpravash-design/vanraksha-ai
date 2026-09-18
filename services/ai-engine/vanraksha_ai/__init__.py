"""VANRAKSHA AI engine.

Turns field-level livestock health reports into explainable risk signals,
geo-temporal early warnings, and routed response actions.

The package has no third-party runtime dependencies, so it can be imported
from the API service, a notebook, a test harness, or a batch job without
carrying a web framework or an ORM along with it.
"""

from .models import (
    NORMAL_TEMPERATURE_C,
    Contribution,
    Observation,
    RiskAssessment,
    RiskBand,
    StatutoryCaution,
    VaccinationStatus,
)
from .pipeline import (
    PIPELINE_VERSION,
    Alert,
    AlertKind,
    Audience,
    SurveillancePipeline,
    SweepResult,
    default_pipeline,
)
from .risk import ENGINE_VERSION, RiskEngine, assess

__version__ = "1.0.0"

__all__ = [
    "Observation", "RiskAssessment", "RiskBand", "Contribution",
    "StatutoryCaution", "VaccinationStatus", "NORMAL_TEMPERATURE_C",
    "RiskEngine", "assess", "ENGINE_VERSION",
    "SurveillancePipeline", "SweepResult", "Alert", "AlertKind", "Audience",
    "default_pipeline", "PIPELINE_VERSION", "__version__",
]
