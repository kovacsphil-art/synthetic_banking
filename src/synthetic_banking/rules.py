"""Controlled selection and execution of account-balance rules."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike


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


def load_rule_proposals(spark, source_run_id: str, batch_id: str = "") -> tuple[RuleProposal, ...]:
    """Snapshot proposal metadata for the SOURCE run and, when supplied, one batch."""
    proposals_table = "workspace.synthetic_profile.ai_rule_proposals"
    batches_table = "workspace.synthetic_profile.ai_rule_batches"
    if not all(spark.catalog.tableExists(name) for name in (proposals_table, batches_table)):
        return ()

    provenance_columns = {"batch_id", "reviewed_by", "reviewed_at", "legacy_approval_status"}
    if not provenance_columns.issubset(spark.table(proposals_table).columns):
        return ()

    rows = spark.sql(
        """
        SELECT p.proposal_id, p.source_run_id, p.target_table, p.target_column,
               p.rule_type, p.parent_columns, p.approval_status, p.batch_id,
               CASE WHEN TRIM(p.reviewed_by) <> ''
                      AND p.reviewed_at IS NOT NULL
                      AND p.legacy_approval_status IS NULL
                      AND b.batch_id IS NOT NULL
                    THEN TRUE ELSE FALSE END AS has_review_provenance
        FROM workspace.synthetic_profile.ai_rule_proposals p
        LEFT JOIN (
            SELECT DISTINCT batch_id
            FROM workspace.synthetic_profile.ai_rule_batches
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
        events.append(RuleExecution(
            proposal_id=proposal.proposal_id,
            batch_id=proposal.batch_id,
            target_table=proposal.target_table,
            target_column=proposal.target_column,
            rule_type=proposal.rule_type,
            outcome="SKIPPED",
            reason=skip.reason,
            implementation_name=skip.implementation_name,
            execution_order=None,
            rows_processed=0,
            parent_columns=proposal.parent_columns,
            approval_status=proposal.approval_status,
            proposed=True,
            approved=proposal.approved,
            implemented=skip.implementation_name is not None,
            applied=False,
        ))

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
