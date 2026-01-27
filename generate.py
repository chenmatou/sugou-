import pandas as pd
import json
import re
import os
import warnings
from datetime import datetime
from urllib.request import urlopen, Request

warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# ==========================================
# 1) 全局配置
# ==========================================
DATA_DIR = "data"
OUTPUT_DIR = "public"

TIER_FILES = {"T0": "T0.xlsx", "T1": "T1.xlsx", "T2": "T2.xlsx", "T3": "T3.xlsx"}

# 你工具里“渠道 key”统一用这些（不要随意改名，否则 ZIP 映射/allowlist/解析都对不上）
CHANNEL_KEYS = [
    "GOFO-报价",
    "GOFO-MT-报价",     # 合并 UNIUNI 的 sheet 里第一块
    "UNIUNI-MT-报价",   # 合并 UNIUNI 的 sheet 里第二块
    "USPS-YSD-报价",
    "FedEx-ECO-MT报价",
    "XLmiles-报价",
    "GOFO大件-GRO-报价",
    "FedEx-632-MT-报价",
    # 其它渠道后续再加
]

# 邮编库仍来自 GOFO-报价（保持不动）
ZIP_DB_SHEET_KEY = "GOFO-报价"
ZIP_COL_MAP = {
    "GOFO-报价": 5,
    "GOFO-MT-报价": 6,
    "UNIUNI-MT-报价": 7,
    "USPS-YSD-报价": 8,
    "FedEx-ECO-MT报价": 9,
    "XLmiles-报价": 10,
    "GOFO大件-GRO-报价": 11,
    "FedEx-632-MT-报价": 12,
    # "FedEx-YSD-报价": 13,  # 你已取消 FedEx-YSD
}

GLOBAL_SURCHARGES = {
    "fuel": 0.16,
    "oversize_fee": 130,
    "unauthorized_fee": 1150
}

US_STATES_CN = {
    'AL':'阿拉巴马','AK':'阿拉斯加','AZ':'亚利桑那','AR':'阿肯色','CA':'加利福尼亚',
    'CO':'科罗拉多','CT':'康涅狄格','DE':'特拉华','FL':'佛罗里达','GA':'佐治亚',
    'HI':'夏威夷','ID':'爱达荷','IL':'伊利诺伊','IN':'印第安纳','IA':'爱荷华',
    'KS':'堪萨斯','KY':'肯塔基','LA':'路易斯安那','ME':'缅因','MD':'马里兰',
    'MA':'马萨诸塞','MI':'密歇根','MN':'明尼苏达','MS':'密西西比','MO':'密苏里',
    'MT':'蒙大拿','NE':'内布拉斯加','NV':'内华达','NH':'新罕布什尔','NJ':'新泽西',
    'NM':'新墨西哥','NY':'纽约','NC':'北卡罗来纳','ND':'北达科他','OH':'俄亥俄',
    'OK':'俄克拉荷马','OR':'俄勒冈','PA':'宾夕法尼亚','RI':'罗德岛','SC':'南卡罗来纳',
    'SD':'南达科他','TN':'田纳西','TX':'德克萨斯','UT':'犹他','VT':'佛蒙特',
    'VA':'弗吉尼亚','WA':'华盛顿','WV':'西弗吉尼亚','WI':'威斯康星','WY':'怀俄明',
    'DC':'华盛顿特区'
}

# ==========================================
# 2) 仓库清单（按你模板：数字仅编号；用于可用渠道过滤 + FedEx Zone 归类）
# ==========================================
WAREHOUSES = [
    {"code": "60632", "label": "SureGo美中芝加哥-60632仓", "region": "CENTRAL"},
    {"code": "91730", "label": "SureGo美西库卡蒙格-91730新仓", "region": "WEST"},
    {"code": "91752", "label": "SureGo美西米拉罗马-91752仓", "region": "WEST"},
    {"code": "08691", "label": "SureGo美东新泽西-08691仓", "region": "EAST"},
    {"code": "06801", "label": "SureGo美东贝塞尔-06801仓", "region": "EAST"},
    {"code": "11791", "label": "SureGo美东长岛-11791仓", "region": "EAST"},
    {"code": "07032", "label": "SureGo美东新泽西-07032仓", "region": "EAST"},
    {"code": "63461", "label": "SureGo退货检测-美中密苏里63461退货仓", "region": "RETURN"},
]

