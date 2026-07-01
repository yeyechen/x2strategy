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
        assert "start_date: 1962-07-01" in yaml_text
        assert "end_date: 2005-12-31" in yaml_text
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
        assert "start_date: 1990-01-01" in yaml_text

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