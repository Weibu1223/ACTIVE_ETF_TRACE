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


def _load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_weight_value(weight_text):
    """把像 '5.34%' 的字串轉成 float(5.34)。"""
    if weight_text is None:
        return None
    s = str(weight_text).strip().replace("%", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def analyze_daily_weight_changes_last_5(config, threshold=1.0):
    """
    近五個交易日（近 5 筆資料）的「每日（日對日）」權重變動分析。
    規則：近 5 筆資料會形成 4 個區間（D1→D2、D2→D3、D3→D4、D4→D5），任一區間 abs(Δ) >= threshold 就列出。
    """
    files = sorted(DATA_DIR.glob(f"{config['key']}_*.json"), reverse=True)
    recent_files = list(reversed(files[:5]))  # 日期由舊到新
    if len(recent_files) < 2:
        return None

    # 預先載入每一天資料
    daily = []
    for f in recent_files:
        date = f.stem.split("_")[-1]
        data = _load_json(f)
        daily.append((date, {item["code"]: item for item in data}))

    # 收集：任一日對日區間達門檻就列出（同一檔股票可能出現多筆）
    events = []
    for i in range(len(daily) - 1):
        from_date, from_map = daily[i]
        to_date, to_map = daily[i + 1]

        for code in set(from_map.keys()) & set(to_map.keys()):
            old_item = from_map[code]
            new_item = to_map[code]
            old_weight = _parse_weight_value(old_item.get("weight", ""))
            new_weight = _parse_weight_value(new_item.get("weight", ""))
            if old_weight is None or new_weight is None:
                continue

            delta = new_weight - old_weight
            if abs(delta) < threshold:
                continue

            events.append({
                "code": code,
                "name": new_item.get("name", old_item.get("name", "")),
                "from_date": from_date,
                "to_date": to_date,
                "old_weight": old_weight,
                "new_weight": new_weight,
                "delta": delta,
                "old_rank": old_item.get("rank", ""),
                "new_rank": new_item.get("rank", ""),
            })

    events.sort(key=lambda x: (abs(x["delta"]), x["to_date"], x["code"]), reverse=True)
    return {
        "start_date": daily[0][0],
        "end_date": daily[-1][0],
        "days_count": len(daily),
        "items": events,
    }


def analyze_weight_change_vs_today_last_5(config, threshold=3.0):
    """
    近五個交易日（含今日）中，計算「今日權重 - 該日權重」的變化。
    僅列出 abs(delta) >= threshold 的標的（用於像：3/23 11%(+6%) 或 3/23 11%(-6%) 這種輸出）。
    """
    files = sorted(DATA_DIR.glob(f"{config['key']}_*.json"), reverse=True)
    recent_files = list(reversed(files[:5]))  # 日期由舊到新
    if len(recent_files) < 2:
        return None

    daily = []
    for f in recent_files:
        date = f.stem.split("_")[-1]
        data = _load_json(f)
        daily.append((date, {item["code"]: item for item in data}))

    today_date, today_map = daily[-1]

    # 先把今日可用的權重轉好，避免重複 parse
    today_weight_by_code = {}
    for code, item in today_map.items():
        w = _parse_weight_value(item.get("weight", ""))
        if w is not None:
            today_weight_by_code[code] = w

    results_by_code = {}
    for past_date, past_map in daily[:-1]:
        for code in set(past_map.keys()) & set(today_weight_by_code.keys()):
            past_item = past_map[code]
            past_weight = _parse_weight_value(past_item.get("weight", ""))
            if past_weight is None:
                continue
            delta = today_weight_by_code[code] - past_weight
            if abs(delta) < threshold:
                continue

            results_by_code.setdefault(code, []).append({
                "date": past_date,
                "past_weight": past_weight,
                "delta": delta,
                "past_rank": past_item.get("rank", ""),
            })

    # 組裝成便於 README 輸出的結構（每檔股票：依 delta 由大到小）
    items = []
    for code, entries in results_by_code.items():
        name = today_map.get(code, {}).get("name", "")
        today_rank = today_map.get(code, {}).get("rank", "")
        today_weight = today_weight_by_code.get(code)
        entries.sort(key=lambda x: (x["delta"], x["date"]), reverse=True)
        items.append({
            "code": code,
            "name": name,
            "today_date": today_date,
            "today_weight": today_weight,
            "today_rank": today_rank,
            "entries": entries,
        })

    items.sort(key=lambda x: max(e["delta"] for e in x["entries"]) if x["entries"] else 0, reverse=True)
    return {
        "start_date": daily[0][0],
        "end_date": today_date,
        "days_count": len(daily),
        "today_date": today_date,
        "items": items,
    }


def render_holdings_markdown(holdings):
    """把持股資料轉成 README 可直接渲染的 markdown 表格。"""
    if not holdings:
        return "_無資料_"

    has_amount = any("amount" in h for h in holdings)
    holdings = sorted(holdings, key=lambda x: x.get("rank", 0))

    if has_amount:
        header = "| 排名 | 代號 | 名稱 | 股數 | 金額 | 權重 |\n|---:|---:|:---|---:|---:|:---|"
        rows = [
            f"| {h['rank']} | {h['code']} | {h['name']} | {h.get('shares','')} | {h.get('amount','')} | {h.get('weight','')} |"
            for h in holdings
        ]
    else:
        header = "| 排名 | 代號 | 名稱 | 股數 | 權重 |\n|---:|---:|:---|---:|:---|"
        rows = [
            f"| {h['rank']} | {h['code']} | {h['name']} | {h.get('shares','')} | {h.get('weight','')} |"
            for h in holdings
        ]

    return header + "\n" + "\n".join(rows)


def render_diff_markdown(diff, old_date, new_date):
    """把差異結果轉成 README 可直接渲染的 markdown。"""
    if old_date is None:
        return f"_首次執行，無前期資料可比較（{new_date}）_"
    if old_date == new_date:
        return f"_已是同日資料（{new_date}），差異比較略過_"
    if not diff:
        return f"_無法比對（前期資料不足）_"

    has_change = diff["added"] or diff["removed"] or diff["changed"]
    if not has_change:
        return f"_與 {old_date} 相比，前10大持股無變動_"

    lines = [f"⚠ 與 {old_date} 相比（資料日期：{new_date}），發現以下變動："]

    if diff["added"]:
        lines.append("\n**新進入前10大**")
        lines.append("| 代號 | 名稱 | 新排名 | 權重 |")
        lines.append("|---:|:---|---:|:---|")
        for h in diff["added"]:
            lines.append(f"| {h['code']} | {h['name']} | {h['rank']} | {h.get('weight','')} |")

    if diff["removed"]:
        lines.append("\n**退出前10大**")
        lines.append("| 代號 | 名稱 | 舊排名 | 原權重 |")
        lines.append("|---:|:---|---:|:---|")
        for h in diff["removed"]:
            lines.append(f"| {h['code']} | {h['name']} | {h['rank']} | {h.get('weight','')} |")

    if diff["changed"]:
        lines.append("\n**排名/權重變動**")
        lines.append("| 代號 | 名稱 | 舊排名 | 新排名 | 變動 | 舊權重 | 新權重 |")
        lines.append("|---:|:---|---:|---:|:---|:---|:---|")
        for c in diff["changed"]:
            rank_diff = c["rank_diff"]
            rank_arrow = "↑" if rank_diff < 0 else "↓"
            rank_str = f"{rank_arrow}{abs(rank_diff)}" if rank_diff != 0 else "→"
            lines.append(
                f"| {c['code']} | {c['name']} | {c['old_rank']} | {c['new_rank']} | {rank_str} | {c.get('old_weight','')} | {c.get('new_weight','')} |"
            )

    return "\n".join(lines)


def write_readme(fund_data, data_date, updated_at):
    """輸出 README.md 給 GitHub repo 首頁直接展示。"""
    root_dir = Path(__file__).parent
    readme_path = root_dir / "README.md"

    lines = []
    lines.append("# ETF 持股監控（每日更新）")
    lines.append("")
    lines.append(f"- 資料日期：`{data_date}`")
    lines.append(f"- 最後更新：`{updated_at}`")
    lines.append("")
    lines.append("每天會抓取兩檔 ETF 前10大持股，並與前一次資料做差異比對。")
    lines.append("")

    for fund_name, config in SOURCES.items():
        if fund_name not in fund_data:
            continue

        holdings = fund_data[fund_name]["holdings"]
        diff = fund_data[fund_name]["diff"]
        old_date = fund_data[fund_name]["old_date"]

        lines.append(f"## {fund_name}")
        lines.append("")
        lines.append(f"- 資料來源：{config['url']}")
        lines.append("")
        lines.append("### 前10大持股")
        lines.append("")
        lines.append(render_holdings_markdown(holdings))
        lines.append("")
        lines.append("### 差異（相較上一筆）")
        lines.append("")
        lines.append(render_diff_markdown(diff, old_date, data_date))
        lines.append("")

    lines.append("## 近五個交易日每日權重變動（±1%以上）")
    lines.append("")
    lines.append("以下以近 5 筆資料形成的 4 個「日對日」區間計算：任一區間權重變動達到 ±1% 即列出。")
    lines.append("")

    for fund_name, config in SOURCES.items():
        analysis = analyze_daily_weight_changes_last_5(config, threshold=1.0)
        lines.append(f"### {fund_name}")
        lines.append("")
        if not analysis:
            lines.append("_資料不足（至少需要 2 天資料）_")
            lines.append("")
            continue

        lines.append(
            f"- 分析區間：`{analysis['start_date']}` → `{analysis['end_date']}`（共 `{analysis['days_count']}` 筆）"
        )
        lines.append("")

        if not analysis["items"]:
            lines.append("_無單日權重變動達到 ±1% 的標的_")
            lines.append("")
            continue

        lines.append("| 代號 | 名稱 | 區間 | 起始權重 | 最新權重 | 變動 | 起始排名 | 最新排名 |")
        lines.append("|---:|:---|:---|---:|---:|:---|---:|---:|")
        for item in analysis["items"]:
            sign = "+" if item["delta"] > 0 else ""
            lines.append(
                f"| {item['code']} | {item['name']} | {item['from_date']}→{item['to_date']} | {item['old_weight']:.2f}% | {item['new_weight']:.2f}% | {sign}{item['delta']:.2f}% | {item['old_rank']} | {item['new_rank']} |"
            )
        lines.append("")

    lines.append("## 近五日持有權重變化（以今日為基準）")
    lines.append("")
    lines.append("以下以「今日權重 - 該日權重」計算，僅列出變化達到 `±3%` 以上的日期。")
    lines.append("")

    for fund_name, config in SOURCES.items():
        analysis = analyze_weight_change_vs_today_last_5(config, threshold=3.0)
        lines.append(f"### {fund_name}")
        lines.append("")
        if not analysis:
            lines.append("_資料不足（至少需要 2 天資料）_")
            lines.append("")
            continue

        lines.append(
            f"- 分析區間：`{analysis['start_date']}` → `{analysis['end_date']}`（共 `{analysis['days_count']}` 筆）"
        )
        lines.append("")

        if not analysis["items"]:
            lines.append("_無符合條件的標的_")
            lines.append("")
            continue

        for item in analysis["items"]:
            lines.append(f"#### {item['code']} {item['name']}")
            lines.append("")
            if item.get("today_weight") is not None:
                lines.append(f"- 今日（`{item['today_date']}`）：{item['today_weight']:.2f}%（排名：{item.get('today_rank','')}）")
            lines.append("")
            for e in item["entries"]:
                sign = "+" if e["delta"] > 0 else ""
                lines.append(f"- `{e['date']}` {e['past_weight']:.2f}%（{sign}{e['delta']:.2f}%）")
            lines.append("")

    readme_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def generate_readme_from_latest():
    """不跑爬蟲、直接用已存在的 JSON 更新 README（用於快速檢查/補檔）。"""
    latest_fund_data = {}

    for fund_name, config in SOURCES.items():
        files = sorted(DATA_DIR.glob(f"{config['key']}_*.json"), reverse=True)
        if not files:
            continue

        latest_file = files[0]
        latest_holdings = _load_json(latest_file)
        latest_date = latest_file.stem.split("_")[-1]

        prev_holdings = None
        prev_date = None
        if len(files) > 1:
            prev_file = files[1]
            prev_holdings = _load_json(prev_file)
            prev_date = prev_file.stem.split("_")[-1]

        diff = compare_holdings(prev_holdings, latest_holdings) if prev_holdings and prev_date else None

        latest_fund_data[fund_name] = {
            "holdings": latest_holdings,
            "diff": diff,
            "old_date": prev_date,
        }

    # README 以「最新的檔案日期」呈現
    all_dates = []
    for fund_name, config in SOURCES.items():
        files = sorted(DATA_DIR.glob(f"{config['key']}_*.json"), reverse=True)
        if files:
            all_dates.append(files[0].stem.split("_")[-1])
    data_date = max(all_dates) if all_dates else datetime.now().strftime("%Y-%m-%d")
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    write_readme(latest_fund_data, data_date, updated_at)


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

    readme_fund_data = {}

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
                # 為了確保 README 與 repo 版本一致，改用實際儲存到檔案的資料
                saved_holdings = _load_json(today_file)

                diff = None
                if old_data and old_date and old_date != today:
                    diff = compare_holdings(old_data, saved_holdings)
                    print(f"\n  ── 差異比較 ──")
                    print(format_diff_report(diff, fund_name, old_date, today))
                elif not old_data:
                    print(f"\n  (首次執行，無前期資料可比較)")

                readme_fund_data[fund_name] = {
                    "holdings": saved_holdings,
                    "diff": diff,
                    "old_date": old_date,
                }

            except Exception as e:
                print(f"  ✗ 錯誤: {e}")
                import traceback
                traceback.print_exc()

        await browser.close()

    # 更新 README，讓 GitHub repo 首頁可以直接顯示最新結果
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        write_readme(readme_fund_data, today, updated_at)
        print(f"  ✓ README.md 已更新（{today}）")
    except Exception as e:
        print(f"  ✗ 更新 README.md 失敗: {e}")

    print("\n" + "=" * 70)
    print(f"  完成  |  資料儲存於: {DATA_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--generate-readme-only":
        generate_readme_from_latest()
    else:
        asyncio.run(main())
