import pandas as pd
import json
import os
import glob
import re

# ================= 配置区域 =================

# 1. 仓库清单 (Key=邮编)
WAREHOUSES = {
    "60632": {"name": "SureGo美中芝加哥-60632仓", "region": "CENTRAL"},
    "91730": {"name": "SureGo美西库卡蒙格-91730新仓", "region": "WEST"},
    "91752": {"name": "SureGo美西米拉罗马-91752仓", "region": "WEST"},
    "08691": {"name": "SureGo美东新泽西-08691仓", "region": "EAST"},
    "06801": {"name": "SureGo美东贝塞尔-06801仓", "region": "EAST"},
    "11791": {"name": "SureGo美东长岛-11791仓", "region": "EAST"},
    "07032": {"name": "SureGo美东新泽西-07032仓", "region": "EAST"},
    "63461": {"name": "SureGo退货检测-美中密苏里63461退货仓", "region": "CENTRAL"} # 仅显示，暂无报价
}

# 2. 渠道配置
# type: 'standard' (普通表), 'split' (商/住分栏), 'xlmiles' (特殊行结构)
# fuel_discount: 1.0 (无折扣), 0.85 (八五折)
CHANNEL_CONFIG = {
    "GOFO-报价": {
        "type": "standard", 
        "wh": ["91730", "60632"], 
        "fuel_discount": 1.0,
        "sheet_keyword": "GOFO-报价",
        "loc": {"zone_start_col": 2, "weight_col": 0, "header_row": 2} # C列是Zone1(index 2)
    },
    "GOFO、UNIUNI-MT-报价": {
        "type": "standard", 
        "wh": ["91730", "60632"], 
        "fuel_discount": 1.0,
        "sheet_keyword": "GOFO、UNIUNI-MT-报价",
        "loc": {"zone_start_col": 2, "weight_col": 0, "header_row": 2} # 取左侧 GOFO 表格
    },
    "USPS-YSD-报价": {
        "type": "standard", 
        "wh": ["91730", "60632"], 
        "fuel_discount": 1.0,
        "sheet_keyword": "USPS-YSD-报价",
        "loc": {"zone_start_col": 3, "weight_col": 1, "header_row": 3} # D列Zone1(index 3), LB在B列(index 1)
    },
    "FedEx-ECO-MT报价": {
        "type": "standard", 
        "wh": ["91730", "60632", "08691"], 
        "fuel_discount": 1.0,
        "sheet_keyword": "FedEx-ECO-MT报价",
        "loc": {"zone_start_col": 2, "weight_col": 0, "header_row": 2} # C列Zone2(index 2), LB在A列(index 0)
    },
    "FedEx-632-MT-报价": {
        "type": "split", 
        "wh": ["91730", "60632", "08691", "06801", "11791", "07032"], 
        "fuel_discount": 0.85, # 燃油八五折
        "sheet_keyword": "FedEx-632-MT-报价",
        "loc": {
            "res_zone_start": 2, "res_weight": 0,  # 住宅 C列
            "com_zone_start": 12, "com_weight": 10, # 商业 M列
            "header_row": 2
        }
    },
    "FedEx-MT-超大包裹-报价": {
        "type": "split", 
        "wh": ["91730", "60632", "08691", "06801", "11791", "07032"], 
        "fuel_discount": 0.85, # 燃油八五折
        "sheet_keyword": "FedEx-MT-超大包裹-报价",
        "loc": {
            "res_zone_start": 2, "res_weight": 0,
            "com_zone_start": 12, "com_weight": 10,
            "header_row": 2
        }
    },
    "FedEx-MT-危险品-报价": {
        "type": "split", 
        "wh": ["60632", "08691", "06801", "11791", "07032"], 
        "fuel_discount": 1.0,
        "sheet_keyword": "FedEx-MT-危险品-报价",
        "loc": {
            "res_zone_start": 2, "res_weight": 0,
            "com_zone_start": 12, "com_weight": 10,
            "header_row": 2
        }
    },
    "GOFO大件-MT-报价": {
        "type": "split", 
        "wh": ["91730", "08691", "06801", "11791", "07032"], 
        "fuel_discount": 1.0,
        "sheet_keyword": "GOFO大件-MT-报价",
        "loc": {
            "res_zone_start": 2, "res_weight": 0,
            "com_zone_start": 12, "com_weight": 10,
            "header_row": 2
        }
    },
    "XLmiles-报价": {
        "type": "xlmiles",
        "wh": ["91730"], 
        "fuel_discount": 1.0,
        "sheet_keyword": "XLmiles-报价"
    }
}

