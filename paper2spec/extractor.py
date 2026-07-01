"""Specification extractor — PaperContent → List[StrategySpec].

9-layer extraction architecture:
  Layer 0: Strategy Detection (how many independent strategies?)
  Layer 1: Metadata (name, type, asset class, description)
  Layer 2: Table scan (list ALL results tables with claimed values)
  Layer 3: Target selection (pick TOP 3 that define successful replication)
  Layer 4: Data (database, sample period, frequency)
  Layer 5: Universe (structured share codes, exchanges, price filter)
  Layer 6: Signal (indicators + formulas)
  Layer 7: Portfolio (logic pipeline — sorting, binning, portfolio formation)
  Layer 8: Execution (rebalancing, timing — informed by targets + logic)

Each layer is a focused LLM call with a targeted prompt, producing
higher-quality structured output than a single monolithic call would.

Multi-strategy support:
  When a paper contains N>1 independent strategies, Layer 0 detects them
  and Layers 1-8 run once per strategy with focused context injection.
"""

import asyncio
import json
import logging
import re
from typing import List, Optional

from paper2spec.llm import achat, chat
from paper2spec.models import (
    ExtractionResult,
    ExecutionAction,
    ExecutionPlan,
    ExecutionTrigger,
    Indicator,
    LogicStep,
    Methodology,
    PaperContent,
    PositionSizing,
    ReplicationTarget,
    SizingStep,
    StrategyBrief,
    StrategySpec,
)
from paper2spec.prompts import (
    LAYER0_STRATEGY_DETECTION_PROMPT,
    L1_METADATA_PROMPT,
    L2_TABLE_SCAN_PROMPT,
    L3_TARGET_SELECTION_PROMPT,
    L4_DATA_PROMPT,
    L5_UNIVERSE_PROMPT,
    L6_SIGNAL_PROMPT,
    L7_PORTFOLIO_PROMPT,
    L8_EXECUTION_PROMPT,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2  # Retry once on JSON parse failure


# ── Public API ───────────────────────────────────────────────


def extract_spec(
    paper_content: "str | PaperContent",
    *,
    model: Optional[str] = None,
    instruction_context: str = "",
) -> ExtractionResult:
    """Synchronous: content.md string or PaperContent -> ExtractionResult.

    Args:
        paper_content: Full markdown string (content.md) or PaperContent.
        model: Override LLM model string.
    """
    return asyncio.run(aextract_spec(paper_content, model=model, instruction_context=instruction_context))


async def aextract_spec(
    paper_content: "str | PaperContent",
    *,
    model: Optional[str] = None,
    instruction_context: str = "",
) -> ExtractionResult:
    """Async: content.md string or PaperContent -> ExtractionResult."""
    # Accept both str (new content.md) and PaperContent (backward compat)
    if isinstance(paper_content, str):
        pc = PaperContent(full_text=paper_content)
        pc.title = _extract_title_from_md(paper_content)
        pc.abstract = _extract_abstract_from_md(paper_content)
    else:
        pc = paper_content

    # Layer 0: Detect strategies
    briefs = await _detect_strategies(pc, model=model)

    if len(briefs) <= 1:
        # Single strategy — run standard 4-layer extraction (no context injection)
        spec = await _extract_multilayer(pc, model=model, instruction_context=instruction_context)
        _postprocess_spec(spec)
        return ExtractionResult(
            strategies=[spec],
            paper_title=pc.title,
            num_detected=1,
        )

    # Multi-strategy — run 4-layer extraction per strategy in parallel
    logger.info("Multi-strategy paper: %d strategies detected", len(briefs))

    async def _extract_one(i: int, brief: StrategyBrief) -> StrategySpec:
        logger.info("━━━ Strategy %d/%d: %s ━━━", i + 1, len(briefs), brief.name)
        strategy_focus = _build_strategy_focus(brief)
        spec = await _extract_multilayer(
            pc, model=model, strategy_focus=strategy_focus, instruction_context=instruction_context
        )
        if not spec.strategy_name or spec.strategy_name == pc.title:
            spec.strategy_name = brief.name
        _postprocess_spec(spec)
        return spec

    specs = list(await asyncio.gather(
        *(_extract_one(i, brief) for i, brief in enumerate(briefs))
    ))

    return ExtractionResult(
        strategies=specs,
        paper_title=pc.title,
        num_detected=len(briefs),
    )


# ── Layer 0: Strategy Detection ──────────────────────────────


async def _detect_strategies(
    pc: PaperContent, *, model: Optional[str] = None
) -> List[StrategyBrief]:
    """Detect how many independent strategies a paper contains."""
    logger.info("Layer 0: Detecting strategies...")
    prompt = LAYER0_STRATEGY_DETECTION_PROMPT.format(
        title=pc.title,
        content=pc.full_text,
    )
    result = await _call_llm_json(prompt, model=model)
    if not result:
        logger.warning("Layer 0 failed — falling back to single strategy")
        return [StrategyBrief(name=pc.title)]

    num = result.get("num_strategies", 1)
    raw_strategies = result.get("strategies", [])

    briefs = []
    for s in raw_strategies:
        if isinstance(s, dict):
            briefs.append(StrategyBrief(
                name=s.get("name", ""),
                strategy_type=s.get("strategy_type", "technical"),
                brief_description=s.get("brief_description", ""),
                differentiation=s.get("differentiation", ""),
                key_section_hints=s.get("key_section_hints", []),
            ))

    if not briefs:
        logger.warning("Layer 0 returned empty strategies list — falling back to single")
        return [StrategyBrief(name=pc.title)]

    logger.info("  → %d strategies detected: %s", len(briefs), [b.name for b in briefs])
    return briefs


def _build_strategy_focus(brief: StrategyBrief) -> str:
    """Build the strategy_focus block injected into Layer 1-4 prompts."""
    lines = [
        f"\n>>> FOCUS ON THIS SPECIFIC STRATEGY <<<",
        f"Strategy Name: {brief.name}",
        f"Type: {brief.strategy_type}",
        f"Description: {brief.brief_description}",
    ]
    if brief.differentiation:
        lines.append(f"Differentiation: {brief.differentiation}")
    if brief.key_section_hints:
        lines.append(f"Relevant sections: {', '.join(brief.key_section_hints)}")
    lines.append(
        "Extract ONLY the indicators, logic, and execution details for THIS strategy. "
        "Ignore other strategies described in the paper."
    )
    return "\n".join(lines)


def _infer_output_type(output_name, declared: str = "label") -> str:
    """Infer canonical dimensionality from output variable names."""
    # Defensive: LLM may return a list, dict, or other type
    if isinstance(output_name, list):
        name = str(output_name[0] if output_name else "").lower()
    elif isinstance(output_name, dict):
        name = str(output_name.get("name", "") or output_name.get("output", "")).lower()
    else:
        name = (str(output_name or "")).lower()
    if name == "portfolio_weights" or name.endswith("_weights"):
        return "vector"
    if any(token in name for token in ("matrix", "covariance", "second_moment", "moment_matrix")):
        return "matrix"
    if name in {"strategy_ret", "strategy_return", "portfolio_return", "portfolio_returns", "realized_return", "oos_return", "sdf_return"}:
        return "series"
    return declared or "label"


def _canonicalize_portfolio_weight_outputs(spec: StrategySpec) -> None:
    """Rename final implementation-specific weight vectors to portfolio_weights."""
    if any(step.output == "portfolio_weights" for step in spec.logic_pipeline):
        return
    excluded = {"ensemble_weights", "ridge_weights", "ridge_portfolio_weights"}
    candidate_idx = None
    for idx, step in enumerate(spec.logic_pipeline):
        output = (step.output or "").strip()
        output_lower = output.lower()
        text = " ".join([step.description or "", step.expression or "", step.executable_explanation or ""]).lower()
        if step.output_type == "vector" and output_lower.endswith("_weights") and output_lower not in excluded and "portfolio" in text:
            candidate_idx = idx
    if candidate_idx is None:
        return
    old_output = spec.logic_pipeline[candidate_idx].output
    if not old_output:
        return
    spec.logic_pipeline[candidate_idx].output = "portfolio_weights"
    for step in spec.logic_pipeline[candidate_idx + 1:]:
        step.inputs = ["portfolio_weights" if item == old_output else item for item in step.inputs]


def _postprocess_spec(spec: StrategySpec) -> None:
    """Apply deterministic canonical fixes after LLM extraction."""
    for ind in spec.indicators:
        ind.output_type = _infer_output_type(ind.indicator_id or ind.name, ind.output_type)
    for step in spec.logic_pipeline:
        step.output_type = _infer_output_type(step.output, step.output_type)
    _canonicalize_portfolio_weight_outputs(spec)

    pipeline_outputs = [step.output for step in spec.logic_pipeline if step.output]
    if not pipeline_outputs:
        return
    final_signal = pipeline_outputs[-1]
    return_like = {"strategy_ret", "strategy_return", "portfolio_return", "portfolio_returns", "realized_return", "oos_return", "sdf_return"}
    tradable_signal = "portfolio_weights" if final_signal in return_like and "portfolio_weights" in pipeline_outputs else final_signal
    if "portfolio_weights" in pipeline_outputs:
        tradable_signal = "portfolio_weights"

    for plan in spec.execution_plan:
        if tradable_signal:
            plan.action.signal_source = tradable_signal
        if tradable_signal == "portfolio_weights":
            plan.action.logic = plan.action.logic or "SET order_target_percent(asset, weight) using portfolio_weights; positive = long exposure, negative = short exposure"
            plan.position_sizing.method = "direct_weight" if plan.position_sizing.method in {"", "equal_weight", "signal_based"} else plan.position_sizing.method
            plan.position_sizing.long_short = plan.position_sizing.long_short or "long_short"
            if not plan.position_sizing.steps:
                plan.position_sizing.steps = [SizingStep(
                    step_id="sizing_step1",
                    description="Map final portfolio weights to order target percentages.",
                    scope="cross_sectional",
                    inputs=["portfolio_weights"],
                    expression="order_weights[t, asset] = portfolio_weights[t, asset]",
                    output="order_weights",
                    output_type="vector",
                    executable_explanation="portfolio_weights are target-exposure fractions; submit them with order_target_percent, not as shares/contracts.",
                )]


# ── Multi-layer extraction (recommended) ─────────────────────


async def _extract_multilayer(
    pc: PaperContent,
    *,
    model: Optional[str] = None,
    strategy_focus: str = "",
    instruction_context: str = "",
) -> StrategySpec:
    """9-layer extraction pipeline (L1-L8, L0 runs separately).

    L1: Metadata (name, type, asset class, description)
    L2: Table scan (list ALL results tables with claimed values)
    L3: Target selection (pick TOP 3 that define successful replication)
    L4: Data (database, sample period, frequency)
    L5: Universe (structured share codes, exchanges, price filter)
    L6: Signal (indicators + formulas)
    L7: Portfolio (logic pipeline — sorting, binning, portfolio formation)
    L8: Execution (rebalancing, timing — informed by targets + logic)
    """
    spec = StrategySpec()

    # ── L1: Metadata (thin — 4 fields) ──
    logger.info("L1: Extracting metadata...")
    l1 = await _call_llm_json(
        L1_METADATA_PROMPT.format(
            title=pc.title,
            content=pc.full_text,
            strategy_focus=strategy_focus,
            instruction_context=instruction_context,
        ),
        model=model,
    )
    if l1:
        spec.strategy_name = l1.get("strategy_name", pc.title)
        spec.strategy_type = l1.get("strategy_type", "technical")
        spec.asset_class = l1.get("asset_class", ["equity"])
        spec.description = l1.get("description", "")
        logger.info("  -> %s (%s)", spec.strategy_name, spec.strategy_type)

    # ── L2: Table scan (comprehensive — all results tables) ──
    logger.info("L2: Scanning results tables...")
    l2 = await _call_llm_json(
        L2_TABLE_SCAN_PROMPT.format(
            title=pc.title,
            content=pc.full_text,
            strategy_focus=strategy_focus,
        ),
        model=model,
    )
    candidates_json = []
    if l2:
        candidates_json = l2.get("candidates", []) if isinstance(l2, dict) else (l2 if isinstance(l2, list) else [])
        logger.info("  -> %d candidate tables", len(candidates_json))

    # ── L3: Target selection (top 3 from L2 candidates) ──
    logger.info("L3: Selecting replication targets...")
    candidates_str = json.dumps(candidates_json, indent=2, ensure_ascii=False) if candidates_json else "[]"
    l3 = await _call_llm_json(
        L3_TARGET_SELECTION_PROMPT.format(
            title=pc.title,
            strategy_name=spec.strategy_name,
            candidates=candidates_str,
        ),
        model=model,
    )
    if l3:
        raw_targets = l3.get("replication_targets", []) if isinstance(l3, dict) else (l3 if isinstance(l3, list) else [])
        spec.replication_targets = [
            ReplicationTarget(**{k: v for k, v in t.items() if k in ReplicationTarget.__dataclass_fields__})
            for t in raw_targets
            if isinstance(t, dict)
        ]
        logger.info("  -> %d replication targets", len(spec.replication_targets))

    # ── L4: Data (database, sample, frequency) ──
    logger.info("L4: Extracting data requirements...")
    l4 = await _call_llm_json(
        L4_DATA_PROMPT.format(
            strategy_name=spec.strategy_name,
            strategy_type=spec.strategy_type,
            content=pc.full_text,
            strategy_focus=strategy_focus,
        ),
        model=model,
    )
    if l4:
        spec.data_source = l4.get("data_source", "")
        spec.data_frequency = l4.get("data_frequency", "daily")
        spec.price_data = l4.get("price_data", True)
        spec.volume_data = l4.get("volume_data", False)
        spec.fundamental_data = l4.get("fundamental_data", [])
        spec.alternative_data = l4.get("alternative_data", [])
        spec.lookback_period = l4.get("lookback_period")
        spec.universe_assets = l4.get("universe_assets", [])
        sample_start = l4.get("sample_start", "")
        sample_end = l4.get("sample_end", "")
        if sample_start or sample_end:
            spec.time_period = f"{sample_start} to {sample_end}"
        logger.info("  -> %s, %s", spec.data_source, spec.time_period or "(no period)")

    # ── L5: Universe (structured filter) ──
    logger.info("L5: Extracting universe filter...")
    l5 = await _call_llm_json(
        L5_UNIVERSE_PROMPT.format(
            strategy_name=spec.strategy_name,
            data_source=spec.data_source,
            content=pc.full_text,
        ),
        model=model,
    )
    if l5:
        spec.methodology = Methodology(
            share_codes=l5.get("share_codes", []),
            exchanges=l5.get("exchanges", []),
            price_filter=l5.get("price_filter"),
            delisting_adjustment=l5.get("delisting_adjustment"),
            breakpoint_universe=l5.get("breakpoint_universe", ""),
            sample_start=sample_start if l4 else "",
            sample_end=sample_end if l4 else "",
            data_frequency=spec.data_frequency,
            rebalancing_frequency=l5.get("rebalancing_frequency", ""),
        )
        # Also fill legacy free-text field for backward compat
        parts = []
        if spec.methodology.share_codes:
            parts.append(f"shrcd in {spec.methodology.share_codes}")
        if spec.methodology.exchanges:
            parts.append(f"exchcd in {spec.methodology.exchanges}")
        if spec.methodology.price_filter:
            parts.append(f"price >= ${spec.methodology.price_filter}")
        spec.universe_selection_criteria = ", ".join(parts)
        logger.info("  -> shrcd=%s, exchcd=%s, price_filter=%s",
                     spec.methodology.share_codes, spec.methodology.exchanges,
                     spec.methodology.price_filter)

    # ── L6: Signal (indicators + formulas) ──
    logger.info("L6: Extracting indicators...")
    l6 = await _call_llm_json(
        L6_SIGNAL_PROMPT.format(
            strategy_name=spec.strategy_name,
            strategy_type=spec.strategy_type,
            description=spec.description,
            content=pc.full_text,
            strategy_focus=strategy_focus,
            instruction_context=instruction_context,
        ),
        model=model,
    )
    if l6:
        raw_indicators = l6.get("indicators", []) if isinstance(l6, dict) else (l6 if isinstance(l6, list) else [])
        spec.indicators = [
            Indicator(**{k: v for k, v in ind.items() if k in Indicator.__dataclass_fields__})
            for ind in raw_indicators
            if isinstance(ind, dict)
        ]
        logger.info("  -> %d indicators", len(spec.indicators))

    # ── L7: Portfolio (logic pipeline) ──
    logger.info("L7: Extracting logic pipeline...")
    indicators_summary = "\n".join(
        f"  - {ind.indicator_id}: {ind.name} ({ind.category}, {ind.scope}, output={ind.output_type})"
        for ind in spec.indicators
    ) or "  (no indicators extracted)"
    l7 = await _call_llm_json(
        L7_PORTFOLIO_PROMPT.format(
            strategy_name=spec.strategy_name,
            strategy_type=spec.strategy_type,
            indicators_summary=indicators_summary,
            content=pc.full_text,
            strategy_focus=strategy_focus,
            instruction_context=instruction_context,
        ),
        model=model,
    )
    if l7:
        raw_steps = l7.get("logic_pipeline", []) if isinstance(l7, dict) else (l7 if isinstance(l7, list) else [])
        spec.logic_pipeline = [
            LogicStep(**{k: v for k, v in step.items() if k in LogicStep.__dataclass_fields__})
            for step in raw_steps
            if isinstance(step, dict)
        ]
        for step in spec.logic_pipeline:
            step.output_type = _infer_output_type(step.output, step.output_type)
        _canonicalize_portfolio_weight_outputs(spec)
        logger.info("  -> %d logic steps", len(spec.logic_pipeline))

    # ── L8: Execution (informed by targets + logic) ──
    logger.info("L8: Extracting execution plan...")
    logic_summary = "\n".join(
        f"  - {step.step_id}: {step.description} -> output={step.output} ({step.output_type})"
        for step in spec.logic_pipeline
    ) or "  (no logic pipeline extracted)"
    targets_summary = "\n".join(
        f"  - [{t.id}] {t.description} (paper: {t.paper_value}, tolerance: {t.tolerance})"
        for t in spec.replication_targets
    ) or "  (no replication targets)"
    l8 = await _call_llm_json(
        L8_EXECUTION_PROMPT.format(
            strategy_name=spec.strategy_name,
            strategy_type=spec.strategy_type,
            logic_summary=logic_summary,
            targets_summary=targets_summary,
            content=pc.full_text,
            strategy_focus=strategy_focus,
            instruction_context=instruction_context,
        ),
        model=model,
    )
    if l8:
        raw_plans = l8.get("execution_plan", []) if isinstance(l8, dict) else (l8 if isinstance(l8, list) else [])
        spec.execution_plan = [_parse_execution_plan(p) for p in raw_plans if isinstance(p, dict)]
        spec.risk_management = l8.get("risk_management", [])
        spec.executable_explanation = l8.get("executable_explanation")
        spec.risk_management_executable_explanation = l8.get("risk_management_executable_explanation")
        spec.needs_human_review = l8.get("needs_human_review", spec.needs_human_review)
        logger.info("  -> %d execution plans, %d risk rules", len(spec.execution_plan), len(spec.risk_management))

    logger.info(
        "Extraction complete: %s — %d targets, %d indicators, %d logic steps, %d exec plans",
        spec.strategy_name,
        len(spec.replication_targets),
        len(spec.indicators),
        len(spec.logic_pipeline),
        len(spec.execution_plan),
    )
    return spec


# ── LLM call with retry + JSON extraction ────────────────────


async def _call_llm_json(
    prompt: str, *, model: Optional[str] = None
) -> Optional[dict]:
    """Call LLM and parse JSON response, with retry on parse failure."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            raw = await achat(prompt, system=SYSTEM_PROMPT, model=model, max_tokens=8192)
            return _parse_json_response(raw)
        except (ValueError, json.JSONDecodeError) as e:
            if attempt < MAX_RETRIES:
                logger.warning("JSON parse failed (attempt %d/%d): %s", attempt + 1, MAX_RETRIES + 1, e)
                await asyncio.sleep(1)
            else:
                logger.error("JSON parse failed after %d attempts: %s", MAX_RETRIES + 1, e)
                return None
    return None


# ── Execution plan parsing helper ─────────────────────────────


def _parse_execution_plan(d: dict) -> ExecutionPlan:
    """Parse a raw dict into an ExecutionPlan with nested dataclasses."""
    trigger_d = d.get("trigger", {})
    action_d = d.get("action", {})
    sizing_d = d.get("position_sizing", {})
    sizing_steps = []
    for step in sizing_d.get("steps", []) or []:
        if isinstance(step, dict):
            sizing_steps.append(SizingStep(**{k: v for k, v in step.items() if k in SizingStep.__dataclass_fields__}))

    return ExecutionPlan(
        plan_id=d.get("plan_id", ""),
        description=d.get("description", ""),
        trigger=ExecutionTrigger(
            trigger_type=trigger_d.get("trigger_type", "time_driven"),
            frequency=trigger_d.get("frequency", "monthly"),
            signal_lookup=trigger_d.get("signal_lookup", ""),
            delay_bars=trigger_d.get("delay_bars", 1),
            price_type=trigger_d.get("price_type", "open"),
        ),
        action=ExecutionAction(
            signal_source=action_d.get("signal_source", ""),
            logic=action_d.get("logic", ""),
            default_action=action_d.get("default_action", "hold"),
        ),
        position_sizing=PositionSizing(
            method=sizing_d.get("method", "equal_weight"),
            max_position_pct=sizing_d.get("max_position_pct"),
            total_exposure=sizing_d.get("total_exposure"),
            long_short=sizing_d.get("long_short", "long_only"),
            steps=sizing_steps,
            executable_explanation=sizing_d.get("executable_explanation"),
        ),
        executable_explanation=d.get("executable_explanation"),
    )


# ── JSON parsing ──────────────────────────────────────────────


def _parse_json_response(text: str) -> dict:
    """Extract and parse JSON from LLM output, handling markdown fences."""
    text = text.strip()

    # Try direct parse
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Try extracting from markdown code fence
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Last resort: find outermost { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response:\n{text[:500]}")


# ── Heuristic helpers (shared with parser) ───────────────────


def _extract_title_from_md(md: str) -> str:
    """Heuristic: first H1 heading in the markdown."""
    import os, re
    m = re.search(r"^#\s+(.+?)$", md[:500], re.MULTILINE)
    if m:
        return m.group(1).strip()
    return "Untitled Paper"


def _extract_abstract_from_md(md: str) -> str:
    """Heuristic: section between '# Abstract' and next heading."""
    import re
    m = re.search(
        r"(?:^|\n)#{1,3}\s*Abstract\s*\n+(.*?)(?:\n#{1,3}\s+|\n\n[A-Z])",
        md[:5000],
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1).strip()
    return ""
