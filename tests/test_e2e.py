"""End-to-end tests: parse → extract → render.

Coverage plan:
  1. Parser (Mode A/B): mock LLM, validate PaperContent structure
  2. Extractor (Layer 0): multi-strategy detection with mock LLM
  3. Extractor (Layers 1-4): full multilayer pipeline with mock LLM
  4. Extractor (single-call legacy): backward compatibility
  5. Render: PaperContent + ExtractionResult → Markdown quality

All tests in this file are deterministic: mocked LLM, synthetic
fixtures, no network. PDF extraction tests live in test_parser/
or are exercised through the OCR path downstream.
"""

import json
import os
import textwrap
from dataclasses import dataclass
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from paper2spec.models import (
    ExtractionResult,
    Indicator,
    LogicStep,
    ExecutionPlan,
    PaperContent,
    StrategyBrief,
    StrategySpec,
)


# ── Constants ────────────────────────────────────────────────

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "examples")

# Realistic mock LLM responses for each layer
_MOCK_LAYER0_SINGLE = json.dumps({
    "num_strategies": 1,
    "strategies": [
        {
            "name": "Time-Series Momentum",
            "strategy_type": "technical",
            "brief_description": "12-1 month momentum signal",
            "differentiation": "",
            "key_section_hints": ["Section 3"],
        }
    ],
})

_MOCK_LAYER0_MULTI = json.dumps({
    "num_strategies": 3,
    "strategies": [
        {
            "name": "Distance Method Pairs Trading",
            "strategy_type": "technical",
            "brief_description": "Find pairs by minimum SSD, trade on divergence",
            "differentiation": "Uses Euclidean distance for pair selection",
            "key_section_hints": ["Section 2.1"],
        },
        {
            "name": "Cointegration Pairs Trading",
            "strategy_type": "technical",
            "brief_description": "Find pairs via Engle-Granger cointegration test",
            "differentiation": "Uses ADF test for stationarity of spread",
            "key_section_hints": ["Section 2.2"],
        },
        {
            "name": "Copula Pairs Trading",
            "strategy_type": "technical",
            "brief_description": "Uses copula functions to model joint distribution",
            "differentiation": "Non-linear dependence structure",
            "key_section_hints": ["Section 2.3"],
        },
    ],
})

_MOCK_LAYER1 = json.dumps({
    "strategy_name": "Time-Series Momentum",
    "strategy_type": "technical",
    "asset_class": ["equity"],
    "description": "Go long winners and short losers based on past 12-month return.",
    "price_data": True,
    "volume_data": False,
    "fundamental_data": [],
    "alternative_data": [],
    "lookback_period": 252,
    "data_frequency": "daily",
    "data_source": "CRSP",
    "time_period": "1963-2020",
    "universe_assets": ["NYSE", "AMEX", "NASDAQ"],
    "universe_selection_criteria": "Price > $5, Market cap > 20th NYSE pctile",
    "expected_sharpe": 0.85,
    "expected_return": 0.12,
    "max_drawdown": -0.35,
    "expected_performance": {"monthly_alpha": 0.008},
})

_MOCK_LAYER2 = json.dumps({
    "indicators": [
        {
            "indicator_id": "MOM_12_1",
            "name": "12-1 Month Momentum",
            "category": "technical",
            "formula": "(P_{t-1} / P_{t-12}) - 1",
            "latex": "r_{i,t-12:t-1}",
            "inputs": ["close_price"],
            "parameters": {"lookback": 12, "skip": 1},
            "scope": "time_series",
            "output_type": "scalar",
        },
        {
            "indicator_id": "MKT_CAP",
            "name": "Market Capitalization",
            "category": "fundamental",
            "formula": "price * shares_outstanding",
            "latex": "",
            "inputs": ["close_price", "shares_outstanding"],
            "parameters": {},
            "scope": "cross_sectional",
            "output_type": "scalar",
        },
    ]
})

