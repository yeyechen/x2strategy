"""Prompt templates for structured extraction.

The multi-layer extraction prompts (LAYER_*) are used by the extractor
to produce a full StrategySpec through 5 focused LLM calls.  Each prompt
injects the full paper markdown as ``{content}``.
"""

SYSTEM_PROMPT = (
    "You are an expert quantitative researcher and algorithmic trader. "
    "Extract precise, structured information from academic finance papers. "
    "Be rigorous — prefer exact values from the paper over guessed defaults."
)

# ═══════════════════════════════════════════════════════════════
# Layer 0: Strategy Detection (multi-strategy pre-scan)
# ═══════════════════════════════════════════════════════════════

LAYER0_STRATEGY_DETECTION_PROMPT = """Analyze this research paper and determine how many INDEPENDENT trading strategies it proposes.

PAPER TITLE: {title}

FULL PAPER CONTENT (markdown format, may contain HTML tables and LaTeX equations):
{content}

INSTRUCTIONS:
A paper may contain multiple independent strategies. Count them carefully:

**Multiple strategies** exist when the paper:
- Proposes distinct strategy approaches that use different indicators or logic (e.g., "Value" vs "Momentum")
- Tests multiple selection methods that are independently implementable (e.g., distance method, cointegration method, stationarity-based method)
- Covers multiple asset classes with fundamentally different signal generation logic

**Single strategy** when:
- The paper has one core idea, even if it tests parameter robustness (different lookback windows)
- Multiple tables just show sub-period or regional breakdown of the SAME strategy
- The paper mixes long-only and long-short versions of the same signal — that's one strategy with two execution plans, not two strategies

Return JSON:
{{
    "num_strategies": <integer>,
    "strategies": [
        {{
            "name": "Short descriptive name",
            "strategy_type": "technical|fundamental|hybrid|multi_asset",
            "brief_description": "1-3 sentences describing the core idea",
            "differentiation": "How this strategy differs from others in the paper (empty if only 1)",
            "key_section_hints": ["Section names, table refs, or formulas relevant to this strategy"]
        }}
    ]
}}

CRITICAL RULES:
1. Be conservative — when in doubt, treat it as ONE strategy. False splits are worse than missing a split.
2. Parameter variations (e.g., 3-month vs 12-month momentum) are NOT separate strategies.
3. Each strategy must be independently implementable with different signal logic.
4. Order strategies by importance/prominence in the paper (main strategy first).

Output ONLY valid JSON."""

# ═══════════════════════════════════════════════════════════════
# Stage 2: Multi-layer specification extraction prompts
# (4 focused LLM calls instead of 1 monolithic call)
# ═══════════════════════════════════════════════════════════════

LAYER1_METADATA_AND_DATA_PROMPT = """Extract strategy metadata and data requirements from this research paper.

PAPER TITLE: {title}
{strategy_focus}
INSTRUCTION / CLARIFICATION CONTEXT (authoritative fallback when paper is incomplete):
{instruction_context}

The paper content below is in markdown format with HTML tables and LaTeX equations.
Focus on the methodology, data description, and results sections.

FULL PAPER CONTENT:
{content}
Extract as JSON:
{{
    "strategy_name": "Concise descriptive name based on paper content",
    "strategy_type": "technical|fundamental|hybrid|multi_asset",
    "asset_class": ["equity", "bonds", "commodities", "crypto", "forex"],
    "description": "2-4 sentence summary of the core trading idea",
    "price_data": true,
    "volume_data": false,
    "fundamental_data": ["P/E", "ROE", "Book-to-Market"],
    "alternative_data": ["FRED-MD macro factors", "sentiment"],
    "lookback_period": null,
    "data_frequency": "daily|weekly|monthly",
    "data_source": "e.g., CRSP, Yahoo Finance",
    "time_period": "e.g., 1963-2019",
    "universe_assets": ["US equities"],
    "universe_selection_criteria": "e.g., NYSE/AMEX common stocks, price > $5",
    "expected_sharpe": null,
    "expected_return": null,
    "max_drawdown": null,
    "expected_performance": {{}},
    "needs_human_review": []
}}

INSTRUCTIONS:
1. strategy_name: Short, specific name (e.g., "MAX Effect: Long-Short Decile Strategy"). Do NOT use the paper title or "Untitled". Keep under 8 words.
1b. strategy_type: "technical" (price/volume only), "fundamental" (accounting data), "hybrid" (both), "multi_asset" (multiple asset classes)
2. fundamental_data: List ALL accounting/financial metrics explicitly used (not just mentioned)
3. alternative_data: External/non-traditional data (macro, sentiment, analyst forecasts)
4. lookback_period: The number of trading days used for signal computation. Convert paper units: "one month" → 21, "12 months" → 252, "60 days" → 60. Use null only if the paper never states a lookback. Always use TRADING DAYS as the unit.
5. universe_selection_criteria: Be comprehensive — include ALL filters (price, market cap, exchange, industry exclusions)
6. expected_*: Extract from MAIN results table only; use null if not reported; annual_return as decimal (0.12 = 12%)
7. If a field is not mentioned in the paper/instructions, use null or empty — do NOT guess.
8. If data coverage, warm-up, and OOS evaluation differ, make time_period data-loading-safe by including all relevant dates.
9. For return-series strategies, set price_data=false and describe return_series semantics in later indicator fields.
10. needs_human_review items must be structured: {{"field_path":"...","label":"...","reason":"...","questions":["..."]}}.

Output ONLY valid JSON."""

