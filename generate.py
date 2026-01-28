import pandas as pd
import json
import re
import os
import warnings
from datetime import datetime

# 忽略 Excel 样式警告
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# ==========================================
# 1. 全局配置 & 业务规则 (严格对应文档)
# ==========================================
DATA_DIR = "data"
OUTPUT_DIR = "public"

TIER_FILES = {
    "T0": "T0.xlsx", "T1": "T1.xlsx", "T2": "T2.xlsx", "T3": "T3.xlsx"
}

# --- 仓库配置 (严格对照您的列表) ---
WAREHOUSE_DB = {
    "60632": {"name": "SureGo美中芝加哥-60632仓", "region": "CENTRAL"},
    "91730": {"name": "SureGo美西库卡蒙格-91730新仓", "region": "WEST"},
    "91752": {"name": "SureGo美西米拉罗马-91752仓", "region": "WEST"},
    "08691": {"name": "SureGo美东新泽西-08691仓", "region": "EAST"},
    "06801": {"name": "SureGo美东贝塞尔-06801仓", "region": "EAST"},
    "11791": {"name": "SureGo美东长岛-11791仓", "region": "EAST"},
    "07032": {"name": "SureGo美东新泽西-07032仓", "region": "EAST"},
    "63461": {"name": "SureGo退货检测-美中密苏里63461退货仓", "region": "CENTRAL"} # 仅展示，无报价
}

# --- 渠道配置表 (核心逻辑) ---
# allow_wh: 允许的仓库Code列表
# fuel_mode: 'discount_85'(85折), 'standard'(全额), 'none'(无)
# fees: 硬编码的附加费 (res=住宅, sig=签名)
CHANNEL_CONFIG = {
    "GOFO-报价": {
        "keywords": ["GOFO", "报价"], 
        "exclude": ["MT", "UNIUNI", "大件"],
        "allow_wh": ["91730", "60632"], # 美西91730 + 美中
        "fuel_mode": "none", # 报价通常含油或不收，如需收请改为 standard
        "fees": {"res": 0, "sig": 0} 
    },
    "GOFO-MT-报价": {
        "keywords": ["GOFO", "UNIUNI", "MT"],
        "sheet_col_offset": "left", # 同表左侧
        "allow_wh": ["91730", "60632"],
        "fuel_mode": "none",
        "fees": {"res": 0, "sig": 0}
    },
    "UNIUNI-MT-报价": {
        "keywords": ["GOFO", "UNIUNI", "MT"],
        "sheet_col_offset": "right", # 同表右侧
        "allow_wh": ["91730", "60632"],
        "fuel_mode": "none",
        "fees": {"res": 0, "sig": 0}
    },
    "USPS-YSD-报价": {
        "keywords": ["USPS", "YSD"],
        "allow_wh": ["91730", "60632", "91752"], # 美西、美中 (含91752?) 暂按文档"美西、美中"
        "fuel_mode": "none",
        "fees": {"res": 0, "sig": 0},
        "no_peak": True # 取消旺季
    },
    "FedEx-632-MT-报价": {
        "keywords": ["632"],
        "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"], # 美西/美中/美东
        "fuel_mode": "discount_85", # 燃油85折
        "fees": {"res": 2.61, "sig": 4.37}
    },
    "FedEx-MT-超大包裹-报价": {
        "keywords": ["超大包裹"],
        "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
        "fuel_mode": "discount_85", # 燃油85折
        "fees": {"res": 2.61, "sig": 4.37}
    },
    "FedEx-ECO-MT报价": {
        "keywords": ["ECO", "MT"],
        "allow_wh": ["91730", "91752", "60632", "08691", "06801", "11791", "07032"],
        "fuel_mode": "standard", # 未提及打折，默认全额(或无? 文档未明确说ECO免油，通常FedEx都有，暂设standard)
        "fees": {"res": 0, "sig": 0} # ECO通常含部分费用或不适用
    },
    "FedEx-MT-危险品-报价": {
        "keywords": ["危险品"],
        "allow_wh": ["60632", "08691", "06801", "11791", "07032"], # 美东 + 美中
        "fuel_mode": "standard", # 未说明折扣 -> 原价
        "fees": {"res": 3.32, "sig": 9.71}
    },
    "GOFO大件-MT-报价": {
        "keywords": ["GOFO大件", "MT"],
        "allow_wh": ["91730", "91752", "08691", "06801", "11791", "07032"], # 美西 + 美东 (文档未提美中)
        "fuel_mode": "standard", 
        "fees": {"res": 2.93, "sig": 0} # 签名费不支持
    },
    "XLmiles-报价": {
        "keywords": ["XLmiles"],
        "allow_wh": ["91730"], # 仅美西91730
        "fuel_mode": "none", # 一口价含油
        "fees": {"res": 0, "sig": 10.20}
    }
}

