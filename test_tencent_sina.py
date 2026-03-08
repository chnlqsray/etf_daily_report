"""
腾讯 + 新浪 A 股接口可访问性测试
测试在 GitHub Actions 环境下能否获取 562060 的：
1. 腾讯 API：最新市价 + IOPV（实时参考净值）
2. 新浪 API：历史 K 线数据
"""

import requests
from datetime import datetime, timedelta

CODE_SINA = "sh562060"
CODE_TENCENT = "sh562060"


def test_tencent():
    """测试1：腾讯行情 API - 市价和 IOPV"""
    print("\n=== 测试1：腾讯 API ===")
    url = f"http://qt.gtimg.cn/q={CODE_TENCENT}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"HTTP 状态码：{resp.status_code}")
        print(f"原始返回内容（前200字符）：{resp.text[:200]}")

        # 解析 ~ 分隔的字段
        raw = resp.text
        data = raw.split("~")
        print(f"字段总数：{len(data)}")

        if len(data) > 4:
            price = data[3]
            print(f"✅ data[3]（最新市价）= {price}")
        else:
            print("❌ 字段数不足，无法取 data[3]")

        if len(data) > 55:
            iopv = data[54]
            print(f"✅ data[54]（IOPV）= {iopv}")
        else:
            print(f"❌ 字段数不足（只有 {len(data)} 个），无法取 data[54]")
            print(f"   现有所有字段：{data}")

    except Exception as e:
        print(f"❌ 请求失败：{e}")


def test_sina():
    """测试2：新浪历史 K 线 API"""
    print("\n=== 测试2：新浪 K 线 API ===")
    url = (
        f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php"
        f"/CN_MarketData.getKLineData"
        f"?symbol={CODE_SINA}&scale=240&ma=no&datalen=1023"
    )
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"HTTP 状态码：{resp.status_code}")
        print(f"原始返回内容（前300字符）：{resp.text[:300]}")

        import json
        data = json.loads(resp.text)
        print(f"✅ 解析成功，共 {len(data)} 条记录")

        if len(data) > 0:
            print(f"   最早一条：{data[0]}")
            print(f"   最新一条：{data[-1]}")

            # 验证自然月回溯是否可行
            latest_date = datetime.strptime(data[-1]["day"], "%Y-%m-%d")
            print(f"\n   最新交易日：{latest_date.strftime('%Y-%m-%d')}")

            for label, months in [("1月", 1), ("3月", 3), ("6月", 6), ("1年", 12), ("3年", 36)]:
                target = latest_date - timedelta(days=months * 30)
                candidates = [
                    d for d in data
                    if datetime.strptime(d["day"], "%Y-%m-%d") <= target
                ]
                if candidates:
                    past = candidates[-1]
                    ret = round(
                        (float(data[-1]["close"]) - float(past["close"]))
                        / float(past["close"]) * 100, 2
                    )
                    print(f"   {label} 收益率：{ret}%（基准日 {past['day']}，收盘 {past['close']}）")
                else:
                    print(f"   {label} 收益率：N/A（数据不足）")

    except json.JSONDecodeError:
        print(f"❌ JSON 解析失败，原始内容：{resp.text[:500]}")
    except Exception as e:
        print(f"❌ 请求失败：{e}")


def main():
    print(f"=== 腾讯 + 新浪接口测试：{CODE_TENCENT} ===")
    print(f"运行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    test_tencent()
    test_sina()
    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    main()
