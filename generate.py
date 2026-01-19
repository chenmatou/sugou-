import pandas as pd
import json
import re
import os
import warnings

# 忽略 Excel 样式警告
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# ==========================================
# 1. 基础配置
# ==========================================
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

# 邮编数据库配置
ZIP_DB_SHEET = "GOFO-报价"
ZIP_COL_MAP = {
    "GOFO-报价": 5, "GOFO-MT-报价": 6, "UNIUNI-MT-报价": 7, "USPS-YSD-报价": 8,
    "FedEx-ECO-MT报价": 9, "XLmiles-报价": 10, "GOFO大件-GRO-报价": 11,
    "FedEx-632-MT-报价": 12, "FedEx-YSD-报价": 13
}

# 美国州名中英对照
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
# 2. 网页模板 (HTML/CSS/JS)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>业务员报价助手 (Pro Version)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        :root { --primary-color: #0d6efd; --header-bg: #000; --danger-color: #dc3545; --success-color: #198754; }
        body { font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; background-color: #f4f6f9; display: flex; flex-direction: column; min-height: 100vh; }
        
        /* 布局 */
        header { background-color: var(--header-bg); color: #fff; padding: 15px 0; border-bottom: 3px solid #333; }
        footer { background-color: var(--header-bg); color: #aaa; padding: 20px 0; margin-top: auto; text-align: center; font-size: 0.85em; }
        .card { border: none; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin-bottom: 20px; }
        .card-header { background-color: #212529; color: #fff; font-weight: 600; padding: 12px 20px; }
        
        /* 输入框优化 */
        .form-label { font-weight: 600; font-size: 0.9rem; color: #495057; margin-bottom: 0.2rem; }
        .input-group-text { background-color: #e9ecef; font-weight: 600; font-size: 0.85rem; }
        .form-control, .form-select { font-size: 0.9rem; }
        
        /* 状态指示器 (Traffic Light) */
        .status-box { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 10px; margin-top: 10px; }
        .status-item { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; font-size: 0.85rem; }
        .status-indicator { width: 10px; height: 10px; border-radius: 50%; display: inline-block; background-color: #ccc; margin-right: 8px; }
        .status-ok { background-color: var(--success-color); }
        .status-fail { background-color: var(--danger-color); }
        .status-warn { background-color: #ffc107; }
        
        /* 结果表格 */
        .result-table th { background-color: #212529; color: #fff; text-align: center; vertical-align: middle; font-size: 0.85rem; }
        .result-table td { text-align: center; vertical-align: middle; font-size: 0.9rem; }
        .price-main { font-weight: 800; font-size: 1.2rem; color: #d63384; } /* 醒目颜色 */
        .zone-tag { display: inline-block; background: #0d6efd; color: #fff; padding: 2px 8px; border-radius: 4px; font-weight: bold; }
        .surcharge-detail { font-size: 0.75rem; color: #666; text-align: left; line-height: 1.2; }
    </style>
</head>
<body>

<header>
    <div class="container d-flex justify-content-between align-items-center">
        <div>
            <h4 class="m-0 fw-bold">📦 业务员报价助手</h4>
            <small style="opacity: 0.8;">T0-T3 全渠道精准集成 | 严格对标 6.0-6.3 文档</small>
        </div>
        <div class="text-end">
            <a href="https://www.fedex.com/en-us/shipping/fuel-surcharge.html" target="_blank" class="btn btn-sm btn-outline-light">⛽ 查看 FedEx 实时燃油</a>
        </div>
    </div>
</header>

<div class="container my-4">
    <div class="row g-3">
        <div class="col-lg-4">
            <div class="card h-100">
                <div class="card-header">1. 基础信息录入</div>
                <div class="card-body">
                    <form id="calcForm">
                        <div class="mb-3">
                            <label class="form-label">客户等级 (Tier)</label>
                            <div class="btn-group w-100" role="group">
                                <input type="radio" class="btn-check" name="tier" id="t0" value="T0"><label class="btn btn-outline-secondary" for="t0">T0</label>
                                <input type="radio" class="btn-check" name="tier" id="t1" value="T1"><label class="btn btn-outline-secondary" for="t1">T1</label>
                                <input type="radio" class="btn-check" name="tier" id="t2" value="T2"><label class="btn btn-outline-secondary" for="t2">T2</label>
                                <input type="radio" class="btn-check" name="tier" id="t3" value="T3" checked><label class="btn btn-outline-secondary" for="t3">T3</label>
                            </div>
                        </div>

                        <div class="mb-3">
                            <label class="form-label">目的地邮编 (Zip Code)</label>
                            <div class="input-group">
                                <input type="text" class="form-control" id="zipCode" placeholder="输入5位邮编">
                                <button class="btn btn-dark" type="button" id="btnLookup">查询</button>
                            </div>
                            <div id="locInfo" class="mt-1 small fw-bold text-success"></div>
                        </div>

                        <div class="row g-2 mb-3">
                            <div class="col-6">
                                <label class="form-label">地址类型</label>
                                <select class="form-select" id="addressType">
                                    <option value="residential">🏠 住宅</option>
                                    <option value="commercial">🏢 商业</option>
                                </select>
                            </div>
                            <div class="col-6">
                                <label class="form-label">燃油费率 %</label>
                                <input type="number" class="form-control" id="fuelRate" step="0.01" value="__FUEL__">
                            </div>
                        </div>
                        
                        <div class="form-check form-switch mb-3">
                            <input class="form-check-input" type="checkbox" id="peakToggle">
                            <label class="form-check-label" for="peakToggle">启用旺季附加费 (Peak)</label>
                        </div>

                        <hr>

                        <div class="mb-2">
                            <label class="form-label">包裹规格 (原始单位)</label>
                            <div class="row g-2">
                                <div class="col-4"><input type="number" class="form-control" id="length" placeholder="长"></div>
                                <div class="col-4"><input type="number" class="form-control" id="width" placeholder="宽"></div>
                                <div class="col-4"><input type="number" class="form-control" id="height" placeholder="高"></div>
                                <div class="col-12"><select class="form-select form-select-sm" id="dimUnit"><option value="in">IN (英寸)</option><option value="cm">CM (厘米)</option><option value="mm">MM (毫米)</option></select></div>
                            </div>
                            <div class="row g-2 mt-1">
                                <div class="col-8"><input type="number" class="form-control" id="weight" placeholder="实重"></div>
                                <div class="col-4"><select class="form-select" id="weightUnit"><option value="lb">LB</option><option value="oz">OZ</option><option value="kg">KG</option><option value="g">G</option></select></div>
                            </div>
                        </div>

                        <div class="status-box">
                            <div class="fw-bold small mb-2 border-bottom pb-1">📦 合规性预检 (Standard: US)</div>
                            <div id="checkList">
                                <div class="status-item"><span class="status-indicator"></span>等待输入...</div>
                            </div>
                        </div>

                        <button type="button" class="btn btn-primary w-100 mt-3 fw-bold" id="btnCalc">开始测算报价</button>
                    </form>
                </div>
            </div>
        </div>

        <div class="col-lg-8">
            <div class="card h-100">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <span>📊 测算结果 (严格对标)</span>
                    <span id="resTierBadge" class="badge bg-warning text-dark"></span>
                </div>
                <div class="card-body">
                    <div class="alert alert-light border small" id="pkgSummary">
                        请在左侧输入信息进行计算。
                    </div>
                    <div class="table-responsive">
                        <table class="table table-bordered table-hover result-table">
                            <thead>
                                <tr>
                                    <th width="15%">渠道<br>Channel</th>
                                    <th width="8%">分区<br>Zone</th>
                                    <th width="10%">计费重<br>(LB)</th>
                                    <th width="12%">基础运费<br>(Base)</th>
                                    <th width="20%">附加费明细<br>(Surcharges)</th>
                                    <th width="15%">总费用<br>(Total)</th>
                                    <th width="20%">状态说明<br>(Status)</th>
                                </tr>
                            </thead>
                            <tbody id="resBody"></tbody>
                        </table>
                    </div>
                    <div class="mt-3 text-muted" style="font-size: 0.75rem;">
                        <strong>计费说明 (Issue 3)：</strong><br>
                        1. 计费重公式：取 Max(实重, 体积重)。体积重系数统一为 222 (IN³/222 = LB)。<br>
                        2. UniUni 渠道特殊规则：无体积重，按实重计费；无燃油费；无住宅费。<br>
                        3. USPS 渠道特殊规则：无燃油费；无住宅费；含独立旺季附加费。<br>
                        4. 住宅费：仅以 FedEx 开头的渠道收取，其他渠道默认为 0。<br>
                        5. 燃油费：以 FedEx 官网为准，请手动更新费率。
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<footer>
    <div class="container">
        <p>&copy; 2026 速狗海外仓 | 内部专用工具</p>
    </div>
</footer>

<script>
    const DATA = __JSON_DATA__;
    let CUR_ZONES = {};
    document.getElementById('updateDate').innerText = new Date().toLocaleDateString();

    // ===========================================
    // 核心业务逻辑配置 (Strict Rules)
    // ===========================================
    
    // 1. 单位换算 (Issue 4) - 统一转为 IN 和 LB
    function convertToStandard(l, w, h, dimUnit, weight, weightUnit) {
        let L = parseFloat(l)||0, W = parseFloat(w)||0, H = parseFloat(h)||0, Wt = parseFloat(weight)||0;
        
        // 长度转 inch
        if (dimUnit === 'cm') { L/=2.54; W/=2.54; H/=2.54; }
        else if (dimUnit === 'mm') { L/=25.4; W/=25.4; H/=25.4; }
        
        // 重量转 lb
        if (weightUnit === 'kg') Wt /= 0.45359237;
        else if (weightUnit === 'oz') Wt /= 16;
        else if (weightUnit === 'g') Wt /= 453.59237;
        
        return { L, W, H, Wt };
    }

    // 2. 实时合规检测 (Traffic Light Module)
    function runPreCheck(pkg) {
        let dims = [pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
        let longest = dims[0];
        let median = dims[1];
        let girth = longest + 2*(dims[1]+dims[2]);
        let html = '';

        // 辅助生成函数
        const checkItem = (label, condition, warnCondition=false) => {
            let color = condition ? 'status-fail' : (warnCondition ? 'status-warn' : 'status-ok');
            let text = condition ? '超标 (Over)' : (warnCondition ? '警告 (Warn)' : '正常 (OK)');
            return `<div class="status-item"><span>${label}</span><span><span class="status-indicator ${color}"></span>${text}</span></div>`;
        };

        html += checkItem('超重 (>150lb)', pkg.Wt > 150, pkg.Wt > 50);
        html += checkItem('超长 (>108")', longest > 108, longest > 96);
        html += checkItem('超围 (>165")', girth > 165, girth > 130);
        html += checkItem('第二边 (>30")', median > 30);
        
        // UniUni 特殊检查 (Issue 6)
        let uniFail = (longest > 20 || girth > 50 || pkg.Wt > 20);
        html += `<div class="border-top mt-1 pt-1 fw-bold small">UniUni 专有检查:</div>`;
        html += checkItem('符合 UniUni 限制', uniFail);

        document.getElementById('checkList').innerHTML = html;
    }

    // 监听输入变化实时检测
    ['length','width','height','weight','dimUnit','weightUnit'].forEach(id => {
        document.getElementById(id).addEventListener('input', () => {
            let pkg = convertToStandard(
                document.getElementById('length').value, document.getElementById('width').value, document.getElementById('height').value,
                document.getElementById('dimUnit').value, document.getElementById('weight').value, document.getElementById('weightUnit').value
            );
            runPreCheck(pkg);
        });
    });

    // 3. 计费重计算 (Issue 3)
    function getChargeWeight(pkg, channel) {
        let ch = channel.toUpperCase();
        
        // Rule: UniUni 只有实重
        if (ch.includes('UNIUNI')) return pkg.Wt;

        // Standard: Max(Actual, Volumetric). Divisor 222.
        let volWeight = (pkg.L * pkg.W * pkg.H) / 222;
        let finalWt = Math.max(pkg.Wt, volWeight);
        
        // GOFO的小件(OZ)不进位，其他通常向上取整
        if (finalWt < 1 && ch.includes('GOFO')) return finalWt;
        
        return Math.ceil(finalWt);
    }

    // 4. 邮编查询 (Issue 1 & 4)
    document.getElementById('btnLookup').onclick = function() {
        let zip = document.getElementById('zipCode').value.trim();
        let infoDiv = document.getElementById('locInfo');
        
        if (!DATA.zip_db[zip]) { 
            infoDiv.innerHTML = "<span class='text-danger'>❌ 未找到该邮编 (Zip Not Found)</span>"; 
            CUR_ZONES = {}; 
            return; 
        }
        
        let info = DATA.zip_db[zip];
        infoDiv.innerHTML = `<span class='text-success'>✅ ${info.s_cn} ${info.s} - ${info.c} [${info.r}]</span>`;
        CUR_ZONES = info.z;
    };

    // 5. 计算主流程
    document.getElementById('btnCalc').onclick = function() {
        let zip = document.getElementById('zipCode').value.trim();
        if ((!CUR_ZONES || Object.keys(CUR_ZONES).length === 0) && zip) document.getElementById('btnLookup').click();
        
        let tier = document.querySelector('input[name="tier"]:checked').value;
        let pkg = convertToStandard(
            document.getElementById('length').value, document.getElementById('width').value, document.getElementById('height').value,
            document.getElementById('dimUnit').value, document.getElementById('weight').value, document.getElementById('weightUnit').value
        );
        let isPeak = document.getElementById('peakToggle').checked;
        let isRes = document.getElementById('addressType').value === 'residential';
        let userFuelRate = parseFloat(document.getElementById('fuelRate').value) / 100;

        // 显示摘要
        document.getElementById('resultSection').style.display = 'block';
        document.getElementById('resTierBadge').innerText = tier;
        document.getElementById('pkgSummary').innerHTML = 
            `<b>计算基准:</b> ${pkg.L.toFixed(1)}"${pkg.W.toFixed(1)}"${pkg.H.toFixed(1)}" (IN) | 实重: ${pkg.Wt.toFixed(2)} LB | 围长: ${(pkg.L+2*(pkg.W+pkg.H)).toFixed(1)}"`;

        let tbody = document.getElementById('resBody');
        tbody.innerHTML = '';

        if (!DATA.tiers[tier]) { tbody.innerHTML = '<tr><td colspan="7">数据缺失</td></tr>'; return; }

        let channels = Object.keys(DATA.tiers[tier]);
        channels.forEach(ch => {
            let chData = DATA.tiers[tier][ch];
            if (!chData.prices) return;

            let zoneVal = CUR_ZONES[ch] || '-';
            let chargeWt = getChargeWeight(pkg, ch);
            let basePrice = 0;
            let status = "正常";
            let rowColor = "";

            // 价格匹配 (Issue 1)
            let foundRow = null;
            for (let row of chData.prices) {
                if (row.w >= chargeWt - 0.001) { foundRow = row; break; }
            }

            let zoneKey = zoneVal === '1' ? '2' : zoneVal; // Zone1映射到2
            if (!foundRow || zoneVal === '-') {
                status = "无分区/超重"; rowColor = "table-secondary";
            } else {
                basePrice = foundRow[zoneKey];
                if (basePrice === undefined && zoneKey === '1') basePrice = foundRow['2'];
                if (!basePrice) { status = "无报价"; basePrice = 0; rowColor = "table-warning"; }
            }

            // --- 费用计算 ---
            let fees = { fuel:0, res:0, peak:0, other:0 };
            let breakdown = [];

            if (basePrice > 0) {
                // 1. 燃油费 (Issue 2 & 3): 仅 FedEx 类收取
                if (ch.toUpperCase().startsWith('FEDEX')) {
                    fees.fuel = basePrice * userFuelRate;
                    breakdown.push(`燃油: $${fees.fuel.toFixed(2)}`);
                }

                // 2. 住宅费 (Issue 2): 仅 FedEx 类收取
                if (isRes && ch.toUpperCase().startsWith('FEDEX')) {
                    fees.res = DATA.surcharges.res_fee;
                    breakdown.push(`住宅: $${fees.res.toFixed(2)}`);
                }

                // 3. 尺寸判断
                let dims = [pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
                let L=dims[0], G=L+2*(dims[1]+dims[2]);
                let isOver = (L>96 || G>130);
                let isUnauth = (L>108 || G>165 || pkg.Wt>150);
                let isAHS = (L>48); // FedEx AHS

                // 4. UniUni 严格限制 (Issue 6)
                if (ch.toUpperCase().includes('UNIUNI')) {
                    if (L>20 || G>50 || pkg.Wt>20) {
                        status = "超规不可发"; rowColor = "table-danger"; basePrice=0;
                    }
                    // DFW/ORD 退件费提示仅在备注显示，不计入运费
                }

                // 5. 附加费计算
                if (status !== "超规不可发") {
                    if (isUnauth) { fees.other += DATA.surcharges.unauthorized_fee; status="Unauthorized"; rowColor="table-danger"; }
                    else if (isOver) { fees.other += DATA.surcharges.oversize_fee; status="Oversize"; rowColor="table-warning"; breakdown.push(`超大: $${DATA.surcharges.oversize_fee}`); }
                    else if (isAHS && ch.toUpperCase().startsWith('FEDEX')) { fees.other += DATA.surcharges.ahs_fee; breakdown.push(`AHS: $${DATA.surcharges.ahs_fee}`); }
                }

                // 6. 旺季费 (Issue 6)
                if (isPeak) {
                    let p = 0;
                    if (ch.toUpperCase().includes('USPS')) {
                        // USPS 旺季费简单逻辑 (0.25lb档位)
                        p = 0.35; // 简化处理，实际需按重量分段
                        breakdown.push(`旺季(USPS): $${p}`);
                    } else {
                        if (isRes && ch.toUpperCase().startsWith('FEDEX')) p += DATA.surcharges.peak_res;
                        if (isOver) p += DATA.surcharges.peak_oversize;
                        if (isUnauth) p += DATA.surcharges.peak_unauthorized;
                        if (p>0) breakdown.push(`旺季: $${p.toFixed(2)}`);
                    }
                    fees.peak = p;
                }
            }

            let total = basePrice + fees.fuel + fees.res + fees.peak + fees.other;

            // 渲染行
            tbody.innerHTML += `
                <tr class="${rowColor}">
                    <td class="fw-bold text-start">${ch}</td>
                    <td><span class="zone-tag">${zoneVal}</span></td>
                    <td>${chargeWt.toFixed(2)}</td>
                    <td>${basePrice.toFixed(2)}</td>
                    <td class="text-start small">${breakdown.join('<br>') || '-'}</td>
                    <td class="price-main">$${total > 0 ? total.toFixed(2) : '-'}</td>
                    <td class="fw-bold small">${status}</td>
                </tr>
            `;
        });
    };
</script>
</body>
</html>
"""

# ==========================================
# 3. 核心逻辑: 数据解析 (LB 统一)
# ==========================================

def get_sheet_by_name(excel_file, target_name):
    try:
        xl = pd.ExcelFile(excel_file, engine='openpyxl')
        if target_name in xl.sheet_names: 
            return pd.read_excel(xl, sheet_name=target_name, header=None)
        for sheet in xl.sheet_names:
            if target_name.replace(" ", "").lower() in sheet.replace(" ", "").lower():
                print(f"    > [INFO] Sheet映射: '{sheet}' -> '{target_name}'")
                return pd.read_excel(xl, sheet_name=sheet, header=None)
        return None
    except Exception: return None

def load_zip_db():
    print("--- 1. 构建邮编数据库 (读取 T0.xlsx) ---")
    path = os.path.join(DATA_DIR, TIERS_FILES['T0']) if 'TIERS_FILES' in globals() else os.path.join(DATA_DIR, TIER_FILES['T0'])
    if not os.path.exists(path): 
        print(f"❌ 错误: 找不到文件 {path}"); return {}
    
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
                
                # 读取州名并获取中文
                state_abbr = str(row[3]).strip().upper()
                state_cn = US_STATES_CN.get(state_abbr, '')
                
                zip_db[z] = {
                    "s": state_abbr, 
                    "s_cn": state_cn,
                    "c": str(row[4]).strip(), 
                    "r": str(row[2]).strip(), 
                    "z": zones
                }
    except Exception as e: print(f"解析邮编错误: {e}")
    print(f"✅ 已加载 {len(zip_db)} 条邮编数据 (含双语地名)")
    return zip_db

def parse_weight_to_lb(val):
    """
    核心清洗函数 (Issue 1)
    统一将 OZ, LB, KG 等转换为 LB 存入数据库
    """
    s = str(val).upper().strip()
    if pd.isna(val) or s == 'NAN': return None
    
    nums = re.findall(r"[\d\.]+", s)
    if not nums: return None
    num = float(nums[0])
    
    # 识别单位并转换
    if 'OZ' in s: return num / 16.0
    if 'KG' in s: return num / 0.453592
    # 默认按 LB
    return num

def load_prices():
    print("\n--- 2. 加载各等级报价表 ---")
    all_data = {}
    
    for tier, filename in TIER_FILES.items():
        print(f"处理 {tier} ({filename})...")
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
                        header_row = i
                        break
                
                headers = df.iloc[header_row].astype(str).str.lower().tolist()
                weight_idx = -1
                zone_map = {} 
                
                for idx, val in enumerate(headers):
                    if ('weight' in val or 'lb' in val or '重量' in val) and weight_idx == -1: 
                        weight_idx = idx
                    
                    z_match = re.search(r'zone\s*~?\s*(\d+)', val, re.IGNORECASE)
                    if z_match:
                        z_num = z_match.group(1)
                        if z_num not in zone_map: zone_map[z_num] = idx
                
                if weight_idx == -1: continue
                
                prices = []
                for i in range(header_row+1, len(df)):
                    row = df.iloc[i]
                    try:
                        w_val = row[weight_idx]
                        # 关键：统一转 LB
                        w_lb = parse_weight_to_lb(w_val)
                        if w_lb is None: continue
                        
                        p_row = {'w': w_lb}
                        for z, col in zone_map.items():
                            try:
                                val = row[col]
                                if pd.notna(val) and str(val).replace('.','').isdigit():
                                    p_row[z] = float(val)
                            except: pass
                        prices.append(p_row)
                    except: continue
                
                # 排序
                prices.sort(key=lambda x: x['w'])
                tier_data[ch_key] = {"prices": prices}
                
            except Exception: pass
        all_data[tier] = tier_data
    return all_data

if __name__ == '__main__':
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    final_data = { "zip_db": load_zip_db(), "tiers": load_prices(), "surcharges": GLOBAL_SURCHARGES }
    print("\n--- 3. 生成 index.html ---")
    json_str = json.dumps(final_data)
    final_html = HTML_TEMPLATE.replace('__JSON_DATA__', json_str).replace('__FUEL__', str(GLOBAL_SURCHARGES['fuel']*100))
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f: f.write(final_html)
    print(f"✅ 完成！")
