"""Data models for paper2spec pipeline.

PaperContent: Structured sections extracted from a PDF.
StrategySpec: Executable strategy specification derived from PaperContent.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import json


# ── PaperContent ──────────────────────────────────────────────


@dataclass
class PaperContent:
    """Structured representation of an academic paper's key sections."""

    title: str = ""
    abstract: str = ""
    methodology: str = ""
    data_description: str = ""
    signal_logic: str = ""
    results: Dict[str, Any] = field(default_factory=dict)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    formulas: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    full_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "PaperContent":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json(cls, s: str) -> "PaperContent":
        return cls.from_dict(json.loads(s))


@dataclass
class ExtractionResult:
    """Wrapper for multi-strategy extraction output."""

    strategies: List["StrategySpec"] = field(default_factory=list)
    paper_title: str = ""
    num_detected: int = 0  # How many strategies Layer 0 detected

    def to_dict(self) -> dict:
        return {
            "paper_title": self.paper_title,
            "num_detected": self.num_detected,
            "strategies": [s.to_dict() for s in self.strategies],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "ExtractionResult":
        from paper2spec.models import StrategySpec  # avoid circular at module level
        return cls(
            paper_title=d.get("paper_title", ""),
            num_detected=d.get("num_detected", 0),
            strategies=[StrategySpec.from_dict(s) for s in d.get("strategies", [])],
        )


# ── Strategy Detection (Layer 0) ──────────────────────────────


@dataclass
class StrategyBrief:
    """Lightweight summary of one strategy variant detected in a paper.

    Used by Layer 0 to enumerate independent strategies before
    running the full 4-layer extraction on each.
    """

    name: str = ""
    strategy_type: str = "technical"  # technical | fundamental | hybrid | multi_asset
    brief_description: str = ""  # 1-3 sentences
    differentiation: str = ""  # How this strategy differs from others in the paper
    key_section_hints: List[str] = field(default_factory=list)  # Section names / table refs


# ── StrategySpec sub‑components ───────────────────────────────


@dataclass
class Indicator:
    """Indicator / signal definition."""

    indicator_id: str = ""
    name: str = ""
    category: str = ""  # technical | fundamental | derived
    formula: str = ""
    latex: str = ""
    inputs: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    scope: str = "time_series"  # time_series | cross_sectional
    output_type: str = "scalar"  # scalar | boolean | ranking | vector | matrix | series
    data_semantics: Optional[str] = None  # price_series | return_series | None
    executable_explanation: Optional[str] = None


@dataclass
class LogicStep:
    """One step in the signal‑generation logic pipeline."""

    step_id: str = ""
    description: str = ""
    function: str = ""  # filter | rank | quantile_sort | condition | threshold | crossover | …
    scope: str = "cross_sectional"  # time_series | cross_sectional | within_group
    group_by: str = ""
    inputs: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    expression: str = ""
    output: str = ""
    output_type: str = "label"  # label | boolean | scalar | ranking | vector | matrix | series
    executable_explanation: Optional[str] = None


@dataclass
class SizingStep:
    """One codegen-facing step that maps signals/weights to order weights."""

    step_id: str = ""
    description: str = ""
    scope: Optional[str] = None
    group_by: Optional[str] = None
    inputs: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    expression: str = ""
    output: str = "order_weights"
    output_type: str = "vector"
    executable_explanation: Optional[str] = None


@dataclass
class ExecutionTrigger:
    """When to execute trades."""

    trigger_type: str = "time_driven"  # time_driven | signal_driven
    frequency: str = "monthly"
    signal_lookup: str = ""
    delay_bars: int = 1
    price_type: Optional[str] = "open"


@dataclass
class PositionSizing:
    """How to size positions."""

    method: str = "equal_weight"  # equal_weight | quantile_based | signal_based | volatility_scaled | direct_weight
    max_position_pct: Optional[float] = None
    total_exposure: Optional[float] = None
    long_short: str = "long_only"  # long_only | short_only | long_short
    steps: List[SizingStep] = field(default_factory=list)
    executable_explanation: Optional[str] = None


@dataclass
class ExecutionAction:
    """Trading action expressed as pseudo‑code."""

    signal_source: str = ""
    logic: str = ""
    default_action: str = "hold"


@dataclass
class ExecutionPlan:
    """Execution plan = trigger + action + sizing."""

    plan_id: str = ""
    description: str = ""
    trigger: ExecutionTrigger = field(default_factory=ExecutionTrigger)
    action: ExecutionAction = field(default_factory=ExecutionAction)
    position_sizing: PositionSizing = field(default_factory=PositionSizing)
    executable_explanation: Optional[str] = None


# ── StrategySpec ──────────────────────────────────────────────


@dataclass
class StrategySpec:
    """Full strategy specification — LLM‑friendly flat structure."""

    # ── Layer 1a: Metadata ──
    strategy_name: str = ""
    strategy_type: str = "technical"
    asset_class: List[str] = field(default_factory=list)
    description: str = ""

    plan_id: Optional[str] = None
    strategy_id: Optional[str] = None
    backtest_id: Optional[str] = None

    # ── Layer 1b: Data Requirements ──
    price_data: bool = True
    volume_data: bool = False
    fundamental_data: List[str] = field(default_factory=list)
    alternative_data: List[str] = field(default_factory=list)
    lookback_period: Optional[int] = None
    data_frequency: str = "daily"
    data_source: str = ""
    time_period: str = ""
    universe_assets: List[str] = field(default_factory=list)
    universe_selection_criteria: str = ""

    # ── Layer 1c: Expected Performance ──
    expected_sharpe: Optional[float] = None
    expected_return: Optional[float] = None
    max_drawdown: Optional[float] = None
    expected_performance: Dict[str, Any] = field(default_factory=dict)

    # ── Layer 2a: Indicators ──
    indicators: List[Indicator] = field(default_factory=list)

    # ── Layer 2b: Logic Pipeline ──
    logic_pipeline: List[LogicStep] = field(default_factory=list)

    # ── Layer 3: Execution ──
    execution_plan: List[ExecutionPlan] = field(default_factory=list)
    risk_management: List[str] = field(default_factory=list)
    executable_explanation: Optional[str] = None
    risk_management_executable_explanation: Optional[str] = None
    needs_human_review: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "StrategySpec":
        """Reconstruct from dict, handling nested dataclasses."""
        kw: dict = {}
        for fname, fdef in cls.__dataclass_fields__.items():
            if fname not in d:
                continue
            val = d[fname]
            if fname == "indicators" and isinstance(val, list):
                kw[fname] = [Indicator(**{k: x for k, x in v.items() if k in Indicator.__dataclass_fields__}) if isinstance(v, dict) else v for v in val]
            elif fname == "logic_pipeline" and isinstance(val, list):
                kw[fname] = [LogicStep(**{k: x for k, x in v.items() if k in LogicStep.__dataclass_fields__}) if isinstance(v, dict) else v for v in val]
            elif fname == "execution_plan" and isinstance(val, list):
                plans = []
                for v in val:
                    if isinstance(v, dict):
                        v = dict(v)
                        if "trigger" in v and isinstance(v["trigger"], dict):
                            v["trigger"] = ExecutionTrigger(**{k: x for k, x in v["trigger"].items() if k in ExecutionTrigger.__dataclass_fields__})
                        if "action" in v and isinstance(v["action"], dict):
                            v["action"] = ExecutionAction(**{k: x for k, x in v["action"].items() if k in ExecutionAction.__dataclass_fields__})
                        if "position_sizing" in v and isinstance(v["position_sizing"], dict):
                            sizing = dict(v["position_sizing"])
                            if "steps" in sizing and isinstance(sizing["steps"], list):
                                sizing["steps"] = [
                                    SizingStep(**{k: x for k, x in step.items() if k in SizingStep.__dataclass_fields__})
                                    if isinstance(step, dict) else step
                                    for step in sizing["steps"]
                                ]
                            v["position_sizing"] = PositionSizing(**{k: x for k, x in sizing.items() if k in PositionSizing.__dataclass_fields__})
                        plans.append(ExecutionPlan(**{k: x for k, x in v.items() if k in ExecutionPlan.__dataclass_fields__}))
                    else:
                        plans.append(v)
                kw[fname] = plans
            else:
                kw[fname] = val
        return cls(**kw)

    @classmethod
    def from_json(cls, s: str) -> "StrategySpec":
        return cls.from_dict(json.loads(s))
