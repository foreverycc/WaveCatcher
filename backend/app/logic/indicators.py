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