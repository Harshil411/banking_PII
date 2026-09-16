"""Runtime configuration.

Everything that differs between a laptop, a container and CI is an environment
variable with a ``PII_`` prefix. v1 had none: host, port, model paths, schema
path and CORS origins were all literals in the module, which is why it could
not be containerised without editing source.

On path resolution: the taxonomy default is derived from this file's location,
which is the pattern v1 used and got burned by. The difference is that v1
guarded every read with ``.exists()`` and degraded to an empty dict, so a
wrong path produced an empty API response instead of an error. Here a missing
taxonomy raises at startup and the service does not come up. A path default
that can be wrong is fine; a wrong path that looks like an empty result is not.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent


class Settings(BaseSettings):
    """Service configuration, overridable through ``PII_*`` environment variables."""

    model_config = SettingsConfigDict(env_prefix="PII_", env_file=".env", extra="ignore")

    taxonomy_path: Path = Field(default=PROJECT_ROOT / "taxonomy" / "entities.yaml")

    #: The committed evaluation baseline, served at /v1/evaluation so the demo
    #: page shows the numbers CI gates on rather than figures typed into HTML.
    #: Optional: a missing file disables the endpoint, not the service.
    evaluation_path: Path = Field(default=PROJECT_ROOT / "evaluation" / "baseline.json")

    #: CSP frame-ancestors. "'self'" forbids embedding the demo in another
    #: site's iframe, which is the safe default for a page that echoes pasted
    #: text. Set to the portfolio origin to allow embedding there.
    frame_ancestors: str = "'self'"

    #: Which detector to build. "deterministic" needs no model and starts
    #: instantly; "presidio" adds spaCy NER for the model-carried types. The
    #: evaluation harness compares engines by setting this alone.
    detector: str = "presidio"
    spacy_model: str = "en_core_web_md"

    #: Requests above this size are rejected rather than queued. A detection
    #: service with no input ceiling is a denial-of-service target: spaCy's
    #: memory use grows with document length.
    max_text_bytes: int = 200_000
    max_batch_size: int = 64

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    #: Comma-separated origins, or "*" for any. The demo page is served from
    #: the same origin as the API and needs none of this; it exists for
    #: callers embedding the service elsewhere.
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins.strip():
            return []
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def get_settings() -> Settings:
    """Build settings from the environment.

    Deliberately not cached. A cached module-level singleton is what makes a
    service awkward to test and impossible to run twice in one process with
    different configurations -- which is exactly what the evaluation harness
    needs to do.
    """
    return Settings()
