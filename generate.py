import pandas as pd
import json
import re
import os
import warnings

# 忽略 Excel 读取警告
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# ================= 配置区域 =================
DATA_DIR = "data"
OUTPUT_DIR = "public"

TIER_FILES = {
    "T0": "T0.xlsx", "T1": "T1.xlsx", "T2": "T2.xlsx", "T3": "T3.xlsx"
}

CHANNEL_SHEET_MAP = {
    "GOFO-报价": "GOFO-报价",
    "GOFO-MT-报价": "GOFO-MT-报价",
    "UNIUNI-MT-报价": "UNIUNI-MT-报价",
    "USPS-YSD-报价": "USPS-YSD-报价",
    "FedEx-ECO-MT报价": "FedEx-ECO-MT报价",
    "XLmiles-报价": "XLmiles-报价",
    "GOFO大件-GRO-报价": "GOFO大件-GRO-报价",
    "FedEx-632-MT-报价": "FedEx-632-MT-报价",
    "FedEx-YSD-报价": "FedEx-YSD-报价"
}

ZIP_DB_SHEET = "GOFO-报价"
ZIP_COL_MAP = {
    "GOFO-报价": 5, "GOFO-MT-报价": 6, "UNIUNI-MT-报价": 7, "USPS-YSD-报价": 8,
    "FedEx-ECO-MT报价": 9, "XLmiles-报价": 10, "GOFO大件-GRO-报价": 11,
    "FedEx-632-MT-报价": 12, "FedEx-YSD-报价": 13
}

GLOBAL_SURCHARGES = {
    "fuel": 0.16, "res_fee": 3.50, "peak_res": 1.32,
    "peak_oversize": 54, "peak_unauthorized": 220,
    "oversize_fee": 130, "ahs_fee": 20, "unauthorized_fee": 1150
}

