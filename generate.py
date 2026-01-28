import pandas as pd
import json
import os
import re

# ================= 1. 基础配置 =================
WAREHOUSES = {
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
        "type": "standard", 
        "wh": ["91730", "60632"], 
        "fuel_discount": 1.0,
        "sheet_keyword": "GOFO-报价",
        "loc": {"zone_start_col": 2, "weight_col": 0, "header_row": 2}
    },
    "GOFO、UNIUNI-MT-报价": {
        "type": "standard", 
        "wh": ["91730", "60632"], 
        "fuel_discount": 1.0,
        "sheet_keyword": "GOFO、UNIUNI-MT-报价",
        "loc": {"zone_start_col": 2, "weight_col": 0, "header_row": 2}
    },
    "USPS-YSD-报价": {
        "type": "standard", 
        "wh": ["91730", "60632"], 
        "fuel_discount": 1.0,
        "sheet_keyword": "USPS-YSD-报价",
        "loc": {"zone_start_col": 3, "weight_col": 1, "header_row": 3}
    },
    "FedEx-ECO-MT报价": {
        "type": "standard", 
        "wh": ["91730", "60632", "08691"], 
        "fuel_discount": 1.0,
        "sheet_keyword": "FedEx-ECO-MT报价",
        "loc": {"zone_start_col": 2, "weight_col": 0, "header_row": 2}
    },
    "FedEx-632-MT-报价": {
        "type": "split", 
        "wh": ["91730", "60632", "08691", "06801", "11791", "07032"], 
        "fuel_discount": 0.85, 
        "sheet_keyword": "FedEx-632-MT-报价",
        "loc": {"res_zone_start": 2, "res_weight": 0, "com_zone_start": 12, "com_weight": 10, "header_row": 2}
    },
    "FedEx-MT-超大包裹-报价": {
        "type": "split", 
        "wh": ["91730", "60632", "08691", "06801", "11791", "07032"], 
        "fuel_discount": 0.85, 
        "sheet_keyword": "FedEx-MT-超大包裹-报价",
        "loc": {"res_zone_start": 2, "res_weight": 0, "com_zone_start": 12, "com_weight": 10, "header_row": 2}
    },
    "FedEx-MT-危险品-报价": {
        "type": "split", 
        "wh": ["60632", "08691", "06801", "11791", "07032"], 
        "fuel_discount": 1.0,
        "sheet_keyword": "FedEx-MT-危险品-报价",
        "loc": {"res_zone_start": 2, "res_weight": 0, "com_zone_start": 12, "com_weight": 10, "header_row": 2}
    },
    "GOFO大件-MT-报价": {
        "type": "split", 
        "wh": ["91730", "08691", "06801", "11791", "07032"], 
        "fuel_discount": 1.0,
        "sheet_keyword": "GOFO大件-MT-报价",
        "loc": {"res_zone_start": 2, "res_weight": 0, "com_zone_start": 12, "com_weight": 10, "header_row": 2}
    },
    "XLmiles-报价": {
        "type": "xlmiles",
        "wh": ["91730"], 
        "fuel_discount": 1.0,
        "sheet_keyword": "XLmiles-报价"
    }
}

FEES_OVERRIDE = {
    "FedEx-632-MT-报价":      {"res": 2.61, "sig": 4.37},
    "FedEx-MT-超大包裹-报价":  {"res": 2.61, "sig": 4.37},
    "FedEx-MT-危险品-报价":    {"res": 3.32, "sig": 9.71},
    "GOFO大件-MT-报价":        {"res": 2.93, "sig": 0}, 
    "XLmiles-报价":           {"res": 0,    "sig": 10.20}
}

