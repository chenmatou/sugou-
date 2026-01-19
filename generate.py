import pandas as pd
import json
import re
import os
import warnings

# 忽略 Excel 样式警告
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# ==========================================
# 1. 全局配置 (绝对置顶，防止 NameError)
# ==========================================
DATA_DIR = "data"
OUTPUT_DIR = "public"

# Excel 文件名对应
TIER_FILES = {
    "T0": "T0.xlsx", 
    "T1": "T1.xlsx", 
    "T2": "T2.xlsx", 
    "T3": "T3.xlsx"
}

# 渠道映射
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

# 邮编库配置
ZIP_DB_SHEET = "GOFO-报价"
ZIP_COL_MAP = {
    "GOFO-报价": 5, "GOFO-MT-报价": 6, "UNIUNI-MT-报价": 7, "USPS-YSD-报价": 8,
    "FedEx-ECO-MT报价": 9, "XLmiles-报价": 10, "GOFO大件-GRO-报价": 11,
    "FedEx-632-MT-报价": 12, "FedEx-YSD-报价": 13
}

# 附加费
GLOBAL_SURCHARGES = {
    "fuel": 0.16, "res_fee": 3.50, "peak_res": 1.32,
    "peak_oversize": 54, "peak_unauthorized": 220,
    "oversize_fee": 130, "ahs_fee": 20, "unauthorized_fee": 1150
}