_MOCK_LAYER3 = json.dumps({
    "logic_pipeline": [
        {
            "step_id": "S1",
            "description": "Compute 12-1 month momentum for each stock",
            "function": "compute",
            "scope": "time_series",
            "group_by": "",
            "inputs": ["close_price"],
            "parameters": {"lookback": 12, "skip": 1},
            "expression": "ret_12_1 = close[-1] / close[-12] - 1",
            "output": "mom_signal",
            "output_type": "scalar",
        },
        {
            "step_id": "S2",
            "description": "Sort stocks into quintiles by momentum signal",
            "function": "quantile_sort",
            "scope": "cross_sectional",
            "group_by": "",
            "inputs": ["mom_signal"],
            "parameters": {"num_groups": 5},
            "expression": "quintile = pd.qcut(mom_signal, 5, labels=False)",
            "output": "quintile_label",
            "output_type": "label",
        },
        {
            "step_id": "S3",
            "description": "Long Q5 (winners), Short Q1 (losers)",
            "function": "condition",
            "scope": "cross_sectional",
            "group_by": "",
            "inputs": ["quintile_label"],
            "parameters": {},
            "expression": "if quintile == 4: LONG; elif quintile == 0: SHORT; else: FLAT",
            "output": "trade_signal",
            "output_type": "label",
        },
    ]
})

_MOCK_LAYER4 = json.dumps({
    "execution_plan": [
        {
            "plan_id": "EP1",
            "description": "Monthly rebalance of momentum quintile portfolio",
            "trigger": {
                "trigger_type": "time_driven",
                "frequency": "monthly",
                "signal_lookup": "trade_signal",
                "delay_bars": 1,
                "price_type": "open",
            },
            "action": {
                "signal_source": "trade_signal",
                "logic": "if trade_signal == LONG: buy; elif SHORT: sell_short; else: close",
                "default_action": "hold",
            },
            "position_sizing": {
                "method": "equal_weight",
                "max_position_pct": 0.05,
                "total_exposure": 1.0,
                "long_short": "long_short",
            },
        }
    ],
    "risk_management": [
        "Stop-loss: -30% per position",
        "Sector cap: max 25% in any sector",
    ],
})


# ── Mock LLM router ─────────────────────────────────────────


def _make_layer_router(layer0_response: str = _MOCK_LAYER0_SINGLE):
    """Create an async LLM mock that returns the appropriate layer response.

    Matches prompts by unique keywords from the actual prompt templates in prompts.py.
    """

    async def router(prompt: str, *, system: str = "", model=None, **kwargs) -> str:
        p = prompt.lower()

        # Layer 0: "how many independent trading strategies"
        if "how many independent" in p or "num_strategies" in p[:800]:
            return layer0_response
        # Layer 4: "execution plan and risk management" — must check BEFORE Layer 3
        if "execution plan and risk management" in p or "position_sizing" in p[:800]:
            return _MOCK_LAYER4
        # Layer 3: "logic pipeline that transforms indicators"
        if "logic pipeline" in p[:500] and "transforms" in p[:500]:
            return _MOCK_LAYER3
        # Layer 2: "all indicators, factors, and computed signals"
        if "indicators, factors" in p[:500] or "indicator_id" in p[:800]:
            return _MOCK_LAYER2
        # Layer 1: "strategy metadata and data requirements"
        if "metadata and data" in p[:500] or "asset_class" in p[:800]:
            return _MOCK_LAYER1
        # Legacy single-call: "executable strategy specification"
        if "executable strategy specification" in p[:500] or "convert the extracted" in p[:500]:
            return _MOCK_LAYER1
        # Parser prompts (from parser.py templates)
        if "synthesize the trading strategy methodology" in p[:500]:
            return "The strategy uses 12-1 month momentum sorted into quintiles."
        if "extract precise trading rules" in p[:500]:
            return "Long top quintile (winners), short bottom quintile (losers)."
        if "extract data requirements" in p[:500]:
            return "CRSP daily data from 1963-2020, NYSE/AMEX/NASDAQ common stocks."
        # Generic fallback
        return json.dumps({"strategy_name": "Fallback", "error": "unrecognized prompt"})

    return router


