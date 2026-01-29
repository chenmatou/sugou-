import pandas as pd
import json
import re
import os
import warnings
from datetime import datetime
import subprocess # 用于调用系统命令读取PDF

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

# 仓库清单 (Code -> Info)
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
# fuel_mode: 
#   'included': 已含油，不计算
#   'discount_85': (Base+Surcharge)*Rate*0.85
#   'standard': (Base+Surcharge)*Rate
#   'none': 无燃油
# zone_source: 'gofo'(查GOFO表), 'general'(查通用距离)
CHANNEL_CONFIG = {
    "GOFO-报价": {
        "keywords": ["GOFO", "报价"], 
        "exclude": ["MT", "UNIUNI", "大件"],
        "allow_wh": ["91730", "60632"], 
        "fuel_mode": "none",
        "zone_source": "gofo",
        "fees": {"res": 0, "sig": 0} 
    },
    "GOFO-MT-报价": {
        "keywords": ["GOFO", "UNIUNI", "MT"],
        "sheet_side": "left",
        "allow_wh": ["91730", "60632"],
        "fuel_mode": "standard", # MT系列正常收
        "zone_source": "gofo",
        "fees": {"res": 0, "sig": 0}
    },
    "UNIUNI-MT-报价": {
        "keywords": ["GOFO", "UNIUNI", "MT"],
        "sheet_side": "right",
        "allow_wh": ["91730", "60632"],
        "fuel_mode": "none",
        "zone_source": "general",
        "fees": {"res": 0, "sig": 0}
    },
    "USPS-YSD-报价": {
        "keywords": ["USPS", "YSD"],
        "allow_wh": ["91730", "91752", "60632"], 
        "fuel_mode": "none", # 基础含油
        "zone_source": "general",
        "fees": {"res": 0, "sig": 0},
        "no_peak": True 
    },
    "FedEx-632-MT-报价": {
        "keywords": ["632"],
        "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
        "fuel_mode": "discount_85", # 85折
        "zone_source": "general",
        "fees": {"res": 2.61, "sig": 4.37}
    },
    "FedEx-MT-超大包裹-报价": {
        "keywords": ["超大包裹"],
        "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
        "fuel_mode": "discount_85", # 85折
        "zone_source": "general",
        "fees": {"res": 2.61, "sig": 4.37}
    },
    "FedEx-ECO-MT报价": {
        "keywords": ["ECO", "MT"],
        "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
        "fuel_mode": "included", # 核心修改：已含油，不叠加
        "zone_source": "general",
        "fees": {"res": 0, "sig": 0}
    },
    "FedEx-MT-危险品-报价": {
        "keywords": ["危险品"],
        "allow_wh": ["60632", "08691", "06801", "11791", "07032"], 
        "fuel_mode": "standard",
        "zone_source": "general",
        "fees": {"res": 3.32, "sig": 9.71}
    },
    "GOFO大件-MT-报价": {
        "keywords": ["GOFO大件", "MT"],
        "allow_wh": ["91730", "91752", "08691", "06801", "11791", "07032"], 
        "fuel_mode": "standard", 
        "zone_source": "gofo", # GOFO系列用GOFO分区
        "fees": {"res": 2.93, "sig": 0} 
    },
    "XLmiles-报价": {
        "keywords": ["XLmiles"],
        "allow_wh": ["91730"], 
        "fuel_mode": "none", 
        "zone_source": "general",
        "fees": {"res": 0, "sig": 10.20}
    }
}