LAYER2_INDICATORS_PROMPT = """Extract all indicators, factors, and computed signals used in this trading strategy.

STRATEGY CONTEXT:
Name: {strategy_name}
Type: {strategy_type}
Description: {description}
{strategy_focus}
INSTRUCTION / CLARIFICATION CONTEXT (authoritative fallback when paper is incomplete):
{instruction_context}

The paper content below is in markdown format with HTML tables and LaTeX equations.
Focus on the signal construction, indicator definitions, and formula sections.

FULL PAPER CONTENT:
{content}

Extract as JSON:
{{
    "indicators": [
        {{
            "name": "Human-readable name",
            "category": "technical|fundamental|derived",
            "formula": "Clear natural language description of the calculation",
            "latex": "LaTeX formula if applicable, e.g., r_{{i,t-12:t-1}}",
            "inputs": ["close", "volume", "book_value", "market_cap"],
            "parameters": {{"window": 252, "threshold": 0.5}},
            "scope": "time_series|cross_sectional",
            "output_type": "scalar|boolean|ranking|vector|matrix|series",
            "data_semantics": "price_series|return_series|null",
            "executable_explanation": "Inputs are X. Build upstream object Y. Output is Z with shape/type T."
        }}
    ]
}}

INDICATOR CATEGORIES:
- **technical**: Computed from price/volume data (SMA, RSI, MACD, momentum returns, volatility)
- **fundamental**: Computed from accounting/financial data (P/E, Book-to-Market, ROE, Operating Profitability)
- **derived**: Combination of multiple indicators or transformations (composite scores, z-scores, residuals)

SCOPE:
- **time_series**: Computed per asset over time (e.g., 12-month return for stock X)
- **cross_sectional**: Computed across assets at a point in time (e.g., rank all stocks by P/E)

OUTPUT TYPE:
- **scalar**: Numeric value (returns, ratios, z-scores)
- **boolean**: True/False signal (RSI < 30)
- **ranking**: Ordinal ranking across assets (1st, 2nd, ...)

INSTRUCTIONS:
1. Extract only indicators/upstream objects consumed by the selected strategy's logic or execution trigger — not benchmarks, diagnostics, robustness tables, theory-only examples, or mentions in passing.
2. indicator_id: Use descriptive lowercase format (e.g., "momentum_12m", "book_to_market", "rsi_14")
3. formula: Describe upstream input construction only. Codegen formulas/objectives/constraints belong to logic_pipeline.
4. inputs: List exact data fields needed (close, open, high, low, volume, book_value, earnings, etc.)
5. parameters: Include all tunable values with exact paper/instruction values; otherwise null. If benchmark/diagnostic/theory-only, mark parameters.implementation_status.
6. If an indicator conflicts with logic_pipeline, later repair the indicator; logic_pipeline is the codegen source of truth.
7. Use vector for N-vectors, matrix for N×N/K×K objects, series for time-indexed returns/PnL; for return-series inputs set data_semantics="return_series".

Output ONLY valid JSON."""