# ═══════════════════════════════════════════════════════════════
# 1. PARSER E2E (Mode A + Mode B)
# ═══════════════════════════════════════════════════════════════

# (TestPDFExtraction + TestPDFExtractorErrors removed: pdf_utils.py deleted in
# the OCR-only cleanup; the OCR path is exercised by the parser tests below.)
# (Test*Search classes + paper2spec/search.py + scripts/search.py removed:
# arxiv + ssrn paper-search is not part of this fork's
# paper→replication pipeline. User provides papers directly.)


SYNTHETIC_PAPER_TEXT = textwrap.dedent("""\
    # Time-Series Momentum Across Asset Classes

    ## Abstract

    We study time-series momentum in equities, bonds, currencies, and commodities
    over the period 1985-2020. Portfolios that go long assets with positive
    12-month returns and short those with negative returns earn significant
    risk-adjusted returns across all asset classes.

    ## Data

    We use daily total return indices from Datastream covering 58 liquid
    futures contracts: 24 commodities, 12 equity indices, 9 currency pairs,
    and 13 bond futures. The sample period runs from January 1985 to
    December 2020. We compute returns as log differences of settlement prices.
    We obtain risk-free rates from the Federal Reserve H.15 release.

    ## Methodology

    For each asset i at month t, we compute the trailing 12-month
    cumulated excess return (TSMOM signal):

    TSMOM_i,t = sign(r_i,t-12:t-1)

    A positive signal indicates a long position, negative indicates short.
    The portfolio is formed at the end of each month with equal volatility
    weighting: each position is scaled to a target annualized volatility
    of 40% / sqrt(N), where N is the number of assets.

    Volatility is estimated using an exponentially-weighted moving average
    (EWMA) with a 60-day half-life:

    sigma_i,t = sqrt(EWMA(r_i^2, halflife=60))

    ## Signal Logic

    Entry signal: Go long when TSMOM_i,t > 0, go short when TSMOM_i,t < 0.
    Position size: w_i,t = (target_vol / sigma_i,t) * sign(TSMOM_i,t) / N
    Rebalancing: Monthly, at the end of each month.
    No transaction cost filter is applied.

    Stop-loss: None in the base strategy.
    Holding period: 1 month until next rebalancing.

    ## Results

    The diversified TSMOM portfolio earns 18.0% per annum with a Sharpe
    ratio of 1.03 and maximum drawdown of 22%. The strategy generates
    positive returns in 8 out of 12 crisis periods. Decomposing by asset
    class: commodities contribute 5.2%, equities 4.8%, bonds 4.5%, and
    currencies 3.5%.

    Table 1: Performance by Asset Class (monthly)
    | Class      | Return | Sharpe | MaxDD |
    |------------|--------|--------|-------|
    | Commodity  | 14.2%  | 0.82   | 28%   |
    | Equity     | 12.5%  | 0.71   | 35%   |
    | Bond       | 9.8%   | 0.65   | 18%   |
    | Currency   | 8.1%   | 0.58   | 21%   |
    | Combined   | 18.0%  | 1.03   | 22%   |
""")


# ── Shared PaperContent fixtures ────────────────────────────────────


@pytest.fixture
def momentum_paper_content():
    """A realistic PaperContent for testing the extractor."""
    return PaperContent(
        title="Time-Series Momentum Across Asset Classes",
        abstract="We study TSMOM across equities, bonds, currencies, and commodities.",
        methodology="12-1 month momentum signal, vol-scaled positions, monthly rebalance.",
        signal_logic="Long when TSMOM > 0, short when TSMOM < 0. Monthly rebalance.",
        data_description="Datastream daily futures data, 58 contracts, 1985-2020.",
        full_text=SYNTHETIC_PAPER_TEXT,
    )


