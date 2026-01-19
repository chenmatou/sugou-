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

# 渠道关键词 (文件名包含列表内所有词即匹配)
CHANNEL_KEYWORDS = {
    "GOFO-报价": ["GOFO", "报价"],
    "GOFO-MT-报价": ["GOFO", "MT"],
    "UNIUNI-MT-报价": ["UNIUNI"],
    "USPS-YSD-报价": ["USPS"],
    "FedEx-ECO-MT报价": ["ECO", "MT"],
    "XLmiles-报价": ["XLmiles"],
    "GOFO大件-GRO-报价": ["GOFO", "大件"],
    "FedEx-632-MT-报价": ["632"],
    "FedEx-YSD-报价": ["YSD"] 
}

# 邮编库配置
ZIP_COL_MAP = {
    "GOFO-报价": 5, "GOFO-MT-报价": 6, "UNIUNI-MT-报价": 7, "USPS-YSD-报价": 8,
    "FedEx-ECO-MT报价": 9, "XLmiles-报价": 10, "GOFO大件-GRO-报价": 11,
    "FedEx-632-MT-报价": 12, "FedEx-YSD-报价": 13
}

# 兜底数据 (防止 KeyError)
GLOBAL_SURCHARGES = {
    "fuel": 0.16, 
    "res_fee": 3.50, "peak_res": 1.32,
    "peak_oversize": 54, "peak_unauthorized": 220,
    "oversize_fee": 130, "ahs_fee": 20, "unauthorized_fee": 1150
}

