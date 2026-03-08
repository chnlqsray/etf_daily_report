import efinance as ef
import yfinance as yf
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime
import os
import time

import pandas as pd
from dateutil.relativedelta import relativedelta

# ================== 邮箱配置（从环境变量读取，不硬编码）==================
SMTP_SERVER = "smtp.126.com"
SMTP_PORT = 465

EMAIL_SENDER   = os.getenv("MY_EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("MY_EMAIL_PWD")
EMAIL_RECEIVER = os.getenv("MY_EMAIL_RECEIVER")

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
        return "#d00000"
    elif c < 0:
        return "#1e8449"
    else:
        return "#555555"

def icon_by_change(c):
    if c > 0:
        return "🔺"
    elif c < 0:
        return "🔻"
    else:
        return "➖"

def calc_returns(series, days):
    if len(series) <= days:
        return None
    latest = series.iloc[-1]
    past = series.iloc[-days]
    return round((latest - past) / past * 100, 2)

def fmt(v):
    return "N/A" if v is None else f"{v}%"

def calc_nav_return_by_month(nav_df, months):
    try:
        df = nav_df.copy()
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.sort_values("日期")
        nav_col = "累计净值" if "累计净值" in df.columns else "单位净值"
        end_date = df["日期"].iloc[-1]
        target_date = end_date - relativedelta(months=months)
        past_df = df[df["日期"] <= target_date]
        if past_df.empty:
            return None
        past_nav = past_df.iloc[-1][nav_col]
        latest_nav = df.iloc[-1][nav_col]
        return round((latest_nav - past_nav) / past_nav * 100, 2)
    except Exception as e:
        print(f"净值收益计算失败: {e}")
        return None

def calc_us_return_by_month(df, months):
    try:
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
        end_date = df.index[-1]
        target_date = end_date - relativedelta(months=months)
        past_df = df[df.index <= target_date]
        if past_df.empty:
            return None
        past_price = float(past_df.iloc[-1][price_col].iloc[0])
        latest_price = float(df.iloc[-1][price_col].iloc[0])
        return round((latest_price - past_price) / past_price * 100, 2)
    except Exception as e:
        print(f"美股收益计算失败: {e}")
        return None


# ================== 重试装饰器 ==================
def with_retry(func, *args, retries=3, delay=10, label=""):
    """
    对 func(*args) 最多重试 retries 次，每次失败等待 delay 秒。
    专为 efinance 跨洋网络波动设计。
    """
    for attempt in range(1, retries + 1):
        try:
            result = func(*args)
            return result
        except Exception as e:
            print(f"[{label}] 第 {attempt} 次尝试失败：{e}")
            if attempt < retries:
                print(f"[{label}] {delay} 秒后重试…")
                time.sleep(delay)
    print(f"[{label}] 全部 {retries} 次尝试均失败，跳过。")
    return None


# ================== 中国 ETF ==================
def get_china_etf(code):
    try:
        price_df = with_retry(
            ef.stock.get_quote_history, code,
            label=f"{code}-price"
        )
        nav_df = with_retry(
            ef.fund.get_quote_history, code,
            label=f"{code}-nav"
        )

        if price_df is None or nav_df is None:
            return None

        price_df = price_df.sort_values("日期")
        nav_df   = nav_df.sort_values("日期")

        price = price_df["收盘"]
        premium = round(
            (price.iloc[-1] - nav_df["单位净值"].iloc[-1])
            / nav_df["单位净值"].iloc[-1] * 100, 2
        )

        returns = {
            "1m": calc_nav_return_by_month(nav_df, 1),
            "3m": calc_nav_return_by_month(nav_df, 3),
            "6m": calc_nav_return_by_month(nav_df, 6),
            "1y": calc_nav_return_by_month(nav_df, 12),
            "3y": calc_nav_return_by_month(nav_df, 36),
        }

        return premium, returns
    except Exception as e:
        print(f"{code} 溢价/收益失败: {e}")
        return None

def get_china_etf_daily(code):
    try:
        df = with_retry(
            ef.stock.get_quote_history, code,
            label=f"{code}-daily"
        )
        if df is None or len(df) < 2:
            return None

        df = df.sort_values("日期")
        prev_close  = df["收盘"].iloc[-2]
        today_close = df["收盘"].iloc[-1]
        daily_ret   = round((today_close - prev_close) / prev_close * 100, 2)

        return prev_close, today_close, daily_ret
    except Exception as e:
        print(f"{code} 日度失败: {e}")
        return None


# ================== 美股 ==================
def get_us_returns(ticker):
    try:
        df = yf.download(ticker, period="5y", interval="1d", progress=False)
        if df.empty:
            return None
        return {
            "1m": calc_us_return_by_month(df, 1),
            "3m": calc_us_return_by_month(df, 3),
            "6m": calc_us_return_by_month(df, 6),
            "1y": calc_us_return_by_month(df, 12),
            "3y": calc_us_return_by_month(df, 36),
        }
    except Exception as e:
        print(f"{ticker} 收益失败: {e}")
        return None


# ================== 美股 HTML ==================
def build_us_etf_html():
    html = "<h3>🇺🇸 美股 ETF</h3>"
    html += """
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

    tickers = ["FTEC", "META", "AMZN", "GOOG"]

    for t in tickers:
        try:
            df = yf.download(t, period="2d", interval="1d", progress=False)
            if len(df) < 2:
                html += f"<tr><td>{t}</td><td colspan='8'>数据不足</td></tr>"
                continue

            prev_close  = df["Close"].iloc[-2].item()
            today_close = df["Close"].iloc[-1].item()
            daily_ret   = round((today_close - prev_close) / prev_close * 100, 2)

            chg_color = color_by_change(daily_ret)
            chg_icon  = icon_by_change(daily_ret)

            returns = get_us_returns(t)
            if returns is None:
                returns = {k: None for k in ["1m","3m","6m","1y","3y"]}

            html += f"""
            <tr>
                <td style="text-align:left;">{t}</td>
                <td>{prev_close:.3f}</td>
                <td>{today_close:.3f}</td>
                <td style="color:{chg_color}; font-weight:bold;">
                    {daily_ret}% {chg_icon}
                </td>
                <td>{fmt(returns['1m'])}</td>
                <td>{fmt(returns['3m'])}</td>
                <td>{fmt(returns['6m'])}</td>
                <td>{fmt(returns['1y'])}</td>
                <td>{fmt(returns['3y'])}</td>
            </tr>
            """
        except Exception as e:
            print(f"{t} 构建行失败: {e}")
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

    china_etfs = {
        "562060": "标普A股红利",
    }

    html = f"""
    <html>
    <body style="font-family:Arial;">
    <h2>ETF / 美股每日监控（{today}）</h2>

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
            daily = get_china_etf_daily(code)
            data  = get_china_etf(code)

            if not daily or not data:
                html += f"<tr><td>{name}</td><td colspan='9'>N/A</td></tr>"
                continue

            prev_close, today_close, daily_ret = daily
            premium, r = data

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
            print(f"{code} 整体失败，跳过: {e}")
            html += f"<tr><td>{name} ({code})</td><td colspan='9'>获取失败</td></tr>"

    html += "</table>"
    html += build_us_etf_html()
    html += "</body></html>"

    send_email(html)
    print("=== 脚本结束 ===")


if __name__ == "__main__":
    main()