@pytest.fixture
def pairs_paper_content():
    """A paper with multiple strategies (pairs trading variants)."""
    return PaperContent(
        title="Pairs Trading: Comprehensive Methods Review",
        abstract="We compare three pairs trading methods: distance, cointegration, copula.",
        methodology=(
            "Distance method: select top 20 pairs by minimum SSD over formation period. "
            "Cointegration: Engle-Granger test with 5% threshold. "
            "Copula: Gaussian copula with rolling MLE estimation."
        ),
        signal_logic=(
            "Distance: trade when spread > 2 std. Cointegration: trade when spread t-stat > 2. "
            "Copula: trade when conditional probability crosses 0.05/0.95."
        ),
        data_description="CRSP daily stock data 1963-2020, all NYSE common stocks.",
        full_text="Full text about pairs trading methods..." * 100,
    )


class TestExtractorLayer0:
    """Test strategy detection (Layer 0)."""

    @pytest.mark.asyncio
    @patch("paper2spec.extractor.achat", new_callable=AsyncMock)
    async def test_detect_single_strategy(self, mock_achat, momentum_paper_content):
        mock_achat.side_effect = _make_layer_router(_MOCK_LAYER0_SINGLE)
        from paper2spec.extractor import _detect_strategies
        briefs = await _detect_strategies(momentum_paper_content)
        assert len(briefs) == 1
        assert briefs[0].name == "Time-Series Momentum"

    @pytest.mark.asyncio
    @patch("paper2spec.extractor.achat", new_callable=AsyncMock)
    async def test_detect_multi_strategy(self, mock_achat, pairs_paper_content):
        mock_achat.side_effect = _make_layer_router(_MOCK_LAYER0_MULTI)
        from paper2spec.extractor import _detect_strategies
        briefs = await _detect_strategies(pairs_paper_content)
        assert len(briefs) == 3
        names = [b.name for b in briefs]
        assert "Distance Method Pairs Trading" in names
        assert "Cointegration Pairs Trading" in names
        assert "Copula Pairs Trading" in names

    @pytest.mark.asyncio
    @patch("paper2spec.extractor.achat", new_callable=AsyncMock)
    async def test_layer0_json_failure_fallback(self, mock_achat, momentum_paper_content):
        """If Layer 0 LLM returns garbage, fall back to single strategy."""
        mock_achat.return_value = "This is not JSON at all."
        from paper2spec.extractor import _detect_strategies
        briefs = await _detect_strategies(momentum_paper_content)
        assert len(briefs) == 1  # fallback
        assert briefs[0].name == momentum_paper_content.title