# 渠道 ↔ 仓库可用（写死）：你模板里“美西/美中/美东”我这里按仓库 code 精确控制
CHANNEL_WAREHOUSE_ALLOW = {
    "GOFO-报价": ["91730", "91752", "60632"],
    "GOFO-MT-报价": ["91730", "91752", "60632"],
    "UNIUNI-MT-报价": ["91730", "91752", "60632"],
    "USPS-YSD-报价": ["91730", "91752", "60632"],
    "FedEx-632-MT-报价": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
    "FedEx-ECO-MT报价": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
    "GOFO大件-GRO-报价": ["91730", "91752", "08691", "06801", "11791", "07032"],
    "XLmiles-报价": ["91730"],  # 只有 91730
    # 退货仓先不计算：63461 不加入 allow（你说先不算）
}

# ==========================================
# 3) Excel 读取基础函数
# ==========================================
def safe_float(val):
    try:
        if pd.isna(val) or val == "" or str(val).strip().lower() == "nan":
            return 0.0
        return float(str(val).replace('$','').replace(',','').strip())
    except:
        return 0.0

def open_sheet(path, sheet_name):
    xl = pd.ExcelFile(path, engine='openpyxl')
    if sheet_name not in xl.sheet_names:
        return None
    return pd.read_excel(xl, sheet_name=sheet_name, header=None)

def get_sheet_by_keyword(path, keyword_list):
    xl = pd.ExcelFile(path, engine='openpyxl')
    for s in xl.sheet_names:
        sn = s.upper().replace(" ", "")
        if all(k.upper().replace(" ", "") in sn for k in keyword_list):
            return pd.read_excel(xl, sheet_name=s, header=None), s
    return None, None

# ==========================================
# 4) 邮编库（GOFO 独立邮编区）
# ==========================================
def load_zip_db():
    print("--- 1. 加载邮编库（GOFO独立邮编区） ---")
    path = os.path.join(DATA_DIR, TIER_FILES["T0"])
    if not os.path.exists(path):
        return {}

    df, real_sheet = get_sheet_by_keyword(path, ["GOFO", "报价"])
    if df is None:
        return {}

    print(f"    > 匹配Sheet: {real_sheet}")
    db = {}
    try:
        start = 0
        for i in range(100):
            cell = str(df.iloc[i,1]).strip()
            if cell.isdigit() and len(cell) == 5:
                start = i
                break

        df = df.fillna("")
        for _, row in df.iloc[start:].iterrows():
            z = str(row[1]).strip().zfill(5)
            if z.isdigit() and len(z) == 5:
                zones = {}
                for k, col in ZIP_COL_MAP.items():
                    v = str(row[col]).strip()
                    zones[k] = None if v in ["-", "nan", "", "0", "0.0"] else v
                st = str(row[3]).strip().upper()
                db[z] = {
                    "s": st,
                    "sn": US_STATES_CN.get(st, ""),
                    "c": str(row[4]).strip(),
                    "r": str(row[2]).strip(),
                    "z": zones
                }
    except:
        pass

    print(f"✅ 邮编库: {len(db)} 条")
    return db

# ==========================================
# 5) 固定坐标解析：解决你现在 GOFO / GOFO-MT / UNIUNI-MT 不出报价
# ==========================================
def col_letter_to_idx(letter):
    return ord(letter.upper()) - ord('A')

