import pandas as pd
import json
import re
import os
import warnings
import subprocess
from datetime import datetime

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

# 州名映射
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

WAREHOUSE_DB = {
    "60632": {"name": "SureGo美中芝加哥-60632仓", "region": "CENTRAL"},
    "91730": {"name": "SureGo美西库卡蒙格-91730新仓", "region": "WEST"},
    "91752": {"name": "SureGo美西米拉罗马-91752仓", "region": "WEST"},
    "08691": {"name": "SureGo美东新泽西-08691仓", "region": "EAST"},
    "06801": {"name": "SureGo美东贝塞尔-06801仓", "region": "EAST"},
    "11791": {"name": "SureGo美东长岛-11791仓", "region": "EAST"},
    "07032": {"name": "SureGo美东新泽西-07032仓", "region": "EAST"},
    "63461": {"name": "SureGo退货检测-美中密苏里63461退货仓", "region": "CENTRAL"}
}

# 渠道配置
CHANNEL_CONFIG = {
    "GOFO-报价": {
        "keywords": ["GOFO", "报价"], "exclude": ["MT", "UNIUNI", "大件"],
        "allow_wh": ["91730", "60632"], "fuel_mode": "none", "zone_source": "gofo",
        "fees": {"res": 0, "sig": 0} 
    },
    "GOFO-MT-报价": {
        "keywords": ["GOFO", "UNIUNI", "MT"], "sheet_side": "left",
        "allow_wh": ["91730", "60632"], "fuel_mode": "standard", "zone_source": "gofo",
        "fees": {"res": 0, "sig": 0}
    },
    "UNIUNI-MT-报价": {
        "keywords": ["GOFO", "UNIUNI", "MT"], "sheet_side": "right",
        "allow_wh": ["91730", "60632"], "fuel_mode": "none", "zone_source": "general",
        "fees": {"res": 0, "sig": 0}
    },
    "USPS-YSD-报价": {
        "keywords": ["USPS", "YSD"], "allow_wh": ["91730", "91752", "60632"], 
        "fuel_mode": "none", "zone_source": "general", "fees": {"res": 0, "sig": 0}, "no_peak": True 
    },
    "FedEx-632-MT-报价": {
        "keywords": ["632"], "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
        "fuel_mode": "discount_85", "zone_source": "general", "fees": {"res": 2.61, "sig": 4.37}
    },
    "FedEx-MT-超大包裹-报价": {
        "keywords": ["超大包裹"], "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
        "fuel_mode": "discount_85", "zone_source": "general", "fees": {"res": 2.61, "sig": 4.37}
    },
    "FedEx-ECO-MT报价": {
        "keywords": ["ECO", "MT"], "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
        "fuel_mode": "included", "zone_source": "general", "fees": {"res": 0, "sig": 0}
    },
    "FedEx-MT-危险品-报价": {
        "keywords": ["危险品"], "allow_wh": ["60632", "08691", "06801", "11791", "07032"], 
        "fuel_mode": "standard", "zone_source": "general", "fees": {"res": 3.32, "sig": 9.71}
    },
    "GOFO大件-MT-报价": {
        "keywords": ["GOFO大件", "MT"], "allow_wh": ["91730", "91752", "08691", "06801", "11791", "07032"], 
        "fuel_mode": "standard", "zone_source": "gofo", "fees": {"res": 2.93, "sig": 0} 
    },
    "XLmiles-报价": {
        "keywords": ["XLmiles"], "allow_wh": ["91730"], 
        "fuel_mode": "none", "zone_source": "xlmiles", "fees": {"res": 0, "sig": 10.20}
    }
}

