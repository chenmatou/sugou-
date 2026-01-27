import json
import os
import re
import warnings
from datetime import datetime
from openpyxl import load_workbook
from openpyxl.utils.cell import column_index_from_string, get_column_letter

# 忽略 Excel 样式警告
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# =========================================================
# 1) 全局路径
# =========================================================
DATA_DIR = "data"
OUTPUT_DIR = "public"

TIER_FILES = {
    "T0": "T0.xlsx",
    "T1": "T1.xlsx",
    "T2": "T2.xlsx",
    "T3": "T3.xlsx",
}

# =========================================================
# 2) 仓库配置 (按您提供的清单)
# =========================================================
WAREHOUSES = [
    {"id": "W60632", "label": "SureGo美中芝加哥-60632仓", "zip": "60632", "region": "CENTRAL", "enabled": True},
    {"id": "W91730", "label": "SureGo美西库卡蒙格-91730新仓", "zip": "91730", "region": "WEST", "enabled": True},
    {"id": "W91752", "label": "SureGo美西米拉罗马-91752仓", "zip": "91752", "region": "WEST", "enabled": True},
    {"id": "E08691", "label": "SureGo美东新泽西-08691仓", "zip": "08691", "region": "EAST", "enabled": True},
    {"id": "E06801", "label": "SureGo美东贝塞尔-06801仓", "zip": "06801", "region": "EAST", "enabled": True},
    {"id": "E11791", "label": "SureGo美东长岛-11791仓", "zip": "11791", "region": "EAST", "enabled": True},
    {"id": "E07032", "label": "SureGo美东新泽西-07032仓", "zip": "07032", "region": "EAST", "enabled": True},
    {"id": "R63461", "label": "SureGo退货检测-美中密苏里63461退货仓", "zip": "63461", "region": "RETURN", "enabled": False},
]

# =========================================================
# 3) 渠道 ↔ 仓库区域映射
# =========================================================
CHANNEL_ALLOW = {
    "GOFO-报价": ["WEST", "CENTRAL"],
    "GOFO、UNIUNI-MT-报价": ["WEST", "CENTRAL"],
    "USPS-YSD-报价": ["WEST", "CENTRAL"],
    "FedEx-632-MT-报价": ["WEST", "CENTRAL", "EAST"],
    "FedEx-MT-超大包裹-报价": ["WEST", "CENTRAL", "EAST"],
    "FedEx-ECO-MT报价": ["WEST", "CENTRAL", "EAST"],
    "FedEx-MT-危险品-报价": ["CENTRAL", "EAST"],
    "GOFO大件-MT-报价": ["WEST", "EAST"],
    "XLmiles-报价": ["WEST"],
}

# =========================================================
# 4) 费用配置 (精确到美分)
# =========================================================
FEES = {
    "res": {
        "FedEx-632-MT-报价": 2.61,
        "FedEx-MT-超大包裹-报价": 2.61,
        "FedEx-MT-危险品-报价": 3.32,
        "GOFO大件-MT-报价": 2.93,
    },
    "sig": {
        "XLmiles-报价": 10.20,
        "FedEx-632-MT-报价": 4.37,
        "FedEx-MT-危险品-报价": 9.71,
        "FedEx-MT-超大包裹-报价": 4.37,
    }
}

# 燃油配置
FUEL_CONFIG = {
    "channels": [
        "FedEx-632-MT-报价",
        "FedEx-MT-超大包裹-报价",
        "FedEx-MT-危险品-报价",
        "GOFO大件-MT-报价"
    ],
    "discount_85": [
        "FedEx-632-MT-报价",
        "FedEx-MT-超大包裹-报价"
    ]
}

# =========================================================
# 5) Excel 工具函数
# =========================================================
def safe_float(val) -> float:
    try:
        if val is None: return 0.0
        s = str(val).strip()
        if not s or s.lower() == "nan": return 0.0
        s = s.replace("$", "").replace(",", "")
        return float(s)
    except: return 0.0

def to_lb(val, unit="LB"):
    if val is None: return None
    s = str(val).strip()
    nums = re.findall(r"[\d\.]+", s)
    if not nums: return None
    n = float(nums[0])
    if "OZ" in unit.upper() or "OZ" in s.upper(): return n / 16.0
    if "KG" in unit.upper() or "KG" in s.upper(): return n / 0.453592
    return n

