"""Test configuration loading and defaults."""
import pytest


def test_config_loads():
    from core.config import get_config
    config = get_config()
    assert config is not None


def test_prop_firm_defaults():
    from core.config import PropFirmConfig
    pf = PropFirmConfig()
    assert pf.initial_balance == 50000.0
    assert pf.max_loss_limit == 2000.0
    assert pf.profit_target == 3000.0
    assert pf.no_overnight is True
    assert pf.consistency_rule == 0.5


def test_personal_risk_defaults():
    from core.config import PersonalRiskConfig
    pr = PersonalRiskConfig()
    assert pr.pdll == 200.0
    assert pr.pdpt == 300.0
    assert pr.max_trades_per_day == 3
    assert pr.min_risk_reward == 2.0
    assert pr.halt_after_daily_losses == 3


def test_execution_defaults():
    from core.config import ExecutionConfig
    ex = ExecutionConfig()
    assert ex.mode == "sandbox"
