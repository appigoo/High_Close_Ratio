import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import io  # 用于 CSV 下载
import traceback  # 用于错误调试

# 设置页面标题
st.title("TSLA (或其他股票) 强势趋势 + 放量高收 回测工具")

# 输入框：股票代码
ticker = st.text_input("股票代码", value="TSLA", help="输入股票代码，如 TSLA")

# 输入框：时间范围（改为 period 选择）
period = st.selectbox("时间范围", ["6mo", "1y", "2y", "5y", "10y"], index=1, help="选择历史数据范围（从当前日期往前）")

# 输入框：数据间隔
interval = st.selectbox("数据间隔", ["1d", "5d", "1wk", "1mo", "3mo"], index=0, help="选择数据时间间隔")

# 参数调整（可选，用户可微调阈值）
st.sidebar.header("回测参数")
high_close_threshold = st.sidebar.slider("高收阈值 (收盘/最高价 ≥ )", 0.90, 1.00, 0.98, 0.01)
volume_multiplier = st.sidebar.slider("放量倍数 (当日量 / 20日均量 > )", 1.0, 3.0, 1.5, 0.1)
sma_period = st.sidebar.slider("强势趋势 SMA 周期 (收盘 > SMA)", 10, 50, 20)

# 侧边栏说明
st.sidebar.markdown("---")
st.sidebar.info("时间范围说明：\n- 6mo: 6个月\n- 1y: 1年\n- 2y: 2年\n- 5y: 5年\n- 10y: 10年")

