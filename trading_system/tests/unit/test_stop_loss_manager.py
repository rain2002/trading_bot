import pytest
from pathlib import Path
from trading_system.app.config.stop_loss_manager import StopLossManager

def test_stop_loss_manager_defaults(tmp_path: Path):
    config_file = str(tmp_path / "stop_loss_test.json")
    sl = StopLossManager(config_path=config_file)
    
    # Default is -0.08 (-8.0%)
    assert sl.get_global_default_pct() == -0.08
    assert sl.get_stop_loss_pct("AAPL") == -0.08
    assert not sl.has_override("AAPL")
    assert not sl.is_custom_override("AAPL")

def test_stop_loss_manager_override_and_reset(tmp_path: Path):
    config_file = str(tmp_path / "stop_loss_test.json")
    sl = StopLossManager(config_path=config_file)
    
    # Set override for NVDA to -5% (-0.05)
    sl.set_stop_loss_pct("NVDA", -0.05)
    assert sl.has_override("NVDA")
    assert sl.get_stop_loss_pct("NVDA") == -0.05
    
    # Verify persistence by creating a new manager pointing to the same file
    sl2 = StopLossManager(config_path=config_file)
    assert sl2.has_override("NVDA")
    assert sl2.get_stop_loss_pct("NVDA") == -0.05
    
    # Reset override
    sl2.reset_stop_loss("NVDA")
    assert not sl2.has_override("NVDA")
    assert sl2.get_stop_loss_pct("NVDA") == -0.08

def test_stop_loss_price_and_distance_calculations(tmp_path: Path):
    config_file = str(tmp_path / "stop_loss_test.json")
    sl = StopLossManager(config_path=config_file)
    
    avg_entry = 100.0
    # Default stop loss is -8% -> stop price should be 92.0
    stop_price = sl.get_stop_price("AAPL", avg_entry)
    assert pytest.approx(stop_price, 0.01) == 92.0
    
    # Current price 95.0 -> distance to stop is (95 - 92) / 95 = 3 / 95 = 0.031579 (3.16%)
    res = sl.get_distance_to_stop("AAPL", current_price=95.0, avg_entry=avg_entry)
    assert pytest.approx(res["stop_price"], 0.01) == 92.0
    assert pytest.approx(res["dollar_buffer"], 0.01) == 3.0
    assert pytest.approx(res["pct_buffer"], 0.01) == 3.16
    assert res["is_breached"] is False
    assert res["is_warning"] is False

    # Price breaches stop (90.0 < 92.0)
    res_breach = sl.get_distance_to_stop("AAPL", current_price=90.0, avg_entry=avg_entry)
    assert res_breach["is_breached"] is True

    # Custom stop loss -10% for MSFT -> stop price 90.0
    sl.set_stop_loss_pct("MSFT", -0.10)
    assert pytest.approx(sl.get_stop_price("MSFT", 100.0), 0.01) == 90.0

def test_stop_loss_global_default_update(tmp_path: Path):
    config_file = str(tmp_path / "stop_loss_test.json")
    sl = StopLossManager(config_path=config_file)
    
    sl.set_global_default_pct(-0.06)
    assert sl.get_global_default_pct() == -0.06
    # Non-overridden tickers use the new global default
    assert sl.get_stop_loss_pct("GOOGL") == -0.06
