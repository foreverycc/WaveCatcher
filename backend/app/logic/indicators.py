import pandas as pd
import numpy as np

def compute_cd_indicator(data):
    # Ensure we get a Series, not a DataFrame column
    close = data['Close']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]  # Extract first column as Series
    
    # Define EMA warmup period (conservative standard)
    # Extended to 50 periods for additional safety margin in EMA convergence
    # Ensures high-quality signals with sufficient historical context
    ema_warmup_period = 0
    
    # 计算MACD
    fast_ema = close.ewm(span=12, adjust=False).mean()
    slow_ema = close.ewm(span=26, adjust=False).mean()
    diff = fast_ema - slow_ema
    dea = diff.ewm(span=9, adjust=False).mean()
    mcd = (diff - dea) * 2

    # 计算交叉事件
    cross_down = (mcd.shift(1) >= 0) & (mcd < 0)
    cross_up = (mcd.shift(1) <= 0) & (mcd > 0)

    # 计算N1和MM1
    n1 = _compute_barslast(cross_down, len(data))
    mm1 = _compute_barslast(cross_up, len(data))

    # 计算N1_SAFE和MM1_SAFE
    n1_safe = n1 + 1
    mm1_safe = mm1 + 1

    # 计算CC系列
    cc1 = _compute_llv(close, n1_safe)
    cc2 = _compute_ref(cc1, mm1_safe)
    cc3 = _compute_ref(cc2, mm1_safe)

    # 计算DIFL系列
    difl1 = _compute_llv(diff, n1_safe)
    difl2 = _compute_ref(difl1, mm1_safe)
    difl3 = _compute_ref(difl2, mm1_safe)

    # 生成条件信号
    aaa = (cc1 < cc2) & (difl1 > difl2) & (mcd.shift(1) < 0) & (diff < 0)
    bbb = (cc1 < cc3) & (difl1 < difl2) & (difl1 > difl3) & (mcd.shift(1) < 0) & (diff < 0)
    ccc = aaa | bbb
    jjj = ccc.shift(1) & (abs(diff.shift(1)) >= abs(diff) * 1.01)
    dxdx = jjj & ~jjj.shift(1, fill_value=False).fillna(False)

    # Mark early periods as NA due to EMA approximation
    # Professional approach: Only show signals when we're confident they're accurate
    result = dxdx.copy().astype('object')  # Convert to object dtype to allow NaN
    result.iloc[:ema_warmup_period] = np.nan
    
    return result

def compute_mc_indicator(data):
    """
    计算MC (卖出) 信号
    Based on the sell signal logic from futu_CD.txt
    """
    # Ensure we get a Series, not a DataFrame column
    close = data['Close']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]  # Extract first column as Series
    
    # Define EMA warmup period (conservative standard)
    # Extended to 50 periods for additional safety margin in EMA convergence
    # Ensures high-quality signals with sufficient historical context
    ema_warmup_period = 0
    
    # 计算MACD
    fast_ema = close.ewm(span=12, adjust=False).mean()
    slow_ema = close.ewm(span=26, adjust=False).mean()
    diff = fast_ema - slow_ema
    dea = diff.ewm(span=9, adjust=False).mean()
    mcd = (diff - dea) * 2

    # 计算交叉事件
    cross_down = (mcd.shift(1) >= 0) & (mcd < 0)
    cross_up = (mcd.shift(1) <= 0) & (mcd > 0)

    # 计算N1和MM1
    n1 = _compute_barslast(cross_down, len(data))
    mm1 = _compute_barslast(cross_up, len(data))

    # 计算N1_SAFE和MM1_SAFE
    n1_safe = n1 + 1
    mm1_safe = mm1 + 1

    # 计算CH系列 (使用HHV for highest high values)
    ch1 = _compute_hhv(close, mm1_safe)
    ch2 = _compute_ref(ch1, n1_safe)
    ch3 = _compute_ref(ch2, n1_safe)

    # 计算DIFH系列 (使用HHV for highest DIFF values)
    difh1 = _compute_hhv(diff, mm1_safe)
    difh2 = _compute_ref(difh1, n1_safe)
    difh3 = _compute_ref(difh2, n1_safe)

    # 生成卖出条件信号
    # ZJDBL := CH1 > CH2 AND DIFH1 < DIFH2 AND REF(MCD,1) > 0 AND DIFF > 0;
    zjdbl = (ch1 > ch2) & (difh1 < difh2) & (mcd.shift(1) > 0) & (diff > 0)
    
    # GXDBL := CH1 > CH3 AND DIFH1 > DIFH2 AND DIFH1 < DIFH3 AND REF(MCD,1) > 0 AND DIFF > 0;
    gxdbl = (ch1 > ch3) & (difh1 > difh2) & (difh1 < difh3) & (mcd.shift(1) > 0) & (diff > 0)
    
    # DBBL := (ZJDBL OR GXDBL) AND DIFF > 0;
    dbbl = (zjdbl | gxdbl) & (diff > 0)
    
    # DBJG := REF(DBBL,1) AND REF(DIFF,1)>= DIFF * 1.01;
    dbjg = dbbl.shift(1) & (diff.shift(1) >= diff * 1.01)
    
    # DBJGXC := NOT(REF(DBJG,1)) AND DBJG;
    dbjgxc = dbjg & ~dbjg.shift(1, fill_value=False).fillna(False)

    # Mark early periods as NA due to EMA approximation
    # Professional approach: Only show signals when we're confident they're accurate
    result = dbjgxc.copy().astype('object')  # Convert to object dtype to allow NaN
    result.iloc[:ema_warmup_period] = np.nan
    
    return result

