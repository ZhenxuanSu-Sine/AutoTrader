from autotrader.strategies.baselines import (
    buy_and_hold_weights,
    cross_sectional_momentum_weights,
    equal_weight_weights,
    moving_average_weights,
    time_series_momentum_weights,
    trend_equal_weight_weights,
)
from autotrader.strategies.defensive import large_cap_low_vol_monthly_weights
from autotrader.strategies.high_sharpe import (
    blend_weights,
    breakout_stock_selection_weights,
    breadth_regime_weights,
    defensive_composite_weights,
    dual_momentum_rotation_weights,
    multifactor_stock_selection_weights,
    multi_horizon_trend_weights,
    weighted_blend_weights,
)
from autotrader.strategies.ml import MLFeatureConfig, ml_feature_frame, rolling_ml_prediction_weights
from autotrader.strategies.monthly_ml import MonthlyMLConfig, monthly_ml_prediction_weights
from autotrader.strategies.overlays import cap_gross_exposure, scale_weights

__all__ = [
    "buy_and_hold_weights",
    "cross_sectional_momentum_weights",
    "equal_weight_weights",
    "moving_average_weights",
    "time_series_momentum_weights",
    "trend_equal_weight_weights",
    "large_cap_low_vol_monthly_weights",
    "blend_weights",
    "breakout_stock_selection_weights",
    "breadth_regime_weights",
    "defensive_composite_weights",
    "dual_momentum_rotation_weights",
    "multifactor_stock_selection_weights",
    "multi_horizon_trend_weights",
    "weighted_blend_weights",
    "MLFeatureConfig",
    "ml_feature_frame",
    "rolling_ml_prediction_weights",
    "MonthlyMLConfig",
    "monthly_ml_prediction_weights",
    "cap_gross_exposure",
    "scale_weights",
]