class TestExtractorMultilayer:
    """Test full 4-layer extraction pipeline."""

    @pytest.mark.asyncio
    @patch("paper2spec.extractor.achat", new_callable=AsyncMock)
    async def test_single_strategy_full_pipeline(self, mock_achat, momentum_paper_content):
        mock_achat.side_effect = _make_layer_router(_MOCK_LAYER0_SINGLE)
        from paper2spec.extractor import aextract_spec
        result = await aextract_spec(momentum_paper_content, mode="multilayer")

        assert isinstance(result, ExtractionResult)
        assert result.num_detected == 1
        assert len(result.strategies) == 1

        spec = result.strategies[0]
        assert spec.strategy_name == "Time-Series Momentum"
        assert spec.strategy_type == "technical"
        assert spec.asset_class == ["equity"]
        assert spec.data_frequency == "daily"
        assert spec.data_source == "CRSP"
        assert spec.lookback_period == 252

    @pytest.mark.asyncio
    @patch("paper2spec.extractor.achat", new_callable=AsyncMock)
    async def test_indicators_extracted(self, mock_achat, momentum_paper_content):
        mock_achat.side_effect = _make_layer_router(_MOCK_LAYER0_SINGLE)
        from paper2spec.extractor import aextract_spec
        result = await aextract_spec(momentum_paper_content, mode="multilayer")

        spec = result.strategies[0]
        assert len(spec.indicators) == 2
        ind_names = [i.name for i in spec.indicators]
        assert "12-1 Month Momentum" in ind_names
        assert "Market Capitalization" in ind_names
        # Check indicator fields
        mom = [i for i in spec.indicators if i.indicator_id == "MOM_12_1"][0]
        assert mom.category == "technical"
        assert mom.scope == "time_series"
        assert isinstance(mom.parameters, dict)
        assert mom.parameters.get("lookback") == 12

    @pytest.mark.asyncio
    @patch("paper2spec.extractor.achat", new_callable=AsyncMock)
    async def test_logic_pipeline_extracted(self, mock_achat, momentum_paper_content):
        mock_achat.side_effect = _make_layer_router(_MOCK_LAYER0_SINGLE)
        from paper2spec.extractor import aextract_spec
        result = await aextract_spec(momentum_paper_content, mode="multilayer")

        spec = result.strategies[0]
        assert len(spec.logic_pipeline) == 3
        step_ids = [s.step_id for s in spec.logic_pipeline]
        assert step_ids == ["S1", "S2", "S3"]
        # Check step details
        assert spec.logic_pipeline[0].function == "compute"
        assert spec.logic_pipeline[1].function == "quantile_sort"
        assert spec.logic_pipeline[2].function == "condition"

    @pytest.mark.asyncio
    @patch("paper2spec.extractor.achat", new_callable=AsyncMock)
    async def test_execution_plan_extracted(self, mock_achat, momentum_paper_content):
        mock_achat.side_effect = _make_layer_router(_MOCK_LAYER0_SINGLE)
        from paper2spec.extractor import aextract_spec
        result = await aextract_spec(momentum_paper_content, mode="multilayer")

        spec = result.strategies[0]
        assert len(spec.execution_plan) == 1
        plan = spec.execution_plan[0]
        assert plan.plan_id == "EP1"
        assert plan.trigger.trigger_type == "time_driven"
        assert plan.trigger.frequency == "monthly"
        assert plan.position_sizing.method == "equal_weight"
        assert plan.position_sizing.long_short == "long_short"

    @pytest.mark.asyncio
    @patch("paper2spec.extractor.achat", new_callable=AsyncMock)
    async def test_risk_management_extracted(self, mock_achat, momentum_paper_content):
        mock_achat.side_effect = _make_layer_router(_MOCK_LAYER0_SINGLE)
        from paper2spec.extractor import aextract_spec
        result = await aextract_spec(momentum_paper_content, mode="multilayer")

        spec = result.strategies[0]
        assert len(spec.risk_management) == 2
        assert any("stop-loss" in r.lower() for r in spec.risk_management)

    @pytest.mark.asyncio
    @patch("paper2spec.extractor.achat", new_callable=AsyncMock)
    async def test_performance_metrics_extracted(self, mock_achat, momentum_paper_content):
        mock_achat.side_effect = _make_layer_router(_MOCK_LAYER0_SINGLE)
        from paper2spec.extractor import aextract_spec
        result = await aextract_spec(momentum_paper_content, mode="multilayer")

        spec = result.strategies[0]
        assert spec.expected_sharpe == 0.85
        assert spec.expected_return == 0.12
        assert spec.max_drawdown == -0.35