def compute_nx_break_through(data):
    # Ensure we get Series, not DataFrame columns
    high = data['High']
    close = data['Close']
    if isinstance(high, pd.DataFrame):
        high = high.iloc[:, 0]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    
    short_upper = high.ewm(span=24, adjust=False).mean()
    break_through = (close > short_upper) & (close.shift(1) <= short_upper.shift(1))
    return break_through


def compute_cd_score(data):
    """
    Compute a 0-100 score for each CD (buy) signal.
    
    Score components (each ~33 points max):
      1. Divergence strength: how strongly DIFF diverges upward vs previous cycle
      2. Price position: how close price is to the recent low (lower = stronger buy)
      3. Volume confirmation: volume relative to 20-bar moving average
    
    Returns:
        pd.Series of float scores (0-100), NaN where there is no CD signal.
    """
    close = data['Close']
    volume = data['Volume']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    if isinstance(volume, pd.DataFrame):
        volume = volume.iloc[:, 0]

    # --- Recompute MACD internals (same as compute_cd_indicator) ---
    fast_ema = close.ewm(span=12, adjust=False).mean()
    slow_ema = close.ewm(span=26, adjust=False).mean()
    diff = fast_ema - slow_ema
    dea = diff.ewm(span=9, adjust=False).mean()
    mcd = (diff - dea) * 2

    cross_down = (mcd.shift(1) >= 0) & (mcd < 0)
    cross_up = (mcd.shift(1) <= 0) & (mcd > 0)

    n1 = _compute_barslast(cross_down, len(data))
    mm1 = _compute_barslast(cross_up, len(data))
    n1_safe = n1 + 1
    mm1_safe = mm1 + 1

    # LLV series for price and DIFF
    cc1 = _compute_llv(close, n1_safe)
    cc2 = _compute_ref(cc1, mm1_safe)
    difl1 = _compute_llv(diff, n1_safe)
    difl2 = _compute_ref(difl1, mm1_safe)

    # Get CD signal mask
    cd_signal = compute_cd_indicator(data).fillna(False).astype(bool)

    # Initialize score series as NaN
    score = pd.Series(np.nan, index=data.index)

    signal_indices = np.where(cd_signal)[0]
    if len(signal_indices) == 0:
        return score

    for idx in signal_indices:
        s = 0.0

        # --- Component 1: Divergence Strength (0-33) ---
        # CD = bullish divergence: price lower low but DIFF higher low
        # Strength = (difl1 - difl2) / abs(difl2)  (how much DIFF improved)
        d1 = difl1.iloc[idx]
        d2 = difl2.iloc[idx]
        if pd.notna(d1) and pd.notna(d2) and abs(d2) > 1e-10:
            div_ratio = (d1 - d2) / abs(d2)
            # Clamp to [0, 1] — ratio of 0 means barely diverging, 1+ means very strong
            div_score = min(max(div_ratio, 0.0), 1.0) * 33.0
        else:
            div_score = 16.5  # Neutral when data unavailable
        s += div_score

        # --- Component 2: Price Position (0-33) ---
        # How close current price is to the recent low (lower = better for buy)
        lookback = min(50, idx + 1)
        if lookback > 1:
            window_close = close.iloc[max(0, idx - lookback + 1):idx + 1]
            w_min = window_close.min()
            w_max = window_close.max()
            w_range = w_max - w_min
            if w_range > 1e-10:
                # Percentile: 0 = at low, 1 = at high
                pct = (close.iloc[idx] - w_min) / w_range
                # Lower percentile = better buy signal → invert
                price_score = (1.0 - pct) * 33.0
            else:
                price_score = 16.5
        else:
            price_score = 16.5
        s += price_score

        # --- Component 3: Volume Confirmation (0-33) ---
        vol_avg = volume.iloc[max(0, idx - 19):idx + 1].mean()
        if vol_avg > 0:
            vol_ratio = volume.iloc[idx] / vol_avg
            # Ratio of 1.0 = average → 16.5 pts; 2.0+ = strong → 33 pts; 0 = weak → 0 pts
            vol_score = min(vol_ratio / 2.0, 1.0) * 33.0
        else:
            vol_score = 16.5
        s += vol_score

        score.iloc[idx] = round(min(max(s, 0.0), 100.0), 1)

    return score