# ==========================================
# 2. 网页模板 (纯净无UI版)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>报价计算器 (V14)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { font-family: sans-serif; font-size: 14px; background: #fff; }
        .container { max-width: 1200px; margin-top: 20px; }
        /* 去除所有花哨样式 */
        .card, .card-header { border-radius: 0 !important; }
        .card-header { background: #eee; color: #000; font-weight: bold; border-bottom: 1px solid #ccc; }
        .btn-primary { background: #333; border-color: #333; border-radius: 0; }
        .btn-dark { border-radius: 0; }
        .form-control, .form-select { border-radius: 0; }
        
        /* 表格样式纯净版 */
        .table { font-size: 13px; }
        .table th { background: #f8f9fa; border-bottom: 2px solid #000; text-align: center; }
        .table td { text-align: center; vertical-align: middle; border-bottom: 1px solid #ddd; }
        
        /* 字体颜色保留功能性区分，但去掉背景色块 */
        .price-text { font-weight: bold; color: #d63384; font-size: 15px; }
        .text-err { color: red; font-weight: bold; }
        .text-warn { color: #e6a700; font-weight: bold; }
        
        #globalError { display: none; color: red; padding: 10px; border: 1px solid red; margin-bottom: 10px; }
        .fuel-link { font-size: 12px; margin-left: 5px; }
    </style>
</head>
<body>

<div class="container">
    <div id="globalError"></div>

    <div class="row mb-3 align-items-center">
        <div class="col-6"><h4 class="m-0">报价计算器 V14</h4></div>
        <div class="col-6 text-end">
            <a href="https://www.fedex.com.cn/en-us/shipping/historical-fuel-surcharge.html" target="_blank" class="fuel-link">查看 FedEx 燃油</a>
        </div>
    </div>

    <div class="row g-4">
        <div class="col-lg-4">
            <div class="card">
                <div class="card-header">参数设置</div>
                <div class="card-body">
                    <form id="calcForm">
                        <div class="mb-3">
                            <label class="form-label fw-bold">1. 燃油费率 (%)</label>
                            <div class="row g-2">
                                <div class="col-6">
                                    <input type="number" class="form-control form-control-sm" id="genFuel" value="16.0">
                                    <small class="text-muted">通用</small>
                                </div>
                                <div class="col-6">
                                    <input type="number" class="form-control form-control-sm" id="gofoFuel" value="15.0">
                                    <small class="text-muted">GOFO大件</small>
                                </div>
                            </div>
                        </div>

                        <div class="mb-3">
                            <label class="form-label fw-bold">2. 客户等级</label>
                            <div>
                                <label><input type="radio" name="tier" value="T0" class="tier-radio"> T0</label> &nbsp;
                                <label><input type="radio" name="tier" value="T1" class="tier-radio"> T1</label> &nbsp;
                                <label><input type="radio" name="tier" value="T2" class="tier-radio"> T2</label> &nbsp;
                                <label><input type="radio" name="tier" value="T3" class="tier-radio" checked> T3</label>
                            </div>
                        </div>

                        <div class="mb-3">
                            <label class="form-label fw-bold">3. 邮编</label>
                            <div class="input-group input-group-sm">
                                <input type="text" class="form-control" id="zipCode" placeholder="5位数字">
                                <button class="btn btn-dark" type="button" id="btnLookup">查询</button>
                            </div>
                            <div id="locInfo" class="mt-1 fw-bold text-success"></div>
                        </div>

                        <div class="mb-3">
                            <label class="form-label fw-bold">4. 地址 & 附加</label>
                            <div class="d-flex align-items-center">
                                <select class="form-select form-select-sm me-2" id="addressType">
                                    <option value="res">住宅地址</option>
                                    <option value="com">商业地址</option>
                                </select>
                                <div class="form-check form-switch ms-2">
                                    <input class="form-check-input" type="checkbox" id="peakToggle">
                                    <label class="form-check-label" for="peakToggle">旺季费</label>
                                </div>
                            </div>
                        </div>

                        <hr>
                        <label class="form-label fw-bold">5. 包裹规格</label>
                        <div class="row g-1 mb-2">
                            <div class="col-3"><input type="number" class="form-control form-control-sm" id="length" placeholder="长"></div>
                            <div class="col-3"><input type="number" class="form-control form-control-sm" id="width" placeholder="宽"></div>
                            <div class="col-3"><input type="number" class="form-control form-control-sm" id="height" placeholder="高"></div>
                            <div class="col-3"><select class="form-select form-select-sm" id="dimUnit"><option value="in">IN</option><option value="cm">CM</option></select></div>
                        </div>
                        <div class="row g-1">
                            <div class="col-9"><input type="number" class="form-control form-control-sm" id="weight" placeholder="重量"></div>
                            <div class="col-3"><select class="form-select form-select-sm" id="weightUnit"><option value="lb">LB</option><option value="oz">OZ</option><option value="kg">KG</option></select></div>
                        </div>

                        <div id="checkList" class="mt-3 small text-muted border-top pt-2"></div>
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
                    <div class="p-2 border-bottom bg-light" id="pkgSummary">请在左侧输入...</div>
                    <table class="table table-hover m-0">
                        <thead>
                            <tr>
                                <th width="20%">渠道</th>
                                <th width="8%">分区</th>
                                <th width="10%">计费重</th>
                                <th width="12%">基础运费</th>
                                <th width="20%">明细</th>
                                <th width="15%">总费用</th>
                                <th width="15%">状态</th>
                            </tr>
                        </thead>
                        <tbody id="resBody"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
    let DATA = {};
    try { DATA = __JSON_DATA__; } catch(e) { 
        document.getElementById('globalError').innerText = '数据加载失败: ' + e.message; 
        document.getElementById('globalError').style.display = 'block'; 
    }
    let CUR_ZONES = {};

    // 换算
    function standardize(l, w, h, du, wt, wu) {
        let L=parseFloat(l)||0, W=parseFloat(w)||0, H=parseFloat(h)||0, Wt=parseFloat(wt)||0;
        if(du==='cm'){L/=2.54;W/=2.54;H/=2.54}
        if(wu==='kg')Wt/=0.453592; else if(wu==='oz')Wt/=16;
        return {L,W,H,Wt};
    }

    // 体积重除数
    function getDivisor(n, vol) {
        let u=n.toUpperCase();
        if(u.includes('UNIUNI')) return 0;
        if(u.includes('USPS')) return vol>1728 ? 166 : 0;
        if(u.includes('ECO')) return vol<1728 ? 400 : 250;
        return 222;
    }

    // 合规检查
    function check(p) {
        let d=[p.L, p.W, p.H].sort((a,b)=>b-a);
        let L=d[0], G=L+2*(d[1]+d[2]);
        let h = '';
        const line = (n, ok) => `<div>${n}: <span class="${ok?'text-success':'text-err'}">${ok?'√':'× 超标'}</span></div>`;
        h += line('USPS (70lb/130")', p.Wt<=70 && G<=130);
        h += line('UniUni (20lb/L20")', p.Wt<=20 && L<=20);
        h += line('FedEx (150lb/108")', p.Wt<=150 && L<=108);
        document.getElementById('checkList').innerHTML = h;
    }

    // 自动计算触发
    document.querySelectorAll('.tier-radio').forEach(r => r.addEventListener('change', () => { 
        if(document.getElementById('weight').value) document.getElementById('btnCalc').click(); 
    }));
    
    // 邮编查询
    document.getElementById('btnLookup').onclick = () => {
        let z = document.getElementById('zipCode').value.trim();
        if(!DATA.zip_db || !DATA.zip_db[z]) { 
            document.getElementById('locInfo').innerText="× 未找到"; CUR_ZONES={}; return; 
        }
        let i = DATA.zip_db[z];
        // 极简显示：State - City
        document.getElementById('locInfo').innerText = `✅ ${i.s} - ${i.c}`;
        CUR_ZONES = i.z;
    };

    // 主计算逻辑
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

            let base=0, st="OK", cls="";
            let zKey = (zone==='1'?'2':zone); // Z1->Z2

            if(!row || zone==='-') { st="无报价"; cls="text-muted"; }
            else { base = row[zKey] || 0; if(!base) { st="缺数据"; cls="text-warn"; } }

            let f=0, r=0, pk=0, ot=0, list=[];
            if(base > 0) {
                let u=ch.toUpperCase();
                // 住宅费
                if(isRes && u.includes('FEDEX') && !u.includes('ECO')) { 
                    r=DATA.surcharges.res_fee; list.push(`住宅:${r}`); 
                }
                
                // 超大/超规 (简化通用逻辑，ECO特殊逻辑暂略以保稳定)
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
                    // (运费+杂费)*(1+燃油) -> 燃油部分 = (运费+杂费)*燃油率
                    let sub = base+r+pk+ot;
                    f = sub * gofoF;
                    list.push(`燃油:${f.toFixed(2)}`);
                } 
                else if(!u.includes('ECO') && !u.includes('GOFO') && !u.includes('XL') && !u.includes('UNI')) {
                    // FedEx/USPS 通用
                    f = base * genF;
                    list.push(`燃油:${f.toFixed(2)}`);
                }
            }

            let tot = base + f + r + pk + ot;
            
            // 纯净输出：Z1, Z2...
            let zDisplay = zone==='-' ? '-' : 'Z'+zone;
            
            tbody.innerHTML += `<tr>
                <td class="fw-bold text-start ps-2">${ch}</td>
                <td>${zDisplay}</td>
                <td>${cWt.toFixed(2)}</td>
                <td class="fw-bold">${base.toFixed(2)}</td>
                <td class="text-start small" style="color:#666">${list.join(' / ')||'-'}</td>
                <td class="price-text">$${tot>0?tot.toFixed(2):'-'}</td>
                <td class="${cls} small fw-bold">${st}</td>
            </tr>`;
        });
    };
</script>
</body>
</html>
"""

# ==========================================
# 3. 核心清洗逻辑 (加强版)
# ==========================================

def get_sheet(xl, keys):
    # 只要 Sheet 名包含列表里的所有词，就抓取
    for name in xl.sheet_names:
        if all(k.upper() in name.upper() for k in keys):
            return pd.read_excel(xl, sheet_name=name, header=None)
    return None

def load_zip_db():
    print("--- 加载邮编库 ---")
    path = os.path.join(DATA_DIR, TIER_FILES['T0'])
    if not os.path.exists(path): return {}
    
    xl = pd.ExcelFile(path, engine='openpyxl')
    # 尝试抓取邮编表
    df = get_sheet(xl, ["GOFO", "报价"]) 
    if df is None: return {}

    db = {}
    try:
        start = 0
        for i in range(100):
            val = str(df.iloc[i,1]).strip()
            if val.isdigit() and len(val)==5: start=i; break
        
        # 填充空值防报错
        df = df.fillna("")
        
        for _, row in df.iloc[start:].iterrows():
            z = str(row[1]).strip().zfill(5)
            if not z.isdigit(): continue
            zones = {}
            for k, v in ZIP_COL_MAP.items():
                zv = str(row[v]).strip()
                if zv in ['nan','-','','0','None']: zones[k] = None
                else: zones[k] = zv
            # 只取州名缩写和城市
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
                            # 暴力清洗: 非数字转0
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
    
    # 构建数据
    final = { 
        "zip_db": load_zip_db(), 
        "tiers": load_tiers(), 
        "surcharges": GLOBAL_SURCHARGES 
    }
    
    print("\n--- 生成网页 ---")
    # 强制不转义汉字，并替换 NaN
    js_str = json.dumps(final, ensure_ascii=False).replace("NaN", "0")
    
    # 替换占位符
    html = HTML_TEMPLATE.replace('__JSON_DATA__', js_str)
    
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    
    print("✅ 成功！V13 已生成。")