class TestExtractorMultiStrategy:
    """Test multi-strategy extraction path."""

    @pytest.mark.asyncio
    @patch("paper2spec.extractor.achat", new_callable=AsyncMock)
    async def test_multi_strategy_extraction(self, mock_achat, pairs_paper_content):
        mock_achat.side_effect = _make_layer_router(_MOCK_LAYER0_MULTI)
        from paper2spec.extractor import aextract_spec
        result = await aextract_spec(pairs_paper_content, mode="multilayer")

        assert result.num_detected == 3
        assert len(result.strategies) == 3
        # Each strategy should be independently extracted
        for spec in result.strategies:
            assert spec.strategy_name
            assert len(spec.indicators) > 0
            assert len(spec.logic_pipeline) > 0

    @pytest.mark.asyncio
    @patch("paper2spec.extractor.achat", new_callable=AsyncMock)
    async def test_multi_strategy_names_preserved(self, mock_achat, pairs_paper_content):
        """Each strategy should retain its Layer 0 name when L1 returns paper title."""
        # Override logic triggers when L1 returns strategy_name == paper title.
        # Create a Layer 1 mock that returns the paper title to trigger override.
        l1_data = json.loads(_MOCK_LAYER1)
        l1_data["strategy_name"] = pairs_paper_content.title
        l1_with_paper_title = json.dumps(l1_data)

        base_router = _make_layer_router(_MOCK_LAYER0_MULTI)

        async def router_with_title_override(prompt, *, system="", model=None, **kwargs):
            p = prompt.lower()
            if "metadata and data" in p[:500] or "asset_class" in p[:800]:
                return l1_with_paper_title
            return await base_router(prompt, system=system, model=model, **kwargs)

        mock_achat.side_effect = router_with_title_override
        from paper2spec.extractor import aextract_spec
        result = await aextract_spec(pairs_paper_content, mode="multilayer")

        names = [s.strategy_name for s in result.strategies]
        brief_names = {"Distance Method Pairs Trading", "Cointegration Pairs Trading", "Copula Pairs Trading"}
        assert set(names) == brief_names

    @pytest.mark.asyncio
    @patch("paper2spec.extractor.achat", new_callable=AsyncMock)
    async def test_multi_strategy_llm_call_count(self, mock_achat, pairs_paper_content):
        """3 strategies × 4 layers + 1 Layer 0 = 13 LLM calls."""
        mock_achat.side_effect = _make_layer_router(_MOCK_LAYER0_MULTI)
        from paper2spec.extractor import aextract_spec
        await aextract_spec(pairs_paper_content, mode="multilayer")
        # Layer 0 (1) + 3 strategies × 4 layers (12) = 13
        # But _call_llm_json may retry on failures, so check minimum
        assert mock_achat.call_count >= 13


class TestExtractorSingleCall:
    """Test legacy single-call extraction mode."""

    @pytest.mark.asyncio
    @patch("paper2spec.extractor.achat", new_callable=AsyncMock)
    async def test_single_call_mode(self, mock_achat, momentum_paper_content):
        mock_achat.side_effect = _make_layer_router()
        from paper2spec.extractor import aextract_spec
        result = await aextract_spec(momentum_paper_content, mode="single")

        assert result.num_detected == 1
        assert len(result.strategies) == 1
        # Single-call mode should make exactly 1 LLM call
        assert mock_achat.call_count == 1


class TestExtractorJSONParsing:
    """Test JSON parsing robustness in extractor."""

    def test_parse_clean_json(self):
        from paper2spec.extractor import _parse_json_response
        result = _parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_markdown_fenced_json(self):
        from paper2spec.extractor import _parse_json_response
        text = '```json\n{"key": "value"}\n```'
        result = _parse_json_response(text)
        assert result == {"key": "value"}

    def test_parse_json_with_preamble(self):
        from paper2spec.extractor import _parse_json_response
        text = 'Here is the JSON:\n\n{"key": "value"}\n\nEnd.'
        result = _parse_json_response(text)
        assert result == {"key": "value"}

    def test_parse_non_json_raises(self):
        from paper2spec.extractor import _parse_json_response
        with pytest.raises(ValueError, match="Could not parse JSON"):
            _parse_json_response("This is plain text with no JSON.")


