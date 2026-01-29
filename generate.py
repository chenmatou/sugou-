import pandas as pd
import json
import re
import os
import warnings
from datetime import datetime

# 忽略 Excel 样式警告
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# ==========================================
# 1. 全局配置 & 业务规则
# ==========================================
DATA_DIR = "data"
OUTPUT_DIR = "public"

TIER_FILES = {
    "T0": "T0.xlsx", "T1": "T1.xlsx", "T2": "T2.xlsx", "T3": "T3.xlsx"
}

# --- 仓库配置 (基于文档) ---
# 归类区域：WEST(美西), CENTRAL(美中), EAST(美东)
# 91730/91752 -> WEST
# 60632/63461 -> CENTRAL
# 08691/06801/11791/07032 -> EAST
WAREHOUSE_DB = {
    "60632": {"name": "SureGo美中芝加哥-60632仓", "region": "CENTRAL"},
    "91730": {"name": "SureGo美西库卡蒙格-91730新仓", "region": "WEST"},
    "91752": {"name": "SureGo美西米拉罗马-91752仓", "region": "WEST"},
    "08691": {"name": "SureGo美东新泽西-08691仓", "region": "EAST"},
    "06801": {"name": "SureGo美东贝塞尔-06801仓", "region": "EAST"},
    "11791": {"name": "SureGo美东长岛-11791仓", "region": "EAST"},
    "07032": {"name": "SureGo美东新泽西-07032仓", "region": "EAST"},
    "63461": {"name": "SureGo退货检测-美中密苏里63461退货仓", "region": "CENTRAL"} # 仅展示
}

# --- 渠道配置表 (核心逻辑) ---
# allow_wh: 仓库白名单 (根据文档片段严格限制)
# fuel_mode: 'discount_85'(85折), 'standard'(全额), 'none'(无)
# fees: 硬编码的附加费 (res=住宅, sig=签名) 根据文档片段或您之前的指定
CHANNEL_CONFIG = {
    "GOFO-报价": {
        "keywords": ["GOFO", "报价"], 
        "exclude": ["MT", "UNIUNI", "大件"],
        # 文档片段: "美西91730仓和美中仓可用"
        "allow_wh": ["91730", "60632"], 
        "fuel_mode": "none", 
        "fees": {"res": 0, "sig": 0} 
    },
    "GOFO-MT-报价": {
        "keywords": ["GOFO", "UNIUNI", "MT"],
        "sheet_col_offset": "left", # 同一张表，取左边
        # 文档片段: "美西91730仓和美中仓可用"
        "allow_wh": ["91730", "60632"],
        "fuel_mode": "none",
        "fees": {"res": 0, "sig": 0}
    },
    "UNIUNI-MT-报价": {
        "keywords": ["GOFO", "UNIUNI", "MT"],
        "sheet_col_offset": "right", # 同一张表，取右边
        # 文档片段: "美西91730仓和美中仓可用"
        "allow_wh": ["91730", "60632"],
        "fuel_mode": "none",
        "fees": {"res": 0, "sig": 0}
    },
    "USPS-YSD-报价": {
        "keywords": ["USPS", "YSD"],
        # 文档片段: "美西、美中仓可用"
        "allow_wh": ["91730", "91752", "60632"], 
        "fuel_mode": "none", # 基础运费含燃油
        "fees": {"res": 0, "sig": 0},
        "no_peak": True # 核心修改: 取消旺季
    },
    "FedEx-632-MT-报价": {
        "keywords": ["632"],
        # 文档片段: "美西仓、美东仓和美中仓可以使用"
        "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
        "fuel_mode": "discount_85", # 燃油85折
        "fees": {"res": 2.61, "sig": 4.37} # 依据您之前提供的精确值
    },
    "FedEx-MT-超大包裹-报价": {
        "keywords": ["超大包裹"],
        # 文档片段: "美西仓、美东仓和美中仓可以使用"
        "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
        "fuel_mode": "discount_85", # 燃油85折
        "fees": {"res": 2.61, "sig": 4.37}
    },
    "FedEx-ECO-MT报价": {
        "keywords": ["ECO", "MT"],
        # 文档片段: "美西仓、美中仓、美东仓可用"
        "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
        "fuel_mode": "standard", # 全额
        "fees": {"res": 0, "sig": 0}
    },
    "FedEx-MT-危险品-报价": {
        "keywords": ["危险品"],
        # 文档片段: "美东仓和美中仓可以使用" (无美西)
        "allow_wh": ["60632", "08691", "06801", "11791", "07032"], 
        "fuel_mode": "standard", # 无折扣
        "fees": {"res": 3.32, "sig": 9.71}
    },
    "GOFO大件-MT-报价": {
        "keywords": ["GOFO大件", "MT"],
        # 文档片段: "美西仓、美东仓可以使用" (注意：片段未提美中，严格按文档走)
        "allow_wh": ["91730", "91752", "08691", "06801", "11791", "07032"], 
        "fuel_mode": "standard", 
        "fees": {"res": 2.93, "sig": 0} 
    },
    "XLmiles-报价": {
        "keywords": ["XLmiles"],
        # 仅美西91730
        "allow_wh": ["91730"], 
        "fuel_mode": "none", # 一口价
        "fees": {"res": 0, "sig": 10.20}
    }
}