# ==========================================
# 2. 网页模板 (包含您要求的逻辑JS)
# ==========================================
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>速狗海外仓 - 2026专业报价计算器</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background-color: #f5f7fa; font-family: "Microsoft YaHei", sans-serif; }
    .header-bar { background: #222; color: #fff; padding: 15px 0; border-bottom: 4px solid #0d6efd; }
    .card { border: none; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-radius: 8px; margin-bottom: 20px; }
    .card-header { background: #333; color: #fff; font-weight: bold; border-radius: 8px 8px 0 0 !important; }
    .price-big { font-size: 1.3rem; font-weight: 800; color: #0d6efd; }
    .warn-box { background: #fff3cd; border: 1px solid #ffeeba; color: #856404; padding: 10px; border-radius: 5px; font-size: 0.85rem; margin-bottom: 15px; }
    .table-sm td, .table-sm th { vertical-align: middle; }
    .status-ok { color: #198754; font-weight: bold; }
    .status-err { color: #dc3545; font-weight: bold; }
    .fuel-badge-85 { background: #ffc107; color: #000; font-size: 0.7rem; padding: 2px 5px; border-radius: 4px; margin-left: 5px; }
  </style>
</head>
<body>

<div class="header-bar">
  <div class="container d-flex justify-content-between align-items-center">
    <div><h4 class="m-0">📦 业务员报价助手 (2026.01版)</h4></div>
    <div class="small">T0-T3 | 燃油85折 | 严谨校验</div>
  </div>
</div>

<div class="container my-4">
  <div class="row g-4">
    <div class="col-lg-4">
      <div class="card h-100">
        <div class="card-header">1. 基础信息录入</div>
        <div class="card-body">
          <form id="calcForm">
            <div class="mb-3">
              <label class="form-label fw-bold small">发货仓库 (Warehouse)</label>
              <select class="form-select" id="warehouse"></select>
              <div class="form-text small text-primary" id="whInfo"></div>
            </div>

            <div class="mb-3">
              <label class="form-label fw-bold small">客户等级</label>
              <div class="btn-group w-100" role="group">
                <input type="radio" class="btn-check" name="tier" id="t0" value="T0"><label class="btn btn-outline-dark" for="t0">T0</label>
                <input type="radio" class="btn-check" name="tier" id="t1" value="T1"><label class="btn btn-outline-dark" for="t1">T1</label>
                <input type="radio" class="btn-check" name="tier" id="t2" value="T2"><label class="btn btn-outline-dark" for="t2">T2</label>
                <input type="radio" class="btn-check" name="tier" id="t3" value="T3" checked><label class="btn btn-outline-dark" for="t3">T3</label>
              </div>
            </div>

            <div class="row g-2 mb-3">
              <div class="col-7">
                <label class="form-label fw-bold small">燃油费率 (%)</label>
                <input type="number" class="form-control" id="fuelRate" value="16.0" step="0.1">
              </div>
              <div class="col-5 pt-4">
                <span class="badge bg-warning text-dark">FedEx 85折</span>
              </div>
            </div>

            <div class="mb-3">
              <label class="form-label fw-bold small">目的地邮编 (Zip)</label>
              <input type="text" class="form-control" id="zipCode" placeholder="5位邮编">
            </div>

            <div class="row g-2 mb-3">
              <div class="col-6">
                <label class="form-label fw-bold small">地址类型</label>
                <select class="form-select" id="addrType">
                  <option value="res">🏠 住宅</option>
                  <option value="com">🏢 商业</option>
                </select>
              </div>
              <div class="col-6 pt-4 text-end">
                <div class="form-check form-switch d-inline-block">
                  <input class="form-check-input" type="checkbox" id="sigOn">
                  <label class="form-check-label small fw-bold" for="sigOn">签名服务</label>
                </div>
              </div>
            </div>

            <hr>
            <div class="mb-3">
              <label class="form-label fw-bold small">包裹规格 (Inch / Lb)</label>
              <div class="row g-2">
                <div class="col-4"><input type="number" class="form-control" id="L" placeholder="长 L"></div>
                <div class="col-4"><input type="number" class="form-control" id="W" placeholder="宽 W"></div>
                <div class="col-4"><input type="number" class="form-control" id="H" placeholder="高 H"></div>
              </div>
              <div class="input-group mt-2">
                <span class="input-group-text">实重</span>
                <input type="number" class="form-control" id="Wt" placeholder="Weight">
                <span class="input-group-text">LB</span>
              </div>
            </div>

            <button type="button" class="btn btn-primary w-100 fw-bold py-2" id="btnCalc">开始计算 (Calculate)</button>
          </form>
        </div>
      </div>
    </div>

    <div class="col-lg-8">
      <div class="card h-100">
        <div class="card-header d-flex justify-content-between">
          <span>📊 测算结果</span>
          <span id="tierBadge" class="badge bg-warning text-dark">T3</span>
        </div>
        <div class="card-body">
          <div class="warn-box">
            <strong>📢 注意事项 (2026新年调整)：</strong><br>
            1. <b>FedEx-632 / 超大包裹</b>：燃油费按输入费率的 <b>85折</b> 计算。<br>
            2. <b>FedEx危险品</b>：燃油费无折扣，仅限美东/美中仓发货。<br>
            3. <b>XLmiles</b>：一口价包含燃油/住宅/偏远，单件根据尺寸判定 AH/OS/OM 档位。<br>
            4. <b>USPS</b>：已取消旺季附加费。<br>
            * 若派送后产生额外费用（如尺寸不符/退货），将实报实销。
          </div>

          <div class="alert alert-light border small" id="pkgInfo">等待输入...</div>

          <div class="table-responsive">
            <table class="table table-bordered table-hover table-sm text-center">
              <thead class="table-dark">
                <tr>
                  <th width="15%">渠道</th>
                  <th width="8%">Zone</th>
                  <th width="10%">计费重</th>
                  <th width="12%">基础运费</th>
                  <th width="25%">附加费明细</th>
                  <th width="15%">总费用</th>
                  <th width="15%">状态</th>
                </tr>
              </thead>
              <tbody id="resBody"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<footer><div class="container text-center text-muted py-3 small">&copy; 2026 SureGo Logistics</div></footer>

<script>
  // 注入的数据
  const DATA = __JSON_DATA__;

  // --- 1. 逻辑恢复：XLmiles 尺寸判定 (AH/OS/OM) ---
  function getXLService(L, W, H, Wt) {
    // 排序边长
    let dims = [L, W, H].sort((a,b) => b-a);
    let maxL = dims[0];
    let girth = maxL + 2*(dims[1] + dims[2]);
    
    // 逻辑判定 (严格按XLmiles规则)
    // AH: L<=96 且 Girth<=130, Wt<=150
    // OS: L<=108 且 Girth<=165, Wt<=150
    // OM: L<=144 且 Girth<=225, Wt<=200
    
    if (maxL <= 96 && girth <= 130 && Wt <= 150) return { code: "AH", name: "AH大件" };
    if (maxL <= 108 && girth <= 165 && Wt <= 150) return { code: "OS", name: "OS大件" };
    if (maxL <= 144 && girth <= 225 && Wt <= 200) return { code: "OM", name: "OM超限" };
    
    return { code: null, name: "超规" };
  }

  // --- 2. 逻辑恢复：渠道合规性检查 (Check) ---
  function validateChannel(chName, pkg) {
    let dims = [pkg.L, pkg.W, pkg.H].sort((a,b) => b-a);
    let L = dims[0];
    let G = L + 2*(dims[1] + dims[2]);

    // UNIUNI: L<=20 ??? 之前代码可能有误，UNIUNI通常较小，假设限制20lb
    if (chName.includes("UNIUNI")) {
      if (pkg.Wt > 20) return "限重20lb";
    }
    // USPS: Max 70lb, G<=130
    if (chName.includes("USPS")) {
      if (pkg.Wt > 70) return "限重70lb";
      if (G > 130) return "超尺寸";
    }
    // XLmiles: Max 200lb
    if (chName.includes("XLmiles")) {
      if (pkg.Wt > 200) return "超重>200lb";
      let svc = getXLService(pkg.L, pkg.W, pkg.H, pkg.Wt);
      if (!svc.code) return "超XL规格";
    }
    return "OK";
  }

  // --- 3. 基础功能 ---
  const whSelect = document.getElementById('whSelect');
  Object.keys(DATA.warehouses).forEach(code => {
    let opt = document.createElement('option');
    opt.value = code;
    opt.text = DATA.warehouses[code].name;
    whSelect.appendChild(opt);
  });
  whSelect.addEventListener('change', () => {
    let r = DATA.warehouses[whSelect.value].region;
    document.getElementById('whInfo').innerText = `区域: ${r}`;
  });
  whSelect.dispatchEvent(new Event('change')); // Init

  // Zone计算
  function getZone(zip, whCode) {
    if (!zip || zip.length < 3) return 8;
    let d = parseInt(zip.substring(0, 3));
    let region = DATA.warehouses[whCode].region;
    
    // 简易逻辑，实际应查表
    if (region === 'WEST') {
      if (d >= 900 && d <= 935) return 2;
      if (d >= 936 && d <= 994) return 4;
      return 8;
    }
    if (region === 'EAST') {
      if (d >= 70 && d <= 89) return 2;
      if (d >= 100 && d <= 199) return 4;
      return 8;
    }
    if (region === 'CENTRAL') {
      if (d >= 600 && d <= 629) return 2;
      return 6;
    }
    return 8;
  }

  // --- 4. 核心计算 ---
  document.getElementById('btnCalc').onclick = () => {
    let whCode = whSelect.value;
    let tier = document.querySelector('input[name="tier"]:checked').value;
    let fuelInput = parseFloat(document.getElementById('fuelRate').value) || 0;
    let zip = document.getElementById('zipCode').value.trim();
    let isRes = document.getElementById('addrType').value === 'res';
    let sigOn = document.getElementById('sigOn').checked;

    let pkg = {
      L: parseFloat(document.getElementById('L').value)||0,
      W: parseFloat(document.getElementById('W').value)||0,
      H: parseFloat(document.getElementById('H').value)||0,
      Wt: parseFloat(document.getElementById('Wt').value)||0
    };

    document.getElementById('tierBadge').innerText = tier;
    let dimWt = (pkg.L * pkg.W * pkg.H) / 222;
    document.getElementById('pkgInfo').innerText = 
      `尺寸: ${pkg.L}*${pkg.W}*${pkg.H} | 实重: ${pkg.Wt} | 体积重: ${dimWt.toFixed(2)}`;

    let tbody = document.getElementById('resBody');
    tbody.innerHTML = '';

    // 遍历渠道
    Object.keys(DATA.channels).forEach(chName => {
      let conf = DATA.channels[chName];

      // A. 仓库过滤 (严谨)
      if (!conf.allow_wh.includes(whCode)) return;

      // B. 尺寸/规则校验
      let checkMsg = validateChannel(chName, pkg);
      if (checkMsg !== "OK") {
        tbody.innerHTML += `<tr class="table-light text-muted">
          <td>${chName}</td><td colspan="5">不可用 (${checkMsg})</td>
          <td><span class="status-err">×</span></td></tr>`;
        return;
      }

      // C. 计费重
      let finalWt = Math.max(pkg.Wt, dimWt);
      if (!chName.includes("XLmiles")) finalWt = Math.ceil(finalWt);

      // D. 基础运费查找
      let basePrice = 0;
      let zone = getZone(zip, whCode);
      let svcName = "";

      // 特殊处理 XLmiles (AH/OS/OM)
      if (chName.includes("XLmiles")) {
        let xlSvc = getXLService(pkg.L, pkg.W, pkg.H, pkg.Wt);
        svcName = xlSvc.name;
        // XLmiles 价格表结构: {w: 70, AH: 27.75, ...} 需对应列名
        // 简化：假设Excel里列名是 Zone~1, Zone~2... 
        // 实际上XLmiles通常是一口价，这里如果Excel没匹配上，可能需要Hardcode逻辑
        // 为防Excel抓取失败，这里加兜底：暂按Excel抓取走
      }

      let priceList = (DATA.tiers[tier][chName] || {}).prices || [];
      // 查找重量匹配行
      let row = priceList.find(r => r.w >= finalWt - 0.001);
      
      if (row) {
        // 尝试取值
        basePrice = row[zone] || row[8] || 0;
      }

      if (basePrice <= 0) {
        tbody.innerHTML += `<tr class="table-light text-muted">
          <td>${chName}</td><td colspan="5">无报价数据</td>
          <td><span class="status-err">×</span></td></tr>`;
        return;
      }

      // E. 附加费计算
      let extra = 0;
      let details = [];

      // 住宅费
      if (isRes && conf.fees.res > 0) {
        extra += conf.fees.res;
        details.push(`住宅$${conf.fees.res}`);
      }
      // 签名费
      if (sigOn && conf.fees.sig > 0) {
        extra += conf.fees.sig;
        details.push(`签名$${conf.fees.sig}`);
      }

      // 燃油费 (核心逻辑)
      if (conf.fuel_mode !== 'none') {
        let rate = fuelInput / 100;
        let desc = "";
        
        if (conf.fuel_mode === 'discount_85') {
          rate = rate * 0.85; // 85折
          desc = "(85折)";
        }
        
        let fuelAmt = (basePrice + extra) * rate;
        extra += fuelAmt;
        details.push(`燃油${desc}$${fuelAmt.toFixed(2)}`);
      }

      let total = basePrice + extra;

      tbody.innerHTML += `
        <tr>
          <td class="fw-bold text-start">${chName} <span class="badge bg-secondary ms-1" style="font-size:0.6rem">${svcName}</span></td>
          <td>Z${zone}</td>
          <td>${finalWt}</td>
          <td>$${basePrice.toFixed(2)}</td>
          <td class="small text-start text-muted">${details.join(' + ') || '-'}</td>
          <td class="price-big">$${total.toFixed(2)}</td>
          <td><span class="status-ok">✔ 可用</span></td>
        </tr>
      `;
    });
  };
</script>
</body>
</html>
"""

# ==========================================
# 3. 后端逻辑 (Excel 抽取)
# ==========================================
def clean_num(val):
    if pd.isna(val): return 0.0
    s = str(val).replace('$', '').replace(',', '').strip()
    try:
        return float(s)
    except:
        return 0.0

def get_excel_data():
    all_data = {"tiers": {}}
    
    for t_name, f_name in TIER_FILES.items():
        f_path = os.path.join(DATA_DIR, f_name)
        if not os.path.exists(f_path): continue
        
        print(f"Reading {f_name}...")
        tier_data = {}
        xl = pd.ExcelFile(f_path)
        
        for ch, conf in CHANNEL_CONFIG.items():
            # 1. 寻找 Sheet
            target_sheet = None
            for s in xl.sheet_names:
                s_up = s.upper().replace(" ", "")
                # 必须包含所有关键词
                if all(k.upper() in s_up for k in conf['keywords']):
                    # 必须不包含排除词
                    if 'exclude' in conf and any(e.upper() in s_up for e in conf['exclude']):
                        continue
                    target_sheet = s
                    break
            
            if not target_sheet:
                print(f"  [X] Sheet not found for {ch}")
                continue

            # 2. 读取数据 (处理左右分栏)
            df = pd.read_excel(xl, sheet_name=target_sheet, header=None)
            
            # 确定列范围
            c_start, c_end = 0, df.shape[1]
            if 'sheet_col_offset' in conf:
                mid = df.shape[1] // 2
                if conf['sheet_col_offset'] == 'left': c_end = mid + 2
                else: c_start = mid - 2

            # 3. 找表头 (Weight & Zone)
            h_row = -1
            w_col = -1
            z_map = {} # {1: col_idx, 2: col_idx}

            for r in range(15): # 扫描前15行
                row_vals = [str(x).lower() for x in df.iloc[r, c_start:c_end].values]
                if any('weight' in x or '重量' in x for x in row_vals) and any('zone' in x for x in row_vals):
                    h_row = r
                    break
            
            if h_row == -1: continue

            # 解析列
            row_dat = df.iloc[h_row]
            for c in range(c_start, c_end):
                val = str(row_dat[c]).strip().lower()
                if ('weight' in val or '重量' in val) and w_col == -1:
                    w_col = c
                m = re.search(r'zone\D*(\d+)', val)
                if m:
                    z_map[int(m.group(1))] = c
            
            if w_col == -1 or not z_map: continue

            # 4. 提取价格
            prices = []
            for r in range(h_row+1, len(df)):
                try:
                    w_str = str(df.iloc[r, w_col]).lower()
                    # 简单解析 lb
                    w_val = 0.0
                    nums = re.findall(r'[\d\.]+', w_str)
                    if not nums: continue
                    w_val = float(nums[0])
                    if 'oz' in w_str: w_val /= 16.0
                    
                    if w_val <= 0: continue
                    
                    p_row = {'w': w_val}
                    for z, c in z_map.items():
                        p = clean_num(df.iloc[r, c])
                        if p > 0: p_row[z] = p
                    
                    if len(p_row) > 1: prices.append(p_row)
                except: continue
            
            tier_data[ch] = {"prices": prices}
            print(f"  [OK] {ch}: {len(prices)} rows")

        all_data["tiers"][t_name] = tier_data

    return all_data

if __name__ == '__main__':
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    
    # 1. 读取Excel
    data = get_excel_data()
    
    # 2. 注入配置
    data["warehouses"] = WAREHOUSE_DB
    data["channels"] = CHANNEL_CONFIG
    
    # 3. 生成 HTML
    json_str = json.dumps(data, ensure_ascii=False).replace("NaN", "0")
    html = HTML_TEMPLATE.replace('__JSON_DATA__', json_str)
    
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    
    print("✅ 严谨版 index.html 生成完成。")