def get_sheet(wb, keywords):
    # 关键词匹配 sheet
    for name in wb.sheetnames:
        if all(k.upper() in name.upper() for k in keywords):
            return wb[name]
    return None

def scan_zones(ws, row, col_start_letter, col_end_letter):
    zmap = {}
    c1 = column_index_from_string(col_start_letter)
    c2 = column_index_from_string(col_end_letter)
    for c in range(c1, c2 + 1):
        v = ws.cell(row=row, column=c).value
        if v:
            s = str(v).strip()
            # 匹配 "Zone 1", "Zone~1", "1", "分区1"
            m = re.search(r"(\d+)", s)
            if m:
                zmap[str(m.group(1))] = get_column_letter(c)
    return zmap

def read_table(ws, weight_col, start_row, zmap, unit="LB"):
    prices = []
    r = start_row
    while r < 5000:
        w_val = ws[f"{weight_col}{r}"].value
        if w_val is None: break
        
        lb = to_lb(w_val, unit)
        if lb is None: 
            r += 1
            continue
            
        item = {"w": lb}
        has_price = False
        for z, col in zmap.items():
            p = safe_float(ws[f"{col}{r}"].value)
            if p > 0:
                item[z] = p
                has_price = True
        
        if has_price: prices.append(item)
        r += 1
    return prices

def extract_das(ws):
    # G181~G186
    items = []
    for r in range(181, 187):
        n = ws[f"I{r}"].value
        p = safe_float(ws[f"G{r}"].value)
        if p > 0:
            items.append(f"{n}: ${p}")
    return items