# ==========================================
# 2. HTML/JS
# ==========================================
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>业务员报价助手 (V2026.10 终极修复版)</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background-color: #f4f7f6; font-family: 'Segoe UI', sans-serif; }
    .header-bar { background: #222; color: #fff; padding: 15px 0; border-bottom: 4px solid #fd7e14; margin-bottom: 20px; }
    .card { border: none; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-radius: 10px; }
    .card-header { background-color: #fff; font-weight: 700; border-bottom: 1px solid #eee; }
    .price-main { font-size: 1.4rem; font-weight: 800; color: #d63384; }
    .warn-box { background: #fff3cd; border: 1px solid #ffeeba; color: #856404; padding: 12px; border-radius: 6px; font-size: 0.85rem; margin-bottom: 15px; }
    .compliance-box { background: #e9ecef; border-radius: 6px; padding: 10px; margin-top: 15px; font-size: 0.85rem; }
    .loc-box { margin-top: 5px; font-size: 0.85rem; }
    .tag-gofo { background: #d1e7dd; color: #0f5132; padding: 3px 8px; border-radius: 4px; border: 1px solid #badbcc; display: block; margin-bottom: 4px; }
    .tag-fedex { background: #cfe2ff; color: #084298; padding: 3px 8px; border-radius: 4px; border: 1px solid #b6d4fe; display: block; }
    .status-ok { color: #198754; font-weight: 700; }
    .status-err { color: #dc3545; font-weight: 700; }
  </style>
</head>
<body>

<div class="header-bar">
  <div class="container d-flex justify-content-between align-items-center">
    <div><h4 class="m-0 fw-bold">📦 业务员报价助手</h4><div class="small opacity-75">V2026.10 | XLmiles修复 | 邮编双显</div></div>
    <div class="text-end d-none d-md-block"><span class="badge bg-warning text-dark">T0-T3 实时</span></div>
  </div>
</div>

<div class="container pb-5">
  <div class="row g-4">
    <div class="col-lg-4">
      <div class="card h-100">
        <div class="card-header">1. 基础信息</div>
        <div class="card-body">
          <form id="calcForm">
            <div class="mb-3">
              <label class="form-label small fw-bold text-muted">发货仓库</label>
              <select class="form-select" id="whSelect"></select>
              <div class="form-text small text-end text-primary" id="whRegion"></div>
            </div>

            <div class="mb-3">
              <label class="form-label small fw-bold text-muted">客户等级</label>
              <div class="btn-group w-100" role="group">
                <input type="radio" class="btn-check" name="tier" id="t0" value="T0"><label class="btn btn-outline-dark" for="t0">T0</label>
                <input type="radio" class="btn-check" name="tier" id="t1" value="T1"><label class="btn btn-outline-dark" for="t1">T1</label>
                <input type="radio" class="btn-check" name="tier" id="t2" value="T2"><label class="btn btn-outline-dark" for="t2">T2</label>
                <input type="radio" class="btn-check" name="tier" id="t3" value="T3" checked><label class="btn btn-outline-dark" for="t3">T3</label>
              </div>
            </div>

            <div class="bg-light p-2 rounded border mb-3">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <label class="form-label small fw-bold text-muted m-0">燃油费率 (%)</label>
                    <span class="badge bg-secondary" style="font-size:0.65rem">MT系列</span>
                </div>
                <div class="input-group input-group-sm">
                    <input type="number" class="form-control fw-bold text-primary" id="fuelInput" value="16.0" step="0.01">
                    <span class="input-group-text">%</span>
                </div>
                <div class="form-text small text-muted" style="font-size:0.7rem">
                  * 仅 FedEx-632/超大件 享85折。
                </div>
            </div>

            <div class="row g-2 mb-3">
              <div class="col-6">
                <label class="form-label small fw-bold text-muted">邮编 (Zip)</label>
                <input type="text" class="form-control" id="zipCode" placeholder="5位数字">
              </div>
              <div class="col-6">
                <label class="form-label small fw-bold text-muted">地址类型</label>
                <select class="form-select" id="addrType">
                  <option value="res">🏠 住宅</option>
                  <option value="com">🏢 商业</option>
                </select>
              </div>
              <div class="col-12" id="locDisplay"></div>
            </div>

            <div class="form-check form-switch mb-3">
              <input class="form-check-input" type="checkbox" id="sigToggle">
              <label class="form-check-label small fw-bold" for="sigToggle">签名服务 (Signature)</label>
            </div>

            <div class="bg-light p-3 rounded border">
              <label class="form-label small fw-bold text-muted mb-2">包裹规格 (Inch / Lb)</label>
              <div class="row g-2 mb-2">
                <div class="col-4"><input type="number" class="form-control form-control-sm" id="dimL" placeholder="长 L"></div>
                <div class="col-4"><input type="number" class="form-control form-control-sm" id="dimW" placeholder="宽 W"></div>
                <div class="col-4"><input type="number" class="form-control form-control-sm" id="dimH" placeholder="高 H"></div>
              </div>
              <div class="input-group input-group-sm">
                <span class="input-group-text">实重</span>
                <input type="number" class="form-control" id="weight" placeholder="LBS">
              </div>
            </div>

            <div class="compliance-box" id="complianceBox" style="display:none;">
              <div class="fw-bold mb-1 text-danger">⚠️ 规格预检</div>
              <ul class="mb-0 ps-3" id="complianceList"></ul>
            </div>

            <button type="button" class="btn btn-primary w-100 mt-4 fw-bold py-2" id="btnCalc">计算报价 (Calculate)</button>
          </form>
        </div>
      </div>
    </div>

    <div class="col-lg-8">
      <div class="card h-100">
        <div class="card-header d-flex justify-content-between align-items-center">
          <span>📊 测算结果</span>
          <span class="badge bg-warning text-dark" id="resTierBadge">T3</span>
        </div>
        <div class="card-body">
          <div class="warn-box">
            <strong>📢 计费规则说明：</strong><br>
            1. <b>燃油费</b>：FedEx-632/超大包裹(85折)；FedEx-ECO-MT(含油)；其他MT(全额)。<br>
            2. <b>邮编逻辑</b>：<br>
               &nbsp;&nbsp; ● <b>GOFO</b>：查自营表(WE/EA/CE)与仓库匹配。<br>
               &nbsp;&nbsp; ● <b>FedEx/USPS</b>：根据 <b>发货仓库</b> 动态计算分区。<br>
            3. <b>XLmiles</b>：按尺寸判定 AH/OS/OM，包含Zone 1/2/3/6。<br>
            4. <b>偏远检查</b>：自动读取 FedEx PDF 偏远库。
          </div>

          <div class="alert alert-info py-2 small" id="pkgInfo">请在左侧录入数据...</div>

          <div class="table-responsive">
            <table class="table table-hover align-middle">
              <thead class="table-light small text-secondary">
                <tr>
                  <th width="20%">渠道</th>
                  <th width="8%">Zone</th>
                  <th width="10%">计费重</th>
                  <th width="12%">基础运费</th>
                  <th width="25%">附加费明细</th>
                  <th width="15%" class="text-end">总费用</th>
                  <th width="10%" class="text-center">状态</th>
                </tr>
              </thead>
              <tbody id="resBody">
                <tr><td colspan="7" class="text-center py-4 text-muted">暂无结果</td></tr>
              </tbody>
            </table>
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

  // 1. 邮编双显
  document.getElementById('zipCode').addEventListener('input', function() {
    let zip = this.value.trim();
    let display = document.getElementById('locDisplay');
    if(zip.length === 5) {
        let html = '';
        // GOFO
        if(DATA.gofo_zips && DATA.gofo_zips[zip]) {
            let g = DATA.gofo_zips[zip];
            html += `<div class="tag-gofo">🟢 [GOFO表] ${g.city}, ${g.state} (${g.cn_state}) - 区:${g.region}</div>`;
        }
        // FedEx
        let fedexInfo = "通用地区";
        if(DATA.fedex_das_remote && DATA.fedex_das_remote.includes(zip)) fedexInfo = "⚠️ FedEx 偏远 (Remote)";
        else if(DATA.fedex_das_extended && DATA.fedex_das_extended.includes(zip)) fedexInfo = "⚠️ FedEx 扩展 (Extended)";
        
        html += `<div class="tag-fedex">🔵 [FedEx/通用] ${fedexInfo}</div>`;
        display.innerHTML = `<div class="loc-box">${html}</div>`;
    } else {
        display.innerHTML = '';
    }
  });

  // 2. 燃油
  (function initFuel() {
    let maxFuel = 0;
    if(DATA.tiers && DATA.tiers.T3) {
        Object.values(DATA.tiers.T3).forEach(ch => {
            if(ch.fuel_rate && ch.fuel_rate > maxFuel) maxFuel = ch.fuel_rate;
        });
    }
    if(maxFuel > 0) document.getElementById('fuelInput').value = (maxFuel * 100).toFixed(2);
  })();

  // 3. 规格校验
  function getXLService(L, W, H, Wt) {
    let dims = [L, W, H].sort((a,b)=>b-a);
    let maxL = dims[0];
    let girth = maxL + 2*(dims[1] + dims[2]);
    if (maxL <= 96 && girth <= 130 && Wt <= 150) return { code: "AH", name: "AH大件" };
    if (maxL <= 108 && girth <= 165 && Wt <= 150) return { code: "OS", name: "OS大件" };
    if (maxL <= 144 && girth <= 225 && Wt <= 200) return { code: "OM", name: "OM超限" };
    return { code: null, name: "超XL规格" };
  }

  function checkCompliance(pkg) {
    let dims = [pkg.L, pkg.W, pkg.H].sort((a,b)=>b-a);
    let L = dims[0], G = dims[0] + 2*(dims[1] + dims[2]);
    let msgs = [];
    if (pkg.Wt > 150) msgs.push("超150lb (限XLmiles)");
    if (L > 108) msgs.push("长>108in (FedEx超长)");
    
    let status = {
      uniuni: (pkg.Wt > 20 || L>20) ? "NO" : "OK",
      usps: (pkg.Wt > 70 || G > 130) ? "NO" : "OK",
      xl: (pkg.Wt > 200 || L > 144 || G > 225) ? "NO" : "OK"
    };
    return { msgs, status };
  }

  function updateComplianceUI() {
    let L = parseFloat(document.getElementById('dimL').value)||0;
    let W = parseFloat(document.getElementById('dimW').value)||0;
    let H = parseFloat(document.getElementById('dimH').value)||0;
    let Wt = parseFloat(document.getElementById('weight').value)||0;
    if(L>0 && Wt>0) {
      let res = checkCompliance({L,W,H,Wt});
      let html = "";
      if(res.msgs.length > 0) html += `<li class="fw-bold">${res.msgs.join(', ')}</li>`;
      html += `<li>UniUni: ${res.status.uniuni}</li><li>USPS: ${res.status.usps}</li><li>XLmiles: ${res.status.xl}</li>`;
      document.getElementById('complianceList').innerHTML = html;
      document.getElementById('complianceBox').style.display = 'block';
    } else {
      document.getElementById('complianceBox').style.display = 'none';
    }
  }
  ['dimL','dimW','dimH','weight'].forEach(id => document.getElementById(id).addEventListener('input', updateComplianceUI));

  // 4. 初始化
  const whSelect = document.getElementById('whSelect');
  Object.keys(DATA.warehouses).forEach(code => {
    let opt = document.createElement('option');
    opt.value = code;
    opt.text = DATA.warehouses[code].name;
    whSelect.appendChild(opt);
  });
  whSelect.addEventListener('change', () => {
    document.getElementById('whRegion').innerText = `区域: ${DATA.warehouses[whSelect.value].region}`;
    document.getElementById('resBody').innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">仓库已切换，请点击计算</td></tr>';
  });
  if(whSelect.options.length > 0) whSelect.dispatchEvent(new Event('change'));

  // 5. Zone 计算
  function calcZone(destZip, originZip, conf) {
    if(!destZip || destZip.length < 3) return 8;
    let d = parseInt(destZip.substring(0,3));
    let whRegion = DATA.warehouses[originZip].region;

    if(conf.zone_source === 'gofo') {
        if(DATA.gofo_zips && DATA.gofo_zips[destZip]) {
            let zReg = DATA.gofo_zips[destZip].region; 
            if(whRegion=='WEST' && zReg=='WE') return 2;
            if(whRegion=='CENTRAL' && zReg=='CE') return 2;
            if(whRegion=='EAST' && zReg=='EA') return 2;
            return 8; 
        }
        return 8;
    }
    
    // XLmiles (Special Zone 1,2,3,6 logic or simple mapping)
    if(conf.zone_source === 'xlmiles') {
        // XLmiles usually only from WEST (91730)
        // Simply map standard zones to XL zones: 
        // 2->2, 3->3, 4->3, 5->6, 6->6, 7->6, 8->6 
        // Logic simplified for demo, you might need exact table
        if(d >= 900 && d <= 935) return 2;
        if(d >= 936 && d <= 994) return 3;
        return 6; 
    }

    // Standard FedEx/USPS
    if(whRegion === 'WEST') {
      if(d >= 900 && d <= 935) return 2; 
      if(d >= 936 && d <= 994) return 4;
      if(d >= 800 && d <= 899) return 5;
      if(d >= 0 && d <= 200) return 8;
      return 7;
    }
    if(whRegion === 'EAST') {
      if(d >= 0 && d <= 199) return 2;
      if(d >= 200 && d <= 299) return 4; 
      if(d >= 900 && d <= 999) return 8;
      return 6;
    }
    if(whRegion === 'CENTRAL') {
       if(d >= 600 && d <= 629) return 2;
       if(d >= 400 && d <= 599) return 4;
       if(d >= 900 && d <= 999) return 7;
       if(d >= 0 && d <= 200) return 6;
       return 5;
    }
    return 8;
  }

  // 6. 计算
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
    let dimWt = (pkg.L * pkg.W * pkg.H) / 222;
    document.getElementById('pkgInfo').innerHTML = 
      `<b>Pkg:</b> ${pkg.L}x${pkg.W}x${pkg.H}" | 实重:${pkg.Wt} | 体积重:${dimWt.toFixed(2)}`;

    const tbody = document.getElementById('resBody');
    tbody.innerHTML = '';

    let comp = checkCompliance(pkg);

    Object.keys(DATA.channels).forEach(chName => {
      const conf = DATA.channels[chName];
      if(!conf.allow_wh.includes(whCode)) return;

      if(chName.includes("UNIUNI") && comp.status.uniuni.startsWith("NO")) return;
      if(chName.includes("USPS") && comp.status.usps.startsWith("NO")) return;
      if(chName.includes("XLmiles") && comp.status.xl.startsWith("NO")) return;
      if(chName.includes("FedEx") && !chName.includes("超大") && (pkg.Wt > 150 || pkg.L > 108)) return;

      let finalWt = Math.max(pkg.Wt, dimWt);
      if(!chName.includes("XLmiles")) finalWt = Math.ceil(finalWt);

      let zone = calcZone(zip, whCode, conf);
      let svcTag = "";
      let priceList = (DATA.tiers[tier][chName] || {}).prices || [];
      let basePrice = 0;

      // XLmiles Special Lookup
      if (chName.includes("XLmiles")) {
        let xl = getXLService(pkg.L, pkg.W, pkg.H, pkg.Wt);
        svcTag = `<br><small class="text-primary">${xl.name}</small>`;
        
        // XLmiles JSON struct: [{service: 'AH', w: 70, 1: 26.64...}, ...]
        // Filter by service type first!
        let row = priceList.find(r => r.service === xl.code && r.w >= finalWt - 0.001);
        if(row) basePrice = row[zone] || row[6] || 0; // Fallback Zone 6
      } else {
        // Standard Lookup
        let row = priceList.find(r => r.w >= finalWt - 0.001);
        if(row) basePrice = row[zone] || row[8] || 0;
      }

      if(basePrice <= 0) return;

      let surcharges = 0;
      let details = [];

      if(isRes && conf.fees.res > 0) {
        surcharges += conf.fees.res;
        details.push(`住宅 $${conf.fees.res}`);
      }
      if(sigOn && conf.fees.sig > 0) {
        surcharges += conf.fees.sig;
        details.push(`签名 $${conf.fees.sig}`);
      }

      if(conf.fuel_mode !== 'none' && conf.fuel_mode !== 'included') {
        let rate = fuelRateInput / 100;
        let tag = "";
        if (conf.fuel_mode === 'discount_85') {
            rate = rate * 0.85; 
            tag = " (85折)";
        }
        let fuelAmt = (basePrice + surcharges) * rate;
        surcharges += fuelAmt;
        details.push(`燃油${tag} ${(rate*100).toFixed(2)}%: $${fuelAmt.toFixed(2)}`);
      } else if (conf.fuel_mode === 'included') {
        details.push(`燃油: 已含`);
      }

      let total = basePrice + surcharges;

      tbody.innerHTML += `
        <tr>
          <td class="fw-bold text-start">${chName} ${svcTag}</td>
          <td><span class="badge bg-light text-dark border">Z${zone}</span></td>
          <td>${finalWt}</td>
          <td>$${basePrice.toFixed(2)}</td>
          <td class="small text-muted" style="line-height:1.2">${details.join('<br>') || '-'}</td>
          <td class="text-end price-main">$${total.toFixed(2)}</td>
          <td class="text-center"><span class="status-ok">✔</span></td>
        </tr>
      `;
    });
    
    if(tbody.innerHTML === '') {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-danger">无可用报价</td></tr>`;
    }
  };
</script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# ==========================================
# 3. 后端处理 (PDF读取 + GOFO表扫描)
# ==========================================

def clean_num(val):
    if pd.isna(val): return 0.0
    s = str(val).replace('$', '').replace(',', '').strip()
    try:
        return float(s)
    except:
        return 0.0

def find_sheet_name(xl, keywords, exclude_keywords=None):
    for sheet in xl.sheet_names:
        s_upper = sheet.upper().replace(" ", "")
        if not all(k.upper() in s_upper for k in keywords):
            continue
        if exclude_keywords and any(e.upper() in s_upper for e in exclude_keywords):
            continue
        return sheet
    return None

def extract_fuel_rate(xl):
    for sheet in xl.sheet_names:
        if "MT" in sheet.upper(): 
            try:
                df = pd.read_excel(xl, sheet_name=sheet, header=None)
                for r in range(min(150, df.shape[0])):
                    for c in range(df.shape[1]):
                        val = str(df.iloc[r, c])
                        if "燃油附加费" in val:
                            if c + 1 < df.shape[1]:
                                rate_val = str(df.iloc[r, c+1]).replace('%', '').strip()
                                try:
                                    f = float(rate_val)
                                    if f > 1: f = f / 100.0
                                    return f
                                except: pass
            except: pass
    return 0.0

def load_gofo_zip_db(tier_file):
    db = {}
    path = os.path.join(DATA_DIR, tier_file)
    if not os.path.exists(path): return db
    try:
        xl = pd.ExcelFile(path)
        sheet_name = find_sheet_name(xl, ["GOFO", "报价"], ["UNIUNI", "MT"])
        if not sheet_name: return db
        df = pd.read_excel(xl, sheet_name=sheet_name, header=None)
        
        start_row = -1
        cols = {}
        for r in range(min(200, df.shape[0])):
            row_vals = [str(x).strip() for x in df.iloc[r].values]
            if "目的地邮编" in row_vals or "GOFO_大区" in row_vals:
                start_row = r
                for c, v in enumerate(row_vals):
                    if "邮编" in v: cols['zip'] = c
                    elif "城市" in v: cols['city'] = c
                    elif "省州" in v: cols['state'] = c
                    elif "大区" in v: cols['region'] = c
                break
        
        if start_row != -1 and 'zip' in cols:
            for r in range(start_row+1, len(df)):
                try:
                    raw_zip = str(df.iloc[r, cols['zip']])
                    z = raw_zip.split('.')[0].strip().zfill(5)
                    if len(z) == 5 and z.isdigit():
                        db[z] = {
                            "city": str(df.iloc[r, cols.get('city', -1)]).strip(),
                            "state": str(df.iloc[r, cols.get('state', -1)]).strip(),
                            "region": str(df.iloc[r, cols.get('region', -1)]).strip(),
                            "cn_state": US_STATES_CN.get(str(df.iloc[r, cols.get('state', -1)]).strip(), "")
                        }
                except: continue
        print(f"  [Info] GOFO Zip DB loaded: {len(db)} entries")
    except Exception as e:
        print(f"  [Err] Failed to load GOFO Zip DB: {e}")
    return db

def load_fedex_pdf_zips():
    remote_zips = set()
    extended_zips = set()
    pdf_files = ["FGE_DAS_Contiguous_Extended_Alaska_Hawaii_2025.pdf", "FGE_DAS_Zip_Code_Changes_2025.pdf"]
    
    for pdf in pdf_files:
        path = os.path.join(DATA_DIR, pdf)
        if not os.path.exists(path): continue
        try:
            txt = subprocess.check_output(["pdftotext", path, "-"], stderr=subprocess.DEVNULL).decode('utf-8')
            zips = re.findall(r'\b\d{5}\b', txt)
            for z in zips: remote_zips.add(z) # 简化：全部视为Remote
        except:
            print(f"  [Warn] PDF read failed: {pdf}")
    return list(remote_zips), list(extended_zips)

def extract_prices(df, split_side=None, channel_name=""):
    if df is None: return []
    
    # === XLmiles 专用解析器 ===
    if "XLmiles" in channel_name:
        prices = []
        # XLmiles 结构: Col 0=Service, Col 2=Weight, Col 3-6=Zone
        # 扫描前20行找 Header
        h_row = -1
        z_map = {}
        for r in range(20):
            row_vals = [str(x).lower() for x in df.iloc[r].values]
            if any("zone" in x for x in row_vals):
                h_row = r
                for c, v in enumerate(row_vals):
                    m = re.search(r'zone\D*(\d+)', v)
                    if m: z_map[int(m.group(1))] = c
                break
        
        if h_row == -1 or not z_map: return []
        
        current_service = "AH" # 默认
        for r in range(h_row+1, len(df)):
            try:
                # 识别服务类型
                svc_raw = str(df.iloc[r, 0])
                if "AH" in svc_raw: current_service = "AH"
                elif "OS" in svc_raw: current_service = "OS"
                elif "OM" in svc_raw: current_service = "OM"
                
                # 识别重量范围 (0<重量<=70) -> 取70
                w_raw = str(df.iloc[r, 2])
                nums = re.findall(r'(\d+)', w_raw)
                if not nums: continue
                w_val = float(nums[-1]) # 取最后一个数字作为上限
                
                entry = {'service': current_service, 'w': w_val}
                for z, c in z_map.items():
                    p = clean_num(df.iloc[r, c])
                    if p > 0: entry[z] = p
                
                prices.append(entry)
            except: continue
        return prices

    # === 标准渠道解析器 ===
    total_cols = df.shape[1]
    c_start, c_end = 0, total_cols
    
    weight_indices = []
    for c in range(total_cols):
        for r in range(50):
            val = str(df.iloc[r, c]).lower()
            if "weight" in val or "重量" in val:
                if c not in weight_indices: weight_indices.append(c)
                break
    weight_indices.sort()
    
    if split_side == 'left':
        if len(weight_indices) > 0:
            c_end = weight_indices[1] if len(weight_indices) > 1 else total_cols
    elif split_side == 'right':
        if len(weight_indices) > 1:
            c_start = weight_indices[1]
        else:
            return [] 

    h_row = -1
    w_col = -1
    z_map = {}

    for r in range(200): 
        row_vals = [str(x).lower() for x in df.iloc[r, c_start:c_end].values]
        has_weight = any('weight' in x or '重量' in x for x in row_vals)
        has_zone = any('zone' in x for x in row_vals)
        if has_weight and has_zone:
            h_row = r
            break
    
    if h_row == -1: return []

    row_dat = df.iloc[h_row]
    for c in range(c_start, c_end):
        if c >= total_cols: break
        val = str(row_dat[c]).strip().lower()
        if ('weight' in val or '重量' in val) and w_col == -1: w_col = c
        m = re.search(r'zone[\D]*(\d+)', val)
        if m: z_map[int(m.group(1))] = c

    if w_col == -1 or not z_map: return []

    prices = []
    for r in range(h_row + 1, len(df)):
        try:
            w_raw = df.iloc[r, w_col]
            w_str = str(w_raw).lower().strip()
            nums = re.findall(r'[\d\.]+', w_str)
            if not nums: continue
            w_val = float(nums[0])
            if 'oz' in w_str: w_val /= 16.0
            elif 'kg' in w_str: w_val /= 0.453592
            
            if w_val <= 0: continue

            entry = {'w': w_val}
            valid = False
            for z, c in z_map.items():
                p = clean_num(df.iloc[r, c])
                if p > 0:
                    entry[z] = p
                    valid = True
            
            if valid: prices.append(entry)
        except: continue
            
    prices.sort(key=lambda x: x['w'])
    return prices

def main():
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    
    print("--- Starting Generation (V2026.10 Final) ---")
    
    zip_db = load_gofo_zip_db("T0.xlsx")
    fedex_remote, fedex_extended = load_fedex_pdf_zips()
    
    final_data = {
        "warehouses": WAREHOUSE_DB,
        "channels": CHANNEL_CONFIG,
        "gofo_zips": zip_db,
        "fedex_das_remote": fedex_remote,
        "fedex_das_extended": fedex_extended,
        "tiers": {}
    }

    for tier, filename in TIER_FILES.items():
        print(f"Processing {tier}...")
        path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(path):
            print(f"  [Warn] File not found: {filename}")
            continue
        
        tier_data = {}
        try:
            xl = pd.ExcelFile(path)
            fuel_rate = extract_fuel_rate(xl)
            
            for ch_key, conf in CHANNEL_CONFIG.items():
                sheet = find_sheet_name(xl, conf["keywords"], conf.get("exclude"))
                if not sheet: continue
                
                df = pd.read_excel(xl, sheet_name=sheet, header=None)
                prices = extract_prices(df, split_side=conf.get("sheet_side"), channel_name=ch_key)
                
                if prices:
                    tier_data[ch_key] = {
                        "prices": prices,
                        "fuel_rate": fuel_rate if conf.get("fuel_calc") == "manual" else 0
                    }
                    print(f"  [OK] {ch_key}: {len(prices)} rows")
        except Exception as e:
            print(f"  [Err] Failed to process {filename}: {e}")
        
        final_data["tiers"][tier] = tier_data

    json_str = json.dumps(final_data, ensure_ascii=False).replace("NaN", "0")
    html = HTML_TEMPLATE.replace('__JSON_DATA__', json_str)
    
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    
    print("✅ index.html generated successfully.")

if __name__ == "__main__":
    main()
