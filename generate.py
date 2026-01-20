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

# 渠道 Sheet 匹配关键词
CHANNEL_KEYWORDS = {
    "GOFO-报价": ["GOFO", "报价"],
    "GOFO-MT-报价": ["GOFO", "MT"],
    "UNIUNI-MT-报价": ["UNIUNI"],
    "USPS-YSD-报价": ["USPS"],
    "FedEx-ECO-MT报价": ["ECO", "MT"],
    "XLmiles-报价": ["XLmiles"],
    "GOFO大件-GRO-报价": ["GOFO", "大件"],
    "FedEx-632-MT-报价": ["632"],
    "FedEx-YSD-报价": ["FedEx", "YSD"] 
}

# 邮编库配置
# 说明：GOFO保持独立列，其他渠道请确保对应的是“美国标准分区”所在的列
ZIP_DB_SHEET_KEY = "GOFO-报价"
ZIP_COL_MAP = {
    "GOFO-报价": 5,             # GOFO 独立区域
    "GOFO-MT-报价": 6,          # GOFO 独立区域
    "UNIUNI-MT-报价": 7,        # 标准或指定列
    "USPS-YSD-报价": 8,         # 标准或指定列
    "FedEx-ECO-MT报价": 9,      # 标准或指定列
    "XLmiles-报价": 10,
    "GOFO大件-GRO-报价": 11,
    "FedEx-632-MT-报价": 12,
    "FedEx-YSD-报价": 13        # 标准或指定列 (请确认Excel中该列号正确)
}

# 默认附加费 (兜底用，USPS-YSD会优先读表)
GLOBAL_SURCHARGES = {
    "res_fee": 3.50, 
    "peak_res": 1.32,
    "peak_oversize": 54, 
    "peak_unauthorized": 220,
    "oversize_fee": 130, 
    "ahs_fee": 20, 
    "unauthorized_fee": 1150
}

