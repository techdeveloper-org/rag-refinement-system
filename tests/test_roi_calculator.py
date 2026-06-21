"""Unit tests for the ROI calculator GTM asset (backend.app.productization)."""

from __future__ import annotations

import math

import pytest

from backend.app.productization.roi_calculator import (
    CONSERVATIVE_REDUCTION,
    EXPECTED_REDUCTION,
    OPTIMISTIC_REDUCTION,
    calculate_roi,
)


def test_expected_case_reduces_only_addressable_spend() -> None:
    report = calculate_roi(current_monthly_spend_usd=10_000.0, context_spend_fraction=0.7)

    assert report.addressable_monthly_spend_usd == pytest.approx(7_000.0)
    assert report.expected.monthly_savings_usd == pytest.approx(
        7_000.0 * EXPECTED_REDUCTION
    )
    assert report.expected.projected_monthly_spend_usd == pytest.approx(
        10_000.0 - 7_000.0 * EXPECTED_REDUCTION
    )


def test_band_is_ordered_conservative_to_optimistic() -> None:
    report = calculate_roi(current_monthly_spend_usd=5_000.0)

    assert report.conservative.token_reduction_pct == CONSERVATIVE_REDUCTION
    assert report.optimistic.token_reduction_pct == OPTIMISTIC_REDUCTION
    assert (
        report.conservative.monthly_savings_usd
        < report.expected.monthly_savings_usd
        < report.optimistic.monthly_savings_usd
    )


def test_annual_savings_is_twelve_times_expected_month() -> None:
    report = calculate_roi(current_monthly_spend_usd=2_500.0)

    assert report.annual_savings_expected_usd == pytest.approx(
        report.expected.monthly_savings_usd * 12
    )


def test_full_context_fraction_makes_entire_spend_addressable() -> None:
    report = calculate_roi(current_monthly_spend_usd=1_000.0, context_spend_fraction=1.0)

    assert report.addressable_monthly_spend_usd == pytest.approx(1_000.0)
    assert report.optimistic.monthly_savings_usd == pytest.approx(
        1_000.0 * OPTIMISTIC_REDUCTION
    )


def test_zero_spend_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        calculate_roi(current_monthly_spend_usd=0.0)


def test_negative_spend_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        calculate_roi(current_monthly_spend_usd=-1.0)


def test_nan_spend_is_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        calculate_roi(current_monthly_spend_usd=math.nan)


@pytest.mark.parametrize("fraction", [0.0, -0.1, 1.1, 2.0])
def test_out_of_range_context_fraction_is_rejected(fraction: float) -> None:
    with pytest.raises(ValueError, match="0.0, 1.0"):
        calculate_roi(current_monthly_spend_usd=1_000.0, context_spend_fraction=fraction)
