"""
ETF 持股監控工具
每天爬取兩個 ETF 的前10大持股，比較差異並記錄
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 強制 stdout/stderr 使用 UTF-8，避免排程器以 CP950 執行時中文或特殊符號出錯
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

SOURCES = {
    "復華未來50 (00991A)": {
        "url": "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23#stockhold",
        "key": "fhtrust_00991A",
        "scraper": "fhtrust",
    },
    "統一台股增長 (00981A)": {
        "url": "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=49YTW",
        "key": "ezmoney_49YTW",
        "scraper": "ezmoney",
    },
}


async def scrape_fhtrust(page):
    """爬取復華未來50的前10大持股"""
    url = "https://www.fhtrust.com.tw/ETF/etf_detail/ETF23#stockhold"
    print(f"  正在載入: {url}")
    await page.goto(url, wait_until="networkidle", timeout=60000)

    # 等待持股表格出現（等待包含「證券代號」的元素）
    try:
        await page.wait_for_selector("text=證券代號", timeout=30000)
    except Exception:
        print("  警告：等待超時，嘗試直接擷取資料")

    # 使用 JavaScript 從 DOM 中提取持股資料
    holdings = await page.evaluate("""
        () => {
            // 找到包含「證券代號」標題的表格
            const allTables = document.querySelectorAll('table');
            for (const table of allTables) {
                const headerRow = table.querySelector('tr');
                if (!headerRow) continue;
                const headerText = headerRow.textContent || '';
                if (headerText.includes('證券代號') && headerText.includes('證券名稱')) {
                    const rows = table.querySelectorAll('tbody tr');
                    const data = [];
                    for (let i = 0; i < Math.min(10, rows.length); i++) {
                        const cells = rows[i].querySelectorAll('td');
                        if (cells.length >= 4) {
                            const code = cells[0].textContent.trim();
                            const name = cells[1].textContent.trim();
                            const shares = cells[2].textContent.trim().replace(/,/g, '');
                            const amount = cells[3].textContent.trim().replace(/,/g, '');
                            const weight = cells[4] ? cells[4].textContent.trim() : '';
                            if (code) {
                                data.push({ rank: i + 1, code, name, shares, amount, weight });
                            }
                        }
                    }
                    return data;
                }
            }

            // 備用方案：嘗試用 div/section 結構
            const headings = document.querySelectorAll('th, td');
            for (const h of headings) {
                if (h.textContent.trim() === '證券代號') {
                    const table = h.closest('table');
                    if (table) {
                        const rows = table.querySelectorAll('tr');
                        const data = [];
                        let count = 0;
                        for (let i = 1; i < rows.length && count < 10; i++) {
                            const cells = rows[i].querySelectorAll('td');
                            if (cells.length >= 4) {
                                const code = cells[0].textContent.trim();
                                if (code && code !== '證券代號') {
                                    data.push({
                                        rank: ++count,
                                        code,
                                        name: cells[1].textContent.trim(),
                                        shares: cells[2].textContent.trim().replace(/,/g, ''),
                                        amount: cells[3].textContent.trim().replace(/,/g, ''),
                                        weight: cells[4] ? cells[4].textContent.trim() : ''
                                    });
                                }
                            }
                        }
                        if (data.length > 0) return data;
                    }
                }
            }
            return null;
        }
    """)

    if not holdings:
        print("  錯誤：無法取得持股資料")
        return None

    return holdings


async def scrape_ezmoney(page):
    """爬取統一台股增長的前10大持股"""
    url = "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=49YTW"
    print(f"  正在載入: {url}")
    await page.goto(url, wait_until="networkidle", timeout=60000)

    # 等待持股表格出現
    try:
        await page.wait_for_selector("text=股票代號", timeout=30000)
    except Exception:
        print("  警告：等待超時，嘗試直接擷取資料")

    # 使用 JavaScript 從 DOM 中提取持股資料
    holdings = await page.evaluate("""
        () => {
            // 找到包含「股票代號」標題的表格
            const allTh = document.querySelectorAll('th, td');
            for (const th of allTh) {
                if (th.textContent.trim() === '股票代號') {
                    const table = th.closest('table');
                    if (table) {
                        const rows = table.querySelectorAll('tr');
                        const data = [];
                        let count = 0;
                        for (let i = 1; i < rows.length && count < 10; i++) {
                            const cells = rows[i].querySelectorAll('td');
                            if (cells.length >= 3) {
                                const code = cells[0].textContent.trim();
                                if (code && /^[0-9A-Z]/.test(code)) {
                                    data.push({
                                        rank: ++count,
                                        code,
                                        name: cells[1].textContent.trim(),
                                        shares: cells[2].textContent.trim().replace(/,/g, ''),
                                        weight: cells[3] ? cells[3].textContent.trim() : ''
                                    });
                                }
                            }
                        }
                        if (data.length > 0) return data;
                    }
                }
            }
            return null;
        }
    """)

    if not holdings:
        print("  錯誤：無法取得持股資料")
        return None

    return holdings


def load_previous_data(key):
    """載入前一天的資料（或最新一筆）"""
    files = sorted(DATA_DIR.glob(f"{key}_*.json"), reverse=True)
    if not files:
        return None, None
    latest_file = files[0]
    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data, latest_file.stem.split("_")[-1]  # 回傳資料和日期字串
    except Exception as e:
        print(f"  讀取舊資料失敗：{e}")
        return None, None


def save_data(key, date_str, holdings):
    """儲存今日資料"""
    filename = DATA_DIR / f"{key}_{date_str}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(holdings, f, ensure_ascii=False, indent=2)
    return filename


def compare_holdings(old_data, new_data):
    """比較新舊持股差異"""
    if not old_data or not new_data:
        return None

    old_map = {item["code"]: item for item in old_data}
    new_map = {item["code"]: item for item in new_data}

    old_codes = set(old_map.keys())
    new_codes = set(new_map.keys())

    added = new_codes - old_codes       # 新進入前10
    removed = old_codes - new_codes     # 離開前10
    changed = []                        # 排名或權重有變化的

    for code in new_codes & old_codes:
        old = old_map[code]
        new = new_map[code]
        rank_diff = new["rank"] - old["rank"]
        if rank_diff != 0 or new.get("weight") != old.get("weight"):
            changed.append({
                "code": code,
                "name": new["name"],
                "old_rank": old["rank"],
                "new_rank": new["rank"],
                "rank_diff": rank_diff,
                "old_weight": old.get("weight", ""),
                "new_weight": new.get("weight", ""),
            })

    return {
        "added": [new_map[c] for c in added],
        "removed": [old_map[c] for c in removed],
        "changed": sorted(changed, key=lambda x: x["new_rank"]),
    }


def format_holdings_table(holdings):
    """格式化持股表格輸出"""
    lines = []
    has_amount = any("amount" in h for h in holdings)

    if has_amount:
        header = f"  {'排名':>3}  {'代號':>6}  {'名稱':<12}  {'股數':>14}  {'金額':>18}  {'權重':>8}"
        separator = "  " + "-" * 70
    else:
        header = f"  {'排名':>3}  {'代號':>6}  {'名稱':<12}  {'股數':>14}  {'權重':>8}"
        separator = "  " + "-" * 55

    lines.append(header)
    lines.append(separator)

    for h in holdings:
        if has_amount:
            lines.append(
                f"  {h['rank']:>3}. {h['code']:>6}  {h['name']:<12}  "
                f"{h['shares']:>14}  {h.get('amount', ''):>18}  {h.get('weight', ''):>8}"
            )
        else:
            lines.append(
                f"  {h['rank']:>3}. {h['code']:>6}  {h['name']:<12}  "
                f"{h['shares']:>14}  {h.get('weight', ''):>8}"
            )

    return "\n".join(lines)


def format_diff_report(diff, fund_name, old_date, new_date):
    """格式化差異報告"""
    if not diff:
        return f"  (無前期資料可比較)"

    lines = []
    has_change = diff["added"] or diff["removed"] or diff["changed"]

    if not has_change:
        lines.append(f"  ✓ 與 {old_date} 相比，前10大持股無變動")
        return "\n".join(lines)

    lines.append(f"  ⚠ 與 {old_date} 相比，發現以下變動：")

    if diff["added"]:
        lines.append("")
        lines.append("  【新進入前10大】")
        for h in diff["added"]:
            lines.append(f"    + {h['code']} {h['name']}  (排名: #{h['rank']}, 權重: {h.get('weight', '')})")

    if diff["removed"]:
        lines.append("")
        lines.append("  【退出前10大】")
        for h in diff["removed"]:
            lines.append(f"    - {h['code']} {h['name']}  (原排名: #{h['rank']}, 原權重: {h.get('weight', '')})")

    if diff["changed"]:
        lines.append("")
        lines.append("  【排名/權重變動】")
        for c in diff["changed"]:
            rank_arrow = "↑" if c["rank_diff"] < 0 else "↓"
            rank_str = f"{rank_arrow}{abs(c['rank_diff'])}" if c["rank_diff"] != 0 else "→"
            weight_str = ""
            if c["old_weight"] != c["new_weight"]:
                weight_str = f"  {c['old_weight']} → {c['new_weight']}"
            lines.append(
                f"    {c['code']} {c['name']:<12} "
                f"排名: #{c['old_rank']} → #{c['new_rank']} ({rank_str}){weight_str}"
            )

    return "\n".join(lines)


async def main():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("錯誤：請先安裝 playwright")
        print("  pip install playwright")
        print("  playwright install chromium")
        sys.exit(1)

    today = datetime.now().strftime("%Y-%m-%d")
    print("=" * 70)
    print(f"  ETF 持股監控  |  {datetime.now().strftime('%Y/%m/%d %H:%M')}")
    print("=" * 70)

    all_results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for fund_name, config in SOURCES.items():
            print(f"\n【{fund_name}】")
            print(f"  資料來源: {config['url']}")

            try:
                page = await browser.new_page()
                await page.set_extra_http_headers({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                })

                if config["scraper"] == "fhtrust":
                    holdings = await scrape_fhtrust(page)
                else:
                    holdings = await scrape_ezmoney(page)

                await page.close()

                if not holdings:
                    print("  ✗ 資料擷取失敗")
                    continue

                # 顯示今日前10大持股
                print(f"\n  ── 前10大持股 ({today}) ──")
                print(format_holdings_table(holdings))

                # 讀取前期資料並比較
                old_data, old_date = load_previous_data(config["key"])

                # 如果今天已有資料，不重複儲存
                today_file = DATA_DIR / f"{config['key']}_{today}.json"
                if not today_file.exists():
                    save_file = save_data(config["key"], today, holdings)
                    print(f"\n  ✓ 資料已儲存: {save_file.name}")
                else:
                    print(f"\n  ✓ 今日資料已存在: {today_file.name}")

                # 比較差異
                if old_data and old_date and old_date != today:
                    diff = compare_holdings(old_data, holdings)
                    print(f"\n  ── 差異比較 ──")
                    print(format_diff_report(diff, fund_name, old_date, today))
                elif not old_data:
                    print(f"\n  (首次執行，無前期資料可比較)")

                all_results[fund_name] = holdings

            except Exception as e:
                print(f"  ✗ 錯誤: {e}")
                import traceback
                traceback.print_exc()

        await browser.close()

    print("\n" + "=" * 70)
    print(f"  完成  |  資料儲存於: {DATA_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
