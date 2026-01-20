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

# 渠道 Sheet 匹配关键词 (精准匹配)
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

# 邮编库配置（GOFO 报价下方独立邮编区域：保持不动，仍从 T0 的 GOFO-报价抽取）
ZIP_DB_SHEET_KEY = "GOFO-报价"
ZIP_COL_MAP = {
    "GOFO-报价": 5, "GOFO-MT-报价": 6, "UNIUNI-MT-报价": 7, "USPS-YSD-报价": 8,
    "FedEx-ECO-MT报价": 9, "XLmiles-报价": 10, "GOFO大件-GRO-报价": 11,
    "FedEx-632-MT-报价": 12, "FedEx-YSD-报价": 13
}

# 默认附加费
GLOBAL_SURCHARGES = {
    "fuel": 0.16,
    "res_fee": 3.50,
    "peak_res": 1.32,
    "peak_oversize": 54,
    "peak_unauthorized": 220,
    "oversize_fee": 130,
    "ahs_fee": 20,
    "unauthorized_fee": 1150
}

# 州名（用于中英文显示）
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
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>业务员报价助手 (Ultimate V9 - 中文兼容版)</title>
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
        .hint { font-size: 0.75rem; color: #6c757d; margin-top: 4px; line-height: 1.2; }
    </style>
</head>
<body>

<div id="globalError" class="alert alert-danger shadow-lg">
    <h5 class="alert-heading">⚠️ 系统运行错误</h5>
    <p id="errorMsg">未知错误</p>
</div>

<header>
    <div class="container d-flex justify-content-between align-items-center">
        <div><h5 class="m-0 fw-bold">📦 业务员报价助手</h5><small class="opacity-75">T0-T3 专家版 (V9.0 中文兼容)</small></div>
        <div class="text-end text-white small">Multi-Channel Compliance Check</div>
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
                            <div class="fw-bold small mb-2 border-bottom">⛽ 燃油费率 (Fuel Surcharge)</div>
                            <div class="row g-2">
                                <div class="col-6 border-end">
                                    <label class="form-label small">统一燃油(%)</label>
                                    <input type="number" class="form-control form-control-sm" id="unifiedFuel" value="16.0">
                                    <div class="hint">仅用于：GOFO大件 / FedEx-YSD / FedEx-632</div>
                                </div>
                                <div class="col-6">
                                    <label class="form-label small">USPS燃油(%)</label>
                                    <input type="number" class="form-control form-control-sm" id="uspsFuel" value="0.0">
                                    <div class="hint">仅用于 USPS-YSD；与 FedEx 分开</div>
                                </div>
                            </div>
                        </div>

                        <div class="mb-3">
                            <label class="form-label">客户等级 (切换自动计算)</label>
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
                            <div class="hint">州/城市显示：优先使用美国标准邮编库（在线查询），失败则回退表内数据。</div>
                        </div>

                        <div class="row g-2 mb-3">
                            <div class="col-7">
                                <label class="form-label">地址类型</label>
                                <select class="form-select" id="addressType">
                                    <option value="res">🏠 住宅 (Residential)</option>
                                    <option value="com">🏢 商业 (Commercial)</option>
                                </select>
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
                        1. <strong>GOFO大件</strong>：(基础+附加费) * (1+燃油率)。燃油=统一燃油。<br>
                        2. <strong>FedEx ECO-MT</strong>：超长/超重/超大 三费取最大值 (Max-of-3)。<br>
                        3. <strong>USPS</strong>：旺季附加费按表格查价；燃油可独立设置（默认0）。<br>
                        4. <strong>UniUni</strong>：实重计费，无燃油/住宅费。<br>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<footer><div class="container"><p>&copy; 2026 速狗海外仓 | Update: <span id="updateDate"></span></p></div></footer>

<script>
    window.onerror = function(msg, u, l) {
        document.getElementById('globalError').style.display='block';
        document.getElementById('errorMsg').innerText=`${msg} (Line ${l})`;
    };
</script>

<script>
    let DATA = {};
    try { DATA = __JSON_DATA__; } catch(e) { throw new Error("Data Init Failed"); }
    let CUR_ZONES = {};
    document.getElementById('updateDate').innerText = new Date().toLocaleDateString();

    // ===================================
    // 自动计算监听
    // ===================================
    document.querySelectorAll('input[name="tier"]').forEach(r => {
        r.addEventListener('change', () => {
            document.getElementById('btnCalc').click();
        });
    });

    // ===================================
    // 核心业务配置
    // ===================================

    const USPS_BLOCK = ['006','007','008','009','090','091','092','093','094','095','096','097','098','099','340','962','963','964','965','966','967','968','969','995','996','997','998','999'];

    // FedEx ECO-MT 附加费表 (Zone 2, 3-4, 5-6, 7+)
    const ECO_FEES = {
        ahs: [6.55, 7.28, 8.03, 8.92],
        overweight: [10.26, 11.14, 11.89, 12.92],
        oversize: [71.28, 77.97, 84.64, 91.33],
        nonstd: [5.80, 6.84, 7.14, 7.43]
    };

    // 仅这 4 个渠道受住宅/商业影响（你点名要求）
    function isResComChannel(name) {
        let u = (name || '').toUpperCase();
        return u.includes('FEDEX-ECO-MT') || u.includes('FEDEX-YSD') || u.includes('FEDEX-632') || u.includes('GOFO大件'.toUpperCase());
    }

    // 仅这 3 个渠道使用统一燃油（你点名要求）
    function isUnifiedFuelChannel(name) {
        let u = (name || '').toUpperCase();
        return u.includes('GOFO大件'.toUpperCase()) || u.includes('FEDEX-YSD') || u.includes('FEDEX-632');
    }

    const RULES = {
        // 住宅费判断：仅作用于你点名的 4 个渠道
        hasResFee: n => {
            return isResComChannel(n);
        },
        // 计费重除数
        getDivisor: (n, vol) => {
            let u = (n || '').toUpperCase();
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

    // 全渠道实时检测模块
    function check(pkg) {
        let d=[pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
        let L=d[0], G=L+2*(d[1]+d[2]);
        let h = '';

        const row = (name, cond, text) => {
            let cls = cond ? 'bg-err' : 'bg-ok';
            let txt = cond ? text : '正常 (OK)';
            return `<tr><td>${name}</td><td class="text-end"><span class="indicator ${cls}"></span>${txt}</td></tr>`;
        };

        // UniUni: 长>20, 围>50, 重>20
        let uFail = (L>20 || (L+d[1]+d[2])>50 || pkg.Wt>20);
        h += row('UniUni', uFail, '限制(L>20/Wt>20)');

        // USPS: 重>70, 围长>130, 长>30
        let usFail = (pkg.Wt>70 || L>30 || (L+(d[1]+d[2])*2)>130);
        h += row('USPS', usFail, '限制(>70lb/130")');

        // FedEx: 重>150, 长>108, 围>165
        let fFail = (pkg.Wt>150 || L>108 || G>165);
        h += row('FedEx', fFail, '不可发(>150lb)');

        // GOFO大件: 重>150
        let gFail = (pkg.Wt>150);
        h += row('GOFO', gFail, '超限(>150lb)');

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

    // USPS 旺季附加费查表
    function getUspsPeakFee(zoneVal, chargeWtLb) {
        if(!DATA.usps_peak || !Array.isArray(DATA.usps_peak) || DATA.usps_peak.length===0) return 0;
        let zKey = (zoneVal==='1') ? '2' : zoneVal; // 与基础报价保持同一处理
        for(let r of DATA.usps_peak) {
            if(typeof r.w !== 'number') continue;
            if(chargeWtLb <= r.w + 1e-9) {
                let fee = r[zKey];
                if(typeof fee === 'number' && fee > 0) return fee;
                return 0;
            }
        }
        return 0;
    }

    // 标准邮编库查询：用于州/城市展示（不影响 GOFO 独立邮编区和分区）
    async function lookupStdZip(zip) {
        try {
            const resp = await fetch(`https://api.zippopotam.us/us/${zip}`, { cache: "no-store" });
            if(!resp.ok) return null;
            const j = await resp.json();
            if(!j || !j.places || !j.places[0]) return null;
            const p = j.places[0];
            const stateAbbr = (p["state abbreviation"] || "").toUpperCase();
            const city = (p["place name"] || "").trim();
            return {
                s: stateAbbr,
                sn: (DATA && DATA.state_cn && DATA.state_cn[stateAbbr]) ? DATA.state_cn[stateAbbr] : (window.US_STATES_CN ? window.US_STATES_CN[stateAbbr] : ""),
                c: city
            };
        } catch(e) {
            return null;
        }
    }

    // 由于模板里没有 window.US_STATES_CN，这里在运行时注入一份（来自后端 DATA.state_cn）
    // DATA.state_cn 是 Python 输出的州中文映射（保证一致）
    window.US_STATES_CN = DATA.state_cn || {};

    document.getElementById('btnLookup').onclick = async () => {
        let z = document.getElementById('zipCode').value.trim();
        let d = document.getElementById('locInfo');

        if(!DATA.zip_db || !DATA.zip_db[z]) {
            d.innerHTML="<span class='text-danger'>❌ 未找到邮编（分区库缺失）</span>";
            CUR_ZONES={};
            return;
        }

        let i = DATA.zip_db[z];
        CUR_ZONES = i.z || {};

        d.innerHTML = `<span class='text-muted'>⏳ 查询中...</span>`;

        // 优先标准邮编库显示州/城市；失败回退表内数据
        let std = await lookupStdZip(z);
        if(std && std.s && std.c) {
            let sn = window.US_STATES_CN[std.s] || '';
            d.innerHTML = `<span class='text-success'>✅ ${sn} ${std.s} - ${std.c} [${i.r}]</span>`;
        } else {
            d.innerHTML = `<span class='text-success'>✅ ${i.sn} ${i.s} - ${i.c} [${i.r}]</span>`;
        }
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

        // 燃油费率获取
        let unifiedFuel = parseFloat(document.getElementById('unifiedFuel').value)/100;
        let uspsFuel = parseFloat(document.getElementById('uspsFuel').value)/100;

        document.getElementById('tierBadge').innerText = tier;

        let dims = [pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
        let L=dims[0], G=L+2*(dims[1]+dims[2]);

        document.getElementById('pkgSummary').innerHTML =
            `<b>基准:</b> ${L.toFixed(1)}"${dims[1].toFixed(1)}"${dims[2].toFixed(1)}" | 实重:${pkg.Wt.toFixed(2)}lb | 围长:${G.toFixed(1)}"`;

        let tbody = document.getElementById('resBody'); tbody.innerHTML='';

        if(!DATA.tiers || !DATA.tiers[tier]) {
            tbody.innerHTML='<tr><td colspan="7" class="text-danger">❌ 等级数据缺失</td></tr>';
            return;
        }

        Object.keys(DATA.tiers[tier]).forEach(ch => {
            let prices = DATA.tiers[tier][ch].prices;
            if(!prices || prices.length===0) return;

            let zoneVal = (CUR_ZONES && CUR_ZONES[ch]) ? CUR_ZONES[ch] : '-';
            let uCh = (ch || '').toUpperCase();

            let base=0, st="正常", cls="text-success", bg="";
            let cWt = pkg.Wt;
            let details = [];

            // 1) 计费重
            let div = RULES.getDivisor(ch, pkg.L*pkg.W*pkg.H);
            if(div > 0) {
                let vWt = (pkg.L*pkg.W*pkg.H)/div;
                cWt = Math.max(pkg.Wt, vWt);
            }
            if(!uCh.includes('GOFO-报价'.toUpperCase()) && cWt>1) cWt = Math.ceil(cWt);

            // 2) 匹配基础价格
            let zKey = (zoneVal==='1') ? '2' : zoneVal;
            let row = null;
            for(let r of prices) {
                if(r.w >= cWt-0.001) { row=r; break; }
            }

            if(!row || zoneVal==='-') {
                st="无分区/超重"; cls="text-muted"; bg="table-light";
            } else {
                base = row[zKey];
                if(base===undefined && zKey==='1') base=row['2'];
                if(!base) { st="无报价"; cls="text-warning"; bg="table-warning"; base=0; }
            }

            // 3) 特殊拦截
            if(uCh.includes('USPS')) {
                if(USPS_BLOCK.some(p => zip.startsWith(p))) {
                    st="无折扣 (Std Rate)"; cls="text-danger"; bg="table-danger"; base=0;
                }
                if(pkg.Wt>70 || L>30 || (L+(dims[1]+dims[2])*2)>130) {
                    st="超规不可发"; cls="text-danger fw-bold"; bg="table-danger"; base=0;
                }
            }
            if(uCh.includes('UNIUNI')) {
                if(L>20 || (L+dims[1]+dims[2])>50 || pkg.Wt>20) {
                    st="超规不可发"; cls="text-danger fw-bold"; bg="table-danger"; base=0;
                }
            }

            // 4) 费用叠加
            let fees = {f:0, r:0, p:0, o:0};

            if(base > 0) {
                // 4.1 住宅费：仅对你点名的 4 个渠道生效
                if(isRes && RULES.hasResFee(ch)) {
                    fees.r = DATA.surcharges.res_fee;
                    details.push(`住宅:$${fees.r}`);
                }

                // 4.2 FedEx ECO-MT Max-of-Three
                if(uCh.includes('ECO-MT')) {
                    let idx = getEcoZoneIdx(zoneVal);
                    let f_ahs = (L>48 || dims[1]>30 || (L+G-L)>105) ? ECO_FEES.ahs[idx] : 0;
                    let f_ow = (pkg.Wt>50) ? ECO_FEES.overweight[idx] : 0;
                    let f_os = (G>108 && G<130) ? ECO_FEES.oversize[idx] : 0;

                    let maxFee = Math.max(f_ahs, f_ow, f_os);
                    if(maxFee > 0) {
                        fees.o += maxFee;
                        let reason = maxFee===f_os?"超大": (maxFee===f_ow?"超重":"AHS");
                        details.push(`${reason}:$${maxFee}`);
                        st = reason; cls = "text-warning fw-bold";
                    }
                    if(pkg.Wt>70 || G>130) {
                        st="不可发(Unauth)"; cls="text-danger fw-bold"; bg="table-danger";
                        fees.o += 2000;
                    }
                }
                // 4.3 常规渠道
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

                // 4.4 旺季
                if(isPeak) {
                    let p=0;

                    // USPS：按旺季附加费表格查价
                    if(uCh.includes('USPS')) {
                        p = getUspsPeakFee(zoneVal, cWt);
                        if(p > 0) details.push(`旺季:$${p.toFixed(2)}`);
                    } else {
                        // 其他渠道保持原逻辑（不动）
                        if(isRes && RULES.hasResFee(ch)) p += DATA.surcharges.peak_res;
                        if(st.includes('Oversize')) p += DATA.surcharges.peak_oversize;
                        if(p>0) details.push(`旺季:$${p.toFixed(2)}`);
                    }

                    fees.p = p;
                }

                // 4.5 燃油
                // 规则：
                // - USPS：用 uspsFuel（与 FedEx 分开）
                // - 仅 GOFO大件/FedEx-YSD/FedEx-632 用 unifiedFuel
                // - 其他渠道视为“已含燃油”，不再叠加
                if(uCh.includes('USPS')) {
                    if(uspsFuel > 0) {
                        fees.f = base * uspsFuel;
                        details.push(`燃油(USPS ${uspsFuel*100}%):$${fees.f.toFixed(2)}`);
                    }
                } else if(isUnifiedFuelChannel(ch)) {
                    if(uCh.includes('GOFO大件'.toUpperCase())) {
                        // GOFO大件： (运费+附加费) * (1+燃油) 里的燃油部分
                        let subTotal = base + fees.r + fees.p + fees.o;
                        fees.f = subTotal * unifiedFuel;
                        details.push(`燃油(统一 ${unifiedFuel*100}%):$${fees.f.toFixed(2)}`);
                    } else {
                        // FedEx-YSD / FedEx-632：运费 * 统一燃油
                        fees.f = base * unifiedFuel;
                        details.push(`燃油(统一 ${unifiedFuel*100}%):$${fees.f.toFixed(2)}`);
                    }
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
# 3. 核心数据清洗
# ==========================================

def safe_float(val):
    try:
        if pd.isna(val) or val == "" or str(val).strip().lower() == "nan":
            return 0.0
        return float(str(val).replace('$', '').replace(',', '').strip())
    except:
        return 0.0

def get_sheet_by_name(excel_file, target_keys):
    try:
        xl = pd.ExcelFile(excel_file, engine='openpyxl')
        for sheet in xl.sheet_names:
            s_name = sheet.upper().replace(" ", "")
            if all(k.upper() in s_name for k in target_keys):
                print(f"    > 匹配Sheet: {sheet}")
                return pd.read_excel(xl, sheet_name=sheet, header=None)
        return None
    except Exception as e:
        print(f"    > 读取失败: {e}")
        return None

def normalize_zone(val):
    """
    修复：邮编库中的分区值若是数字格式，pandas 可能读成 float（如 1.0）。
    前端查价用 key '1','2'...，若这里变成 '1.0' 则匹配不到。
    """
    try:
        if pd.isna(val):
            return None
    except:
        pass

    s = str(val).strip()
    if s == "" or s.lower() == "nan" or s == "-" or s == "0":
        return None

    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        return s
    except:
        m = re.fullmatch(r"(\d+)\.0+", s)
        if m:
            return m.group(1)
        return s

def load_zip_db():
    print("--- 1. 加载邮编库（GOFO 报价下方独立邮编区，保持不动） ---")
    path = os.path.join(DATA_DIR, TIER_FILES['T0'])
    if not os.path.exists(path):
        return {}

    df = get_sheet_by_name(path, ["GOFO", "报价"])
    if df is None:
        return {}

    db = {}
    try:
        start = 0
        for i in range(100):
            cell = str(df.iloc[i, 1]).strip()
            if cell.isdigit() and len(cell) == 5:
                start = i
                break

        df = df.fillna("")
        for _, row in df.iloc[start:].iterrows():
            z = str(row[1]).strip().zfill(5)
            if z.isdigit() and len(z) == 5:
                zones = {}
                for k, v in ZIP_COL_MAP.items():
                    zones[k] = normalize_zone(row[v])

                sb = str(row[3]).strip().upper()
                db[z] = {
                    "s": sb,
                    "sn": US_STATES_CN.get(sb, ''),
                    "c": str(row[4]).strip(),
                    "r": str(row[2]).strip(),
                    "z": zones
                }
    except:
        pass

    print(f"✅ 邮编库: {len(db)} 条")
    return db

def to_lb(val):
    s = str(val).upper().strip()
    if pd.isna(val) or s == 'NAN' or s == '':
        return None
    nums = re.findall(r"[\d\.]+", s)
    if not nums:
        return None
    n = float(nums[0])
    if 'OZ' in s:
        return n / 16.0
    if 'KG' in s:
        return n / 0.453592
    return n

def load_tiers():
    print("\n--- 2. 加载报价表（中文兼容） ---")
    all_tiers = {}
    for t_name, f_name in TIER_FILES.items():
        print(f"处理 {t_name}...")
        path = os.path.join(DATA_DIR, f_name)
        if not os.path.exists(path):
            continue

        t_data = {}
        for ch_key, keywords in CHANNEL_KEYWORDS.items():
            df = get_sheet_by_name(path, keywords)
            if df is None:
                continue

            try:
                h_row = 0
                for i in range(50):
                    row_str = " ".join(df.iloc[i].astype(str).values).lower()
                    has_zone = ("zone" in row_str or "分区" in row_str)
                    has_weight = ("weight" in row_str or "lb" in row_str or "重量" in row_str)
                    if has_zone and has_weight:
                        h_row = i
                        break

                headers = df.iloc[h_row].astype(str).str.lower().tolist()
                w_idx = -1
                z_map = {}

                for i, v in enumerate(headers):
                    if ('weight' in v or 'lb' in v or '重量' in v) and w_idx == -1:
                        w_idx = i
                    m = re.search(r'(?:zone|分区)\s*~?\s*(\d+)', v)
                    if m:
                        zn = m.group(1)
                        if zn not in z_map:
                            z_map[zn] = i

                if w_idx == -1:
                    continue

                prices = []
                for i in range(h_row + 1, len(df)):
                    row = df.iloc[i]
                    try:
                        lb = to_lb(row[w_idx])
                        if lb is None:
                            continue
                        item = {'w': lb}
                        for z, col in z_map.items():
                            clean_p = safe_float(row[col])
                            if clean_p > 0:
                                item[z] = clean_p
                        if len(item) > 1:
                            prices.append(item)
                    except:
                        continue

                prices.sort(key=lambda x: x['w'])
                t_data[ch_key] = {"prices": prices}
            except:
                pass

        all_tiers[t_name] = t_data

    return all_tiers

def _find_row_contains(df, patterns, max_rows=200):
    pats = [p.lower() for p in patterns]
    for i in range(min(max_rows, len(df))):
        row_str = " ".join(df.iloc[i].astype(str).values).lower()
        if all(p in row_str for p in pats):
            return i
    return -1

def load_usps_peak_table():
    """
    USPS-YSD-报价：旺季附加费必须严格按表格报价独立结合计算
    读取 T0 的 USPS sheet 中 “旺季附加费”矩阵，输出为：
    [
      {"w": 1.0, "1":0.12, "2":0.12, ...},
      {"w": 2.0, "1":0.12, "2":0.13, ...},
      ...
    ]
    """
    print("\n--- 2.1 解析 USPS 旺季附加费表 ---")
    path = os.path.join(DATA_DIR, TIER_FILES['T0'])
    if not os.path.exists(path):
        return []

    df = get_sheet_by_name(path, ["USPS"])
    if df is None:
        print("⚠️ 未找到 USPS sheet")
        return []

    df = df.fillna("")

    # 先定位“旺季附加费”块（兼容中英文）
    anchor = _find_row_contains(df, ["旺季", "附加费"], max_rows=400)
    if anchor < 0:
        anchor = _find_row_contains(df, ["peak", "surcharge"], max_rows=400)
    if anchor < 0:
        print("⚠️ 未定位到 USPS 旺季附加费块（将导致 USPS 旺季不生效）")
        return []

    # 从 anchor 往下找 header：包含“重量/不超过/weight” + “zone”
    header_row = -1
    for i in range(anchor, min(anchor + 40, len(df))):
        row_str = " ".join(df.iloc[i].astype(str).values).lower()
        has_w = ("weight" in row_str or "重量" in row_str or "不超过" in row_str)
        has_z = ("zone" in row_str or "分区" in row_str)
        if has_w and has_z:
            header_row = i
            break

    if header_row < 0:
        print("⚠️ USPS 旺季表：未找到表头行")
        return []

    headers = df.iloc[header_row].astype(str).str.lower().tolist()

    # weight 列
    w_idx = -1
    z_map = {}
    for i, v in enumerate(headers):
        if w_idx == -1 and (("weight" in v) or ("重量" in v) or ("不超过" in v)):
            w_idx = i
        m = re.search(r'(?:zone|分区)\s*~?\s*(\d+)', v)
        if m:
            zn = m.group(1)
            if zn not in z_map:
                z_map[zn] = i

    if w_idx == -1 or not z_map:
        print("⚠️ USPS 旺季表：weight/zone 列解析失败")
        return []

    table = []
    for i in range(header_row + 1, len(df)):
        row = df.iloc[i]
        # weight 上限（磅）可能是数字或文本
        w = to_lb(row[w_idx])
        if w is None:
            # 遇到空行/新块，结束
            row_str = " ".join(row.astype(str).values).strip()
            if row_str == "" or row_str.lower() == "nan":
                continue
            # 若出现明显非数据区，尝试终止
            if "旺季" in row_str or "附加费" in row_str:
                continue
            # 不是数字则跳过
            continue

        item = {"w": float(w)}
        any_fee = False
        for z, col in z_map.items():
            fee = safe_float(row[col])
            if fee > 0:
                item[z] = fee
                any_fee = True
        if any_fee:
            table.append(item)

    table.sort(key=lambda x: x["w"])
    print(f"✅ USPS 旺季表: {len(table)} 行")
    return table

if __name__ == '__main__':
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    final = {
        "zip_db": load_zip_db(),
        "tiers": load_tiers(),
        "surcharges": GLOBAL_SURCHARGES,
        "usps_peak": load_usps_peak_table(),
        "state_cn": US_STATES_CN
    }

    print("\n--- 3. 生成网页 ---")
    try:
        js_str = json.dumps(final, allow_nan=False)
    except:
        js_str = json.dumps(final).replace("NaN", "0")

    html = HTML_TEMPLATE.replace('__JSON_DATA__', js_str)

    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ 完成！")
