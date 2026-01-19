import pandas as pd
import json
import re
import os
import warnings

# 忽略 Excel 样式警告
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# ==========================================
# 1. 全局配置
# ==========================================
DATA_DIR = "data"
OUTPUT_DIR = "public"

TIER_FILES = {
    "T0": "T0.xlsx", "T1": "T1.xlsx", "T2": "T2.xlsx", "T3": "T3.xlsx"
}

# 渠道关键词 (文件名包含这些词即匹配)
CHANNEL_KEYWORDS = {
    "GOFO-报价": ["GOFO", "报价"],
    "GOFO-MT-报价": ["GOFO", "MT"],
    "UNIUNI-MT-报价": ["UNIUNI"],
    "USPS-YSD-报价": ["USPS"],
    "FedEx-ECO-MT报价": ["ECO", "MT"],
    "XLmiles-报价": ["XLmiles"],
    "GOFO大件-GRO-报价": ["GOFO", "大件"],
    "FedEx-632-MT-报价": ["632"],
    "FedEx-YSD-报价": ["YSD"]  # 暴力匹配 YSD
}

# 邮编库配置
ZIP_COL_MAP = {
    "GOFO-报价": 5, "GOFO-MT-报价": 6, "UNIUNI-MT-报价": 7, "USPS-YSD-报价": 8,
    "FedEx-ECO-MT报价": 9, "XLmiles-报价": 10, "GOFO大件-GRO-报价": 11,
    "FedEx-632-MT-报价": 12, "FedEx-YSD-报价": 13
}

# 兜底数据
GLOBAL_SURCHARGES = {
    "fuel": 0.16, "res_fee": 3.50, "peak_res": 1.32,
    "peak_oversize": 54, "peak_unauthorized": 220,
    "oversize_fee": 130, "ahs_fee": 20, "unauthorized_fee": 1150
}