def parse_fixed_table(df, header_row_1based, zone_start_col_letter, weight_rules):
    """
    df: 0-based
    header_row_1based: 例如 3 表示 Excel 第3行（Zone~1 在这一行）
    zone_start_col_letter: 例如 'C'
    weight_rules: list of tuples: (col_letter, unit, start_row_1based)
        例：GOFO-报价：OZ 在 A4-A19；LB 从 A20 往下；KG 从 B4 往下
        => [('A','oz',4), ('A','lb',20), ('B','kg',4)]
    逻辑：逐行扫描，从最“靠后的单位规则”优先生效（例如同列 A 既有 oz 又有 lb，则 >=20 用 lb）
    """
    if df is None or df.empty:
        return [], []

    df = df.fillna("")
    hr = header_row_1based - 1
    z0 = col_letter_to_idx(zone_start_col_letter)

    # 解析 zones：从 zone_start 往右读到空为止
    zones = []
    for c in range(z0, df.shape[1]):
        v = str(df.iloc[hr, c]).strip()
        if not v:
            break
        m = re.search(r'(\d+)', v)
        if m:
            zones.append((m.group(1), c))
        else:
            # 不是 zone 列就跳过
            continue

    # 没读到 zone 列直接返回空
    if not zones:
        return [], []

    # weight_rules 预处理：按 start_row 降序，让“更靠后的规则”覆盖更早的
    rules = []
    for col, unit, sr in weight_rules:
        rules.append((col_letter_to_idx(col), unit.lower(), sr - 1))
    rules.sort(key=lambda x: x[2], reverse=True)

    prices = []
    # 数据区：从 header_row+1 开始扫
    for r in range(hr + 1, df.shape[0]):
        w_lb = None

        # 按规则挑 weight
        for c_idx, unit, sr0 in rules:
            if r < sr0:
                continue
            cell = str(df.iloc[r, c_idx]).strip()
            if cell == "":
                continue
            # 允许纯数字/带单位
            nums = re.findall(r"[\d\.]+", cell)
            if not nums:
                continue
            n = float(nums[0])
            if unit == "oz":
                w_lb = n / 16.0
            elif unit == "kg":
                w_lb = n / 0.453592
            else:  # lb
                w_lb = n
            break

        if w_lb is None:
            continue

        item = {"w": float(w_lb)}
        for zname, c in zones:
            p = safe_float(df.iloc[r, c])
            if p > 0:
                item[zname] = p

        if len(item) > 1:
            prices.append(item)

    prices.sort(key=lambda x: x["w"])
    return [z for z, _ in zones], prices

def load_tiers():
    print("\n--- 2. 加载报价表（按你模板坐标优先） ---")
    all_tiers = {}

    for t_name, f_name in TIER_FILES.items():
        print(f"处理 {t_name}...")
        path = os.path.join(DATA_DIR, f_name)
        if not os.path.exists(path):
            continue

        t_data = {}

        # 2.1 GOFO-报价（固定坐标）
        df_gofo, sh = get_sheet_by_keyword(path, ["GOFO", "报价"])
        if df_gofo is not None:
            zones, prices = parse_fixed_table(
                df_gofo,
                header_row_1based=3,
                zone_start_col_letter="C",
                weight_rules=[("A", "oz", 4), ("A", "lb", 20), ("B", "kg", 4)]
            )
            t_data["GOFO-报价"] = {"prices": prices}
            print(f"    > GOFO-报价(sheet={sh}): zones={zones}, prices={len(prices)}")

        # 2.2 GOFO、UNIUNI-MT-报价（一个 sheet 两块表）
        df_mt, sh_mt = get_sheet_by_keyword(path, ["GOFO", "UNIUNI", "MT"])
        if df_mt is not None:
            # GOFO-MT 块：Zone~1 在 C3；重量规则同 GOFO
            zones1, prices1 = parse_fixed_table(
                df_mt,
                header_row_1based=3,
                zone_start_col_letter="C",
                weight_rules=[("A", "oz", 3), ("A", "lb", 20), ("B", "kg", 4)]
            )
            t_data["GOFO-MT-报价"] = {"prices": prices1}
            print(f"    > GOFO-MT-报价(sheet={sh_mt}): zones={zones1}, prices={len(prices1)}")

            # UNIUNI-MT 块：Zone~1 在 N3；重量 OZ=L3-L19；LB=L20；KG=M4
            zones2, prices2 = parse_fixed_table(
                df_mt,
                header_row_1based=3,
                zone_start_col_letter="N",
                weight_rules=[("L", "oz", 3), ("L", "lb", 20), ("M", "kg", 4)]
            )
            t_data["UNIUNI-MT-报价"] = {"prices": prices2}
            print(f"    > UNIUNI-MT-报价(sheet={sh_mt}): zones={zones2}, prices={len(prices2)}")

        # 2.3 USPS-YSD-报价（固定坐标：Zone~1-9 D4-L4；LB=B4；KG=C4）
        df_usps, sh_usps = get_sheet_by_keyword(path, ["USPS", "YSD"])
        if df_usps is not None:
            zones, prices = parse_fixed_table(
                df_usps,
                header_row_1based=4,
                zone_start_col_letter="D",
                weight_rules=[("B", "lb", 4), ("C", "kg", 4)]
            )
            t_data["USPS-YSD-报价"] = {"prices": prices}
            print(f"    > USPS-YSD-报价(sheet={sh_usps}): zones={zones}, prices={len(prices)}")

        # 2.4 其它渠道：先按“猜表头”保留原逻辑（不影响本次你要先修的 3 个渠道）
        #     你后续要拆 FedEx-MT 超大包裹/危险品/大件等，再补固定坐标即可。
        all_tiers[t_name] = t_data

    return all_tiers

