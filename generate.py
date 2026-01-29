import pandas as pd
import json
import re
import os
import warnings
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

# 仓库配置
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
# fuel_calc: 'manual'(手动/自动抓取), 'none'(无)
# fuel_discount: True 表示该渠道燃油费打85折
CHANNEL_CONFIG = {
    "GOFO-报价": {
        "keywords": ["GOFO", "报价"], 
        "exclude": ["MT", "UNIUNI", "大件"],
        "allow_wh": ["91730", "60632"], 
        "fuel_calc": "none", 
        "fuel_discount": False,
        "fees": {"res": 0, "sig": 0} 
    },
    "GOFO-MT-报价": {
        "keywords": ["GOFO", "UNIUNI", "MT"],
        "sheet_col_offset": "left",
        "allow_wh": ["91730", "60632"],
        "fuel_calc": "manual", # MT系列需要燃油
        "fuel_discount": False,
        "fees": {"res": 0, "sig": 0}
    },
    "UNIUNI-MT-报价": {
        "keywords": ["GOFO", "UNIUNI", "MT"],
        "sheet_col_offset": "right",
        "allow_wh": ["91730", "60632"],
        "fuel_calc": "none",
        "fuel_discount": False,
        "fees": {"res": 0, "sig": 0}
    },
    "USPS-YSD-报价": {
        "keywords": ["USPS", "YSD"],
        "allow_wh": ["91730", "91752", "60632"], 
        "fuel_calc": "none",
        "fuel_discount": False,
        "fees": {"res": 0, "sig": 0},
        "no_peak": True 
    },
    "FedEx-632-MT-报价": {
        "keywords": ["632"],
        "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
        "fuel_calc": "manual", 
        "fuel_discount": True, # 85折
        "fees": {"res": 2.61, "sig": 4.37}
    },
    "FedEx-MT-超大包裹-报价": {
        "keywords": ["超大包裹"],
        "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
        "fuel_calc": "manual",
        "fuel_discount": True, # 85折
        "fees": {"res": 2.61, "sig": 4.37}
    },
    "FedEx-ECO-MT报价": {
        "keywords": ["ECO", "MT"],
        "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
        "fuel_calc": "manual",
        "fuel_discount": False,
        "fees": {"res": 0, "sig": 0}
    },
    "FedEx-MT-危险品-报价": {
        "keywords": ["危险品"],
        "allow_wh": ["60632", "08691", "06801", "11791", "07032"], 
        "fuel_calc": "manual",
        "fuel_discount": False,
        "fees": {"res": 3.32, "sig": 9.71}
    },
    "GOFO大件-MT-报价": {
        "keywords": ["GOFO大件", "MT"],
        "allow_wh": ["91730", "91752", "08691", "06801", "11791", "07032"], 
        "fuel_calc": "manual", 
        "fuel_discount": False,
        "fees": {"res": 2.93, "sig": 0} 
    },
    "XLmiles-报价": {
        "keywords": ["XLmiles"],
        "allow_wh": ["91730"], 
        "fuel_calc": "none", 
        "fuel_discount": False,
        "fees": {"res": 0, "sig": 10.20}
    }
}

