"""Tests for utils.config — render_run_config + load_run_config round-trip."""

import json
import tempfile
from pathlib import Path

import pytest

from utils.config import load_run_config, render_run_config, RunConfigError


# ── render_run_config ────────────────────────────────────────


class TestRenderRunConfig:
    def test_renders_max_paper_spec(self):
        """Render a MAX-paper-style spec and check key fields."""
        spec = {
            "paper_title": "Maxing Out",
            "num_detected": 1,
            "strategies": [
                {
                    "strategy_name": "MAX Effect",
                    "strategy_type": "equity_long_short",
                    "asset_class": ["equity"],
                    "time_period": {
                        "start_date": "1962-07-01",
                        "end_date": "2005-12-31",
                    },
                    "indicators": [
                        {
                            "indicator_id": "max_daily_return",
                            "name": "MAX",
                            "output_type": "scalar",
                        },
                    ],
                    "execution_plan": [
                        {
                            "position_sizing": {
                                "steps": [
                                    {
                                        "parameters": {
                                            "weighting": "value-weighted"
                                        }
                                    }
                                ]
                            }
                        }
                    ],
                }
            ],
        }
        yaml_text = render_run_config(spec)
        assert "start_date: '1962-07-01'" in yaml_text or 'start_date: "1962-07-01"' in yaml_text
        assert "end_date: '2005-12-31'" in yaml_text or 'end_date: "2005-12-31"' in yaml_text
        assert "weighting: VW" in yaml_text  # 'value-weighted' → 'VW'
        assert "n_bins: 10" in yaml_text
        assert "forward_returns_lag: 1" in yaml_text
        # FF controls enabled for cross-sectional equity
        assert "ff_controls:" in yaml_text
        assert "ff.four_factor_monthly" in yaml_text
        assert "mom" in yaml_text
        # Commissions are NOT modelled (academic papers don't model them)
        assert "commission_rates" not in yaml_text

    def test_renders_minimal_spec_with_defaults(self):
        """A spec with no time_period / no indicators should still render."""
        spec = {
            "strategies": [
                {
                    "strategy_name": "test",
                    "strategy_type": "single_asset",
                    "asset_class": ["equity"],
                }
            ]
        }
        yaml_text = render_run_config(spec)
        # Defaults applied
        assert "start_date" in yaml_text
        assert "n_bins: 10" in yaml_text
        # Commissions are NOT modelled (academic papers don't model them)
        assert "commission_rates" not in yaml_text

    def test_dates_load_as_strings(self, tmp_path):
        """Dates in run_config.yaml must load as str, not datetime.date.

        Regression test: render_run_config used to strip quotes around
        date-shaped strings, causing PyYAML to parse them as
        datetime.date objects — which broke string operations
        (slicing, comparison) in generated strategy code.
        """
        import yaml
        spec = {
            "strategies": [{
                "strategy_name": "test",
                "strategy_type": "equity_long_short",
                "asset_class": ["equity"],
                "time_period": {"start_date": "1962-07-01", "end_date": "2005-12-31"},
            }]
        }
        yaml_text = render_run_config(spec)
        cfg = yaml.safe_load(yaml_text)
        assert isinstance(cfg["start_date"], str), (
            f"start_date should be str, got {type(cfg['start_date']).__name__}"
        )
        assert isinstance(cfg["end_date"], str), (
            f"end_date should be str, got {type(cfg['end_date']).__name__}"
        )
        # String operations should work
        assert cfg["start_date"][:7] == "1962-07"

    def test_unwraps_extraction_result(self):
        """If spec_dict has 'strategies' list, render the first strategy."""
        spec = {
            "paper_title": "Multi-strategy paper",
            "num_detected": 2,
            "strategies": [
                {
                    "strategy_name": "first",
                    "strategy_type": "equity_long_short",
                    "asset_class": ["equity"],
                    "indicators": [{"indicator_id": "x", "output_type": "scalar"}],
                    "time_period": {"start_date": "1990-01-01", "end_date": "2000-12-31"},
                },
                {
                    "strategy_name": "second",
                    "strategy_type": "single_asset",
                    "asset_class": ["equity"],
                    "indicators": [{"indicator_id": "y", "output_type": "scalar"}],
                },
            ],
        }
        yaml_text = render_run_config(spec)
        # First strategy's time_period wins
        assert "start_date: '1990-01-01'" in yaml_text or 'start_date: "1990-01-01"' in yaml_text

    def test_empty_strategies_raises(self):
        with pytest.raises(ValueError, match="empty 'strategies'"):
            render_run_config({"strategies": []})

    def test_no_ff_controls_for_single_asset(self):
        """FF controls should not be set for non-cross-sectional strategies."""
        spec = {
            "strategies": [
                {
                    "strategy_name": "test",
                    "strategy_type": "single_asset",
                    "asset_class": ["equity"],
                    "indicators": [{"indicator_id": "x", "output_type": "scalar"}],
                }
            ]
        }
        yaml_text = render_run_config(spec)
        assert "ff_controls" not in yaml_text

    def test_signals_long_leg_emitted_to_yaml(self):
        """Per-signal `long_leg` direction is emitted to run_config.yaml.

        Prevents the v3 bug where the agent guessed the ID direction
        instead of reading it from the spec. The spec lists each
        signal with ``long_leg: high | low``; the renderer passes it
        through unchanged so strategy.py can build the L/S portfolio
        from a known direction.
        """
        spec = {
            "strategies": [
                {
                    "strategy_name": "fip_test",
                    "strategy_type": "equity_long_short",
                    "asset_class": ["equity"],
                    "time_period": {"start_date": "1976-01-01", "end_date": "2007-12-31"},
                    "signals": [
                        {"name": "pret", "long_leg": "high"},
                        {"name": "id",   "long_leg": "low"},
                    ],
                }
            ]
        }
        yaml_text = render_run_config(spec)
        # Both signals are emitted with their direction
        assert "name: pret" in yaml_text
        assert "long_leg: high" in yaml_text
        assert "name: id" in yaml_text
        assert "long_leg: low" in yaml_text
        # signals: section header present
        assert "signals:" in yaml_text

    def test_signals_long_leg_validates_values(self):
        """Invalid long_leg values (not 'high' or 'low') are dropped silently.

        The renderer is best-effort: a bad value in the spec should
        not crash the YAML emission. The strategy code falls back to
        a sensible default when the signals list is empty.
        """
        spec = {
            "strategies": [
                {
                    "strategy_name": "test",
                    "strategy_type": "equity_long_short",
                    "asset_class": ["equity"],
                    "signals": [
                        {"name": "good", "long_leg": "high"},
                        {"name": "bad_typo", "long_leg": "hi"},   # invalid
                        {"name": "bad_null", "long_leg": None},   # invalid
                        {"name": "no_long_leg"},                   # missing
                    ],
                }
            ]
        }
        yaml_text = render_run_config(spec)
        # The valid signal is present
        assert "name: good" in yaml_text
        # The invalid ones are absent
        assert "bad_typo" not in yaml_text
        assert "bad_null" not in yaml_text
        assert "no_long_leg" not in yaml_text

    def test_weightings_reported_emitted(self):
        """weightings_reported from the spec is passed through to YAML.

        Most cross-sectional academic papers report BOTH EW and VW
        spreads in the same table. The renderer normalizes to
        uppercase, drops invalid entries, and dedupes — the strategy
        code uses this to compute both numbers and report them as
        bare + suffixed keys in metrics.json (see SKILL.md).
        """
        spec = {
            "strategies": [
                {
                    "strategy_name": "fip_test",
                    "strategy_type": "equity_long_short",
                    "asset_class": ["equity"],
                    "weightings_reported": ["EW", "VW", "vw", "MV", "EW"],
                }
            ]
        }
        yaml_text = render_run_config(spec)
        # Both valid values present, deduped, normalized to uppercase.
        # PyYAML emits lists in block style by default, not inline.
        assert "weightings_reported:" in yaml_text
        assert "\n- EW\n- VW\n" in yaml_text or "\n- VW\n- EW\n" in yaml_text
        # The invalid "MV" entry is dropped
        assert "MV" not in yaml_text
        # "EW" appears only once (deduped)
        assert yaml_text.count("- EW") == 1
        # Missing field → empty list
        spec2 = {"strategies": [{"strategy_name": "x", "asset_class": ["equity"]}]}
        yaml_text2 = render_run_config(spec2)
        assert "weightings_reported: []" in yaml_text2

    def test_universe_filter_built_correctly(self):
        spec = {
            "strategies": [
                {
                    "strategy_name": "test",
                    "strategy_type": "single_asset",
                    "asset_class": ["equity"],
                }
            ]
        }
        yaml_text = render_run_config(spec)
        assert "exchcd IN (1,2,3)" in yaml_text
        assert "shrcd IN (10,11)" in yaml_text

    def test_convention_defaults_present(self):
        """Convention defaults from paper_conventions.md should land in YAML."""
        spec = {
            "strategies": [
                {
                    "strategy_name": "test",
                    "strategy_type": "equity_long_short",
                    "asset_class": ["equity"],
                }
            ]
        }
        yaml_text = render_run_config(spec)
        assert "price_filter: 5.0" in yaml_text
        assert "delisting_adjustment: true" in yaml_text
        assert 'breakpoint_universe: NYSE' in yaml_text or "breakpoint_universe: NYSE" in yaml_text