# HTML 模板 (直接内嵌)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SureGo 运费计算器</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
</head>
<body class="bg-gray-50 min-h-screen">
    <div id="app" class="max-w-4xl mx-auto p-4">
        <header class="mb-6 text-center">
            <h1 class="text-3xl font-bold text-blue-800">SureGo 运费计算器</h1>
            <p class="text-gray-500 text-sm mt-1">2025新年版 | 含燃油85折优惠</p>
        </header>

        <div class="bg-white rounded-lg shadow-md p-6 mb-6 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">发货仓库</label>
                <select v-model="selectedWarehouse" @change="updateAvailableChannels" class="w-full border-gray-300 rounded-md shadow-sm border p-2">
                    <option value="">请选择仓库...</option>
                    <option v-for="(info, code) in warehouses" :key="code" :value="code">
                        {{ info.name }}
                    </option>
                </select>
                <p class="text-xs text-gray-400 mt-1" v-if="selectedWarehouse">
                    区域: {{ warehouses[selectedWarehouse].region }}
                </p>
            </div>

            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">物流渠道</label>
                <select v-model="selectedChannel" class="w-full border-gray-300 rounded-md shadow-sm border p-2" :disabled="!selectedWarehouse">
                    <option value="">请选择渠道...</option>
                    <option v-for="ch in availableChannels" :key="ch" :value="ch">
                        {{ ch }}
                    </option>
                </select>
            </div>

            <div class="col-span-1 md:col-span-2 grid grid-cols-2 md:grid-cols-4 gap-4 bg-gray-50 p-3 rounded">
                <div>
                    <label class="block text-xs font-bold text-gray-500">重量 (LB)</label>
                    <input type="number" v-model.number="weight" class="w-full border p-1 rounded" step="0.1" min="0">
                </div>
                <div>
                    <label class="block text-xs font-bold text-gray-500">分区 (Zone)</label>
                    <select v-model.number="zone" class="w-full border p-1 rounded">
                        <option v-for="z in 9" :key="z" :value="z">Zone {{ z }}</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-bold text-gray-500">地址类型</label>
                    <select v-model="addressType" class="w-full border p-1 rounded">
                        <option value="residential">住宅 (Residential)</option>
                        <option value="commercial">商业 (Commercial)</option>
                    </select>
                </div>
                <div class="flex items-center pt-4">
                    <input type="checkbox" v-model="needSignature" id="sig" class="mr-2">
                    <label for="sig" class="text-sm">需要签名</label>
                </div>
            </div>
            
            <div class="col-span-1 md:col-span-2">
                <label class="block text-xs text-gray-400">价格周期</label>
                <div class="flex space-x-4">
                    <label v-for="t in ['T0','T1','T2','T3']" :key="t" class="inline-flex items-center cursor-pointer">
                        <input type="radio" v-model="timePeriod" :value="t" class="text-blue-600">
                        <span class="ml-1 text-sm">{{ t }}</span>
                    </label>
                </div>
            </div>
        </div>

        <div v-if="result" class="bg-blue-50 border border-blue-200 rounded-lg p-6 shadow-sm">
            <div class="flex justify-between items-end mb-4 border-b border-blue-200 pb-2">
                <h2 class="text-xl font-bold text-blue-900">预估运费: <span class="text-3xl text-red-600">${{ result.total.toFixed(2) }}</span></h2>
                <div class="text-right text-xs text-gray-500">
                    <div v-if="result.fuelDiscountApplied" class="text-green-600 font-bold">★ 已应用燃油85折</div>
                    <div>应用燃油费率: {{ (result.fuelRate * 100).toFixed(2) }}%</div>
                </div>
            </div>
            <div class="grid grid-cols-2 gap-y-2 text-sm text-gray-700">
                <div class="flex justify-between"><span>基础运费:</span> <span>${{ result.base.toFixed(2) }}</span></div>
                <div class="flex justify-between" v-if="result.resFee > 0"><span>住宅费:</span> <span>${{ result.resFee.toFixed(2) }}</span></div>
                <div class="flex justify-between" v-if="result.sigFee > 0"><span>签名费:</span> <span>${{ result.sigFee.toFixed(2) }}</span></div>
                <div class="flex justify-between text-blue-600"><span>燃油费:</span> <span>${{ result.fuelCost.toFixed(2) }}</span></div>
            </div>
        </div>
        <div v-else-if="selectedChannel" class="text-center text-gray-400 py-8">
            未找到对应报价，请检查重量或Zone。
        </div>
    </div>

    <script>
        const { createApp } = Vue;
        createApp({
            data() { return { warehouses: {}, config: {}, pricing: {}, selectedWarehouse: '', selectedChannel: '', availableChannels: [], weight: 1, zone: 2, addressType: 'residential', needSignature: false, timePeriod: 'T0' } },
            async mounted() {
                try {
                    const res = await fetch('data.json');
                    const data = await res.json();
                    this.warehouses = data.warehouses;
                    this.config = data.config;
                    this.pricing = data.pricing;
                } catch(e) { console.error(e); }
            },
            computed: {
                result() {
                    if (!this.selectedChannel || !this.selectedWarehouse || !this.pricing[this.timePeriod]) return null;
                    const periodData = this.pricing[this.timePeriod].channels[this.selectedChannel];
                    if (!periodData) return null;
                    
                    let basePrice = 0;
                    let rates = periodData.rates;
                    
                    if (periodData.type === 'xlmiles') {
                        const candidates = rates.filter(r => this.weight <= r.weight && r.prices[`zone${this.zone}`]);
                        if (candidates.length > 0) basePrice = candidates[0].prices[`zone${this.zone}`];
                    } else if (periodData.type === 'split') {
                        const table = this.addressType === 'residential' ? rates.residential : rates.commercial;
                        const match = table.find(r => r.weight >= this.weight);
                        if (match && match.prices[`zone${this.zone}`]) basePrice = match.prices[`zone${this.zone}`];
                    } else {
                        const match = rates.find(r => r.weight >= this.weight);
                        if (match && match.prices[`zone${this.zone}`]) basePrice = match.prices[`zone${this.zone}`];
                    }
                    
                    if (!basePrice) return null;
                    
                    let resFee = (this.addressType === 'residential') ? (periodData.fees.res || 0) : 0;
                    let sigFee = this.needSignature ? (periodData.fees.sig || 0) : 0;
                    let fuelRate = periodData.fuel_rate;
                    
                    let subtotal = basePrice + resFee + sigFee;
                    let fuelCost = subtotal * fuelRate;
                    
                    return {
                        base: basePrice, resFee, sigFee, fuelRate, fuelCost,
                        total: subtotal + fuelCost,
                        fuelDiscountApplied: this.config[this.selectedChannel].fuel_discount < 1
                    };
                }
            },
            methods: {
                updateAvailableChannels() {
                    this.selectedChannel = '';
                    if (!this.selectedWarehouse) { this.availableChannels = []; return; }
                    this.availableChannels = Object.keys(this.config).filter(k => this.config[k].wh.includes(this.selectedWarehouse));
                }
            }
        }).mount('#app');
    </script>