# =========================================================
# 6) 核心加载逻辑
# =========================================================
def load_data():
    db = {"tiers": {}, "zip_db": {}}
    
    # 1. 加载邮编库 (从 T0 的 GOFO-报价)
    print("--- 加载邮编库 ---")
    if os.path.exists(os.path.join(DATA_DIR, "T0.xlsx")):
        wb0 = load_workbook(os.path.join(DATA_DIR, "T0.xlsx"), data_only=True)
        ws_zip = get_sheet(wb0, ["GOFO", "报价"])
        if ws_zip:
            # 假设邮编在B列, State在D, City在E (按V19逻辑)
            # 这里的Zone列映射对应 ZIP_COL_MAP
            # GOFO(F), GOFO-MT(G), UNI(H), USPS(I), ECO(J), XL(K), GOFO-Big(L), 632(M), YSD(N) -> 这里的列号需根据Excel实际调整
            # 既然没有Excel实际文件，我采用你之前提供的列号逻辑：
            # C=3, D=4, E=5 ...
            for r in range(4, 50000): # 假设数据从第4行开始
                z = str(ws_zip[f"B{r}"].value).strip().zfill(5)
                if not z.isdigit(): continue
                if len(z) != 5: continue
                
                info = {
                    "s": str(ws_zip[f"D{r}"].value).strip(),
                    "c": str(ws_zip[f"E{r}"].value).strip(),
                    "z": {}
                }
                
                # 映射 Zone 值 (根据你提供的 ZIP_COL_MAP 索引)
                # 5->F, 6->G ...
                # GOFO-报价:5, GOFO/UNI-MT:6, USPS:8, ECO:9, XL:10, GOFO大件:11, 632:12
                mapping = {
                    "GOFO-报价": 5, "GOFO、UNIUNI-MT-报价": 6, "USPS-YSD-报价": 8,
                    "FedEx-ECO-MT报价": 9, "XLmiles-报价": 10, "GOFO大件-MT-报价": 11,
                    "FedEx-632-MT-报价": 12, "FedEx-MT-超大包裹-报价": 12, "FedEx-MT-危险品-报价": 12
                }
                
                for ch, col_idx in mapping.items():
                    val = ws_zip.cell(row=r, column=col_idx+1).value # openpyxl is 1-based
                    if val and str(val) not in ['-', '0']:
                        info['z'][ch] = str(val)
                
                db["zip_db"][z] = info
    print(f"✅ 邮编库加载完成: {len(db['zip_db'])} 条")

    # 2. 加载价格表
    print("--- 加载价格表 ---")
    for tier, fname in TIER_FILES.items():
        fpath = os.path.join(DATA_DIR, fname)
        if not os.path.exists(fpath): continue
        print(f"Processing {tier}...")
        
        wb = load_workbook(fpath, data_only=True)
        tier_data = {}
        
        # 1) GOFO-报价
        ws = get_sheet(wb, ["GOFO", "报价"])
        if ws:
            # 混合: OZ(A4-A19), LB(A20+)
            zmap = scan_zones(ws, 3, "C", "J")
            p_oz = read_table(ws, "A", 4, zmap, "OZ") # 读到空为止? 限制行数更好
            # 修正: read_table 读到空停止，这里需要分段
            # 手动读 OZ 段
            oz_prices = []
            for r in range(4, 20):
                w = to_lb(ws[f"A{r}"].value, "OZ")
                if w: 
                    it = {"w": w}
                    for z, c in zmap.items(): 
                        pv = safe_float(ws[f"{c}{r}"].value)
                        if pv>0: it[z]=pv
                    oz_prices.append(it)
            # LB 段
            lb_prices = read_table(ws, "A", 20, zmap, "LB")
            tier_data["GOFO-报价"] = {"type": "single", "prices": oz_prices + lb_prices, "das": extract_das(ws)}

        # 2) GOFO、UNIUNI-MT
        ws = get_sheet(wb, ["GOFO", "UNIUNI", "MT"])
        if ws:
            # GOFO部分: Weight A3, Zone C3-J3
            zmap_g = scan_zones(ws, 3, "C", "J")
            p_g = read_table(ws, "A", 4, zmap_g, "LB") # 假设主要是LB，如果混合需特殊处理，这里简化为LB
            # UNIUNI部分: Weight L3, Zone N3-U3
            zmap_u = scan_zones(ws, 3, "N", "U")
            p_u = read_table(ws, "L", 4, zmap_u, "LB")
            
            tier_data["GOFO、UNIUNI-MT-报价"] = {
                "type": "combo", 
                "gofo": p_g, 
                "uni": p_u, 
                "das": extract_das(ws)
            }

        # 3) USPS-YSD
        ws = get_sheet(wb, ["USPS", "YSD"])
        if ws:
            zmap = scan_zones(ws, 4, "D", "L")
            p = read_table(ws, "B", 5, zmap, "LB")
            tier_data["USPS-YSD-报价"] = {"type": "single", "prices": p, "das": extract_das(ws)}

        # 4) FedEx-ECO
        ws = get_sheet(wb, ["FedEx", "ECO"])
        if ws:
            zmap = scan_zones(ws, 3, "C", "I")
            p = read_table(ws, "A", 4, zmap, "LB")
            tier_data["FedEx-ECO-MT报价"] = {"type": "single", "prices": p, "das": extract_das(ws)}

        # 5) FedEx-632 / DG / Oversize / GOFO大件 (结构类似：双表)
        dual_channels = [
            ("FedEx-632-MT-报价", ["632"]),
            ("FedEx-MT-危险品-报价", ["危险品"]),
            ("FedEx-MT-超大包裹-报价", ["超大"]),
            ("GOFO大件-MT-报价", ["GOFO", "大件"])
        ]
        
        for ch_name, keywords in dual_channels:
            ws = get_sheet(wb, keywords)
            if ws:
                # Res: W=A, Z=C-I
                zmap_res = scan_zones(ws, 3, "C", "I")
                p_res = read_table(ws, "A", 4, zmap_res, "LB")
                # Com: W=K, Z=M-S
                zmap_com = scan_zones(ws, 3, "M", "S")
                p_com = read_table(ws, "K", 4, zmap_com, "LB")
                
                tier_data[ch_name] = {
                    "type": "dual",
                    "res": p_res,
                    "com": p_com,
                    "das": extract_das(ws)
                }

        # 6) XLmiles
        ws = get_sheet(wb, ["XLmiles"])
        if ws:
            zmap = scan_zones(ws, 3, "D", "G") # Zone 1,2,3,6
            p = read_table(ws, "C", 4, zmap, "LB")
            tier_data["XLmiles-报价"] = {"type": "single", "prices": p, "das": extract_das(ws)}

        db["tiers"][tier] = tier_data

    return db

