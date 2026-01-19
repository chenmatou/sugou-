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

ZIP_DB_SHEET = "GOFO-报价"
ZIP_COL_MAP = {
    "GOFO-报价": 5, "GOFO-MT-报价": 6, "UNIUNI-MT-报价": 7, "USPS-YSD-报价": 8,
    "FedEx-ECO-MT报价": 9, "XLmiles-报价": 10, "GOFO大件-GRO-报价": 11,
    "FedEx-632-MT-报价": 12, "FedEx-YSD-报价": 13
}

# 全局附加费 (T3为基准)
GLOBAL_SURCHARGES = {
    "fuel": 0.16, "res_fee": 3.50, "peak_res": 1.32,
    "peak_oversize": 54, "peak_unauthorized": 220,
    "oversize_fee": 130, "ahs_fee": 20, "unauthorized_fee": 1150
}

# 美国州名中英对照表
US_STATES_CN = {
    'AL': '阿拉巴马州', 'AK': '阿拉斯加州', 'AZ': '亚利桑那州', 'AR': '阿肯色州', 'CA': '加利福尼亚州',
    'CO': '科罗拉多州', 'CT': '康涅狄格州', 'DE': '特拉华州', 'FL': '佛罗里达州', 'GA': '佐治亚州',
    'HI': '夏威夷州', 'ID': '爱达荷州', 'IL': '伊利诺伊州', 'IN': '印第安纳州', 'IA': '爱荷华州',
    'KS': '堪萨斯州', 'KY': '肯塔基州', 'LA': '路易斯安那州', 'ME': '缅因州', 'MD': '马里兰州',
    'MA': '马萨诸塞州', 'MI': '密歇根州', 'MN': '明尼苏达州', 'MS': '密西西比州', 'MO': '密苏里州',
    'MT': '蒙大拿州', 'NE': '内布拉斯加州', 'NV': '内华达州', 'NH': '新罕布什尔州', 'NJ': '新泽西州',
    'NM': '新墨西哥州', 'NY': '纽约州', 'NC': '北卡罗来纳州', 'ND': '北达科他州', 'OH': '俄亥俄州',
    'OK': '俄克拉荷马州', 'OR': '俄勒冈州', 'PA': '宾夕法尼亚州', 'RI': '罗德岛州', 'SC': '南卡罗来纳州',
    'SD': '南达科他州', 'TN': '田纳西州', 'TX': '德克萨斯州', 'UT': '犹他州', 'VT': '佛蒙特州',
    'VA': '弗吉尼亚州', 'WA': '华盛顿州', 'WV': '西弗吉尼亚州', 'WI': '威斯康星州', 'WY': '怀俄明州',
    'DC': '华盛顿特区'
}