# ==========================================
# 6) HTML_TEMPLATE（保持你已有 UI：合规检查 + 仓库过滤 + 报价结果）
#     这里只做“必须用到的数据字段”对齐：warehouses + channel_wh_allow + tiers + zip_db
# ==========================================
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>业务员报价助手</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body{background:#f4f6f9; font-family:'Segoe UI','Microsoft YaHei',sans-serif;}
    header{background:#000;color:#fff;padding:12px 0;}
    .card{border:none;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,.05)}
    .card-header{background:#212529;color:#fff;font-weight:700;border-radius:10px 10px 0 0}
    .indicator{display:inline-block;padding:2px 8px;border-radius:4px;color:#fff;font-weight:700;font-size:12px}
    .bg-ok{background:#198754}.bg-err{background:#dc3545}
    .result-table th{background:#212529;color:#fff;vertical-align:middle;text-align:center}
    .result-table td{vertical-align:middle;text-align:center}
    .price-text{font-weight:800;font-size:18px;color:#0d6efd}
  </style>
</head>
<body>

<header>
  <div class="container d-flex justify-content-between align-items-center">
    <div>
      <div class="fw-bold">📦 业务员报价助手</div>
      <div class="small opacity-75">T0-T3 报价表解析版</div>
    </div>
    <div class="small">Quote Tool</div>
  </div>
</header>

<div class="container my-4">
  <div class="row g-4">
    <div class="col-lg-4">
      <div class="card">
        <div class="card-header">基础信息</div>
        <div class="card-body">

          <div class="mb-3">
            <label class="form-label fw-bold">发货仓库（仅用于可用渠道过滤）</label>
            <select class="form-select" id="warehouse"></select>
            <div class="small text-muted mt-1">你选择仓库后，只显示该仓可用渠道。</div>
          </div>

          <div class="mb-3">
            <label class="form-label fw-bold">客户等级</label>
            <div class="btn-group w-100" role="group">
              <input type="radio" class="btn-check" name="tier" id="t0" value="T0"><label class="btn btn-outline-secondary" for="t0">T0</label>
              <input type="radio" class="btn-check" name="tier" id="t1" value="T1"><label class="btn btn-outline-secondary" for="t1">T1</label>
              <input type="radio" class="btn-check" name="tier" id="t2" value="T2"><label class="btn btn-outline-secondary" for="t2">T2</label>
              <input type="radio" class="btn-check" name="tier" id="t3" value="T3" checked><label class="btn btn-outline-secondary" for="t3">T3</label>
            </div>
          </div>

          <div class="mb-3">
            <label class="form-label fw-bold">目的地邮编</label>
            <div class="input-group">
              <input type="text" class="form-control" id="zipCode" placeholder="5位邮编">
              <button class="btn btn-dark" id="btnLookup" type="button">查询</button>
            </div>
            <div id="locInfo" class="small text-muted mt-1">请输入邮编</div>
          </div>

          <hr>

          <div class="mb-3">
            <label class="form-label fw-bold">包裹规格</label>
            <div class="row g-2">
              <div class="col-4"><input class="form-control" id="length" type="number" placeholder="长 L"></div>
              <div class="col-4"><input class="form-control" id="width" type="number" placeholder="宽 W"></div>
              <div class="col-4"><input class="form-control" id="height" type="number" placeholder="高 H"></div>
              <div class="col-12">
                <select class="form-select" id="dimUnit">
                  <option value="in">IN</option><option value="cm">CM</option><option value="mm">MM</option>
                </select>
              </div>
              <div class="col-8"><input class="form-control" id="weight" type="number" placeholder="重量"></div>
              <div class="col-4">
                <select class="form-select" id="weightUnit">
                  <option value="lb">LB</option><option value="oz">OZ</option><option value="kg">KG</option><option value="g">G</option>
                </select>
              </div>
            </div>
          </div>

          <div class="bg-light p-2 rounded border mb-3">
            <div class="fw-bold small mb-2 border-bottom">🚦 各渠道合规性一览</div>
            <table class="table table-sm mb-0" id="checkTable">
              <tr><td class="text-muted">等待输入尺寸...</td></tr>
            </table>
          </div>

          <button class="btn btn-primary w-100 fw-bold" id="btnCalc" type="button">开始计算</button>

        </div>
      </div>
    </div>

    <div class="col-lg-8">
      <div class="card">
        <div class="card-header d-flex justify-content-between">
          <span>报价结果</span>
          <span class="badge bg-warning text-dark" id="tierBadge"></span>
        </div>
        <div class="card-body">
          <div class="alert alert-info py-2 small" id="pkgSummary">请先输入邮编和包裹信息</div>

          <div class="table-responsive">
            <table class="table table-bordered table-hover result-table">
              <thead>
                <tr>
                  <th width="25%">渠道</th>
                  <th width="20%">仓库</th>
                  <th width="10%">Zone</th>
                  <th width="15%">计费重(LB)</th>
                  <th width="15%">基础运费</th>
                  <th width="15%">总费用</th>
                </tr>
              </thead>
              <tbody id="resBody"></tbody>
            </table>
          </div>

          <div class="small text-muted mt-2">
            说明：本页先保证 GOFO/GOFO-MT/UNIUNI/USPS 四个渠道“能正常出价”；其它 FedEx 拆表、DAS、燃油折扣等在下一轮按你表定位补齐。
          </div>

        </div>
      </div>
    </div>
  </div>
</div>

<script>
  let DATA = {};
  try { DATA = __JSON_DATA__; } catch(e) { alert("Data Init Failed"); }

  // ---------- 仓库下拉 ----------
  (function initWarehouse(){
    const sel = document.getElementById("warehouse");
    (DATA.warehouses || []).forEach(w=>{
      const opt = document.createElement("option");
      opt.value = w.code;
      opt.textContent = `${w.label}（${w.code}）`;
      sel.appendChild(opt);
    });
    if(sel.options.length>0) sel.value = (DATA.warehouses[0]||{}).code || "";
  })();

  // ---------- 自动计算 ----------
  document.querySelectorAll('input[name="tier"]').forEach(r=>{
    r.addEventListener("change", ()=>document.getElementById("btnCalc").click());
  });
  document.getElementById("warehouse").addEventListener("change", ()=>document.getElementById("btnCalc").click());

  // ---------- 单位标准化 ----------
  function standardize(l,w,h,du,wt,wu){
    let L=parseFloat(l)||0, W=parseFloat(w)||0, H=parseFloat(h)||0, Weight=parseFloat(wt)||0;
    if(du==='cm'){L/=2.54;W/=2.54;H/=2.54} else if(du==='mm'){L/=25.4;W/=25.4;H/=25.4}
    if(wu==='kg')Weight/=0.453592; else if(wu==='oz')Weight/=16; else if(wu==='g')Weight/=453.592;
    return {L,W,H,Wt:Weight};
  }

  // ---------- 合规检查（恢复你要的尺寸判断模块） ----------
  function check(pkg){
    let d=[pkg.L,pkg.W,pkg.H].sort((a,b)=>b-a);
    let L=d[0], G=L+2*(d[1]+d[2]);
    const row=(name,fail,tip)=>{
      let cls=fail?'bg-err':'bg-ok';
      let txt=fail?tip:'正常(OK)';
      return `<tr><td>${name}</td><td class="text-end"><span class="indicator ${cls}"></span> ${txt}</td></tr>`;
    };
    let html='';
    // UniUni（你原口径）
    html += row('UNIUNI', (L>20 || (L+d[1]+d[2])>50 || pkg.Wt>20), '限制(L>20 / Wt>20)');
    // USPS（你原口径）
    html += row('USPS', (pkg.Wt>70 || L>30 || (L+(d[1]+d[2])*2)>130), '限制(>70lb / 130")');
    // GOFO（大件只示意）
    html += row('GOFO', (pkg.Wt>150), '超限(>150lb)');
    document.getElementById("checkTable").innerHTML = html;
  }

  ['length','width','height','weight','dimUnit','weightUnit'].forEach(id=>{
    document.getElementById(id).addEventListener("input", ()=>{
      let p=standardize(
        document.getElementById('length').value,
        document.getElementById('width').value,
        document.getElementById('height').value,
        document.getElementById('dimUnit').value,
        document.getElementById('weight').value,
        document.getElementById('weightUnit').value
      );
      check(p);
    });
  });

  // ---------- 邮编查询（优先 zip_db） ----------
  let CUR_ZONES = {};
  async function lookupZip(zip){
    CUR_ZONES = {};
    const d=document.getElementById("locInfo");

    if(DATA.zip_db && DATA.zip_db[zip]){
      let i=DATA.zip_db[zip];
      d.innerHTML = `✅ ${i.sn} ${i.s} - ${i.c} [${i.r}]`;
      CUR_ZONES = i.z || {};
      return;
    }
    d.innerHTML = `❌ 未在邮编库找到该邮编（无法给 GOFO/USPS 分区）`;
  }

  document.getElementById("btnLookup").onclick = async ()=>{
    const zip=document.getElementById("zipCode").value.trim();
    if(zip.length!==5){ alert("请输入5位邮编"); return; }
    await lookupZip(zip);
    document.getElementById("btnCalc").click();
  };

  // ---------- 计费重除数（保留最基本，不改动其它渠道） ----------
  function getDivisor(ch, vol){
    let u=ch.toUpperCase();
    if(u.includes('UNIUNI')) return 0;
    if(u.includes('USPS')) return vol>1728?166:0;
    return 0; // GOFO/GOFO-MT 按实重（先满足出价）
  }

  // ---------- 核心计算：修复你说的三个渠道出价失败 ----------
  document.getElementById("btnCalc").onclick = async ()=>{
    const zip=document.getElementById("zipCode").value.trim();
    if(zip.length===5 && (!CUR_ZONES || Object.keys(CUR_ZONES).length===0)){
      await lookupZip(zip);
    }

    const tier=document.querySelector('input[name="tier"]:checked').value;
    const wh=document.getElementById("warehouse").value;
    const whLabel = (DATA.warehouse_map && DATA.warehouse_map[wh]) ? DATA.warehouse_map[wh] : wh;

    document.getElementById("tierBadge").innerText=tier;

    const pkg=standardize(
      document.getElementById('length').value,
      document.getElementById('width').value,
      document.getElementById('height').value,
      document.getElementById('dimUnit').value,
      document.getElementById('weight').value,
      document.getElementById('weightUnit').value
    );
    let dims=[pkg.L,pkg.W,pkg.H].sort((a,b)=>b-a);
    let G=dims[0]+2*(dims[1]+dims[2]);
    document.getElementById("pkgSummary").innerHTML =
      `<b>基准:</b> ${dims[0].toFixed(1)}"×${dims[1].toFixed(1)}"×${dims[2].toFixed(1)}" | 实重:${pkg.Wt.toFixed(2)}lb | 围长:${G.toFixed(1)}"`;

    const tbody=document.getElementById("resBody");
    tbody.innerHTML="";

    const tiers=DATA.tiers || {};
    const tdata=tiers[tier] || {};
    const allowMap=DATA.channel_wh_allow || {};

    const channels = Object.keys(tdata);

    channels.forEach(ch=>{
      // 1) 仓库可用过滤（不可用直接不显示）
      const allow = allowMap[ch] || [];
      if(allow.length>0 && !allow.includes(wh)) return;

      // 2) zone：GOFO/GOFO-MT/UNIUNI/USPS 都用 zip_db 的 CUR_ZONES
      const zoneVal = (CUR_ZONES && CUR_ZONES[ch]) ? String(CUR_ZONES[ch]) : "-";

      // 3) 计费重
      let cWt=pkg.Wt;
      const div=getDivisor(ch, pkg.L*pkg.W*pkg.H);
      if(div>0){
        const vWt=(pkg.L*pkg.W*pkg.H)/div;
        cWt=Math.max(pkg.Wt, vWt);
      }
      if(cWt>1) cWt=Math.ceil(cWt);

      // 4) 匹配价格
      const prices = (tdata[ch] && tdata[ch].prices) ? tdata[ch].prices : [];
      let base=0;

      if(zoneVal==="-" || prices.length===0){
        tbody.innerHTML += `
          <tr class="table-light">
            <td class="fw-bold text-start">${ch}</td>
            <td class="text-start">${whLabel}</td>
            <td>${zoneVal}</td>
            <td>${cWt.toFixed(2)}</td>
            <td>0.00</td>
            <td class="text-muted">-</td>
          </tr>`;
        return;
      }

      // 关键：GOFO/GOFO-MT/UNIUNI 的 zone 结构是 1-8；USPS 是 1-9
      let row=null;
      for(let r of prices){
        if(r.w >= cWt-0.001){ row=r; break; }
      }
      if(row && row[zoneVal] !== undefined){
        base = parseFloat(row[zoneVal])||0;
      }

      tbody.innerHTML += `
        <tr>
          <td class="fw-bold text-start">${ch}</td>
          <td class="text-start">${whLabel}</td>
          <td>Zone ${zoneVal}</td>
          <td>${cWt.toFixed(2)}</td>
          <td>${base.toFixed(2)}</td>
          <td class="price-text">${base>0?("$"+base.toFixed(2)):"-"}</td>
        </tr>`;
    });

    // 如果全部没显示，给最明显的排查提示（不影响你其它逻辑）
    if(tbody.children.length===0){
      tbody.innerHTML = `<tr><td colspan="6" class="text-danger fw-bold">❌ 该仓库无可用渠道（或 allowlist 未配置）</td></tr>`;
    }
  };
</script>

</body>
</html>
"""

# ==========================================
# 7) 主入口：生成 public/index.html
# ==========================================
if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    zip_db = load_zip_db()
    tiers = load_tiers()

    # warehouse_map 给前端显示
    warehouse_map = {w["code"]: w["label"] for w in WAREHOUSES}

    final = {
        "zip_db": zip_db,
        "tiers": tiers,
        "surcharges": GLOBAL_SURCHARGES,
        "warehouses": WAREHOUSES,
        "warehouse_map": warehouse_map,
        "channel_wh_allow": CHANNEL_WAREHOUSE_ALLOW,
        "meta": {"generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}
    }

    print("\n--- 3. 生成网页 ---")
    js_str = json.dumps(final, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("__JSON_DATA__", js_str)

    out_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ 完成！已生成: {out_path}")
