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

# 渠道关键词配置
# 逻辑：必须包含列表内【所有】关键词才匹配 Sheet
CHANNEL_KEYWORDS = {
    "GOFO-报价": ["GOFO", "报价"],
    "GOFO-MT-报价": ["GOFO", "MT"],
    "UNIUNI-MT-报价": ["UNIUNI"],
    "USPS-YSD-报价": ["USPS", "YSD"],
    "FedEx-ECO-MT报价": ["ECO", "MT"],
    "XLmiles-报价": ["XLmiles"],
    "GOFO大件-GRO-报价": ["GOFO", "大件"],
    "FedEx-632-MT-报价": ["632"],
    "FedEx-YSD-报价": ["FedEx", "YSD"]  # 必须同时包含 FedEx 和 YSD
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
# 2. 网页模板 (纯净版 V16)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>报价计算器 (V16)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { font-family: 'Segoe UI', sans-serif; background-color: #fff; font-size: 14px; }
        header { background: #000; color: #fff; padding: 10px 0; border-bottom: 2px solid #333; }
        .card { border: 1px solid #ddd; box-shadow: none; border-radius: 4px; }
        .card-header { background: #f8f9fa; font-weight: bold; border-bottom: 1px solid #ddd; padding: 8px 15px; }
        .form-label { font-weight: 600; font-size: 13px; margin-bottom: 2px; }
        .form-control, .form-select { border-radius: 2px; font-size: 13px; }
        .btn { border-radius: 2px; }
        
        /* 结果表格 - 极简风格 */
        .result-table th { background: #333; color: #fff; text-align: center; font-size: 12px; padding: 8px; }
        .result-table td { text-align: center; vertical-align: middle; border-bottom: 1px solid #eee; padding: 6px; }
        .price-text { color: #d63384; font-weight: 800; font-size: 15px; }
        .fuel-link { font-size: 12px; text-decoration: none; margin-left: 10px; }
        
        #globalError { display: none; background: #ffe6e6; color: #d00; padding: 10px; text-align: center; font-weight: bold; }
    </style>
</head>
<body>

<div id="globalError"></div>

<header>
    <div class="container d-flex justify-content-between align-items-center">
        <h6 class="m-0">📦 业务员报价助手 V16 (Fix)</h6>
        <a href="https://www.fedex.com.cn/en-us/shipping/historical-fuel-surcharge.html" target="_blank" class="text-white fuel-link">FedEx燃油</a>
    </div>
</header>

<div class="container my-3">
    <div class="row g-3">
        <div class="col-lg-4">
            <div class="card h-100">
                <div class="card-header">参数录入</div>
                <div class="card-body">
                    <form id="calcForm">
                        <div class="mb-3 border p-2 bg-light">
                            <label class="form-label">燃油费率 (%)</label>
                            <div class="row g-2">
                                <div class="col-6">
                                    <input type="number" class="form-control form-control-sm" id="genFuel" value="16.0">
                                    <div class="form-text" style="font-size:11px">通用 (FedEx/USPS)</div>
                                </div>
                                <div class="col-6">
                                    <input type="number" class="form-control form-control-sm" id="gofoFuel" value="15.0">
                                    <div class="form-text" style="font-size:11px">GOFO大件独立</div>
                                </div>
                            </div>
                        </div>

                        <div class="mb-3">
                            <label class="form-label">客户等级</label>
                            <div class="btn-group w-100">
                                <input type="radio" class="btn-check tier-radio" name="tier" id="t0" value="T0"><label class="btn btn-sm btn-outline-dark" for="t0">T0</label>
                                <input type="radio" class="btn-check tier-radio" name="tier" id="t1" value="T1"><label class="btn btn-sm btn-outline-dark" for="t1">T1</label>
                                <input type="radio" class="btn-check tier-radio" name="tier" id="t2" value="T2"><label class="btn btn-sm btn-outline-dark" for="t2">T2</label>
                                <input type="radio" class="btn-check tier-radio" name="tier" id="t3" value="T3" checked><label class="btn btn-sm btn-outline-dark" for="t3">T3</label>
                            </div>
                        </div>

                        <div class="mb-3">
                            <label class="form-label">邮编 (Zip)</label>
                            <div class="input-group input-group-sm">
                                <input type="text" class="form-control" id="zipCode" placeholder="5位数字">
                                <button class="btn btn-dark" type="button" id="btnLookup">查询</button>
                            </div>
                            <div id="locInfo" class="mt-1 fw-bold text-success" style="font-size:13px"></div>
                        </div>

                        <div class="row g-2 mb-3">
                            <div class="col-7"><select class="form-select form-select-sm" id="addressType"><option value="res">🏠 住宅地址</option><option value="com">🏢 商业地址</option></select></div>
                            <div class="col-5 pt-1"><div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="peakToggle"><label class="form-check-label" for="peakToggle">旺季费</label></div></div>
                        </div>

                        <hr>
                        <label class="form-label">包裹规格</label>
                        <div class="row g-1 mb-2">
                            <div class="col-3"><input type="number" class="form-control form-control-sm" id="length" placeholder="长"></div>
                            <div class="col-3"><input type="number" class="form-control form-control-sm" id="width" placeholder="宽"></div>
                            <div class="col-3"><input type="number" class="form-control form-control-sm" id="height" placeholder="高"></div>
                            <div class="col-3"><select class="form-select form-select-sm" id="dimUnit"><option value="in">IN</option><option value="cm">CM</option></select></div>
                        </div>
                        <div class="row g-1">
                            <div class="col-9"><input type="number" class="form-control form-control-sm" id="weight" placeholder="实重"></div>
                            <div class="col-3"><select class="form-select form-select-sm" id="weightUnit"><option value="lb">LB</option><option value="oz">OZ</option><option value="kg">KG</option></select></div>
                        </div>

                        <div id="checkList" class="mt-3 text-muted" style="font-size:12px"></div>
                        <button type="button" class="btn btn-primary w-100 mt-3" id="btnCalc">计 算</button>
                    </form>
                </div>
            </div>
        </div>

        <div class="col-lg-8">
            <div class="card h-100">
                <div class="card-header d-flex justify-content-between">
                    <span>计算结果</span>
                    <span id="tierLabel">T3</span>
                </div>
                <div class="card-body p-0">
                    <div class="p-2 border-bottom bg-light small" id="pkgSummary">等待输入...</div>
                    <div class="table-responsive">
                        <table class="table table-hover result-table m-0">
                            <thead><tr><th>渠道</th><th>分区</th><th>计费重</th><th>基础运费</th><th>明细</th><th>总费用</th><th>状态</th></tr></thead>
                            <tbody id="resBody"></tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
    let DATA = {};
    try { DATA = __JSON_DATA__; } catch(e) { 
        document.getElementById('globalError').innerText='数据加载失败: ' + e.message; 
        document.getElementById('globalError').style.display='block'; 
    }
    let CUR_ZONES = {};

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

    function check(p) {
        let d=[p.L, p.W, p.H].sort((a,b)=>b-a);
        let L=d[0], G=L+2*(d[1]+d[2]);
        let h = '';
        const row = (n, ok) => `<div class="d-flex justify-content-between mb-1"><span>${n}</span><span style="color:${ok?'green':'red'}">${ok?'√':'× 超标'}</span></div>`;
        h += row('USPS (70lb/130")', p.Wt<=70 && G<=130);
        h += row('UniUni (20lb/L20")', p.Wt<=20 && L<=20);
        h += row('FedEx (150lb/108")', p.Wt<=150 && L<=108);
        document.getElementById('checkList').innerHTML = h;
    }

    document.querySelectorAll('.tier-radio').forEach(el => el.addEventListener('change', () => { 
        if(document.getElementById('weight').value) document.getElementById('btnCalc').click(); 
    }));

    document.getElementById('btnLookup').onclick = () => {
        let z = document.getElementById('zipCode').value.trim();
        if(!DATA.zip_db || !DATA.zip_db[z]) { 
            document.getElementById('locInfo').innerText="❌ 未找到"; CUR_ZONES={}; return; 
        }
        let i = DATA.zip_db[z];
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

        document.getElementById('tierLabel').innerText = tier;
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

            let base=0, st="OK", bg="";
            let zKey = (zone==='1'?'2':zone);

            if(!row || zone==='-') { st="无报价"; bg="#f9f9f9"; }
            else { base = row[zKey]; if(!base) { base=0; st="缺数据"; } }

            let f=0, r=0, pk=0, ot=0, list=[];
            if(base > 0) {
                let u=ch.toUpperCase();
                // 住宅费
                if(isRes && u.includes('FEDEX') && !u.includes('ECO')) { 
                    r=DATA.surcharges.res_fee; list.push(`住宅:${r}`); 
                }
                
                // 超大
                let d=[p.L,p.W,p.H].sort((a,b)=>b-a);
                if(d[0]>96 || d[0]+2*(d[1]+d[2])>130) { 
                    ot=DATA.surcharges.oversize_fee; list.push(`超大:${ot}`); 
                }

                // 旺季
                if(isPeak) {
                    if(u.includes('USPS')) pk=0.35;
                    else { if(r>0) pk+=DATA.surcharges.peak_res; if(ot>0) pk+=DATA.surcharges.peak_oversize; }
                    if(pk>0) list.push(`旺季:${pk.toFixed(2)}`);
                }

                // 燃油费
                if(u.includes('GOFO') && u.includes('大件')) {
                    // GOFO大件特殊公式
                    let sub = base+r+pk+ot;
                    f = sub * gofoF;
                    list.push(`燃油:${f.toFixed(2)}`);
                } 
                else if(!u.includes('ECO') && !u.includes('GOFO') && !u.includes('XL') && !u.includes('UNI')) {
                    // 通用
                    f = base * genF;
                    list.push(`燃油:${f.toFixed(2)}`);
                }
            }

            let tot = base + f + r + pk + ot;
            let zDisplay = zone==='-' ? '-' : 'Z'+zone;

            tbody.innerHTML += `<tr style="background-color:${bg}">
                <td class="fw-bold text-start ps-2">${ch}</td>
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
# 3. 核心清洗逻辑 (Fix)
# ==========================================

def get_sheet(xl, keys):
    # 模糊匹配
    for name in xl.sheet_names:
        if all(k.upper() in name.upper() for k in keys):
            print(f"    > Sheet匹配成功: {name}")
            return pd.read_excel(xl, sheet_name=name, header=None)
    return None

def safe_float(val):
    # 强制清洗：去除 $ , 空格 等干扰
    try:
        s = str(val).replace('$','').replace(',','').strip()
        if not s or s.lower() == 'nan': return 0.0
        return float(s)
    except: return 0.0

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
        print(f"处理 {t_name}...")
        path = os.path.join(DATA_DIR, f_name)
        if not os.path.exists(path): continue
        xl = pd.ExcelFile(path, engine='openpyxl')
        t_data = {}
        for ch_key, keywords in CHANNEL_KEYWORDS.items():
            df = get_sheet(xl, keywords)
            if df is None: continue
            try:
                # FedEx-YSD 特殊处理：强制找 'Zone 2'
                is_fedex_ysd = "YSD" in ch_key and "FEDEX" in ch_key.upper()
                
                h_row = 0
                for i in range(50):
                    txt = " ".join(df.iloc[i].astype(str).values).lower()
                    # FedEx-YSD 必须匹配 zone 2
                    if is_fedex_ysd:
                        if "zone" in txt and "2" in txt and ("weight" in txt or "lb" in txt): h_row=i; break
                    else:
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
                            f_val = safe_float(row[col])
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
    print("✅ V16 完成！")