# 州名映射 (用于标准地图显示)
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
# 2. 网页模板
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>业务员报价助手 (V11 - 独立燃油/USPS旺季表/标准地图)</title>
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
        .status-table { width: 100%; font-size: 0.85rem; }
        .status-table td { padding: 6px; border-bottom: 1px solid #eee; vertical-align: middle; }
        .indicator { display: inline-block; padding: 2px 8px; border-radius: 4px; color: #fff; font-weight: bold; font-size: 0.75rem; }
        .bg-ok { background-color: #198754; } .bg-warn { background-color: #ffc107; color:#000; } .bg-err { background-color: #dc3545; }
        .result-table th { background-color: #212529; color: #fff; text-align: center; font-size: 0.85rem; vertical-align: middle; }
        .result-table td { text-align: center; vertical-align: middle; font-size: 0.9rem; }
        .price-text { font-weight: 800; font-size: 1.1rem; color: #0d6efd; }
        .fuel-link { font-size: 0.75rem; text-decoration: none; color: #0d6efd; display: block; margin-top: 3px; }
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
        <div><h5 class="m-0 fw-bold">📦 业务员报价助手</h5><small class="opacity-75">T0-T3 旗舰版 (V11.0)</small></div>
        <div class="text-end text-white small">Multi-Channel & Fuel Separate</div>
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
                            <div class="fw-bold small mb-2 border-bottom">⛽ 燃油费率 (独立配置)</div>
                            <div class="row g-2">
                                <div class="col-4">
                                    <label class="form-label small">FedEx (%)</label>
                                    <input type="number" class="form-control form-control-sm" id="fedexFuel" value="16.0">
                                </div>
                                <div class="col-4">
                                    <label class="form-label small">USPS (%)</label>
                                    <input type="number" class="form-control form-control-sm" id="uspsFuel" value="0.0">
                                </div>
                                <div class="col-4">
                                    <label class="form-label small">GOFO大件(%)</label>
                                    <input type="number" class="form-control form-control-sm" id="gofoFuel" value="15.0">
                                </div>
                                <div class="col-12 text-end">
                                     <a href="https://www.fedex.com.cn/en-us/shipping/historical-fuel-surcharge.html" target="_blank" class="fuel-link">🔗 FedEx燃油官网</a>
                                </div>
                            </div>
                        </div>

                        <div class="mb-3">
                            <label class="form-label">客户等级 (自动计算)</label>
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
                            <div class="col-7">
                                <label class="form-label">地址类型</label>
                                <select class="form-select" id="addressType"><option value="res">🏠 住宅 (Residential)</option><option value="com">🏢 商业 (Commercial)</option></select>
                            </div>
                            <div class="col-5 pt-4">
                                <div class="form-check form-switch">
                                    <input class="form-check-input" type="checkbox" id="peakToggle">
                                    <label class="form-check-label small fw-bold" for="peakToggle">旺季附加费</label>
                                </div>
                            </div>
                        </div>

                        <hr>

                        <div class="mb-3">
                            <label class="form-label">包裹规格 (中文/原始单位)</label>
                            <div class="row g-2">
                                <div class="col-4"><div class="input-group input-group-sm"><span class="input-group-text">长</span><input type="number" class="form-control" id="length" placeholder="L"></div></div>
                                <div class="col-4"><div class="input-group input-group-sm"><span class="input-group-text">宽</span><input type="number" class="form-control" id="width" placeholder="W"></div></div>
                                <div class="col-4"><div class="input-group input-group-sm"><span class="input-group-text">高</span><input type="number" class="form-control" id="height" placeholder="H"></div></div>
                                <div class="col-12"><select class="form-select form-select-sm" id="dimUnit"><option value="in">IN (英寸)</option><option value="cm">CM (厘米)</option><option value="mm">MM (毫米)</option></select></div>
                            </div>
                            <div class="row g-2 mt-2">
                                <div class="col-8"><div class="input-group input-group-sm"><span class="input-group-text">重量</span><input type="number" class="form-control" id="weight" placeholder="实重"></div></div>
                                <div class="col-4"><select class="form-select form-select-sm" id="weightUnit"><option value="lb">LB (磅)</option><option value="oz">OZ (盎司)</option><option value="kg">KG (千克)</option><option value="g">G (克)</option></select></div>
                            </div>
                        </div>

                        <div class="bg-light p-2 rounded border mb-3">
                            <div class="fw-bold small mb-2 border-bottom">🚦 各渠道合规性一览</div>
                            <table class="status-table" id="checkTable">
                                <tr><td class="text-muted">等待输入尺寸...</td></tr>
                            </table>
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
                    <div class="mt-2 text-muted small border-top pt-2">
                        <strong>计费逻辑说明：</strong><br>
                        1. <strong>GOFO大件</strong>：燃油独立，住宅/商业逻辑生效。<br>
                        2. <strong>USPS-YSD</strong>：旺季费率严格按照表格内“旺季”列计算，燃油独立。<br>
                        3. <strong>FedEx渠道</strong>：严格区分住宅/商业地址，燃油独立。<br>
                        4. <strong>邮编逻辑</strong>：GOFO独立分区；其他渠道使用美国标准地图分区显示。<br>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<footer><div class="container"><p>&copy; 2026 速狗海外仓 | Update: <span id="updateDate"></span></p></div></footer>

<script>
    window.onerror = function(msg, u, l) { document.getElementById('globalError').style.display='block'; document.getElementById('errorMsg').innerText=`${msg} (Line ${l})`; };
</script>

<script>
    let DATA = {};
    try { DATA = __JSON_DATA__; } catch(e) { throw new Error("Data Init Failed"); }
    let CUR_ZONES = {};
    document.getElementById('updateDate').innerText = new Date().toLocaleDateString();

    // 自动计算监听
    document.querySelectorAll('input[name="tier"]').forEach(r => {
        r.addEventListener('change', () => { 
            if(document.getElementById('weight').value) document.getElementById('btnCalc').click(); 
        });
    });

    // ===================================
    // 核心业务配置 (Expert Logic V11)
    // ===================================
    
    // 指定必须计算住宅费的渠道 (白名单)
    const RES_FEE_CHANNELS = [
        "FEDEX-ECO-MT",
        "FEDEX-YSD",
        "FEDEX-632-MT",
        "GOFO大件-GRO" // 包含 GOFO 大件 GRO
    ];

    const USPS_BLOCK = ['006','007','008','009','090','091','092','093','094','095','096','097','098','099','340','962','963','964','965','966','967','968','969','995','996','997','998','999'];

    const ECO_FEES = {
        ahs: [6.55, 7.28, 8.03, 8.92],
        overweight: [10.26, 11.14, 11.89, 12.92],
        oversize: [71.28, 77.97, 84.64, 91.33],
        nonstd: [5.80, 6.84, 7.14, 7.43]
    };

    const RULES = {
        // 住宅费判断：只对指定的 FedEx 和 GOFO-GRO 生效
        hasResFee: n => {
            let u = n.toUpperCase();
            // 检查当前渠道是否在白名单关键词中
            return RES_FEE_CHANNELS.some(key => u.includes(key));
        },
        getDivisor: (n, vol) => {
            let u = n.toUpperCase();
            if(u.includes('UNIUNI')) return 0; 
            if(u.includes('USPS')) return vol > 1728 ? 166 : 0;
            if(u.includes('ECO-MT')) return vol < 1728 ? 400 : 250;
            return 222; 
        }
    };

    function getEcoZoneIdx(z) {
        if(z==='2') return 0;
        if(z==='3'||z==='4') return 1;
        if(z==='5'||z==='6') return 2;
        return 3; 
    }

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
        const row = (name, cond, text) => {
            let cls = cond ? 'bg-err' : 'bg-ok';
            let txt = cond ? text : '正常 (OK)';
            return `<tr><td>${name}</td><td class="text-end"><span class="indicator ${cls}"></span>${txt}</td></tr>`;
        };
        h += row('UniUni', (L>20 || (L+d[1]+d[2])>50 || pkg.Wt>20), '限制(L>20/Wt>20)');
        h += row('USPS', (pkg.Wt>70 || L>30 || (L+(d[1]+d[2])*2)>130), '限制(>70lb/130")');
        h += row('FedEx', (pkg.Wt>150 || L>108 || G>165), '不可发(>150lb)');
        h += row('GOFO', (pkg.Wt>150), '超限(>150lb)');
        document.getElementById('checkTable').innerHTML = h;
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

    document.getElementById('btnLookup').onclick = () => {
        let z = document.getElementById('zipCode').value.trim();
        let d = document.getElementById('locInfo');
        if(!DATA.zip_db || !DATA.zip_db[z]) { d.innerHTML="<span class='text-danger'>❌ 未找到邮编</span>"; CUR_ZONES={}; return; }
        let i = DATA.zip_db[z];
        // 按照要求显示：标准地图信息 (州-城市 中英文)
        d.innerHTML = `<span class='text-success'>✅ ${i.sn}(${i.s}) - ${i.c} [${i.r}]</span>`;
        CUR_ZONES = i.z;
    };

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
        
        // 燃油费率分离
        let fedexFuel = parseFloat(document.getElementById('fedexFuel').value)/100;
        let uspsFuel = parseFloat(document.getElementById('uspsFuel').value)/100;
        let gofoFuel = parseFloat(document.getElementById('gofoFuel').value)/100;

        document.getElementById('tierBadge').innerText = tier;
        let dims = [pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
        let L=dims[0], G=L+2*(dims[1]+dims[2]);
        
        document.getElementById('pkgSummary').innerHTML = `<b>基准:</b> ${L.toFixed(1)}"${dims[1].toFixed(1)}"${dims[2].toFixed(1)}" | 实重:${pkg.Wt.toFixed(2)}lb | 围长:${G.toFixed(1)}"`;
        let tbody = document.getElementById('resBody'); tbody.innerHTML='';

        if(!DATA.tiers || !DATA.tiers[tier]) { tbody.innerHTML='<tr><td colspan="7" class="text-danger">❌ 等级数据缺失</td></tr>'; return; }

        Object.keys(DATA.tiers[tier]).forEach(ch => {
            let prices = DATA.tiers[tier][ch].prices;
            if(!prices || prices.length===0) return;

            let zoneVal = CUR_ZONES[ch] || '-';
            let uCh = ch.toUpperCase();
            let base=0, st="正常", cls="text-success", bg="";
            let cWt = pkg.Wt;
            let details = [];

            // 1. 计费重
            let div = RULES.getDivisor(ch, pkg.L*pkg.W*pkg.H);
            if(div > 0) {
                let vWt = (pkg.L*pkg.W*pkg.H)/div;
                cWt = Math.max(pkg.Wt, vWt);
            }
            if(!uCh.includes('GOFO-报价') && cWt>1) cWt = Math.ceil(cWt);

            // 2. 匹配价格 (查找重量和分区)
            let zKey = zoneVal==='1'?'2':zoneVal;
            let row = null;
            for(let r of prices) { if(r.w >= cWt-0.001) { row=r; break; } }

            if(!row || zoneVal==='-') { st="无分区/超重"; cls="text-muted"; bg="table-light"; }
            else {
                base = row[zKey];
                if(base===undefined && zKey==='1') base=row['2'];
                if(!base) { st="无报价"; cls="text-warning"; bg="table-warning"; base=0; }
            }

            // 3. 费用叠加
            let fees = {f:0, r:0, p:0, o:0};
            
            if(base > 0) {
                // 住宅费 (严格按照指定的渠道列表)
                if(isRes && RULES.hasResFee(ch)) { 
                    fees.r = DATA.surcharges.res_fee; 
                    details.push(`住宅:$${fees.r}`); 
                }

                // 旺季附加费
                if(isPeak) {
                    let p = 0;
                    // 【逻辑修改】USPS-YSD: 严格读取表格内的旺季费
                    if(uCh.includes('USPS-YSD')) {
                        if(row.peak !== undefined && row.peak !== null) {
                            p = row.peak;
                            details.push(`旺季(表):$${p}`);
                        } else {
                            // 如果表格没读到，兜底
                            p = 0.35; 
                            details.push(`旺季(默认):$${p}`);
                        }
                    } else {
                        // 其他渠道逻辑不变
                        if(isRes && RULES.hasResFee(ch)) p += DATA.surcharges.peak_res;
                        if(st.includes('Oversize')) p += DATA.surcharges.peak_oversize;
                        if(p>0) details.push(`旺季:$${p.toFixed(2)}`);
                    }
                    fees.p = p;
                }

                // FedEx ECO-MT Max-of-Three
                if(uCh.includes('ECO-MT')) {
                    let idx = getEcoZoneIdx(zoneVal);
                    let f_ahs = (L>48 || dims[1]>30 || (L+G-L)>105) ? ECO_FEES.ahs[idx] : 0;
                    let f_ow = (pkg.Wt>50) ? ECO_FEES.overweight[idx] : 0;
                    let f_os = (G>108 && G<130) ? ECO_FEES.oversize[idx] : 0;
                    let maxFee = Math.max(f_ahs, f_ow, f_os);
                    if(maxFee > 0) {
                        fees.o += maxFee;
                        st = maxFee===f_os?"超大":(maxFee===f_ow?"超重":"AHS"); 
                        cls = "text-warning fw-bold";
                        details.push(`${st}:$${maxFee}`);
                    }
                } 
                else if(st !== "超规不可发" && st !== "无折扣 (Std Rate)") {
                    let isUn = (L>108 || G>165 || pkg.Wt>150);
                    let isOver = (L>96 || G>130);
                    if(isUn) { 
                        fees.o += DATA.surcharges.unauthorized_fee; 
                        st="Unauthorized"; cls="text-danger fw-bold"; bg="table-danger"; 
                    } else if(isOver) { 
                        fees.o += DATA.surcharges.oversize_fee; 
                        st="Oversize"; cls="text-warning fw-bold"; 
                        details.push(`超大:$${DATA.surcharges.oversize_fee}`);
                    }
                }

                // 燃油费 (三者完全独立)
                let appliedFuel = 0;
                let fuelName = "";
                
                if(uCh.includes('GOFO大件')) {
                    appliedFuel = gofoFuel;
                    fuelName = "GOFO燃油";
                    // GOFO公式: (基础+附加) * 燃油
                    let subTotal = base + fees.r + fees.p + fees.o;
                    fees.f = subTotal * appliedFuel;
                } else if(uCh.includes('USPS')) {
                    appliedFuel = uspsFuel; // 使用独立的USPS燃油
                    fuelName = "USPS燃油";
                    fees.f = base * appliedFuel;
                } else if(uCh.includes('FEDEX') || uCh.includes('ECO') || uCh.includes('XLMILES')) {
                    appliedFuel = fedexFuel; // 使用FedEx燃油
                    fuelName = "FedEx燃油";
                    fees.f = base * appliedFuel;
                }
                
                if(fees.f > 0) {
                    details.push(`${fuelName}(${(appliedFuel*100).toFixed(1)}%):$${fees.f.toFixed(2)}`);
                }
            }

            let tot = base + fees.f + fees.r + fees.p + fees.o;

            tbody.innerHTML += `<tr class="${bg}">
                <td class="fw-bold text-start text-nowrap">${ch}</td>
                <td><span class="badge-zone">Zone ${zoneVal}</span></td>
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
# 3. 核心数据清洗 (支持旺季表读取)
# ==========================================

def safe_float(val):
    try:
        if pd.isna(val) or val == "" or str(val).strip().lower() == "nan": return 0.0
        return float(str(val).replace('$','').replace(',','').strip())
    except: return 0.0

def get_sheet_by_name(excel_file, target_keys):
    try:
        xl = pd.ExcelFile(excel_file, engine='openpyxl')
        for sheet in xl.sheet_names:
            s_name = sheet.upper().replace(" ", "")
            if all(k.upper() in s_name for k in target_keys):
                return pd.read_excel(xl, sheet_name=sheet, header=None)
        return None
    except: return None

def load_zip_db():
    print("--- 1. 加载邮编库 (含标准地图信息) ---")
    path = os.path.join(DATA_DIR, TIER_FILES['T0'])
    if not os.path.exists(path): return {}
    
    df = get_sheet_by_name(path, ["GOFO", "报价"])
    if df is None: return {}

    db = {}
    try:
        start = 0
        for i in range(100):
            cell = str(df.iloc[i,1]).strip()
            if cell.isdigit() and len(cell) == 5: start = i; break
        df = df.fillna("")
        for idx, row in df.iloc[start:].iterrows():
            z = str(row[1]).strip().zfill(5)
            if z.isdigit() and len(z)==5:
                zones = {}
                for k, v in ZIP_COL_MAP.items():
                    val = str(row[v]).strip()
                    if val in ['-', 'nan', '', '0', 0]: zones[k] = None
                    else: zones[k] = val
                
                # 读取州简写 (Col 3) 和 城市 (Col 4)
                sb = str(row[3]).strip().upper()
                city = str(row[4]).strip()
                state_cn = US_STATES_CN.get(sb, sb) # 获取中文州名
                
                db[z] = { 
                    "s": sb, 
                    "sn": state_cn, 
                    "c": city, 
                    "r": str(row[2]).strip(), 
                    "z": zones 
                }
    except: pass
    print(f"✅ 邮编库: {len(db)} 条")
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
    print("\n--- 2. 加载报价表 (含旺季列读取) ---")
    all_tiers = {}
    for t_name, f_name in TIER_FILES.items():
        path = os.path.join(DATA_DIR, f_name)
        if not os.path.exists(path): continue
        t_data = {}
        for ch_key, keywords in CHANNEL_KEYWORDS.items():
            df = get_sheet_by_name(path, keywords)
            if df is None: continue
            try:
                h_row = -1
                for i in range(50):
                    row_str = " ".join(df.iloc[i].astype(str).values).lower()
                    has_zone = ("zone" in row_str or "分区" in row_str)
                    has_weight = ("weight" in row_str or "lb" in row_str or "重量" in row_str)
                    if has_zone and has_weight: h_row = i; break
                
                if h_row == -1: continue

                headers = df.iloc[h_row].astype(str).str.lower().tolist()
                w_idx = -1; peak_idx = -1; z_map = {}
                
                for i, v in enumerate(headers):
                    if (('weight' in v) or ('lb' in v) or ('重量' in v)) and w_idx==-1: w_idx = i
                    # 识别旺季列 (Peak / 旺季)
                    if (('peak' in v) or ('旺季' in v)) and peak_idx==-1: peak_idx = i
                    m = re.search(r'(?:zone|分区)[\s\-\~]*(\d+)', v)
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
                        
                        # 如果有旺季列，读取它
                        if peak_idx != -1:
                            p_val = safe_float(row[peak_idx])
                            if p_val > 0: item['peak'] = p_val

                        for z, col in z_map.items():
                            clean_p = safe_float(row[col])
                            if clean_p > 0: item[z] = clean_p
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
    print("\n--- 3. 生成网页 ---")
    try: js_str = json.dumps(final, allow_nan=False)
    except: js_str = json.dumps(final).replace("NaN", "0")
    
    html = HTML_TEMPLATE.replace('__JSON_DATA__', js_str)
    
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f: f.write(html)
    print("✅ V11完成！已更新USPS燃油/旺季表/标准地图逻辑！")
