import pandas as pd
import json
import re
import os
import warnings
from datetime import datetime

# 忽略 Excel 样式警告
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# ==========================================
# 1. 全局配置 (2026 新年调价严谨版)
# ==========================================
DATA_DIR = "data"
OUTPUT_DIR = "public"

TIER_FILES = {
    "T0": "T0.xlsx", "T1": "T1.xlsx", "T2": "T2.xlsx", "T3": "T3.xlsx"
}

# 2) 仓库清单配置
WAREHOUSE_CONFIG = {
    "91730": {"name": "SureGo美西库卡蒙格-91730新仓", "region": "WEST"},
    "91752": {"name": "SureGo美西米拉罗马-91752仓", "region": "WEST"},
    "60632": {"name": "SureGo美中芝加哥-60632仓", "region": "CENTRAL"},
    "63461": {"name": "SureGo退货检测-美中密苏里63461退货仓", "region": "CENTRAL"},
    "08691": {"name": "SureGo美东新泽西-08691仓", "region": "EAST"},
    "06801": {"name": "SureGo美东贝塞尔-06801仓", "region": "EAST"},
    "11791": {"name": "SureGo美东长岛-11791仓", "region": "EAST"},
    "07032": {"name": "SureGo美东新泽西-07032仓", "region": "EAST"}
}

# 3) 渠道详细配置
# split_mode: 'left'/'right' 用于处理同一张 Sheet 左右两边不同渠道的情况
# fuel_discount: 0.85 表示燃油费 85 折
# res_fee / sig_fee: 强制覆盖的附加费金额 (单位: 美元)
CHANNEL_MAP = {
    "GOFO-报价": {
        "keywords": ["GOFO", "报价"], 
        "exclude": ["MT", "UNIUNI", "大件"],
        "allow_wh": ["91730", "60632", "63461"],
        "res_fee": 0, "sig_fee": 0, "fuel_discount": 1.0
    },
    "GOFO-MT-报价": {
        "keywords": ["GOFO", "UNIUNI", "MT"],
        "split_mode": "left",  # 提取 Sheet 左半部分
        "allow_wh": ["91730", "60632", "63461"],
        "res_fee": 0, "sig_fee": 0, "fuel_discount": 1.0
    },
    "UNIUNI-MT-报价": {
        "keywords": ["GOFO", "UNIUNI", "MT"],
        "split_mode": "right", # 提取 Sheet 右半部分
        "allow_wh": ["91730", "60632", "63461"],
        "res_fee": 0, "sig_fee": 0, "fuel_discount": 1.0
    },
    "USPS-YSD-报价": {
        "keywords": ["USPS", "YSD"],
        "allow_wh": ["91730", "60632", "63461"],
        "res_fee": 0, "sig_fee": 0, "fuel_discount": 1.0, 
        "no_peak": True # 取消旺季
    },
    "FedEx-632-MT-报价": {
        "keywords": ["632"],
        "allow_wh": ["91730", "60632", "08691", "06801", "11791", "07032"],
        "res_fee": 2.61, "sig_fee": 4.37, "fuel_discount": 0.85
    },
    "FedEx-MT-超大包裹-报价": {
        "keywords": ["超大包裹"],
        "allow_wh": ["91730", "60632", "08691", "06801", "11791", "07032"],
        "res_fee": 2.61, "sig_fee": 4.37, "fuel_discount": 0.85
    },
    "FedEx-ECO-MT报价": {
        "keywords": ["ECO", "MT"],
        "allow_wh": ["91730", "60632", "08691", "06801", "11791", "07032"],
        "res_fee": 0, "sig_fee": 0, "fuel_discount": 1.0
    },
    "FedEx-MT-危险品-报价": {
        "keywords": ["危险品"],
        "allow_wh": ["60632", "08691", "06801", "11791", "07032"],
        "res_fee": 3.32, "sig_fee": 9.71, "fuel_discount": 1.0
    },
    "GOFO大件-MT-报价": {
        "keywords": ["GOFO大件", "MT"],
        "allow_wh": ["91730", "08691", "06801", "11791", "07032"],
        "res_fee": 2.93, "sig_fee": 0, "fuel_discount": 1.0
    },
    "XLmiles-报价": {
        "keywords": ["XLmiles"],
        "allow_wh": ["91730"],
        "res_fee": 0, "sig_fee": 10.20, "fuel_discount": 1.0
    }
}

