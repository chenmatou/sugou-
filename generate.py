import pandas as pd
import json
import re
import os
import warnings

# 忽略 Excel 读取时的样式警告
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# ==========================================
# 1. 基础配置
# ==========================================
DATA_DIR = "data"
OUTPUT_DIR = "public"

# Excel 文件名对应 (确保您上传的文件名匹配)
TIER_FILES = {
    "T0": "T0.xlsx",
    "T1": "T1.xlsx",
    "T2": "T2.xlsx",
    "T3": "T3.xlsx"
}

# Excel Sheet 名称映射 (左边是显示名称，右边是Excel里的Sheet名)
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

# 邮编数据库配置 (从 T0 的 GOFO 表中读取)
ZIP_DB_SHEET = "GOFO-报价"
# 列索引：0代表A列，5代表F列
ZIP_COL_MAP = {
    "GOFO-报价": 5, "GOFO-MT-报价": 6, "UNIUNI-MT-报价": 7, "USPS-YSD-报价": 8,
    "FedEx-ECO-MT报价": 9, "XLmiles-报价": 10, "GOFO大件-GRO-报价": 11,
    "FedEx-632-MT-报价": 12, "FedEx-YSD-报价": 13
}

# 默认附加费 (作为兜底数据)
GLOBAL_SURCHARGES = {
    "fuel": 0.16, "res_fee": 3.50, "peak_res": 1.32,
    "peak_oversize": 54, "peak_unauthorized": 220,
    "oversize_fee": 130, "ahs_fee": 20, "unauthorized_fee": 1150
}