# ==========================================
# 2. 网页模板 (UI恢复，仅Zone去色)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>报价计算器 (V15)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        :root { --primary-color: #0d6efd; --header-bg: #000; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background-color: #f4f6f9; min-height: 100vh; display: flex; flex-direction: column; }
        header { background-color: var(--header-bg); color: #fff; padding: 12px 0; border-bottom: 3px solid #333; }
        footer { background-color: var(--header-bg); color: #aaa; padding: 20px 0; margin-top: auto; text-align: center; font-size: 0.8rem; }
        
        /* 恢复好看的卡片样式 */
        .card { border: none; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 20px; }
        .card-header { background-color: #212529; color: #fff; font-weight: 600; padding: 10px 20px; border-radius: 8px 8px 0 0 !important; }
        
        .form-label { font-weight: 600; font-size: 0.85rem; color: #555; margin-bottom: 4px; }
        .input-group-text { font-size: 0.85rem; font-weight: 600; background-color: #e9ecef; }
        .form-control, .form-select { font-size: 0.9rem; }
        
        .result-table th { background-color: #212529; color: #fff; text-align: center; font-size: 0.85rem; vertical-align: middle; }
        .result-table td { text-align: center; vertical-align: middle; font-size: 0.9rem; }
        .price-text { font-weight: 800; font-size: 1.1rem; color: #0d6efd; }
        
        /* 错误提示 */
        #globalError { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); z-index: 9999; width: 80%; display: none; }
        
        /* 状态灯 */
        .indicator { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .bg-ok { background-color: #198754; } .bg-err { background-color: #dc3545; }
        
        .fuel-link { font-size: 0.75rem; text-decoration: none; color: #0d6efd; display: block; margin-top: 2px; }
    </style>
</head>
<body>

<div id="globalError" class="alert alert-danger shadow-lg">
    <h5 class="alert-heading">⚠️ 系统运行错误</h5>
    <p id="errorMsg">未知错误</p>
</div>

<header>
    <div class="container d-flex justify-content-between align-items-center">
        <div><h5 class="m-0 fw-bold">📦 业务员报价助手</h5><small class="opacity-75">T0-T3 专家版 (V15)</small></div>
        <div class="text-end"><a href="https://www.fedex.com.cn/en-us/shipping/historical-fuel-surcharge.html" target="_blank" class="text-white small" style="text-decoration:none;">⛽ FedEx燃油官网</a></div>
    </div>
</header>

<div class="container my-4">
    <div class="row g-4">
        <div class="col-lg-4">
            <div class="card h-100">
                <div class="card-header">1. 基础信息录入</div>
                <div class="card-body">
                    <form id="calcForm">
                        <div class="bg-light p-2 rounded border mb-3">
                            <div class="fw-bold small mb-2 border-bottom">⛽ 燃油费率</div>
                            <div class="row g-2">
                                <div class="col-6 border-end">
                                    <label class="form-label small">通用燃油 (%)</label>
                                    <input type="number" class="form-control form-control-sm" id="genFuel" value="16.0">
                                </div>
                                <div class="col-6">
                                    <label class="form-label small">GOFO大件 (%)</label>
                                    <input type="number" class="form-control form-control-sm" id="gofoFuel" value="15.0">
                                </div>
                            </div>
                        </div>

                        <div class="mb-3">
                            <label class="form-label">客户等级</label>
                            <div class="btn-group w-100" role="group">
                                <input type="radio" class="btn-check tier-radio" name="tier" id="t0" value="T0"><label class="btn btn-outline-secondary" for="t0">T0</label>
                                <input type="radio" class="btn-check tier-radio" name="tier" id="t1" value="T1"><label class="btn btn-outline-secondary" for="t1">T1</label>
                                <input type="radio" class="btn-check tier-radio" name="tier" id="t2" value="T2"><label class="btn btn-outline-secondary" for="t2">T2</label>
                                <input type="radio" class="btn-check tier-radio" name="tier" id="t3" value="T3" checked><label class="btn btn-outline-secondary" for="t3">T3</label>
                            </div>
                        </div>

                        <div class="mb-3">
                            <label class="form-label">目的地邮编 (Zip)</label>
                            <div class="input-group">
                                <input type="text" class="form-control" id="zipCode" placeholder="5位邮编">
                                <button class="btn btn-dark" type="button" id="btnLookup">查询</button>
                            </div>
                            <div id="locInfo" class="mt-1 small fw-bold text-success ps-1"></div>
                        </div>

                        <div class="row g-2 mb-3">
                            <div class="col-7">
                                <label class="form-label">地址类型</label>
                                <select class="form-select" id="addressType"><option value="res">🏠 住宅地址</option><option value="com">🏢 商业地址</option></select>
                            </div>
                            <div class="col-5 pt-4">
                                <div class="form-check form-switch">
                                    <input class="form-check-input" type="checkbox" id="peakToggle">
                                    <label class="form-check-label small fw-bold" for="peakToggle">旺季费</label>
                                </div>
                            </div>
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
                                <div class="col-4"><select class="form-select form-select-sm" id="weightUnit"><option value="lb">LB</option><option value="oz">OZ</option><option value="kg">KG</option><option value="g">G</option></select></div>
                            </div>
                        </div>

                        <div class="bg-light p-2 rounded border mb-3">
                            <div class="fw-bold small mb-2 border-bottom">🚦 渠道合规性检查</div>
                            <div id="checkList" class="small text-muted">等待输入...</div>
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
                    <div class="table-responsive">
                        <table class="table table-bordered table-hover result-table">
                            <thead>
                                <tr>
                                    <th width="15%">渠道</th>
                                    <th width="8%">分区</th>
                                    <th width="10%">计费重</th>
                                    <th width="12%">基础运费</th>
                                    <th width="20%">明细</th>
                                    <th width="15%">总费用</th>
                                    <th width="20%">状态</th>
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

<footer><div class="container"><p>&copy; 2026 速狗海外仓 | Update: <span id="updateDate"></span></p></div></footer>

<script>
    // 错误处理
    window.onerror = function(msg, u, l) { 
        document.getElementById('globalError').style.display='block'; 
        document.getElementById('errorMsg').innerText=`${msg} (L${l})`; 
    };

    let DATA = {};
    try { DATA = __JSON_DATA__; } catch(e) { throw new Error("JSON数据加载失败"); }
    let CUR_ZONES = {};
    document.getElementById('updateDate').innerText = new Date().toLocaleDateString();

    // 核心工具函数
    function standardize(l, w, h, du, wt, wu) {
        let L=parseFloat(l)||0, W=parseFloat(w)||0, H=parseFloat(h)||0, Wt=parseFloat(wt)||0;
        if(du==='cm'){L/=2.54;W/=2.54;H/=2.54}
        if(wu==='kg')Wt/=0.453592; else if(wu==='oz')Wt/=16;
        return {L,W,H,Wt};
    }

    function getDivisor(n, vol) {
        let u=n.toUpperCase();
        if(u.includes('UNIUNI')) return 0;
        if(u.includes('USPS')) return vol>1728 ? 166 : 0;
        if(u.includes('ECO')) return vol<1728 ? 400 : 250;
        return 222;
    }

    // 实时检测
    function check(p) {
        let d=[p.L, p.W, p.H].sort((a,b)=>b-a);
        let L=d[0], G=L+2*(d[1]+d[2]);
        let h = '';
        const row = (n, ok) => `<div class="d-flex justify-content-between mb-1"><span>${n}</span><span class="${ok?'text-success':'text-danger'}">${ok?'√ 正常':'× 超标'}</span></div>`;
        h += row('USPS (70lb/130")', p.Wt<=70 && G<=130);
        h += row('UniUni (20lb/L20")', p.Wt<=20 && L<=20);
        h += row('FedEx (150lb/108")', p.Wt<=150 && L<=108);
        document.getElementById('checkList').innerHTML = h;
    }

    // 事件绑定
    document.querySelectorAll('.tier-radio').forEach(r => r.addEventListener('change', () => { 
        if(document.getElementById('weight').value) document.getElementById('btnCalc').click(); 
    }));

    ['length','width','height','weight'].forEach(id => {
        document.getElementById(id).addEventListener('input', () => {
             // 简单的输入监听，实际计算还是点按钮
        });
    });

    document.getElementById('btnLookup').onclick = () => {
        let z = document.getElementById('zipCode').value.trim();
        if(!DATA.zip_db || !DATA.zip_db[z]) { 
            document.getElementById('locInfo').innerText="❌ 未找到"; CUR_ZONES={}; return; 
        }
        let i = DATA.zip_db[z];
        // 纯净显示：State - City
        document.getElementById('locInfo').innerText = `✅ ${i.s} - ${i.c}`;
        CUR_ZONES = i.z;
    };

    document.getElementById('btnCalc').onclick = () => {
        if((!CUR_ZONES || Object.keys(CUR_ZONES).length===0) && document.getElementById('zipCode').value) {
            document.getElementById('btnLookup').click();
        }
        
        let tier = document.querySelector('input[name="tier"]:checked').value;
        let p = standardize(
            document.getElementById('length').value, document.getElementById('width').value, 
            document.getElementById('height').value, document.getElementById('dimUnit').value, 
            document.getElementById('weight').value, document.getElementById('weightUnit').value
        );
        let isPeak = document.getElementById('peakToggle').checked;
        let isRes = document.getElementById('addressType').value === 'res';
        let genF = parseFloat(document.getElementById('genFuel').value)/100;
        let gofoF = parseFloat(document.getElementById('gofoFuel').value)/100;

        document.getElementById('tierBadge').innerText = tier;
        document.getElementById('pkgSummary').innerText = `${p.L.toFixed(1)}x${p.W.toFixed(1)}x${p.H.toFixed(1)}" | ${p.Wt.toFixed(2)}lb`;
        let tbody = document.getElementById('resBody'); tbody.innerHTML='';
        check(p);

        if(!DATA.tiers || !DATA.tiers[tier]) return;

        Object.keys(DATA.tiers[tier]).forEach(ch => {
            let prices = DATA.tiers[tier][ch].prices;
            if(!prices) return;

            let zone = CUR_ZONES[ch] || '-';
            let vol = p.L * p.W * p.H;
            let div = getDivisor(ch, vol);
            let cWt = (div > 0) ? Math.max(p.Wt, vol/div) : p.Wt;
            if(!ch.includes('GOFO') && cWt>1) cWt = Math.ceil(cWt);

            let row = null;
            let sWt = parseFloat(cWt)||0;
            for(let r of prices) { if(r.w >= sWt-0.001) { row=r; break; } }

            let base=0, st="正常", bg=""; 
            let zKey = (zone==='1'?'2':zone); // Z1->Z2

            if(!row || zone==='-') { st="无报价"; bg="table-light"; }
            else { base = row[zKey]; if(!base) { base=0; st="缺数据"; } }

            let f=0, r=0, pk=0, ot=0, list=[];
            if(base > 0) {
                let u = ch.toUpperCase();
                // 住宅费
                if(isRes && u.includes('FEDEX') && !u.includes('ECO')) { 
                    r=DATA.surcharges.res_fee; list.push(`住宅:${r}`); 
                }
                
                // 超大检查 (简化版, 保证稳定)
                let d=[p.L,p.W,p.H].sort((a,b)=>b-a);
                if(d[0]>96 || d[0]+2*(d[1]+d[2])>130) { 
                    ot=DATA.surcharges.oversize_fee; list.push(`超大:${ot}`); 
                }

                // 旺季费
                if(isPeak) {
                    if(u.includes('USPS')) pk=0.35;
                    else { if(r>0) pk+=DATA.surcharges.peak_res; if(ot>0) pk+=DATA.surcharges.peak_oversize; }
                    if(pk>0) list.push(`旺季:${pk.toFixed(2)}`);
                }

                // 燃油费
                if(u.includes('GOFO') && u.includes('大件')) {
                    // GOFO大件公式: (运费+杂费)*(1+燃油) -> 燃油部分
                    let sub = base+r+pk+ot;
                    f = sub * gofoF;
                    list.push(`燃油:${f.toFixed(2)}`);
                } 
                else if(!u.includes('ECO') && !u.includes('GOFO') && !u.includes('XL') && !u.includes('UNI')) {
                    // 通用燃油
                    f = base * genF;
                    list.push(`燃油:${f.toFixed(2)}`);
                }
            }

            let tot = base + f + r + pk + ot;
            
            // 纯净显示分区：直接显示 Z1, Z2... 无颜色
            let zDisplay = zone==='-' ? '-' : 'Z'+zone;

            tbody.innerHTML += `<tr class="${bg}">
                <td class="fw-bold text-start ps-3">${ch}</td>
                <td>${zDisplay}</td>
                <td>${cWt.toFixed(2)}</td>
                <td class="fw-bold">${base.toFixed(2)}</td>
                <td class="text-start small" style="color:#666">${list.join(' / ')||'-'}</td>
                <td class="price-text">$${tot>0?tot.toFixed(2):'-'}</td>
                <td class="small">${st}</td>
            </tr>`;
        });
    };
</script>
</body>
</html>
"""

# ==========================================
# 3. 核心清洗逻辑
# ==========================================

def get_sheet(xl, keys):
    for name in xl.sheet_names:
        if all(k.upper() in name.upper() for k in keys):
            return pd.read_excel(xl, sheet_name=name, header=None)
    return None

def load_zip_db():
    print("--- 加载邮编库 ---")
    path = os.path.join(DATA_DIR, TIER_FILES['T0'])
    if not os.path.exists(path): return {}
    xl = pd.ExcelFile(path, engine='openpyxl')
    df = get_sheet(xl, ["GOFO", "报价"])
    if df is None: return {}
    db = {}
    try:
        start = 0
        for i in range(100):
            val = str(df.iloc[i,1]).strip()
            if val.isdigit() and len(val)==5: start=i; break
        df = df.fillna("")
        for _, row in df.iloc[start:].iterrows():
            z = str(row[1]).strip().zfill(5)
            if not z.isdigit(): continue
            zones = {}
            for k, v in ZIP_COL_MAP.items():
                zv = str(row[v]).strip()
                zones[k] = zv if zv not in ['nan','-','','0','None'] else None
            sb = str(row[3]).strip().upper()
            ct = str(row[4]).strip()
            db[z] = { "s": sb, "c": ct, "z": zones }
    except: pass
    return db

def load_tiers():
    print("--- 加载报价表 ---")
    all_tiers = {}
    for t_name, f_name in TIER_FILES.items():
        path = os.path.join(DATA_DIR, f_name)
        if not os.path.exists(path): continue
        xl = pd.ExcelFile(path, engine='openpyxl')
        t_data = {}
        for ch_key, keywords in CHANNEL_KEYWORDS.items():
            df = get_sheet(xl, keywords)
            if df is None: continue
            try:
                h_row = 0
                for i in range(50):
                    txt = " ".join(df.iloc[i].astype(str).values).lower()
                    if "zone" in txt and ("weight" in txt or "lb" in txt): h_row=i; break
                headers = df.iloc[h_row].astype(str).str.lower().tolist()
                w_idx = -1; z_map = {}
                for i, v in enumerate(headers):
                    if ('weight' in v or 'lb' in v) and w_idx==-1: w_idx=i
                    m = re.search(r'zone\s*~?\s*(\d+)', v)
                    if m: z_map[m.group(1)] = i
                if w_idx == -1: continue
                prices = []
                for _, row in df.iloc[h_row+1:].iterrows():
                    try:
                        w_raw = str(row[w_idx]).upper().strip()
                        nums = re.findall(r"[\d\.]+", w_raw)
                        if not nums: continue
                        w = float(nums[0])
                        if 'OZ' in w_raw: w/=16.0
                        elif 'KG' in w_raw: w/=0.453592
                        item = {'w': w}
                        for zk, col in z_map.items():
                            val = str(row[col]).replace('$','').replace(',','').strip()
                            try: f_val = float(val)
                            except: f_val = 0.0
                            if f_val > 0: item[zk] = f_val
                        if len(item) > 1: prices.append(item)
                    except: continue
                prices.sort(key=lambda x: x['w'])
                t_data[ch_key] = {"prices": prices}
            except: pass
        all_tiers[t_name] = t_data
    return all_tiers

if __name__ == '__main__':
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    final = { "zip_db": load_zip_db(), "tiers": load_tiers(), "surcharges": GLOBAL_SURCHARGES }
    print("\n--- 生成网页 ---")
    try: js_str = json.dumps(final, allow_nan=False)
    except: js_str = json.dumps(final).replace("NaN", "0")
    html = HTML_TEMPLATE.replace('__JSON_DATA__', js_str).replace('__FUEL__', str(GLOBAL_SURCHARGES['fuel']*100))
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f: f.write(html)
    print("✅ V15 完成！")