# ==========================================
# 2. 前端模板 (嵌入式 HTML/JS)
# ==========================================
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SureGo 报价计算器 (2026新年版)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        :root { --sg-blue: #0d6efd; --sg-dark: #212529; }
        body { background-color: #f0f2f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
        .header-bar { background: var(--sg-dark); color: white; padding: 15px 0; border-bottom: 4px solid var(--sg-blue); margin-bottom: 20px; }
        .card { border: none; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border-radius: 10px; }
        .card-header { background: #fff; border-bottom: 1px solid #eee; font-weight: 700; color: #444; padding: 15px 20px; border-radius: 10px 10px 0 0 !important; }
        .price-val { color: var(--sg-blue); font-weight: 800; font-size: 1.2rem; }
        .badge-tier { font-size: 0.9rem; padding: 5px 10px; }
        .fuel-tag { font-size: 0.7rem; background: #e3f2fd; color: #0d6efd; padding: 2px 6px; border-radius: 4px; margin-left: 5px; }
        .table-hover tbody tr:hover { background-color: #f8fbff; }
    </style>
</head>
<body>

<div class="header-bar">
    <div class="container d-flex justify-content-between align-items-center">
        <div>
            <h4 class="m-0 fw-bold">📦 SureGo 报价助手</h4>
            <div class="small opacity-75">V2026.1 | 新年调价版 | 燃油85折适配</div>
        </div>
        <div class="text-end d-none d-md-block">
            <span class="badge bg-primary">T0-T3 实时计算</span>
        </div>
    </div>
</div>

<div class="container pb-5">
    <div class="row g-4">
        <div class="col-lg-4">
            <div class="card h-100">
                <div class="card-header">🛠️ 测算参数</div>
                <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label small fw-bold text-muted">发货仓库</label>
                        <select class="form-select" id="whSelect"></select>
                        <div class="form-text small text-end" id="whRegion"></div>
                    </div>

                    <div class="mb-3">
                        <label class="form-label small fw-bold text-muted">客户等级</label>
                        <div class="btn-group w-100" role="group">
                            <input type="radio" class="btn-check" name="tier" id="t0" value="T0"><label class="btn btn-outline-secondary" for="t0">T0</label>
                            <input type="radio" class="btn-check" name="tier" id="t1" value="T1"><label class="btn btn-outline-secondary" for="t1">T1</label>
                            <input type="radio" class="btn-check" name="tier" id="t2" value="T2"><label class="btn btn-outline-secondary" for="t2">T2</label>
                            <input type="radio" class="btn-check" name="tier" id="t3" value="T3" checked><label class="btn btn-outline-secondary" for="t3">T3</label>
                        </div>
                    </div>

                    <div class="row g-2 mb-3">
                        <div class="col-8">
                            <label class="form-label small fw-bold text-muted">燃油费率 (%)</label>
                            <input type="number" class="form-control" id="fuelInput" value="16.0" step="0.1">
                        </div>
                        <div class="col-4 d-flex align-items-end pb-2">
                             <span class="badge bg-light text-dark border small">指定85折</span>
                        </div>
                    </div>

                    <div class="row g-2 mb-3">
                        <div class="col-6">
                            <label class="form-label small fw-bold text-muted">目的地邮编</label>
                            <input type="text" class="form-control" id="zipCode" placeholder="5位ZIP">
                        </div>
                        <div class="col-6">
                            <label class="form-label small fw-bold text-muted">地址类型</label>
                            <select class="form-select" id="addrType">
                                <option value="res">🏠 住宅</option>
                                <option value="com">🏢 商业</option>
                            </select>
                        </div>
                    </div>

                    <div class="form-check form-switch mb-4">
                        <input class="form-check-input" type="checkbox" id="sigToggle">
                        <label class="form-check-label small" for="sigToggle">需要签名服务 (Signature)</label>
                    </div>

                    <div class="bg-light p-3 rounded border">
                        <label class="form-label small fw-bold text-muted mb-2">包裹信息 (英寸/磅)</label>
                        <div class="row g-2 mb-2">
                            <div class="col-4"><input type="number" id="dimL" class="form-control form-control-sm" placeholder="长 L"></div>
                            <div class="col-4"><input type="number" id="dimW" class="form-control form-control-sm" placeholder="宽 W"></div>
                            <div class="col-4"><input type="number" id="dimH" class="form-control form-control-sm" placeholder="高 H"></div>
                        </div>
                        <div class="input-group input-group-sm">
                            <span class="input-group-text">实重</span>
                            <input type="number" id="weight" class="form-control" placeholder="LBS">
                        </div>
                    </div>

                    <button class="btn btn-primary w-100 mt-4 py-2 fw-bold" id="btnCalc">开始计算</button>
                </div>
            </div>
        </div>

        <div class="col-lg-8">
            <div class="card h-100">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <span>📊 报价一览</span>
                    <span class="badge bg-warning text-dark badge-tier" id="resTierBadge">T3</span>
                </div>
                <div class="card-body">
                    <div class="alert alert-info py-2 small" id="pkgInfo">请在左侧录入数据...</div>
                    <div class="table-responsive">
                        <table class="table table-hover align-middle">
                            <thead class="table-light small text-secondary">
                                <tr>
                                    <th width="22%">渠道</th>
                                    <th width="8%">Zone</th>
                                    <th width="10%">计费重</th>
                                    <th width="15%">基础运费</th>
                                    <th width="25%">附加费明细</th>
                                    <th width="20%" class="text-end">总费用</th>
                                </tr>
                            </thead>
                            <tbody id="resBody">
                                <tr><td colspan="6" class="text-center py-4 text-muted">暂无结果</td></tr>
                            </tbody>
                        </table>
                    </div>
                    <div class="mt-3 small text-muted fst-italic border-top pt-2">
                        * 注：FedEx-632 / 超大包裹 已应用燃油费85折。XLmiles为一口价模式。
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<footer class="text-center py-4 text-muted small">
    &copy; 2026 SureGo Logistics | Data Generated: <span id="updateTime"></span>
</footer>

<script>
    const DATA = __JSON_DATA__;
    document.getElementById('updateTime').innerText = new Date().toLocaleDateString();

    // 1. 初始化仓库
    const whSelect = document.getElementById('whSelect');
    const whRegion = document.getElementById('whRegion');
    
    Object.keys(DATA.warehouses).forEach(code => {
        let opt = document.createElement('option');
        opt.value = code;
        opt.text = DATA.warehouses[code].name;
        whSelect.appendChild(opt);
    });
    
    whSelect.addEventListener('change', () => {
        let r = DATA.warehouses[whSelect.value].region;
        whRegion.innerText = `区域归属: ${r}`;
    });
    // 默认触发一次
    if(whSelect.options.length > 0) whSelect.dispatchEvent(new Event('change'));

    // 2. Zone 简易计算逻辑 (基于区域)
    function calcZone(destZip, originZip) {
        if(!destZip || destZip.length < 3) return 8;
        let d = parseInt(destZip.substring(0,3));
        let originRegion = DATA.warehouses[originZip].region;

        // 简化的逻辑：
        // 美西仓(9开头) -> 美西ZIP(9开头) = Zone2-4, 否则 Zone8
        if(originRegion === 'WEST') {
            if(d >= 900 && d <= 935) return 2;
            if(d >= 936 && d <= 994) return 4;
            return 8;
        }
        // 美东仓 -> 美东ZIP(0-1开头) = Zone2-4
        if(originRegion === 'EAST') {
            if(d >= 70 && d <= 89) return 2;
            if(d >= 100 && d <= 199) return 4;
            return 8;
        }
        // 美中
        if(originRegion === 'CENTRAL') {
             if(d >= 600 && d <= 629) return 2;
             return 6;
        }
        return 8; // 默认 Zone 8
    }

    // 3. 核心计算
    document.getElementById('btnCalc').onclick = () => {
        const whCode = whSelect.value;
        const tier = document.querySelector('input[name="tier"]:checked').value;
        const fuelRateInput = parseFloat(document.getElementById('fuelInput').value) || 0;
        const zip = document.getElementById('zipCode').value.trim();
        const isRes = document.getElementById('addrType').value === 'res';
        const sigOn = document.getElementById('sigToggle').checked;
        
        const pkg = {
            L: parseFloat(document.getElementById('dimL').value)||0,
            W: parseFloat(document.getElementById('dimW').value)||0,
            H: parseFloat(document.getElementById('dimH').value)||0,
            Wt: parseFloat(document.getElementById('weight').value)||0
        };

        document.getElementById('resTierBadge').innerText = tier;
        let vol = pkg.L * pkg.W * pkg.H;
        let dimWt = vol / 222; // 默认除222
        document.getElementById('pkgInfo').innerHTML = 
            `<b>当前包裹:</b> ${pkg.L}x${pkg.W}x${pkg.H}" | 实重:${pkg.Wt} lb | 体积重:${dimWt.toFixed(2)} lb`;

        const tbody = document.getElementById('resBody');
        tbody.innerHTML = '';
        let hasResult = false;

        // 遍历所有渠道
        Object.keys(DATA.channels).forEach(chName => {
            const conf = DATA.channels[chName];
            
            // 1. 仓库过滤
            if(!conf.allow_wh.includes(whCode)) return;

            // 2. 计费重 (XLmiles除外)
            let finalWt = Math.max(pkg.Wt, dimWt);
            if(!chName.includes("XLmiles") && finalWt > 1) {
                finalWt = Math.ceil(finalWt);
            }

            // 3. Zone
            let zone = calcZone(zip, whCode);

            // 4. 查表获取基础运费
            let priceTable = (DATA.tiers[tier][chName] || {}).prices || [];
            let row = priceTable.find(r => r.w >= finalWt - 0.001);
            
            if(!row) return; // 没找到对应重量，跳过

            // 优先找对应Zone，没有则找最大Zone(8)兜底
            let basePrice = row[zone] || row[8] || 0;
            if(basePrice <= 0) return;

            hasResult = true;

            // 5. 附加费计算
            let surcharges = 0;
            let details = [];

            // 住宅费 (硬编码金额)
            if(isRes && conf.res_fee > 0) {
                surcharges += conf.res_fee;
                details.push(`住宅 $${conf.res_fee}`);
            }

            // 签名费 (硬编码金额)
            if(sigOn && conf.sig_fee > 0) {
                surcharges += conf.sig_fee;
                details.push(`签名 $${conf.sig_fee}`);
            }

            // 燃油费 (含85折逻辑)
            if(chName.includes("FedEx") || chName.includes("GOFO")) {
                let appliedRate = fuelRateInput / 100;
                let tag = "";
                
                // 应用折扣
                if(conf.fuel_discount < 1.0) {
                    appliedRate = appliedRate * conf.fuel_discount;
                    tag = "(85折)";
                }

                // 燃油基数 = 基础费 + 住宅 + 签名
                let fuelAmt = (basePrice + surcharges) * appliedRate;
                surcharges += fuelAmt;
                details.push(`燃油${tag} $${fuelAmt.toFixed(2)}`);
            }

            let total = basePrice + surcharges;

            // 渲染行
            tbody.innerHTML += `
                <tr>
                    <td class="fw-bold text-nowrap">${chName}</td>
                    <td><span class="badge bg-light text-dark border">Z${zone}</span></td>
                    <td>${finalWt} lb</td>
                    <td>$${basePrice.toFixed(2)}</td>
                    <td class="small text-muted" style="line-height:1.2">${details.join('<br>') || '-'}</td>
                    <td class="text-end price-val">$${total.toFixed(2)}</td>
                </tr>
            `;
        });

        if(!hasResult) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-danger">无可用报价 (可能超重/超尺寸/仓库不支持)</td></tr>`;
        }
    };
</script>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# ==========================================
# 3. 后端处理逻辑
# ==========================================

def clean_money(val):
    """ 清洗金额字符串 """
    if pd.isna(val): return 0.0
    s = str(val).replace('$', '').replace(',', '').strip()
    try:
        return float(s)
    except:
        return 0.0

def find_sheet(excel_path, keywords, exclude_keywords=None):
    """ 根据关键词匹配 Excel Sheet """
    try:
        xl = pd.ExcelFile(excel_path)
        for sheet in xl.sheet_names:
            s_upper = sheet.upper().replace(" ", "")
            # 必须包含所有关键词
            if not all(k.upper() in s_upper for k in keywords):
                continue
            # 不能包含排除词
            if exclude_keywords and any(e.upper() in s_upper for e in exclude_keywords):
                continue
            return pd.read_excel(xl, sheet_name=sheet, header=None)
    except Exception as e:
        print(f"Error reading {excel_path}: {e}")
    return None

def extract_prices(df, split_mode=None):
    """ 
    提取价格表 
    split_mode: 'left' (取左半边), 'right' (取右半边), None (全表)
    """
    if df is None: return []
    
    # 1. 确定扫描范围
    total_cols = df.shape[1]
    col_start = 0
    col_end = total_cols
    
    if split_mode == 'left':
        col_end = total_cols // 2 + 2 # 左半区 (多预留2列防溢出)
    elif split_mode == 'right':
        col_start = total_cols // 2 - 2 # 右半区 (多预留2列)

    # 2. 寻找表头行 (必须包含 Weight 和 Zone)
    header_row_idx = -1
    zone_map = {} # {'Zone~1': col_idx, ...}
    weight_col_idx = -1
    
    # 扫描前 10 行
    for r in range(10):
        # 获取当前行在指定范围内的内容
        row_vals = [str(x).lower() for x in df.iloc[r, col_start:col_end].values]
        
        # 判断是否是表头
        has_weight = any('weight' in x or '重量' in x for x in row_vals)
        has_zone = any('zone' in x for x in row_vals)
        
        if has_weight and has_zone:
            header_row_idx = r
            break
    
    if header_row_idx == -1: return []

    # 3. 解析列索引
    row_data = df.iloc[header_row_idx]
    
    for c in range(col_start, col_end):
        if c >= total_cols: break
        val = str(row_data[c]).strip()
        val_lower = val.lower()
        
        # 找重量列
        if ('weight' in val_lower or '重量' in val_lower) and weight_col_idx == -1:
            weight_col_idx = c
        
        # 找 Zone 列 (支持 Zone~2, Zone 2, Zone-2)
        m = re.search(r'zone\D*(\d+)', val_lower)
        if m:
            z_num = int(m.group(1))
            zone_map[z_num] = c

    if weight_col_idx == -1 or not zone_map:
        return []

    # 4. 提取数据行
    prices = []
    for r in range(header_row_idx + 1, len(df)):
        try:
            # 读取重量
            w_raw = df.iloc[r, weight_col_idx]
            w_str = str(w_raw).lower().strip()
            
            # 处理 "1 oz", "0.5", "10 LB"
            weight_val = 0.0
            nums = re.findall(r'[\d\.]+', w_str)
            if not nums: continue
            
            val = float(nums[0])
            if 'oz' in w_str:
                weight_val = val / 16.0
            elif 'kg' in w_str:
                weight_val = val / 0.453592
            else:
                weight_val = val # 默认为 LB

            if weight_val <= 0: continue

            # 读取各 Zone 价格
            row_dict = {'w': weight_val}
            for z_num, c_idx in zone_map.items():
                p = clean_money(df.iloc[r, c_idx])
                if p > 0:
                    row_dict[z_num] = p
            
            if len(row_dict) > 1:
                prices.append(row_dict)

        except:
            continue
            
    # 按重量排序
    prices.sort(key=lambda x: x['w'])
    return prices

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    all_data = {
        "warehouses": WAREHOUSE_CONFIG,
        "channels": CHANNEL_MAP,
        "tiers": {}
    }

    # 遍历 T0-T3
    for tier, filename in TIER_FILES.items():
        print(f"Processing {tier} ({filename})...")
        path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(path):
            print(f"  [Warning] {filename} not found.")
            continue
        
        tier_data = {}
        
        # 遍历渠道
        for ch_key, conf in CHANNEL_MAP.items():
            # 1. 找 Sheet
            df = find_sheet(path, conf["keywords"], conf.get("exclude"))
            if df is None:
                continue
            
            # 2. 提取价格 (处理拆表逻辑)
            prices = extract_prices(df, split_mode=conf.get("split_mode"))
            if prices:
                tier_data[ch_key] = {"prices": prices}
                print(f"    Loaded {ch_key}: {len(prices)} rows")
        
        all_data["tiers"][tier] = tier_data

    # 生成 HTML
    json_str = json.dumps(all_data, ensure_ascii=False)
    # 处理可能的 NaN
    json_str = json_str.replace("NaN", "0")
    
    html_content = HTML_TEMPLATE.replace("__JSON_DATA__", json_str)
    
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print("\n✅ Build Success! Public/index.html generated.")

if __name__ == "__main__":
    main()