# 下载数据和回测
if st.button("开始回测"):
    with st.spinner("下载数据中..."):
        try:
            # 使用 period 参数下载数据
            data = yf.download(ticker, period=period, interval=interval)
            if data.empty:
                st.error("数据下载失败，请检查股票代码或范围。")
            else:
                st.success(f"数据下载成功！范围: {period}, 共 {len(data)} 条记录。")
                
                # 修复 MultiIndex 列（常见于 yfinance）
                if isinstance(data.columns, pd.MultiIndex):
                    st.info("检测到 MultiIndex 列，正在扁平化...")
                    data.columns = data.columns.droplevel(0)  # 移除顶层（如 ticker 名称）
                
                st.write("数据概览：")
                st.dataframe(data.head())

                # 添加 CSV 下载按钮（原始数据）
                csv_buffer = io.StringIO()
                data.to_csv(csv_buffer)
                st.download_button(
                    label="下载原始数据 CSV",
                    data=csv_buffer.getvalue(),
                    file_name=f"{ticker}_{period}_{interval}_data.csv",
                    mime="text/csv"
                )
        except Exception as e:
            st.error(f"下载数据出错：{e}")
            st.stop()

    try:
        # 增强调试信息
        st.write("**调试信息**：")
        st.write(f"Data shape: {data.shape}")
        st.write(f"Data columns: {data.columns.tolist()}")
        st.write(f"Columns type: {type(data.columns)}")
        if isinstance(data.columns, pd.MultiIndex):
            st.write(f"MultiIndex levels: {data.columns.levels}")
        st.write(f"Volume type: {type(data['Volume'])}")
        st.write(f"Volume shape: {data['Volume'].shape if hasattr(data['Volume'], 'shape') else 'No shape'}")

        # 计算指标 - 强制转换为 Series
        sma_series = data['Close'].rolling(window=sma_period).mean()
        if isinstance(sma_series, pd.DataFrame):
            sma_series = sma_series.iloc[:, 0]  # 提取第一列
        data['SMA'] = sma_series.fillna(0)

        avg_volume_series = data['Volume'].rolling(window=20).mean()
        if isinstance(avg_volume_series, pd.DataFrame):
            avg_volume_series = avg_volume_series.iloc[:, 0]
        data['Avg_Volume'] = avg_volume_series.fillna(0)

        high_close_series = data['Close'] / data['High']
        if isinstance(high_close_series, pd.DataFrame):
            high_close_series = high_close_series.iloc[:, 0]
        data['High_Close_Ratio'] = high_close_series.fillna(0)

        volume_ratio_series = data['Volume'] / data['Avg_Volume']
        if isinstance(volume_ratio_series, pd.DataFrame):
            volume_ratio_series = volume_ratio_series.iloc[:, 0]
        data['Volume_Ratio'] = volume_ratio_series.fillna(0)

        # 验证
        st.write(f"Volume_Ratio type after fix: {type(data['Volume_Ratio'])}")
        st.write(f"Volume_Ratio shape: {data['Volume_Ratio'].shape if hasattr(data['Volume_Ratio'], 'shape') else 'OK'}")

    except Exception as calc_error:
        st.error(f"计算指标出错：{calc_error}")
        st.code(traceback.format_exc())
        st.stop()

    # 定义信号：强势趋势 + 放量高收
    data['Strong_Trend'] = data['Close'] > data['SMA']
    data['High_Close'] = data['High_Close_Ratio'] >= high_close_threshold
    data['High_Volume'] = data['Volume_Ratio'] > volume_multiplier
    data['Signal'] = data['Strong_Trend'] & data['High_Close'] & data['High_Volume']

    # 回测：计算下一个交易日回报
    data['Next_Close'] = data['Close'].shift(-1)
    data['Return'] = (data['Next_Close'] - data['Close']) / data['Close']
    data['Success'] = data['Return'] > 0  # 上涨为成功

    # 过滤信号日子（排除最后一个 NaN）
    signals = data[data['Signal'] == True].copy()
    signals = signals.dropna(subset=['Next_Close'])  # 移除无下一个日的

    if signals.empty:
        st.warning("在指定条件下未找到任何信号日子。请调整参数或范围。")
    else:
        # 计算成功率
        success_rate = signals['Success'].mean() * 100
        total_signals = len(signals)
        successes = signals['Success'].sum()

        st.header(f"回测结果 ({period} 范围)")
        st.write(f"满足条件的天数：{total_signals}")
        st.write(f"成功次数（下一个交易日上涨）：{successes}")
        st.write(f"成功率：{success_rate:.2f}%")

        # 显示信号日子详情
        st.subheader("满足条件的日子详情")
        signals_display = signals[['Close', 'High_Close_Ratio', 'Volume_Ratio', 'Next_Close', 'Return', 'Success']].copy()
        signals_display['Success'] = signals_display['Success'].map({True: '是', False: '否'})
        signals_display['Return'] = signals_display['Return'].apply(lambda x: f"{x*100:.2f}%" if pd.notna(x) else 'N/A')
        st.dataframe(signals_display)

        # 添加信号 CSV 下载
        signals_csv = signals[['Close', 'High_Close_Ratio', 'Volume_Ratio', 'Next_Close', 'Return', 'Success']].copy()
        signals_csv_buffer = io.StringIO()
        signals_csv.to_csv(signals_csv_buffer)
        st.download_button(
            label="下载信号日子详情 CSV",
            data=signals_csv_buffer.getvalue(),
            file_name=f"{ticker}_{period}_{interval}_signals.csv",
            mime="text/csv"
        )

        # 图表：价格走势 + 信号标记
        st.subheader("价格走势图（信号标记）")
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(data.index, data['Close'], label='收盘价', color='blue')
        ax.plot(data.index, data['SMA'], label=f'SMA{sma_period}', color='orange')
        
        # 标记信号日子
        signal_dates = signals.index
        ax.scatter(signal_dates, data.loc[signal_dates, 'Close'], color='green', marker='^', s=100, label='买入信号')
        
        ax.set_title(f"{ticker} 价格走势 (信号: 强势趋势 + 放量高收, 范围: {period})")
        ax.set_xlabel("日期")
        ax.set_ylabel("价格")
        ax.legend()
        ax.grid(True)
        st.pyplot(fig)

        # 额外统计：平均回报
        avg_return = signals['Return'].mean() * 100
        st.write(f"满足条件后的平均下一个交易日回报：{avg_return:.2f}%")

# 页脚
st.sidebar.markdown("---")
st.sidebar.info("说明：\n- 强势趋势：收盘 > SMA(20)\n- 放量高收：收盘/最高 ≥ 0.98 且 量 > 20日均量 1.5x\n- 回测基于历史数据，不保证未来表现。\n- 支持下载原始数据和信号 CSV。\n- 新增 MultiIndex 修复，如仍有问题查看调试信息。")
