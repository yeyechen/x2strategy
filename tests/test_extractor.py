"""Tests for paper2spec.extractor — Layer 0 detection and pipeline orchestration.

Tests that require LLM calls are mocked to be deterministic.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from paper2spec.extractor import _build_strategy_focus, extract_spec
from paper2spec.operator_pitfall import (
    load_operator_pitfall_entries,
    operator_pitfall_queries_from_spec,
)
from paper2spec.models import (
    ExecutionAction,
    ExecutionPlan,
    LogicStep,
    PositionSizing,
    ExtractionResult,
    PaperContent,
    StrategyBrief,
    StrategySpec,
)


@pytest.fixture
def paper_content():
    return PaperContent(
        title="Test Paper",
        abstract="Testing paper about momentum and value",
        methodology="We combine momentum and value factors",
        signal_logic="Long top quintile momentum, short bottom",
        full_text="Full text here",
    )


# ── _build_strategy_focus ─────────────────────────────────────


class TestBuildStrategyFocus:
    def test_contains_name_and_type(self):
        brief = StrategyBrief(
            name="Distance Method",
            strategy_type="technical",
            brief_description="Pairs by min SSD",
        )
        focus = _build_strategy_focus(brief)
        assert "Distance Method" in focus
        assert "technical" in focus
        assert "Pairs by min SSD" in focus

    def test_includes_differentiation(self):
        brief = StrategyBrief(
            name="A",
            differentiation="Uses ADF test instead of distance",
        )
        focus = _build_strategy_focus(brief)
        assert "ADF test instead of distance" in focus

    def test_includes_section_hints(self):
        brief = StrategyBrief(
            name="A",
            key_section_hints=["Section 3", "Table 5"],
        )
        focus = _build_strategy_focus(brief)
        assert "Section 3" in focus
        assert "Table 5" in focus

    def test_focus_directive(self):
        brief = StrategyBrief(name="A")
        focus = _build_strategy_focus(brief)
        assert "FOCUS ON THIS SPECIFIC STRATEGY" in focus
        assert "Ignore other strategies" in focus


# ── extract_spec (mocked) ────────────────────────────────────


class TestExtractSpecSingleStrategy:
    """Tests for single-strategy detection path."""

    @patch("paper2spec.extractor._extract_multilayer")
    @patch("paper2spec.extractor._detect_strategies")
    def test_single_strategy_path(self, mock_detect, mock_multilayer, paper_content):
        mock_detect.return_value = [
            StrategyBrief(name="Only Strategy")
        ]
        mock_multilayer.return_value = StrategySpec(
            strategy_name="Only Strategy",
            strategy_type="technical",
        )

        result = extract_spec(paper_content, mode="multilayer")

        assert isinstance(result, ExtractionResult)
        assert result.num_detected == 1
        assert len(result.strategies) == 1
        assert result.strategies[0].strategy_name == "Only Strategy"
        assert result.paper_title == "Test Paper"
        # _extract_multilayer called once with no strategy_focus
        mock_multilayer.assert_called_once()
        call_kwargs = mock_multilayer.call_args[1]
        assert "strategy_focus" not in call_kwargs


class TestExtractSpecMultiStrategy:
    """Tests for multi-strategy detection path."""

    @patch("paper2spec.extractor._extract_multilayer")
    @patch("paper2spec.extractor._detect_strategies")
    def test_multi_strategy_path(self, mock_detect, mock_multilayer, paper_content):
        mock_detect.return_value = [
            StrategyBrief(name="Strategy A", brief_description="First"),
            StrategyBrief(name="Strategy B", brief_description="Second"),
        ]
        mock_multilayer.side_effect = [
            StrategySpec(strategy_name="Strategy A", strategy_type="technical"),
            StrategySpec(strategy_name="Strategy B", strategy_type="fundamental"),
        ]

        result = extract_spec(paper_content, mode="multilayer")

        assert result.num_detected == 2
        assert len(result.strategies) == 2
        assert result.strategies[0].strategy_name == "Strategy A"
        assert result.strategies[1].strategy_name == "Strategy B"
        # Called twice — once per strategy
        assert mock_multilayer.call_count == 2
        # Each call should include strategy_focus
        for call in mock_multilayer.call_args_list:
            assert "strategy_focus" in call[1]

    @patch("paper2spec.extractor._extract_multilayer")
    @patch("paper2spec.extractor._detect_strategies")
    def test_name_override_when_layer1_misses(self, mock_detect, mock_multilayer, paper_content):
        """If Layer 1 returns paper title as strategy name, override with brief name."""
        mock_detect.return_value = [
            StrategyBrief(name="Real Name A"),
            StrategyBrief(name="Real Name B"),
        ]
        # Layer 1 fails to pick up the correct name
        mock_multilayer.side_effect = [
            StrategySpec(strategy_name="Test Paper"),  # == paper_content.title
            StrategySpec(strategy_name=""),  # empty
        ]

        result = extract_spec(paper_content, mode="multilayer")

        assert result.strategies[0].strategy_name == "Real Name A"
        assert result.strategies[1].strategy_name == "Real Name B"


class TestExtractSpecSingleMode:
    """Tests for legacy single-call mode."""

    @patch("paper2spec.extractor._extract_single_call")
    def test_single_mode(self, mock_single, paper_content):
        mock_single.return_value = StrategySpec(
            strategy_name="Legacy",
            strategy_type="technical",
        )

        result = extract_spec(paper_content, mode="single")

        assert result.num_detected == 1
        assert result.strategies[0].strategy_name == "Legacy"
        mock_single.assert_called_once()


class TestCanonicalPostprocess:
    """Tests for deterministic QSA-style canonical fixes."""

    @patch("paper2spec.extractor._detect_strategies")
    @patch("paper2spec.extractor._extract_multilayer")
    def test_portfolio_weight_output_and_direct_sizing(self, mock_multilayer, mock_detect, paper_content):
        mock_detect.return_value = [StrategyBrief(name="Allocation")]
        mock_multilayer.return_value = StrategySpec(
            strategy_name="Allocation",
            strategy_type="allocation",
            logic_pipeline=[
                LogicStep(
                    step_id="step1",
                    description="Compute final portfolio allocation weights",
                    output="upsa_weights",
                    output_type="vector",
                )
            ],
            execution_plan=[
                ExecutionPlan(
                    action=ExecutionAction(signal_source="upsa_weights"),
                    position_sizing=PositionSizing(method="equal_weight"),
                )
            ],
        )

        result = extract_spec(paper_content, mode="multilayer")
        spec = result.strategies[0]

        assert spec.logic_pipeline[0].output == "portfolio_weights"
        assert spec.execution_plan[0].action.signal_source == "portfolio_weights"
        assert spec.execution_plan[0].position_sizing.method == "direct_weight"
        assert spec.execution_plan[0].position_sizing.steps[0].output == "order_weights"


class TestOperatorPitfallRetrievalInputs:
    """Tests for deterministic retrieval inputs (no FAISS dependency)."""

    def test_corpus_contains_qsa_operator_entries(self):
        entries = load_operator_pitfall_entries()
        operator_ids = {entry["operator_id"] for entry in entries}

        assert "second_moment" in operator_ids
        assert "ensemble_weight_optimization" in operator_ids
        assert "shrinkage_normalization" in operator_ids
        assert "loo_closed_form" in operator_ids

    def test_queries_include_component_paths(self):
        spec = {
            "indicators": [
                {"indicator_id": "second_moment", "formula": "M = R.T @ R / T"}
            ],
            "logic_pipeline": [
                {
                    "step_id": "step1",
                    "description": "Compute LOO ridge portfolio returns with Sherman-Morrison correction",
                    "expression": "Use alpha * lambda_i + z_l denominators",
                    "output": "loo_returns",
                }
            ],
            "execution_plan": [
                {
                    "position_sizing": {
                        "steps": [
                            {
                                "description": "Map portfolio_weights to order weights",
                                "expression": "order_weights = portfolio_weights",
                                "output": "order_weights",
                            }
                        ]
                    }
                }
            ],
        }

        paths = [path for path, _ in operator_pitfall_queries_from_spec(spec)]

        assert any(path.startswith("indicators[0]") for path in paths)
        assert any(path.startswith("logic_pipeline[0]") for path in paths)
        assert any(path.startswith("execution_plan[0].position_sizing.steps[0]") for path in paths)
