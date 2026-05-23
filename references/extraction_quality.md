# Extraction Quality Reference

This reference captures the quality rules for `paper2spec` extraction and repair.
Read it whenever you extract, re-extract, audit, or prepare a `StrategySpec` for
code generation. It is intentionally detailed so agent-skill retrieval can
retrieve the relevant rule instead of relying on compressed prompt memory.

## When to Use This Reference

Use this reference when:

- Reviewing `spec.json` / `spec.md` before code generation.
- Re-extracting a paper because the first spec mixed variants or missed formulas.
- Loading user-provided instruction, clarification, or repair notes.
- Handling allocation, portfolio optimization, direct-weight, volatility-scaling,
  second-moment, covariance, shrinkage, PCA, LOO, Sherman-Morrison, or QP logic.
- Resolving conflicts between paper text, extracted indicators, logic steps,
  execution plans, and reported performance metrics.
- Matching high-risk formulas to the Operator Pitfall Index before repair.

Important: in the QSA `paper2spec-repair` workflow, “RAG” means a semantic
lookup over an operator-pitfall corpus, not a general paper/library RAG database.
The paper text, plans, and instruction/clarification files are loaded directly
from JSON/Markdown files and searched with normal reading/grep. Retrieved
operator-pitfall entries are mandatory audit checks for matched components, but
they are not primary evidence for paper formulas or constants.

QSA calls this repair skill from Stage 2 after extracting a selected plan:
`SpecificationExtractor._run_spec_fixer()` passes the draft spec, `plan_id`,
`output_dir`, `thread_id`, and user requirements to `skill_based_spec_repair()`.
The repair helper writes `{plan_id}_specs.json`, locates `*_content.json` and `*_plans.json` in the output directory, grants the CLI access to the sibling `uploads/` directory, retrieves operator pitfalls from a vector index, and then invokes Claude Code CLI to edit the spec in place. x2strategy currently uses these rules as an extraction/audit reference; it does not automatically run that QSA repair helper, so the agent must first choose the target strategy/plan and then run the same review/repair logic itself. To avoid model-only pitfall selection, run the x2strategy retrieval code (`paper2spec/operator_pitfall.py`, exposed by `scripts/operator_pitfalls.py`) to generate matched operator context via semantic similarity before asking the model to repair high-risk components.

## Grounding Order

Use the following evidence order:

1. Selected paper/document text.
2. Selected strategy/backtest/experiment context, if present.
3. User-provided or workspace files matching:
   - `*instruction*.md`
   - `*clarification*.md`
   - `*reference*.md`
4. Existing extracted `content.json`, `content.md`, `spec.json`, and `spec.md`.
5. Matched Operator Pitfall Index entries for high-risk components. These guide
  checks and repairs but do not replace paper/plan/instruction evidence.

Instruction/clarification files are authoritative fallback when the paper is
incomplete, including footnote-only formulas, appendix-only constants,
cited-but-not-restated equations, and missing empirical settings.

Do not reconstruct formulas from memory. If a formula/constant remains missing
after the grounding pass, write a structured `needs_human_review` item instead
of inventing a default.

Before extraction, ask the user whether they want to add clarifications,
custom selected-plan requirements, known constraints, or
instruction file paths. Academic papers often leave implementation choices in
appendices, footnotes, or cited work; these user-provided clarifications should
be loaded as high-priority instruction context.

## Operator Pitfall Retrieval

Before repairing any high-risk formula, first make sure the target strategy/plan has been selected, then match the draft component against
[../paper2spec/resources/operator_pitfall_index.md](../paper2spec/resources/operator_pitfall_index.md).
This mirrors QSA `paper2spec-repair`:

The pitfall corpus is intentionally editable. If the user knows a repeated
formula/timing/sizing/implementation pitfall that is not covered, ask during the
paper2spec flow and add a concise new `## operator:` entry before retrieval.

1. Split the draft spec into independent retrieval queries from:
   - `indicators[*]`, using `description`, `name`, `formula`, and
     `executable_explanation`;
   - `logic_pipeline[*]`, using `description`, `expression`,
     `executable_explanation`, and `output`;
   - `expected_performance.metric_definitions[*].steps[*]`, using step
     description/expression/explanation/output;
   - `execution_plan[*].position_sizing.steps[*]`, using step
     description/expression/explanation/output.