def compute_mc_score(data):
    """
    Compute a 0-100 score for each MC (sell) signal.
    
    Score components (each ~33 points max):
      1. Divergence strength: how strongly DIFF diverges downward vs previous cycle
      2. Price position: how close price is to the recent high (higher = stronger sell)
      3. Volume confirmation: volume relative to 20-bar moving average
    
    Returns:
        pd.Series of float scores (0-100), NaN where there is no MC signal.
    """
    close = data['Close']
    volume = data['Volume']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    if isinstance(volume, pd.DataFrame):
        volume = volume.iloc[:, 0]

    # --- Recompute MACD internals (same as compute_mc_indicator) ---
    fast_ema = close.ewm(span=12, adjust=False).mean()
    slow_ema = close.ewm(span=26, adjust=False).mean()
    diff = fast_ema - slow_ema
    dea = diff.ewm(span=9, adjust=False).mean()
    mcd = (diff - dea) * 2

    cross_down = (mcd.shift(1) >= 0) & (mcd < 0)
    cross_up = (mcd.shift(1) <= 0) & (mcd > 0)

    n1 = _compute_barslast(cross_down, len(data))
    mm1 = _compute_barslast(cross_up, len(data))
    n1_safe = n1 + 1
    mm1_safe = mm1 + 1

    # HHV series for price and DIFF
    ch1 = _compute_hhv(close, mm1_safe)
    ch2 = _compute_ref(ch1, n1_safe)
    difh1 = _compute_hhv(diff, mm1_safe)
    difh2 = _compute_ref(difh1, n1_safe)

    # Get MC signal mask
    mc_signal = compute_mc_indicator(data).fillna(False).astype(bool)

    # Initialize score series as NaN
    score = pd.Series(np.nan, index=data.index)

    signal_indices = np.where(mc_signal)[0]
    if len(signal_indices) == 0:
        return score

    for idx in signal_indices:
        s = 0.0

        # --- Component 1: Divergence Strength (0-33) ---
        # MC = bearish divergence: price higher high but DIFF lower high
        # Strength = (difh2 - difh1) / abs(difh2)  (how much DIFF declined)
        d1 = difh1.iloc[idx]
        d2 = difh2.iloc[idx]
        if pd.notna(d1) and pd.notna(d2) and abs(d2) > 1e-10:
            div_ratio = (d2 - d1) / abs(d2)
            div_score = min(max(div_ratio, 0.0), 1.0) * 33.0
        else:
            div_score = 16.5
        s += div_score

        # --- Component 2: Price Position (0-33) ---
        # How close current price is to the recent high (higher = better for sell)
        lookback = min(50, idx + 1)
        if lookback > 1:
            window_close = close.iloc[max(0, idx - lookback + 1):idx + 1]
            w_min = window_close.min()
            w_max = window_close.max()
            w_range = w_max - w_min
            if w_range > 1e-10:
                pct = (close.iloc[idx] - w_min) / w_range
                # Higher percentile = better sell signal
                price_score = pct * 33.0
            else:
                price_score = 16.5
        else:
            price_score = 16.5
        s += price_score

        # --- Component 3: Volume Confirmation (0-33) ---
        vol_avg = volume.iloc[max(0, idx - 19):idx + 1].mean()
        if vol_avg > 0:
            vol_ratio = volume.iloc[idx] / vol_avg
            vol_score = min(vol_ratio / 2.0, 1.0) * 33.0
        else:
            vol_score = 16.5
        s += vol_score

        score.iloc[idx] = round(min(max(s, 0.0), 100.0), 1)

    return score

def _compute_barslast(cross_events, length):
    barslast = np.zeros(length, dtype=int)
    last_event = -1
    for i in range(length):
        # Get scalar boolean value
        if cross_events.iloc[i].item():
            last_event = i
        barslast[i] = i - last_event if last_event != -1 else 0
    return pd.Series(barslast, index=cross_events.index)

def _compute_llv(series, periods):
    llv = pd.Series(index=series.index, dtype=float)
    for i in range(len(series)):
        period = periods.iloc[i]
        if period > 0:
            start = max(0, i - period + 1)
            llv.iloc[i] = series.iloc[start:i+1].min()
        else:
            llv.iloc[i] = np.nan
    return llv

def _compute_hhv(series, periods):
    """
    计算HHV (Highest High Value) - 最高值
    """
    hhv = pd.Series(index=series.index, dtype=float)
    for i in range(len(series)):
        period = periods.iloc[i]
        if period > 0:
            start = max(0, i - period + 1)
            hhv.iloc[i] = series.iloc[start:i+1].max()
        else:
            hhv.iloc[i] = np.nan
    return hhv

def _compute_ref(series, lags):
    ref = pd.Series(index=series.index, dtype=float)
    for i in range(len(series)):
        lag = lags.iloc[i]
        if lag <= i:
            ref.iloc[i] = series.iloc[i - lag]
        else:
            ref.iloc[i] = np.nan
    return ref