# ═══════════════════════════════════════════════════════════════
# 2. RENDER QUALITY TESTS
# ═══════════════════════════════════════════════════════════════


class TestRenderContentE2E:
    """Test content_to_markdown quality."""

    def test_full_render_structure(self, momentum_paper_content):
        from paper2spec.render import content_to_markdown
        md = content_to_markdown(momentum_paper_content)

        assert md.startswith("# Time-Series Momentum")
        assert "## Methodology" in md
        assert "## Data Description" in md
        assert "## Signal Logic" in md
        assert "Full text:" in md  # stats footer

    def test_abstract_as_blockquote(self, momentum_paper_content):
        from paper2spec.render import content_to_markdown
        md = content_to_markdown(momentum_paper_content)
        # Abstract should be in blockquote format
        assert "> " in md


class TestRenderSpecE2E:
    """Test spec_to_markdown quality and completeness."""

    def _make_full_result(self) -> ExtractionResult:
        """Create a fully populated ExtractionResult."""
        from paper2spec.models import ExecutionTrigger, ExecutionAction, PositionSizing
        spec = StrategySpec(
            strategy_name="TSMOM",
            strategy_type="technical",
            asset_class=["equity", "commodity"],
            description="Time-series momentum with vol scaling.",
            data_source="Datastream",
            time_period="1985-2020",
            data_frequency="daily",
            lookback_period=252,
            expected_sharpe=1.03,
            expected_return=0.18,
            max_drawdown=-0.22,
            indicators=[
                Indicator(
                    indicator_id="MOM_12_1",
                    name="12-1 Momentum",
                    category="technical",
                    formula="(P_{t-1}/P_{t-12})-1",
                    scope="time_series",
                    output_type="scalar",
                ),
            ],
            logic_pipeline=[
                LogicStep(
                    step_id="S1",
                    description="Compute momentum signal",
                    function="compute",
                    scope="time_series",
                    output="mom_signal",
                    output_type="scalar",
                ),
            ],
            execution_plan=[
                ExecutionPlan(
                    plan_id="EP1",
                    description="Monthly rebalance",
                    trigger=ExecutionTrigger(frequency="monthly"),
                    action=ExecutionAction(logic="long/short based on signal"),
                    position_sizing=PositionSizing(method="equal_weight", long_short="long_short"),
                ),
            ],
            risk_management=["Stop-loss at -30%", "Max 5% per position"],
        )
        return ExtractionResult(
            strategies=[spec],
            paper_title="Time-Series Momentum Paper",
            num_detected=1,
        )

    def test_spec_markdown_has_all_sections(self):
        from paper2spec.render import spec_to_markdown
        result = self._make_full_result()
        md = spec_to_markdown(result)

        assert "# Time-Series Momentum Paper" in md
        assert "### Data Requirements" in md
        assert "### Expected Performance" in md
        assert "### Indicators" in md
        assert "### Logic Pipeline" in md
        assert "### Execution" in md
        assert "### Risk Management" in md

    def test_indicator_table_format(self):
        from paper2spec.render import spec_to_markdown
        md = spec_to_markdown(self._make_full_result())
        assert "| ID |" in md  # table header
        assert "MOM_12_1" in md
        assert "12-1 Momentum" in md

    def test_multi_strategy_render(self):
        from paper2spec.render import spec_to_markdown
        result = self._make_full_result()
        result.strategies.append(StrategySpec(strategy_name="Vol Timing"))
        result.num_detected = 2
        md = spec_to_markdown(result)
        assert "2 independent strategies" in md
        assert "Strategy 1:" in md
        assert "Strategy 2:" in md

# (TestLibraryQuality + TestLibraryCrossExampleQuality removed: gated on
# `examples/pairs_trading_*.json` / `tactical_aa_*.json` /
# `value_momentum_*.json` which don't exist in this fork. Only
# `examples/upsa/` is shipped; the upstream example names were never
# replicated here.)