2. Build semantic search over operator entries from
  [../paper2spec/resources/operator_pitfall_index.md](../paper2spec/resources/operator_pitfall_index.md). In x2strategy, run
   `scripts/operator_pitfalls.py <spec.json> --strategy-index <i> -o <context.md>`
   for this step. This uses FAISS + HuggingFace embeddings when optional
   `agent` dependencies are installed.
3. Keep only relevant matches above threshold. The QSA implementation uses
  `SPEC_REPAIR_OPERATOR_PITFALL_THRESHOLD` and
  `SPEC_REPAIR_OPERATOR_PITFALL_TOP_K` to control this retrieval. x2strategy
  uses `X2STRATEGY_OPERATOR_PITFALL_THRESHOLD`,
  `X2STRATEGY_OPERATOR_PITFALL_TOP_K`, and
  `X2STRATEGY_OPERATOR_PITFALL_EMBEDDING_MODEL`.
4. Apply matched pitfalls only to the reported `matched_from` component path.
5. Use the matched entry as an audit checklist, not as a source for missing
   formulas or numeric constants.

The repair prompt may also include the matched entries inline and/or write them
to a temporary context document, such as
`{plan_id}_operator_pitfall_context.md`, so the repairing agent can read them
before editing. Never ask the model to scan the full pitfall index and decide
matches by itself.

Uploads are not part of this vector lookup. They are direct file evidence:
the repair workflow grants the agent access to the `uploads/` directory and also
copies `*instruction*.md` / `*_instruction.md` content into the prompt as
high-priority clarification context.

## Structured Review Flag Shape

Use this shape for every unresolved item:

```json
{
  "field_path": "logic_pipeline[2].parameters.gamma",
  "label": "Gamma",
  "reason": "Paper mentions gamma but does not state the selected-plan value.",
  "questions": ["What gamma value is used in this plan?"]
}
```

Rules:

- Make `field_path` precise enough to edit directly.
- Ask concrete questions, not generic “please review” notes.
- After extraction or repair, if any `needs_human_review` item exists, do not
  move directly to code generation. Present the unresolved questions through the
  interactive question tool. The user can answer in the dialog or provide an
  instruction/clarification file path; use the answer as repair context and
  update the spec before implementation.
- If a value is in `needs_human_review`, do not state it as confirmed in
  `description`, `expression`, or `executable_explanation`.

## Canonical Spec Contract

### Field Ownership

- `indicators`: upstream inputs and data objects only — data semantics, source
  fields, windows, shapes, and reference/debug definitions.
- `logic_pipeline`: executable research algorithm — formulas, objectives,
  constraints, shrinkage, normalization, signal generation, and final weights.
- `position_sizing`: how signals or weights become order weights, including
  direct-weight sizing, quantile-based sizing, signal-based sizing, or explicitly
  stated volatility scaling.
- `position_sizing.steps`: codegen-facing mapping from `trade_signal` or
  `portfolio_weights` to `order_weights`.
- `expected_performance.metric_definitions`: paper-specific metric formulas,
  metric overrides, and reported/evaluation-only scaling.
- `risk_management`: explicit live risk controls only, such as stop loss,
  drawdown limits, leverage caps, or position caps stated by the paper.

### Final Output Names

- Categorical signal strategies end at `trade_signal`.
- Optimizer/allocation/direct-weight strategies end at exactly
  `portfolio_weights` with `output_type="vector"`.
- If a paper selects assets before optimizing, keep selection first and
  `portfolio_weights` last.
- If both a realized return series and `portfolio_weights` exist, execution uses
  `portfolio_weights`; the return series is for metrics/reporting.

### Canonical Shapes

- `scalar`: one numeric value.
- `vector`: per-asset/per-factor numeric vector; final weights are
  `portfolio_weights`.
- `matrix`: covariance, second moment, loadings, kernels, or K×K/N×N objects.
- `series`: time-indexed returns, PnL, or realized strategy returns.
- `label`: categorical labels such as quantile names or target classes.
- `boolean`: true/false signal.
- `ranking`: ordinal cross-sectional rank.

