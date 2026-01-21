import pandas as pd
import json
import re
import os
import warnings
from datetime import datetime
from urllib.request import urlopen, Request

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

# 邮编库配置：GOFO 邮编区（保持不动）
ZIP_DB_SHEET_KEY = "GOFO-报价"
ZIP_COL_MAP = {
    "GOFO-报价": 5, "GOFO-MT-报价": 6, "UNIUNI-MT-报价": 7, "USPS-YSD-报价": 8,
    "FedEx-ECO-MT报价": 9, "XLmiles-报价": 10, "GOFO大件-GRO-报价": 11,
    "FedEx-632-MT-报价": 12, "FedEx-YSD-报价": 13
}

# 你的旧全局附加费仍保留（但住宅费/签名费/旺季 FedEx 改为按渠道逻辑覆盖）
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

# 州名（展示用）
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
# 1.5 FedEx 官网：住宅地址旺季附加费（Demand Surcharges）抓取
# - 说明：GitHub Pages 前端无法跨域实时抓 fedex.com（CORS），所以在构建时抓取并注入 JSON
# ==========================================
def fetch_fedex_residential_peak_table():
    """
    从 FedEx Demand Surcharges 页面解析：
    “FedEx Ground residential shipments and FedEx Home Delivery residential shipments”
    的三段固定每包金额（Oct.27–Jan.18 那段）。
    解析不到则 fallback。
    """
    url = "https://www.fedex.com/en-us/shipping/rate-changes/demand-surcharges.html"
    fallback = {
        "type": "fixed_by_date",
        "source": "fallback",
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "periods": [
            {"start": "2025-10-27", "end": "2025-11-23", "amount": 0.40},
            {"start": "2025-11-24", "end": "2025-12-28", "amount": 0.65},
            {"start": "2025-12-29", "end": "2026-01-18", "amount": 0.40}
        ]
    }
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")

        # 粗暴但稳定：定位该段标题附近的金额
        # 页面文本中有：FedEx Ground residential shipments... 然后依次出现 $0.40 $0.65 $0.40 和日期段
        if "FedEx Ground residential shipments" not in html:
            return fallback

        # 抓三段金额（按出现顺序）
        # 只取这一块附近的片段减少误匹配
        idx = html.find("FedEx Ground residential shipments")
        snippet = html[idx: idx + 5000]

        amts = re.findall(r"\$([0-9]+\.[0-9]{2})", snippet)
        # 该段前面还有别的 surcharge 金额，需进一步收敛：在该段之后最先出现的 3 个小额（<5）通常是 0.40/0.65/0.40
        small = []
        for a in amts:
            v = float(a)
            if v < 5:
                small.append(v)
            if len(small) >= 3:
                break
        if len(small) < 3:
            return fallback

        # 日期段：直接按 FedEx 页面写死这三段（页面上就是这三段）
        # 若未来 FedEx 改了日期，金额也会变；日期可后续再做更严格解析，这里先满足“自动更新金额”
        return {
            "type": "fixed_by_date",
            "source": url,
            "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "periods": [
                {"start": "2025-10-27", "end": "2025-11-23", "amount": float(small[0])},
                {"start": "2025-11-24", "end": "2025-12-28", "amount": float(small[1])},
                {"start": "2025-12-29", "end": "2026-01-18", "amount": float(small[2])}
            ]
        }
    except:
        return fallback