# ==========================================
# 2. 网页模板 (含严格的 JS 计算逻辑)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>业务员报价助手 (Ultimate Version)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        :root { --primary-color: #0d6efd; --header-bg: #000; }
        body { font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; background-color: #f4f6f9; display: flex; flex-direction: column; min-height: 100vh; }
        
        header { background-color: var(--header-bg); color: #fff; padding: 15px 0; border-bottom: 3px solid #333; }
        footer { background-color: var(--header-bg); color: #aaa; padding: 20px 0; margin-top: auto; text-align: center; font-size: 0.85em; }
        
        .card { border: none; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin-bottom: 20px; }
        .card-header { background-color: #212529; color: #fff; font-weight: 600; border-radius: 8px 8px 0 0 !important; padding: 12px 20px; }
        
        .form-label { font-weight: 600; font-size: 0.9rem; color: #495057; }
        .input-group-text { background-color: #e9ecef; border-color: #ced4da; color: #495057; font-weight: 600; }
        
        .result-table th { background-color: #212529; color: #fff; text-align: center; vertical-align: middle; font-size: 0.9rem; }
        .result-table td { text-align: center; vertical-align: middle; font-size: 0.95rem; }
        
        .price-main { font-weight: 800; font-size: 1.15rem; color: #198754; }
        .status-badge { font-size: 0.85rem; padding: 4px 8px; border-radius: 4px; }
        .badge-zone { background-color: #6c757d; color: #fff; font-size: 0.85rem; padding: 3px 8px; border-radius: 4px; }
    </style>
</head>
<body>

<header>
    <div class="container d-flex justify-content-between align-items-center">
        <div>
            <h4 class="m-0 fw-bold">📦 业务员报价助手</h4>
            <small style="opacity: 0.8; font-size: 0.8rem;">T0-T3 全渠道精准测算 | 自动单位换算</small>
        </div>
        <div class="text-end">
            <span class="badge bg-secondary">V6.0-6.3 Fix</span>
            <div style="font-size: 0.7em; opacity: 0.6;">Update: <span id="updateDate"></span></div>
        </div>
    </div>
</header>

<div class="container my-4">
    <div class="card">
        <div class="card-header">⚙️ 参数设置 (Configuration)</div>
        <div class="card-body">
            <form id="calcForm">
                <div class="row g-3 mb-3">
                    <div class="col-md-5">
                        <label class="form-label">1. 客户等级 (Tier)</label>
                        <div class="bg-white p-2 rounded border d-flex justify-content-between align-items-center">
                            <div class="form-check"><input class="form-check-input" type="radio" name="tier" id="t0" value="T0"><label class="form-check-label" for="t0">T0 (VIP)</label></div>
                            <div class="form-check"><input class="form-check-input" type="radio" name="tier" id="t1" value="T1"><label class="form-check-label" for="t1">T1</label></div>
                            <div class="form-check"><input class="form-check-input" type="radio" name="tier" id="t2" value="T2"><label class="form-check-label" for="t2">T2</label></div>
                            <div class="form-check"><input class="form-check-input" type="radio" name="tier" id="t3" value="T3" checked><label class="form-check-label" for="t3">T3 (常规)</label></div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <label class="form-label">2. 地址类型</label>
                        <select class="form-select" id="addressType">
                            <option value="residential">🏠 住宅 (Residential)</option>
                            <option value="commercial">🏢 商业 (Commercial)</option>
                        </select>
                    </div>
                    <div class="col-md-2">
                        <label class="form-label">附加选项</label>
                        <div class="form-check form-switch mt-2">
                            <input class="form-check-input" type="checkbox" id="peakToggle">
                            <label class="form-check-label" for="peakToggle">旺季附加费</label>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <label class="form-label">燃油费率 %</label>
                        <input type="number" class="form-control" id="fuelRate" step="0.01" value="__FUEL__">
                    </div>
                </div>

                <hr class="text-muted">

                <div class="row g-3">
                    <div class="col-md-4 border-end">
                        <label class="form-label">3. 目的地邮编 (Zip Code)</label>
                        <div class="input-group">
                            <input type="text" class="form-control" id="zipCode" placeholder="输入5位美国邮编">
                            <button class="btn btn-dark" type="button" id="btnLookup">查询分区</button>
                        </div>
                        <div id="locInfo" class="mt-2 p-2 rounded bg-light small fw-bold text-muted" style="min-height: 2.5em;">请输入邮编点击查询...</div>
                    </div>

                    <div class="col-md-8">
                        <label class="form-label">4. 包裹规格 (Package Specs)</label>
                        <div class="row g-2">
                            <div class="col-md-3">
                                <div class="input-group input-group-sm">
                                    <span class="input-group-text">L</span>
                                    <input type="number" class="form-control" id="length" placeholder="长">
                                </div>
                            </div>
                            <div class="col-md-3">
                                <div class="input-group input-group-sm">
                                    <span class="input-group-text">W</span>
                                    <input type="number" class="form-control" id="width" placeholder="宽">
                                </div>
                            </div>
                            <div class="col-md-3">
                                <div class="input-group input-group-sm">
                                    <span class="input-group-text">H</span>
                                    <input type="number" class="form-control" id="height" placeholder="高">
                                </div>
                            </div>
                            <div class="col-md-3">
                                <select class="form-select form-select-sm" id="dimUnit">
                                    <option value="in">inch (英寸)</option>
                                    <option value="cm">cm (厘米)</option>
                                    <option value="mm">mm (毫米)</option>
                                    <option value="m">m (米)</option>
                                </select>
                            </div>
                            
                            <div class="col-md-9 mt-2">
                                <div class="input-group">
                                    <span class="input-group-text">实重 Weight</span>
                                    <input type="number" class="form-control" id="weight" placeholder="输入数值">
                                </div>
                            </div>
                            <div class="col-md-3 mt-2">
                                <select class="form-select" id="weightUnit">
                                    <option value="lb">lb (磅)</option>
                                    <option value="oz">oz (盎司)</option>
                                    <option value="kg">kg (千克)</option>
                                    <option value="g">g (克)</option>
                                </select>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="d-grid mt-4">
                    <button type="button" class="btn btn-primary btn-lg shadow-sm" id="btnCalc">
                        开始计算 (Calculate)
                    </button>
                </div>
            </form>
        </div>
    </div>

    <div class="row" id="resultSection" style="display:none;">
        <div class="col-12">
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <span>📊 测算结果 (Results)</span>
                    <span id="resTierBadge" class="badge bg-warning text-dark"></span>
                </div>
                <div class="card-body">
                    <div class="alert alert-info py-2 small" id="pkgSummary"></div>
                    <div class="table-responsive">
                        <table class="table table-bordered table-hover result-table">
                            <thead>
                                <tr>
                                    <th width="12%">渠道<br>(Channel)</th>
                                    <th width="6%">分区<br>(Zone)</th>
                                    <th width="8%">计费重<br>(LB)</th>
                                    <th width="10%">基础运费<br>(Base)</th>
                                    <th width="8%">燃油<br>(Fuel)</th>
                                    <th width="8%">旺季<br>(Peak)</th>
                                    <th width="8%">住宅<br>(Res)</th>
                                    <th width="10%">超规/其他<br>(Other)</th>
                                    <th width="15%">总费用<br>(Total)</th>
                                    <th width="15%">状态<br>(Status)</th>
                                </tr>
                            </thead>
                            <tbody id="resBody">
                                </tbody>
                        </table>
                    </div>
                    <div class="mt-2 text-muted small">
                        * 注：所有价格均已按表格要求换算为 LB 进行匹配。USPS 渠道不含燃油费及住宅费。
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<footer>
    <div class="container">
        <p>&copy; 2026 速狗海外仓报价系统 | 数据版本: GitHub Auto-Build</p>
    </div>
</footer>

<script>
    const DATA = __JSON_DATA__;
    let CUR_ZONES = {};
    document.getElementById('updateDate').innerText = new Date().toLocaleDateString();

    // ===========================================
    // 核心配置：渠道特殊规则 (Issue 3)
    // ===========================================
    const CHANNEL_CONFIG = {
        // 判断函数：是否收取住宅费
        hasResFee: function(name) {
            let n = name.toUpperCase();
            if (n.includes('USPS')) return false; // USPS不收住宅费
            if (n.includes('XLMILES')) return false; // XLmiles通常一口价
            return true; // FedEx, GOFO, UniUni 默认收
        },
        // 判断函数：是否收取燃油费
        hasFuelFee: function(name) {
            let n = name.toUpperCase();
            if (n.includes('USPS')) return false; // USPS含燃油
            return true;
        }
    };

    // 1. 严格单位换算 (Issue 2 & 5)
    // 无论输入什么，输出统一为 { L, W, H (inch), Wt (lb) }
    function convertToStandard(l, w, h, dimUnit, weight, weightUnit) {
        let L = parseFloat(l)||0, W = parseFloat(w)||0, H = parseFloat(h)||0, Wt = parseFloat(weight)||0;
        
        // 长度转 inch
        if (dimUnit === 'cm') { L/=2.54; W/=2.54; H/=2.54; }
        else if (dimUnit === 'mm') { L/=25.4; W/=25.4; H/=25.4; }
        else if (dimUnit === 'm') { L/=0.0254; W/=0.0254; H/=0.0254; }
        
        // 重量转 lb
        if (weightUnit === 'kg') Wt /= 0.45359237;
        else if (weightUnit === 'oz') Wt /= 16;
        else if (weightUnit === 'g') Wt /= 453.59237;
        
        return { L, W, H, Wt };
    }

    // 2. 计费重计算 (FedEx规则)
    function getDimWeight(L, W, H, channel) {
        let vol = L * W * H; // in³
        let divisor = 250;
        if (channel.toLowerCase().includes('fedex')) { 
            // 1 cuft = 1728 in³
            if (vol < 1728) divisor = 400; 
            else divisor = 250; 
        }
        // UniUni 通常也是 250
        return vol / divisor;
    }

    // 3. 邮编查询 (Issue 4: 中英双语)
    document.getElementById('btnLookup').onclick = function() {
        let zip = document.getElementById('zipCode').value.trim();
        let infoDiv = document.getElementById('locInfo');
        
        if (!DATA.zip_db[zip]) { 
            infoDiv.innerHTML = "<span class='text-danger'>❌ 未找到该邮编 (Zip Not Found)</span>"; 
            CUR_ZONES = {}; 
            return; 
        }
        
        let info = DATA.zip_db[zip];
        // 双语显示
        let cnState = info.s_cn ? `${info.s_cn} ` : '';
        infoDiv.innerHTML = `<span class='text-success'>✅ ${cnState}(${info.s}) - ${info.c} [${info.r}]</span>`;
        CUR_ZONES = info.z;
    };

    // 4. 计算主逻辑
    document.getElementById('btnCalc').onclick = function() {
        let zip = document.getElementById('zipCode').value.trim();
        // 自动触发查询
        if ((!CUR_ZONES || Object.keys(CUR_ZONES).length === 0) && zip) { 
            document.getElementById('btnLookup').click(); 
        }
        
        let tier = document.querySelector('input[name="tier"]:checked').value;
        // 获取并标准化输入
        let pkg = convertToStandard(
            document.getElementById('length').value,
            document.getElementById('width').value,
            document.getElementById('height').value,
            document.getElementById('dimUnit').value,
            document.getElementById('weight').value,
            document.getElementById('weightUnit').value
        );
        
        let isPeak = document.getElementById('peakToggle').checked;
        let isRes = document.getElementById('addressType').value === 'residential';
        let userFuelRate = parseFloat(document.getElementById('fuelRate').value) / 100;
        
        // 准备界面
        document.getElementById('resultSection').style.display = 'block';
        document.getElementById('resTierBadge').innerText = tier;
        document.getElementById('pkgSummary').innerHTML = 
            `<b>📦 计费基准 (Standardized):</b> ${pkg.L.toFixed(2)}" x ${pkg.W.toFixed(2)}" x ${pkg.H.toFixed(2)}" | <b>实重:</b> ${pkg.Wt.toFixed(3)} lb`;
            
        let tbody = document.getElementById('resBody');
        tbody.innerHTML = '';
        
        if (!DATA.tiers[tier]) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-danger p-3">❌ 错误：未加载到该等级 (' + tier + ') 的数据文件</td></tr>';
            return;
        }
        
        let channels = Object.keys(DATA.tiers[tier]);
        
        channels.forEach(ch => {
            let chData = DATA.tiers[tier][ch];
            if (!chData.prices) return;
            
            // 1. 获取分区 (无分区则无法计算)
            let zoneVal = CUR_ZONES[ch] || '-';
            
            // 2. 确定计费重
            let dimWt = getDimWeight(pkg.L, pkg.W, pkg.H, ch);
            // 逻辑修正：实重 vs 体积重 取大，然后向上取整到整数 (通常是进位)
            // *但是* GOFO的小件(OZ)不需要进位到LB。
            // 策略：先保留小数进行精确查找，如果没找到，再尝试进位查找。
            let chargeWt = Math.max(pkg.Wt, dimWt);
            
            let basePrice = 0;
            let status = "正常";
            let statusClass = "text-success";
            
            // 3. 价格匹配逻辑 (Issue 1: 混合单位处理)
            // 我们在Python端已经把所有价格表的重量列转为了LB。
            // 所以这里直接拿着 chargeWt (lb) 去找 >= 的最小档位。
            
            let foundRow = null;
            // 遍历价格表 (已按重量排序)
            for (let row of chData.prices) {
                // 允许微小误差 (0.001)
                if (row.w >= chargeWt - 0.001) {
                    foundRow = row;
                    break;
                }
            }
            
            // 处理 Zone 映射 (例如表头没有 Zone 1，通常沿用 Zone 2)
            let zoneKey = zoneVal === '1' ? '2' : zoneVal;
            
            if (!foundRow) {
                status = "超重/无报价";
                statusClass = "text-danger fw-bold";
            } else if (zoneVal === '-') {
                status = "无分区";
                statusClass = "text-muted";
            } else {
                basePrice = foundRow[zoneKey];
                // 如果还找不到，尝试回退 Zone 2 (防止极个别缺漏)
                if (basePrice === undefined && zoneKey === '1') basePrice = foundRow['2'];
                
                if (basePrice === undefined || basePrice === null) {
                    status = "该区无报价";
                    statusClass = "text-warning fw-bold";
                    basePrice = 0;
                }
            }
            
            // 4. 费用叠加
            let fuelFee = 0, peakFee = 0, resFee = 0, otherFee = 0, total = 0;
            
            if (basePrice > 0) {
                // 燃油费 (Issue 3: 验证是否收取)
                if (CHANNEL_CONFIG.hasFuelFee(ch)) {
                    fuelFee = basePrice * userFuelRate;
                }
                
                // 住宅费 (Issue 3: 验证是否收取)
                if (isRes && CHANNEL_CONFIG.hasResFee(ch)) {
                    resFee = DATA.surcharges.res_fee;
                }
                
                // 超规费 (通用逻辑)
                let dims = [pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
                let longest = dims[0];
                let girth = longest + 2*(dims[1]+dims[2]);
                
                // 判断条件 (严格对标表格)
                let isOversize = (longest > 96 || girth > 130);
                let isUnauthorized = (longest > 108 || girth > 165 || chargeWt > 150);
                let isAHS = (longest > 48); // Additional Handling
                
                if (isUnauthorized) {
                    otherFee += DATA.surcharges.unauthorized_fee;
                    status = "不可发(Unauthorized)";
                    statusClass = "text-danger fw-bold";
                } else if (isOversize) {
                    otherFee += DATA.surcharges.oversize_fee;
                    status = "超大件(Oversize)";
                    statusClass = "text-warning fw-bold";
                } else if (isAHS) {
                    otherFee += DATA.surcharges.ahs_fee;
                    status = "超长(AHS)";
                    statusClass = "text-warning";
                }
                
                // 旺季附加费
                if (isPeak) {
                    if (isRes && CHANNEL_CONFIG.hasResFee(ch)) peakFee += DATA.surcharges.peak_res;
                    if (isOversize) peakFee += DATA.surcharges.peak_oversize;
                    if (isUnauthorized) peakFee += DATA.surcharges.peak_unauthorized;
                }
                
                total = basePrice + fuelFee + peakFee + resFee + otherFee;
            }
            
            // 渲染
            let trClass = status.includes("不可发") ? "table-danger" : "";
            // 显示匹配到的计费重量档位，方便核对
            let matchedWeight = foundRow ? foundRow.w.toFixed(3) : '-';
            
            let html = `
                <tr class="${trClass}">
                    <td class="fw-bold text-start text-nowrap">${ch}</td>
                    <td><span class="badge-zone">${zoneVal}</span></td>
                    <td class="small">${chargeWt.toFixed(2)}<br><span class="text-muted" style="font-size:0.75em">(档:${matchedWeight})</span></td>
                    <td class="fw-bold">${basePrice.toFixed(2)}</td>
                    <td>${fuelFee.toFixed(2)}</td>
                    <td>${peakFee.toFixed(2)}</td>
                    <td>${resFee.toFixed(2)}</td>
                    <td>${otherFee.toFixed(2)}</td>
                    <td class="price-main">$${total > 0 ? total.toFixed(2) : '-'}</td>
                    <td class="${statusClass}">${status}</td>
                </tr>
            `;
            tbody.innerHTML += html;
        });
    };
</script>
</body>
</html>
"""

# ==========================================
# 3. 核心逻辑: Excel 解析 (增强版)
# ==========================================

def get_sheet_by_name(excel_file, target_name):
    """读取Excel的特定Sheet，使用openpyxl引擎"""
    try:
        xl = pd.ExcelFile(excel_file, engine='openpyxl')
        if target_name in xl.sheet_names: 
            return pd.read_excel(xl, sheet_name=target_name, header=None)
        for sheet in xl.sheet_names:
            if target_name.replace(" ", "").lower() in sheet.replace(" ", "").lower():
                print(f"    > [Sheet映射] '{sheet}' -> '{target_name}'")
                return pd.read_excel(xl, sheet_name=sheet, header=None)
        print(f"    > [WARN] 未找到 Sheet: {target_name}")
        return None
    except Exception as e:
        print(f"    > [ERROR] 读取 Excel 失败: {e}")
        return None

def load_zip_db():
    print("--- 1. 构建邮编数据库 (读取 T0.xlsx) ---")
    path = os.path.join(DATA_DIR, TIER_FILES['T0'])
    if not os.path.exists(path): 
        print(f"❌ 错误: 找不到文件 {path}"); return {}
    
    df = get_sheet_by_name(path, ZIP_DB_SHEET)
    if df is None: return {}

    zip_db = {}
    try:
        start_row = 0
        for i in range(100):
            val = str(df.iloc[i, 1]).strip()
            if val.isdigit() and len(val) == 5: 
                start_row = i; break
        
        for idx, row in df.iloc[start_row:].iterrows():
            z = str(row[1]).strip()
            if z.isdigit() and len(z) == 5:
                zones = {}
                for ch, col in ZIP_COL_MAP.items():
                    val = str(row[col]).strip()
                    zones[ch] = val if val not in ['-','nan','', 'None'] else None
                
                state_abbr = str(row[3]).strip().upper()
                # 注入中文州名 (Issue 4)
                state_cn = US_STATES_CN.get(state_abbr, '')
                
                zip_db[z] = {
                    "s": state_abbr, 
                    "s_cn": state_cn,
                    "c": str(row[4]).strip(), 
                    "r": str(row[2]).strip(), 
                    "z": zones
                }
    except Exception as e: 
        print(f"解析邮编数据出错: {e}")
    
    print(f"✅ 已加载 {len(zip_db)} 条邮编数据 (含中文州名)")
    return zip_db

def parse_weight_to_lb(val):
    """
    核心功能：将表格中乱七八糟的重量单位统一转为 LB (Issue 1 & 2)
    支持: '1', '1 OZ', '1 LB', '0.5'
    """
    s = str(val).upper().strip()
    if pd.isna(val) or s == 'NAN': return None
    
    # 提取数字
    nums = re.findall(r"[\d\.]+", s)
    if not nums: return None
    num = float(nums[0])
    
    # 判断单位
    if 'OZ' in s:
        return num / 16.0  # 转化为 LB
    # 默认按 LB 处理 (GOFO表里没写单位的行通常是 LB)
    return num

def load_prices():
    print("\n--- 2. 加载各等级报价表 ---")
    all_data = {}
    
    for tier, filename in TIER_FILES.items():
        print(f"处理 {tier} ({filename})...")
        path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(path):
            print(f"    > 跳过: 文件不存在")
            continue
            
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
                
                # 智能识别列
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
                        # 关键调用：统一转 LB
                        w_lb = parse_weight_to_lb(w_val)
                        if w_lb is None: continue
                        
                        p_row = {'w': w_lb} # w 存的是 LB
                        for z, col in zone_map.items():
                            try:
                                val = row[col]
                                if pd.notna(val) and str(val).replace('.','').isdigit():
                                    p_row[z] = float(val)
                            except: pass
                        prices.append(p_row)
                    except: continue
                
                # 按重量升序排序，方便JS查找
                prices.sort(key=lambda x: x['w'])
                tier_data[ch_key] = {"prices": prices}
                
            except Exception as e:
                print(f"    > 解析 {ch_key} 失败: {e}")
                pass
                
        all_data[tier] = tier_data
    return all_data

# ==========================================
# 4. 主程序
# ==========================================

if __name__ == '__main__':
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # 1. 抓取数据
    final_data = {
        "zip_db": load_zip_db(),
        "tiers": load_prices(),
        "surcharges": GLOBAL_SURCHARGES
    }
    
    print("\n--- 3. 生成 index.html ---")
    json_str = json.dumps(final_data)
    
    # 2. 注入 HTML
    final_html = HTML_TEMPLATE.replace('__JSON_DATA__', json_str)
    final_html = final_html.replace('__FUEL__', str(GLOBAL_SURCHARGES['fuel']*100))
    
    # 3. 写入
    output_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_html)
    
    print(f"✅ 成功！文件已生成: {output_path}")
