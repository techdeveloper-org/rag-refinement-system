"""ROI calculator for the RAG Refinement System (PRD GTM asset, C8).

Projects the monthly LLM-spend savings a customer can expect from the
documented token-reduction range when they place this refinement layer in
front of their existing RAG stack. The savings band is anchored to the
PRD-verified range of 40-70% average token reduction vs. full-document RAG
(PRD §15.1 / §21), with a documented conservative/expected/optimistic split.

This module is a pure-function GTM/sales utility. It performs no I/O, calls no
provider, and does not touch routing, ingestion, or persistence. The dollar
figures are projections for modeling and explicitly not a billing source of
truth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Documented token-reduction band (fraction of input tokens removed by routing
# the query to the relevant sections before retrieval). Anchored to the
# PRD-verified 40-70% range; the "expected" point is the midpoint of that band.
CONSERVATIVE_REDUCTION = 0.40
EXPECTED_REDUCTION = 0.55
OPTIMISTIC_REDUCTION = 0.70


@dataclass(frozen=True)
class SavingsProjection:
    """A single token-reduction scenario and its projected monthly saving.

    Attributes:
        label: Human-readable scenario name (conservative/expected/optimistic).
        token_reduction_pct: Fraction of context tokens removed (0.0-1.0).
        monthly_savings_usd: Projected USD saved per month at this reduction.
        projected_monthly_spend_usd: Projected post-refinement monthly spend.
    """

    label: str
    token_reduction_pct: float
    monthly_savings_usd: float
    projected_monthly_spend_usd: float


@dataclass(frozen=True)
class RoiReport:
    """Full ROI projection across the documented token-reduction band.

    Attributes:
        current_monthly_spend_usd: The customer's stated current monthly LLM
            spend attributable to retrieval context.
        context_spend_fraction: Fraction of that spend driven by retrieved
            context (the portion this layer can reduce).
        addressable_monthly_spend_usd: The context-driven, reducible slice of
            the current spend.
        conservative: Projection at the low (40%) end of the band.
        expected: Projection at the midpoint (55%) of the band.
        optimistic: Projection at the high (70%) end of the band.
        annual_savings_expected_usd: Expected-case saving multiplied to a year.
    """

    current_monthly_spend_usd: float
    context_spend_fraction: float
    addressable_monthly_spend_usd: float
    conservative: SavingsProjection
    expected: SavingsProjection
    optimistic: SavingsProjection
    annual_savings_expected_usd: float


def _round_money(value: float) -> float:
    """Round a USD amount to cents.

    Args:
        value: Raw USD amount.

    Returns:
        The amount rounded to two decimal places.
    """
    return round(value, 2)


def _project(
    label: str,
    reduction: float,
    current_spend: float,
    addressable_spend: float,
) -> SavingsProjection:
    """Build one savings projection for a given reduction fraction.

    Only the addressable (context-driven) slice of spend is reduced; the
    remainder of the bill (prompt scaffolding, generation, fixed costs) is left
    untouched, which keeps the projection honest rather than headline-inflated.

    Args:
        label: Scenario name.
        reduction: Token-reduction fraction applied to the addressable spend.
        current_spend: Current total monthly spend.
        addressable_spend: Reducible, context-driven slice of the spend.

    Returns:
        A SavingsProjection for this scenario.
    """
    monthly_savings = addressable_spend * reduction
    projected_spend = current_spend - monthly_savings
    return SavingsProjection(
        label=label,
        token_reduction_pct=reduction,
        monthly_savings_usd=_round_money(monthly_savings),
        projected_monthly_spend_usd=_round_money(projected_spend),
    )


def calculate_roi(
    current_monthly_spend_usd: float,
    context_spend_fraction: float = 0.7,
) -> RoiReport:
    """Project monthly LLM-spend savings from the token-reduction range.

    Models the saving as: only the context-driven slice of the current bill
    (``context_spend_fraction``) is addressable, and routing removes the
    documented 40/55/70% of that slice. This avoids over-promising by never
    reducing the non-retrieval portion of the bill.

    Args:
        current_monthly_spend_usd: Current monthly LLM spend in USD. Must be a
            finite, non-negative number.
        context_spend_fraction: Fraction (0.0-1.0] of the spend attributable to
            retrieved context that this layer can reduce. Defaults to 0.7, a
            common context-heavy RAG profile.

    Returns:
        An :class:`RoiReport` with conservative, expected, and optimistic
        projections plus the expected annual saving.

    Raises:
        ValueError: If the spend is negative/non-finite or the context
            fraction is outside the (0.0, 1.0] range.
    """
    if current_monthly_spend_usd < 0 or math.isnan(current_monthly_spend_usd) or math.isinf(current_monthly_spend_usd):
        raise ValueError("current_monthly_spend_usd must be a finite, non-negative number")
    if not 0.0 < context_spend_fraction <= 1.0 or math.isinf(context_spend_fraction):
        raise ValueError("context_spend_fraction must be in the range (0.0, 1.0]")

    addressable = current_monthly_spend_usd * context_spend_fraction

    conservative = _project(
        "conservative", CONSERVATIVE_REDUCTION, current_monthly_spend_usd, addressable
    )
    expected = _project(
        "expected", EXPECTED_REDUCTION, current_monthly_spend_usd, addressable
    )
    optimistic = _project(
        "optimistic", OPTIMISTIC_REDUCTION, current_monthly_spend_usd, addressable
    )

    return RoiReport(
        current_monthly_spend_usd=_round_money(current_monthly_spend_usd),
        context_spend_fraction=context_spend_fraction,
        addressable_monthly_spend_usd=_round_money(addressable),
        conservative=conservative,
        expected=expected,
        optimistic=optimistic,
        annual_savings_expected_usd=_round_money(expected.monthly_savings_usd * 12),
    )