# 州名映射 (用于显示中文)
STATE_MAP = {
    "CA": "加利福尼亚", "NY": "纽约", "NJ": "新泽西", "TX": "德克萨斯",
    "IL": "伊利诺伊", "FL": "佛罗里达", "PA": "宾夕法尼亚", "OH": "俄亥俄"
    # ... 可继续补充
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
  <title>业务员报价助手 (V2026.4 修正版)</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background-color: #f0f2f5; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    .header-bar { background: #343a40; color: #fff; padding: 15px 0; border-bottom: 4px solid #0d6efd; margin-bottom: 25px; }
    .card { border: none; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border-radius: 10px; }
    .card-header { background-color: #fff; font-weight: 700; border-bottom: 1px solid #eee; padding: 15px 20px; border-radius: 10px 10px 0 0 !important; }
    .price-main { font-size: 1.3rem; font-weight: 800; color: #0d6efd; }
    .warn-box { background: #fff3cd; border: 1px solid #ffeeba; color: #856404; padding: 12px; border-radius: 6px; font-size: 0.85rem; margin-bottom: 15px; }
    .status-ok { color: #198754; font-weight: 700; }
    .status-err { color: #dc3545; font-weight: 700; }
    .status-warn { color: #fd7e14; font-weight: 700; }
    .table-sm td, .table-sm th { vertical-align: middle; }
    .compliance-box { background: #e9ecef; border-radius: 6px; padding: 10px; margin-top: 15px; font-size: 0.85rem; }
    .location-tag { font-size: 0.8rem; background: #e7f1ff; color: #0d6efd; padding: 2px 6px; border-radius: 4px; margin-left: 5px; }
  </style>
</head>
<body>

<div class="header-bar">
  <div class="container d-flex justify-content-between align-items-center">
    <div><h4 class="m-0 fw-bold">📦 业务员报价助手</h4><div class="small opacity-75">MT燃油手动微调 | 地区中文显示 | 85折修正</div></div>
    <div class="text-end d-none d-md-block"><span class="badge bg-primary">T0-T3 实时计算</span></div>
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
                    <span class="badge bg-warning text-dark" style="font-size:0.65rem">MT系列生效</span>
                </div>
                <div class="input-group input-group-sm">
                    <input type="number" class="form-control fw-bold text-primary" id="fuelInput" value="16.0" step="0.01">
                    <span class="input-group-text">%</span>
                </div>
                <div class="form-text small text-muted" style="font-size:0.75rem">* 系统已自动抓取文档费率，可手动修改。FedEx-632/超大件自动打85折。</div>
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
              <div class="fw-bold mb-1 text-danger">⚠️ 规格/重量 预检</div>
              <ul class="mb-0 ps-3" id="complianceList"></ul>
            </div>

            <button type="button" class="btn btn-primary w-100 mt-4 fw-bold py-2" id="btnCalc">开始计算 (Calculate)</button>
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
            1. <b>燃油费</b>：您可手动调整左侧费率。仅 <b>FedEx-632 / 超大包裹</b> 享受 <b>85折</b>。<br>
            2. <b>邮编分区</b>：GOFO渠道使用自营分区表；FedEx系列使用标准分区逻辑。<br>
            3. <b>无报价</b>：若显示无报价，请检查包裹是否超过该渠道的最大重量/尺寸限制。<br>
            4. <b>USPS</b>：已取消旺季附加费。<br>
            5. <b>实报实销</b>：产生额外费用（复核尺寸不符/退货/偏远等）按账单收取。
          </div>

          <div class="alert alert-info py-2 small" id="pkgInfo">请录入数据...</div>

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
  &copy; 2026 SureGo Logistics | Data: <span id="updateTime"></span>
</footer>

<script>
  const DATA = __JSON_DATA__;
  document.getElementById('updateTime').innerText = new Date().toLocaleDateString();

  // --- 1. 邮编地区显示 ---
  document.getElementById('zipCode').addEventListener('blur', function() {
    let zip = this.value.trim();
    let display = document.getElementById('locDisplay');
    display.innerHTML = '';
    
    if(zip.length === 5 && DATA.zip_db && DATA.zip_db[zip]) {
        let info = DATA.zip_db[zip];
        display.innerHTML = `<div class="location-tag">📍 ${info.city}, ${info.state} (${info.cn_state || ''})</div>`;
    }
  });

  // --- 2. 自动填入抓取的燃油费 (取最大值) ---
  (function initFuel() {
    let maxFuel = 0;
    // 遍历所有Tier找最大的抓取燃油值作为默认
    Object.values(DATA.tiers).forEach(t => {
        Object.values(t).forEach(ch => {
            if(ch.fuel_rate && ch.fuel_rate > maxFuel) maxFuel = ch.fuel_rate;
        });
    });
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
    
    // 全局提示
    if (pkg.Wt > 150) msgs.push("超过150lb (除XLmiles外不可发)");
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
  });
  if(whSelect.options.length > 0) whSelect.dispatchEvent(new Event('change'));

  // --- 5. Zone 计算 ---
  function calcZone(destZip, originZip, chName) {
    if(!destZip || destZip.length < 3) return 8;
    
    // 如果是GOFO渠道，优先查GOFO自己的表 (暂简化，若JSON里有zone字段可直接用)
    // 这里使用通用逻辑：
    let d = parseInt(destZip.substring(0,3));
    let region = DATA.warehouses[originZip].region;

    if(region === 'WEST') {
      if(d >= 900 && d <= 935) return 2;
      if(d >= 936 && d <= 994) return 4;
      return 8;
    }
    if(region === 'EAST') {
      if(d >= 70 && d <= 89) return 2;
      if(d >= 100 && d <= 199) return 4;
      return 8;
    }
    if(region === 'CENTRAL') {
       if(d >= 600 && d <= 629) return 2;
       return 6;
    }
    return 8;
  }

  // --- 6. 计算主逻辑 ---
  document.getElementById('btnCalc').onclick = () => {
    const whCode = whSelect.value;
    const tier = document.querySelector('input[name="tier"]:checked').value;
    const fuelRateInput = parseFloat(document.getElementById('fuelInput').value) || 0; // 获取手动输入
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

    // 预检
    let comp = checkCompliance(pkg);

    Object.keys(DATA.channels).forEach(chName => {
      const conf = DATA.channels[chName];
      
      // A. 仓库过滤
      if(!conf.allow_wh.includes(whCode)) return;

      // B. 渠道硬性阻断 (无报价)
      if(chName.includes("UNIUNI") && comp.status.uniuni.startsWith("NO")) return;
      if(chName.includes("USPS") && comp.status.usps.startsWith("NO")) return;
      if(chName.includes("XLmiles") && comp.status.xl.startsWith("NO")) return;
      if(chName.includes("FedEx") && !chName.includes("超大") && (pkg.Wt > 150 || pkg.L > 108)) return;

      // C. 计费重
      let finalWt = Math.max(pkg.Wt, dimWt);
      if(!chName.includes("XLmiles")) finalWt = Math.ceil(finalWt);

      let zone = calcZone(zip, whCode, chName);
      let svcTag = "";

      if (chName.includes("XLmiles")) {
        let xl = getXLService(pkg.L, pkg.W, pkg.H, pkg.Wt);
        svcTag = `<br><small class="text-primary">${xl.name}</small>`;
      }

      // D. 查基础运费
      let priceTable = (DATA.tiers[tier][chName] || {}).prices || [];
      // 核心修正：查找 大于等于 finalWt 的最小行
      let row = priceTable.find(r => r.w >= finalWt - 0.001);
      
      if(!row) {
         // 无报价 (超重或数据缺失)
         return; 
      }

      let basePrice = row[zone] || row[8] || 0;
      if(basePrice <= 0) return;

      // E. 附加费
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

      // F. 燃油费 (使用手动输入值 + 85折逻辑)
      if(conf.fuel_calc !== 'none') {
        let rate = fuelRateInput / 100;
        let tag = "";
        
        if (conf.fuel_discount) {
            rate = rate * 0.85; // 仅指定渠道打折
            tag = " (85折)";
        }
        
        let fuelAmt = (basePrice + surcharges) * rate;
        surcharges += fuelAmt;
        details.push(`燃油${tag} ${(rate*100).toFixed(2)}%: $${fuelAmt.toFixed(2)}`);
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
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-danger">无可用报价 (请检查规格是否超标，或该仓库不支持)</td></tr>`;
    }
  };
</script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# ==========================================
# 3. 后端处理逻辑
# ==========================================

def clean_num(val):
    if pd.isna(val): return 0.0
    s = str(val).replace('$', '').replace(',', '').strip()
    try:
        return float(s)
    except:
        return 0.0

def find_csv_path(tier, keywords):
    files = os.listdir('.')
    target = None
    for f in files:
        # 必须匹配 {Tier}.xlsx 开头
        if not f.startswith(f"{tier}.xlsx"): continue
        if all(k in f for k in keywords):
            target = f
            break
    return target

def extract_fuel_rate_from_csv(df):
    """ 从MT表格中抓取燃油费率 (如 0.16) """
    for r in range(min(150, df.shape[0])):
        for c in range(df.shape[1]):
            val = str(df.iloc[r, c])
            # 关键字匹配 "燃油附加费"
            if "燃油附加费" in val:
                # 尝试看右边一格
                if c + 1 < df.shape[1]:
                    rate_val = str(df.iloc[r, c+1])
                    rate_val = rate_val.replace('%', '').strip()
                    try:
                        f = float(rate_val)
                        if f > 1: f = f / 100.0 # 处理 16% 变成 0.16
                        return f
                    except:
                        pass
    return 0.0

def load_zip_db():
    """ 尝试从 GOFO 报价表中读取邮编库 """
    db = {}
    # 找任意一个 GOFO 文件
    csv_files = [f for f in os.listdir('.') if "GOFO-报价" in f]
    if not csv_files: return db
    
    try:
        df = pd.read_csv(csv_files[0], header=None)
        # 寻找包含 "目的地邮编" 的行
        start_row = -1
        zip_col = -1
        city_col = -1
        state_col = -1
        
        for r in range(100):
            row_vals = [str(x) for x in df.iloc[r].values]
            if "目的地邮编" in row_vals or "Zip" in row_vals:
                start_row = r
                # 确定列索引
                for c, v in enumerate(row_vals):
                    if "邮编" in v or "Zip" in v: zip_col = c
                    if "城市" in v or "City" in v: city_col = c
                    if "州" in v or "State" in v: state_col = c
                break
        
        if start_row != -1 and zip_col != -1:
            for r in range(start_row+1, len(df)):
                try:
                    z = str(df.iloc[r, zip_col]).strip().split('.')[0].zfill(5) # 格式化邮编
                    city = str(df.iloc[r, city_col]).strip() if city_col!=-1 else ""
                    state = str(df.iloc[r, state_col]).strip() if state_col!=-1 else ""
                    if len(z) == 5 and z.isdigit():
                        db[z] = {
                            "city": city,
                            "state": state,
                            "cn_state": STATE_MAP.get(state, state)
                        }
                except: continue
        print(f"  [Info] Loaded {len(db)} ZIP entries from GOFO.")
    except Exception as e:
        print(f"  [Err] Failed to load ZIP DB: {e}")
    return db

def extract_prices(df, split_mode=None):
    if df is None: return []
    
    total_cols = df.shape[1]
    c_start, c_end = 0, total_cols
    
    if split_mode == 'left': c_end = total_cols // 2 + 1
    elif split_mode == 'right': c_start = total_cols // 2 - 1

    # 1. 扫描表头 (优化：增加扫描行数)
    h_row = -1
    w_col = -1
    z_map = {}

    for r in range(30): # 扩大扫描范围防止表头靠下
        row_vals = [str(x).lower() for x in df.iloc[r, c_start:c_end].values]
        has_weight = any('weight' in x or '重量' in x for x in row_vals)
        has_zone = any('zone' in x for x in row_vals)
        if has_weight and has_zone:
            h_row = r
            break
    
    if h_row == -1: return []

    # 2. 映射列
    row_dat = df.iloc[h_row]
    for c in range(c_start, c_end):
        if c >= total_cols: break
        val = str(row_dat[c]).strip().lower()
        if ('weight' in val or '重量' in val) and w_col == -1: w_col = c
        m = re.search(r'zone\D*(\d+)', val)
        if m: z_map[int(m.group(1))] = c

    if w_col == -1 or not z_map: return []

    # 3. 提取数据
    prices = []
    for r in range(h_row + 1, len(df)):
        try:
            w_raw = df.iloc[r, w_col]
            w_str = str(w_raw).lower().strip()
            
            # 解析重量
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
    
    print("--- Starting Generation (V2026.4 Final) ---")
    
    final_data = {
        "warehouses": WAREHOUSE_DB,
        "channels": CHANNEL_CONFIG,
        "zip_db": load_zip_db(), # 载入邮编库
        "tiers": {}
    }

    for tier in ["T0", "T1", "T2", "T3"]:
        print(f"Processing {tier}...")
        tier_data = {}
        
        for ch_key, conf in CHANNEL_CONFIG.items():
            csv_name = find_csv_path(tier, conf["keywords"])
            if not csv_name: continue
            
            try:
                df = pd.read_csv(csv_name, header=None)
            except: continue

            # 1. 提取价格
            prices = extract_prices(df, split_mode=conf.get("sheet_col_offset"))
            
            # 2. 提取燃油费 (仅MT渠道尝试抓取)
            fuel_rate = 0.0
            if conf.get("fuel_calc") == "manual":
                fuel_rate = extract_fuel_rate_from_csv(df)
            
            if prices:
                tier_data[ch_key] = {
                    "prices": prices,
                    "fuel_rate": fuel_rate
                }
                print(f"  [OK] {ch_key}: {len(prices)} rows, Fuel: {fuel_rate}")
        
        final_data["tiers"][tier] = tier_data

    # 生成 HTML
    json_str = json.dumps(final_data, ensure_ascii=False).replace("NaN", "0")
    html = HTML_TEMPLATE.replace('__JSON_DATA__', json_str)
    
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    
    print("✅ index.html generated successfully.")

if __name__ == "__main__":
    main()
