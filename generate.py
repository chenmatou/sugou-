# generate.py  (按你本次口径：更新渠道/仓库/启用状态/燃油85折/住宅费/签名费；取消FedEx-YSD；USPS不算旺季)
import pandas as pd
import json
import re
import os
import warnings
from datetime import datetime
from urllib.request import urlopen, Request
import subprocess
import tempfile
import shutil

warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# ==========================================
# 1. 全局配置
# ==========================================
DATA_DIR = "data"
OUTPUT_DIR = "public"

TIER_FILES = {"T0": "T0.xlsx", "T1": "T1.xlsx", "T2": "T2.xlsx", "T3": "T3.xlsx"}

# =========================
# 1.1 仓库清单（写死在前端下拉）
# - value 使用“邮编(5位)”字符串
# - region 用于 FedEx Zone 归类（WEST/CENTRAL/EAST）
# - 退货仓（63461）暂不计算（按你口径：等你拿到数据）
# =========================
WAREHOUSES = [
    {"code": "60632", "label": "SureGo美中芝加哥-60632仓", "region": "CENTRAL", "calc_enabled": True},
    {"code": "91730", "label": "SureGo美西库卡蒙格-91730新仓", "region": "WEST", "calc_enabled": True},
    {"code": "91752", "label": "SureGo美西米拉罗马-91752仓", "region": "WEST", "calc_enabled": True},
    {"code": "08691", "label": "SureGo美东新泽西-08691仓", "region": "EAST", "calc_enabled": True},
    {"code": "06801", "label": "SureGo美东贝塞尔-06801仓", "region": "EAST", "calc_enabled": True},
    {"code": "11791", "label": "SureGo美东长岛-11791仓", "region": "EAST", "calc_enabled": True},
    {"code": "07032", "label": "SureGo美东新泽西-07032仓", "region": "EAST", "calc_enabled": True},
    {"code": "63461", "label": "SureGo退货检测-美中密苏里63461退货仓", "region": "CENTRAL", "calc_enabled": False},
]

WEST_CODES = ["91730", "91752"]
CENTRAL_CODES = ["60632"]  # 63461 为退货仓暂不计算
EAST_CODES = ["08691", "06801", "11791", "07032"]

# =========================
# 1.2 渠道清单（启用/取消口径）
# - 取消：FedEx-YSD-报价（本次口径明确取消）
# - 合并：GOFO-MT 与 UNIUNI-MT（显示名：GOFO-MT（合并UNIUNI））
# - 新增/调整：FedEx-MT-超大包裹、FedEx-MT-危险品、GOFO大件-MT
# =========================
CHANNELS_ENABLED = [
    "GOFO-报价",
    "GOFO-MT（合并UNIUNI）",
    "USPS-YSD-报价",
    "FedEx-MT-超大包裹-报价",
    "FedEx-ECO-MT报价",          # 显示为 FedEx-Economy（前端文案已改）
    "FedEx-MT-危险品-报价",
    "FedEx-632-MT-报价",
    "GOFO大件-MT-报价",
    "XLmiles-报价",
]

# 渠道 Sheet 匹配关键词（关键词包含匹配；避免依赖“猜名字”，但仍按你给的命名稳定定位）
CHANNEL_KEYWORDS = {
    "GOFO-报价": ["GOFO", "报价"],
    "GOFO-MT（合并UNIUNI）": ["GOFO", "UNIUNI", "MT", "报价"],  # sheet 名：GOFO、UNIUNI-MT-报价（包含 GOFO/UNIUNI/MT/报价）
    "USPS-YSD-报价": ["USPS"],
    "FedEx-ECO-MT报价": ["ECO", "MT"],

    "FedEx-632-MT-报价": ["632"],
    "FedEx-MT-危险品-报价": ["FedEx", "危险品"],
    "FedEx-MT-超大包裹-报价": ["FedEx", "MT", "超大"],        # 兼容包含“超大包裹/Oversize”
    "GOFO大件-MT-报价": ["GOFO", "大件", "MT"],

    "XLmiles-报价": ["XLmiles"],
}

# ==========================================
# 1.3 邮编库配置：GOFO 邮编区（保持独立）
# - 你本次口径：合并 GOFO-MT 和 UNIUNI-MT，所以 ZIP_COL_MAP 只保留一个“合并渠道”映射
# - 取消：FedEx-YSD
# ==========================================
ZIP_DB_SHEET_KEY = "GOFO-报价"
ZIP_COL_MAP = {
    "GOFO-报价": 5,
    "GOFO-MT（合并UNIUNI）": 6,      # 取原 GOFO-MT 列（你若后续确认合并列位置，我再按新列改）
    "USPS-YSD-报价": 8,
    "FedEx-ECO-MT报价": 9,
    "XLmiles-报价": 10,
    "GOFO大件-MT-报价": 11,
    "FedEx-632-MT-报价": 12,
    # "FedEx-YSD-报价": 13,  # 本次口径取消
}

# 旧全局附加费保留（但住宅/签名/旺季/燃油按渠道逻辑覆盖）
GLOBAL_SURCHARGES = {
    "fuel": 0.16,
    "res_fee": 3.50,
    "peak_res": 1.32,
    "peak_oversize": 54,
    "peak_unauthorized": 220,
    "oversize_fee": 130,
    "ahs_fee": 20,
    "unauthorized_fee": 1150
}

US_STATES_CN = {
    'AL': '阿拉巴马', 'AK': '阿拉斯加', 'AZ': '亚利桑那', 'AR': '阿肯色', 'CA': '加利福尼亚',
    'CO': '科罗拉多', 'CT': '康涅狄格', 'DE': '特拉华', 'FL': '佛罗里达', 'GA': '佐治亚',
    'HI': '夏威夷', 'ID': '爱达荷', 'IL': '伊利诺伊', 'IN': '印第安纳', 'IA': '爱荷华',
    'KS': '堪萨斯', 'KY': '肯塔基', 'LA': '路易斯安那', 'ME': '缅因', 'MD': '马里兰',
    'MA': '马萨诸塞', 'MI': '密歇根', 'MN': '明尼苏达', 'MS': '密西西比', 'MO': '密苏里',
    'MT': '蒙大拿', 'NE': '内布拉斯加', 'NV': '内华达', 'NH': '新罕布什尔', 'NJ': '新泽西',
    'NM': '新墨西哥', 'NY': '纽约', 'NC': '北卡罗来纳', 'ND': '北达科他', 'OH': '俄亥俄',
    'OK': '俄克拉荷马', 'OR': '俄勒冈', 'PA': '宾夕法尼亚', 'RI': '罗德岛', 'SC': '南卡罗来纳',
    'SD': '南达科他', 'TN': '田纳西', 'TX': '德克萨斯', 'UT': '犹他', 'VT': '佛蒙特',
    'VA': '弗吉尼亚', 'WA': '华盛顿', 'WV': '西弗吉尼亚', 'WI': '威斯康星', 'WY': '怀俄明',
    'DC': '华盛顿特区'
}

