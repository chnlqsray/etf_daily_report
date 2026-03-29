# ETF 每日监控日报 · ETF Daily Monitor

一套通过 GitHub Actions 全自动运行的个人投资数据监控系统，每个工作日定时拉取 A 股 ETF 与美股数据，生成带颜色标注的 HTML 富文本邮件推送至指定邮箱。由本人主导需求与架构，通过与 AI 协作完成开发，零基础设施成本运行。

A fully automated personal investment monitoring system running on GitHub Actions. Every weekday, it fetches A-share ETF and US stock data, computes multi-period returns, and delivers a colour-coded HTML email report. Designed and directed by me, implemented through LLM collaboration, running at zero infrastructure cost.

---

## 功能说明 · Features

**A 股 ETF 监控**：调用腾讯行情 API（`qt.gtimg.cn` 实时接口 + `web.ifzq.gtimg.cn` 前复权K线接口），获取昨收、今收、日涨跌幅、单位净值与溢价率；前复权K线正确处理历史分红，计算 1 月、3 月、6 月、1 年、3 年五期收益率。

**A-share ETF monitoring**: Calls Tencent market APIs (real-time quote interface + forward-adjusted daily K-line interface) to retrieve previous close, current price, daily change, NAV, and premium rate. Forward-adjusted K-lines correctly account for historical dividends when computing 1M, 3M, 6M, 1Y, and 3Y returns.

**美股监控**：通过 yfinance 获取美股实时行情，同样按自然月回溯计算五期收益率，与 A 股数据在同一封邮件中并排展示。

**US stock monitoring**: Fetches US equity data via yfinance and computes the same five-period returns using a calendar-month lookback, displayed alongside A-share data in the same email.

**HTML 富文本邮件**：正涨显示红色 🔺，负跌显示绿色 🔻，溢价率按阈值分档着色（低于 1% 红色警示），一眼识别异常数据。邮件通过 126 邮箱 SMTP_SSL 发送，API 密钥从 GitHub Secrets 读取，代码中无任何硬编码。

**HTML rich-text email**: Gains shown in red 🔺, losses in green 🔻, premium rate colour-coded by threshold (below 1% triggers red warning). Email is sent via 126 SMTP_SSL; all credentials are read from GitHub Secrets — nothing is hard-coded.

**跨境数据访问解决方案**：A 股数据改用腾讯行情 API 而非国内券商接口，原因是腾讯 `qt.gtimg.cn` 可从 GitHub Actions 海外服务器（US East）直接访问，彻底绕开跨境访问限制。

**Cross-border data access**: A-share data is sourced from Tencent's market API rather than domestic broker interfaces, because `qt.gtimg.cn` is directly accessible from GitHub Actions runners (US East), completely bypassing cross-border restrictions.

---

## 定时计划 · Schedule

```yaml
# 英国时间早上 8:30（UTC 8:30），周一至周五
- cron: '30 8 * * 1-5'
```

夏令时期间（3–10 月）对应英国时间 9:30；冬令时期间（11–3 月）对应 8:30。如需调整为北京时间固定时刻，可修改为 `'30 1 * * 1-5'`（UTC+8 早上 9:30）。

During BST (Mar–Oct) this corresponds to 09:30 UK time; during GMT (Nov–Mar) it corresponds to 08:30 UK time. To fix to Beijing time instead, use `'30 1 * * 1-5'` (09:30 CST = 01:30 UTC).

---

## 配置方式 · Configuration

**第一步：添加 GitHub Secrets**

进入仓库 → Settings → Secrets and variables → Actions → New repository secret，依次添加：

Go to repository → Settings → Secrets and variables → Actions → New repository secret, and add:

| Secret 名称 | 说明 |
|-------------|------|
| `MY_EMAIL_SENDER` | 发件人邮箱地址（需开启 SMTP 授权） |
| `MY_EMAIL_PWD` | 邮箱 SMTP 授权码（非登录密码） |
| `MY_EMAIL_RECEIVER` | 收件人邮箱地址 |

**第二步：修改监控标的**

在 `etf_daily_cloud.py` 的 `main()` 函数中修改 `china_etfs` 字典与 `us_tickers` 列表，即可自定义监控的 A 股 ETF 代码和美股代码。

Edit the `china_etfs` dict and `us_tickers` list in the `main()` function of `etf_daily_cloud.py` to customise your watchlist.

**第三步：手动触发测试**

进入仓库 → Actions → ETF Daily Report → Run workflow，验证邮件发送是否正常。

Go to Actions → ETF Daily Report → Run workflow to trigger a manual test run and verify email delivery.

---

## 技术栈 · Tech Stack

| 类别 | 依赖 |
|------|------|
| 运行平台 | GitHub Actions (ubuntu-latest) |
| A 股数据 | 腾讯行情 API (requests) |
| 美股数据 | yfinance |
| 数据处理 | Pandas |
| 邮件发送 | smtplib + SMTP_SSL (126邮箱) |

---

## 仓库结构 · Repository Structure

```
etf_daily_report/
├── etf_daily_cloud.py      # 主脚本：数据拉取、计算、HTML生成、邮件发送
├── etf_daily.yml           # GitHub Actions workflow 配置
├── ETF.webp                # 运行结果示例图
└── requirements.txt        # 依赖列表
```

---

*Independently designed and delivered · 2026*
