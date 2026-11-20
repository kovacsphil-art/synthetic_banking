"""The legacy arbitrary-CSV archive is intentionally disabled for row release."""

from synthetic_banking.config import CSV_OUTPUT_DIR, SOURCE_DIR
from synthetic_banking.privacy import PrivacyGateError


def zip_existing_csvs(output_dir=CSV_OUTPUT_DIR, *, local_path="/tmp/RCAR_generated_row_level.zip", volume_path=SOURCE_DIR + "/RCAR_generated_row_level.zip"):
    """No existing CSV manifest proves these files came from an assessed generation.

    A future generation-bound exporter must call privacy.require_row_level_release
    with exact SOURCE/generation/assessment IDs before writing or distributing rows.
    """
    raise PrivacyGateError(
        "Row-level CSV packaging is disabled: existing files are not bound to a privacy-assessed generation. "
        "A generation-bound exporter must enforce require_row_level_release before any dataset download."
    )
