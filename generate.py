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
    "FedEx-YSD-报价": ["FedEx", "YSD"],
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

# 默认附加费（FedEx 旺季 / 超大 / Unauthorized 等）
GLOBAL_SURCHARGES = {
    "peak_res": 1.32,            # 旺季住宅附加费 (Peak Residential)
    "peak_oversize": 54,         # 旺季超大附加费 (Peak Oversize)
    "peak_unauthorized": 220,    # 旺季不可发附加费 (Peak Unauthorized)
    "oversize_fee": 130,         # 超大附加费 (Oversize)
    "ahs_fee": 20,               # 旺季额外超重超尺寸 (Peak AHS) - 占位值
    "unauthorized_fee": 1150,    # 不可发包裹 (Unauthorized)
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

# 出库费 / 自提费（四个等级展示表：仅展示，不参与运费计算）
# TODO：把你们真实的四档费用填进来（单位按你页面展示习惯：¥或$）
FEE_TABLE = {
    "T0": {"outbound_fee": "-", "pickup_fee": "-"},
    "T1": {"outbound_fee": "-", "pickup_fee": "-"},
    "T2": {"outbound_fee": "-", "pickup_fee": "-"},
    "T3": {"outbound_fee": "-", "pickup_fee": "-"},
}

# 仓库可用渠道（写死：严格按你最新描述；不可用不显示）
# - GOFO/GOFO-MT/UNIUNI：美西91730 + 美中
# - USPS-YSD、FedEx-YSD：美西 + 美中
# - XLmiles：仅美西91730
# - GOFO大件、FedEx-632：美西 + 美中 + 美东
# 注意：你未把 FedEx-ECO-MT 写进可用清单，因此这里不对任何仓库展示该渠道
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
    ],
    "CENTRAL": [
        "GOFO-报价",
        "GOFO-MT-报价",
        "UNIUNI-MT-报价",
        "USPS-YSD-报价",
        "FedEx-YSD-报价",
        "GOFO大件-GRO-报价",
        "FedEx-632-MT-报价",
    ],
    "EAST": [
        "GOFO大件-GRO-报价",
        "FedEx-632-MT-报价",
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
#   - 删除“计费逻辑说明”
#   - 新增：出库费/自提费四档表格（清晰可见）
#   - 附加费明细：统一命名+注释更清晰（前端 details 文案）
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
    .mini-table th { background:#f1f3f5; font-size:0.85rem; }
    .mini-table td { font-size:0.9rem; }
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

            <div class="mb-3">
              <label class="form-label">发货仓库 (仅决定可用渠道显示)</label>
              <select class="form-select" id="warehouse">
                <option value="WEST_91730">美西 - 91730</option>
                <option value="CENTRAL">美中</option>
                <option value="EAST">美东</option>
              </select>
              <div class="text-muted small mt-1">说明：选仓库后，仅展示该仓库可用渠道；不可用渠道不显示报价。</div>
            </div>

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
                <div><b>已包含燃油的报价：</b>GOFO-报价、GOFO-MT、UNIUNI-MT（这些渠道不额外叠加燃油）</div>
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

          <!-- 新增：出库费 / 自提费 四档表格（替换原“计费逻辑说明”） -->
          <div class="mt-3">
            <div class="fw-bold mb-2">出库费 / 自提费（四个等级报价表）</div>
            <div class="table-responsive">
              <table class="table table-sm table-bordered mini-table">
                <thead>
                  <tr>
                    <th width="15%">等级</th>
                    <th width="42%">出库费 (Outbound Fee)</th>
                    <th width="43%">自提费 (Pickup Fee)</th>
                  </tr>
                </thead>
                <tbody id="feeTableBody"></tbody>
              </table>
            </div>
            <div class="text-muted small">备注：该表仅展示仓内费用档位，不参与上方快递运费计算。</div>
          </div>

          <!-- 旺季/免责声明板块（仅展示说明，不影响计算） -->
          <div class="alert alert-warning mt-3 note-box">
            <div class="fw-bold mb-1">旺季附加费 / 注意事项（必读）</div>
            <div>① USPS Ground Advantage 2025 报价表的旺季附加费在报价表右侧，全名称：<b>2025旺季附加费-USPS Ground Advantage</b>，USPS-YSD 旺季费需按该表格独立查价并叠加。</div>
            <div>② 末端实际产生额外费用（复核尺寸不符/退货/其它附加费等）导致物流商向我司加收，我司将实报实销。</div>
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

  // 填充 出库费/自提费 四档表格
  (function renderFeeTable(){
    try{
      let tb = document.getElementById('feeTableBody');
      let ft = (DATA && DATA.fee_table) ? DATA.fee_table : {};
      let tiers = ['T0','T1','T2','T3'];
      let html = '';
      tiers.forEach(t=>{
        let o = (ft[t] && ft[t].outbound_fee !== undefined) ? ft[t].outbound_fee : '-';
        let p = (ft[t] && ft[t].pickup_fee !== undefined) ? ft[t].pickup_fee : '-';
        html += `<tr><td class="fw-bold">${t}</td><td>${o}</td><td>${p}</td></tr>`;
      });
      tb.innerHTML = html || `<tr><td colspan="3" class="text-muted">未配置</td></tr>`;
    }catch(e){}
  })();

  // 自动计算监听
  document.querySelectorAll('input[name="tier"]').forEach(r => {
    r.addEventListener('change', () => document.getElementById('btnCalc').click());
  });
  document.getElementById('warehouse').addEventListener('change', () => document.getElementById('btnCalc').click());

  // USPS 特殊拦截前缀
  const USPS_BLOCK = ['006','007','008','009','090','091','092','093','094','095','096','097','098','099','340','962','963','964','965','966','967','968','969','995','996','997','998','999'];

  // XLmiles 判定（仅用于合规性/明细标注；不改动基础报价表逻辑）
  function classifyXLmiles(pkg) {
    let d = [pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
    let L = d[0];
    let G = L + 2*(d[1]+d[2]);

    // OM: <=144", G<=225, <=200lb
    if (L <= 144 && G <= 225 && pkg.Wt <= 200) return { ok:true, type:"OM" };
    // OS: <=108", G<=165, <=150lb
    if (L <= 108 && G <= 165 && pkg.Wt <= 150) return { ok:true, type:"OS" };
    // AH: <=96", G<=130, <=150lb
    if (L <= 96 && G <= 130 && pkg.Wt <= 150) return { ok:true, type:"AH" };

    return { ok:false, type:"超限" };
  }

  const RULES = {
    // 哪些渠道“需要燃油”
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
      return 222;
    }
  };

  function standardize(l, w, h, du, wt, wu) {
    let L=parseFloat(l)||0, W=parseFloat(w)||0, H=parseFloat(h)||0, Weight=parseFloat(wt)||0;
    if(du==='cm'){L/=2.54;W/=2.54;H/=2.54} else if(du==='mm'){L/=25.4;W/=25.4;H/=25.4}
    if(wu==='kg')Weight/=0.453592; else if(wu==='oz')Weight/=16; else if(wu==='g')Weight/=453.592;
    return {L,W,H,Wt:Weight};
  }

  // 合规性一览（含 XLmiles）
  function check(pkg) {
    let d=[pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
    let L=d[0], G=L+2*(d[1]+d[2]);
    let h = '';

    const row = (name, cond, textOk, textBad) => {
      let bad = !!cond;
      let cls = bad ? 'bg-err' : 'bg-ok';
      let txt = bad ? textBad : textOk;
      return `<tr><td>${name}</td><td class="text-end"><span class="indicator ${cls}"></span>${txt}</td></tr>`;
    };

    // UNIUNI: 长>20, 围>50, 重>20
    let uFail = (L>20 || (L+d[1]+d[2])>50 || pkg.Wt>20);
    h += row('UNIUNI', uFail, '正常 (OK)', '超限(L>20 / Wt>20 / 围>50)');

    // USPS: 重>70, 围长>130, 长>30
    let usFail = (pkg.Wt>70 || L>30 || (L+(d[1]+d[2])*2)>130);
    h += row('USPS', usFail, '正常 (OK)', '超限(>70lb / L>30 / 围>130)');

    // FedEx: 重>150, 长>108, 围>165
    let fFail = (pkg.Wt>150 || L>108 || G>165);
    h += row('FedEx', fFail, '正常 (OK)', '不可发(>150lb 或超尺寸)');

    // GOFO大件: 重>150
    let gFail = (pkg.Wt>150);
    h += row('GOFO大件', gFail, '正常 (OK)', '超限(>150lb)');

    // XLmiles
    let xl = classifyXLmiles(pkg);
    h += row('XLmiles', !xl.ok, `可发:${xl.type}`, '超限(超过OM范围)');

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

    // 燃油费率
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

    Object.keys(DATA.tiers[tier]).forEach(ch => {
      if(!isChannelAvailable(ch)) return;

      let prices = DATA.tiers[tier][ch].prices;
      if(!prices || prices.length===0) return;

      // Zone 取值：FedEx-YSD 若缺失则用 632 兜底（同属 FedEx 标准算区）
      let zoneVal = CUR_ZONES[ch];
      if((zoneVal===null || zoneVal===undefined || zoneVal==='') && ch === 'FedEx-YSD-报价') {
        zoneVal = CUR_ZONES['FedEx-632-MT-报价'] || null;
        try { console.warn('[debug] FedEx-YSD zone missing, fallback to 632 zone=', zoneVal); } catch(e){}
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

      // 2) 匹配价格（FedEx-YSD：报价从 zone2 开始；若 zone1 则按 zone2 取价）
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
          // ✅ XLmiles：附加费明细必须标注清楚（仅做“明细标注”，不改变基础报价表取价）
          details.push(`XLmiles服务类型 (Service): ${xl.type}`);
          details.push(`XLmiles可用仓库: 仅美西91730`);
          // zone 组提示（明细标注）
          if(zoneVal==='1' || zoneVal==='2') details.push(`XLmiles分区组 (Zone Group): 1-2`);
          if(zoneVal==='3') details.push(`XLmiles分区组 (Zone Group): 3`);
        }
      }

      // 4) 费用叠加（明细命名统一、注释更清楚）
      let fees = {fuel:0, res:0, peak:0, other:0, sig:0};

      if(base > 0) {

        // 4.1 住宅地址费 Residential Fee（按渠道固定）
        if(isRes && DATA.res_fee_by_channel && DATA.res_fee_by_channel[ch] !== undefined) {
          fees.res = DATA.res_fee_by_channel[ch];
          details.push(`住宅地址费 (Residential): $${fees.res.toFixed(2)}`);
        }

        // 4.2 签名签收费 Signature（按渠道固定）
        if(DATA.signature_fee_by_channel && DATA.signature_fee_by_channel[ch] !== undefined) {
          fees.sig = DATA.signature_fee_by_channel[ch];
          details.push(`签名签收 (Direct/Indirect Signature): $${fees.sig.toFixed(2)}`);
        }

        // 4.3 FedEx-YSD / 632：超大/不可发 + 旺季逻辑（明细清晰标注）
        if(ch === 'FedEx-YSD-报价' || ch === 'FedEx-632-MT-报价') {
          let isUn = (L>108 || G>165 || pkg.Wt>150);
          let isOver = (L>96 || G>130);

          if(isUn) {
            fees.other += DATA.surcharges.unauthorized_fee;
            st="Unauthorized"; cls="text-danger fw-bold"; bg="table-danger";
            details.push(`不可发附加费 (Unauthorized): $${DATA.surcharges.unauthorized_fee.toFixed(2)}`);
          } else if(isOver) {
            fees.other += DATA.surcharges.oversize_fee;
            st="Oversize"; cls="text-warning fw-bold";
            details.push(`超大附加费 (Oversize): $${DATA.surcharges.oversize_fee.toFixed(2)}`);
          }

          if(isPeak) {
            let isAHS = (L>48 || dims[1]>30 || (L+2*(dims[1]+dims[2]))>105 || pkg.Wt>50);
            if(isAHS) {
              fees.peak += DATA.surcharges.ahs_fee;
              details.push(`旺季AHS (Peak AHS): $${DATA.surcharges.ahs_fee.toFixed(2)}`);
            }
            if(st.includes('Oversize')) {
              fees.peak += DATA.surcharges.peak_oversize;
              details.push(`旺季超大 (Peak Oversize): $${DATA.surcharges.peak_oversize.toFixed(2)}`);
            }
            if(st.includes('Unauthorized')) {
              fees.peak += DATA.surcharges.peak_unauthorized;
              details.push(`旺季不可发 (Peak Unauthorized): $${DATA.surcharges.peak_unauthorized.toFixed(2)}`);
            }
            if(isRes && DATA.res_fee_by_channel && DATA.res_fee_by_channel[ch] !== undefined) {
              fees.peak += DATA.surcharges.peak_res;
              details.push(`旺季住宅 (Peak Residential): $${DATA.surcharges.peak_res.toFixed(2)}`);
            }
          }
        } else {
          // 4.4 其他渠道：保持原有“超大/不可发”判定（仅明细标注，不引入额外规则）
          if(st !== "超规不可发" && st !== "无折扣 (Std Rate)") {
            let isUn = (L>108 || G>165 || pkg.Wt>150);
            let isOver = (L>96 || G>130);

            if(isUn) {
              fees.other += DATA.surcharges.unauthorized_fee;
              st="Unauthorized"; cls="text-danger fw-bold"; bg="table-danger";
              details.push(`不可发附加费 (Unauthorized): $${DATA.surcharges.unauthorized_fee.toFixed(2)}`);
            } else if(isOver) {
              fees.other += DATA.surcharges.oversize_fee;
              st="Oversize"; cls="text-warning fw-bold";
              details.push(`超大附加费 (Oversize): $${DATA.surcharges.oversize_fee.toFixed(2)}`);
            }
          }
        }

        // 4.5 USPS 旺季：按表格查价叠加（明细标注）
        if(isPeak && ch === 'USPS-YSD-报价') {
          let p = getUspsPeakFee(cWt, zoneVal);
          if(p > 0) {
            fees.peak += p;
            details.push(`USPS旺季附加费 (Peak by Table): $${p.toFixed(2)}`);
          } else {
            details.push(`USPS旺季附加费 (Peak by Table): $0.00`);
          }
        }

        // 4.6 燃油 Fuel（按分组：UNIFIED / USPS / NONE）
        let fg = RULES.fuelGroup(ch);
        if(fg === 'UNIFIED') {
          if(ch === 'GOFO大件-GRO-报价') {
            let subTotal = base + fees.res + fees.peak + fees.other + fees.sig;
            fees.fuel = subTotal * unifiedFuel;
            details.push(`燃油 (Fuel, on Base+Surcharges) ${(unifiedFuel*100).toFixed(1)}%: $${fees.fuel.toFixed(2)}`);
          } else {
            fees.fuel = base * unifiedFuel;
            details.push(`燃油 (Fuel, on Base) ${(unifiedFuel*100).toFixed(1)}%: $${fees.fuel.toFixed(2)}`);
          }
        } else if(fg === 'USPS') {
          fees.fuel = base * uspsFuel;
          details.push(`燃油 (Fuel, USPS) ${(uspsFuel*100).toFixed(1)}%: $${fees.fuel.toFixed(2)}`);
        } else {
          // NONE：报价已含燃油，不额外加
        }
      }

      let tot = base + fees.fuel + fees.res + fees.peak + fees.other + fees.sig;

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
#   - USPS 旺季表：避免 iloc 越界（scan_n）
#   - 增加最小排查日志：仓库渠道映射是否命中 tiers
# ==========================================
def safe_float(val):
    """兼容 $ / ￥ / ¥ / 逗号，并尽量从字符串中提取数字"""
    try:
        if pd.isna(val) or val == "" or str(val).strip().lower() == "nan":
            return 0.0
        s = str(val).strip()
        s = s.replace(",", "").replace("$", "").replace("￥", "").replace("¥", "")
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
        scan_n = min(100, len(df))
        for i in range(scan_n):
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
    USPS 旺季附加费表：从 USPS-YSD-报价 副本右侧表格读取
    兼容解析：识别表头行，然后按 weight + zone 列抽取
    """
    print("\n--- 1.2 解析 USPS 旺季附加费表格（按表格查价） ---")
    path = os.path.join(DATA_DIR, TIER_FILES["T0"])
    if not os.path.exists(path):
        return []

    df = get_sheet_by_name(path, ["USPS", "YSD"])
    if df is None:
        return []

    df = df.fillna("")

    # 最小排查日志（1行）
    print(f"    > USPS旺季表sheet维度: rows={len(df)}, cols={df.shape[1] if hasattr(df,'shape') else 'NA'}")

    h_row = None
    scan_n = min(80, len(df))
    for i in range(scan_n):
        row_str = " ".join(df.iloc[i].astype(str).values).lower().replace(" ", "")
        if (("旺季附加费" in row_str) or ("2025" in row_str)) and (("zone" in row_str) or ("分区" in row_str)) and (("weight" in row_str) or ("重量" in row_str) or ("lb" in row_str)):
            h_row = i
            break

    if h_row is None:
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
                scan_n = min(80, len(df))
                for i in range(scan_n):
                    row_str = " ".join(df.iloc[i].astype(str).values).lower()
                    has_zone = ("zone" in row_str or "分区" in row_str)
                    has_weight = ("weight" in row_str or "lb" in row_str or "重量" in row_str)
                    if has_zone and has_weight:
                        h_row = i
                        break

                headers = df.iloc[h_row].astype(str).str.lower().tolist()
                w_idx = -1
                z_map = {}

                if ch_key == "XLmiles-报价":
                    for i, v in enumerate(headers):
                        vv = str(v).lower().replace(" ", "")
                        if w_idx == -1 and (("weight" in vv) or ("lb" in vv) or ("重量" in vv)):
                            w_idx = i
                        if ("zone" in vv or "分区" in vv) and (("1-2" in vv) or ("1~2" in vv) or ("1/2" in vv) or (("1" in vv) and ("2" in vv))):
                            z_map["1"] = i
                            z_map["2"] = i
                        if ("zone" in vv or "分区" in vv) and re.search(r"(?:zone|分区)\s*~?\s*3", vv):
                            z_map["3"] = i

                if w_idx == -1:
                    for i, v in enumerate(headers):
                        vv = str(v).lower()
                        if ("weight" in vv or "lb" in vv or "重量" in vv) and w_idx == -1:
                            w_idx = i

                if not z_map:
                    for i, v in enumerate(headers):
                        vv = str(v).lower()
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

def audit_warehouse_channel_mapping(tiers_data):
    """
    排查：仓库-渠道映射是否对应正确
    只打印排查日志，不改计算逻辑
    """
    print("\n--- 2.9 排查：仓库-渠道可用性映射 ---")
    try:
        # 以 T3 为主做“是否存在该渠道数据”的校验（缺失就提示）
        base_tier = "T3" if ("T3" in tiers_data) else (list(tiers_data.keys())[0] if tiers_data else None)
        exist = set(tiers_data.get(base_tier, {}).keys()) if base_tier else set()

        for wh, chs in WAREHOUSE_CHANNELS.items():
            miss = [c for c in chs if c not in exist]
            extra = []  # 这里不做反向推断，避免误报
            print(f"    > {wh}: {len(chs)} 个渠道")
            if miss:
                print(f"      ⚠️ 映射内但报价数据缺失({base_tier}): {miss}")
        # 关键规则复核（XLmiles 仅 WEST_91730）
        xl_in_west = "XLmiles-报价" in WAREHOUSE_CHANNELS.get("WEST_91730", [])
        xl_in_other = any("XLmiles-报价" in WAREHOUSE_CHANNELS.get(k, []) for k in ["CENTRAL", "EAST"])
        print(f"    > 规则复核: XLmiles 仅美西91730 -> west={xl_in_west}, other={xl_in_other}")
    except Exception as e:
        print(f"    > 排查失败: {e}")

if __name__ == "__main__":
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    zip_db = load_zip_db()
    tiers = load_tiers()
    audit_warehouse_channel_mapping(tiers)

    final = {
        "zip_db": zip_db,
        "tiers": tiers,
        "surcharges": GLOBAL_SURCHARGES,
        "res_fee_by_channel": RES_FEE_BY_CHANNEL,
        "signature_fee_by_channel": SIGNATURE_FEE_BY_CHANNEL,
        "warehouse_channels": WAREHOUSE_CHANNELS,
        "usps_peak_table": load_usps_peak_table(),
        "fee_table": FEE_TABLE,  # ✅ 新增：出库费/自提费表格（仅展示）
    }

    print("\n--- 3. 生成网页 ---")
    try:
        js_str = json.dumps(final, allow_nan=False)
    except:
        js_str = json.dumps(final).replace("NaN", "0")

    html = HTML_TEMPLATE.replace("__JSON_DATA__", js_str)

    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ 完成！本次仅修复/改动以下问题点：")
    print("  - XLmiles（仅美西91730可用）：附加费明细增加清晰标注（服务类型/可用仓库/分区组/签名费等）")
    print("  - 仓库-渠道映射按你最新清单重排，并新增排查日志（不改计算逻辑）")
    print("  - 附加费明细命名统一：Residential / Signature / Fuel / Peak / Oversize / Unauthorized / AHS")
    print("  - 删除“计费逻辑说明”，替换为“出库费/自提费四档报价表”（仅展示，不参与运费计算）")