LAYER3_LOGIC_PIPELINE_PROMPT = """Extract the logic pipeline that transforms indicators into final trade signals.

STRATEGY: {strategy_name}
TYPE: {strategy_type}
{strategy_focus}
INSTRUCTION / CLARIFICATION CONTEXT (authoritative fallback when paper is incomplete):
{instruction_context}

AVAILABLE INDICATORS:
{indicators_summary}

The paper content below is in markdown format with HTML tables and LaTeX equations.
Focus on the sorting procedures, portfolio construction steps, and weighting schemes.

FULL PAPER CONTENT:
{content}

Extract as JSON:
{{
    "logic_pipeline": [
        {{
            "step_id": "step1",
            "description": "What this step does",
            "function": "filter|rank|quantile_sort|group_quantile_sort|condition|threshold|crossover|arithmetic|z_score|custom",
            "scope": "time_series|cross_sectional|within_group",
            "group_by": "",
            "inputs": ["indicator_id_or_prior_step_output"],
            "parameters": {{"n_quantiles": 5, "threshold": 0.5}},
            "expression": "Natural language or pseudo-code expression",
            "output": "output_variable_name",
            "output_type": "label|boolean|scalar|ranking|vector|matrix|series",
            "executable_explanation": "Inputs are X with shape S; compute Y; output Z with type T."
        }}
    ]
}}

FUNCTION TAXONOMY:

## Cross-sectional Operations (across all assets at one point in time):
- **filter**: Remove assets based on condition (e.g., "keep if price > $5, market cap > $100M")
- **rank**: Rank all assets by indicator value (output: 1, 2, 3...)
- **quantile_sort**: Sort assets into N quantiles/groups (output: "Q1", "Q2", ..., "Qn")
- **group_quantile_sort**: Sort WITHIN groups from a prior step (scope: within_group, group_by: prior_output)
- **z_score**: Standardize indicator values across assets at each time point

## Time-series Operations (per asset over time):
- **condition**: Boolean or categorical check (e.g., "if close > SMA_200") → output_type: boolean or label
- **threshold**: Classify into categories based on numeric thresholds → output_type: label
- **crossover**: Detect signal crossovers (e.g., "SMA_50 crosses above SMA_200") → output_type: boolean

## General Operations:
- **arithmetic**: Mathematical combination of indicators (e.g., "indicator_A - indicator_B")
- **custom**: Any other logic — describe clearly in expression

OUTPUT TYPES:
- **label**: Categorical ("Q1", "long_target", "oversold", "value_stock")
- **boolean**: True/False
- **scalar**: Numeric value
- **ranking**: Integer rank (1, 2, 3...)
- **vector**: Per-asset/per-factor numeric vector, including final `portfolio_weights`
- **matrix**: Cross-sectional matrix (covariance, second moment, loadings, kernel)
- **series**: Time-indexed return/PnL series, including `strategy_ret`

CANONICAL SPEC CONTRACT:
- `logic_pipeline` is the only codegen source of truth for formulas, objectives, constraints, shrinkage, normalization, and signal/weight generation.
- Categorical strategies end at `trade_signal`.
- Weight/optimizer/allocation strategies end at exactly `portfolio_weights` with output_type="vector".
- If selection precedes optimization, keep `trade_signal` first and `portfolio_weights` last.
- Do not infer objectives/constraints from Sharpe, cumulative return, or evaluation metrics; use explicit paper/plan/instruction equations only.
- Every constraint must name the constrained variable, dimension, and whether it applies to intermediate variables or final `portfolio_weights`.
- Do not propagate intermediate constraints (e.g. ensemble weights >= 0) to final asset weights.
- For quadratic utility, call M=E[RR'] an uncentered second moment matrix unless the paper centers returns.
- For shrinkage/eigendecomposition/PCA/LOO/Sherman-Morrison/QP, include paper-stated component formulas; if missing after checking instructions, add structured needs_human_review rather than guessing.

MULTI-DIMENSIONAL STRATEGIES (Double/Triple Sort):
For strategies with multiple sorting dimensions:
1. Step N-2: First sort (quantile_sort → factor_a_quintile)
2. Step N-1: Second sort WITHIN groups (group_quantile_sort, group_by: factor_a_quintile)
3. Step N (FINAL): Combine into trade signal using condition function

Example double-sort:
  step1: quantile_sort by book_to_market → value_quintile (Q1..Q5)
  step2: group_quantile_sort by momentum WITHIN value_quintile → momentum_decile (D1..D10)
  step3: condition → IF value_quintile='Q1' AND momentum_decile='D10' THEN 'long_target'

CRITICAL RULES:
1. The FINAL step must produce an actionable trade signal (long/short/hold), not an intermediate classification
2. step_id must be sequential (step1, step2, ...)
3. Each step's inputs must reference either indicator_ids or prior step outputs
4. Include ALL intermediate steps — don't skip from raw indicators to final signal
5. For sorting strategies: specify n_quantiles, breakpoint methodology
6. expression field: Write clear pseudo-code showing the exact logic.
7. Include all prior variables used by each expression in inputs.
8. Numeric constants must be exact selected-paper/instruction values; otherwise use null and flag review.
9. Report/custom metric formulas belong in expected_performance.metric_definitions, not as traded logic unless they change weights/orders.

Output ONLY valid JSON."""