# 3. 杂费配置 (Residential, Signature) - 单位: USD
FEES_OVERRIDE = {
    "FedEx-632-MT-报价":      {"res": 2.61, "sig": 4.37},
    "FedEx-MT-超大包裹-报价":  {"res": 2.61, "sig": 4.37},
    "FedEx-MT-危险品-报价":    {"res": 3.32, "sig": 9.71},
    "GOFO大件-MT-报价":        {"res": 2.93, "sig": 0}, # 不支持签名或含在内
    "XLmiles-报价":           {"res": 0,    "sig": 10.20} # 通常含住宅
}

# ================= 逻辑函数 =================

def safe_float(val):
    try:
        if isinstance(val, str):
            val = val.replace('$', '').replace(',', '').strip()
        return float(val)
    except:
        return 0.0

def get_sheet_by_keyword(excel_path, keyword):
    """根据关键词在Excel中查找Sheet"""
    try:
        # 优先尝试作为CSV读取 (适配环境上传的CSV)
        csv_name = f"{excel_path} - {keyword}.csv"
        if os.path.exists(csv_name):
            return pd.read_csv(csv_name, header=None)
        
        # 其次尝试读取Excel (适配实际仓库环境)
        if os.path.exists(excel_path):
            xls = pd.ExcelFile(excel_path)
            for sheet in xls.sheet_names:
                if keyword in sheet:
                    return pd.read_excel(excel_path, sheet_name=sheet, header=None)
    except Exception as e:
        print(f"Error reading {keyword} in {excel_path}: {e}")
    return None

def extract_fuel(df, channel_name):
    """提取燃油费率"""
    fuel = 0.0
    # 通用逻辑：尝试在表头上方或特定的“燃油”单元格查找
    # 对于 FedEx 表格，燃油通常在 Row 1 (index 1), Col 23 (X列) 附近
    try:
        # 遍历前几行查找 "燃油附加费" 或 "Fuel"
        found = False
        for r in range(5):
            for c in range(30):
                val = str(df.iloc[r, c])
                if "燃油" in val or "Fuel" in val:
                    # 尝试取右边一格
                    candidate = df.iloc[r, c+1]
                    try:
                        fuel = float(candidate)
                        found = True
                        break
                    except:
                        pass
            if found: break
    except:
        pass
    
    # 如果没找到，给个默认值（例如 16%），或者根据渠道写死
    if fuel == 0 and "FedEx" in channel_name:
        fuel = 0.16 
    if fuel > 1: fuel = fuel / 100.0 # 修正百分比
    
    return fuel

def parse_standard_table(df, loc):
    """解析标准 Zone 表 (Rows: Weight, Cols: Zone)"""
    rates = []
    header_row = loc['header_row']
    start_col = loc['zone_start_col']
    weight_col = loc['weight_col']
    
    # 确定最大行
    max_rows = len(df)
    
    for r in range(header_row + 1, max_rows):
        row_data = df.iloc[r]
        try:
            w_val = row_data[weight_col]
            if pd.isna(w_val): continue
            
            # 处理重量字符串 "1 OZ" -> 0.0625 LB
            w_str = str(w_val).upper()
            weight = 0.0
            if "OZ" in w_str:
                weight = safe_float(w_str.replace("OZ", "")) / 16.0
            else:
                weight = safe_float(w_str.replace("LB", "").replace("LBS", ""))
            
            if weight == 0: continue
            
            row_rates = {}
            # 假设 Zone 1-9 (最多)
            for z in range(1, 10):
                # 列索引计算：Zone 1 对应 start_col, Zone 2 对应 start_col + 1...
                # 需要根据实际 header 判断当前列是不是该 Zone
                # 简单起见，假设连续
                col_idx = start_col + (z - 1)
                # 某些表 Zone 2 开始 (FedEx)
                if "FedEx" in str(df.iloc[header_row, start_col]): # 如果表头是 Zone 2
                     col_idx = start_col + (z - 2)
                
                # 边界检查
                if col_idx < 0 or col_idx >= len(row_data): continue
                
                price = safe_float(row_data[col_idx])
                if price > 0:
                    row_rates[f"zone{z}"] = price
            
            if row_rates:
                rates.append({"weight": weight, "prices": row_rates})
                
        except Exception as e:
            continue
            
    return rates

