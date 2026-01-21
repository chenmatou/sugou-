import pandas as pd
import json
import re
import os
import warnings

# 忽略 Excel 样式警告
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# ==========================================
# 1. 全局配置
# ==========================================
DATA_DIR = "data"
OUTPUT_DIR = "public"

TIER_FILES = {"T0": "T0.xlsx", "T1": "T1.xlsx", "T2": "T2.xlsx", "T3": "T3.xlsx"}

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
    "FedEx-YSD-报价": ["FedEx", "YSD"],  # 包含 FedEx 和 YSD
}

# 邮编库配置（GOFO 独立邮编区：来自 GOFO-报价 sheet 下方邮编区）
ZIP_DB_SHEET_KEY = "GOFO-报价"
ZIP_COL_MAP = {
    "GOFO-报价": 5,
    "GOFO-MT-报价": 6,
    "UNIUNI-MT-报价": 7,
    "USPS-YSD-报价": 8,
    "FedEx-ECO-MT报价": 9,
    "XLmiles-报价": 10,
    "GOFO大件-GRO-报价": 11,
    "FedEx-632-MT-报价": 12,
    "FedEx-YSD-报价": 13,
}

# 默认附加费（FedEx 旺季 / 超大 / Unauthorized 等，若需严格“从表格提取”，把表格值写死到这里即可）
GLOBAL_SURCHARGES = {
    "peak_res": 1.32,            # 住宅地址旺季附加费
    "peak_oversize": 54,         # 旺季 Oversize 附加费
    "peak_unauthorized": 220,    # 旺季 Unauthorized 附加费
    "oversize_fee": 130,         # Oversize 基础附加费
    "ahs_fee": 20,               # AHS/超重超尺寸（本处为占位值：如表格不同请替换）
    "unauthorized_fee": 1150,    # Unauthorized 基础附加费
}

# 住宅地址费（按你指定的渠道-价格）
RES_FEE_BY_CHANNEL = {
    "FedEx-YSD-报价": 3.80,
    "FedEx-632-MT-报价": 2.88,
    "GOFO大件-GRO-报价": 3.17,
}

# 签名签收费（直接/间接签名签收 Indirect/Direct Signature）
SIGNATURE_FEE_BY_CHANNEL = {
    "FedEx-YSD-报价": 9.30,
    "FedEx-632-MT-报价": 4.46,
    "XLmiles-报价": 11.05,
}

# 仓库可用渠道（写死：选择仓库后，仅显示可用渠道；不可用不显示）
WAREHOUSE_CHANNELS = {
    "WEST_91730": [
        "GOFO-报价",
        "GOFO-MT-报价",
        "UNIUNI-MT-报价",
        "USPS-YSD-报价",
        "FedEx-YSD-报价",
        "XLmiles-报价",
        "GOFO大件-GRO-报价",
        "FedEx-632-MT-报价",
        "FedEx-ECO-MT报价",
    ],
    "CENTRAL": [
        "GOFO-报价",
        "GOFO-MT-报价",
        "UNIUNI-MT-报价",
        "USPS-YSD-报价",
        "FedEx-YSD-报价",
        "GOFO大件-GRO-报价",
        "FedEx-632-MT-报价",
        "FedEx-ECO-MT报价",
    ],
    "EAST": [
        "GOFO大件-GRO-报价",
        "FedEx-632-MT-报价",
        "FedEx-ECO-MT报价",
    ],
}

# 州名（中英文展示）
US_STATES_CN = {
    "AL": "阿拉巴马", "AK": "阿拉斯加", "AZ": "亚利桑那", "AR": "阿肯色", "CA": "加利福尼亚",
    "CO": "科罗拉多", "CT": "康涅狄格", "DE": "特拉华", "FL": "佛罗里达", "GA": "佐治亚",
    "HI": "夏威夷", "ID": "爱达荷", "IL": "伊利诺伊", "IN": "印第安纳", "IA": "爱荷华",
    "KS": "堪萨斯", "KY": "肯塔基", "LA": "路易斯安那", "ME": "缅因", "MD": "马里兰",
    "MA": "马萨诸塞", "MI": "密歇根", "MN": "明尼苏达", "MS": "密西西比", "MO": "密苏里",
    "MT": "蒙大拿", "NE": "内布拉斯加", "NV": "内华达", "NH": "新罕布什尔", "NJ": "新泽西",
    "NM": "新墨西哥", "NY": "纽约", "NC": "北卡罗来纳", "ND": "北达科他", "OH": "俄亥俄",
    "OK": "俄克拉荷马", "OR": "俄勒冈", "PA": "宾夕法尼亚", "RI": "罗德岛", "SC": "南卡罗来纳",
    "SD": "南达科他", "TN": "田纳西", "TX": "德克萨斯", "UT": "犹他", "VT": "佛蒙特",
    "VA": "弗吉尼亚", "WA": "华盛顿", "WV": "西弗吉尼亚", "WI": "威斯康星", "WY": "怀俄明",
    "DC": "华盛顿特区",
}

