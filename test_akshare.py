"""
AKShare 数据接口测试脚本
测试在 GitHub Actions 环境下能否获取 562060（标普A股红利）的：
1. 复权收盘价（用于涨跌幅）
2. 基金净值（用于溢价率分子）
3. ETF 实时/最新市价（用于溢价率分母）
"""

import akshare as ak
import pandas as pd

CODE = "562060"
NAME = "标普A股红利"

def test_price():
    """测试1：复权收盘价（前复权），用于计算日涨跌幅和各期收益率"""
    print("\n=== 测试1：复权收盘价 ===")
    try:
        df = ak.fund_etf_hist_em(
            symbol=CODE,
            period="daily",
            adjust="qfq",   # 前复权
            start_date="20250101",
            end_date="20500101",
        )
        print(f"✅ 成功，共 {len(df)} 行")
        print(f"   列名：{list(df.columns)}")
        print(f"   最新两行：\n{df.tail(2).to_string(index=False)}")
        return df
    except Exception as e:
        print(f"❌ 失败：{e}")
        return None

def test_nav():
    """测试2：基金单位净值，用于溢价率计算"""
    print("\n=== 测试2：基金净值 ===")
    try:
        df = ak.fund_open_fund_info_em(
            fund=CODE,
            indicator="单位净值走势",
        )
        print(f"✅ 成功，共 {len(df)} 行")
        print(f"   列名：{list(df.columns)}")
        print(f"   最新两行：\n{df.tail(2).to_string(index=False)}")
        return df
    except Exception as e:
        print(f"❌ 失败：{e}")
        return None

def test_realtime():
    """测试3：ETF 实时行情，用于获取当日市价"""
    print("\n=== 测试3：ETF 实时行情（当日市价）===")
    try:
        df = ak.fund_etf_spot_em()
        row = df[df["代码"] == CODE]
        if row.empty:
            print(f"❌ 在实时行情中未找到 {CODE}")
            return None
        print(f"✅ 成功")
        print(f"   列名：{list(df.columns)}")
        print(f"   {CODE} 数据：\n{row.to_string(index=False)}")
        return row
    except Exception as e:
        print(f"❌ 失败：{e}")
        return None

def test_premium(price_df, nav_df):
    """测试4：尝试计算溢价率"""
    print("\n=== 测试4：溢价率计算 ===")
    if price_df is None or nav_df is None:
        print("⚠️ 依赖数据缺失，跳过")
        return

    try:
        # 取最新市价
        latest_price = float(price_df.sort_values("日期").iloc[-1]["收盘"])

        # 取最新净值
        nav_col = [c for c in nav_df.columns if "净值" in c][0]
        date_col = [c for c in nav_df.columns if "日期" in c or "date" in c.lower()][0]
        nav_df[date_col] = pd.to_datetime(nav_df[date_col])
        latest_nav = float(nav_df.sort_values(date_col).iloc[-1][nav_col])

        premium = round((latest_price - latest_nav) / latest_nav * 100, 2)
        print(f"✅ 最新市价：{latest_price}，最新净值：{latest_nav}，溢价率：{premium}%")
    except Exception as e:
        print(f"❌ 计算失败：{e}")

def main():
    print(f"=== AKShare 接口测试：{NAME} ({CODE}) ===")

    price_df = test_price()
    nav_df   = test_nav()
    test_realtime()
    test_premium(price_df, nav_df)

    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    main()