# ==========================================
# 2. 网页模板 (HTML + JS核心逻辑)
# ==========================================
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>速狗海外仓 - 业务报价助手 (2026正式版)</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background-color: #f8f9fa; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    .header-bar { background: #212529; color: #fff; padding: 15px 0; border-bottom: 4px solid #0d6efd; margin-bottom: 25px; }
    .card { border: none; box-shadow: 0 2px 10px rgba(0,0,0,0.05); border-radius: 10px; }
    .card-header { background: #fff; font-weight: 700; border-bottom: 1px solid #eee; padding: 15px 20px; border-radius: 10px 10px 0 0 !important; }
    .price-val { font-size: 1.25rem; font-weight: 800; color: #0d6efd; }
    .warn-box { background: #fff3cd; border: 1px solid #ffeeba; color: #856404; padding: 15px; border-radius: 8px; font-size: 0.9rem; margin-bottom: 20px; }
    .status-badge { font-size: 0.8rem; padding: 4px 8px; border-radius: 4px; }
    .bg-ok { background-color: #d1e7dd; color: #0f5132; }
    .bg-err { background-color: #f8d7da; color: #842029; }
    .table-hover tbody tr:hover { background-color: #f1f3f5; }
  </style>
</head>
<body>

<div class="header-bar">
  <div class="container d-flex justify-content-between align-items-center">
    <div>
      <h4 class="m-0 fw-bold">📦 业务员报价助手</h4>
      <div class="small opacity-75">V2026.2 | 恢复尺寸校验 | 渠道合并适配</div>
    </div>
    <div class="text-end d-none d-md-block">
      <span class="badge bg-primary">T0-T3 实时计算</span>
    </div>
  </div>
</div>

<div class="container pb-5">
  <div class="row g-4">
    <div class="col-lg-4">
      <div class="card h-100">
        <div class="card-header">🛠️ 测算参数</div>
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
                <input type="radio" class="btn-check" name="tier" id="t0" value="T0"><label class="btn btn-outline-secondary" for="t0">T0</label>
                <input type="radio" class="btn-check" name="tier" id="t1" value="T1"><label class="btn btn-outline-secondary" for="t1">T1</label>
                <input type="radio" class="btn-check" name="tier" id="t2" value="T2"><label class="btn btn-outline-secondary" for="t2">T2</label>
                <input type="radio" class="btn-check" name="tier" id="t3" value="T3" checked><label class="btn btn-outline-secondary" for="t3">T3</label>
              </div>
            </div>

            <div class="row g-2 mb-3">
              <div class="col-8">
                <label class="form-label small fw-bold text-muted">燃油费率 (%)</label>
                <input type="number" class="form-control" id="fuelInput" value="16.0" step="0.1">
              </div>
              <div class="col-4 d-flex align-items-end pb-2">
                 <span class="badge bg-warning text-dark border">FedEx 85折</span>
              </div>
            </div>

            <div class="row g-2 mb-3">
              <div class="col-6">
                <label class="form-label small fw-bold text-muted">目的地邮编</label>
                <input type="text" class="form-control" id="zipCode" placeholder="5位ZIP">
              </div>
              <div class="col-6">
                <label class="form-label small fw-bold text-muted">地址类型</label>
                <select class="form-select" id="addrType">
                  <option value="res">🏠 住宅</option>
                  <option value="com">🏢 商业</option>
                </select>
              </div>
            </div>

            <div class="form-check form-switch mb-4">
              <input class="form-check-input" type="checkbox" id="sigToggle">
              <label class="form-check-label small" for="sigToggle">需要签名服务 (Signature)</label>
            </div>

            <div class="bg-light p-3 rounded border">
              <label class="form-label small fw-bold text-muted mb-2">包裹信息 (英寸 / 磅)</label>
              <div class="row g-2 mb-2">
                <div class="col-4"><input type="number" id="dimL" class="form-control form-control-sm" placeholder="长 L"></div>
                <div class="col-4"><input type="number" id="dimW" class="form-control form-control-sm" placeholder="宽 W"></div>
                <div class="col-4"><input type="number" id="dimH" class="form-control form-control-sm" placeholder="高 H"></div>
              </div>
              <div class="input-group input-group-sm">
                <span class="input-group-text">实重</span>
                <input type="number" id="weight" class="form-control" placeholder="LBS">
              </div>
            </div>

            <button type="button" class="btn btn-primary w-100 mt-4 py-2 fw-bold" id="btnCalc">开始计算</button>
          </form>
        </div>
      </div>
    </div>

    <div class="col-lg-8">
      <div class="card h-100">
        <div class="card-header d-flex justify-content-between align-items-center">
          <span>📊 报价一览</span>
          <span class="badge bg-warning text-dark" id="resTierBadge">T3</span>
        </div>
        <div class="card-body">
          <div class="warn-box">
            <strong>📢 注意事项 (2026.01更新)：</strong><br>
            1. <b>FedEx-632 / 超大包裹</b>：燃油费按输入费率的 <b>85折</b> 计算。<br>
            2. <b>USPS</b>：已取消旺季附加费。<br>
            3. <b>XLmiles</b>：一口价含燃油/住宅，按单件尺寸判定 AH/OS/OM 档位。<br>
            4. <b>GOFO/UniUni</b>：合并为同一报价表，请根据仓库选择。<br>
            5. <b>免责声明</b>：若产生额外费用（复核尺寸不符/退货/偏远等），将实报实销。
          </div>

          <div class="alert alert-info py-2 small" id="pkgInfo">请录入数据...</div>

          <div class="table-responsive">
            <table class="table table-hover align-middle">
              <thead class="table-light small text-secondary">
                <tr>
                  <th width="20%">渠道</th>
                  <th width="10%">Zone</th>
                  <th width="12%">计费重</th>
                  <th width="13%">基础运费</th>
                  <th width="25%">附加费明细</th>
                  <th width="20%" class="text-end">总费用</th>
                </tr>
              </thead>
              <tbody id="resBody">
                <tr><td colspan="6" class="text-center py-4 text-muted">暂无结果</td></tr>
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

  // --- 1. 恢复：尺寸合规性校验逻辑 (Validate) ---
  function getXLService(L, W, H, Wt) {
    let dims = [L, W, H].sort((a,b) => b-a);
    let maxL = dims[0];
    let girth = maxL + 2*(dims[1] + dims[2]);
    // 依据文档片段逻辑
    if (maxL <= 96 && girth <= 130 && Wt <= 150) return { code: "AH", name: "AH大件" };
    if (maxL <= 108 && girth <= 165 && Wt <= 150) return { code: "OS", name: "OS大件" };
    if (maxL <= 144 && girth <= 225 && Wt <= 200) return { code: "OM", name: "OM超限" };
    return { code: null, name: "超XL规格" };
  }

  function checkCompliance(chName, pkg) {
    let dims = [pkg.L, pkg.W, pkg.H].sort((a,b) => b-a);
    let L = dims[0];
    let G = L + 2*(dims[1] + dims[2]);

    // UniUni: 通常限制较小 (参考之前逻辑: 20lb/20in? 暂定宽松点或按之前)
    // 根据您的要求“恢复判定”，假设 UniUni 限制 50lb (保守) 或 20lb (之前代码)
    // 这里按常见小包限制: 
    if (chName.includes("UNIUNI")) {
      if (pkg.Wt > 20) return "限重20lb"; 
    }
    // USPS: Max 70lb, G<=130
    if (chName.includes("USPS")) {
      if (pkg.Wt > 70) return "限重70lb";
      if (G > 130) return "超尺寸(G>130)";
    }
    // XLmiles: Max 200lb, OM Limit
    if (chName.includes("XLmiles")) {
      if (pkg.Wt > 200) return "超重>200lb";
      let svc = getXLService(pkg.L, pkg.W, pkg.H, pkg.Wt);
      if (!svc.code) return "超XL规格";
    }
    // FedEx常规 (非超大): Max 150lb
    if (chName.includes("FedEx") && !chName.includes("超大")) {
      if (pkg.Wt > 150) return "超重>150lb";
      if (L > 108 || G > 165) return "超尺寸(转超大)";
    }
    return "OK";
  }

  // --- 2. 初始化 ---
  const whSelect = document.getElementById('whSelect');
  const whRegion = document.getElementById('whRegion');
  
  Object.keys(DATA.warehouses).forEach(code => {
    let opt = document.createElement('option');
    opt.value = code;
    opt.text = DATA.warehouses[code].name;
    whSelect.appendChild(opt);
  });
  
  whSelect.addEventListener('change', () => {
    let r = DATA.warehouses[whSelect.value].region;
    whRegion.innerText = `区域: ${r}`;
  });
  if(whSelect.options.length > 0) whSelect.dispatchEvent(new Event('change'));

  // --- 3. Zone 计算 ---
  function calcZone(destZip, originZip) {
    if(!destZip || destZip.length < 3) return 8;
    let d = parseInt(destZip.substring(0,3));
    let originRegion = DATA.warehouses[originZip].region;

    if(originRegion === 'WEST') {
      if(d >= 900 && d <= 935) return 2;
      if(d >= 936 && d <= 994) return 4;
      return 8;
    }
    if(originRegion === 'EAST') {
      if(d >= 70 && d <= 89) return 2;
      if(d >= 100 && d <= 199) return 4;
      return 8;
    }
    if(originRegion === 'CENTRAL') {
       if(d >= 600 && d <= 629) return 2;
       return 6;
    }
    return 8;
  }

  // --- 4. 计算核心 ---
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
    let vol = pkg.L * pkg.W * pkg.H;
    let dimWt = vol / 222;
    document.getElementById('pkgInfo').innerHTML = 
      `<b>当前:</b> ${pkg.L}x${pkg.W}x${pkg.H} | 实重:${pkg.Wt} | 体积重:${dimWt.toFixed(2)}`;

    const tbody = document.getElementById('resBody');
    tbody.innerHTML = '';

    Object.keys(DATA.channels).forEach(chName => {
      const conf = DATA.channels[chName];
      
      // A. 仓库白名单校验
      if(!conf.allow_wh.includes(whCode)) return;

      // B. 尺寸合规校验 (恢复逻辑)
      let status = checkCompliance(chName, pkg);
      if (status !== "OK") {
        tbody.innerHTML += `
          <tr class="table-light text-muted">
            <td>${chName}</td>
            <td colspan="4">不可用: ${status}</td>
            <td class="text-end"><span class="badge bg-err">×</span></td>
          </tr>`;
        return;
      }

      // C. 计费重
      let finalWt = Math.max(pkg.Wt, dimWt);
      if(!chName.includes("XLmiles")) finalWt = Math.ceil(finalWt);

      let zone = calcZone(zip, whCode);
      let svcTag = "";

      // XLmiles 显示 AH/OS
      if (chName.includes("XLmiles")) {
        let xl = getXLService(pkg.L, pkg.W, pkg.H, pkg.Wt);
        svcTag = `<br><small class="text-info">${xl.name}</small>`;
      }

      // D. 查价
      let priceTable = (DATA.tiers[tier][chName] || {}).prices || [];
      let row = priceTable.find(r => r.w >= finalWt - 0.001);
      
      if(!row) {
         // 无报价
         tbody.innerHTML += `
          <tr class="table-light text-muted">
            <td>${chName}</td>
            <td colspan="4">无对应重量报价</td>
            <td class="text-end"><span class="badge bg-secondary">N/A</span></td>
          </tr>`;
         return; 
      }

      let basePrice = row[zone] || row[8] || 0;
      if(basePrice <= 0) return;

      // E. 附加费
      let surcharges = 0;
      let details = [];

      // 住宅
      if(isRes && conf.fees.res > 0) {
        surcharges += conf.fees.res;
        details.push(`住宅 $${conf.fees.res}`);
      }
      // 签名
      if(sigOn && conf.fees.sig > 0) {
        surcharges += conf.fees.sig;
        details.push(`签名 $${conf.fees.sig}`);
      }

      // 燃油
      if(conf.fuel_mode !== 'none') {
        let appliedRate = fuelRateInput / 100;
        let tag = "";
        
        if(conf.fuel_mode === 'discount_85') {
          appliedRate = appliedRate * 0.85;
          tag = "(85折)";
        }

        let fuelAmt = (basePrice + surcharges) * appliedRate;
        surcharges += fuelAmt;
        details.push(`燃油${tag} $${fuelAmt.toFixed(2)}`);
      }

      let total = basePrice + surcharges;

      tbody.innerHTML += `
        <tr>
          <td class="fw-bold">${chName} ${svcTag}</td>
          <td><span class="badge bg-light text-dark border">Z${zone}</span></td>
          <td>${finalWt}</td>
          <td>$${basePrice.toFixed(2)}</td>
          <td class="small text-muted" style="line-height:1.2">${details.join('<br>') || '-'}</td>
          <td class="text-end price-val">$${total.toFixed(2)}</td>
        </tr>
      `;
    });
  };
</script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# ==========================================
# 3. 后端处理逻辑
# ==========================================

def clean_money(val):
    if pd.isna(val): return 0.0
    s = str(val).replace('$', '').replace(',', '').strip()
    try:
        return float(s)
    except:
        return 0.0

def find_sheet(excel_path, keywords, exclude_keywords=None):
    try:
        xl = pd.ExcelFile(excel_path)
        for sheet in xl.sheet_names:
            s_upper = sheet.upper().replace(" ", "")
            if not all(k.upper() in s_upper for k in keywords):
                continue
            if exclude_keywords and any(e.upper() in s_upper for e in exclude_keywords):
                continue
            return pd.read_excel(xl, sheet_name=sheet, header=None)
    except Exception as e:
        print(f"Error reading {excel_path}: {e}")
    return None

def extract_prices(df, split_mode=None):
    """ split_mode: 'left' (GOFO侧), 'right' (UNIUNI侧), None (整表) """
    if df is None: return []
    
    # 确定扫描列范围
    total_cols = df.shape[1]
    col_start = 0
    col_end = total_cols
    
    if split_mode == 'left':
        col_end = total_cols // 2 + 1 
    elif split_mode == 'right':
        col_start = total_cols // 2 - 1

    # 1. 找表头
    header_row_idx = -1
    zone_map = {}
    weight_col_idx = -1
    
    for r in range(15): # 扫描前15行
        # 只看指定范围内的列
        row_vals = [str(x).lower() for x in df.iloc[r, col_start:col_end].values]
        if any('weight' in x or '重量' in x for x in row_vals) and \
           any('zone' in x for x in row_vals):
            header_row_idx = r
            break
    
    if header_row_idx == -1: return []

    # 2. 解析列
    row_data = df.iloc[header_row_idx]
    for c in range(col_start, col_end):
        if c >= total_cols: break
        val = str(row_data[c]).strip().lower()
        
        if ('weight' in val or '重量' in val) and weight_col_idx == -1:
            weight_col_idx = c
        
        m = re.search(r'zone\D*(\d+)', val)
        if m:
            z_num = int(m.group(1))
            zone_map[z_num] = c

    if weight_col_idx == -1 or not zone_map:
        return []

    # 3. 提取
    prices = []
    for r in range(header_row_idx + 1, len(df)):
        try:
            w_raw = df.iloc[r, weight_col_idx]
            w_str = str(w_raw).lower().strip()
            
            # 解析重量
            nums = re.findall(r'[\d\.]+', w_str)
            if not nums: continue
            
            weight_val = float(nums[0])
            if 'oz' in w_str: weight_val /= 16.0
            elif 'kg' in w_str: weight_val /= 0.453592
            
            if weight_val <= 0: continue

            row_dict = {'w': weight_val}
            for z_num, c_idx in zone_map.items():
                p = clean_money(df.iloc[r, c_idx])
                if p > 0:
                    row_dict[z_num] = p
            
            if len(row_dict) > 1:
                prices.append(row_dict)
        except:
            continue
            
    prices.sort(key=lambda x: x['w'])
    return prices

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    all_data = {
        "warehouses": WAREHOUSE_DB,
        "channels": CHANNEL_CONFIG,
        "tiers": {}
    }

    for tier, filename in TIER_FILES.items():
        print(f"Processing {tier} ({filename})...")
        path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(path):
            print(f"  Warning: {filename} not found.")
            continue
        
        tier_data = {}
        for ch_key, conf in CHANNEL_CONFIG.items():
            df = find_sheet(path, conf["keywords"], conf.get("exclude"))
            if df is None:
                continue
            
            prices = extract_prices(df, split_mode=conf.get("sheet_col_offset")) # 修正参数名
            if prices:
                tier_data[ch_key] = {"prices": prices}
                print(f"    Loaded {ch_key}: {len(prices)} rows")
        
        all_data["tiers"][tier] = tier_data

    json_str = json.dumps(all_data, ensure_ascii=False).replace("NaN", "0")
    html_content = HTML_TEMPLATE.replace("__JSON_DATA__", json_str)
    
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print("\n✅ Public/index.html generated successfully.")

if __name__ == "__main__":
    main()
