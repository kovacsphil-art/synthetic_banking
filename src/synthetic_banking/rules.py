"""Controlled selection and execution of balance and conditional account rules."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike
from synthetic_banking.config import PROFILE_SCHEMA


def available_to_buy(credit_limit: ArrayLike, current_balance: ArrayLike):
    """Apply the existing available-to-buy formula to aligned account rows."""
    return np.maximum(
        np.asarray(credit_limit, dtype=float) - np.asarray(current_balance, dtype=float),
        0,
    )


def overlimit_amount(credit_limit: ArrayLike, current_balance: ArrayLike):
    """Apply the existing overlimit formula to aligned account rows."""
    return np.maximum(
        np.asarray(current_balance, dtype=float) - np.asarray(credit_limit, dtype=float),
        0,
    )


BalanceImplementation = Callable[[ArrayLike, ArrayLike], np.ndarray | np.float64]

_BALANCE_TABLE = "TKQ_ACCOUNT_BALANCE"
_BALANCE_PARENT_COLUMNS = (
    "TKQ_ACCOUNT.CREDIT_LIMIT_AMT",
    "TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT",
)
_BALANCE_PARENTS = frozenset(_BALANCE_PARENT_COLUMNS)
_BALANCE_PARENT_ALIASES = {
    parent.rsplit(".", 1)[-1]: parent for parent in _BALANCE_PARENTS
}
_IMPLEMENTATIONS: dict[str, BalanceImplementation] = {
    "AVAILABLE_TO_BUY_AMT": available_to_buy,
    "OVERLIMIT_AMT": overlimit_amount,
}

_UTILIZATION_BUCKETS = ("0-30%", "30-60%", "60-80%", "80-100%", "100%+")
_DELINQUENCY_TARGET = ("TKQ_ACCOUNT", "PAST_DUE_INDICATO_CD")
_UTILIZATION_PARENT = "TKQ_ACCOUNT.UTILIZATION_RATE"
_UTILIZATION_ALIASES = {
    "UTILIZATION_RATE", "_UTILIZATION_RATE",
    "TKQ_ACCOUNT.UTILIZATION_RATE", "TKQ_ACCOUNT._UTILIZATION_RATE",
}


class ConditionalRuleError(ValueError):
    """Measured evidence or generated inputs cannot support the conditional rule."""


def delinquency_by_utilization(
    source_run_id: str,
    utilization: ArrayLike,
    conditional_profile: Iterable[Mapping[str, object]] | None,
    uniform_draws: ArrayLike,
) -> np.ndarray:
    """Sample delinquency from measured SOURCE bucket rates using caller-supplied draws."""
    if not source_run_id:
        raise ValueError("A pinned SOURCE run ID is required.")
    utilization = np.asarray(utilization, dtype=float)
    draws = np.asarray(uniform_draws, dtype=float)
    if utilization.ndim != 1 or draws.shape != utilization.shape:
        raise ValueError("Utilization and random draws must be aligned one-dimensional arrays.")
    if not np.all(np.isfinite(draws) & (draws >= 0) & (draws < 1)):
        raise ValueError("Random draws must be finite values in [0, 1).")
    if not np.all(np.isfinite(utilization)):
        raise ConditionalRuleError("invalid_utilization")

    rates = {}
    if conditional_profile is None:
        conditional_profile = ()
    for row in conditional_profile:
        if (
            row.get("run_id") != source_run_id
            or row.get("entity_name") != "ACCOUNT"
            or row.get("condition_variable") != "UTILIZATION_RATE"
            or row.get("outcome_variable") != "PAST_DUE_INDICATO_CD"
        ):
            continue
        bucket = row.get("condition_bucket")
        if bucket not in _UTILIZATION_BUCKETS:
            continue
        try:
            count = float(row["record_count"])
            rate = float(row["outcome_rate"])
        except (KeyError, TypeError, ValueError):
            raise ConditionalRuleError("invalid_conditional_profile") from None
        if (
            bucket in rates
            or not np.isfinite(count) or count <= 0 or count != np.floor(count)
            or not np.isfinite(rate) or not 0 <= rate <= 1
        ):
            raise ConditionalRuleError("invalid_conditional_profile")
        rates[bucket] = rate

    buckets = np.select(
        [utilization < .30, utilization < .60, utilization < .80, utilization <= 1.00],
        _UTILIZATION_BUCKETS[:4], default=_UTILIZATION_BUCKETS[4],
    )
    if any(bucket not in rates for bucket in np.unique(buckets)):
        raise ConditionalRuleError("missing_conditional_profile")
    probabilities = np.array([rates[bucket] for bucket in buckets], dtype=float)
    return draws < probabilities


_CONDITIONAL_IMPLEMENTATIONS = {_DELINQUENCY_TARGET: delinquency_by_utilization}


@dataclass(frozen=True)
class RuleProposal:
    proposal_id: str
    source_run_id: str
    target_table: str
    target_column: str
    rule_type: str
    parent_columns: tuple[str, ...]
    approval_status: str
    batch_id: str | None = None
    has_review_provenance: bool = False

    @property
    def approved(self) -> bool:
        return (
            self.approval_status == "APPROVED"
            and self.batch_id is not None
            and self.has_review_provenance
        )


@dataclass(frozen=True)
class BalanceRuleSelection:
    target_column: str
    implementation: BalanceImplementation
    # No proposal ID means the implementation runs as legacy behavior.
    approved_proposal_id: str | None


@dataclass(frozen=True)
class SkippedProposal:
    proposal_id: str
    reason: str
    implementation_name: str | None


@dataclass(frozen=True)
class RuleExecution:
    proposal_id: str | None
    batch_id: str | None
    target_table: str
    target_column: str
    rule_type: str
    outcome: str
    reason: str | None
    implementation_name: str | None
    execution_order: int | None
    rows_processed: int
    parent_columns: tuple[str, ...]
    approval_status: str | None
    proposed: bool
    approved: bool
    implemented: bool
    applied: bool


def _skipped_execution(proposal: RuleProposal, reason: str, implementation_name: str | None) -> RuleExecution:
    return RuleExecution(
        proposal_id=proposal.proposal_id,
        batch_id=proposal.batch_id,
        target_table=proposal.target_table,
        target_column=proposal.target_column,
        rule_type=proposal.rule_type,
        outcome="SKIPPED",
        reason=reason,
        implementation_name=implementation_name,
        execution_order=None,
        rows_processed=0,
        parent_columns=proposal.parent_columns,
        approval_status=proposal.approval_status,
        proposed=True,
        approved=proposal.approved,
        implemented=implementation_name is not None,
        applied=False,
    )


def partition_rule_proposals(
    proposals: Iterable[RuleProposal],
) -> tuple[tuple[RuleProposal, ...], tuple[RuleProposal, ...]]:
    """Route each proposal to one execution phase so it receives one proposal audit row."""
    balance, conditional = [], []
    for proposal in proposals:
        if (proposal.target_table, proposal.target_column) in _CONDITIONAL_IMPLEMENTATIONS:
            conditional.append(proposal)
        else:
            balance.append(proposal)
    return tuple(balance), tuple(conditional)


def load_rule_proposals(spark, source_run_id: str, batch_id: str = "") -> tuple[RuleProposal, ...]:
    """Snapshot proposal metadata for the SOURCE run and, when supplied, one batch."""
    proposals_table = f"{PROFILE_SCHEMA}.ai_rule_proposals"
    batches_table = f"{PROFILE_SCHEMA}.ai_rule_batches"
    if not all(spark.catalog.tableExists(name) for name in (proposals_table, batches_table)):
        return ()

    provenance_columns = {"batch_id", "reviewed_by", "reviewed_at", "legacy_approval_status"}
    if not provenance_columns.issubset(spark.table(proposals_table).columns):
        return ()

    rows = spark.sql(
        f"""
        SELECT p.proposal_id, p.source_run_id, p.target_table, p.target_column,
               p.rule_type, p.parent_columns, p.approval_status, p.batch_id,
               CASE WHEN TRIM(p.reviewed_by) <> ''
                      AND p.reviewed_at IS NOT NULL
                      AND p.legacy_approval_status IS NULL
                      AND b.batch_id IS NOT NULL
                    THEN TRUE ELSE FALSE END AS has_review_provenance
        FROM {PROFILE_SCHEMA}.ai_rule_proposals p
        LEFT JOIN (
            SELECT DISTINCT batch_id
            FROM {PROFILE_SCHEMA}.ai_rule_batches
            WHERE source_run_id = :source_run_id
        ) b ON b.batch_id = p.batch_id
        WHERE p.source_run_id = :source_run_id
          AND (:batch_id = '' OR p.batch_id = :batch_id)
          AND TRIM(p.proposal_id) <> ''
        ORDER BY p.batch_id, p.proposal_id
        """,
        args={"source_run_id": source_run_id, "batch_id": batch_id},
    ).collect()
    return tuple(
        RuleProposal(
            proposal_id=row["proposal_id"],
            source_run_id=row["source_run_id"],
            target_table=row["target_table"],
            target_column=row["target_column"],
            rule_type=row["rule_type"],
            parent_columns=tuple(row["parent_columns"] or ()),
            approval_status=row["approval_status"],
            batch_id=row["batch_id"],
            has_review_provenance=bool(row["has_review_provenance"]),
        )
        for row in rows
    )


def _match_balance_implementation(
    proposal: RuleProposal,
) -> tuple[BalanceImplementation | None, str | None]:
    if (
        proposal.target_table != _BALANCE_TABLE
        or proposal.target_column not in _IMPLEMENTATIONS
        or proposal.rule_type != "DERIVED"
    ):
        return None, "no_implementation"

    parents = {_BALANCE_PARENT_ALIASES.get(parent, parent) for parent in proposal.parent_columns}
    if len(proposal.parent_columns) != len(_BALANCE_PARENTS) or parents != _BALANCE_PARENTS:
        return None, "parent_mismatch"

    return _IMPLEMENTATIONS[proposal.target_column], None


def plan_balance_rules(
    source_run_id: str,
    proposals: Iterable[RuleProposal],
    *,
    has_credit_limit: bool = True,
) -> tuple[tuple[BalanceRuleSelection, ...], tuple[SkippedProposal, ...]]:
    """Select pilot rules against a caller-pinned SOURCE run.

    Only the two known bare parent names can be resolved to qualified names.
    The caller supplies aligned, already-generated credit limits and balances.
    """
    if not source_run_id:
        raise ValueError("A pinned SOURCE run ID is required.")

    candidates: dict[str, list[RuleProposal]] = {
        target: [] for target in _IMPLEMENTATIONS
    }
    skipped: list[SkippedProposal] = []

    for proposal in proposals:
        implementation, reason = _match_balance_implementation(proposal)
        if proposal.source_run_id != source_run_id:
            reason = "source_run_mismatch"
        elif proposal.approval_status != "APPROVED":
            reason = "not_approved"
        elif not proposal.approved:
            reason = "unverified_approval"
        elif implementation is not None and not has_credit_limit:
            reason = "missing_credit_limit"

        if reason is None:
            candidates[proposal.target_column].append(proposal)
        else:
            skipped.append(SkippedProposal(
                proposal.proposal_id, reason, implementation.__name__ if implementation else None
            ))

    selections = []
    for target, implementation in _IMPLEMENTATIONS.items():
        matches = candidates[target]
        if len(matches) > 1:
            skipped.extend(
                SkippedProposal(proposal.proposal_id, "conflicting_approvals", implementation.__name__)
                for proposal in matches
            )
        proposal_id = matches[0].proposal_id if len(matches) == 1 else None
        selections.append(BalanceRuleSelection(target, implementation, proposal_id))

    return tuple(selections), tuple(skipped)


def apply_balance_rules(
    source_run_id: str,
    proposals: Iterable[RuleProposal],
    credit_limit: ArrayLike,
    current_balance: ArrayLike,
    *,
    has_credit_limit: bool = True,
) -> tuple[dict[str, np.ndarray | np.float64], tuple[RuleExecution, ...]]:
    """Run the fixed formulas and describe which path produced each result."""
    proposals = tuple(proposals)
    selections, skipped = plan_balance_rules(
        source_run_id, proposals, has_credit_limit=has_credit_limit
    )
    by_id = {proposal.proposal_id: proposal for proposal in proposals}
    events = []
    for skip in skipped:
        proposal = by_id[skip.proposal_id]
        events.append(_skipped_execution(proposal, skip.reason, skip.implementation_name))

    amounts = {}
    for order, selection in enumerate(selections, start=1):
        amounts[selection.target_column] = selection.implementation(credit_limit, current_balance)
        proposal = by_id.get(selection.approved_proposal_id)
        rows_processed = int(np.size(amounts[selection.target_column]))
        if proposal is None:
            outcome, reason = "LEGACY_FALLBACK", "no_eligible_approval"
        elif rows_processed == 0:
            outcome, reason = "SKIPPED", "no_rows"
        else:
            outcome, reason = "APPLIED", None

        events.append(RuleExecution(
            proposal_id=proposal.proposal_id if proposal else None,
            batch_id=proposal.batch_id if proposal else None,
            target_table=_BALANCE_TABLE,
            target_column=selection.target_column,
            rule_type="DERIVED",
            outcome=outcome,
            reason=reason,
            implementation_name=selection.implementation.__name__,
            execution_order=order,
            rows_processed=rows_processed,
            parent_columns=proposal.parent_columns if proposal else _BALANCE_PARENT_COLUMNS,
            approval_status=proposal.approval_status if proposal else None,
            proposed=proposal is not None,
            approved=proposal.approved if proposal else False,
            implemented=True,
            applied=outcome == "APPLIED",
        ))

    return amounts, tuple(events)


def apply_delinquency_rule(
    source_run_id: str,
    proposals: Iterable[RuleProposal],
    utilization: ArrayLike,
    conditional_profile: Iterable[Mapping[str, object]] | None,
    uniform_draws: ArrayLike,
    legacy_probabilities: ArrayLike,
) -> tuple[np.ndarray, tuple[RuleExecution, ...]]:
    """Apply one reviewed conditional rule, or preserve the caller's legacy sampling path."""
    if not source_run_id:
        raise ValueError("A pinned SOURCE run ID is required.")
    utilization = np.asarray(utilization, dtype=float)
    draws = np.asarray(uniform_draws, dtype=float)
    legacy = np.asarray(legacy_probabilities, dtype=float)
    if utilization.ndim != 1 or utilization.shape != draws.shape or draws.shape != legacy.shape:
        raise ValueError("Utilization, random draws, and legacy probabilities must be aligned arrays.")
    events, candidates = [], []
    for proposal in proposals:
        implementation = _CONDITIONAL_IMPLEMENTATIONS.get((proposal.target_table, proposal.target_column))
        if implementation is None or proposal.rule_type != "CONDITIONAL":
            implementation, reason = None, "no_implementation"
        elif len(proposal.parent_columns) != 1 or proposal.parent_columns[0] not in _UTILIZATION_ALIASES:
            implementation, reason = None, "parent_mismatch"
        else:
            reason = None
        if proposal.source_run_id != source_run_id:
            reason = "source_run_mismatch"
        elif proposal.approval_status != "APPROVED":
            reason = "not_approved"
        elif not proposal.approved:
            reason = "unverified_approval"
        if reason is None:
            candidates.append(proposal)
        else:
            events.append(_skipped_execution(
                proposal, reason, implementation.__name__ if implementation else None,
            ))

    selected = candidates[0] if len(candidates) == 1 else None
    if len(candidates) > 1:
        events.extend(_skipped_execution(
            proposal, "conflicting_approvals", delinquency_by_utilization.__name__,
        ) for proposal in candidates)
    if selected is not None:
        try:
            sampled = _CONDITIONAL_IMPLEMENTATIONS[_DELINQUENCY_TARGET](
                source_run_id, utilization, conditional_profile, draws,
            )
        except ConditionalRuleError as error:
            events.append(_skipped_execution(selected, str(error), delinquency_by_utilization.__name__))
        else:
            outcome = "APPLIED" if sampled.size else "SKIPPED"
            events.append(RuleExecution(
                proposal_id=selected.proposal_id, batch_id=selected.batch_id,
                target_table=selected.target_table, target_column=selected.target_column,
                rule_type="CONDITIONAL", outcome=outcome,
                reason=None if sampled.size else "no_rows",
                implementation_name=delinquency_by_utilization.__name__, execution_order=3,
                rows_processed=int(sampled.size), parent_columns=selected.parent_columns,
                approval_status=selected.approval_status, proposed=True, approved=True,
                implemented=True, applied=outcome == "APPLIED",
            ))
            return sampled, tuple(events)

    sampled = draws < legacy
    events.append(RuleExecution(
        proposal_id=None, batch_id=None, target_table=_DELINQUENCY_TARGET[0],
        target_column=_DELINQUENCY_TARGET[1], rule_type="CONDITIONAL", outcome="LEGACY_FALLBACK",
        reason="no_eligible_approval", implementation_name="get_delinquency_probability",
        execution_order=3, rows_processed=int(sampled.size), parent_columns=(_UTILIZATION_PARENT,),
        approval_status=None, proposed=False, approved=False, implemented=True, applied=False,
    ))
    return sampled, tuple(events)