# ==========================================
# 2. 网页模板
# ==========================================
HTML_TEMPLATE = """
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
        .note-box{background:#fff; border:1px solid #e5e5e5; border-radius:8px; padding:10px;}
        .mono{font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;}
    </style>
</head>
<body>

<div id="globalError" class="alert alert-danger shadow-lg">
    <h5 class="alert-heading">⚠️ 系统运行错误</h5>
    <p id="errorMsg">未知错误</p>
</div>

<header>
    <div class="container d-flex justify-content-between align-items-center">
        <div><h5 class="m-0 fw-bold">📦 业务员报价助手</h5><small class="opacity-75">T0-T3 专家版 (V9.1)</small></div>
        <div class="text-end text-white small">Multi-Channel Quote</div>
    </div>
</header>

<div class="container my-4">
    <div class="row g-4">
        <div class="col-lg-4">
            <div class="card h-100">
                <div class="card-header">1. 基础信息录入</div>
                <div class="card-body">
                    <form id="calcForm">

                        <div class="mb-3">
                            <label class="form-label">发货仓库 (影响 FedEx Zone)</label>
                            <select class="form-select" id="warehouse">
                                <option value="WEST">美西 91730</option>
                                <option value="CENTRAL">美中 606</option>
                                <option value="EAST">美东 088</option>
                            </select>
                            <div class="small text-muted mt-1">仅显示该仓库可用渠道；FedEx 标准渠道 Zone 由仓库+邮编计算。</div>
                        </div>

                        <div class="bg-light p-2 rounded border mb-3">
                            <div class="fw-bold small mb-2 border-bottom">⛽ 燃油费率 (Fuel Surcharge)</div>
                            <div class="small text-danger fw-bold mb-2">仅：FedEx-YSD / FedEx-632-MT / GOFO大件</div>
                            <div class="row g-2">
                                <div class="col-6 border-end">
                                    <label class="form-label small">FedEx(YSD/632) (%)</label>
                                    <input type="number" class="form-control form-control-sm" id="fedexFuel" value="16.0">
                                    <a href="https://www.fedex.com/en-us/shipping/fuel-surcharge.html" target="_blank" class="fuel-link">🔗 FedEx燃油官网</a>
                                </div>
                                <div class="col-6">
                                    <label class="form-label small">GOFO大件 (%)</label>
                                    <input type="number" class="form-control form-control-sm" id="gofoFuel" value="15.0">
                                    <span class="text-muted small d-block mt-1">GOFO大件独立</span>
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
                            <div id="zoneInfo" class="mt-1 small text-muted ps-1"></div>
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

                        <div class="mb-3">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="sigToggle">
                                <label class="form-check-label fw-bold">签名签收 (Indirect/Direct Signature)</label>
                            </div>
                            <div class="small text-muted">仅：FedEx-YSD / FedEx-632-MT / XLmiles</div>
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

                    <div class="note-box mb-3">
                        <div class="fw-bold">旺季附加费说明（必读）</div>
                        <div class="small mt-1" style="line-height:1.35">
                            ① <b>USPS Ground Advantage</b>：旺季附加费来自 <b>USPS-YSD-报价</b> 表内右侧副本（全名：<b>2025旺季附加费-USPS Ground Advantage</b>），按重量档 + Zone 查价叠加。<br>
                            ② <b>FedEx-ECO-MT</b>：FedEx 与 USPS 联合承运，末端 USPS 派送；本渠道报价表仅供参考，<b>不包含旺季附加费</b>，实际以系统账单为准。<br>
                            ③ 若派送后产生额外费用（复核尺寸不符/退货/其他附加费等），物流商向我司收取后我司将 <b>实报实销</b>。
                        </div>
                        <div class="small text-muted mt-2">
                            FedEx “住宅地址旺季附加费”参考官方 Demand Surcharges 页面构建时自动更新：<span class="mono" id="fedexPeakMeta"></span>
                        </div>
                    </div>

                    <div class="table-responsive">
                        <table class="table table-bordered table-hover result-table">
                            <thead>
                                <tr>
                                    <th width="15%">渠道</th>
                                    <th width="10%">仓库</th>
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
                        1. <strong>燃油费</strong>：仅 FedEx-YSD / FedEx-632-MT / GOFO大件 额外计算；其余渠道报价已含燃油。<br>
                        2. <strong>住宅费</strong>：仅 FedEx-YSD($3.80) / FedEx-632($2.88) / GOFO大件($3.17)。<br>
                        3. <strong>签名费</strong>：仅 FedEx-YSD($9.30) / FedEx-632($4.46) / XLmiles($11.05)，由开关控制是否叠加。<br>
                        4. <strong>FedEx 标准渠道 Zone</strong>：FedEx-YSD / FedEx-632 / FedEx-ECO-MT 使用“仓库+邮编”计算 Zone（不再依赖 GOFO 邮编区）。<br>
                        5. <strong>XLmiles</strong>：按 AH/OS/OM 三类服务规则计算，Zone 仅支持 1-2 / 3（>3 默认不可用）。<br>
                        <div class="mt-2">
                            <strong>XLmiles 注意事项：</strong><br>
                            LA,NJ,HOU 核心区域免费揽收；实时包裹追踪；POD 在我司系统一键获取；对标 Threshold 等级服务，投递至前门/后门/车库门。
                        </div>
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

    document.getElementById('updateDate').innerText = new Date().toLocaleDateString();

    // 显示 FedEx 旺季元信息
    (function(){
        let meta = DATA.fedex_res_peak || {};
        let s = (meta.source || 'n/a');
        let t = (meta.updated_at || 'n/a');
        document.getElementById('fedexPeakMeta').innerText = `source=${s} | updated=${t}`;
    })();

    // ===================================
    // 自动计算监听
    // ===================================
    document.querySelectorAll('input[name="tier"]').forEach(r => {
        r.addEventListener('change', () => document.getElementById('btnCalc').click());
    });
    document.getElementById('warehouse').addEventListener('change', () => document.getElementById('btnCalc').click());
    document.getElementById('addressType').addEventListener('change', () => document.getElementById('btnCalc').click());
    document.getElementById('peakToggle').addEventListener('change', () => document.getElementById('btnCalc').click());
    document.getElementById('sigToggle').addEventListener('change', () => document.getElementById('btnCalc').click());

    // ===================================
    // 渠道可用仓库（写死）
    // ===================================
    const WAREHOUSE_LABEL = {
        "WEST": "美西 91730",
        "CENTRAL": "美中 606",
        "EAST": "美东 088"
    };
    const CHANNEL_WAREHOUSE_ALLOW = {
        "GOFO-报价": ["WEST","CENTRAL"],
        "GOFO-MT-报价": ["WEST","CENTRAL"],
        "UNIUNI-MT-报价": ["WEST","CENTRAL"],
        "USPS-YSD-报价": ["WEST","CENTRAL"],
        "FedEx-YSD-报价": ["WEST","CENTRAL"],
        "XLmiles-报价": ["WEST"],
        "GOFO大件-GRO-报价": ["WEST","CENTRAL","EAST"],
        "FedEx-632-MT-报价": ["WEST","CENTRAL","EAST"],
        "FedEx-ECO-MT报价": ["WEST","CENTRAL","EAST"]
    };

    // ===================================
    // FedEx Zone 计算（从你 V2.4 思路移植）
    // ===================================
    function calculateZoneMath(destZip, wh) {
        if(!destZip || destZip.length < 3) return 8;
        let p = parseInt(destZip.substring(0,3), 10);

        // 偏远/海岛
        if ((p >= 967 && p <= 969) || (p >= 995 && p <= 999) || destZip.startsWith('00')) return 9;

        // wh -> originType
        let originType = (wh==="WEST") ? "917" : (wh==="CENTRAL" ? "606" : "088");

        if (originType === '917') {
            if (p >= 900 && p <= 935) return 2;
            if (p >= 936 && p <= 961) return 3;
            if (p >= 890 && p <= 898) return 3;
            if (p >= 970 && p <= 994) return 4;
            if (p >= 840 && p <= 884) return 4;
            if (p >= 500 && p <= 799) return 6;
            if (p >= 0 && p <= 499) return 8;
        } else if (originType === '606') {
            if (p >= 600 && p <= 629) return 2;
            if (p >= 460 && p <= 569) return 3;
            if (p >= 400 && p <= 459) return 4;
            if (p >= 700 && p <= 799) return 4;
            if (p >= 200 && p <= 399) return 5;
            if (p >= 800 && p <= 899) return 6;
            if (p >= 0 && p <= 199) return 7;
            if (p >= 900 && p <= 966) return 8;
        } else { // 088
            if (p >= 70 && p <= 89) return 2;
            if (p >= 0 && p <= 69) return 3;
            if (p >= 150 && p <= 199) return 3;
            if (p >= 200 && p <= 299) return 4;
            if (p >= 400 && p <= 599) return 5;
            if (p >= 600 && p <= 799) return 7;
            if (p >= 800 && p <= 966) return 8;
        }
        return 8;
    }

    function isFedexStandardChannel(ch){
        return (ch.includes("FedEx-YSD") || ch.includes("FedEx-632") || ch.includes("FedEx-ECO-MT"));
    }

    // ===================================
    // USPS 不可用前缀（保留你原逻辑）
    // ===================================
    const USPS_BLOCK = ['006','007','008','009','090','091','092','093','094','095','096','097','098','099','340','962','963','964','965','966','967','968','969','995','996','997','998','999'];

    // ===================================
    // XLmiles 规则（按你给的说明）
    // Zone：仅 1-2/3；>3 视为不可用
    // ===================================
    function xl_zone_group(z){
        if(z===1 || z===2) return "1-2";
        if(z===3) return "3";
        return null;
    }
    function xl_services_price(pkg, xlZone){
        // pkg: {L,W,H,Wt} in inches/lb
        // 计算围长 G = L + 2*(W+H)，L 为最长边
        let dims = [pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
        let L = dims[0];
        let G = L + 2*(dims[1]+dims[2]);

        // AH：L<=96 且 G<=130，Wt<=90 或 <=150
        // OS：L<=108 且 G<=165，Wt<=150
        // OM：L<=144 且 G<=225，Wt<=200
        // 价格（按你给的）：
        // AH <=90: Z1-2 33, Z3 36；AH <=150: Z1-2 52, Z3 56
        // OS <=150: Z1-2 65, Z3 69
        // OM <=200: Z1-2 104, Z3 117
        let zone = xlZone; // "1-2" or "3"
        let ah = null, os = null, om = null;

        if(L<=96 && G<=130){
            if(pkg.Wt<=90) ah = (zone==="1-2") ? 33 : 36;
            else if(pkg.Wt<=150) ah = (zone==="1-2") ? 52 : 56;
        }
        if(L<=108 && G<=165 && pkg.Wt<=150){
            os = (zone==="1-2") ? 65 : 69;
        }
        if(L<=144 && G<=225 && pkg.Wt<=200){
            om = (zone==="1-2") ? 104 : 117;
        }

        // 若都不满足 => 不可用
        if(ah===null && os===null && om===null){
            return {ok:false, reason:"超规不可发", details:[], base:0};
        }

        // 组合计费：若同时包含 AH/OS/OM 的产品，你给的是“分摊+叠加”示例。
        // 这里按“若同时满足多档，按较高档为主”会偏保守；但你明确给了分摊公式，所以按以下策略：
        // - AH 与 OS 同时可选：各 50%
        // - OM 若可选：全额叠加（按你示例 OM 全额 + AH*0.5 + OS*0.5）
        let base = 0;
        let details = [];
        if(ah!==null && os!==null){
            base += ah*0.5; details.push(`AH*0.5=$${(ah*0.5).toFixed(2)}`);
            base += os*0.5; details.push(`OS*0.5=$${(os*0.5).toFixed(2)}`);
        } else if(ah!==null){
            base += ah; details.push(`AH=$${ah.toFixed(2)}`);
        } else if(os!==null){
            base += os; details.push(`OS=$${os.toFixed(2)}`);
        }
        if(om!==null){
            base += om; details.push(`OM=$${om.toFixed(2)}`);
        }

        return {ok:true, reason:"正常", details, base};
    }

    // ===================================
    // 计费重、单位标准化
    // ===================================
    function standardize(l, w, h, du, wt, wu) {
        let L=parseFloat(l)||0, W=parseFloat(w)||0, H=parseFloat(h)||0, Weight=parseFloat(wt)||0;
        if(du==='cm'){L/=2.54;W/=2.54;H/=2.54} else if(du==='mm'){L/=25.4;W/=25.4;H/=25.4}
        if(wu==='kg')Weight/=0.453592; else if(wu==='oz')Weight/=16; else if(wu==='g')Weight/=453.592;
        return {L,W,H,Wt:Weight};
    }

    // ===================================
    // 合规性一览（新增 XLmiles）
    // ===================================
    function check(pkg) {
        let d=[pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
        let L=d[0], G=L+2*(d[1]+d[2]);
        let h = '';

        const row = (name, cond, text) => {
            let cls = cond ? 'bg-err' : 'bg-ok';
            let txt = cond ? text : '正常 (OK)';
            return `<tr><td>${name}</td><td class="text-end"><span class="indicator ${cls}"></span>${txt}</td></tr>`;
        };

        // UniUni: 长>20, 围>50(这里你原逻辑是 L+W+H>50), 重>20
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
        h += row('GOFO大件', gFail, '超限(>150lb)');

        // XLmiles: OM 上限：L<=144 且 G<=225 且 Wt<=200
        let xlFail = (pkg.Wt>200 || L>144 || G>225);
        h += row('XLmiles', xlFail, '范围(<=200lb/144"/225")');

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

    // ===================================
    // 邮编查询：优先 GOFO 邮编库；否则 zippopotam.us
    // ===================================
    let CUR_ZONES = {}; // 仅给 GOFO 邮编区那些渠道用
    let LAST_LOC = null;

    async function lookupZip(zip){
        let d = document.getElementById('locInfo');
        let zinfo = document.getElementById('zoneInfo');
        let wh = document.getElementById('warehouse').value;

        CUR_ZONES = {};
        LAST_LOC = null;

        if(DATA.zip_db && DATA.zip_db[zip]){
            let i = DATA.zip_db[zip];
            d.innerHTML = `<span class='text-success'>✅ ${i.sn} ${i.s} - ${i.c} [${i.r}]</span>`;
            CUR_ZONES = i.z || {};
            LAST_LOC = {state:i.s, city:i.c};
        }else{
            d.innerHTML = `<span class='text-warning'>⚠️ GOFO邮编库无该邮编，改用公共库查询州/城市</span>`;
            try{
                let resp = await fetch(`https://api.zippopotam.us/us/${zip}`);
                if(resp.ok){
                    let data = await resp.json();
                    let place = (data.places && data.places[0]) ? data.places[0] : null;
                    if(place){
                        let city = place['place name'];
                        let st = place['state abbreviation'];
                        LAST_LOC = {state:st, city:city};
                        d.innerHTML = `<span class='text-success'>✅ ${st} - ${city}</span>`;
                    }
                }
            }catch(e){}
        }

        // 同时展示 FedEx Zone 预估
        if(zip && zip.length>=3){
            let z = calculateZoneMath(zip, wh);
            zinfo.innerHTML = `FedEx Zone(按仓库计算): <b>Zone ${z}</b>`;
        }else{
            zinfo.innerHTML = '';
        }
    }

    document.getElementById('btnLookup').onclick = async () => {
        let zip = document.getElementById('zipCode').value.trim();
        if(zip.length!==5){ alert("请输入5位邮编"); return; }
        await lookupZip(zip);
    };

    // ===================================
    // 规则：燃油/住宅费/签名费
    // - 燃油：仅 YSD/632/GOFO大件
    // - 住宅费：YSD=3.8, 632=2.88, GOFO大件=3.17
    // - 签名费：YSD=9.30, 632=4.46, XLmiles=11.05（由开关控制）
    // ===================================
    function getResFee(ch){
        if(ch.includes("FedEx-YSD")) return 3.80;
        if(ch.includes("FedEx-632")) return 2.88;
        if(ch.includes("GOFO大件")) return 3.17;
        return 0;
    }
    function getSigFee(ch){
        if(ch.includes("FedEx-YSD")) return 9.30;
        if(ch.includes("FedEx-632")) return 4.46;
        if(ch.includes("XLmiles")) return 11.05;
        return 0;
    }
    function hasFuel(ch){
        if(ch.includes("FedEx-YSD") || ch.includes("FedEx-632") || ch.includes("GOFO大件")) return true;
        return false; // 其它已含燃油
    }

    // ===================================
    // FedEx 官网：住宅地址旺季附加费（构建时注入 DATA.fedex_res_peak）
    // 仅在：peak=ON 且 addr=res 且 渠道=FedEx-YSD/632 时叠加
    // ===================================
    function getFedexResPeakAmount(todayStr){
        let meta = DATA.fedex_res_peak;
        if(!meta || !meta.periods) return 0;
        let t = new Date(todayStr);
        for(let p of meta.periods){
            let s = new Date(p.start + "T00:00:00");
            let e = new Date(p.end + "T23:59:59");
            if(t>=s && t<=e) return parseFloat(p.amount)||0;
        }
        return 0;
    }

    // ===================================
    // 取 Excel 报价行（保留你原方式）
    // ===================================
    function getDivisor(ch, vol){
        let u = ch.toUpperCase();
        if(u.includes('UNIUNI')) return 0;
        if(u.includes('USPS')) return vol > 1728 ? 166 : 0;
        if(u.includes('ECO-MT')) return vol < 1728 ? 400 : 250;
        return 222;
    }

    // ===================================
    // 计算按钮
    // ===================================
    document.getElementById('btnCalc').onclick = async () => {
        let zip = document.getElementById('zipCode').value.trim();
        if(zip && zip.length===5 && (!LAST_LOC && (!CUR_ZONES || Object.keys(CUR_ZONES).length===0))){
            await lookupZip(zip);
        }

        let tier = document.querySelector('input[name="tier"]:checked').value;
        let wh = document.getElementById('warehouse').value;
        let whLabel = WAREHOUSE_LABEL[wh] || wh;

        let pkg = standardize(
            document.getElementById('length').value, document.getElementById('width').value, document.getElementById('height').value,
            document.getElementById('dimUnit').value, document.getElementById('weight').value, document.getElementById('weightUnit').value
        );

        let isPeak = document.getElementById('peakToggle').checked;
        let isRes = document.getElementById('addressType').value === 'res';
        let sigOn = document.getElementById('sigToggle').checked;

        let fedexFuel = parseFloat(document.getElementById('fedexFuel').value)/100;
        let gofoFuel = parseFloat(document.getElementById('gofoFuel').value)/100;

        document.getElementById('tierBadge').innerText = tier;

        let dims = [pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
        let L=dims[0], G=L+2*(dims[1]+dims[2]);
        document.getElementById('pkgSummary').innerHTML =
            `<b>基准:</b> ${dims[0].toFixed(1)}"${dims[1].toFixed(1)}"${dims[2].toFixed(1)}" | 实重:${pkg.Wt.toFixed(2)}lb | 围长:${G.toFixed(1)}"`;

        let tbody = document.getElementById('resBody');
        tbody.innerHTML='';

        if(!DATA.tiers || !DATA.tiers[tier]) {
            tbody.innerHTML='<tr><td colspan="8" class="text-danger">❌ 等级数据缺失</td></tr>';
            return;
        }

        // FedEx 计算用 zone
        let fedexZone = (zip && zip.length>=3) ? calculateZoneMath(zip, wh) : null;

        // 遍历该 tier 的渠道
        Object.keys(DATA.tiers[tier]).forEach(ch => {
            // 过滤仓库可用
            let allow = CHANNEL_WAREHOUSE_ALLOW[ch] || ["WEST","CENTRAL","EAST"];
            if(!allow.includes(wh)) return;

            let uCh = ch.toUpperCase();
            let prices = (DATA.tiers[tier][ch] && DATA.tiers[tier][ch].prices) ? DATA.tiers[tier][ch].prices : [];
            let zoneVal = "-";

            // Zone 选择：
            // - FedEx 标准渠道：用仓库+邮编计算
            // - 其它：仍用 GOFO 邮编库（CUR_ZONES）
            if(isFedexStandardChannel(ch)){
                zoneVal = fedexZone ? String(fedexZone) : "-";
            }else{
                zoneVal = (CUR_ZONES && CUR_ZONES[ch]) ? String(CUR_ZONES[ch]) : "-";
            }

            let base = 0;
            let st = "正常";
            let cls = "text-success";
            let bg = "";
            let details = [];

            // 计费重
            let cWt = pkg.Wt;
            let div = getDivisor(ch, pkg.L*pkg.W*pkg.H);
            if(div > 0) {
                let vWt = (pkg.L*pkg.W*pkg.H)/div;
                cWt = Math.max(pkg.Wt, vWt);
            }
            if(!uCh.includes('GOFO-报价') && cWt>1) cWt = Math.ceil(cWt);

            // ===== XLmiles：不走 Excel，走规则 =====
            if(ch.includes("XLmiles")){
                if(!fedexZone){
                    st="无分区/超重";
                    cls="text-muted";
                    bg="table-light";
                }else{
                    let xg = xl_zone_group(fedexZone);
                    if(!xg){
                        st="仓库/Zone不支持";
                        cls="text-muted";
                        bg="table-light";
                    }else{
                        zoneVal = "Z" + xg;
                        let r = xl_services_price(pkg, xg);
                        if(!r.ok){
                            st=r.reason; cls="text-danger fw-bold"; bg="table-danger";
                            base=0;
                        }else{
                            base=r.base;
                            details = details.concat(r.details);
                        }
                    }
                }

                // 住宅费：XLmiles 不收（未指定）
                // 签名费：按开关
                if(base>0 && sigOn){
                    let sf = getSigFee(ch);
                    if(sf>0){ details.push(`签名:$${sf.toFixed(2)}`); base += sf; }
                }

                let tot = base;
                tbody.innerHTML += `<tr class="${bg}">
                    <td class="fw-bold text-start text-nowrap">${ch}</td>
                    <td class="text-nowrap">${whLabel}</td>
                    <td>${zoneVal}</td>
                    <td>${cWt.toFixed(2)}</td>
                    <td class="fw-bold">${base>0?base.toFixed(2):"0.00"}</td>
                    <td class="text-start small" style="line-height:1.2">${details.join('<br>')||'-'}</td>
                    <td class="price-text">${tot>0?("$"+tot.toFixed(2)):'-'}</td>
                    <td class="${cls} small fw-bold">${st}</td>
                </tr>`;
                return;
            }

            // ===== 其它渠道：走 Excel 报价表 =====
            let zKey = zoneVal==='1' ? '2' : zoneVal; // 你的需求：YSD 从 Zone2 开始；Zone1 用 Zone2
            let row = null;
            if(prices && prices.length>0 && zKey!=='-'){
                for(let r of prices){
                    if(r.w >= cWt-0.001) { row=r; break; }
                }
            }
            if(!row || zoneVal==='-'){
                st="无分区/超重"; cls="text-muted"; bg="table-light";
                base=0;
            }else{
                base = row[zKey];
                if(base===undefined && zKey==='1') base=row['2'];
                if(!base){
                    st="无报价"; cls="text-warning"; bg="table-warning";
                    base=0;
                }
            }

            // 特殊拦截：USPS
            if(uCh.includes('USPS')) {
                if(zip && USPS_BLOCK.some(p => zip.startsWith(p))) {
                    st="无折扣 (Std Rate)"; cls="text-danger"; bg="table-danger"; base=0;
                }
                if(pkg.Wt>70 || L>30 || (L+(dims[1]+dims[2])*2)>130) {
                    st="超规不可发"; cls="text-danger fw-bold"; bg="table-danger"; base=0;
                }
            }

            // 特殊拦截：UniUni
            if(uCh.includes('UNIUNI')) {
                if(L>20 || (L+dims[1]+dims[2])>50 || pkg.Wt>20) {
                    st="超规不可发"; cls="text-danger fw-bold"; bg="table-danger"; base=0;
                }
            }

            // 费用叠加
            let fees = {fuel:0, res:0, peak:0, other:0, sig:0};

            if(base > 0) {
                // 住宅费（按渠道不同）
                if(isRes){
                    let rf = getResFee(ch);
                    if(rf>0){
                        fees.res = rf;
                        details.push(`住宅:$${rf.toFixed(2)}`);
                    }
                }

                // 旺季：目前只做你“必须真实更新”的 FedEx 住宅地址旺季附加费（官网 Demand Surcharge 固定每包金额）
                // 其余 AHS/OVERSIZE/Unauthorized 旺季项你要完全按 Excel 抽取再注入，我可以下一版加（需要你确认各项对应关系）
                if(isPeak){
                    // USPS 旺季：你原来是“按表查价叠加”，这里暂不破坏你现有结构（你说已能按表查价）
                    if(ch.includes("FedEx-YSD") || ch.includes("FedEx-632")){
                        if(isRes){
                            let today = new Date();
                            let todayStr = today.toISOString().slice(0,10);
                            let v = getFedexResPeakAmount(todayStr);
                            if(v>0){
                                fees.peak += v;
                                details.push(`住宅旺季:$${v.toFixed(2)}`);
                            }
                        }
                    }
                }

                // 签名费（按开关）
                if(sigOn){
                    let sf = getSigFee(ch);
                    if(sf>0){
                        fees.sig = sf;
                        details.push(`签名:$${sf.toFixed(2)}`);
                    }
                }

                // 燃油费
                if(hasFuel(ch)){
                    if(ch.includes("GOFO大件")){
                        let sub = base + fees.res + fees.peak + fees.sig + fees.other;
                        fees.fuel = sub * gofoFuel;
                        details.push(`燃油(${(gofoFuel*100).toFixed(1)}%):$${fees.fuel.toFixed(2)}`);
                    }else{
                        // FedEx-YSD / 632：燃油按基础运费计算（符合你当前口径）
                        fees.fuel = base * fedexFuel;
                        details.push(`燃油(${(fedexFuel*100).toFixed(1)}%):$${fees.fuel.toFixed(2)}`);
                    }
                }else{
                    // 已含燃油的渠道：不额外加
                }
            }

            let tot = base + fees.fuel + fees.res + fees.peak + fees.other + fees.sig;
            tbody.innerHTML += `<tr class="${bg}">
                <td class="fw-bold text-start text-nowrap">${ch}</td>
                <td class="text-nowrap">${whLabel}</td>
                <td>${zoneVal==='-'?'Zone -':('Zone '+zoneVal)}</td>
                <td>${cWt.toFixed(2)}</td>
                <td class="fw-bold">${base.toFixed(2)}</td>
                <td class="text-start small" style="line-height:1.2">${details.join('<br>')||'-'}</td>
                <td class="price-text">${tot>0?("$"+tot.toFixed(2)):'-'}</td>
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
            if all(k.upper().replace(" ", "") in s_name for k in target_keys):
                print(f"    > 匹配Sheet: {sheet}")
                return pd.read_excel(xl, sheet_name=sheet, header=None)
        return None
    except Exception as e:
        print(f"    > 读取失败: {e}")
        return None

def load_zip_db():
    print("--- 1. 加载邮编库（GOFO独立邮编区） ---")
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
        for idx, row in df.iloc[start:].iterrows():
            z = str(row[1]).strip().zfill(5)
            if z.isdigit() and len(z) == 5:
                zones = {}
                for k, v in ZIP_COL_MAP.items():
                    val = str(row[v]).strip()
                    if val in ['-', 'nan', '', '0', 0]:
                        zones[k] = None
                    else:
                        zones[k] = val
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
    print("\n--- 2. 加载报价表 (中文兼容版) ---")
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

                    # 解析 Zone：支持 Zone 1 / 分区1 / zone~1
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

                # === 排查日志（你要求“最小改动一行日志”）：输出每个渠道 zones/prices 数量 ===
                print(f"    > {t_name}/{ch_key}: zones={list(z_map.keys())}, prices={len(prices)}")

            except:
                pass

        all_tiers[t_name] = t_data

    return all_tiers

if __name__ == '__main__':
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # 构建时抓 FedEx 官方住宅旺季（Demand）固定每包金额
    fedex_res_peak = fetch_fedex_residential_peak_table()

    final = {
        "zip_db": load_zip_db(),
        "tiers": load_tiers(),
        "surcharges": GLOBAL_SURCHARGES,
        "fedex_res_peak": fedex_res_peak
    }

    print("\n--- 3. 生成网页 ---")
    try:
        js_str = json.dumps(final, allow_nan=False)
    except:
        js_str = json.dumps(final).replace("NaN", "0")

    html = HTML_TEMPLATE.replace('__JSON_DATA__', js_str)

    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ 完成！FedEx 标准渠道已改为仓库+邮编算 Zone；XLmiles 已按规则计算；FedEx住宅旺季构建时自动更新。")