LAYER4_EXECUTION_PROMPT = """Extract the execution plan and risk management rules.

STRATEGY: {strategy_name}
TYPE: {strategy_type}
{strategy_focus}
INSTRUCTION / CLARIFICATION CONTEXT (authoritative fallback when paper is incomplete):
{instruction_context}

LOGIC PIPELINE (available signals):
{logic_summary}

The paper content below is in markdown format with HTML tables and LaTeX equations.
Focus on the rebalancing frequency, execution timing, and risk management rules.

FULL PAPER CONTENT:
{content}

Extract as JSON:
{{
  "executable_explanation": "Single line: how data flows from inputs to final position, including timing and data type.",
    "execution_plan": [
        {{
            "plan_id": "exec_1",
            "description": "Description of this execution plan",
            "trigger": {{
                "trigger_type": "time_driven|signal_driven",
                "frequency": "daily|weekly|monthly|end_of_month|quarterly",
                "signal_lookup": "signal_name_if_signal_driven",
                "delay_bars": 1,
                "price_type": "open|close|vwap"
            }},
            "action": {{
                "signal_source": "final_signal_from_pipeline",
                "logic": "WHEN 'long_target': LONG; WHEN 'short_target': SHORT",
                "default_action": "hold"
            }},
            "position_sizing": {{
              "method": "equal_weight|quantile_based|signal_based|volatility_scaled|direct_weight",
              "max_position_pct": null,
              "total_exposure": null,
              "long_short": "long_only|short_only|long_short",
              "steps": [
                {{
                  "step_id": "sizing_step1",
                  "description": "How to turn the logic output into order weights",
                  "scope": "time_series|cross_sectional|within_group|null",
                  "group_by": null,
                  "inputs": ["final_signal_or_portfolio_weights"],
                  "parameters": {{}},
                  "expression": "Natural language or formula",
                  "output": "order_weights",
                  "output_type": "vector",
                  "executable_explanation": "Codegen-facing timing, lag, shape, and order-weight details."
                }}
              ],
              "executable_explanation": "What method means for codegen and how it consumes the logic_pipeline output."
            }},
            "executable_explanation": "How this plan consumes the logic_pipeline final output and what positive/negative values mean."
        }}
    ],
    "risk_management": [
        "Rule description (e.g., Stop loss at -10%)",
        "Position limit per asset",
        "Maximum sector exposure 25%"
    ],
    "risk_management_executable_explanation": "Single line: explicit risk rules present; if none, state none are specified.",
    "needs_human_review": []
}}

ACTION LOGIC FORMAT (pseudo-code):
  WHEN 'signal_value': ACTION [on TARGET]
  Examples:
    "WHEN 'Q1': LONG; WHEN 'Q5': SHORT"
    "WHEN long_signal=True: LONG; WHEN long_signal=False: EXIT"
    "WHEN spread_zscore < -2: LONG stock_A, SHORT stock_B; WHEN |zscore| < 0.5: CLOSE ALL"

INSTRUCTIONS:
1. trigger_type: "time_driven" for calendar-based rebalancing, "signal_driven" for indicator-triggered
2. frequency: Match the paper's rebalancing frequency (most academic papers use monthly or quarterly)
3. delay_bars: Set to 1 for lookahead bias prevention (execute next bar after signal)
4. signal_source: Reference the tradable output from logic_pipeline. If final return series exists after portfolio_weights, use portfolio_weights for orders and the return series only for metrics/reporting.
5. logic: Use pseudo-code describing which signal values trigger which actions
6. method: Use direct_weight when final output is portfolio_weights; equal_weight/quantile_based/signal_based only for categorical signals; volatility_scaled only when paper explicitly changes traded order weights.
7. long_short: "long_only" if paper only tests long positions, "long_short" if both
8. risk_management: Extract any stop-loss, position limits, drawdown constraints mentioned
9. If the paper doesn't specify a rule, use null or omit — don't fabricate constraints, fully invested assumptions, leverage caps, position caps, stop-losses, or drawdown limits.
10. For direct_weight, state portfolio_weights are target-exposure fractions for order_target_percent, not shares/contracts/order sizes.
11. If paper reports/evaluates returns scaled to annual volatility, separate raw order path from reported/evaluation path. Add a sizing step only when needed for reporting, with parameters target_annualized_volatility, annualization_factor, ddof=1, scale_type="ex_post_reported_evaluation_scale", not_live_risk_rule=true. Do not overwrite raw order_weights unless explicitly live-traded.
12. needs_human_review items must be structured: {{"field_path":"...","label":"...","reason":"...","questions":["..."]}}.

Output ONLY valid JSON."""