## Selected-Plan Fidelity

- Match `time_period`, `data_frequency`, `universe_assets`,
  `universe_selection_criteria`, and parameter values to the selected
  strategy/backtest/experiment.
- Remove contamination from other plans, robustness tables, theory sections,
  baselines, or benchmarks.
- If an entry is theoretical, benchmark-only, or diagnostic-only, mark it in the
  existing `parameters` as `implementation_status` with one of:
  - `theoretical_only`
  - `benchmark_only`
  - `diagnostic_only`
- Do not add unsupported top-level fields for implementation status.

## Data and Timing Safety

- `lookback_period` must be explicitly supported by the paper/instruction/plan;
  otherwise use `null`.
- If data coverage, warm-up, and OOS evaluation differ, make `time_period`
  data-loading-safe by including required coverage, warm-up, and OOS dates in a
  single string or note.
- For each signal/execution path, clarify:
  - estimation date,
  - execution delay,
  - execution price type,
  - realized-return period.
- Include these details in `executable_explanation`.
- For return-series strategies:
  - set `price_data=false`,
  - use `data_semantics="return_series"`,
  - avoid OHLC inputs unless synthetic prices are explicitly needed downstream,
  - use `trigger.price_type=null` unless the execution engine truly requires a
    synthetic price field.

## Indicator Rules

- Keep indicators to upstream objects consumed by `logic_pipeline` or execution
  triggers.
- Do not keep benchmark, diagnostic, robustness, theory, or generic example
  objects unless marked via `parameters.implementation_status`.
- Formula definitions that produce tradable outputs belong in `logic_pipeline`,
  not duplicated in `indicators`.
- If an indicator conflicts with `logic_pipeline`, repair the indicator; the
  logic pipeline is the codegen source of truth.
- If an indicator is useful only for debugging or reference, state that in
  `parameters.implementation_status`.

## Logic Pipeline Rules

- Every executable formula, objective, constraint, shrinkage, normalization, and
  allocation equation lives in `logic_pipeline`.
- Every step must include all prior variables used by its expression in
  `inputs`.
- `step_id` values should be sequential and stable.
- `executable_explanation` should state input shapes, computation, output shape,
  timing, and one implementation guard if necessary.
- Numeric constants must be exact paper/plan/instruction values; otherwise use
  `null` and add `needs_human_review`.
- Formulas attributed to another paper should not be reconstructed from memory.

## Formula Grounding Safeguards

- Every indicator and logic expression must be present in the paper, selected
  plan, instruction file, clarification file, or customization.
- If the paper states only target/intent but not executable formulas, use the
  exact formula from instruction/clarification files if available.
- Replace vague wording and extractor-invented formulas with sourced executable
  formulas.
- If a formula appears inferred, reconstructed, or guessed, convert it into a
  precise `needs_human_review` item.
- Named algorithms need component formulas or review flags, including:
  - leave-one-out / LOO,
  - Sherman-Morrison,
  - PCA/eigendecomposition,
  - shrinkage,
  - quadratic programming / QP,
  - cross-validation grids,
  - ridge penalties,
  - normalization and back-projection.

## Matrix, Utility, and Shrinkage Rules

- For quadratic utility, call `M = E[RR']` an uncentered second-moment matrix,
  not covariance, unless the paper centers returns.
- Use covariance only when the paper explicitly says covariance or centers
  returns:
  `C[i,j] = mean_t (R[t,i] - mu[i]) * (R[t,j] - mu[j])`.
- Preserve full cross-term matrices. Do not collapse to diagonal variance unless
  explicitly specified.
- For eigenvalue shrinkage, describe `f(lambda)` as a shrinkage multiplier
  applied to `lambda`, unless the paper states replacement eigenvalues.
- If a step references eigenvectors, eigenvalues, or ridge penalty grid values,
  ensure its `inputs` include the eigendecomposition and relevant penalty grid.

## Portfolio Optimization and Allocation Rules

- A `portfolio_optimize` objective must come from an explicit paper/plan/
  instruction equation. Never infer it from Sharpe, return, alpha, or cumulative
  performance metrics.