# ==========================================
# 1.5 FedEx 官网：住宅地址旺季附加费抓取（保留开关模块；USPS 旺季=本次口径完全不算）
# ==========================================
def fetch_fedex_residential_peak_table():
    """
    从 FedEx Demand Surcharges 页面解析：
    “FedEx Ground residential shipments and FedEx Home Delivery residential shipments”
    的三段固定每包金额（Oct.27–Jan.18 那段）。
    解析不到则 fallback（你可后续更新日期段）。
    """
    url = "https://www.fedex.com/en-us/shipping/rate-changes/demand-surcharges.html"
    fallback = {
        "type": "fixed_by_date",
        "source": "fallback",
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "periods": [
            {"start": "2025-10-27", "end": "2025-11-23", "amount": 0.40},
            {"start": "2025-11-24", "end": "2025-12-28", "amount": 0.65},
            {"start": "2025-12-29", "end": "2026-01-18", "amount": 0.40}
        ]
    }
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
        if "FedEx Ground residential shipments" not in html:
            return fallback

        idx = html.find("FedEx Ground residential shipments")
        snippet = html[idx: idx + 5000]

        amts = re.findall(r"\$([0-9]+\.[0-9]{2})", snippet)
        small = []
        for a in amts:
            v = float(a)
            if v < 5:
                small.append(v)
            if len(small) >= 3:
                break
        if len(small) < 3:
            return fallback

        return {
            "type": "fixed_by_date",
            "source": url,
            "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "periods": [
                {"start": "2025-10-27", "end": "2025-11-23", "amount": float(small[0])},
                {"start": "2025-11-24", "end": "2025-12-28", "amount": float(small[1])},
                {"start": "2025-12-29", "end": "2026-01-18", "amount": float(small[2])}
            ]
        }
    except:
        return fallback

# ==========================================
# 1.6 FedEx DAS：PDF ZIP 集合 + Excel 金额抽取并注入 JSON
# - ZIP 集合：data/fedex_das/*.pdf
# - 金额：每个渠道统一在同一个 sheet 的同一位置（G181~G186）
# - 本次口径：移除 FedEx-YSD；新增/覆盖 632/危险品/超大包裹/GOFO大件
# ==========================================
FEDEX_DAS_DIR = os.path.join(DATA_DIR, "fedex_das")
PDF_LIST = "FGE_DAS_Contiguous_Extended_Alaska_Hawaii_2025.pdf"
PDF_CHANGES = "FGE_DAS_Zip_Code_Changes_2025.pdf"

DAS_ROWS_1BASED = [181, 182, 183, 184, 185, 186]  # 1-based Excel row index
DAS_COL_G_0BASED = 6  # G 列

DAS_KEYS = [
    "das_res",         # 181
    "das_com",         # 182
    "das_ext_res",     # 183
    "das_ext_com",     # 184
    "das_remote_res",  # 185
    "das_remote_com"   # 186
]

DAS_CHANNELS = [
    "FedEx-632-MT-报价",
    "FedEx-MT-危险品-报价",
    "FedEx-MT-超大包裹-报价",
    "GOFO大件-MT-报价",
]

def money_to_float(x):
    s = str(x).strip()
    if s in ("", "nan", "NaN", "None", "#NA", "#N/A"):
        return 0.0
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except:
        return 0.0