</body>
</html>
"""

# ================= 2. 逻辑函数 =================

def safe_float(val):
    try:
        # 核心修正：显式处理空值
        if pd.isna(val) or val is None: return 0.0
        
        if isinstance(val, str):
            val = val.replace('$', '').replace(',', '').strip()
            if not val: return 0.0
        
        f = float(val)
        if pd.isna(f): return 0.0
        return f
    except:
        return 0.0

def get_sheet_by_keyword(excel_path, keyword):
    try:
        csv_name = f"{excel_path} - {keyword}.csv"
        if os.path.exists(csv_name):
            return pd.read_csv(csv_name, header=None)
        if os.path.exists(excel_path):
            xls = pd.ExcelFile(excel_path)
            for sheet in xls.sheet_names:
                if keyword in sheet:
                    return pd.read_excel(excel_path, sheet_name=sheet, header=None)
    except Exception as e:
        print(f"Error reading {keyword}: {e}")
    return None

def extract_fuel(df, channel_name):
    """智能搜索燃油费率"""
    fuel = 0.0
    found = False
    
    # 扩大搜索范围，并增强容错
    for r in range(min(5, len(df))):
        for c in range(min(30, df.shape[1])):
            try:
                val = str(df.iloc[r, c])
                if "燃油" in val or "Fuel" in val:
                    # 尝试取右侧单元格
                    candidate = df.iloc[r, c+1]
                    f_val = safe_float(candidate)
                    if f_val > 0:
                        fuel = f_val
                        found = True
                        break
            except: pass
        if found: break
    
    # 默认值兜底 (如果文件里没写或读取失败，给一个默认值防止NaN)
    if fuel == 0 and "FedEx" in channel_name:
        fuel = 0.16 # 默认16%
    
    # 百分比修正
    if fuel > 1: fuel = fuel / 100.0
    
    return fuel

def parse_standard_table(df, loc):
    rates = []
    header_row = loc['header_row']
    start_col = loc['zone_start_col']
    weight_col = loc['weight_col']
    
    for r in range(header_row + 1, len(df)):
        try:
            row_data = df.iloc[r]
            w_str = str(row_data[weight_col]).upper()
            if "OZ" in w_str: weight = safe_float(w_str.replace("OZ", "")) / 16.0
            else: weight = safe_float(w_str.replace("LB", "").replace("LBS", ""))
            
            if weight == 0: continue
            
            row_rates = {}
            header_txt = str(df.iloc[header_row, start_col])
            start_z_num = 2 if "2" in header_txt else 1
            
            for z in range(1, 10):
                if z < start_z_num: continue
                col_idx = start_col + (z - start_z_num)
                if col_idx < len(row_data):
                    p = safe_float(row_data[col_idx])
                    if p > 0: row_rates[f"zone{z}"] = p
            
            if row_rates: rates.append({"weight": weight, "prices": row_rates})
        except: pass
    return rates

def parse_split_table(df, loc):
    res = parse_standard_table(df, {"header_row":loc['header_row'], "zone_start_col":loc['res_zone_start'], "weight_col":loc['res_weight']})
    com = parse_standard_table(df, {"header_row":loc['header_row'], "zone_start_col":loc['com_zone_start'], "weight_col":loc['com_weight']})
    return {"residential": res, "commercial": com}

def parse_xlmiles(df):
    zone_map = {3: 1, 4: 2, 5: 3, 6: 6}
    rates = []
    for r in range(len(df)):
        try:
            col2 = str(df.iloc[r, 2])
            if "重量" in col2 and ("<" in col2 or "≤" in col2):
                nums = re.findall(r"[-+]?\d*\.\d+|\d+", col2)
                if nums:
                    weight = float(nums[-1])
                    prices = {}
                    for c_idx, z_num in zone_map.items():
                        p = safe_float(df.iloc[r, c_idx])
                        if p > 0: prices[f"zone{z_num}"] = p
                    if prices:
                        rates.append({"weight": weight, "prices": prices})
        except: pass
    return rates

# ================= 3. 主程序 =================
def main():
    if not os.path.exists('public'): os.makedirs('public')
    
    all_data = {}
    for t in ['T0', 'T1', 'T2', 'T3']:
        print(f"Processing {t}...")
        t_data = {"channels": {}}
        base_path = f"data/{t}.xlsx"
        if not os.path.exists(base_path): base_path = f"{t}.xlsx" 
        
        for name, cfg in CHANNEL_CONFIG.items():
            df = get_sheet_by_keyword(base_path, cfg['sheet_keyword'])
            if df is None or df.empty: continue
            
            fuel = extract_fuel(df, name)
            if cfg['fuel_discount'] < 1:
                fuel_final = fuel * cfg['fuel_discount']
                print(f"  {name}: Fuel {fuel:.4f} -> 85% Discount -> {fuel_final:.4f}")
                fuel = fuel_final
            
            if cfg['type'] == 'standard': rates = parse_standard_table(df, cfg['loc'])
            elif cfg['type'] == 'split': rates = parse_split_table(df, cfg['loc'])
            elif cfg['type'] == 'xlmiles': rates = parse_xlmiles(df)
            else: rates = []
            
            t_data["channels"][name] = {
                "fuel_rate": fuel,
                "rates": rates,
                "fees": FEES_OVERRIDE.get(name, {"res":0, "sig":0}),
                "type": cfg['type']
            }
        all_data[t] = t_data
        
    with open('public/data.json', 'w', encoding='utf-8') as f:
        json.dump({"warehouses": WAREHOUSES, "config": CHANNEL_CONFIG, "pricing": all_data}, f, ensure_ascii=False)
    
    with open('public/index.html', 'w', encoding='utf-8') as f:
        f.write(HTML_TEMPLATE)
        
    print("Done! public/data.json and public/index.html generated.")

if __name__ == "__main__":
    main()