# ==========================================
# 2. 完整网页模板 (HTML/CSS/JS)
# ==========================================
# 这是一个包含完整逻辑的单页应用模板
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
        
        /* 黑色页眉页脚 */
        header { background-color: var(--header-bg); color: #fff; padding: 15px 0; box-shadow: 0 2px 10px rgba(0,0,0,0.2); }
        footer { background-color: var(--header-bg); color: #888; padding: 20px 0; margin-top: auto; text-align: center; font-size: 0.85em; }
        
        .card { border: none; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 20px; transition: transform 0.2s; }
        .card-header { background-color: #212529; color: #fff; font-weight: 600; border-radius: 8px 8px 0 0 !important; }
        
        .btn-calc { background-color: var(--primary-color); border: none; font-weight: bold; padding: 12px; transition: all 0.3s; }
        .btn-calc:hover { background-color: #0b5ed7; transform: translateY(-1px); }
        
        /* 状态徽章 */
        .badge-zone { font-size: 0.9em; background-color: #e9ecef; color: #000; padding: 5px 10px; border-radius: 4px; }
        
        /* 结果表格 */
        .result-table th { background-color: #212529; color: #fff; text-align: center; vertical-align: middle; }
        .result-table td { text-align: center; vertical-align: middle; font-size: 0.95em; }
        .price-main { font-weight: 800; font-size: 1.1em; color: var(--primary-color); }
        
        /* 状态颜色 */
        .status-ok { color: #198754; font-weight: bold; }
        .status-warn { color: #ffc107; font-weight: bold; }
        .status-error { color: #dc3545; font-weight: bold; }
    </style>
</head>
<body>

<header>
    <div class="container d-flex justify-content-between align-items-center">
        <div>
            <h4 class="m-0">📦 业务员报价助手</h4>
            <small style="opacity: 0.7;">T0-T3 全渠道集成版</small>
        </div>
        <div class="text-end">
            <span class="badge bg-secondary">V6.0-6.3</span>
            <div style="font-size: 0.7em; opacity: 0.6;">Update: <span id="updateDate"></span></div>
        </div>
    </div>
</header>

<div class="container my-4">
    <div class="row">
        <div class="col-lg-12">
            <div class="card">
                <div class="card-header">⚙️ 参数配置 (Configuration)</div>
                <div class="card-body">
                    <form id="calcForm">
                        <div class="row mb-4">
                            <div class="col-md-5">
                                <label class="form-label fw-bold">1. 客户等级 (Tier)</label>
                                <div class="bg-light p-2 rounded border">
                                    <div class="form-check form-check-inline">
                                        <input class="form-check-input" type="radio" name="tier" id="t0" value="T0">
                                        <label class="form-check-label" for="t0">T0 (VIP)</label>
                                    </div>
                                    <div class="form-check form-check-inline">
                                        <input class="form-check-input" type="radio" name="tier" id="t1" value="T1">
                                        <label class="form-check-label" for="t1">T1</label>
                                    </div>
                                    <div class="form-check form-check-inline">
                                        <input class="form-check-input" type="radio" name="tier" id="t2" value="T2">
                                        <label class="form-check-label" for="t2">T2</label>
                                    </div>
                                    <div class="form-check form-check-inline">
                                        <input class="form-check-input" type="radio" name="tier" id="t3" value="T3" checked>
                                        <label class="form-check-label" for="t3">T3 (常规)</label>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-3">
                                <label class="form-label fw-bold">2. 地址属性</label>
                                <select class="form-select" id="addressType">
                                    <option value="residential">🏠 住宅地址 (Res)</option>
                                    <option value="commercial">🏢 商业地址 (Com)</option>
                                </select>
                            </div>
                            <div class="col-md-2">
                                <label class="form-label fw-bold">旺季附加费</label>
                                <div class="form-check form-switch mt-2">
                                    <input class="form-check-input" type="checkbox" id="peakToggle">
                                    <label class="form-check-label" for="peakToggle">启用 (Peak)</label>
                                </div>
                            </div>
                            <div class="col-md-2">
                                <label class="form-label fw-bold">燃油费率 %</label>
                                <input type="number" class="form-control" id="fuelRate" step="0.01" value="__FUEL__">
                            </div>
                        </div>

                        <hr class="text-muted">

                        <div class="row g-3">
                            <div class="col-md-4 border-end">
                                <label class="form-label fw-bold">3. 美国邮编 (Zip Code)</label>
                                <div class="input-group">
                                    <input type="text" class="form-control" id="zipCode" placeholder="输入5位邮编 (e.g. 90001)">
                                    <button class="btn btn-dark" type="button" id="btnLookup">查询分区</button>
                                </div>
                                <div id="locInfo" class="mt-2 small fw-bold text-muted">请输入邮编查询...</div>
                            </div>

                            <div class="col-md-8">
                                <label class="form-label fw-bold">4. 包裹规格 (Package)</label>
                                <div class="row g-2">
                                    <div class="col-3">
                                        <div class="input-group input-group-sm">
                                            <span class="input-group-text">L</span>
                                            <input type="number" class="form-control" id="length" placeholder="长">
                                        </div>
                                    </div>
                                    <div class="col-3">
                                        <div class="input-group input-group-sm">
                                            <span class="input-group-text">W</span>
                                            <input type="number" class="form-control" id="width" placeholder="宽">
                                        </div>
                                    </div>
                                    <div class="col-3">
                                        <div class="input-group input-group-sm">
                                            <span class="input-group-text">H</span>
                                            <input type="number" class="form-control" id="height" placeholder="高">
                                        </div>
                                    </div>
                                    <div class="col-3">
                                        <select class="form-select form-select-sm" id="dimUnit">
                                            <option value="in">inch</option>
                                            <option value="cm">cm</option>
                                            <option value="mm">mm</option>
                                        </select>
                                    </div>
                                    
                                    <div class="col-6 mt-2">
                                        <div class="input-group">
                                            <span class="input-group-text">实重</span>
                                            <input type="number" class="form-control" id="weight" placeholder="Weight">
                                        </div>
                                    </div>
                                    <div class="col-6 mt-2">
                                        <select class="form-select" id="weightUnit">
                                            <option value="lb">lb (磅)</option>
                                            <option value="kg">kg (千克)</option>
                                            <option value="oz">oz (盎司)</option>
                                            <option value="g">g (克)</option>
                                        </select>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div class="d-grid mt-4">
                            <button type="button" class="btn btn-primary btn-calc btn-lg text-white" id="btnCalc">
                                开始计算报价 (Calculate)
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>

    <div class="row" id="resultSection" style="display:none;">
        <div class="col-12">
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <span>📊 报价结果 (Results)</span>
                    <span id="resTierBadge" class="badge bg-warning text-dark"></span>
                </div>
                <div class="card-body">
                    <div class="alert alert-info py-2" id="pkgSummary"></div>
                    <div class="table-responsive">
                        <table class="table table-bordered table-hover result-table">
                            <thead>
                                <tr>
                                    <th width="15%">渠道</th>
                                    <th width="5%">分区</th>
                                    <th width="8%">计费重<br>(LB)</th>
                                    <th width="10%">基础运费</th>
                                    <th width="10%">燃油费</th>
                                    <th width="10%">旺季费</th>
                                    <th width="10%">住宅/其他</th>
                                    <th width="10%">超规费</th>
                                    <th width="12%">总费用($)</th>
                                    <th width="10%">状态</th>
                                </tr>
                            </thead>
                            <tbody id="resBody">
                                </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<footer>
    <div class="container">
        <p>&copy; 2026 速狗海外仓报价系统 | Powered by GitHub Actions</p>
        <small class="text-muted">仅供参考，实际费用以仓库账单为准。</small>
    </div>
</footer>

<script>
    // ===========================================
    // 数据注入点 (由 Python 替换)
    // ===========================================
    const DATA = __JSON_DATA__;
    
    // 全局状态
    let CUR_ZONES = {}; // 当前邮编的分区信息
    
    // 初始化时间
    document.getElementById('updateDate').innerText = new Date().toLocaleDateString();

    // 1. 单位换算
    function convertToStandard(l, w, h, dimUnit, weight, weightUnit) {
        let L = parseFloat(l) || 0;
        let W = parseFloat(w) || 0;
        let H = parseFloat(h) || 0;
        let Wt = parseFloat(weight) || 0;
        
        // 尺寸转 inch
        if (dimUnit === 'cm') { L/=2.54; W/=2.54; H/=2.54; }
        else if (dimUnit === 'mm') { L/=25.4; W/=25.4; H/=25.4; }
        
        // 重量转 lb
        if (weightUnit === 'kg') Wt /= 0.45359237;
        else if (weightUnit === 'oz') Wt /= 16;
        else if (weightUnit === 'g') Wt /= 453.59237;
        
        return { L, W, H, Wt };
    }

    // 2. 计费重计算 (核心规则)
    function getDimWeight(L, W, H, channel) {
        let vol = L * W * H; // 立方英寸
        let divisor = 250;   // 默认除数
        
        // FedEx 规则: 体积<1728(1立方英尺)除以400，否则250
        if (channel.toLowerCase().includes('fedex')) {
             if (vol < 1728) divisor = 400; 
             else divisor = 250;
        }
        
        return vol / divisor;
    }

    // 3. 邮编查询事件
    document.getElementById('btnLookup').onclick = function() {
        let zip = document.getElementById('zipCode').value.trim();
        let infoDiv = document.getElementById('locInfo');
        
        if (!DATA.zip_db[zip]) {
            infoDiv.innerHTML = "<span class='text-danger'>❌ 未找到该邮编 (Zip Not Found)</span>";
            CUR_ZONES = {};
            return;
        }
        
        let info = DATA.zip_db[zip];
        infoDiv.innerHTML = `<span class='text-success'>📍 ${info.s} - ${info.c} (${info.r})</span>`;
        CUR_ZONES = info.z; // 保存分区数据
    };

    // 4. 计算主逻辑
    document.getElementById('btnCalc').onclick = function() {
        // 自动触发查询
        let zip = document.getElementById('zipCode').value.trim();
        if ((!CUR_ZONES || Object.keys(CUR_ZONES).length === 0) && zip) {
            document.getElementById('btnLookup').click();
        }
        
        // 获取输入
        let tier = document.querySelector('input[name="tier"]:checked').value;
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
        let fuelRate = parseFloat(document.getElementById('fuelRate').value) / 100;
        
        // UI 准备
        document.getElementById('resultSection').style.display = 'block';
        document.getElementById('resTierBadge').innerText = tier;
        document.getElementById('pkgSummary').innerHTML = 
            `<b>包裹:</b> ${pkg.L.toFixed(1)}x${pkg.W.toFixed(1)}x${pkg.H.toFixed(1)} in | <b>实重:</b> ${pkg.Wt.toFixed(2)} lb`;
            
        let tbody = document.getElementById('resBody');
        tbody.innerHTML = '';
        
        // 遍历渠道
        if (!DATA.tiers[tier]) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-danger">无该等级数据</td></tr>';
            return;
        }
        
        let channels = Object.keys(DATA.tiers[tier]);
        
        channels.forEach(ch => {
            let chData = DATA.tiers[tier][ch];
            if (!chData.prices) return;
            
            // 获取分区
            let zoneVal = CUR_ZONES[ch] || '-';
            
            // 计算计费重 (进位)
            let dimWt = getDimWeight(pkg.L, pkg.W, pkg.H, ch);
            let chargeWt = Math.ceil(Math.max(pkg.Wt, dimWt));
            
            // 查找基础运费
            let basePrice = 0;
            // 处理 Zone 1 映射 (通常表里没有Zone 1，按Zone 2算)
            let zoneKey = zoneVal === '1' ? '2' : zoneVal;
            
            let foundRow = null;
            for (let row of chData.prices) {
                if (row.w >= chargeWt) {
                    foundRow = row;
                    break;
                }
            }
            
            // 状态判断
            let status = "正常";
            let statusClass = "status-ok";
            
            if (!foundRow || zoneVal === '-') {
                status = "无分区/超重";
                statusClass = "text-muted";
            } else {
                basePrice = foundRow[zoneKey];
                if (!basePrice) {
                    status = "缺报价";
                    statusClass = "status-warn";
                    basePrice = 0;
                }
            }
            
            // 费用计算
            let fuelFee = 0, peakFee = 0, resFee = 0, otherFee = 0, total = 0;
            
            if (basePrice > 0) {
                fuelFee = basePrice * fuelRate;
                
                if (isRes) {
                    resFee = DATA.surcharges.res_fee;
                }
                
                // 超规判断
                let dims = [pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
                let longest = dims[0]; // 最长边
                let girth = longest + 2*(dims[1]+dims[2]); // 围长
                
                let isOversize = (longest > 96 || girth > 130);
                let isUnauthorized = (longest > 108 || girth > 165 || chargeWt > 150);
                
                // 旺季费
                if (isPeak) {
                    if (isRes) peakFee += DATA.surcharges.peak_res;
                    if (isOversize) peakFee += DATA.surcharges.peak_oversize;
                    if (isUnauthorized) peakFee += DATA.surcharges.peak_unauthorized;
                }
                
                // 物理附加费
                if (isUnauthorized) {
                    otherFee += DATA.surcharges.unauthorized_fee;
                    status = "不可发!";
                    statusClass = "status-error";
                } else if (isOversize) {
                    otherFee += DATA.surcharges.oversize_fee;
                    status = "超大件";
                    statusClass = "status-warn";
                } else if (longest > 48) {
                    otherFee += DATA.surcharges.ahs_fee;
                    status = "超长(AHS)";
                    statusClass = "status-warn";
                }
                
                total = basePrice + fuelFee + peakFee + resFee + otherFee;
            }
            
            // 渲染行
            let trClass = status.includes("不可发") ? "table-danger" : "";
            
            let html = `
                <tr class="${trClass}">
                    <td class="fw-bold text-start">${ch}</td>
                    <td><span class="badge-zone">${zoneVal}</span></td>
                    <td>${chargeWt}</td>
                    <td>${basePrice.toFixed(2)}</td>
                    <td>${fuelFee.toFixed(2)}</td>
                    <td>${peakFee.toFixed(2)}</td>
                    <td>${(resFee + (isRes ? 0 : 0)).toFixed(2)}</td>
                    <td>${otherFee.toFixed(2)}</td>
                    <td class="price-main">${total > 0 ? total.toFixed(2) : '-'}</td>
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
# 3. 核心逻辑: Excel 解析器
# ==========================================

def get_sheet_by_name(excel_file, target_name):
    """在Excel中模糊查找Sheet，支持大小写和部分匹配"""
    try:
        xl = pd.ExcelFile(excel_file)
        # 1. 尝试精确匹配
        if target_name in xl.sheet_names:
            return pd.read_excel(xl, sheet_name=target_name, header=None)
        
        # 2. 尝试模糊匹配 (包含名字即可)
        for sheet in xl.sheet_names:
            # 移除空格后对比
            if target_name.replace(" ", "").lower() in sheet.replace(" ", "").lower():
                print(f"    > [INFO] 映射 Sheet: '{sheet}' -> '{target_name}'")
                return pd.read_excel(xl, sheet_name=sheet, header=None)
        
        print(f"    > [WARN] 未找到 Sheet: {target_name}")
        return None
    except Exception as e:
        print(f"    > [ERROR] 读取 Excel 失败: {e}")
        return None

def load_zip_db():
    """从 T0.xlsx 加载邮编数据 (作为基准)"""
    print("--- 正在构建邮编数据库 (读取 T0.xlsx) ---")
    path = os.path.join(DATA_DIR, TIER_FILES['T0'])
    if not os.path.exists(path):
        print(f"❌ 错误: 找不到文件 {path}")
        return {}
    
    df = get_sheet_by_name(path, ZIP_DB_SHEET)
    if df is None: return {}

    zip_db = {}
    try:
        # 寻找数据起始行 (第2列为5位数字)
        start_row = 0
        for i in range(100):
            val = str(df.iloc[i, 1]).strip()
            if val.isdigit() and len(val) == 5:
                start_row = i
                break
        
        # 遍历数据
        for idx, row in df.iloc[start_row:].iterrows():
            z = str(row[1]).strip()
            if z.isdigit() and len(z) == 5:
                zones = {}
                for ch, col in ZIP_COL_MAP.items():
                    val = str(row[col]).strip()
                    zones[ch] = val if val not in ['-','nan','', 'None'] else None
                
                zip_db[z] = {
                    "s": str(row[3]).strip(), # State
                    "c": str(row[4]).strip(), # City
                    "r": str(row[2]).strip(), # Region
                    "z": zones
                }
    except Exception as e:
        print(f"解析邮编数据出错: {e}")
    
    print(f"✅ 已加载 {len(zip_db)} 条邮编数据")
    return zip_db

def load_prices():
    """加载所有等级的报价"""
    print("\n--- 正在加载各等级报价表 ---")
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
                # 寻找表头 (包含 "Zone" 和 "Weight" 的行)
                header_row = 0
                for i in range(30):
                    row_str = " ".join(df.iloc[i].astype(str).values).lower()
                    if "zone" in row_str and ("lb" in row_str or "weight" in row_str or "重量" in row_str):
                        header_row = i
                        break
                
                # 解析表头列索引
                headers = df.iloc[header_row].astype(str).str.lower().tolist()
                weight_idx = -1
                zone_map = {} 
                
                for idx, val in enumerate(headers):
                    if 'weight' in val or 'lb' in val or '重量' in val: 
                        weight_idx = idx
                    if 'zone' in val:
                        # 提取数字 "Zone 2" -> "2", "Zone~2" -> "2"
                        z = re.sub(r'[^\d]', '', val) 
                        if z: zone_map[z] = idx
                
                if weight_idx == -1: 
                    print(f"    > [WARN] {ch_key} 未找到重量列 (Header at row {header_row})")
                    continue
                
                # 读取价格行
                prices = []
                for i in range(header_row+1, len(df)):
                    row = df.iloc[i]
                    try:
                        w_val = row[weight_idx]
                        if pd.isna(w_val): continue
                        
                        # 确保重量是数字 (处理 "1 lb" 这种格式)
                        w_str = str(w_val)
                        if not re.search(r'\d', w_str): continue
                        w = float(re.findall(r"[\d\.]+", w_str)[0])
                        
                        p_row = {'w': w}
                        for z, col in zone_map.items():
                            try:
                                val = row[col]
                                if pd.notna(val) and str(val).replace('.','').isdigit():
                                    p_row[z] = float(val)
                            except: pass
                        prices.append(p_row)
                    except: continue
                
                tier_data[ch_key] = {"prices": prices}
                
            except Exception as e:
                print(f"    > 解析 {ch_key} 失败: {e}")
                pass
                
        all_data[tier] = tier_data
    return all_data

# ==========================================
# 4. 主执行入口
# ==========================================

if __name__ == '__main__':
    # 确保输出目录存在
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # 1. 加载数据
    final_data = {
        "zip_db": load_zip_db(),
        "tiers": load_prices(),
        "surcharges": GLOBAL_SURCHARGES
    }
    
    # 2. 生成 JSON
    print("\n--- 正在生成静态文件 ---")
    json_str = json.dumps(final_data)
    
    # 3. 注入 HTML
    # 替换占位符
    final_html = HTML_TEMPLATE.replace('__JSON_DATA__', json_str)
    final_html = final_html.replace('__FUEL__', str(GLOBAL_SURCHARGES['fuel']*100))
    
    # 4. 写入文件
    output_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_html)
    
    print(f"✅ 构建成功！")
    print(f"文件位置: {output_path}")
    print(f"文件大小: {os.path.getsize(output_path)/1024/1024:.2f} MB")