- Every constraint must name:
  - constrained variable,
  - dimension,
  - whether it applies to an intermediate variable or final `portfolio_weights`.
- Do not propagate intermediate constraints to final asset weights. For example,
  non-negativity of ensemble weights does not imply non-negative asset weights.
- Do not assume:
  - fully invested portfolio,
  - gross exposure = 1,
  - net exposure = 0,
  - leverage caps,
  - stop-loss,
  - drawdown limits,
  - max position caps.
- If the paper states an algorithmic normalization that changes weights before
  trading, put it in `logic_pipeline` and end with final `portfolio_weights`.
- If the normalization is only for reported/evaluation metrics, put it in
  `expected_performance.metric_definitions` or a clearly separated reported
  branch in `position_sizing.steps`.

## Position Sizing Rules

- If the final tradable output is `portfolio_weights`, use
  `position_sizing.method="direct_weight"`.
- `direct_weight` means `portfolio_weights` are target-exposure fractions for
  `order_target_percent`, not shares, contracts, or raw order sizes.
- `position_sizing.steps` must link the tradable signal/weights to
  `order_weights`.
- For categorical `trade_signal`, state how selected assets are converted to
  weights, for example equal-weight long/short buckets.
- For direct weights, use a step like:
  `order_weights[t, asset] = portfolio_weights[t, asset]`.
- `action.signal_source` must point to the tradable signal, usually
  `trade_signal` or `portfolio_weights`, not a realized return series.

## Expected Performance and Metrics

- Put custom metric formulas in `expected_performance.metric_definitions`.
- If the paper overrides a standard metric definition, record the override.
- Sharpe should use sample standard deviation (`ddof=1`) by default unless the
  paper states otherwise.
- Factor diagnostics such as alpha, beta, t-stats, or regression diagnostics
  should not become codegen-facing trading logic unless the strategy explicitly
  trades on them.
- Metric and reported-scaling inputs must reuse existing logic-pipeline return
  series names.

## Explanation Consistency

For each field, ensure `description`, `formula`, `expression`, and
`executable_explanation` describe the same operation.

- If two fields disagree, keep the one directly supported by selected evidence.
- Add `needs_human_review` only when evidence is genuinely contradictory or
  missing after all grounding sources are checked.
- Do not describe unsupported values as confirmed.
- Avoid legacy aliases when canonical names exist.

## Final Consistency Pass

Before code generation or finalizing a repaired spec, check:

- Only the selected strategy/backtest remains.
- Final numeric weights are `portfolio_weights`.
- `indicators` only lists entries consumed by `logic_pipeline` or triggers.
- No duplicate/conflicting formula remains in both `indicators` and
  `logic_pipeline`.
- `logic_pipeline` contains objectives, constraints, normalization equations,
  and final signal/weight generation.
- `position_sizing.steps` links signals/weights to order weights.
- Report/custom metric formulas live in `expected_performance.metric_definitions`.
- Traded/order scaling lives in `logic_pipeline` or `position_sizing.steps` only
  when it changes actual orders.
- Reported/evaluation scaling is explicitly separated from raw order path.
- `output_type` matches actual dimensionality.
- Unsupported defaults are removed or set to `null`.
- `needs_human_review` items are structured and precise.
- If `position_sizing.method="direct_weight"`, `action.signal_source` points to
  `portfolio_weights`, and `action.logic` uses target-percent semantics.

## Direct Search Checklist

Use direct reading/grep over the paper content, selected plan, uploads, and
instruction files before finalizing:

- strategy name + `formula calculation parameters`
- strategy name + `portfolio construction objective constraints`
- strategy name + `rolling window rebalancing execution timing`
- strategy name + `second moment covariance matrix`
- strategy name + `eigenvalue shrinkage PCA ridge penalty grid`
- strategy name + `leave one out Sherman Morrison formula`
- strategy name + `portfolio weights normalization`
- `reported returns scaled annual volatility target volatility cumulative returns`
- `alpha regression statistical significance scaled returns`
- `table notes figure caption scaling annualized volatility`

If snippets conflict, prefer selected plan/instruction files over generic paper
sections, and record unresolved conflicts in `needs_human_review`.