# 州名双语对照
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
# 2. 网页模板 (已修复 JS 错误)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>报价计算器 (Fixed)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        :root { --primary-color: #0d6efd; --header-bg: #000; }
        body { font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; background-color: #f4f6f9; min-height: 100vh; display: flex; flex-direction: column; }
        header { background-color: var(--header-bg); color: #fff; padding: 15px 0; border-bottom: 3px solid #333; }
        footer { background-color: var(--header-bg); color: #aaa; padding: 20px 0; margin-top: auto; text-align: center; font-size: 0.85rem; }
        .card { border: none; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 20px; }
        .card-header { background-color: #212529; color: #fff; font-weight: 600; padding: 10px 20px; border-radius: 8px 8px 0 0 !important; }
        .form-label { font-weight: 600; font-size: 0.85rem; color: #555; margin-bottom: 4px; }
        .input-group-text { font-size: 0.85rem; font-weight: 600; background-color: #e9ecef; }
        .form-control, .form-select { font-size: 0.9rem; }
        /* 状态灯 */
        .status-item { display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 4px; }
        .indicator { width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 6px; }
        .bg-ok { background-color: #198754; } .bg-warn { background-color: #ffc107; } .bg-err { background-color: #dc3545; }
        /* 表格 */
        .result-table th { background-color: #212529; color: #fff; text-align: center; font-size: 0.85rem; vertical-align: middle; }
        .result-table td { text-align: center; vertical-align: middle; font-size: 0.9rem; }
        .price-text { font-weight: 800; font-size: 1.1rem; color: #0d6efd; }
        #globalError { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); z-index: 9999; width: 80%; display: none; }
    </style>
</head>
<body>

<div id="globalError" class="alert alert-danger shadow-lg">
    <h5 class="alert-heading">⚠️ 系统运行错误</h5>
    <p id="errorMsg">未知错误</p>
</div>

<header>
    <div class="container d-flex justify-content-between align-items-center">
        <div><h5 class="m-0 fw-bold">📦 业务员报价助手</h5><small class="opacity-75">T0-T3 全渠道集成 (Final Fix)</small></div>
        <div class="text-end"><a href="https://www.fedex.com/en-us/shipping/fuel-surcharge.html" target="_blank" class="btn btn-sm btn-outline-secondary text-white border-secondary">⛽ FedEx燃油</a></div>
    </div>
</header>

<div class="container my-4">
    <div class="row g-4">
        <div class="col-lg-4">
            <div class="card h-100">
                <div class="card-header">1. 基础信息</div>
                <div class="card-body">
                    <form id="calcForm">
                        <div class="mb-3">
                            <label class="form-label">客户等级</label>
                            <div class="btn-group w-100" role="group">
                                <input type="radio" class="btn-check" name="tier" id="t0" value="T0"><label class="btn btn-outline-secondary" for="t0">T0</label>
                                <input type="radio" class="btn-check" name="tier" id="t1" value="T1"><label class="btn btn-outline-secondary" for="t1">T1</label>
                                <input type="radio" class="btn-check" name="tier" id="t2" value="T2"><label class="btn btn-outline-secondary" for="t2">T2</label>
                                <input type="radio" class="btn-check" name="tier" id="t3" value="T3" checked><label class="btn btn-outline-secondary" for="t3">T3</label>
                            </div>
                        </div>

                        <div class="mb-3">
                            <label class="form-label">目的地邮编 (Zip)</label>
                            <div class="input-group">
                                <input type="text" class="form-control" id="zipCode" placeholder="5位邮编">
                                <button class="btn btn-dark" type="button" id="btnLookup">查询</button>
                            </div>
                            <div id="locInfo" class="mt-1 small fw-bold text-muted ps-1">请输入邮编查询...</div>
                        </div>

                        <div class="row g-2 mb-3">
                            <div class="col-6">
                                <label class="form-label">地址类型</label>
                                <select class="form-select" id="addressType"><option value="res">🏠 住宅</option><option value="com">🏢 商业</option></select>
                            </div>
                            <div class="col-6">
                                <label class="form-label">燃油费率 %</label>
                                <input type="number" class="form-control" id="fuelRate" value="__FUEL__">
                            </div>
                        </div>
                        
                        <div class="form-check form-switch mb-3">
                            <input class="form-check-input" type="checkbox" id="peakToggle">
                            <label class="form-check-label" for="peakToggle">启用旺季附加费</label>
                        </div>

                        <hr>

                        <div class="mb-3">
                            <label class="form-label">包裹规格 (原始单位)</label>
                            <div class="row g-2">
                                <div class="col-4"><div class="input-group input-group-sm"><span class="input-group-text">L</span><input type="number" class="form-control" id="length"></div></div>
                                <div class="col-4"><div class="input-group input-group-sm"><span class="input-group-text">W</span><input type="number" class="form-control" id="width"></div></div>
                                <div class="col-4"><div class="input-group input-group-sm"><span class="input-group-text">H</span><input type="number" class="form-control" id="height"></div></div>
                                <div class="col-12"><select class="form-select form-select-sm" id="dimUnit"><option value="in">IN (英寸)</option><option value="cm">CM (厘米)</option><option value="mm">MM (毫米)</option></select></div>
                            </div>
                            <div class="row g-2 mt-2">
                                <div class="col-8"><div class="input-group input-group-sm"><span class="input-group-text">Weight</span><input type="number" class="form-control" id="weight"></div></div>
                                <div class="col-4"><select class="form-select form-select-sm" id="weightUnit"><option value="lb">LB</option><option value="oz">OZ</option><option value="kg">KG</option><option value="g">G</option></select></div>
                            </div>
                        </div>

                        <div class="bg-light p-2 rounded border mb-3">
                            <div class="fw-bold small mb-2 border-bottom">🚦 合规预检 (US Standard)</div>
                            <div id="checkList"><small class="text-muted">等待输入...</small></div>
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
                                    <th width="10%">计费重<br>(LB)</th>
                                    <th width="12%">基础运费</th>
                                    <th width="20%">附加费明细</th>
                                    <th width="15%">总费用</th>
                                    <th width="20%">状态</th>
                                </tr>
                            </thead>
                            <tbody id="resBody"></tbody>
                        </table>
                    </div>
                    <div class="mt-2 text-muted" style="font-size:0.75rem">
                        * 说明：UNIUNI/USPS 无燃油/住宅费；UNIUNI 按实重计费；其余体积重除数222。
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<footer><div class="container"><p>&copy; 2026 速狗海外仓 | Update: <span id="updateDate"></span></p></div></footer>

<script>
    window.onerror = function(msg, url, line) {
        document.getElementById('globalError').style.display = 'block';
        document.getElementById('errorMsg').innerText = `脚本错误: ${msg} (Line ${line})`;
        return false;
    };
</script>

<script>
    // 1. 数据注入
    let DATA = {};
    try {
        DATA = __JSON_DATA__;
    } catch(e) {
        throw new Error("数据初始化失败: JSON格式错误");
    }

    let CUR_ZONES = {};
    document.getElementById('updateDate').innerText = new Date().toLocaleDateString();

    // 2. 初始化检查
    window.addEventListener('load', function() {
        if (!DATA.zip_db || Object.keys(DATA.zip_db).length === 0) {
            document.getElementById('globalError').style.display = 'block';
            document.getElementById('errorMsg').innerHTML = '<strong>数据加载失败！</strong><br>未找到邮编数据库。请检查 data/T0.xlsx 是否存在且格式正确。';
        }
    });

    const RULES = {
        hasResFee: n => !/USPS|XLMILES|UNIUNI/i.test(n),
        hasFuel: n => !/USPS|UNIUNI/i.test(n)
    };

    function standardize(l, w, h, du, wt, wu) {
        let L=parseFloat(l)||0, W=parseFloat(w)||0, H=parseFloat(h)||0, Weight=parseFloat(wt)||0;
        if(du==='cm'){L/=2.54;W/=2.54;H/=2.54} else if(du==='mm'){L/=25.4;W/=25.4;H/=25.4}
        if(wu==='kg')Weight/=0.453592; else if(wu==='oz')Weight/=16; else if(wu==='g')Weight/=453.592;
        return {L,W,H,Wt:Weight};
    }

    function check(pkg) {
        let d=[pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
        let L=d[0], G=L+2*(d[1]+d[2]);
        let h = '';
        const item = (t, nok, warn) => {
            let c = nok ? 'bg-err' : (warn ? 'bg-warn' : 'bg-ok');
            let s = nok ? '超标' : (warn ? '警告' : '正常');
            return `<div class="status-item"><span>${t}</span><span><span class="indicator ${c}"></span>${s}</span></div>`;
        };
        h += item('超重 (>150lb)', pkg.Wt>150, pkg.Wt>50);
        h += item('超长 (>108")', L>108, L>96);
        h += item('超围 (>165")', G>165, G>130);
        
        let uFail = (L>20 || G>50 || pkg.Wt>20);
        h += `<div class="border-top mt-1 pt-1 fw-bold text-primary" style="font-size:0.8rem">UniUni 专有检查:</div>` + item('符合限制', uFail);
        document.getElementById('checkList').innerHTML = h;
    }

    ['length','width','height','weight','dimUnit','weightUnit'].forEach(id=>{
        document.getElementById(id).addEventListener('input', ()=>{
            let p = standardize(
                document.getElementById('length').value, document.getElementById('width').value, document.getElementById('height').value,
                document.getElementById('dimUnit').value, document.getElementById('weight').value, document.getElementById('weightUnit').value
            );
            check(p);
        })
    });

    // 查询邮编
    document.getElementById('btnLookup').onclick = () => {
        let z = document.getElementById('zipCode').value.trim();
        let d = document.getElementById('locInfo');
        if(!DATA.zip_db || !DATA.zip_db[z]) { d.innerHTML="<span class='text-danger'>❌ 未找到邮编</span>"; CUR_ZONES={}; return; }
        let i = DATA.zip_db[z];
        d.innerHTML = `<span class='text-success'>✅ ${i.sn} ${i.s} - ${i.c} [${i.r}]</span>`;
        CUR_ZONES = i.z;
    };

    // 计算
    document.getElementById('btnCalc').onclick = () => {
        let zip = document.getElementById('zipCode').value.trim();
        if((!CUR_ZONES || Object.keys(CUR_ZONES).length===0) && zip) document.getElementById('btnLookup').click();
        
        let tier = document.querySelector('input[name="tier"]:checked').value;
        let pkg = standardize(
            document.getElementById('length').value, document.getElementById('width').value, document.getElementById('height').value,
            document.getElementById('dimUnit').value, document.getElementById('weight').value, document.getElementById('weightUnit').value
        );
        let isPeak = document.getElementById('peakToggle').checked;
        let isRes = document.getElementById('addressType').value === 'res';
        let fuelRate = parseFloat(document.getElementById('fuelRate').value)/100;

        // 这里移除了导致报错的 resultSection.style.display 调用
        // 因为在新的布局中，结果区域是常驻的，或者是通过父级容器控制
        // 如果这里 id="resultSection" 实际上不可见，确保 HTML 中有 display:none
        // (修复版 HTML 中有 style="display:none;" 且 id 存在)
        let resSec = document.getElementById('resultSection');
        if(resSec) resSec.style.display = 'block';

        document.getElementById('tierBadge').innerText = tier;
        document.getElementById('pkgSummary').innerHTML = `<b>计费基准:</b> ${pkg.L.toFixed(1)}"${pkg.W.toFixed(1)}"${pkg.H.toFixed(1)} | 实重:${pkg.Wt.toFixed(2)}lb`;
        let tbody = document.getElementById('resBody'); tbody.innerHTML='';

        if(!DATA.tiers || !DATA.tiers[tier]) { tbody.innerHTML='<tr><td colspan="7" class="text-danger">❌ 该等级数据未加载，请检查后台文件</td></tr>'; return; }

        Object.keys(DATA.tiers[tier]).forEach(ch => {
            let prices = DATA.tiers[tier][ch].prices;
            if(!prices || prices.length === 0) return;

            let zone = CUR_ZONES[ch] || '-';
            let cWt = pkg.Wt;
            if(!ch.toUpperCase().includes('UNIUNI')) {
                let vWt = (pkg.L*pkg.W*pkg.H)/222;
                cWt = Math.max(pkg.Wt, vWt);
                if(!ch.includes('GOFO') && cWt>1) cWt = Math.ceil(cWt);
            }

            let row = null;
            cWt = cWt || 0;
            for(let r of prices) { if(r.w >= cWt-0.001) { row=r; break; } }
            
            let base=0, st="正常", cls="text-success", bg="";
            let zKey = zone==='1'?'2':zone;

            if(!row || zone==='-') { st="无分区/超重"; cls="text-muted"; bg="table-light"; }
            else {
                base = row[zKey];
                if(base===undefined && zKey==='1') base=row['2'];
                if(!base) { st="无报价"; cls="text-warning"; bg="table-warning"; base=0; }
            }

            let fees = {f:0, r:0, p:0, o:0}, details=[];
            if(base>0) {
                if(RULES.hasFuel(ch)) { fees.f = base*fuelRate; details.push(`燃油:$${fees.f.toFixed(2)}`); }
                if(isRes && RULES.hasResFee(ch)) { fees.r = DATA.surcharges.res_fee; details.push(`住宅:$${fees.r}`); }
                
                let d=[pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
                let L=d[0], G=L+2*(d[1]+d[2]);
                let isOver=(L>96||G>130), isUn=(L>108||G>165||pkg.Wt>150), isAhs=(L>48);

                if(ch.toUpperCase().includes('UNIUNI')) {
                    if(L>20||G>50||pkg.Wt>20) { st="超规不可发"; cls="text-danger fw-bold"; bg="table-danger"; base=0; }
                }

                if(base>0) {
                    if(isUn) { fees.o+=DATA.surcharges.unauthorized_fee; st="Unauthorized"; cls="text-danger fw-bold"; bg="table-danger"; }
                    else if(isOver) { fees.o+=DATA.surcharges.oversize_fee; st="Oversize"; cls="text-warning fw-bold"; bg="table-warning"; details.push(`超大:$${DATA.surcharges.oversize_fee}`); }
                    else if(isAhs && ch.toUpperCase().startsWith('FEDEX')) { fees.o+=DATA.surcharges.ahs_fee; details.push(`AHS:$${DATA.surcharges.ahs_fee}`); }
                    
                    if(isPeak) {
                        let p=0;
                        if(ch.toUpperCase().includes('USPS')) { p=0.35; details.push(`旺季(USPS):$${p}`); }
                        else {
                            if(isRes && RULES.hasResFee(ch)) p+=DATA.surcharges.peak_res;
                            if(isOver) p+=DATA.surcharges.peak_oversize;
                            if(isUn) p+=DATA.surcharges.peak_unauthorized;
                            if(p>0) details.push(`旺季:$${p.toFixed(2)}`);
                        }
                        fees.p = p;
                    }
                }
            }

            let tot = base + fees.f + fees.r + fees.p + fees.o;
            
            tbody.innerHTML += `<tr class="${bg}">
                <td class="fw-bold text-start">${ch}</td>
                <td><span class="badge bg-secondary">${zone}</span></td>
                <td>${cWt.toFixed(2)}</td>
                <td class="fw-bold">${base.toFixed(2)}</td>
                <td class="text-start small" style="line-height:1.2">${details.join('<br>')||'-'}</td>
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
# 3. 核心数据清洗 (防止崩溃的防火墙)
# ==========================================

def safe_float(val):
    try:
        if pd.isna(val) or val == "" or str(val).strip().lower() == "nan":
            return 0.0
        clean_val = str(val).replace('$', '').replace(',', '').strip()
        return float(clean_val)
    except:
        return 0.0

def get_sheet_by_name(excel_file, target_name):
    try:
        xl = pd.ExcelFile(excel_file, engine='openpyxl')
        if target_name in xl.sheet_names: 
            return pd.read_excel(xl, sheet_name=target_name, header=None)
        for sheet in xl.sheet_names:
            if target_name.replace(" ", "").lower() in sheet.replace(" ", "").lower():
                print(f"    > 匹配Sheet: {sheet} -> {target_name}")
                return pd.read_excel(xl, sheet_name=sheet, header=None)
        return None
    except Exception as e:
        print(f"    > 读取失败: {e}")
        return None

def load_zip_db():
    print("--- 1. 加载邮编库 (T0.xlsx) ---")
    path = os.path.join(DATA_DIR, TIER_FILES['T0'])
    if not os.path.exists(path):
        print(f"❌ 错误: {path} 不存在！")
        return {}
    
    df = get_sheet_by_name(path, ZIP_DB_SHEET)
    if df is None: return {}

    db = {}
    try:
        start = 0
        for i in range(100):
            cell = str(df.iloc[i,1]).strip()
            if cell.isdigit() and len(cell) == 5:
                start = i; break
        
        df = df.fillna("")
        
        for idx, row in df.iloc[start:].iterrows():
            z = str(row[1]).strip()
            z = z.zfill(5)
            
            if z.isdigit() and len(z)==5:
                zones = {}
                for k, v in ZIP_COL_MAP.items():
                    val = str(row[v]).strip()
                    if val in ['-', 'nan', '', 'None', '0', 0]:
                        zones[k] = None
                    else:
                        zones[k] = val
                
                sb = str(row[3]).strip().upper()
                db[z] = { 
                    "s": sb, 
                    "sn": US_STATES_CN.get(sb,''), 
                    "c": str(row[4]).strip(), 
                    "r": str(row[2]).strip(), 
                    "z": zones 
                }
    except Exception as e: 
        print(f"邮编解析错误: {e}")
    print(f"✅ 邮编库加载完毕: {len(db)} 条")
    return db

def to_lb(val):
    s = str(val).upper().strip()
    if pd.isna(val) or s=='NAN' or s=='': return None
    nums = re.findall(r"[\d\.]+", s)
    if not nums: return None
    n = float(nums[0])
    if 'OZ' in s: return n/16.0
    if 'KG' in s: return n/0.453592
    return n

def load_tiers():
    print("\n--- 2. 加载报价表 ---")
    all_tiers = {}
    for t_name, f_name in TIER_FILES.items():
        print(f"处理 {t_name}...")
        path = os.path.join(DATA_DIR, f_name)
        if not os.path.exists(path): continue
        
        t_data = {}
        for ch_key, sheet_name in CHANNEL_SHEET_MAP.items():
            df = get_sheet_by_name(path, sheet_name)
            if df is None: continue
            
            try:
                h_row = 0
                for i in range(50):
                    row_str = " ".join(df.iloc[i].astype(str).values).lower()
                    if "zone" in row_str and ("weight" in row_str or "lb" in row_str):
                        h_row = i; break
                
                headers = df.iloc[h_row].astype(str).str.lower().tolist()
                w_idx = -1; z_map = {}
                
                for i, v in enumerate(headers):
                    if ('weight' in v or 'lb' in v) and w_idx==-1: w_idx = i
                    m = re.search(r'zone\s*~?\s*(\d+)', v)
                    if m: 
                        zn = m.group(1)
                        if zn not in z_map: z_map[zn] = i
                
                if w_idx == -1: continue
                
                prices = []
                for i in range(h_row+1, len(df)):
                    row = df.iloc[i]
                    try:
                        w_val = row[w_idx]
                        lb = to_lb(w_val)
                        if lb is None: continue
                        
                        item = {'w': lb}
                        for z, col in z_map.items():
                            val = row[col]
                            clean_p = safe_float(val)
                            if clean_p > 0:
                                item[z] = clean_p
                        
                        if len(item) > 1:
                            prices.append(item)
                    except: continue
                
                prices.sort(key=lambda x: x['w'])
                t_data[ch_key] = {"prices": prices}
            except: pass
        all_tiers[t_name] = t_data
    return all_tiers

# ==========================================
# 4. 主程序
# ==========================================
if __name__ == '__main__':
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    
    # 1. 抓取
    final = {
        "zip_db": load_zip_db(),
        "tiers": load_tiers(),
        "surcharges": GLOBAL_SURCHARGES
    }
    
    # 2. 注入
    print("\n--- 3. 生成网页 ---")
    try:
        js_str = json.dumps(final, allow_nan=False)
    except ValueError as e:
        print(f"❌ 严重错误: 数据中包含 NaN (非数字)，请检查 Excel 清洗逻辑。错误: {e}")
        js_str = json.dumps(final).replace("NaN", "0")

    html = HTML_TEMPLATE.replace('__JSON_DATA__', js_str).replace('__FUEL__', str(GLOBAL_SURCHARGES['fuel']*100))
    
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    
    print("✅ 全部完成！请推送至 GitHub。")