# ── load_run_config ─────────────────────────────────────────


class TestLoadRunConfig:
    def test_round_trip(self, tmp_path):
        # Build a config and write it to a fake paper layout
        import yaml
        cfg = {
            "start_date": "1962-07-01",
            "end_date": "2005-12-31",
            "n_bins": 10,
            "weighting": "VW",
            "data_sources": {"daily_returns": "crsp_202601.dsf"},
        }
        slug = "test_paper"
        config_dir = tmp_path / slug / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "run_config.yaml").write_text(yaml.safe_dump(cfg))

        # Load it back via the function
        loaded = load_run_config(slug, replications_root=tmp_path)
        assert loaded["start_date"] == "1962-07-01"
        assert loaded["n_bins"] == 10
        assert loaded["data_sources"]["daily_returns"] == "crsp_202601.dsf"

    def test_missing_file_raises(self, tmp_path):
        slug = "nonexistent"
        (tmp_path / slug / "config").mkdir(parents=True)
        # No run_config.yaml written
        with pytest.raises(RunConfigError, match="run_config.yaml not found"):
            load_run_config(slug, replications_root=tmp_path)

    def test_malformed_yaml_raises(self, tmp_path):
        slug = "bad_yaml"
        config_dir = tmp_path / slug / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "run_config.yaml").write_text("invalid: : yaml: : :")

        with pytest.raises(RunConfigError, match="Failed to parse"):
            load_run_config(slug, replications_root=tmp_path)

    def test_empty_yaml_returns_empty_dict(self, tmp_path):
        slug = "empty"
        config_dir = tmp_path / slug / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "run_config.yaml").write_text("")
        loaded = load_run_config(slug, replications_root=tmp_path)
        assert loaded == {}

    def test_yaml_not_mapping_raises(self, tmp_path):
        slug = "list_yaml"
        config_dir = tmp_path / slug / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "run_config.yaml").write_text("- item1\n- item2\n")
        with pytest.raises(RunConfigError, match="did not parse to a mapping"):
            load_run_config(slug, replications_root=tmp_path)