# =========================================================
# 7) 生成 HTML
# =========================================================
if __name__ == '__main__':
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    
    data = load_data()
    
    # 注入配置
    data["warehouses"] = WAREHOUSES
    data["channel_allow"] = CHANNEL_ALLOW
    data["fees"] = FEES
    data["fuel_config"] = FUEL_CONFIG
    
    # HTML 模板
    html = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>报价助手 V20</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #fff; font-family: 'Segoe UI', sans-serif; font-size: 14px; }
        .card { border: 1px solid #dee2e6; box-shadow: none; }
        .card-header { background-color: #f8f9fa; font-weight: bold; border-bottom: 1px solid #dee2e6; }
        .form-label { font-weight: 600; font-size: 13px; margin-bottom: 2px; }
        .form-control, .form-select { font-size: 13px; border-radius: 3px; }
        .btn { font-size: 14px; font-weight: 600; border-radius: 3px; }
        .table th { background-color: #343a40; color: #fff; font-weight: normal; font-size: 13px; text-align: center; }
        .table td { text-align: center; vertical-align: middle; font-size: 13px; }
        .price-text { color: #d63384; font-weight: 800; font-size: 15px; }
        .small-muted { font-size: 12px; color: #6c757d; }
    </style>
</head>
<body>
<div class="container py-3">
    <div class="d-flex justify-content-between align-items-center mb-3 border-bottom pb-2">
        <h5 class="m-0 fw-bold">📦 业务员报价助手 V20</h5>
        <small class="text-muted">Update: <span id="date"></span></small>
    </div>

    <div class="row g-3">
        <div class="col-lg-4">
            <div class="card h-100">
                <div class="card-header">参数设置</div>
                <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label">发货仓库</label>
                        <select class="form-select" id="warehouse"></select>
                    </div>
                    
                    <div class="mb-3">
                        <label class="form-label">客户等级</label>
                        <div class="btn-group w-100">
                            <input type="radio" class="btn-check tier-radio" name="tier" id="t0" value="T0"><label class="btn btn-outline-secondary" for="t0">T0</label>
                            <input type="radio" class="btn-check tier-radio" name="tier" id="t1" value="T1"><label class="btn btn-outline-secondary" for="t1">T1</label>
                            <input type="radio" class="btn-check tier-radio" name="tier" id="t2" value="T2"><label class="btn btn-outline-secondary" for="t2">T2</label>
                            <input type="radio" class="btn-check tier-radio" name="tier" id="t3" value="T3" checked><label class="btn btn-outline-secondary" for="t3">T3</label>
                        </div>
                    </div>

                    <div class="mb-3">
                        <label class="form-label">目的地邮编</label>
                        <div class="input-group">
                            <input type="text" class="form-control" id="zipCode" placeholder="5位数字">
                            <button class="btn btn-dark" id="btnLookup">查询</button>
                        </div>
                        <div id="locInfo" class="mt-1 text-success fw-bold small"></div>
                    </div>

                    <div class="row g-2 mb-3">
                        <div class="col-6">
                            <label class="form-label">地址类型</label>
                            <select class="form-select" id="addressType">
                                <option value="res">住宅地址</option>
                                <option value="com">商业地址</option>
                            </select>
                        </div>
                        <div class="col-6 pt-4">
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" id="sigToggle">
                                <label class="form-check-label small fw-bold" for="sigToggle">签名服务</label>
                            </div>
                        </div>
                    </div>

                    <div class="bg-light p-2 rounded border mb-3">
                        <div class="fw-bold small border-bottom mb-2">⛽ 燃油费率 (%)</div>
                        <div class="row g-2">
                            <div class="col-6">
                                <input type="number" class="form-control form-control-sm" id="fedexFuel" value="16.0">
                                <small class="text-muted">FedEx通用</small>
                            </div>
                            <div class="col-6">
                                <input type="number" class="form-control form-control-sm" id="gofoFuel" value="15.0">
                                <small class="text-muted">GOFO大件</small>
                            </div>
                        </div>
                    </div>

                    <div class="mb-3">
                        <label class="form-label">包裹信息</label>
                        <div class="row g-2 mb-2">
                            <div class="col-4"><input type="number" class="form-control" id="L" placeholder="长(in)"></div>
                            <div class="col-4"><input type="number" class="form-control" id="W" placeholder="宽(in)"></div>
                            <div class="col-4"><input type="number" class="form-control" id="H" placeholder="高(in)"></div>
                        </div>
                        <div class="row g-2">
                            <div class="col-8"><input type="number" class="form-control" id="Wt" placeholder="重量"></div>
                            <div class="col-4">
                                <select class="form-select" id="WtUnit">
                                    <option value="lb">lb</option>
                                    <option value="oz">oz</option>
                                    <option value="kg">kg</option>
                                </select>
                            </div>
                        </div>
                    </div>

                    <button class="btn btn-primary w-100" id="btnCalc">开始计算</button>
                </div>
            </div>
        </div>

        <div class="col-lg-8">
            <div class="card h-100">
                <div class="card-header d-flex justify-content-between">
                    <span>计算结果</span>
                    <span id="resTierBadge" class="badge bg-warning text-dark"></span>
                </div>
                <div class="card-body p-0">
                    <div class="p-2 border-bottom bg-light small" id="pkgSummary">请先输入数据...</div>
                    <div class="table-responsive">
                        <table class="table table-hover m-0">
                            <thead>
                                <tr>
                                    <th>渠道</th>
                                    <th>分区</th>
                                    <th>计费重</th>
                                    <th>基础运费</th>
                                    <th>明细</th>
                                    <th>总费用</th>
                                </tr>
                            </thead>
                            <tbody id="resBody"></tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
    const DATA = __JSON_DATA__;
    document.getElementById('date').innerText = new Date().toLocaleDateString();

    // 初始化仓库
    const whSel = document.getElementById('warehouse');
    DATA.warehouses.forEach(w => {
        let opt = document.createElement('option');
        opt.value = w.id;
        opt.text = w.label;
        whSel.add(opt);
    });

    let CUR_ZONES = {};

    // 标准化重量
    function stdWt(v, unit) {
        v = parseFloat(v) || 0;
        if (unit === 'oz') return v / 16;
        if (unit === 'kg') return v / 0.453592;
        return v;
    }

    // 计算 FedEx Zone (简化版: 3位邮编差)
    function calcFedExZone(dest, origin) {
        if (!dest || dest.length < 3) return null;
        let d = parseInt(dest.substring(0,3));
        let o = parseInt(origin.substring(0,3));
        let diff = Math.abs(d - o);
        // 简单模拟: 实际应使用完整 Zone 表
        if (diff < 5) return 2;
        if (diff < 20) return 3;
        if (diff < 40) return 4;
        if (diff < 60) return 5;
        if (diff < 80) return 6;
        if (diff < 90) return 7;
        return 8;
    }

    function calc() {
        const zip = document.getElementById('zipCode').value.trim();
        const tier = document.querySelector('input[name="tier"]:checked').value;
        const whId = whSel.value;
        const wh = DATA.warehouses.find(w => w.id === whId);
        const isRes = document.getElementById('addressType').value === 'res';
        const isSig = document.getElementById('sigToggle').checked;
        
        const pkg = {
            L: parseFloat(document.getElementById('L').value)||0,
            W: parseFloat(document.getElementById('W').value)||0,
            H: parseFloat(document.getElementById('H').value)||0,
            Wt: stdWt(document.getElementById('Wt').value, document.getElementById('WtUnit').value)
        };

        if (pkg.Wt <= 0) return;

        document.getElementById('resTierBadge').innerText = tier;
        document.getElementById('pkgSummary').innerHTML = `<b>${pkg.L}x${pkg.W}x${pkg.H}"</b> | 实重: ${pkg.Wt.toFixed(2)} lb`;

        const tbody = document.getElementById('resBody');
        tbody.innerHTML = '';

        if (!wh.enabled) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-muted">该仓库暂不支持在线报价</td></tr>';
            return;
        }

        const tierData = DATA.tiers[tier];
        if (!tierData) return;

        // 遍历所有渠道
        for (let ch in DATA.channel_allow) {
            // 1. 检查仓库权限
            if (!DATA.channel_allow[ch].includes(wh.region)) continue;

            // 2. 准备数据
            let chData = tierData[ch];
            if (!chData && ch !== "GOFO、UNIUNI-MT-报价") continue; // Combo 特殊处理

            // 处理 Combo (拆分成两行)
            let subChannels = [];
            if (ch === "GOFO、UNIUNI-MT-报价") {
                if (tierData[ch]) {
                    subChannels.push({name: "GOFO-MT", data: tierData[ch].gofo});
                    subChannels.push({name: "UNIUNI-MT", data: tierData[ch].uni});
                }
            } else {
                subChannels.push({name: ch, data: chData});
            }

            subChannels.forEach(sub => {
                let prices = (sub.data.type === 'dual') ? (isRes ? sub.data.res : sub.data.com) : sub.data.prices;
                if (!prices) return;

                // 3. 确定 Zone
                let zone = '-';
                if (ch.includes('FedEx') || ch.includes('XLmiles') || ch.includes('GOFO大件')) {
                    // 使用计算 Zone (需完善算法，暂时模拟)
                    let z = calcFedExZone(zip, wh.zip);
                    if (z) zone = z.toString();
                } else {
                    // 使用查表 Zone
                    if (CUR_ZONES[ch]) zone = CUR_ZONES[ch];
                }

                // 4. 计算计费重
                let dimW = (pkg.L * pkg.W * pkg.H) / 250; // 默认除250? 根据规则调整
                // UNIUNI 无体积重
                if (sub.name.includes('UNIUNI')) dimW = 0;
                // FedEx/GOFO 一般 250 或 139? 假设 250 (原代码逻辑未细化，暂定)
                if (ch.includes('ECO')) dimW = (pkg.L * pkg.W * pkg.H) / 250; 
                
                let billWt = Math.max(pkg.Wt, dimW);
                billWt = Math.ceil(billWt); // 向上取整

                // 5. 查基础价
                let basePrice = 0;
                let zoneKey = zone;
                // 修正 Zone 映射 (例如 Excel 表头是 2,3,4...)
                if (zone == '1') zoneKey = '2'; 

                let row = prices.find(p => p.w >= billWt);
                if (row && row[zoneKey]) basePrice = row[zoneKey];

                if (basePrice > 0) {
                    let total = basePrice;
                    let details = [];

                    // 住宅费
                    if (isRes && DATA.fees.res[ch]) {
                        let rf = DATA.fees.res[ch];
                        total += rf;
                        details.push(`住宅:${rf}`);
                    }

                    // 签名费
                    if (isSig && DATA.fees.sig[ch]) {
                        let sf = DATA.fees.sig[ch];
                        total += sf;
                        details.push(`签名:${sf}`);
                    }

                    // 燃油费
                    if (DATA.fuel_config.channels.includes(ch)) {
                        let rate = 0;
                        if (ch.includes('GOFO大件')) {
                            rate = parseFloat(document.getElementById('gofoFuel').value) / 100;
                            // GOFO大件公式: (运费+杂费) * 燃油率
                            let fuelAmt = total * rate; 
                            total += fuelAmt;
                            details.push(`燃油:${fuelAmt.toFixed(2)}`);
                        } else {
                            rate = parseFloat(document.getElementById('fedexFuel').value) / 100;
                            if (DATA.fuel_config.discount_85.includes(ch)) {
                                rate = rate * 0.85;
                            }
                            // FedEx: 基础运费 * 燃油率
                            let fuelAmt = basePrice * rate;
                            total += fuelAmt;
                            details.push(`燃油:${fuelAmt.toFixed(2)}`);
                        }
                    }

                    tbody.innerHTML += `
                        <tr>
                            <td class="text-start fw-bold">${sub.name}</td>
                            <td>Z${zone}</td>
                            <td>${billWt}</td>
                            <td>${basePrice.toFixed(2)}</td>
                            <td class="small text-muted text-start">${details.join(' | ') || '-'}</td>
                            <td class="price-text">$${total.toFixed(2)}</td>
                        </tr>
                    `;
                }
            });
        }
    }

    // 事件绑定
    document.getElementById('btnLookup').onclick = () => {
        let z = document.getElementById('zipCode').value.trim();
        if (DATA.zip_db[z]) {
            let i = DATA.zip_db[z];
            document.getElementById('locInfo').innerText = `✅ ${i.s} - ${i.c}`;
            CUR_ZONES = i.z;
        } else {
            document.getElementById('locInfo').innerText = "❌ 未找到";
            CUR_ZONES = {};
        }
    };

    document.getElementById('btnCalc').onclick = calc;
    document.querySelectorAll('.tier-radio').forEach(r => r.onchange = () => {
        if(document.getElementById('Wt').value) calc();
    });

</script>
</body>
</html>
    """
    
    html = html.replace('__JSON_DATA__', json.dumps(data, ensure_ascii=False))
    
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    
    print("✅ V20 生成完成")

if __name__ == '__main__':
    load_data()
