"""
ETF / 美股每日监控 - 云端版
部署平台：GitHub Actions

A 股数据来源：腾讯行情 API（境外可访问）
  - 实时接口：qt.gtimg.cn         → 当日市价、净值、溢价率、日涨跌幅
  - 复权K线：web.ifzq.gtimg.cn    → 前复权历史价格，正确处理分红，用于各期收益率

美股数据来源：yfinance（雅虎财经，境外原生访问）

邮箱配置：从 GitHub Secrets 环境变量读取，不硬编码
"""

import requests
import yfinance as yf
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime, timedelta
import os
import json

import pandas as pd

# ================== 邮箱配置（从 GitHub Secrets 环境变量读取）==================
SMTP_SERVER = "smtp.126.com"
SMTP_PORT   = 465

EMAIL_SENDER   = os.getenv("MY_EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("MY_EMAIL_PWD")
EMAIL_RECEIVER = os.getenv("MY_EMAIL_RECEIVER")

# ================== 请求头（模拟浏览器，防止被拦截）==================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ================== 工具函数 ==================
def color_by_premium(p):
    if p < 1:
        return "#d00000"
    elif p < 3:
        return "#e67e22"
    else:
        return "#000000"

def icon_by_premium(p):
    if p < 1:
        return "🔴"
    elif p < 3:
        return "🟠"
    else:
        return ""

def color_by_change(c):
    if c > 0:
        return "#d00000"   # 红涨
    elif c < 0:
        return "#1e8449"   # 绿跌
    else:
        return "#555555"

def icon_by_change(c):
    if c > 0:
        return "🔺"
    elif c < 0:
        return "🔻"
    else:
        return "➖"

def fmt(v):
    """格式化收益率，None 显示 N/A"""
    return "N/A" if v is None else f"{v}%"


# ================== 腾讯实时接口：日涨跌幅 + 溢价率 ==================
def get_china_etf_realtime(code):
    """
    调用腾讯实时行情接口获取：
      - 昨收、今收、日涨跌幅
      - 单位净值（data[81]）、溢价率

    返回：(prev_close, today_close, daily_ret, nav, premium) 或 None
    """
    url = f"http://qt.gtimg.cn/q=sh{code}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()

        # 原始格式：v_sh562060="1~名称~代码~今收~昨收~..."
        raw  = resp.text
        body = raw.split('"')[1]          # 取引号内的内容
        data = body.split("~")

        today_close = float(data[3])      # 最新价（今收）
        prev_close  = float(data[4])      # 昨收
        daily_ret   = round((today_close - prev_close) / prev_close * 100, 2)

        nav         = float(data[81])     # 单位净值（经验证字段）
        premium     = round((today_close / nav - 1) * 100, 2)

        return prev_close, today_close, daily_ret, nav, premium

    except Exception as e:
        print(f"[{code}] 腾讯实时接口失败: {e}")
        return None


# ================== 腾讯复权K线接口：各期收益率 ==================
def get_china_etf_returns(code):
    """
    调用腾讯前复权日K线接口，按自然月回溯计算各期收益率。
    前复权已将历史分红折算进价格，适用于高频分红型 ETF（如 562060）。

    返回：{"1m": ..., "3m": ..., "6m": ..., "1y": ..., "3y": ...} 或 None
    """
    url = (
        f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param=sh{code},day,,,750,qfq"   # qfq=前复权，最多取750条
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        raw_data = json.loads(resp.text)
        klines   = raw_data["data"][f"sh{code}"]["qfqday"]
        # 每条格式：[日期, 开盘, 收盘, 最高, 最低, 成交量]

        if not klines:
            return None

        latest_date  = datetime.strptime(klines[-1][0], "%Y-%m-%d")
        latest_close = float(klines[-1][2])   # index 2 = 收盘价

        returns = {}
        for label, months in [("1m", 1), ("3m", 3), ("6m", 6), ("1y", 12), ("3y", 36)]:
            target = latest_date - timedelta(days=months * 30)
            # 取所有 ≤ target 日期中最近的一条
            candidates = [
                k for k in klines
                if datetime.strptime(k[0], "%Y-%m-%d") <= target
            ]
            if candidates:
                past_close = float(candidates[-1][2])
                returns[label] = round(
                    (latest_close - past_close) / past_close * 100, 2
                )
            else:
                returns[label] = None   # 数据不足（如基金成立时间较短）

        return returns

    except Exception as e:
        print(f"[{code}] 腾讯K线接口失败: {e}")
        return None


# ================== 美股：日涨跌幅 + 各期收益率 ==================
def calc_us_return_by_month(df, months):
    """按自然月回溯计算美股收益率，贴近网页口径"""
    try:
        df   = df.copy().sort_index()
        end  = df.index[-1]
        target = end - timedelta(days=months * 30)
        past_df = df[df.index <= target]
        if past_df.empty:
            return None
        past    = float(past_df.iloc[-1]["Close"].iloc[0])
        latest  = float(df.iloc[-1]["Close"].iloc[0])
        return round((latest - past) / past * 100, 2)
    except Exception as e:
        print(f"美股收益计算失败: {e}")
        return None

def get_us_data(ticker):
    """
    返回：(prev_close, today_close, daily_ret, returns_dict) 或 None
    """
    try:
        df2 = yf.download(ticker, period="2d",  interval="1d", progress=False)
        df5 = yf.download(ticker, period="5y",  interval="1d", progress=False)

        if len(df2) < 2 or df5.empty:
            return None

        prev_close  = float(df2["Close"].iloc[-2].iloc[0])
        today_close = float(df2["Close"].iloc[-1].iloc[0])
        daily_ret   = round((today_close - prev_close) / prev_close * 100, 2)

        returns = {
            "1m": calc_us_return_by_month(df5, 1),
            "3m": calc_us_return_by_month(df5, 3),
            "6m": calc_us_return_by_month(df5, 6),
            "1y": calc_us_return_by_month(df5, 12),
            "3y": calc_us_return_by_month(df5, 36),
        }
        return prev_close, today_close, daily_ret, returns

    except Exception as e:
        print(f"[{ticker}] 美股数据失败: {e}")
        return None


# ================== 构建 A 股 ETF HTML 表格 ==================
def build_china_etf_html(china_etfs):
    html = """
    <h3>🇨🇳 中国 ETF</h3>
    <table border="1" cellpadding="6" cellspacing="0"
           style="border-collapse:collapse; font-size:13px; text-align:right;">
    <tr style="background-color:#f0f0f0;">
        <th style="text-align:left;">ETF</th>
        <th>昨收</th>
        <th>今收</th>
        <th>日涨跌</th>
        <th>溢价率</th>
        <th>1月</th>
        <th>3月</th>
        <th>6月</th>
        <th>1年</th>
        <th>3年</th>
    </tr>
    """

    for code, name in china_etfs.items():
        try:
            realtime = get_china_etf_realtime(code)
            returns  = get_china_etf_returns(code)

            if not realtime:
                html += f"<tr><td>{name} ({code})</td><td colspan='9'>实时数据获取失败</td></tr>"
                continue

            prev_close, today_close, daily_ret, nav, premium = realtime
            r = returns or {k: None for k in ["1m","3m","6m","1y","3y"]}

            chg_color = color_by_change(daily_ret)
            chg_icon  = icon_by_change(daily_ret)
            p_color   = color_by_premium(premium)
            p_icon    = icon_by_premium(premium)

            html += f"""
            <tr>
                <td style="text-align:left;">{name} ({code})</td>
                <td>{prev_close:.3f}</td>
                <td>{today_close:.3f}</td>
                <td style="color:{chg_color}; font-weight:bold;">
                    {daily_ret}% {chg_icon}
                </td>
                <td style="color:{p_color}; font-weight:bold;">
                    {premium}% {p_icon}
                </td>
                <td>{fmt(r['1m'])}</td>
                <td>{fmt(r['3m'])}</td>
                <td>{fmt(r['6m'])}</td>
                <td>{fmt(r['1y'])}</td>
                <td>{fmt(r['3y'])}</td>
            </tr>
            """
        except Exception as e:
            print(f"[{code}] 构建行失败，跳过: {e}")
            html += f"<tr><td>{name} ({code})</td><td colspan='9'>获取失败</td></tr>"

    html += "</table>"
    return html


# ================== 构建美股 HTML 表格 ==================
def build_us_etf_html(tickers):
    html = """
    <h3>🇺🇸 美股 ETF</h3>
    <table border="1" cellpadding="6" cellspacing="0"
           style="border-collapse:collapse; font-size:13px; text-align:right;">
    <tr style="background-color:#f0f0f0;">
        <th style="text-align:left;">ETF</th>
        <th>昨收</th>
        <th>今收</th>
        <th>涨跌幅</th>
        <th>1月</th>
        <th>3月</th>
        <th>6月</th>
        <th>1年</th>
        <th>3年</th>
    </tr>
    """

    for t in tickers:
        try:
            result = get_us_data(t)
            if not result:
                html += f"<tr><td>{t}</td><td colspan='8'>数据获取失败</td></tr>"
                continue

            prev_close, today_close, daily_ret, r = result
            chg_color = color_by_change(daily_ret)
            chg_icon  = icon_by_change(daily_ret)

            html += f"""
            <tr>
                <td style="text-align:left;">{t}</td>
                <td>{prev_close:.3f}</td>
                <td>{today_close:.3f}</td>
                <td style="color:{chg_color}; font-weight:bold;">
                    {daily_ret}% {chg_icon}
                </td>
                <td>{fmt(r['1m'])}</td>
                <td>{fmt(r['3m'])}</td>
                <td>{fmt(r['6m'])}</td>
                <td>{fmt(r['1y'])}</td>
                <td>{fmt(r['3y'])}</td>
            </tr>
            """
        except Exception as e:
            print(f"[{t}] 构建行失败，跳过: {e}")
            html += f"<tr><td>{t}</td><td colspan='8'>获取失败</td></tr>"

    html += "</table>"
    return html


# ================== 邮件发送 ==================
def send_email(html):
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER]):
        print("❌ 邮箱环境变量未配置，跳过发送。")
        return

    msg = MIMEText(html, "html", "utf-8")
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECEIVER
    msg["Subject"] = Header("ETF / 美股每日监控", "utf-8")

    server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
    server.login(EMAIL_SENDER, EMAIL_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("✅ 邮件发送成功")


# ================== 主逻辑 ==================
def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"=== ETF 日报脚本启动：{today} ===")

    # ── 在此添加或修改监控标的 ──────────────────────────────────────────
    china_etfs = {
        "562060": "标普A股红利",
    }
    us_tickers = ["FTEC", "META", "AMZN", "GOOG"]
    # ────────────────────────────────────────────────────────────────────

    html = f"""
    <html>
    <body style="font-family:Arial;">
    <h2>ETF / 美股每日监控（{today}）</h2>
    {build_china_etf_html(china_etfs)}
    {build_us_etf_html(us_tickers)}
    </body></html>
    """

    send_email(html)
    print("=== 脚本结束 ===")


if __name__ == "__main__":
    main()
