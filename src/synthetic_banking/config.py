"""Shared pipeline defaults. Notebook widgets remain the place for per-run choices."""

from dataclasses import dataclass
import re

CATALOG = "workspace"
PROFILE_SCHEMA = f"{CATALOG}.synthetic_profile"
GENERATED_SCHEMA = f"{CATALOG}.synthetic_generated"
STAGING_SCHEMA = f"{CATALOG}.default"
SOURCE_DIR = "/Volumes/workspace/default/scotia"
CSV_OUTPUT_DIR = f"{SOURCE_DIR}/generated_row_level"
MODEL_ENDPOINT = "system.ai.gpt-oss-20b"
DEFAULT_SEED = 42
DEFAULT_CUSTOMERS = 10_000
SOURCE_ALIASES = {
    "PERSON": "bronze_cis_mdm.TOS_PERSON",
    "CUSTOMER_ACCOUNT_REL": "bronze_cis_mdm.TOS_CUSTOMER_ACCOUNT_RELATIONSHIP",
    "CUSTOMER_RELATIONSHIP": "bronze_cis_mdm.TOS_CUSTOMER_RELATIONSHIP",
    "TKQ_ACCOUNT": "bronze_tsys.KQ_TKQ_ACCOUNT",
    "TKQ_ACCOUNT_BALANCE": "bronze_tsys.KQ_TKQ_ACCOUNT_BALANCE",
    "TRADELINES": "bronze_transunion.tradlines_file",
}


@dataclass(frozen=True)
class GenerationSettings:
    num_customers: int = DEFAULT_CUSTOMERS
    seed: int = DEFAULT_SEED
    pilot_batch_id: str = ""
    pilot_proposal_ids: tuple[str, ...] = ()
    # Job batch scoping is separate from the stricter one-to-three-rule manual pilot.
    proposal_batch_id: str = ""


def configured_sql(text):
    """Qualify trusted repository SQL definitions using the shared defaults.

    This receives static SQL from source code, never proposed_rule/model text.
    """
    text = (text.replace("workspace.synthetic_profile", PROFILE_SCHEMA)
            .replace("workspace.synthetic_generated", GENERATED_SCHEMA)
            .replace("workspace.default", STAGING_SCHEMA)
            .replace("workspace.", CATALOG + ".")
            .replace("USE CATALOG workspace", f"USE CATALOG {CATALOG}"))
    return re.sub(r"(?<![\w.])synthetic_profile\b", PROFILE_SCHEMA, text)