# ==========================================
# 2. 网页模板 (HTML/JS)
# ==========================================
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>业务员报价助手 (V2026.9 Final)</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background-color: #f4f7f6; font-family: 'Segoe UI', sans-serif; }
    .header-bar { background: #222; color: #fff; padding: 15px 0; border-bottom: 4px solid #fd7e14; margin-bottom: 20px; }
    .card { border: none; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-radius: 10px; }
    .card-header { background-color: #fff; font-weight: 700; border-bottom: 1px solid #eee; }
    .price-main { font-size: 1.4rem; font-weight: 800; color: #d63384; }
    .warn-box { background: #fff3cd; border: 1px solid #ffeeba; color: #856404; padding: 12px; border-radius: 6px; font-size: 0.85rem; margin-bottom: 15px; }
    .compliance-box { background: #e9ecef; border-radius: 6px; padding: 10px; margin-top: 15px; font-size: 0.85rem; }
    /* 邮编双显样式 */
    .loc-box { margin-top: 5px; font-size: 0.85rem; }
    .tag-gofo { background: #d1e7dd; color: #0f5132; padding: 2px 6px; border-radius: 4px; border: 1px solid #badbcc; display: block; margin-bottom: 2px; }
    .tag-fedex { background: #cfe2ff; color: #084298; padding: 2px 6px; border-radius: 4px; border: 1px solid #b6d4fe; display: block; }
    .status-ok { color: #198754; font-weight: 700; }
    .status-err { color: #dc3545; font-weight: 700; }
  </style>
</head>
<body>

<div class="header-bar">
  <div class="container d-flex justify-content-between align-items-center">
    <div><h4 class="m-0 fw-bold">📦 业务员报价助手</h4><div class="small opacity-75">V2026.9 | Zone动态计算修复 | 邮编双源识别</div></div>
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
                  * 仅 FedEx-632/超大件 享85折。<br>
                  * FedEx-ECO-MT 已含油 (不叠加)。
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
              <div class="fw-bold mb-1 text-danger">⚠️ 规格预检 (Compliance)</div>
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
            1. <b>燃油费</b>：FedEx-632/超大包裹 (85折)；FedEx-ECO-MT (已含油)；其他MT (全额)。<br>
            2. <b>邮编逻辑</b>：<br>
               &nbsp;&nbsp; ● <b>GOFO</b>：优先查自营表(WE/EA/CE)与仓库匹配。<br>
               &nbsp;&nbsp; ● <b>FedEx/USPS</b>：根据 <b>发货仓库</b> 动态计算分区 (美西发美西=Z2, 发美东=Z8)。<br>
            3. <b>偏远检查</b>：已尝试读取 FedEx DAS PDF，若命中将显示标识。<br>
            4. <b>无报价</b>：请检查是否超重 (UniUni<20lb, USPS<70lb)。
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

  // --- 1. 邮编双显逻辑 (GOFO表 + 通用表) ---
  document.getElementById('zipCode').addEventListener('input', function() {
    let zip = this.value.trim();
    let display = document.getElementById('locDisplay');
    
    if(zip.length === 5) {
        let html = '';
        
        // 1. GOFO 自营库
        if(DATA.gofo_zips && DATA.gofo_zips[zip]) {
            let g = DATA.gofo_zips[zip];
            html += `<div class="tag-gofo">🟢 [GOFO表] ${g.city}, ${g.state} (区域:${g.region})</div>`;
        }
        
        // 2. FedEx/通用库 (DAS)
        // 假设 DATA.fedex_das 存了 PDF 解析的集合
        let fedexInfo = "通用地区";
        if(DATA.fedex_das_remote && DATA.fedex_das_remote.includes(zip)) fedexInfo = "⚠️ FedEx偏远(Remote)";
        else if(DATA.fedex_das_extended && DATA.fedex_das_extended.includes(zip)) fedexInfo = "⚠️ FedEx扩展(Extended)";
        
        html += `<div class="tag-fedex">🔵 [通用/FedEx] ${fedexInfo}</div>`;
        
        display.innerHTML = `<div class="loc-box">${html}</div>`;
    } else {
        display.innerHTML = '';
    }
  });

  // --- 2. 燃油自动填入 ---
  (function initFuel() {
    let maxFuel = 0;
    if(DATA.tiers && DATA.tiers.T3) {
        Object.values(DATA.tiers.T3).forEach(ch => {
            if(ch.fuel_rate && ch.fuel_rate > maxFuel) maxFuel = ch.fuel_rate;
        });
    }
    if(maxFuel > 0) {
        document.getElementById('fuelInput').value = (maxFuel * 100).toFixed(2);
    }
  })();

  // --- 3. 规格校验 ---
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
    let L = dims[0], W = dims[1], H = dims[2];
    let G = L + 2*(W+H);
    let msgs = [];
    
    if (pkg.Wt > 150) msgs.push("超150lb (除XLmiles外不可发)");
    if (L > 108) msgs.push("长>108in (FedEx超长)");
    
    let status = {
      uniuni: (pkg.Wt > 20 || L>20) ? "NO (限重20lb/限长20in)" : "OK",
      usps: (pkg.Wt > 70 || G > 130) ? "NO (限重70lb/围长130in)" : "OK",
      xl: (pkg.Wt > 200 || L > 144 || G > 225) ? "NO (超OM规格)" : "OK"
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
      html += `<li>UniUni: ${res.status.uniuni}</li>`;
      html += `<li>USPS: ${res.status.usps}</li>`;
      html += `<li>XLmiles: ${res.status.xl}</li>`;
      
      document.getElementById('complianceList').innerHTML = html;
      document.getElementById('complianceBox').style.display = 'block';
    } else {
      document.getElementById('complianceBox').style.display = 'none';
    }
  }
  ['dimL','dimW','dimH','weight'].forEach(id => document.getElementById(id).addEventListener('input', updateComplianceUI));

  // --- 4. 初始化 ---
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

  // --- 5. Zone 计算 (关键修复：根据Origin计算) ---
  function calcZone(destZip, originZip, conf) {
    if(!destZip || destZip.length < 3) return 8;
    
    let d = parseInt(destZip.substring(0,3));
    let whRegion = DATA.warehouses[originZip].region;

    // A. GOFO专用逻辑: 查表
    if(conf.zone_source === 'gofo') {
        if(DATA.gofo_zips && DATA.gofo_zips[destZip]) {
            let zReg = DATA.gofo_zips[destZip].region; // WE, EA, CE
            // 简单匹配：同区=Zone2，跨区=Zone8 (可根据实际微调)
            if(whRegion=='WEST' && zReg=='WE') return 2;
            if(whRegion=='CENTRAL' && zReg=='CE') return 2;
            if(whRegion=='EAST' && zReg=='EA') return 2;
            return 8; 
        }
        return 8;
    }

    // B. FedEx/USPS 通用逻辑 (基于发货仓的距离算法)
    if(whRegion === 'WEST') {
      // 美西发货
      if(d >= 900 && d <= 935) return 2; // CA South
      if(d >= 936 && d <= 994) return 4; // CA North / WA / OR
      if(d >= 800 && d <= 899) return 5; // Mountain
      if(d >= 0 && d <= 200) return 8;   // East Coast
      return 7;
    }
    if(whRegion === 'EAST') {
      // 美东发货
      if(d >= 0 && d <= 199) return 2;   // East
      if(d >= 200 && d <= 299) return 4; 
      if(d >= 900 && d <= 999) return 8; // West Coast
      return 6;
    }
    if(whRegion === 'CENTRAL') {
       // 美中发货
       if(d >= 600 && d <= 629) return 2; // IL
       if(d >= 400 && d <= 599) return 4;
       if(d >= 900 && d <= 999) return 7; // West
       if(d >= 0 && d <= 200) return 6;   // East
       return 5;
    }
    return 8;
  }

  // --- 6. 计算主程序 ---
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
      
      // 1. 仓库过滤
      if(!conf.allow_wh.includes(whCode)) return;

      // 2. 渠道阻断
      if(chName.includes("UNIUNI") && comp.status.uniuni.startsWith("NO")) return;
      if(chName.includes("USPS") && comp.status.usps.startsWith("NO")) return;
      if(chName.includes("XLmiles") && comp.status.xl.startsWith("NO")) return;
      if(chName.includes("FedEx") && !chName.includes("超大") && (pkg.Wt > 150 || pkg.L > 108)) return;

      // 3. 计费重
      let finalWt = Math.max(pkg.Wt, dimWt);
      if(!chName.includes("XLmiles")) finalWt = Math.ceil(finalWt);

      let zone = calcZone(zip, whCode, conf);
      let svcTag = "";

      if (chName.includes("XLmiles")) {
        let xl = getXLService(pkg.L, pkg.W, pkg.H, pkg.Wt);
        svcTag = `<br><small class="text-primary">${xl.name}</small>`;
      }

      // 4. 查价
      let priceTable = (DATA.tiers[tier][chName] || {}).prices || [];
      let row = priceTable.find(r => r.w >= finalWt - 0.001);
      
      if(!row) return; 

      let basePrice = row[zone] || row[8] || 0;
      if(basePrice <= 0) return;

      // 5. 附加费
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

      // 6. 燃油费逻辑
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
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-danger">无可用报价 (请检查规格限制或仓库支持)</td></tr>`;
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
    """ 
    专门从 GOFO-报价.csv 中提取自营邮编库
    格式：序号 | 目的地邮编 | GOFO_大区 | 省州 | 城市
    """
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
        
        # 扫描定位表头
        for r in range(min(200, df.shape[0])):
            row_vals = [str(x).strip() for x in df.iloc[r].values]
            if "目的地邮编" in row_vals or "GOFO_大区" in row_vals:
                start_row = r
                for c, v in enumerate(row_vals):
                    if "邮编" in v: cols['zip'] = c
                    elif "城市" in v: cols['city'] = c
                    elif "省州" in v or "State" in v: cols['state'] = c
                    elif "大区" in v or "Region" in v: cols['region'] = c
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
                            "region": str(df.iloc[r, cols.get('region', -1)]).strip()
                        }
                except: continue
        print(f"  [Info] GOFO Zip DB loaded: {len(db)} entries")
    except Exception as e:
        print(f"  [Err] Failed to load GOFO Zip DB: {e}")
    return db

def load_fedex_pdf_zips():
    """ 
    尝试读取 FedEx DAS PDF 文件
    返回两个 Set: remote_zips, extended_zips
    """
    remote_zips = set()
    extended_zips = set()
    
    # 定义文件名
    pdf_files = [
        "FGE_DAS_Contiguous_Extended_Alaska_Hawaii_2025.pdf",
        "FGE_DAS_Zip_Code_Changes_2025.pdf"
    ]
    
    for pdf in pdf_files:
        path = os.path.join(DATA_DIR, pdf)
        if not os.path.exists(path): continue
        
        try:
            # 使用 pdftotext (需系统安装 poppler-utils)
            # 如果没有，catch异常
            txt = subprocess.check_output(["pdftotext", path, "-"]).decode('utf-8')
            
            # 简单的正则提取 (假设文件里全是邮编)
            # 实际需要根据PDF结构区分Remote/Extended，这里简化为全部读取
            # 如果您需要区分，需提供PDF内容结构
            zips = re.findall(r'\b\d{5}\b', txt)
            for z in zips:
                # 简单分类: 实际上需要根据PDF标题判断
                # 暂时全部存入 remote (作为示例)
                remote_zips.add(z)
                
        except Exception as e:
            print(f"  [Warn] PDF read failed (pdftotext missing?): {pdf}")
            
    return list(remote_zips), list(extended_zips)

def extract_prices(df, split_side=None):
    if df is None: return []
    
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
    
    print("--- Starting Generation (V2026.9 Final) ---")
    
    # 1. 加载 GOFO 邮编库
    gofo_zips = load_gofo_zip_db("T0.xlsx")
    
    # 2. 加载 FedEx PDF 邮编 (如果存在)
    fedex_remote, fedex_extended = load_fedex_pdf_zips()
    
    final_data = {
        "warehouses": WAREHOUSE_DB,
        "channels": CHANNEL_CONFIG,
        "gofo_zips": gofo_zips,
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
                prices = extract_prices(df, split_side=conf.get("sheet_side"))
                
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