def pdftotext_read(pdf_path):
    if not os.path.exists(pdf_path):
        return "", f"missing_pdf:{os.path.basename(pdf_path)}"
    if shutil.which("pdftotext") is None:
        return "", "pdftotext_not_found"
    try:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
            out_txt = tf.name
        subprocess.run(
            ["pdftotext", "-layout", pdf_path, out_txt],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        with open(out_txt, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        try:
            os.remove(out_txt)
        except:
            pass
        return txt, None
    except Exception as e:
        return "", f"pdftotext_failed:{type(e).__name__}"

def parse_das_zip_sets_from_text(txt):
    sets = {"contiguous": set(), "extended": set(), "remote": set(), "all_zips": set()}
    problems = []
    if not txt or len(txt.strip()) < 50:
        problems.append("pdf_text_empty_or_too_short")
        return sets, problems

    cur = None
    for line in txt.splitlines():
        u = line.upper()
        if "DELIVERY AREA SURCHARGE REMOTE" in u or re.search(r"\bREMOTE\b", u):
            cur = "remote"
        elif "DELIVERY AREA SURCHARGE EXTENDED" in u or re.search(r"\bEXTENDED\b", u):
            cur = "extended"
        elif "DELIVERY AREA SURCHARGE" in u and ("EXTENDED" not in u) and ("REMOTE" not in u):
            cur = "contiguous"

        zips = re.findall(r"\b(\d{5})\b", line)
        for z in zips:
            sets["all_zips"].add(z)
            if cur in ("contiguous", "extended", "remote"):
                sets[cur].add(z)

    if (len(sets["contiguous"]) + len(sets["extended"]) + len(sets["remote"])) == 0 and len(sets["all_zips"]) > 0:
        problems.append("bucket_headers_not_detected_only_all_zips_collected")

    return sets, problems

def parse_das_changes_from_text(txt):
    changes = {"add": set(), "remove": set()}
    problems = []
    if not txt or len(txt.strip()) < 50:
        problems.append("changes_pdf_text_empty_or_too_short")
        return changes, problems

    for line in txt.splitlines():
        u = line.upper()
        zips = set(re.findall(r"\b(\d{5})\b", line))
        if not zips:
            continue
        if "ADD" in u or "ADDED" in u:
            changes["add"].update(zips)
        elif "REMOVE" in u or "REMOVED" in u or "DELETE" in u or "DELETED" in u:
            changes["remove"].update(zips)

    if len(changes["add"]) == 0 and len(changes["remove"]) == 0:
        problems.append("no_add_remove_keywords_detected")

    return changes, problems

def build_fedex_das_zip_sets():
    audit = {"problems": [], "sources": {}}
    out = {
        "effective_from": "2025-06-02",
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sets": {"contiguous": [], "extended": [], "remote": []},
        "changes": {"add": [], "remove": []},
        "audit": audit
    }

    list_pdf = os.path.join(FEDEX_DAS_DIR, PDF_LIST)
    chg_pdf = os.path.join(FEDEX_DAS_DIR, PDF_CHANGES)

    txt1, err1 = pdftotext_read(list_pdf)
    audit["sources"]["list_pdf"] = os.path.basename(list_pdf)
    if err1:
        audit["problems"].append(err1)
        return out

    sets, p1 = parse_das_zip_sets_from_text(txt1)
    audit["problems"].extend(p1)

    txt2, err2 = pdftotext_read(chg_pdf)
    audit["sources"]["changes_pdf"] = os.path.basename(chg_pdf)
    if err2:
        audit["problems"].append(err2)
        out["sets"]["contiguous"] = sorted(list(sets["contiguous"]))
        out["sets"]["extended"] = sorted(list(sets["extended"]))
        out["sets"]["remote"] = sorted(list(sets["remote"]))
        return out

    changes, p2 = parse_das_changes_from_text(txt2)
    audit["problems"].extend(p2)

    union = set(sets["contiguous"]) | set(sets["extended"]) | set(sets["remote"])
    union |= changes["add"]
    union -= changes["remove"]

    if "bucket_headers_not_detected_only_all_zips_collected" in audit["problems"]:
        sets["contiguous"] = union
        sets["extended"] = set()
        sets["remote"] = set()
    else:
        for k in ("contiguous", "extended", "remote"):
            sets[k] |= changes["add"]
            sets[k] -= changes["remove"]

    out["sets"]["contiguous"] = sorted(list(sets["contiguous"]))
    out["sets"]["extended"] = sorted(list(sets["extended"]))
    out["sets"]["remote"] = sorted(list(sets["remote"]))
    out["changes"]["add"] = sorted(list(changes["add"]))
    out["changes"]["remove"] = sorted(list(changes["remove"]))
    return out

def safe_float(val):
    try:
        if pd.isna(val) or val == "" or str(val).strip().lower() == "nan":
            return 0.0
        return float(str(val).replace('$', '').replace(',', '').strip())
    except:
        return 0.0

def get_sheet_by_name(excel_file, target_keys):
    try:
        xl = pd.ExcelFile(excel_file, engine='openpyxl')
        for sheet in xl.sheet_names:
            s_name = sheet.upper().replace(" ", "")
            if all(k.upper().replace(" ", "") in s_name for k in target_keys):
                print(f"    > 匹配Sheet: {sheet}")
                return pd.read_excel(xl, sheet_name=sheet, header=None)
        return None
    except Exception as e:
        print(f"    > 读取失败: {e}")
        return None

def extract_das_fees_from_channel_sheet(df):
    fees = {}
    for i, r1 in enumerate(DAS_ROWS_1BASED):
        r0 = r1 - 1
        key = DAS_KEYS[i]
        try:
            v = df.iloc[r0, DAS_COL_G_0BASED]
        except:
            v = 0
        fees[key] = money_to_float(v)
    return fees

def load_das_fees_all_tiers():
    print("\n--- 1.3 抽取 DAS 金额（G181~G186 自动抽取） ---")
    all_fees = {}
    for t_name, f_name in TIER_FILES.items():
        path = os.path.join(DATA_DIR, f_name)
        if not os.path.exists(path):
            continue
        all_fees[t_name] = {}
        for ch in DAS_CHANNELS:
            kws = CHANNEL_KEYWORDS.get(ch, [])
            df = get_sheet_by_name(path, kws) if kws else None
            if df is None:
                all_fees[t_name][ch] = {k: 0.0 for k in DAS_KEYS}
                print(f"    > {t_name}/{ch}: sheet_not_found -> all_zero")
                continue
            fees = extract_das_fees_from_channel_sheet(df)
            all_fees[t_name][ch] = fees
            print(f"    > {t_name}/{ch}: {fees}")
    return all_fees

def load_zip_db():
    print("--- 1. 加载邮编库（GOFO独立邮编区） ---")
    path = os.path.join(DATA_DIR, TIER_FILES['T0'])
    if not os.path.exists(path):
        return {}

    df = get_sheet_by_name(path, ["GOFO", "报价"])
    if df is None:
        return {}

    db = {}
    try:
        start = 0
        for i in range(100):
            cell = str(df.iloc[i, 1]).strip()
            if cell.isdigit() and len(cell) == 5:
                start = i
                break
        df = df.fillna("")
        for idx, row in df.iloc[start:].iterrows():
            z = str(row[1]).strip().zfill(5)
            if z.isdigit() and len(z) == 5:
                zones = {}
                for k, v in ZIP_COL_MAP.items():
                    val = str(row[v]).strip()
                    if val in ['-', 'nan', '', '0', 0]:
                        zones[k] = None
                    else:
                        zones[k] = val
                sb = str(row[3]).strip().upper()
                db[z] = {
                    "s": sb,
                    "sn": US_STATES_CN.get(sb, ''),
                    "c": str(row[4]).strip(),
                    "r": str(row[2]).strip(),
                    "z": zones
                }
    except:
        pass
    print(f"✅ 邮编库: {len(db)} 条")
    return db

def to_lb(val):
    s = str(val).upper().strip()
    if pd.isna(val) or s == 'NAN' or s == '':
        return None
    nums = re.findall(r"[\d\.]+", s)
    if not nums:
        return None
    n = float(nums[0])
    if 'OZ' in s:
        return n / 16.0
    if 'KG' in s:
        return n / 0.453592
    return n

def load_tiers():
    print("\n--- 2. 加载报价表 (中文兼容版) ---")
    all_tiers = {}

    for t_name, f_name in TIER_FILES.items():
        print(f"处理 {t_name}...")
        path = os.path.join(DATA_DIR, f_name)
        if not os.path.exists(path):
            continue

        t_data = {}
        for ch_key in CHANNELS_ENABLED:
            keywords = CHANNEL_KEYWORDS.get(ch_key, [])
            if not keywords:
                continue
            df = get_sheet_by_name(path, keywords)
            if df is None:
                continue

            try:
                h_row = 0
                for i in range(50):
                    row_str = " ".join(df.iloc[i].astype(str).values).lower()
                    has_zone = ("zone" in row_str or "分区" in row_str)
                    has_weight = ("weight" in row_str or "lb" in row_str or "重量" in row_str)
                    if has_zone and has_weight:
                        h_row = i
                        break

                headers = df.iloc[h_row].astype(str).str.lower().tolist()
                w_idx = -1
                z_map = {}

                for i, v in enumerate(headers):
                    if ('weight' in v or 'lb' in v or '重量' in v) and w_idx == -1:
                        w_idx = i
                    m = re.search(r'(?:zone|分区)\s*~?\s*(\d+)', v)
                    if m:
                        zn = m.group(1)
                        if zn not in z_map:
                            z_map[zn] = i

                if w_idx == -1:
                    continue

                prices = []
                for i in range(h_row + 1, len(df)):
                    row = df.iloc[i]
                    try:
                        lb = to_lb(row[w_idx])
                        if lb is None:
                            continue
                        item = {'w': lb}
                        for z, col in z_map.items():
                            clean_p = safe_float(row[col])
                            if clean_p > 0:
                                item[z] = clean_p
                        if len(item) > 1:
                            prices.append(item)
                    except:
                        continue

                prices.sort(key=lambda x: x['w'])
                t_data[ch_key] = {"prices": prices}

                # === 保留日志 ===
                print(f"    > {t_name}/{ch_key}: zones={list(z_map.keys())}, prices={len(prices)}")

            except:
                pass

        all_tiers[t_name] = t_data

    return all_tiers

# ==========================================
# 2. 网页模板（按本次口径改仓库/渠道/费用/燃油85折/取消FedEx-YSD/USPS不算旺季）
# ==========================================
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>业务员报价助手 (Ultimate V9 - 中文兼容版)</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    :root { --primary-color: #0d6efd; --header-bg: #000; }
    body { font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; background-color: #f4f6f9; min-height: 100vh; display: flex; flex-direction: column; }
    header { background-color: var(--header-bg); color: #fff; padding: 15px 0; border-bottom: 3px solid #333; }
    footer { background-color: var(--header-bg); color: #aaa; padding: 20px 0; margin-top: auto; text-align: center; font-size: 0.85rem; }
    .card { border: none; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 20px; }
    .card-header { background-color: #212529; color: #fff; font-weight: 600; padding: 10px 20px; border-radius: 8px 8px 0 0 !important; }
    .form-label { font-weight: 600; font-size: 0.85rem; color: #555; margin-bottom: 4px; }
    .input-group-text { font-size: 0.85rem; font-weight: 600; background-color: #e9ecef; }
    .form-control, .form-select { font-size: 0.9rem; }
    .status-table { width: 100%; font-size: 0.85rem; }
    .status-table td { padding: 6px; border-bottom: 1px solid #eee; vertical-align: middle; }
    .indicator { display: inline-block; padding: 2px 8px; border-radius: 4px; color: #fff; font-weight: bold; font-size: 0.75rem; }
    .bg-ok { background-color: #198754; } .bg-warn { background-color: #ffc107; color:#000; } .bg-err { background-color: #dc3545; }
    .result-table th { background-color: #212529; color: #fff; text-align: center; font-size: 0.85rem; vertical-align: middle; }
    .result-table td { text-align: center; vertical-align: middle; font-size: 0.9rem; }
    .price-text { font-weight: 800; font-size: 1.1rem; color: #0d6efd; }
    .fuel-link { font-size: 0.75rem; text-decoration: none; color: #0d6efd; display: block; margin-top: 3px; }
    #globalError { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); z-index: 9999; width: 80%; display: none; }
    .note-box{background:#fff; border:1px solid #e5e5e5; border-radius:8px; padding:10px;}
    .mono{font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;}
  </style>
</head>
<body>

<div id="globalError" class="alert alert-danger shadow-lg">
  <h5 class="alert-heading">⚠️ 系统运行错误</h5>
  <p id="errorMsg">未知错误</p>
</div>

<header>
  <div class="container d-flex justify-content-between align-items-center">
    <div><h5 class="m-0 fw-bold">📦 业务员报价助手</h5><small class="opacity-75">T0-T3 专家版 (V9.2-渠道更新版)</small></div>
    <div class="text-end text-white small">Multi-Channel Quote</div>
  </div>
</header>

<div class="container my-4">
  <div class="row g-4">
    <div class="col-lg-4">
      <div class="card h-100">
        <div class="card-header">1. 基础信息录入</div>
        <div class="card-body">
          <form id="calcForm">

            <div class="mb-3">
              <label class="form-label">发货仓库 (影响 FedEx Zone)</label>
              <select class="form-select" id="warehouse"></select>
              <div class="small text-muted mt-1">选仓后仅显示可用渠道；FedEx 标准渠道 Zone=仓库起始邮编(前三位)+目的地邮编(前三位)计算。</div>
              <div id="whWarn" class="small text-danger fw-bold mt-1" style="display:none;"></div>
            </div>

            <div class="bg-light p-2 rounded border mb-3">
              <div class="fw-bold small mb-2 border-bottom">⛽ 燃油费率 (Fuel Surcharge)</div>
              <div class="small text-danger fw-bold mb-2">
                仅：FedEx-632 / FedEx-MT-超大包裹 / FedEx-Economy / FedEx-MT-危险品<br>
                其中：<b>燃油85折</b>：FedEx-632、FedEx-MT-超大包裹；FedEx-Economy 仅美西仓85折
              </div>
              <div class="row g-2">
                <div class="col-12">
                  <label class="form-label small">FedEx Fuel (%)</label>
                  <input type="number" class="form-control form-control-sm" id="fedexFuel" value="16.0">
                  <a href="https://www.fedex.com/en-us/shipping/fuel-surcharge.html" target="_blank" class="fuel-link">🔗 FedEx燃油官网</a>
                </div>
              </div>
            </div>

            <div class="mb-3">
              <label class="form-label">客户等级 (切换自动计算)</label>
              <div class="btn-group w-100" role="group">
                <input type="radio" class="btn-check" name="tier" id="t0" value="T0"><label class="btn btn-outline-secondary" for="t0">T0</label>
                <input type="radio" class="btn-check" name="tier" id="t1" value="T1"><label class="btn btn-outline-secondary" for="t1">T1</label>
                <input type="radio" class="btn-check" name="tier" id="t2" value="T2"><label class="btn btn-outline-secondary" for="t2">T2</label>
                <input type="radio" class="btn-check" name="tier" id="t3" value="T3" checked><label class="btn btn-outline-secondary" for="t3">T3</label>
              </div>
            </div>

            <div class="mb-3">
              <label class="form-label">目的地邮编 (Zip)</label>
              <div class="input-group">
                <input type="text" class="form-control" id="zipCode" placeholder="5位邮编">
                <button class="btn btn-dark" type="button" id="btnLookup">查询</button>
              </div>
              <div id="locInfo" class="mt-1 small fw-bold text-muted ps-1">请输入邮编查询...</div>
              <div id="zoneInfo" class="mt-1 small text-muted ps-1"></div>
              <div id="dasInfo" class="mt-1 small text-muted ps-1"></div>
            </div>

            <div class="row g-2 mb-3">
              <div class="col-7">
                <label class="form-label">地址类型</label>
                <select class="form-select" id="addressType">
                  <option value="res">🏠 住宅 (Residential)</option>
                  <option value="com">🏢 商业 (Commercial)</option>
                </select>
              </div>
              <div class="col-5 pt-4">
                <div class="form-check form-switch">
                  <input class="form-check-input" type="checkbox" id="peakToggle">
                  <label class="form-check-label small fw-bold" for="peakToggle">旺季附加费</label>
                </div>
              </div>
            </div>

            <div class="mb-3">
              <div class="form-check">
                <input class="form-check-input" type="checkbox" id="sigToggle">
                <label class="form-check-label fw-bold">签名签收 (Signature)</label>
              </div>
              <div class="small text-muted">仅：XLmiles / FedEx-632 / FedEx-MT-危险品 / FedEx-MT-超大包裹</div>
            </div>

            <hr>

            <div class="mb-3">
              <label class="form-label">包裹规格</label>
              <div class="row g-2">
                <div class="col-4"><div class="input-group input-group-sm"><span class="input-group-text">长</span><input type="number" class="form-control" id="length" placeholder="L"></div></div>
                <div class="col-4"><div class="input-group input-group-sm"><span class="input-group-text">宽</span><input type="number" class="form-control" id="width" placeholder="W"></div></div>
                <div class="col-4"><div class="input-group input-group-sm"><span class="input-group-text">高</span><input type="number" class="form-control" id="height" placeholder="H"></div></div>
                <div class="col-12"><select class="form-select form-select-sm" id="dimUnit"><option value="in">IN (英寸)</option><option value="cm">CM (厘米)</option><option value="mm">MM (毫米)</option></select></div>
              </div>
              <div class="row g-2 mt-2">
                <div class="col-8"><div class="input-group input-group-sm"><span class="input-group-text">重量</span><input type="number" class="form-control" id="weight" placeholder="实重"></div></div>
                <div class="col-4"><select class="form-select form-select-sm" id="weightUnit"><option value="lb">LB (磅)</option><option value="oz">OZ (盎司)</option><option value="kg">KG (千克)</option><option value="g">G (克)</option></select></div>
              </div>
            </div>

            <div class="bg-light p-2 rounded border mb-3">
              <div class="fw-bold small mb-2 border-bottom">🚦 各渠道合规性一览</div>
              <table class="status-table" id="checkTable">
                <tr><td class="text-muted">等待输入尺寸...</td></tr>
              </table>
            </div>

            <button type="button" class="btn btn-primary w-100 fw-bold" id="btnCalc">开始计算 (Calculate)</button>
          </form>
        </div>
      </div>
    </div>

    <div class="col-lg-8">
      <div class="card h-100">
        <div class="card-header d-flex justify-content-between">
          <span>📊 测算结果</span>
          <span id="tierBadge" class="badge bg-warning text-dark"></span>
        </div>
        <div class="card-body">
          <div class="alert alert-info py-2 small" id="pkgSummary">请在左侧输入数据...</div>

          <div class="note-box mb-3">
            <div class="fw-bold">旺季附加费说明（本次口径）</div>
            <div class="small mt-1" style="line-height:1.35">
              ① <b>USPS 旺季附加费</b>：本次口径为 <b>完全不计算</b>（你已取消 USPS 旺季栏目）。<br>
              ② <b>FedEx 住宅旺季附加费</b>：仅在你打开“旺季附加费”开关且地址为住宅时，对部分 FedEx 渠道叠加（按构建时自动抓取的 FedEx Demand Surcharges 页面）。<br>
              ③ 若派送后产生额外费用（复核尺寸不符/退货/其他附加费等），物流商向我司收取后我司将 <b>实报实销</b>。
            </div>
            <div class="small text-muted mt-2">
              FedEx “住宅地址旺季附加费”构建时自动更新：<span class="mono" id="fedexPeakMeta"></span><br>
              FedEx DAS（偏远/扩展/超偏远）ZIP 集合：<span class="mono" id="dasMeta"></span>
            </div>
          </div>

          <div class="table-responsive">
            <table class="table table-bordered table-hover result-table">
              <thead>
                <tr>
                  <th width="18%">渠道</th>
                  <th width="18%">仓库</th>
                  <th width="8%">分区</th>
                  <th width="10%">计费重<br>(LB)</th>
                  <th width="12%">基础运费</th>
                  <th width="22%">附加费明细</th>
                  <th width="12%">总费用</th>
                  <th width="18%">状态</th>
                </tr>
              </thead>
              <tbody id="resBody"></tbody>
            </table>
          </div>

          <div class="mt-2 text-muted small border-top pt-2">
            <strong>计费逻辑说明（本次口径）：</strong><br>
            1. <strong>燃油费</strong>：仅 FedEx-632 / FedEx-MT-超大包裹 / FedEx-Economy / FedEx-MT-危险品 额外计算；其余渠道报价已含燃油或不适用。<br>
            2. <strong>燃油85折</strong>：FedEx-632、FedEx-MT-超大包裹固定85折；FedEx-Economy 仅美西仓85折。<br>
            3. <strong>住宅费(仅住宅地址)</strong>：FedEx-632($2.61) / FedEx-MT-超大包裹($2.61) / FedEx-MT-危险品($3.32) / GOFO大件($2.93)。<br>
            4. <strong>签名费(开关控制)</strong>：XLmiles($10.20) / FedEx-632($4.37) / FedEx-MT-危险品($9.71) / FedEx-MT-超大包裹($4.37)。<br>
            5. <strong>FedEx 标准渠道 Zone</strong>：FedEx-632 / FedEx-Economy / FedEx-MT-危险品 / FedEx-MT-超大包裹 使用“仓库起始邮编前三位+目的地邮编前三位”计算。<br>
            6. <strong>FedEx DAS</strong>：若 ZIP 命中 DAS/Extended/Remote，对 632/危险品/超大包裹/GOFO大件 按地址类型叠加（金额从 Excel 的 G181~G186 抽取）。<br>
            7. <strong>XLmiles</strong>：单件按 AH/OS/OM 满足条件的“最高档”计费；“一票多件第二件半价”需输入多件数据才可计算，当前仅提示规则不参与计算。
          </div>

        </div>
      </div>
    </div>
  </div>
</div>

<footer><div class="container"><p>&copy; 2026 速狗海外仓 | Update: <span id="updateDate"></span></p></div></footer>

<script>
  window.onerror = function(msg, u, l) {
    document.getElementById('globalError').style.display='block';
    document.getElementById('errorMsg').innerText=`${msg} (Line ${l})`;
  };
</script>

<script>
  let DATA = {};
  try { DATA = __JSON_DATA__; } catch(e) { throw new Error("Data Init Failed"); }

  document.getElementById('updateDate').innerText = new Date().toLocaleDateString();

  // ========= 仓库下拉（写死）=========
  const WAREHOUSE_META = {
    "60632": {label:"SureGo美中芝加哥-60632仓", region:"CENTRAL", calc_enabled:true},
    "91730": {label:"SureGo美西库卡蒙格-91730新仓", region:"WEST", calc_enabled:true},
    "91752": {label:"SureGo美西米拉罗马-91752仓", region:"WEST", calc_enabled:true},
    "08691": {label:"SureGo美东新泽西-08691仓", region:"EAST", calc_enabled:true},
    "06801": {label:"SureGo美东贝塞尔-06801仓", region:"EAST", calc_enabled:true},
    "11791": {label:"SureGo美东长岛-11791仓", region:"EAST", calc_enabled:true},
    "07032": {label:"SureGo美东新泽西-07032仓", region:"EAST", calc_enabled:true},
    "63461": {label:"SureGo退货检测-美中密苏里63461退货仓", region:"CENTRAL", calc_enabled:false},
  };

  (function initWarehouses(){
    const sel = document.getElementById('warehouse');
    const order = ["91730","91752","60632","08691","06801","11791","07032","63461"];
    sel.innerHTML = order.map(c=>{
      const m = WAREHOUSE_META[c];
      return `<option value="${c}">${m.label}</option>`;
    }).join('');
  })();

  // 显示元信息
  (function(){
    let meta = DATA.fedex_res_peak || {};
    document.getElementById('fedexPeakMeta').innerText =
      `source=${meta.source || 'n/a'} | updated=${meta.updated_at || 'n/a'}`;

    let das = DATA.fedex_das || {};
    let audit = (das.audit && das.audit.problems) ? das.audit.problems.join("|") : "ok";
    document.getElementById('dasMeta').innerText =
      `effective_from=${das.effective_from || 'n/a'} | updated=${das.updated_at || 'n/a'} | audit=${audit}`;
  })();

  // 自动计算监听
  document.querySelectorAll('input[name="tier"]').forEach(r => r.addEventListener('change', () => document.getElementById('btnCalc').click()));
  document.getElementById('warehouse').addEventListener('change', () => document.getElementById('btnCalc').click());
  document.getElementById('addressType').addEventListener('change', () => document.getElementById('btnCalc').click());
  document.getElementById('peakToggle').addEventListener('change', () => document.getElementById('btnCalc').click());
  document.getElementById('sigToggle').addEventListener('change', () => document.getElementById('btnCalc').click());

  // ========= 渠道 ↔ 仓库可用映射（写死，选仓后不显示不可用渠道）=========
  const CHANNEL_WAREHOUSE_ALLOW = {
    "GOFO-报价": ["91730","91752","60632"],
    "GOFO-MT（合并UNIUNI）": ["91730","91752","60632"],
    "USPS-YSD-报价": ["91730","91752","60632"],

    "FedEx-632-MT-报价": ["91730","91752","60632","08691","06801","11791","07032"],
    "FedEx-MT-超大包裹-报价": ["91730","91752","60632","08691","06801","11791","07032"],
    "FedEx-ECO-MT报价": ["91730","91752","60632","08691","06801","11791","07032"],
    "FedEx-MT-危险品-报价": ["60632","08691","06801","11791","07032"],
    "GOFO大件-MT-报价": ["91730","91752","08691","06801","11791","07032"],
    "XLmiles-报价": ["91730"],
  };

  const CHANNEL_ORDER = Object.keys(CHANNEL_WAREHOUSE_ALLOW);

  // ========= FedEx Zone 计算（起始=仓库邮编前三位；地区归类沿用原分段，East 分支统一处理）=========
  function calculateZoneMath(destZip, originZip3) {
    if(!destZip || destZip.length < 3) return 8;
    let p = parseInt(destZip.substring(0,3), 10);
    if ((p >= 967 && p <= 969) || (p >= 995 && p <= 999) || destZip.startsWith('00')) return 9;

    let o = String(originZip3 || "088");
    if (o === '917') {
      if (p >= 900 && p <= 935) return 2;
      if (p >= 936 && p <= 961) return 3;
      if (p >= 890 && p <= 898) return 3;
      if (p >= 970 && p <= 994) return 4;
      if (p >= 840 && p <= 884) return 4;
      if (p >= 500 && p <= 799) return 6;
      if (p >= 0 && p <= 499) return 8;
    } else if (o === '606') {
      if (p >= 600 && p <= 629) return 2;
      if (p >= 460 && p <= 569) return 3;
      if (p >= 400 && p <= 459) return 4;
      if (p >= 700 && p <= 799) return 4;
      if (p >= 200 && p <= 399) return 5;
      if (p >= 800 && p <= 899) return 6;
      if (p >= 0 && p <= 199) return 7;
      if (p >= 900 && p <= 966) return 8;
    } else {
      // EAST：086/068/117/070 统一按原 East 分支
      if (p >= 70 && p <= 89) return 2;
      if (p >= 0 && p <= 69) return 3;
      if (p >= 150 && p <= 199) return 3;
      if (p >= 200 && p <= 299) return 4;
      if (p >= 400 && p <= 599) return 5;
      if (p >= 600 && p <= 799) return 7;
      if (p >= 800 && p <= 966) return 8;
    }
    return 8;
  }

  function isFedexStandardChannel(ch){
    return (ch.includes("FedEx-632") || ch.includes("FedEx-ECO-MT") || ch.includes("FedEx-MT-危险品") || ch.includes("FedEx-MT-超大包裹"));
  }

  // USPS block
  const USPS_BLOCK = ['006','007','008','009','090','091','092','093','094','095','096','097','098','099','340','962','963','964','965','966','967','968','969','995','996','997','998','999'];

  // XLmiles：仅支持 Z1-2 / Z3
  function xl_zone_group(z){
    if(z===1 || z===2) return "1-2";
    if(z===3) return "3";
    return null;
  }
  function xl_single_piece_base(pkg, xlZoneGroup){
    let dims = [pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
    let L = dims[0];
    let G = L + 2*(dims[1]+dims[2]);
    let zone = xlZoneGroup;

    let ah = null, os = null, om = null;

    if(L<=96 && G<=130){
      if(pkg.Wt<=90) ah = (zone==="1-2") ? 33 : 36;
      else if(pkg.Wt<=150) ah = (zone==="1-2") ? 52 : 56;
    }
    if(L<=108 && G<=165 && pkg.Wt<=150){
      os = (zone==="1-2") ? 65 : 69;
    }
    if(L<=144 && G<=225 && pkg.Wt<=200){
      om = (zone==="1-2") ? 104 : 117;
    }

    if(om!==null) return {ok:true, svc:"OM", base:om, msg:"OverMax Delivery"};
    if(os!==null) return {ok:true, svc:"OS", base:os, msg:"Oversize Delivery"};
    if(ah!==null) return {ok:true, svc:"AH", base:ah, msg:"Additional Handling Delivery"};
    return {ok:false, svc:null, base:0, msg:"超规不可发"};
  }

  function standardize(l, w, h, du, wt, wu) {
    let L=parseFloat(l)||0, W=parseFloat(w)||0, H=parseFloat(h)||0, Weight=parseFloat(wt)||0;
    if(du==='cm'){L/=2.54;W/=2.54;H/=2.54} else if(du==='mm'){L/=25.4;W/=25.4;H/=25.4}
    if(wu==='kg')Weight/=0.453592; else if(wu==='oz')Weight/=16; else if(wu==='g')Weight/=453.592;
    return {L,W,H,Wt:Weight};
  }

  // 合规性一览（含 XLmiles）
  function check(pkg) {
    let d=[pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
    let L=d[0], G=L+2*(d[1]+d[2]);
    let h = '';

    const row = (name, cond, text) => {
      let cls = cond ? 'bg-err' : 'bg-ok';
      let txt = cond ? text : '正常 (OK)';
      return `<tr><td>${name}</td><td class="text-end"><span class="indicator ${cls}"></span>${txt}</td></tr>`;
    };

    let uFail = (L>20 || (L+d[1]+d[2])>50 || pkg.Wt>20);
    h += row('UniUni(MT合并)', uFail, '限制(L>20/Wt>20)');

    let usFail = (pkg.Wt>70 || L>30 || (L+(d[1]+d[2])*2)>130);
    h += row('USPS', usFail, '限制(>70lb/130")');

    let fFail = (pkg.Wt>150 || L>108 || G>165);
    h += row('FedEx', fFail, '不可发(>150lb)');

    let gFail = (pkg.Wt>150);
    h += row('GOFO大件', gFail, '超限(>150lb)');

    let xlFail = (pkg.Wt>200 || L>144 || G>225);
    h += row('XLmiles', xlFail, '范围(<=200lb/144"/225")');

    document.getElementById('checkTable').innerHTML = h;
  }

  ['length','width','height','weight','dimUnit','weightUnit'].forEach(id=>{
    document.getElementById(id).addEventListener('input', ()=>{
      let p = standardize(
        document.getElementById('length').value, document.getElementById('width').value, document.getElementById('height').value,
        document.getElementById('dimUnit').value, document.getElementById('weight').value, document.getElementById('weightUnit').value
      );
      check(p);
    })
  });

  // 邮编查询：优先 GOFO 邮编库；否则 zippopotam.us
  let CUR_ZONES = {};
  let LAST_LOC = null;

  function das_bucket_of_zip(zip){
    let das = DATA.fedex_das;
    if(!das || !das.sets || !zip) return null;
    let z = String(zip);
    if(das.sets.remote && das.sets.remote.includes(z)) return "remote";
    if(das.sets.extended && das.sets.extended.includes(z)) return "extended";
    if(das.sets.contiguous && das.sets.contiguous.includes(z)) return "contiguous";
    return null;
  }

  async function lookupZip(zip){
    let d = document.getElementById('locInfo');
    let zinfo = document.getElementById('zoneInfo');
    let dinfo = document.getElementById('dasInfo');

    let whCode = document.getElementById('warehouse').value;
    let whZip3 = String(whCode).substring(0,3);

    CUR_ZONES = {};
    LAST_LOC = null;

    if(DATA.zip_db && DATA.zip_db[zip]){
      let i = DATA.zip_db[zip];
      d.innerHTML = `<span class='text-success'>✅ ${i.sn} ${i.s} - ${i.c} [${i.r}]</span>`;
      CUR_ZONES = i.z || {};
      LAST_LOC = {state:i.s, city:i.c};
    }else{
      d.innerHTML = `<span class='text-warning'>⚠️ GOFO邮编库无该邮编，改用公共库查询州/城市</span>`;
      try{
        let resp = await fetch(`https://api.zippopotam.us/us/${zip}`);
        if(resp.ok){
          let data = await resp.json();
          let place = (data.places && data.places[0]) ? data.places[0] : null;
          if(place){
            let city = place['place name'];
            let st = place['state abbreviation'];
            LAST_LOC = {state:st, city:city};
            d.innerHTML = `<span class='text-success'>✅ ${st} - ${city}</span>`;
          }
        }
      }catch(e){}
    }

    if(zip && zip.length>=3){
      let z = calculateZoneMath(zip, whZip3);
      zinfo.innerHTML = `FedEx Zone(按仓库计算): <b>Zone ${z}</b>`;
    }else{
      zinfo.innerHTML = '';
    }

    let b = das_bucket_of_zip(zip);
    if(b){
      dinfo.innerHTML = `FedEx DAS 命中：<b>${b.toUpperCase()}</b>`;
    }else{
      dinfo.innerHTML = `FedEx DAS：未命中`;
    }
  }

  document.getElementById('btnLookup').onclick = async () => {
    let zip = document.getElementById('zipCode').value.trim();
    if(zip.length!==5){ alert("请输入5位邮编"); return; }
    await lookupZip(zip);
  };

  // =========================
  // 规则：住宅费/签名费/燃油
  // =========================
  function round2(x){ return Math.round((parseFloat(x||0)+Number.EPSILON)*100)/100; }

  // 住宅费：按你给的精确数 -> 四舍五入到美分
  function getResFee(ch){
    if(ch.includes("FedEx-632")) return 2.61;                 // 2.607 -> 2.61
    if(ch.includes("FedEx-MT-超大包裹")) return 2.61;          // 2.607 -> 2.61
    if(ch.includes("FedEx-MT-危险品")) return 3.32;            // 3.324 -> 3.32
    if(ch.includes("GOFO大件")) return 2.93;                   // 2.929... -> 2.93
    return 0;
  }

  // 签名费：按你给的精确数 -> 四舍五入到美分
  function getSigFee(ch){
    if(ch.includes("XLmiles")) return 10.20;                   // 10.2 -> 10.20
    if(ch.includes("FedEx-632")) return 4.37;                  // 4.367 -> 4.37
    if(ch.includes("FedEx-MT-危险品")) return 9.71;             // 9.708 -> 9.71
    if(ch.includes("FedEx-MT-超大包裹")) return 4.37;           // 4.367 -> 4.37
    return 0;
  }

  // 燃油：仅 FedEx-632 / 超大包裹 / Economy / 危险品
  function hasFuel(ch){
    return (ch.includes("FedEx-632") || ch.includes("FedEx-MT-超大包裹") || ch.includes("FedEx-ECO-MT") || ch.includes("FedEx-MT-危险品"));
  }

  // 燃油折扣：85折逻辑（按你口径）
  function fuelDiscountFactor(ch, whCode){
    // 632、超大包裹：固定 0.85
    if(ch.includes("FedEx-632") || ch.includes("FedEx-MT-超大包裹")) return 0.85;

    // Economy：仅美西仓 0.85
    if(ch.includes("FedEx-ECO-MT")) {
      let w = String(whCode||"");
      if(w.startsWith("917")) return 0.85;
      return 1.0;
    }

    // 危险品：未说明折扣 -> 默认 1.0
    return 1.0;
  }

  function getFedexResPeakAmount(todayStr){
    let meta = DATA.fedex_res_peak;
    if(!meta || !meta.periods) return 0;
    let t = new Date(todayStr);
    for(let p of meta.periods){
      let s = new Date(p.start + "T00:00:00");
      let e = new Date(p.end + "T23:59:59");
      if(t>=s && t<=e) return parseFloat(p.amount)||0;
    }
    return 0;
  }

  function getDasFee(tier, ch, zip, isRes){
    let das = DATA.fedex_das;
    if(!das || !das.fees || !das.fees[tier] || !das.fees[tier][ch]) return 0;
    let bucket = das_bucket_of_zip(zip);
    if(!bucket) return 0;
    let m = das.fees[tier][ch];
    if(bucket==="remote"){
      return isRes ? (m.das_remote_res||0) : (m.das_remote_com||0);
    }
    if(bucket==="extended"){
      return isRes ? (m.das_ext_res||0) : (m.das_ext_com||0);
    }
    return isRes ? (m.das_res||0) : (m.das_com||0);
  }

  // 计费重除数
  function getDivisor(ch, vol){
    let u = ch.toUpperCase();
    if(u.includes('UNIUNI')) return 0;
    if(u.includes('USPS')) return vol > 1728 ? 166 : 0;
    if(u.includes('ECO-MT')) return vol < 1728 ? 400 : 250;
    return 222;
  }

  // 计算按钮
  document.getElementById('btnCalc').onclick = async () => {
    let zip = document.getElementById('zipCode').value.trim();
    if(zip && zip.length===5 && (!LAST_LOC && (!CUR_ZONES || Object.keys(CUR_ZONES).length===0))){
      await lookupZip(zip);
    }

    let tier = document.querySelector('input[name="tier"]:checked').value;

    let whCode = document.getElementById('warehouse').value;
    let whMeta = WAREHOUSE_META[whCode] || {label:whCode, calc_enabled:true};
    let whLabel = whMeta.label;

    // 退货仓：暂不计算（按你口径）
    let warn = document.getElementById('whWarn');
    if(whMeta.calc_enabled===false){
      warn.style.display = 'block';
      warn.innerText = '退货仓暂不计费（等你拿到退货仓报价数据后再接入）';
    }else{
      warn.style.display = 'none';
      warn.innerText = '';
    }

    let pkg = standardize(
      document.getElementById('length').value, document.getElementById('width').value, document.getElementById('height').value,
      document.getElementById('dimUnit').value, document.getElementById('weight').value, document.getElementById('weightUnit').value
    );

    let isPeak = document.getElementById('peakToggle').checked;
    let isRes = document.getElementById('addressType').value === 'res';
    let sigOn = document.getElementById('sigToggle').checked;

    let fedexFuel = parseFloat(document.getElementById('fedexFuel').value)/100;

    document.getElementById('tierBadge').innerText = tier;

    let dims = [pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
    let L=dims[0], G=L+2*(dims[1]+dims[2]);
    document.getElementById('pkgSummary').innerHTML =
      `<b>基准:</b> ${dims[0].toFixed(1)}"${dims[1].toFixed(1)}"${dims[2].toFixed(1)}" | 实重:${pkg.Wt.toFixed(2)}lb | 围长:${G.toFixed(1)}"`;

    let tbody = document.getElementById('resBody');
    tbody.innerHTML='';

    if(!DATA.tiers || !DATA.tiers[tier]) {
      tbody.innerHTML='<tr><td colspan="8" class="text-danger">❌ 等级数据缺失</td></tr>';
      return;
    }

    let whZip3 = String(whCode).substring(0,3);
    let fedexZone = (zip && zip.length>=3) ? calculateZoneMath(zip, whZip3) : null;

    // 若仓库不计费，直接提示
    if(whMeta.calc_enabled===false){
      tbody.innerHTML = `<tr class="table-light"><td colspan="8" class="text-muted fw-bold">该仓库暂不计费（退货仓报价未接入）</td></tr>`;
      return;
    }

    CHANNEL_ORDER.forEach(ch => {
      let allow = CHANNEL_WAREHOUSE_ALLOW[ch] || [];
      if(!allow.includes(whCode)) return;

      let prices = (DATA.tiers[tier][ch] && DATA.tiers[tier][ch].prices) ? DATA.tiers[tier][ch].prices : [];

      let zoneVal = "-";
      if(isFedexStandardChannel(ch)){
        zoneVal = fedexZone ? String(fedexZone) : "-";
      }else{
        zoneVal = (CUR_ZONES && CUR_ZONES[ch]) ? String(CUR_ZONES[ch]) : "-";
      }

      let base = 0;
      let st = "正常";
      let cls = "text-success";
      let bg = "";
      let details = [];

      // 计费重
      let cWt = pkg.Wt;
      let div = getDivisor(ch, pkg.L*pkg.W*pkg.H);
      if(div > 0) {
        let vWt = (pkg.L*pkg.W*pkg.H)/div;
        cWt = Math.max(pkg.Wt, vWt);
      }
      if(!ch.includes('GOFO-报价') && cWt>1) cWt = Math.ceil(cWt);

      // ===== XLmiles：规则计费（单件最高档）=====
      if(ch.includes("XLmiles")){
        if(!fedexZone){
          st="无分区/超重"; cls="text-muted"; bg="table-light";
        }else{
          let xg = xl_zone_group(fedexZone);
          if(!xg){
            st="仓库/Zone不支持"; cls="text-muted"; bg="table-light";
          }else{
            zoneVal = "Z" + xg;
            let r = xl_single_piece_base(pkg, xg);
            if(!r.ok){
              st=r.msg; cls="text-danger fw-bold"; bg="table-danger";
              base=0;
            }else{
              base=r.base;
              details.push(`一口价: ${r.svc} ($${base.toFixed(2)})`);
              details.push(`包含: 保价/预约/签收证明等服务`);
              details.push(`一票多件: 第二件起半价(需录入多件才可算)`);
            }
          }
        }

        if(base>0 && sigOn){
          let sf = getSigFee(ch);
          if(sf>0){ details.push(`签名:$${sf.toFixed(2)}`); base += sf; }
        }

        let tot = base;
        tbody.innerHTML += `<tr class="${bg}">
          <td class="fw-bold text-start text-nowrap">${ch}</td>
          <td class="text-nowrap">${whLabel}</td>
          <td>${zoneVal}</td>
          <td>${cWt.toFixed(2)}</td>
          <td class="fw-bold">${base>0?base.toFixed(2):"0.00"}</td>
          <td class="text-start small" style="line-height:1.2">${details.join('<br>')||'-'}</td>
          <td class="price-text">${tot>0?("$"+tot.toFixed(2)):'-'}</td>
          <td class="${cls} small fw-bold">${st}</td>
        </tr>`;
        return;
      }

      // ===== 其它渠道：走 Excel 报价表 =====
      // FedEx Zone 若为 1：本次表头从 Zone~2 起（你给的定位均为 Zone~2 开始） => 统一映射 1->2
      let zKey = zoneVal;
      if(isFedexStandardChannel(ch) && zoneVal==='1') zKey = '2';

      let row = null;
      if(prices && prices.length>0 && zKey!=='-'){
        for(let r of prices){
          if(r.w >= cWt-0.001) { row=r; break; }
        }
      }

      if(!row || zoneVal==='-'){
        st="无分区/超重"; cls="text-muted"; bg="table-light";
        base=0;
      }else{
        base = row[zKey];
        if(!base){
          st="无报价"; cls="text-warning"; bg="table-warning";
          base=0;
        }
      }

      // 特殊拦截：USPS
      if(ch.includes('USPS')) {
        if(zip && USPS_BLOCK.some(p => zip.startsWith(p))) {
          st="无折扣 (Std Rate)"; cls="text-danger"; bg="table-danger"; base=0;
        }
        if(pkg.Wt>70 || L>30 || (L+(dims[1]+dims[2])*2)>130) {
          st="超规不可发"; cls="text-danger fw-bold"; bg="table-danger"; base=0;
        }
      }

      // UniUni(MT合并) 的尺寸限制仍沿用
      if(ch.includes('GOFO-MT（合并UNIUNI）')) {
        if(L>20 || (L+dims[1]+dims[2])>50 || pkg.Wt>20) {
          st="超规不可发"; cls="text-danger fw-bold"; bg="table-danger"; base=0;
        }
      }

      // 费用叠加
      let fees = {fuel:0, res:0, peak:0, other:0, sig:0};

      if(base > 0) {
        // 住宅费（按本次口径）
        if(isRes){
          let rf = getResFee(ch);
          if(rf>0){
            fees.res = rf;
            details.push(`住宅:$${rf.toFixed(2)}`);
          }
        }

        // 旺季：本次仅保留 FedEx 住宅旺季（USPS 完全不算）
        if(isPeak){
          if(isFedexStandardChannel(ch) && isRes){
            let today = new Date();
            let todayStr = today.toISOString().slice(0,10);
            let v = getFedexResPeakAmount(todayStr);
            if(v>0){
              fees.peak += v;
              details.push(`住宅旺季:$${v.toFixed(2)}`);
            }
          }
        }

        // DAS
        if(zip && (ch.includes("FedEx-632") || ch.includes("FedEx-MT-危险品") || ch.includes("FedEx-MT-超大包裹") || ch.includes("GOFO大件"))){
          let dasv = getDasFee(tier, ch, zip, isRes);
          if(dasv>0){
            fees.other += dasv;
            let b = das_bucket_of_zip(zip);
            details.push(`DAS-${b}:$${dasv.toFixed(2)}`);
          }
        }

        // 签名费（按开关 + 本次口径渠道）
        if(sigOn){
          let sf = getSigFee(ch);
          if(sf>0){
            fees.sig = sf;
            details.push(`签名:$${sf.toFixed(2)}`);
          }
        }

        // 燃油费（按本次口径 + 85折逻辑）
        if(hasFuel(ch)){
          let factor = fuelDiscountFactor(ch, whCode);
          fees.fuel = base * fedexFuel * factor;
          let tag = (factor===0.85) ? "×0.85" : "×1.00";
          details.push(`燃油(${(fedexFuel*100).toFixed(1)}% ${tag}):$${fees.fuel.toFixed(2)}`);
        }
      }

      let tot = base + fees.fuel + fees.res + fees.peak + fees.other + fees.sig;
      tbody.innerHTML += `<tr class="${bg}">
        <td class="fw-bold text-start text-nowrap">${ch}</td>
        <td class="text-nowrap">${whLabel}</td>
        <td>${zoneVal==='-'?'Zone -':('Zone '+zoneVal)}</td>
        <td>${cWt.toFixed(2)}</td>
        <td class="fw-bold">${base.toFixed(2)}</td>
        <td class="text-start small" style="line-height:1.2">${details.join('<br>')||'-'}</td>
        <td class="price-text">${tot>0?("$"+tot.toFixed(2)):'-'}</td>
        <td class="${cls} small fw-bold">${st}</td>
      </tr>`;
    });

    if(document.getElementById('resBody').innerHTML.trim()===''){
      document.getElementById('resBody').innerHTML = `<tr class="table-light"><td colspan="8" class="text-muted fw-bold">该仓库无可用渠道</td></tr>`;
    }
  };
</script>
</body>
</html>
"""

# ==========================================
# 4. 主程序
# ==========================================
if __name__ == '__main__':
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # 1) FedEx 官网住宅旺季
    fedex_res_peak = fetch_fedex_residential_peak_table()

    # 2) FedEx DAS：ZIP 集合（PDF） + 金额（Excel G181~G186）
    fedex_das_sets = build_fedex_das_zip_sets()
    das_fees = load_das_fees_all_tiers()
    fedex_das_sets["fees"] = das_fees

    final = {
        "zip_db": load_zip_db(),
        "tiers": load_tiers(),
        "surcharges": GLOBAL_SURCHARGES,
        "fedex_res_peak": fedex_res_peak,
        "fedex_das": fedex_das_sets
    }

    print("\n--- 3. 生成网页 ---")
    try:
        js_str = json.dumps(final, allow_nan=False)
    except:
        js_str = json.dumps(final).replace("NaN", "0")

    html = HTML_TEMPLATE.replace('__JSON_DATA__', js_str)

    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ 完成！已按本次口径更新：仓库下拉(含退货仓不计费)、渠道清单/启用、取消FedEx-YSD、USPS不算旺季、燃油85折规则、住宅费/签名费。")
