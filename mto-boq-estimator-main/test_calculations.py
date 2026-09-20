"""
Unit tests for engineering/calculations.py.

Run with:  pytest tests/
These tests lock in the arithmetic of the deterministic calculation layer
so future refactors can't silently change a formula.
"""
import math

import pytest

from ai.extraction import default_building_params
from engineering.calculations import (
    compute_excavation,
    compute_footing_concrete,
    compute_column_concrete,
    generate_all_quantities,
    steel_sanity_check,
)
from models.schemas import ConfidenceLevel, Estimate, FootingSpec, ProjectInputs, Source


def make_estimate(value, confidence=ConfidenceLevel.HIGH):
    return Estimate(value=value, confidence=confidence, source=Source.USER_INPUT, note="test")


def test_excavation_volume_basic():
    footings = FootingSpec(
        footing_type="isolated",
        count=make_estimate(4),
        length_m=make_estimate(1.0),
        width_m=make_estimate(1.0),
        depth_m=make_estimate(1.0),
    )
    item = compute_excavation(footings, "Hard soil")
    # (1 + 0.3) * (1 + 0.3) * 1.0 * 1.0(slope factor) * 4 footings
    expected = 4 * (1.0 + 0.3) * (1.0 + 0.3) * 1.0 * 1.0
    assert math.isclose(item.quantity, round(expected, 3), rel_tol=1e-6)
    assert item.unit == "m3"
    assert item.category == "Excavation"


def test_footing_concrete_volume():
    footings = FootingSpec(
        footing_type="isolated",
        count=make_estimate(6),
        length_m=make_estimate(1.5),
        width_m=make_estimate(1.5),
        depth_m=make_estimate(0.6),
    )
    item = compute_footing_concrete(footings, "M20")
    expected = 6 * 1.5 * 1.5 * 0.6
    assert math.isclose(item.quantity, round(expected, 3), rel_tol=1e-6)


def test_column_concrete_includes_plinth_height():
    from models.schemas import ColumnSpec

    columns = ColumnSpec(
        count=make_estimate(4),
        width_m=make_estimate(0.3),
        depth_m=make_estimate(0.3),
        height_per_floor_m=make_estimate(3.0),
    )
    item = compute_column_concrete(columns, num_floors=2, grade="M20")
    # total_height = 3.0*2 + 0.6 (default plinth height) = 6.6
    expected = 4 * 0.3 * 0.3 * 6.6
    assert math.isclose(item.quantity, round(expected, 3), rel_tol=1e-6)


def test_confidence_propagation_is_worst_case():
    footings = FootingSpec(
        footing_type="isolated",
        count=make_estimate(4, ConfidenceLevel.HIGH),
        length_m=make_estimate(1.0, ConfidenceLevel.LOW),
        width_m=make_estimate(1.0, ConfidenceLevel.HIGH),
        depth_m=make_estimate(1.0, ConfidenceLevel.HIGH),
    )
    item = compute_excavation(footings, "Ordinary soil")
    assert item.confidence == ConfidenceLevel.LOW


def test_generate_all_quantities_with_defaults_produces_positive_values():
    params = default_building_params()
    inputs = ProjectInputs(project_name="Unit Test House")
    items = generate_all_quantities(params, inputs)

    assert len(items) > 15
    for item in items:
        assert item.quantity >= 0, f"{item.item_code} has negative quantity"
        assert item.unit
        assert item.formula


def test_steel_sanity_check_flags_out_of_range():
    ok = steel_sanity_check(structural_concrete_m3=10.0, total_steel_kg=1000.0)  # 100 kg/m3
    assert ok["status"] == "OK"

    review = steel_sanity_check(structural_concrete_m3=10.0, total_steel_kg=5000.0)  # 500 kg/m3
    assert review["status"] == "Review"


def test_steel_sanity_check_handles_zero_concrete():
    result = steel_sanity_check(structural_concrete_m3=0.0, total_steel_kg=100.0)
    assert result["status"] == "n/a"


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