# ================= HTML 模板 (含修复后的 JS 逻辑) =================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>业务员报价助手 (Sales Calculator)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        :root { --primary-color: #0d6efd; --header-bg: #000; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background-color: #f4f6f9; display: flex; flex-direction: column; min-height: 100vh; }
        header { background-color: var(--header-bg); color: #fff; padding: 15px 0; }
        footer { background-color: var(--header-bg); color: #888; padding: 20px 0; margin-top: auto; text-align: center; font-size: 0.85em; }
        .card { border: none; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 20px; }
        .btn-calc { background-color: var(--primary-color); border: none; font-weight: bold; padding: 12px; }
        .badge-zone { font-size: 0.9em; background-color: #e9ecef; color: #000; padding: 5px 10px; border-radius: 4px; }
        .result-table th { background-color: #212529; color: #fff; text-align: center; vertical-align: middle; }
        .result-table td { text-align: center; vertical-align: middle; font-size: 0.95em; }
        .price-main { font-weight: 800; font-size: 1.1em; color: var(--primary-color); }
        .status-ok { color: #198754; font-weight: bold; }
        .status-warn { color: #ffc107; font-weight: bold; }
        .status-error { color: #dc3545; font-weight: bold; }
    </style>
</head>
<body>

<header>
    <div class="container d-flex justify-content-between align-items-center">
        <div><h4 class="m-0">📦 业务员报价助手</h4><small style="opacity: 0.7;">T0-T3 全渠道集成版 (Fix v2)</small></div>
        <div class="text-end"><span class="badge bg-secondary">已修复 USPS/FedEx</span></div>
    </div>
</header>

<div class="container my-4">
    <div class="row"><div class="col-lg-12">
        <div class="card">
            <div class="card-header text-white" style="background-color: #343a40;">⚙️ 参数配置</div>
            <div class="card-body">
                <form id="calcForm">
                    <div class="row mb-4">
                        <div class="col-md-5">
                            <label class="form-label fw-bold">1. 客户等级</label>
                            <div class="bg-light p-2 rounded border">
                                <div class="form-check form-check-inline"><input class="form-check-input" type="radio" name="tier" id="t0" value="T0"><label class="form-check-label" for="t0">T0 (VIP)</label></div>
                                <div class="form-check form-check-inline"><input class="form-check-input" type="radio" name="tier" id="t1" value="T1"><label class="form-check-label" for="t1">T1</label></div>
                                <div class="form-check form-check-inline"><input class="form-check-input" type="radio" name="tier" id="t2" value="T2"><label class="form-check-label" for="t2">T2</label></div>
                                <div class="form-check form-check-inline"><input class="form-check-input" type="radio" name="tier" id="t3" value="T3" checked><label class="form-check-label" for="t3">T3 (常规)</label></div>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label fw-bold">2. 地址属性</label>
                            <select class="form-select" id="addressType"><option value="residential">🏠 住宅地址 (Res)</option><option value="commercial">🏢 商业地址 (Com)</option></select>
                        </div>
                        <div class="col-md-2"><label class="form-label fw-bold">旺季费</label><div class="form-check form-switch mt-2"><input class="form-check-input" type="checkbox" id="peakToggle"><label class="form-check-label" for="peakToggle">启用</label></div></div>
                        <div class="col-md-2"><label class="form-label fw-bold">燃油费率 %</label><input type="number" class="form-control" id="fuelRate" step="0.01" value="__FUEL__"></div>
                    </div>
                    <hr class="text-muted">
                    <div class="row g-3">
                        <div class="col-md-4 border-end">
                            <label class="form-label fw-bold">3. 邮编 (Zip)</label>
                            <div class="input-group"><input type="text" class="form-control" id="zipCode" placeholder="输入5位邮编"><button class="btn btn-dark" type="button" id="btnLookup">查询</button></div>
                            <div id="locInfo" class="mt-2 small fw-bold text-muted">请输入邮编查询...</div>
                        </div>
                        <div class="col-md-8">
                            <label class="form-label fw-bold">4. 包裹规格</label>
                            <div class="row g-2">
                                <div class="col-3"><div class="input-group input-group-sm"><span class="input-group-text">L</span><input type="number" class="form-control" id="length" placeholder="长"></div></div>
                                <div class="col-3"><div class="input-group input-group-sm"><span class="input-group-text">W</span><input type="number" class="form-control" id="width" placeholder="宽"></div></div>
                                <div class="col-3"><div class="input-group input-group-sm"><span class="input-group-text">H</span><input type="number" class="form-control" id="height" placeholder="高"></div></div>
                                <div class="col-3"><select class="form-select form-select-sm" id="dimUnit"><option value="in">inch</option><option value="cm">cm</option><option value="mm">mm</option></select></div>
                                <div class="col-6 mt-2"><div class="input-group"><span class="input-group-text">实重</span><input type="number" class="form-control" id="weight" placeholder="Weight"></div></div>
                                <div class="col-6 mt-2"><select class="form-select" id="weightUnit"><option value="lb">lb (磅)</option><option value="kg">kg (千克)</option><option value="oz">oz</option><option value="g">g</option></select></div>
                            </div>
                        </div>
                    </div>
                    <div class="d-grid mt-4"><button type="button" class="btn btn-primary btn-calc btn-lg text-white" id="btnCalc">计算报价 (Calculate)</button></div>
                </form>
            </div>
        </div>
    </div></div>

    <div class="row" id="resultSection" style="display:none;">
        <div class="col-12"><div class="card">
            <div class="card-header d-flex justify-content-between align-items-center"><span>📊 报价结果</span><span id="resTierBadge" class="badge bg-warning text-dark"></span></div>
            <div class="card-body">
                <div class="alert alert-info py-2" id="pkgSummary"></div>
                <div class="table-responsive">
                    <table class="table table-bordered table-hover result-table">
                        <thead><tr><th width="15%">渠道</th><th width="5%">分区</th><th width="8%">计费重</th><th width="10%">基础运费</th><th width="10%">燃油费</th><th width="10%">旺季费</th><th width="10%">住宅/其他</th><th width="10%">超规费</th><th width="12%">总费用($)</th><th width="10%">状态</th></tr></thead>
                        <tbody id="resBody"></tbody>
                    </table>
                </div>
            </div>
        </div></div>
    </div>
</div>

<footer><div class="container"><small>&copy; 2026 速狗海外仓报价系统</small></div></footer>

<script>
    const DATA = __JSON_DATA__;
    let CUR_ZONES = {};

    function convertToStandard(l, w, h, dimUnit, weight, weightUnit) {
        let L = parseFloat(l)||0, W = parseFloat(w)||0, H = parseFloat(h)||0, Wt = parseFloat(weight)||0;
        if (dimUnit === 'cm') { L/=2.54; W/=2.54; H/=2.54; } else if (dimUnit === 'mm') { L/=25.4; W/=25.4; H/=25.4; }
        if (weightUnit === 'kg') Wt /= 0.45359237; else if (weightUnit === 'oz') Wt /= 16; else if (weightUnit === 'g') Wt /= 453.59237;
        return { L, W, H, Wt };
    }

    function getDimWeight(L, W, H, channel) {
        let vol = L * W * H; let divisor = 250;
        if (channel.toLowerCase().includes('fedex')) { divisor = (vol < 1728) ? 400 : 250; }
        return vol / divisor;
    }

    document.getElementById('btnLookup').onclick = function() {
        let zip = document.getElementById('zipCode').value.trim();
        let infoDiv = document.getElementById('locInfo');
        if (!DATA.zip_db[zip]) { infoDiv.innerHTML = "<span class='text-danger'>❌ 未找到该邮编</span>"; CUR_ZONES = {}; return; }
        infoDiv.innerHTML = `<span class='text-success'>📍 ${DATA.zip_db[zip].s} - ${DATA.zip_db[zip].c} (${DATA.zip_db[zip].r})</span>`;
        CUR_ZONES = DATA.zip_db[zip].z;
    };

    document.getElementById('btnCalc').onclick = function() {
        let zip = document.getElementById('zipCode').value.trim();
        if ((!CUR_ZONES || Object.keys(CUR_ZONES).length === 0) && zip) { document.getElementById('btnLookup').click(); }
        
        let tier = document.querySelector('input[name="tier"]:checked').value;
        let pkg = convertToStandard(document.getElementById('length').value, document.getElementById('width').value, document.getElementById('height').value, document.getElementById('dimUnit').value, document.getElementById('weight').value, document.getElementById('weightUnit').value);
        let isPeak = document.getElementById('peakToggle').checked;
        let isRes = document.getElementById('addressType').value === 'residential';
        let globalFuelRate = parseFloat(document.getElementById('fuelRate').value) / 100;
        
        document.getElementById('resultSection').style.display = 'block';
        document.getElementById('resTierBadge').innerText = tier;
        document.getElementById('pkgSummary').innerHTML = `<b>包裹:</b> ${pkg.L.toFixed(1)}x${pkg.W.toFixed(1)}x${pkg.H.toFixed(1)} in | <b>实重:</b> ${pkg.Wt.toFixed(2)} lb`;
        let tbody = document.getElementById('resBody'); tbody.innerHTML = '';
        
        if (!DATA.tiers[tier]) return;
        let channels = Object.keys(DATA.tiers[tier]);
        
        channels.forEach(ch => {
            let chData = DATA.tiers[tier][ch];
            if (!chData.prices) return;
            
            let zoneVal = CUR_ZONES[ch] || '-';
            let dimWt = getDimWeight(pkg.L, pkg.W, pkg.H, ch);
            let chargeWt = Math.ceil(Math.max(pkg.Wt, dimWt));
            let basePrice = 0;
            
            // 修复 Zone 1 逻辑：只有当表中没有 Zone 1 时，才映射到 Zone 2
            // 大部分渠道 Zone 1 = Zone 2，但 USPS 有独立 Zone 1
            let zoneKey = zoneVal;
            // 检查价格表中是否有 '1' 这个key
            let hasZone1 = chData.prices.some(r => r['1'] !== undefined);
            if (zoneKey === '1' && !hasZone1) zoneKey = '2';

            let foundRow = null;
            for (let row of chData.prices) { if (row.w >= chargeWt) { foundRow = row; break; } }
            
            let status = "正常"; let statusClass = "status-ok";
            if (!foundRow || zoneVal === '-') { status = "无分区/超重"; statusClass = "text-muted"; } 
            else { 
                basePrice = foundRow[zoneKey]; 
                if (basePrice === undefined) { 
                    // 如果还没有，尝试回退到 Zone 2 (防止极少数情况)
                    if (zoneKey === '1') basePrice = foundRow['2'];
                }
                if (!basePrice) { status = "缺报价"; statusClass = "status-warn"; basePrice = 0; } 
            }
            
            let fuelFee = 0, peakFee = 0, resFee = 0, otherFee = 0, total = 0;
            if (basePrice > 0) {
                // 修复 USPS 燃油费逻辑：USPS 不收燃油费
                let isUSPS = ch.toLowerCase().includes('usps');
                fuelFee = isUSPS ? 0 : (basePrice * globalFuelRate);
                
                if (isRes) resFee = DATA.surcharges.res_fee;
                
                let dims = [pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
                let longest = dims[0]; let girth = longest + 2*(dims[1]+dims[2]);
                let isOversize = (longest > 96 || girth > 130);
                let isUnauthorized = (longest > 108 || girth > 165 || chargeWt > 150);
                
                if (isPeak) { 
                    if (isRes) peakFee += DATA.surcharges.peak_res; 
                    if (isOversize) peakFee += DATA.surcharges.peak_oversize; 
                    if (isUnauthorized) peakFee += DATA.surcharges.peak_unauthorized; 
                }
                
                if (isUnauthorized) { otherFee += DATA.surcharges.unauthorized_fee; status = "不可发!"; statusClass = "status-error"; } 
                else if (isOversize) { otherFee += DATA.surcharges.oversize_fee; status = "超大件"; statusClass = "status-warn"; } 
                else if (longest > 48) { otherFee += DATA.surcharges.ahs_fee; status = "超长(AHS)"; statusClass = "status-warn"; }
                
                total = basePrice + fuelFee + peakFee + resFee + otherFee;
            }
            let trClass = status.includes("不可发") ? "table-danger" : "";
            tbody.innerHTML += `<tr class="${trClass}"><td class="fw-bold text-start">${ch}</td><td><span class="badge-zone">${zoneVal}</span></td><td>${chargeWt}</td><td>${basePrice.toFixed(2)}</td><td>${fuelFee.toFixed(2)}</td><td>${peakFee.toFixed(2)}</td><td>${(resFee + (isRes ? 0 : 0)).toFixed(2)}</td><td>${otherFee.toFixed(2)}</td><td class="price-main">${total > 0 ? total.toFixed(2) : '-'}</td><td class="${statusClass}">${status}</td></tr>`;
        });
    };
</script>
</body>
</html>
"""

# ==========================================
# 3. 核心逻辑: Excel 解析 (修复版)
# ==========================================

def get_sheet_by_name(excel_file, target_name):
    try:
        # 强制使用 openpyxl
        xl = pd.ExcelFile(excel_file, engine='openpyxl')
        if target_name in xl.sheet_names: return pd.read_excel(xl, sheet_name=target_name, header=None)
        # 模糊匹配
        for sheet in xl.sheet_names:
            if target_name.replace(" ", "").lower() in sheet.replace(" ", "").lower():
                print(f"    > [INFO] Sheet映射: '{sheet}' -> '{target_name}'")
                return pd.read_excel(xl, sheet_name=sheet, header=None)
        print(f"    > [WARN] 未找到 Sheet: {target_name}")
        return None
    except Exception as e:
        print(f"    > [ERROR] 读取 Excel 失败: {e}")
        return None

def load_zip_db():
    print("--- 构建邮编数据库 (T0.xlsx) ---")
    path = os.path.join(DATA_DIR, TIER_FILES['T0'])
    if not os.path.exists(path): print(f"❌ 错误: 找不到 {path}"); return {}
    df = get_sheet_by_name(path, ZIP_DB_SHEET)
    if df is None: return {}
    zip_db = {}
    try:
        start_row = 0
        for i in range(100):
            val = str(df.iloc[i, 1]).strip()
            if val.isdigit() and len(val) == 5: start_row = i; break
        for idx, row in df.iloc[start_row:].iterrows():
            z = str(row[1]).strip()
            if z.isdigit() and len(z) == 5:
                zones = {}
                for ch, col in ZIP_COL_MAP.items():
                    val = str(row[col]).strip()
                    zones[ch] = val if val not in ['-','nan','', 'None'] else None
                zip_db[z] = { "s": str(row[3]).strip(), "c": str(row[4]).strip(), "r": str(row[2]).strip(), "z": zones }
    except Exception as e: print(f"解析邮编出错: {e}")
    print(f"✅ 已加载 {len(zip_db)} 条邮编")
    return zip_db

def load_prices():
    print("\n--- 加载报价表 ---")
    all_data = {}
    for tier, filename in TIER_FILES.items():
        print(f"处理 {tier}...")
        path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(path): continue
        tier_data = {}
        for ch_key, sheet_name in CHANNEL_SHEET_MAP.items():
            df = get_sheet_by_name(path, sheet_name)
            if df is None: continue
            try:
                # 寻找表头
                header_row = 0
                for i in range(30):
                    row_str = " ".join(df.iloc[i].astype(str).values).lower()
                    if "zone" in row_str and ("lb" in row_str or "weight" in row_str or "重量" in row_str):
                        header_row = i; break
                
                headers = df.iloc[header_row].astype(str).str.lower().tolist()
                weight_idx = -1; zone_map = {}
                
                for idx, val in enumerate(headers):
                    if 'weight' in val or 'lb' in val or '重量' in val: 
                        # 修复: FedEx-YSD有左右两个表，我们只取第一个Weight列(住宅)
                        if weight_idx == -1: weight_idx = idx
                    
                    # 修复: 提取 Zone 数字，使用正则精准提取 'Zone 2'，忽略 Pandas 自动加的后缀 '.1'
                    # 例如 'zone 2' -> match group 1 is '2'
                    # 'zone 2.1' -> match group 1 is '2' (regex: zone.*?(\d+))
                    z_match = re.search(r'zone\s*~?\s*(\d+)', val, re.IGNORECASE)
                    if z_match:
                        z_num = z_match.group(1)
                        # 修复: 只记录第一次出现的列 (防止读取到右侧商业表覆盖左侧住宅表)
                        if z_num not in zone_map:
                            zone_map[z_num] = idx

                if weight_idx == -1: continue
                
                prices = []
                for i in range(header_row+1, len(df)):
                    row = df.iloc[i]
                    try:
                        w_val = row[weight_idx]
                        if pd.isna(w_val): continue
                        w_str = str(w_val)
                        if not re.search(r'\d', w_str): continue
                        w = float(re.findall(r"[\d\.]+", w_str)[0])
                        p_row = {'w': w}
                        for z, col in zone_map.items():
                            try:
                                val = row[col]
                                if pd.notna(val) and str(val).replace('.','').isdigit(): p_row[z] = float(val)
                            except: pass
                        prices.append(p_row)
                    except: continue
                tier_data[ch_key] = {"prices": prices}
            except: pass
        all_data[tier] = tier_data
    return all_data

if __name__ == '__main__':
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    final_data = { "zip_db": load_zip_db(), "tiers": load_prices(), "surcharges": GLOBAL_SURCHARGES }
    print("\n--- 生成 index.html ---")
    json_str = json.dumps(final_data)
    final_html = HTML_TEMPLATE.replace('__JSON_DATA__', json_str).replace('__FUEL__', str(GLOBAL_SURCHARGES['fuel']*100))
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f: f.write(final_html)
    print(f"✅ 完成! 文件已生成。")