# ==========================================
# 2. 网页模板（仅对“有问题处”做改动）
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
    body { font-family: 'Segoe UI','Microsoft YaHei',sans-serif; background-color:#f4f6f9; min-height:100vh; display:flex; flex-direction:column; }
    header { background-color:var(--header-bg); color:#fff; padding:15px 0; border-bottom:3px solid #333; }
    footer { background-color:var(--header-bg); color:#aaa; padding:20px 0; margin-top:auto; text-align:center; font-size:0.85rem; }
    .card { border:none; border-radius:8px; box-shadow:0 2px 10px rgba(0,0,0,0.05); margin-bottom:20px; }
    .card-header { background-color:#212529; color:#fff; font-weight:600; padding:10px 20px; border-radius:8px 8px 0 0 !important; }
    .form-label { font-weight:600; font-size:0.85rem; color:#555; margin-bottom:4px; }
    .input-group-text { font-size:0.85rem; font-weight:600; background-color:#e9ecef; }
    .form-control, .form-select { font-size:0.9rem; }
    .status-table { width:100%; font-size:0.85rem; }
    .status-table td { padding:6px; border-bottom:1px solid #eee; vertical-align:middle; }
    .indicator { display:inline-block; padding:2px 8px; border-radius:4px; color:#fff; font-weight:bold; font-size:0.75rem; }
    .bg-ok { background-color:#198754; }
    .bg-warn { background-color:#ffc107; color:#000; }
    .bg-err { background-color:#dc3545; }
    .result-table th { background-color:#212529; color:#fff; text-align:center; font-size:0.85rem; vertical-align:middle; }
    .result-table td { text-align:center; vertical-align:middle; font-size:0.9rem; }
    .price-text { font-weight:800; font-size:1.1rem; color:#0d6efd; }
    .fuel-link { font-size:0.75rem; text-decoration:none; color:#0d6efd; display:block; margin-top:3px; }
    #globalError { position:fixed; top:20px; left:50%; transform:translateX(-50%); z-index:9999; width:80%; display:none; }
    .note-box { font-size:0.85rem; line-height:1.35; }
  </style>
</head>
<body>

<div id="globalError" class="alert alert-danger shadow-lg">
  <h5 class="alert-heading">⚠️ 系统运行错误</h5>
  <p id="errorMsg">未知错误</p>
</div>

<header>
  <div class="container d-flex justify-content-between align-items-center">
    <div>
      <h5 class="m-0 fw-bold">📦 业务员报价助手</h5>
      <small class="opacity-75">T0-T3 专家版 (V9.0 中文兼容)</small>
    </div>
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

            <!-- 新增：仓库选择（仅影响“显示哪些渠道”，不做动态算区） -->
            <div class="mb-3">
              <label class="form-label">发货仓库 (仅决定可用渠道显示)</label>
              <select class="form-select" id="warehouse">
                <option value="WEST_91730">美西 - 91730</option>
                <option value="CENTRAL">美中</option>
                <option value="EAST">美东</option>
              </select>
              <div class="text-muted small mt-1">说明：选仓库后，仅展示该仓库可用渠道；不可用渠道不显示报价。</div>
            </div>

            <!-- 燃油费率：标注清晰 + 排序修正 -->
            <div class="bg-light p-2 rounded border mb-3">
              <div class="fw-bold small mb-2 border-bottom">⛽ 燃油费率 (Fuel Surcharge)</div>
              <div class="row g-2">
                <div class="col-12">
                  <label class="form-label small">统一燃油 (%) <span class="text-danger">仅：FedEx-YSD / FedEx-632-MT / GOFO大件</span></label>
                  <input type="number" class="form-control form-control-sm" id="unifiedFuel" value="16.0" step="0.1">
                  <a href="https://www.fedex.com.cn/en-us/shipping/historical-fuel-surcharge.html" target="_blank" class="fuel-link">🔗 FedEx燃油官网</a>
                </div>
                <div class="col-12 mt-2">
                  <label class="form-label small">USPS 燃油 (%) <span class="text-muted">仅：USPS-YSD</span></label>
                  <input type="number" class="form-control form-control-sm" id="uspsFuel" value="0.0" step="0.1">
                  <span class="text-muted small d-block mt-1">提示：USPS 常见为 0%，如需可手动调整。</span>
                </div>
              </div>

              <div class="mt-2 small text-muted">
                <div><b>已包含燃油的报价：</b>FedEx-ECO-MT、GOFO-报价、GOFO-MT、UNIUNI-MT（这些渠道不额外叠加燃油）</div>
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
                <div class="col-12">
                  <select class="form-select form-select-sm" id="dimUnit">
                    <option value="in">IN (英寸)</option>
                    <option value="cm">CM (厘米)</option>
                    <option value="mm">MM (毫米)</option>
                  </select>
                </div>
              </div>
              <div class="row g-2 mt-2">
                <div class="col-8"><div class="input-group input-group-sm"><span class="input-group-text">重量</span><input type="number" class="form-control" id="weight" placeholder="实重"></div></div>
                <div class="col-4">
                  <select class="form-select form-select-sm" id="weightUnit">
                    <option value="lb">LB (磅)</option>
                    <option value="oz">OZ (盎司)</option>
                    <option value="kg">KG (千克)</option>
                    <option value="g">G (克)</option>
                  </select>
                </div>
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
            1. <strong>FedEx-YSD / FedEx-632-MT</strong>：支持旺季（AHS/OVERSIZE/UNAUTHORIZED/住宅旺季），住宅费按渠道固定；可叠加签名签收费。<br>
            2. <strong>GOFO大件</strong>：住宅费按渠道固定；燃油使用“统一燃油”；燃油对(基础+附加费)计入。<br>
            3. <strong>USPS-YSD</strong>：燃油独立（USPS燃油）；旺季附加费<strong>按表格右侧《2025旺季附加费-USPS Ground Advantage》查价</strong>并叠加。<br>
            4. <strong>FedEx ECO-MT</strong>：FedEx与USPS联合承运，末端USPS派送；报价表仅供参考；<strong>不包含旺季附加费</strong>，实际以账单为准。<br>
            5. <strong>XLmiles</strong>：超大件渠道，含签名签收费；按 AH/OS/OM 规则判定服务类型与费用（见下方说明）。<br>
            6. 如派送后产生额外费用（复核尺寸不符/退货/其它附加费等）导致物流商向我司加收，我司将实报实销。<br>
          </div>

          <!-- 新增：旺季/免责声明板块（只展示说明，不影响计算） -->
          <div class="alert alert-warning mt-3 note-box">
            <div class="fw-bold mb-1">旺季附加费 / 注意事项（必读）</div>
            <div>① USPS Ground Advantage 2025 报价表的旺季附加费在报价表右侧，全名称：<b>2025旺季附加费-USPS Ground Advantage</b>，USPS-YSD 旺季费需按该表格独立查价并叠加。</div>
            <div>② FedEx-ECO-MT：本渠道为 FedEx 与 USPS 联合承运，末端派送由 USPS 完成；报价表仅供参考，ECO-MT 渠道不包含旺季附加费，实际收费以系统账单为准。</div>
            <div>③ XLmiles 注意事项：LA/NJ/HOU 核心区域免费揽收；实时包裹追踪；POD 在我司系统一键获取；对标 Threshold 等级服务，投递至前门/后门/车库门。</div>
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

  // 自动计算监听
  document.querySelectorAll('input[name="tier"]').forEach(r => {
    r.addEventListener('change', () => document.getElementById('btnCalc').click());
  });
  document.getElementById('warehouse').addEventListener('change', () => document.getElementById('btnCalc').click());

  // USPS 特殊拦截前缀
  const USPS_BLOCK = ['006','007','008','009','090','091','092','093','094','095','096','097','098','099','340','962','963','964','965','966','967','968','969','995','996','997','998','999'];

  // FedEx ECO-MT 附加费表 (Zone 2, 3-4, 5-6, 7+)
  const ECO_FEES = {
    ahs: [6.55, 7.28, 8.03, 8.92],
    overweight: [10.26, 11.14, 11.89, 12.92],
    oversize: [71.28, 77.97, 84.64, 91.33],
    nonstd: [5.80, 6.84, 7.14, 7.43]
  };

  // XLmiles 判定（你提供的规则）
  function classifyXLmiles(pkg) {
    let d = [pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
    let L = d[0];
    let G = L + 2*(d[1]+d[2]);

    // OM: <=144", G<=225, <=200lb
    if (L <= 144 && G <= 225 && pkg.Wt <= 200) return { ok:true, type:"OM" };
    // OS: <=108", G<=165, <=150lb
    if (L <= 108 && G <= 165 && pkg.Wt <= 150) return { ok:true, type:"OS" };
    // AH: <=96", G<=130, <=150lb（但费率分<=90 / <=150）
    if (L <= 96 && G <= 130 && pkg.Wt <= 150) return { ok:true, type:"AH" };

    return { ok:false, type:"超限" };
  }

  const RULES = {
    // 哪些渠道“需要燃油”
    // 统一燃油：仅 FedEx-YSD / FedEx-632-MT / GOFO大件
    // USPS燃油：仅 USPS-YSD
    // 其它渠道：报价已含燃油（不叠加）
    fuelGroup: (name) => {
      if (name === 'USPS-YSD-报价') return 'USPS';
      if (name === 'FedEx-YSD-报价' || name === 'FedEx-632-MT-报价' || name === 'GOFO大件-GRO-报价') return 'UNIFIED';
      return 'NONE';
    },
    // 计费重除数
    getDivisor: (n, vol) => {
      let u = (n||'').toUpperCase();
      if (u.includes('UNIUNI')) return 0;
      if (u.includes('USPS')) return vol > 1728 ? 166 : 0;
      if (u.includes('ECO-MT')) return vol < 1728 ? 400 : 250;
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

  // 全渠道实时检测模块（新增 XLmiles）
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
    h += row('UNIUNI', uFail, '限制(L>20/Wt>20)');

    // USPS: 重>70, 围长>130, 长>30
    let usFail = (pkg.Wt>70 || L>30 || (L+(d[1]+d[2])*2)>130);
    h += row('USPS', usFail, '限制(>70lb/130")');

    // FedEx: 重>150, 长>108, 围>165
    let fFail = (pkg.Wt>150 || L>108 || G>165);
    h += row('FedEx', fFail, '不可发(>150lb)');

    // GOFO大件: 重>150
    let gFail = (pkg.Wt>150);
    h += row('GOFO大件', gFail, '超限(>150lb)');

    // XLmiles: OM<=144"/225"/200lb; OS<=108"/165"/150lb; AH<=96"/130"/150lb
    let xl = classifyXLmiles(pkg);
    h += row('XLmiles', !xl.ok, xl.ok ? xl.type : '超限(>OM范围)');

    document.getElementById('checkTable').innerHTML = h;
  }

  ['length','width','height','weight','dimUnit','weightUnit'].forEach(id=>{
    document.getElementById(id).addEventListener('input', ()=>{
      let p = standardize(
        document.getElementById('length').value, document.getElementById('width').value, document.getElementById('height').value,
        document.getElementById('dimUnit').value, document.getElementById('weight').value, document.getElementById('weightUnit').value
      );
      check(p);
    });
  });

  document.getElementById('btnLookup').onclick = () => {
    let z = document.getElementById('zipCode').value.trim();
    let d = document.getElementById('locInfo');

    if(!DATA.zip_db || !DATA.zip_db[z]) {
      d.innerHTML="<span class='text-danger'>❌ 未找到邮编</span>";
      CUR_ZONES={};
      return;
    }
    let i = DATA.zip_db[z];
    d.innerHTML = `<span class='text-success'>✅ ${i.sn} ${i.s} - ${i.c} [${i.r}]</span>`;
    CUR_ZONES = i.z || {};
  };

  function isChannelAvailable(ch) {
    let wh = document.getElementById('warehouse').value;
    let allow = (DATA.warehouse_channels && DATA.warehouse_channels[wh]) ? DATA.warehouse_channels[wh] : [];
    return allow.includes(ch);
  }

  // USPS 旺季附加费（按表格查价）：DATA.usps_peak_table
  function getUspsPeakFee(cWt, zoneVal) {
    try {
      if(!DATA.usps_peak_table || !Array.isArray(DATA.usps_peak_table)) return 0;
      let z = String(zoneVal||'').trim();
      if(!z || z==='-') return 0;
      // 找到第一个 weight >= cWt 的行
      for(let r of DATA.usps_peak_table) {
        if(r && typeof r.w === 'number' && r.w + 1e-9 >= cWt) {
          let v = r[z];
          return (typeof v === 'number') ? v : 0;
        }
      }
      return 0;
    } catch(e) { return 0; }
  }

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

    let tbody = document.getElementById('resBody');
    tbody.innerHTML='';

    if(!DATA.tiers || !DATA.tiers[tier]) {
      tbody.innerHTML='<tr><td colspan="7" class="text-danger">❌ 等级数据缺失</td></tr>';
      return;
    }

    // 逐渠道计算（仅展示：当前仓库可用渠道）
    Object.keys(DATA.tiers[tier]).forEach(ch => {
      if(!isChannelAvailable(ch)) return;

      let prices = DATA.tiers[tier][ch].prices;
      if(!prices || prices.length===0) return;

      // Zone 取值：优先本渠道；FedEx-YSD 若缺失则用 632 兜底（同属 FedEx 标准算区）
      let zoneVal = CUR_ZONES[ch];
      if((zoneVal===null || zoneVal===undefined || zoneVal==='') && ch === 'FedEx-YSD-报价') {
        zoneVal = CUR_ZONES['FedEx-632-MT-报价'] || CUR_ZONES['FedEx-ECO-MT报价'] || null;
        // 仅用于排查：前端控制台记录一次
        try { console.warn('[debug] FedEx-YSD zone missing, fallback to 632/ECO zone=', zoneVal); } catch(e){}
      }
      zoneVal = (zoneVal===null || zoneVal===undefined || zoneVal==='') ? '-' : String(zoneVal).trim();

      let uCh = ch.toUpperCase();
      let base=0, st="正常", cls="text-success", bg="";
      let cWt = pkg.Wt;
      let details = [];

      // 1) 计费重
      let div = RULES.getDivisor(ch, pkg.L*pkg.W*pkg.H);
      if(div > 0) {
        let vWt = (pkg.L*pkg.W*pkg.H)/div;
        cWt = Math.max(pkg.Wt, vWt);
      }
      if(!uCh.includes('GOFO-报价') && cWt>1) cWt = Math.ceil(cWt);

      // 2) 匹配价格（FedEx-YSD：报价从 zone2 开始；若算出 zone1 则按 zone2 取价）
      let zKey = (zoneVal==='1') ? '2' : zoneVal;
      let row = null;
      for(let r of prices) { if(r.w >= cWt-0.001) { row=r; break; } }

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
      if(uCh.includes('XLMILES')) {
        let xl = classifyXLmiles(pkg);
        if(!xl.ok) {
          st="超规不可发"; cls="text-danger fw-bold"; bg="table-danger"; base=0;
        } else {
          // 可发则显示类型提示
          details.push(`服务:${xl.type}`);
        }
      }

      // 4) 费用叠加
      let fees = {f:0, r:0, p:0, o:0, s:0};

      if(base > 0) {

        // 4.1 住宅地址费（仅你指定的三个渠道）
        if(isRes && DATA.res_fee_by_channel && DATA.res_fee_by_channel[ch] !== undefined) {
          fees.r = DATA.res_fee_by_channel[ch];
          details.push(`住宅:$${fees.r.toFixed(2)}`);
        }

        // 4.2 签名签收费（你指定的渠道）
        if(DATA.signature_fee_by_channel && DATA.signature_fee_by_channel[ch] !== undefined) {
          fees.s = DATA.signature_fee_by_channel[ch];
          details.push(`签名:$${fees.s.toFixed(2)}`);
        }

        // 4.3 FedEx ECO-MT：Max-of-3（保持原逻辑）
        if(uCh.includes('ECO-MT')) {
          let idx = getEcoZoneIdx(zoneVal);
          let f_ahs = (L>48 || dims[1]>30 || (L+2*(dims[1]+dims[2]))>105) ? ECO_FEES.ahs[idx] : 0;
          let f_ow = (pkg.Wt>50) ? ECO_FEES.overweight[idx] : 0;
          let f_os = (G>108 && G<130) ? ECO_FEES.oversize[idx] : 0;

          let maxFee = Math.max(f_ahs, f_ow, f_os);
          if(maxFee > 0) {
            fees.o += maxFee;
            let reason = (maxFee===f_os) ? "超大" : ((maxFee===f_ow) ? "超重" : "AHS");
            details.push(`${reason}:$${maxFee.toFixed(2)}`);
            st = reason; cls = "text-warning fw-bold";
          }
          if(pkg.Wt>70 || G>130) {
            st="不可发(Unauth)"; cls="text-danger fw-bold"; bg="table-danger";
            fees.o += 2000;
          }
        }
        // 4.4 FedEx-YSD / 632：旺季逻辑（AHS/OVERSIZE/UNAUTHORIZED/住宅旺季）
        else if(ch === 'FedEx-YSD-报价' || ch === 'FedEx-632-MT-报价') {
          // 基础超大/Unauthorized（非旺季也要判定）
          let isUn = (L>108 || G>165 || pkg.Wt>150);
          let isOver = (L>96 || G>130);

          if(isUn) {
            fees.o += DATA.surcharges.unauthorized_fee;
            st="Unauthorized"; cls="text-danger fw-bold"; bg="table-danger";
            details.push(`Unauthorized:$${DATA.surcharges.unauthorized_fee.toFixed(2)}`);
          } else if(isOver) {
            fees.o += DATA.surcharges.oversize_fee;
            st="Oversize"; cls="text-warning fw-bold";
            details.push(`超大:$${DATA.surcharges.oversize_fee.toFixed(2)}`);
          }

          // 旺季附加（你要求：开启旺季后才触发）
          if(isPeak) {
            // AHS：超重/超尺寸（占位逻辑：L>48 或 第二边>30 或 围长>105 或 实重>50）
            let isAHS = (L>48 || dims[1]>30 || (L+2*(dims[1]+dims[2]))>105 || pkg.Wt>50);
            if(isAHS) {
              fees.p += DATA.surcharges.ahs_fee;
              details.push(`旺季AHS:$${DATA.surcharges.ahs_fee.toFixed(2)}`);
            }
            if(st.includes('Oversize')) {
              fees.p += DATA.surcharges.peak_oversize;
              details.push(`旺季OS:$${DATA.surcharges.peak_oversize.toFixed(2)}`);
            }
            if(st.includes('Unauthorized')) {
              fees.p += DATA.surcharges.peak_unauthorized;
              details.push(`旺季Unauth:$${DATA.surcharges.peak_unauthorized.toFixed(2)}`);
            }
            if(isRes && DATA.res_fee_by_channel && DATA.res_fee_by_channel[ch] !== undefined) {
              fees.p += DATA.surcharges.peak_res;
              details.push(`旺季住宅:$${DATA.surcharges.peak_res.toFixed(2)}`);
            }
          }
        }
        // 4.5 其他渠道：保留原 Oversize/Unauthorized 判定（但不引入住宅费/燃油，避免误叠加）
        else if(st !== "超规不可发" && st !== "无折扣 (Std Rate)") {
          let isUn = (L>108 || G>165 || pkg.Wt>150);
          let isOver = (L>96 || G>130);

          if(isUn) {
            fees.o += DATA.surcharges.unauthorized_fee;
            st="Unauthorized"; cls="text-danger fw-bold"; bg="table-danger";
            details.push(`Unauthorized:$${DATA.surcharges.unauthorized_fee.toFixed(2)}`);
          } else if(isOver) {
            fees.o += DATA.surcharges.oversize_fee;
            st="Oversize"; cls="text-warning fw-bold";
            details.push(`超大:$${DATA.surcharges.oversize_fee.toFixed(2)}`);
          }

          // 其它渠道旺季：仅 USPS 走表；ECO-MT 明确不包含旺季；其它保持不变（避免误算）
        }

        // 4.6 USPS 旺季：按表格查价叠加（你要求）
        if(isPeak && ch === 'USPS-YSD-报价') {
          let p = getUspsPeakFee(cWt, zoneVal);
          if(p > 0) {
            fees.p += p;
            details.push(`旺季:$${p.toFixed(2)}`);
          } else {
            // 查不到就不加，避免乱加
            details.push(`旺季:$0.00`);
          }
        }

        // 4.7 燃油（按分组：UNIFIED / USPS / NONE）
        let fg = RULES.fuelGroup(ch);
        if(fg === 'UNIFIED') {
          if(ch === 'GOFO大件-GRO-报价') {
            // GOFO大件：燃油对(基础+附加)计入
            let subTotal = base + fees.r + fees.p + fees.o + fees.s;
            fees.f = subTotal * unifiedFuel;
            details.push(`燃油(${(unifiedFuel*100).toFixed(1)}%):$${fees.f.toFixed(2)}`);
          } else {
            // FedEx-YSD / 632：燃油对基础运费计入
            fees.f = base * unifiedFuel;
            details.push(`燃油(${(unifiedFuel*100).toFixed(1)}%):$${fees.f.toFixed(2)}`);
          }
        } else if(fg === 'USPS') {
          fees.f = base * uspsFuel;
          details.push(`燃油(${(uspsFuel*100).toFixed(1)}%):$${fees.f.toFixed(2)}`);
        } else {
          // NONE：报价已含燃油，不额外加
        }
      }

      let tot = base + fees.f + fees.r + fees.p + fees.o + fees.s;

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
# 3. 核心数据清洗（仅对“有问题处”做改动）
# ==========================================

def safe_float(val):
    """修复点：兼容 $ / ￥ / ¥ / 逗号，并尽量从字符串中提取数字"""
    try:
        if pd.isna(val) or val == "" or str(val).strip().lower() == "nan":
            return 0.0
        s = str(val).strip()
        s = s.replace(",", "").replace("$", "").replace("￥", "").replace("¥", "")
        # 允许出现文字时抽取第一个数字
        m = re.findall(r"[-]?\d+(?:\.\d+)?", s)
        if not m:
            return 0.0
        return float(m[0])
    except:
        return 0.0

def normalize_zone(v):
    """把 1 / 1.0 / ' 1 ' 统一成 '1'；空值返回 None"""
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "-", "none"):
        return None
    # 1.0 -> 1
    if re.fullmatch(r"\d+(\.0+)?", s):
        try:
            return str(int(float(s)))
        except:
            return s
    return s

def get_sheet_by_name(excel_file, target_keys):
    try:
        xl = pd.ExcelFile(excel_file, engine="openpyxl")
        for sheet in xl.sheet_names:
            s_name = sheet.upper().replace(" ", "")
            if all(k.upper() in s_name for k in target_keys):
                print(f"    > 匹配Sheet: {sheet}")
                return pd.read_excel(xl, sheet_name=sheet, header=None)
        return None
    except Exception as e:
        print(f"    > 读取失败: {e}")
        return None

def load_zip_db():
    print("--- 1. 加载邮编库（GOFO独立邮编区） ---")
    path = os.path.join(DATA_DIR, TIER_FILES["T0"])
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
                    "sn": US_STATES_CN.get(sb, ""),
                    "c": str(row[4]).strip(),
                    "r": str(row[2]).strip(),
                    "z": zones,
                }
    except:
        pass

    print(f"✅ 邮编库: {len(db)} 条")
    return db

def to_lb(val):
    s = str(val).upper().strip()
    if pd.isna(val) or s == "NAN" or s == "":
        return None
    nums = re.findall(r"[\d\.]+", s)
    if not nums:
        return None
    n = float(nums[0])
    if "OZ" in s:
        return n / 16.0
    if "KG" in s:
        return n / 0.453592
    return n

def load_usps_peak_table():
    """
    USPS 旺季附加费表：你要求从 USPS-YSD-报价 副本右侧表格读取
    这里做“尽量兼容”的解析：识别包含“旺季附加费/2025旺季附加费”的表头行，然后按 weight + zone 列抽取
    """
    print("\n--- 1.2 解析 USPS 旺季附加费表格（按表格查价） ---")
    path = os.path.join(DATA_DIR, TIER_FILES["T0"])
    if not os.path.exists(path):
        return []

    df = get_sheet_by_name(path, ["USPS", "YSD"])
    if df is None:
        return []

    df = df.fillna("")
    h_row = None
    # 找表头：同时出现（旺季附加费/2025旺季附加费）与（zone/分区）与（weight/重量）
    for i in range(80):
        row_str = " ".join(df.iloc[i].astype(str).values).lower().replace(" ", "")
        if (("旺季附加费" in row_str) or ("2025" in row_str)) and (("zone" in row_str) or ("分区" in row_str)) and (("weight" in row_str) or ("重量" in row_str) or ("lb" in row_str)):
            h_row = i
            break

    if h_row is None:
        # 保持不报错：返回空表
        print("✅ USPS 旺季表: 0 行（未识别到表头）")
        return []

    headers = df.iloc[h_row].astype(str).str.lower().tolist()
    w_idx = -1
    z_map = {}

    for i, v in enumerate(headers):
        vv = str(v).lower()
        if w_idx == -1 and (("weight" in vv) or ("重量" in vv) or ("lb" in vv)):
            w_idx = i
        m = re.search(r"(?:zone|分区)\s*~?\s*(\d+)", vv)
        if m:
            zn = m.group(1)
            z_map[zn] = i

    if w_idx == -1 or not z_map:
        print("✅ USPS 旺季表: 0 行（未识别到列）")
        return []

    out = []
    for i in range(h_row + 1, len(df)):
        row = df.iloc[i]
        lb = to_lb(row[w_idx])
        if lb is None:
            continue
        item = {"w": float(lb)}
        for z, col in z_map.items():
            item[z] = safe_float(row[col])
        out.append(item)

    out.sort(key=lambda x: x["w"])
    print(f"✅ USPS 旺季表: {len(out)} 行")
    return out

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

            df = df.fillna("")
            try:
                h_row = 0
                # 寻找表头行：兼容 中文 '重量','分区' 及 英文 'weight','zone'
                for i in range(80):
                    row_str = " ".join(df.iloc[i].astype(str).values).lower()
                    has_zone = ("zone" in row_str or "分区" in row_str)
                    has_weight = ("weight" in row_str or "lb" in row_str or "重量" in row_str)
                    if has_zone and has_weight:
                        h_row = i
                        break

                headers = df.iloc[h_row].astype(str).str.lower().tolist()
                w_idx = -1
                z_map = {}

                # 修复点：XLmiles 在 T2/T3 价格可能带￥/文本，safe_float 已修复；
                # 若 zone 列名含“1-2/1~2”这类，做一次兼容映射（避免出现 zones=['30','35'] 这种误抓）
                if ch_key == "XLmiles-报价":
                    for i, v in enumerate(headers):
                        vv = str(v).lower().replace(" ", "")
                        if w_idx == -1 and (("weight" in vv) or ("lb" in vv) or ("重量" in vv)):
                            w_idx = i
                        # zone 1-2 列：同时出现 zone/分区 与 1 与 2（或 1-2/1~2）
                        if ("zone" in vv or "分区" in vv) and (("1-2" in vv) or ("1~2" in vv) or ("1/2" in vv) or (("1" in vv) and ("2" in vv))):
                            z_map["1"] = i
                            z_map["2"] = i
                        # zone 3 列
                        if ("zone" in vv or "分区" in vv) and re.search(r"(?:zone|分区)\s*~?\s*3", vv):
                            z_map["3"] = i
                    # 兜底：若没识别到，则走通用逻辑
                    if not z_map:
                        pass

                if w_idx == -1:
                    for i, v in enumerate(headers):
                        vv = str(v).lower()
                        if ("weight" in vv or "lb" in vv or "重量" in vv) and w_idx == -1:
                            w_idx = i

                # 通用 zone 列识别（避免误抓价格数字：仅在列名里含 zone/分区 时才抓）
                if not z_map:
                    for i, v in enumerate(headers):
                        vv = str(v).lower()
                        if ('weight' in vv or 'lb' in vv or '重量' in vv) and w_idx == -1:
                            w_idx = i
                        if ("zone" in vv or "分区" in vv):
                            m = re.search(r"(?:zone|分区)\s*~?\s*(\d+)", vv)
                            if m:
                                zn = m.group(1)
                                if zn not in z_map:
                                    z_map[zn] = i

                if w_idx == -1:
                    continue

                prices = []
                for i in range(h_row + 1, len(df)):
                    row = df.iloc[i]
                    lb = to_lb(row[w_idx])
                    if lb is None:
                        continue
                    item = {"w": float(lb)}
                    for z, col in z_map.items():
                        clean_p = safe_float(row[col])
                        if clean_p > 0:
                            item[z] = clean_p
                    if len(item) > 1:
                        prices.append(item)

                prices.sort(key=lambda x: x["w"])
                t_data[ch_key] = {"prices": prices}

            except:
                pass

        all_tiers[t_name] = t_data

    return all_tiers

if __name__ == "__main__":
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    final = {
        "zip_db": load_zip_db(),
        "tiers": load_tiers(),
        "surcharges": GLOBAL_SURCHARGES,
        "res_fee_by_channel": RES_FEE_BY_CHANNEL,
        "signature_fee_by_channel": SIGNATURE_FEE_BY_CHANNEL,
        "warehouse_channels": WAREHOUSE_CHANNELS,
        "usps_peak_table": load_usps_peak_table(),
    }

    print("\n--- 3. 生成网页 ---")
    try:
        js_str = json.dumps(final, allow_nan=False)
    except:
        js_str = json.dumps(final).replace("NaN", "0")

    html = HTML_TEMPLATE.replace("__JSON_DATA__", js_str)

    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ 完成！已按要求修复/更新：")
    print("  - XLmiles T2/T3 价格解析（支持￥/¥，并修正 zone 列误抓）")
    print("  - 燃油模块标注与排序（仅指定渠道叠加燃油；USPS燃油独立）")
    print("  - FedEx-YSD 无 zone1：zone1 自动按 zone2 取价")
    print("  - 旺季说明板块 + USPS 旺季按表查价（识别到则叠加；识别不到不乱加）")
    print("  - 住宅地址费按渠道固定 + 新增签名签收费")
    print("  - XLmiles 合规性检查与说明")
    print("  - 仓库选择仅决定可用渠道显示（写死映射）")