def parse_split_table(df, loc):
    """解析左右分栏表 (左住宅，右商业)"""
    res_rates = parse_standard_table(df, {
        "header_row": loc['header_row'],
        "zone_start_col": loc['res_zone_start'],
        "weight_col": loc['res_weight']
    })
    com_rates = parse_standard_table(df, {
        "header_row": loc['header_row'],
        "zone_start_col": loc['com_zone_start'],
        "weight_col": loc['com_weight']
    })
    return {"residential": res_rates, "commercial": com_rates}

def parse_xlmiles(df):
    """专门解析 XLmiles 特殊结构"""
    # AH: Rows C4-C8 (3-7), Zones D3-G3 (Zone 1,2,3,6)
    # OS: Rows C9-C11 (8-10)
    # OM: Rows C12-C13 (11-12)
    # Weight col: C (2)
    # Zone cols: D(3)=Z1, E(4)=Z2, F(5)=Z3, G(6)=Z6
    
    # 映射表头列到Zone
    zone_map = {3: 1, 4: 2, 5: 3, 6: 6}
    
    sections = [
        {"name": "AH", "rows": range(3, 8)},
        {"name": "OS", "rows": range(8, 11)},
        {"name": "OM", "rows": range(11, 13)}
    ]
    
    rates = []
    
    for sec in sections:
        for r in sec["rows"]:
            try:
                if r >= len(df): break
                w_raw = str(df.iloc[r, 2]) # C列
                # 提取数字 "0<重量<=70" -> 取 70? 或者是上限。
                # 简单提取字符串中的最大数字作为 key weight
                nums = re.findall(r"[-+]?\d*\.\d+|\d+", w_raw)
                if not nums: continue
                weight = float(nums[-1]) # 取最后一个数字作为重量上限
                
                row_price = {}
                for col_idx, z_num in zone_map.items():
                    p = safe_float(df.iloc[r, col_idx])
                    if p > 0:
                        row_price[f"zone{z_num}"] = p
                
                if row_price:
                    rates.append({
                        "type": sec["name"],
                        "weight": weight,
                        "prices": row_price
                    })
            except:
                pass
    return rates

def extract_data():
    all_data = {}
    files = ['T0', 'T1', 'T2', 'T3']
    
    for t in files:
        print(f"Processing {t}...")
        t_data = {"channels": {}}
        
        # 构造文件名 (支持 csv 或 xlsx)
        # 实际代码中，我们主要寻找 data/T0.xlsx，如果不存在则找 csv
        base_path = f"data/{t}.xlsx"
        if not os.path.exists(base_path) and os.path.exists(f"{t}.xlsx"):
            base_path = f"{t}.xlsx" # 兼容当前目录
        
        # 遍历渠道
        for ch_name, cfg in CHANNEL_CONFIG.items():
            df = get_sheet_by_keyword(t if os.path.exists(f"{t}.xlsx - {ch_name}.csv") else base_path, cfg['sheet_keyword'])
            if df is None or df.empty:
                print(f"  Skipping {ch_name} (Not found)")
                continue
            
            # 1. 提取燃油
            fuel_raw = extract_fuel(df, ch_name)
            
            # 2. 应用折扣
            fuel_final = fuel_raw
            if cfg.get("fuel_discount") == 0.85:
                fuel_final = fuel_raw * 0.85
                print(f"  {ch_name}: Fuel {fuel_raw:.4f} -> 85% Discount -> {fuel_final:.4f}")
            
            # 3. 提取费率
            parsed_rates = None
            if cfg['type'] == 'standard':
                parsed_rates = parse_standard_table(df, cfg['loc'])
            elif cfg['type'] == 'split':
                parsed_rates = parse_split_table(df, cfg['loc'])
            elif cfg['type'] == 'xlmiles':
                parsed_rates = parse_xlmiles(df)
            
            # 4. 获取杂费覆盖
            fees = FEES_OVERRIDE.get(ch_name, {"res": 0, "sig": 0})
            
            t_data["channels"][ch_name] = {
                "fuel_rate": fuel_final,
                "fuel_original": fuel_raw, # 记录原价以便前端展示说明
                "rates": parsed_rates,
                "fees": fees,
                "type": cfg['type']
            }
            
        all_data[t] = t_data

    return all_data

if __name__ == "__main__":
    if not os.path.exists('public'):
        os.makedirs('public')
        
    print("Starting extraction...")
    data = extract_data()
    
    final_output = {
        "warehouses": WAREHOUSES,
        "config": CHANNEL_CONFIG,
        "pricing": data
    }
    
    with open('public/data.json', 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)
    
    print("Done! public/data.json generated.")