# ═══════════════════════════════════════════════════════════════
# Legacy: single-call specification prompt (kept for backward compat)
# ═══════════════════════════════════════════════════════════════

SPECIFICATION_PROMPT = """Convert the extracted paper content into a precise, executable strategy specification.

FULL PAPER CONTENT (markdown, may include HTML tables and LaTeX):
{content}

Instruction / clarification context: {instruction_context}

Map the information into a JSON object with the following structure:

{{
  "strategy_name": "<concise name>",
  "strategy_type": "technical | fundamental | hybrid",
  "asset_class": ["equity"],
  "description": "<one-paragraph summary>",
  "price_data": true,
  "volume_data": false,
  "fundamental_data": [],
  "alternative_data": [],
  "lookback_period": 200,
  "data_frequency": "daily",
  "data_source": "",
  "time_period": "",
  "universe_assets": [],
  "universe_selection_criteria": "",
  "expected_sharpe": null,
  "expected_return": null,
  "max_drawdown": null,
  "indicators": [
    {{
      "indicator_id": "ind_1",
      "name": "SMA",
      "category": "technical",
      "formula": "Simple moving average of close prices",
      "inputs": ["close"],
      "parameters": {{"window": 20}},
      "scope": "time_series",
      "output_type": "scalar"
    }}
  ],
  "logic_pipeline": [
    {{
      "step_id": "step_1",
      "description": "...",
      "function": "condition",
      "scope": "time_series",
      "inputs": ["ind_1"],
      "parameters": {{}},
      "expression": "close > SMA_20",
      "output": "long_signal",
      "output_type": "boolean"
    }}
  ],
  "execution_plan": [
    {{
      "plan_id": "exec_1",
      "description": "...",
      "trigger": {{
        "trigger_type": "time_driven",
        "frequency": "daily",
        "delay_bars": 1,
        "price_type": "open"
      }},
      "action": {{
        "signal_source": "long_signal",
        "logic": "if long_signal: buy; else: sell",
        "default_action": "hold"
      }},
      "position_sizing": {{
        "method": "equal_weight",
        "total_exposure": 1.0,
        "long_short": "long_only"
      }}
    }}
  ],
  "risk_management": []
}}

Return ONLY the JSON object, no additional text."""
