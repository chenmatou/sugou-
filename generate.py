<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>一件代发综合运费计算器 (V2.4 精准定位版)</title>
    <style>
        :root {
            --primary-color: #0056b3;
            --bg-color: #f4f7f6;
            --highlight-color: #fff8c5;
            --danger-color: #dc3545;
            --success-color: #28a745;
            --warning-color: #ffc107;
            --purple-color: #6f42c1;
        }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: var(--bg-color); padding: 20px; }
        .container { max-width: 1280px; margin: 0 auto; background: #fff; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1); border-radius: 8px; }
        h2, h3 { color: #333; border-bottom: 2px solid var(--primary-color); padding-bottom: 10px; }

        /* 布局 */
        .grid-section { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .control-group { margin-bottom: 12px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; font-size: 13px; }
        input, select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }

        /* 燃油费 */
        .fuel-row { display: flex; gap: 10px; align-items: flex-end; }
        .fuel-input-box { flex: 1; }
        .fuel-link { font-size: 11px; margin-top: 3px; display: block; text-decoration: none; color: var(--primary-color); }

        /* 按钮与开关区域 (紧凑设计) */
        .action-bar {
            display: flex; flex-wrap: wrap; gap: 20px; align-items: center;
            background: #fff5f5; padding: 10px; border: 1px solid #ffdcdc; border-radius: 8px; margin-bottom: 20px;
        }
        .toggle-item { display: flex; align-items: center; gap: 8px; font-size: 14px; cursor: pointer; }
        .toggle-item input { width: auto; margin: 0; cursor: pointer; transform: scale(1.2); }
        .toggle-peak { color: #d9534f; font-weight: bold; }
        .toggle-self { color: var(--purple-color); font-weight: bold; }

        .btn-group { display: flex; gap: 10px; margin-top: 10px; width: 100%; }
        button { padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; color: #fff; flex: 1; }
        .btn-calc { background-color: var(--primary-color); }
        .btn-clear { background-color: #6c757d; }
        .btn-calc:hover { background-color: #004494; }

        /* 费用明细折叠 */
        details { background: #e9ecef; padding: 10px; border-radius: 4px; margin-bottom: 20px; }
        summary { cursor: pointer; font-weight: bold; color: var(--primary-color); font-size: 14px; }
        .fee-table { width: 100%; font-size: 11px; margin-top: 10px; border-collapse: collapse; }
        .fee-table th, .fee-table td { border: 1px solid #ccc; padding: 4px; text-align: center; }
        .fee-table th { background: #dee2e6; }

        /* 结果表格 */
        .result-table-wrapper { overflow-x: auto; margin-top: 20px; }
        table.main-table { width: 100%; border-collapse: collapse; min-width: 1000px; }
        .main-table th, .main-table td { border: 1px solid #ddd; padding: 8px; text-align: center; font-size: 14px; }
        .main-table th { background-color: var(--primary-color); color: white; }
        .main-table tr:nth-child(even) { background-color: #f9f9f9; }
        .highlight-zone { background-color: var(--highlight-color) !important; border: 2px solid #ffc107 !important; font-weight: bold; }

        /* 信息面板 */
        .location-panel { background: #e3f2fd; border: 1px solid #90caf9; padding: 8px; border-radius: 4px; margin-top: 5px; font-size: 12px; color: #0d47a1; display: none; }
        .status-panel { grid-column: 1 / -1; background: #fff; border: 1px solid #ddd; padding: 8px; border-radius: 4px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
        .status-badge { padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; color: #fff; background-color: #ccc; }
        .bg-ok { background-color: var(--success-color); }
        .bg-warn { background-color: var(--warning-color); color: #333; }
        .bg-err { background-color: var(--danger-color); }
    </style>
</head>
<body>

<div class="container">
    <h2>一件代发综合运费计算器 V2.4 (精准定位版)</h2>

    <details>
        <summary>点击查看：出库费与自提费明细表 (0 - 150LB+)</summary>
        <div style="max-height: 300px; overflow-y: auto;">
            <table class="fee-table">
                <thead>
                    <tr>
                        <th rowspan="2">重量段 (LB)</th>
                        <th colspan="2">6.0 (T0/VIP)</th>
                        <th colspan="2">6.1 (T1)</th>
                        <th colspan="2">6.2 (T2)</th>
                        <th colspan="2">6.3 (T3/常规)</th>
                    </tr>
                    <tr>
                        <th>出库</th><th>自提</th><th>出库</th><th>自提</th><th>出库</th><th>自提</th><th>出库</th><th>自提</th>
                    </tr>
                </thead>
                <tbody id="opFeeListBody"></tbody>
            </table>
        </div>
    </details>

    <div class="grid-section" style="background: #e9ecef; padding: 15px; border-radius: 5px;">
        <div class="control-group">
            <label>发货仓库 (影响分区计算)</label>
            <select id="warehouseOrigin" onchange="detectZone()">
                <option value="917">美西 - 洛杉矶 (917xx)</option>
                <option value="606">美中 - 芝加哥 (606xx)</option>
                <option value="088">美东 - 新泽西 (088xx)</option>
            </select>
        </div>

        <div class="control-group">
            <label>客户等级</label>
            <select id="priceTier">
                <option value="6.0">6.0 - T1VIP (T0)</option>
                <option value="6.1">6.1 - T1标准 (T1)</option>
                <option value="6.2">6.2 - T2客户 (T2)</option>
                <option value="6.3" selected>6.3 - 常规报价 (T3)</option>
            </select>
        </div>

        <div class="control-group">
            <label>收件邮编 (Destination Zip)</label>
            <input type="text" id="zipCode" placeholder="输入5位邮编 (如 10001)" oninput="detectZone()" maxlength="5">
            <div id="locationInfoBox" class="location-panel">
                <span style="font-weight:bold">📍 地点:</span> <span id="loc_state">--</span><br>
                <span style="font-weight:bold">🚚 分区:</span> <span id="loc_zone" style="color:#d9534f; font-weight:bold; font-size:1.1em">--</span><br>
                <span id="loc_type" style="color:#666"></span>
            </div>
        </div>

        <div class="control-group">
            <label>地址类型</label>
            <select id="addressType">
                <option value="residential">住宅地址 (Residential)</option>
                <option value="commercial">商业地址 (Commercial)</option>
            </select>
        </div>

        <div class="control-group">
            <label>燃油附加费率 (%)</label>
            <div class="fuel-row">
                <div class="fuel-input-box">
                    <input type="number" id="fuelFedEx" value="16.0" step="0.1" placeholder="FedEx">
                    <a href="https://www.fedex.com/en-us/shipping/fuel-surcharge.html" target="_blank" class="fuel-link">FedEx燃油 &nearr;</a>
                </div>
                <div class="fuel-input-box">
                    <input type="number" id="fuelUSPS" value="0.0" step="0.1" placeholder="USPS">
                    <a href="https://pe.usps.com/PriceChange" target="_blank" class="fuel-link">USPS燃油 &nearr;</a>
                </div>
            </div>
        </div>
    </div>

    <div class="action-bar">
        <label class="toggle-item toggle-peak">
            <input type="checkbox" id="peakMode">
            <span>开启旺季附加费 (Peak/AHS)</span>
        </label>
        <div style="width: 1px; height: 20px; background: #ccc; margin: 0 10px;"></div>
        <label class="toggle-item toggle-self">
            <input type="checkbox" id="selfPickupMode" onchange="toggleSelfPickup()">
            <span>开启自提 (Self-Pickup)</span>
        </label>
    </div>

    <h3>产品信息录入</h3>
    <div class="control-group" style="width: 200px;">
        <label>计量单位</label>
        <select id="unitSystem" onchange="toggleUnits()">
            <option value="cm_kg">公制 (cm / kg)</option>
            <option value="in_lb">英制 (inch / lb)</option>
        </select>
    </div>

    <div class="grid-section">
        <div class="control-group"><label id="lbl_l">长 (cm)</label><input type="number" id="length" placeholder="0" oninput="liveCalc()"></div>
        <div class="control-group"><label id="lbl_w">宽 (cm)</label><input type="number" id="width" placeholder="0" oninput="liveCalc()"></div>
        <div class="control-group"><label id="lbl_h">高 (cm)</label><input type="number" id="height" placeholder="0" oninput="liveCalc()"></div>
        <div class="control-group"><label id="lbl_weight">实重 (kg)</label><input type="number" id="actualWeight" placeholder="0" oninput="liveCalc()"></div>

        <div class="status-panel" id="productStatusBox">
            <span class="status-badge" id="badge_weight">重量: --</span>
            <span class="status-badge" id="badge_size">尺寸: --</span>
            <span class="status-badge" id="badge_girth">围长: --</span>
            <span class="status-badge" id="badge_final">综合: 待输入</span>
        </div>
    </div>

    <div id="calcDisplay" class="grid-section" style="background: #fff; border: 1px solid #ddd; padding: 10px;">
        <div><strong>体积重:</strong> <span id="disp_vol_w">0</span></div>
        <div><strong>计费重 (Final):</strong> <span id="disp_charge_w" style="color:red; font-size:1.2em;">0</span> <span class="unit-w">kg</span></div>
        <div><strong>围长 (L+2W+2H):</strong> <span id="disp_girth">0</span></div>
    </div>

    <div class="btn-group">
        <button class="btn-calc" onclick="calculateFinalPrices()">计算最终费用</button>
        <button class="btn-clear" onclick="clearInputs()">一键清空</button>
    </div>

    <h3>费用预估明细 <span id="zoneTitleBadge" style="font-size:0.8em; color:var(--primary-color)"></span></h3>
    <div class="result-table-wrapper">
        <table class="main-table" id="resultTable">
            <thead>
                <tr>
                    <th rowspan="2">渠道 / 服务</th>
                    <th rowspan="2">费用构成</th>
                    <th colspan="9">分区总价 (Zone 1 - 9)</th>
                </tr>
                <tr id="zoneHeader">
                    <th>Z1</th><th>Z2</th><th>Z3</th><th>Z4</th><th>Z5</th><th>Z6</th><th>Z7</th><th>Z8</th><th>Z9</th>
                </tr>
            </thead>
            <tbody></tbody>
        </table>
        <p style="font-size:12px; color:#666; margin-top:10px;" id="noteText">
            * <b>代发模式</b>: 费用 = 基础运费 + 燃油费 + 出库费 (不含自提费)。<br>
            * <b>自提模式</b>: 费用 = 出库费 + 自提费 (无运费/燃油)。<br>
            * <b>提示</b>: 邮编信息由公共API提供，仅供辅助参考。
        </p>
    </div>
</div>

<script>
    // --- 1. 数据配置 ---
    const opFeeData = [
        { lb: 0.99,  t0:{o:0.4, s:0.2}, t1:{o:0.4, s:0.3}, t2:{o:0.45, s:0.3}, t3:{o:0.5, s:0.3} },
        { lb: 4.99,  t0:{o:0.64, s:0.3}, t1:{o:0.64, s:0.5}, t2:{o:0.72, s:0.5}, t3:{o:0.8, s:0.5} },
        { lb: 9.99,  t0:{o:0.96, s:0.5}, t1:{o:0.96, s:0.8}, t2:{o:1.08, s:0.8}, t3:{o:1.2, s:0.8} },
        { lb: 19.99, t0:{o:1.2, s:0.6},  t1:{o:1.2, s:1.0},  t2:{o:1.35, s:1.0}, t3:{o:1.5, s:1.0} },
        { lb: 29.99, t0:{o:1.44, s:0.6}, t1:{o:1.44, s:1.2}, t2:{o:1.62, s:1.2}, t3:{o:1.8, s:1.2} },
        { lb: 39.99, t0:{o:1.68, s:0.6}, t1:{o:1.68, s:1.4}, t2:{o:1.89, s:1.4}, t3:{o:2.1, s:1.4} },
        { lb: 49.99, t0:{o:1.92, s:0.6}, t1:{o:1.92, s:1.6}, t2:{o:2.16, s:1.6}, t3:{o:2.4, s:1.6} },
        { lb: 59.99, t0:{o:2.16, s:1.0}, t1:{o:2.16, s:1.8}, t2:{o:2.43, s:1.8}, t3:{o:2.7, s:1.8} },
        { lb: 69.99, t0:{o:2.40, s:1.0}, t1:{o:2.40, s:2.0}, t2:{o:2.70, s:2.0}, t3:{o:3.0, s:2.0} },
        { lb: 79.99, t0:{o:2.88, s:1.5}, t1:{o:2.88, s:2.2}, t2:{o:3.24, s:2.2}, t3:{o:3.6, s:2.2} },
        { lb: 89.99, t0:{o:3.20, s:1.5}, t1:{o:3.20, s:2.4}, t2:{o:3.60, s:2.4}, t3:{o:4.0, s:2.4} },
        { lb: 99.99, t0:{o:3.52, s:2.0}, t1:{o:3.52, s:2.6}, t2:{o:3.96, s:2.6}, t3:{o:4.4, s:2.6} },
        { lb: 109.99,t0:{o:3.84, s:2.0}, t1:{o:3.84, s:2.8}, t2:{o:4.32, s:2.8}, t3:{o:4.8, s:2.8} },
        { lb: 119.99,t0:{o:4.16, s:2.5}, t1:{o:4.16, s:3.0}, t2:{o:4.68, s:3.0}, t3:{o:5.2, s:3.0} },
        { lb: 129.99,t0:{o:4.48, s:2.5}, t1:{o:4.48, s:3.0}, t2:{o:5.04, s:3.0}, t3:{o:5.6, s:3.0} },
        { lb: 149.99,t0:{o:4.80, s:3.0}, t1:{o:4.80, s:3.0}, t2:{o:5.40, s:3.0}, t3:{o:6.0, s:3.0} },
        { lb: 9999,  t0:{o:5.20, s:3.5}, t1:{o:5.20, s:3.5}, t2:{o:5.85, s:3.5}, t3:{o:6.5, s:3.5} }
    ];

    function initOpTable() {
        const tbody = document.getElementById('opFeeListBody');
        let prev = 0;
        opFeeData.forEach(r => {
            let label = r.lb >= 9999 ? '150 LB +' : `${prev} ~ ${r.lb}`;
            let row = `<tr>
                <td>${label}</td>
                <td>$${r.t0.o}</td><td>$${r.t0.s}</td>
                <td>$${r.t1.o}</td><td>$${r.t1.s}</td>
                <td>$${r.t2.o}</td><td>$${r.t2.s}</td>
                <td>$${r.t3.o}</td><td>$${r.t3.s}</td>
            </tr>`;
            tbody.innerHTML += row;
            prev = (r.lb + 0.01).toFixed(2);
        });
    }
    initOpTable();

    // --- 2. 增强版分区逻辑 (API + 离线兜底) ---

    function getStateFallback(prefix) {
        const p = parseInt(prefix);
        if (p >= 900 && p <= 961) return "CA (加州) [估算]";
        if (p >= 100 && p <= 149) return "NY (纽约) [估算]";
        if (p >= 600 && p <= 629) return "IL (伊利诺伊) [估算]";
        if (p >= 750 && p <= 799) return "TX (德州) [估算]";
        if (p >= 320 && p <= 349) return "FL (佛州) [估算]";
        if ((p >= 967 && p <= 969) || (p>=995)) return "AK/HI (偏远) [估算]";
        return "美国本土 (待查询)";
    }

    function calculateZoneMath(destZip, originType) {
        if (!destZip || destZip.length < 3) return 8;
        const p = parseInt(destZip.substring(0, 3));

        if ((p >= 967 && p <= 969) || (p >= 995 && p <= 999) || (destZip.startsWith('00'))) return 9;

        if (originType === '917') {
            if (p >= 900 && p <= 935) return 2;
            if (p >= 936 && p <= 961) return 3;
            if (p >= 890 && p <= 898) return 3;
            if (p >= 970 && p <= 994) return 4;
            if (p >= 840 && p <= 884) return 4;
            if (p >= 500 && p <= 799) return 6;
            if (p >= 0 && p <= 499) return 8;
        }
        else if (originType === '606') {
            if (p >= 600 && p <= 629) return 2;
            if (p >= 460 && p <= 569) return 3;
            if (p >= 400 && p <= 459) return 4;
            if (p >= 700 && p <= 799) return 4;
            if (p >= 200 && p <= 399) return 5;
            if (p >= 800 && p <= 899) return 6;
            if (p >= 0 && p <= 199) return 7;
            if (p >= 900 && p <= 966) return 8;
        }
        else if (originType === '088') {
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

    let detectedZoneVal = null;
    let locationRequestTimer = null;

    function detectZone() {
        const zip = document.getElementById('zipCode').value;
        const origin = document.getElementById('warehouseOrigin').value;
        const panel = document.getElementById('locationInfoBox');

        if (zip.length >= 3) {
            panel.style.display = 'block';

            let z = calculateZoneMath(zip, origin);
            detectedZoneVal = z;
            document.getElementById('loc_zone').innerText = `Zone ${z}`;

            let typeHint = "地址类型: 默认住宅";
            if (z === 9) {
                typeHint = "⚠️ 偏远/海岛地区";
                document.getElementById('loc_type').style.color = "red";
            } else {
                document.getElementById('loc_type').style.color = "#666";
            }
            document.getElementById('loc_type').innerText = typeHint;

            if (zip.length === 5) {
                document.getElementById('loc_state').innerText = "📍 查询中...";
                if(locationRequestTimer) clearTimeout(locationRequestTimer);

                locationRequestTimer = setTimeout(() => {
                    fetch(`https://api.zippopotam.us/us/${zip}`)
                        .then(resp => {
                            if(!resp.ok) throw new Error("Not Found");
                            return resp.json();
                        })
                        .then(data => {
                            const place = data.places[0];
                            const city = place['place name'];
                            const state = place['state abbreviation'];
                            document.getElementById('loc_state').innerText = `${state} - ${city}`;
                            if(state === 'HI' || state === 'AK' || state === 'PR') {
                                detectedZoneVal = 9;
                                document.getElementById('loc_zone').innerText = "Zone 9 (偏远)";
                                document.getElementById('loc_zone').style.color = "red";
                            } else {
                                document.getElementById('loc_zone').style.color = "#d9534f";
                            }
                        })
                        .catch(err => {
                            document.getElementById('loc_state').innerText = getStateFallback(zip.substring(0,3));
                        });
                }, 300);
            } else {
                document.getElementById('loc_state').innerText = getStateFallback(zip.substring(0,3));
            }

        } else {
            panel.style.display = 'none';
            detectedZoneVal = null;
        }
    }

    // --- 3. 基础计算与状态 ---
    let currentUnit = 'cm_kg';
    function toggleUnits() {
        currentUnit = document.getElementById('unitSystem').value;
        const isCM = currentUnit === 'cm_kg';
        document.getElementById('lbl_l').innerText = isCM ? '长 (cm)' : '长 (in)';
        document.getElementById('lbl_w').innerText = isCM ? '宽 (cm)' : '宽 (in)';
        document.getElementById('lbl_h').innerText = isCM ? '高 (cm)' : '高 (in)';
        document.getElementById('lbl_weight').innerText = isCM ? '实重 (kg)' : '实重 (lb)';
        document.querySelectorAll('.unit-w').forEach(e => e.innerText = isCM ? 'kg' : 'lb');
        liveCalc();
    }

    function toggleSelfPickup() {
        const isSelf = document.getElementById('selfPickupMode').checked;
        if(isSelf) {
            document.getElementById('zipCode').disabled = true;
            document.getElementById('fuelFedEx').disabled = true;
            document.getElementById('fuelUSPS').disabled = true;
            document.getElementById('warehouseOrigin').disabled = true;
        } else {
            document.getElementById('zipCode').disabled = false;
            document.getElementById('fuelFedEx').disabled = false;
            document.getElementById('fuelUSPS').disabled = false;
            document.getElementById('warehouseOrigin').disabled = false;
        }
        liveCalc();
    }

    function updateStatusBadge(id, text, status) {
        const el = document.getElementById(id);
        el.innerText = text;
        el.className = 'status-badge';
        if (status === 'ok') el.classList.add('bg-ok');
        else if (status === 'warn') el.classList.add('bg-warn');
        else if (status === 'err') el.classList.add('bg-err');
    }

    function liveCalc() {
        let l = parseFloat(document.getElementById('length').value) || 0;
        let w = parseFloat(document.getElementById('width').value) || 0;
        let h = parseFloat(document.getElementById('height').value) || 0;
        let weight = parseFloat(document.getElementById('actualWeight').value) || 0;

        let l_cm = currentUnit === 'cm_kg' ? l : l * 2.54;
        let w_cm = currentUnit === 'cm_kg' ? w : w * 2.54;
        let h_cm = currentUnit === 'cm_kg' ? h : h * 2.54;
        let act_kg = currentUnit === 'cm_kg' ? weight : weight * 0.4536;

        let vol_lb_exact = ((l_cm/2.54)*(w_cm/2.54)*(h_cm/2.54)) / 222;
        let act_lb = act_kg * 2.2046;
        let charge_lb = Math.max(act_lb, vol_lb_exact);
        let vol_kg = (l_cm * w_cm * h_cm) / 8000;

        let sides = [l_cm, w_cm, h_cm].sort((a,b)=>b-a);
        let maxSide = sides[0];
        let girth = maxSide + 2*(sides[1]+sides[2]);

        let dispCharge = currentUnit === 'cm_kg' ? (charge_lb/2.2046) : charge_lb;
        document.getElementById('disp_vol_w').innerText = (currentUnit==='cm_kg' ? vol_kg : vol_lb_exact).toFixed(2);
        document.getElementById('disp_charge_w').innerText = dispCharge.toFixed(2);
        document.getElementById('disp_girth').innerText = (currentUnit==='cm_kg' ? girth : girth/2.54).toFixed(2);

        if (act_lb > 50) updateStatusBadge('badge_weight', `重量: 超重 (>50lb)`, 'warn');
        else updateStatusBadge('badge_weight', '重量: 正常', 'ok');

        let sizeText = '尺寸: 正常', sizeStatus = 'ok';
        if (maxSide > 122) { sizeText = '尺寸: 超长 (>122cm)'; sizeStatus = 'warn'; }
        if (maxSide >= 274) { sizeText = '尺寸: 拒收 (>274cm)'; sizeStatus = 'err'; }
        updateStatusBadge('badge_size', sizeText, sizeStatus);

        if (girth > 266) {
            if (girth > 330) updateStatusBadge('badge_girth', `围长: 拒收 (>330cm)`, 'err');
            else updateStatusBadge('badge_girth', `围长: 超规 (>266cm)`, 'warn');
        } else {
            updateStatusBadge('badge_girth', '围长: 正常', 'ok');
        }

        const isReject = maxSide >= 274 || girth > 330;
        if (isReject) updateStatusBadge('badge_final', '综合: 不可发', 'err');
        else if (charge_lb > 0) updateStatusBadge('badge_final', '综合: 标准件', 'ok');
        else updateStatusBadge('badge_final', '综合: 待输入', '');

        return { charge_lb, isOver50: act_lb>50, isAHS: (maxSide>122 || girth>266), isReject };
    }

    function clearInputs() {
        document.querySelectorAll('input[type=number], input[type=text]').forEach(i => i.value = '');
        document.getElementById('fuelFedEx').value = 16.0;
        document.getElementById('fuelUSPS').value = 0.0;
        document.getElementById('zipCode').disabled = false;
        document.getElementById('warehouseOrigin').disabled = false;
        document.getElementById('selfPickupMode').checked = false;
        document.getElementById('resultTable').querySelector('tbody').innerHTML = '';
        document.getElementById('locationInfoBox').style.display = 'none';
        updateStatusBadge('badge_final', '综合: 待输入', '');
        liveCalc();
    }

    // --- 4. 最终计算 ---
    function getShippingRate(carrier, weight, zone, tier) {
        let base = 0;
        if(carrier === 'USPS') base = 4.0 + (weight*0.4) + (zone*0.5);
        if(carrier === 'FedEx') base = 8.5 + (weight*0.75) + (zone*0.9);
        if(carrier === 'UniUni') base = 3.5 + (weight*0.35) + (zone*0.3);
        if(carrier === 'GOFO') base = 3.8 + (weight*0.4) + (zone*0.25);
        return base;
    }

    function calculateFinalPrices() {
        const { charge_lb, isOver50, isAHS, isReject } = liveCalc();
        if(charge_lb <= 0) return alert("请输入有效尺寸和重量");
        if(isReject) return alert("该货物尺寸/围长超过快递限制，无法发货！");

        const tier = document.getElementById('priceTier').value;
        const isRes = document.getElementById('addressType').value === 'residential';
        const isPeakMode = document.getElementById('peakMode').checked;
        const isSelfPickup = document.getElementById('selfPickupMode').checked;
        const targetZone = detectedZoneVal;

        let tierKey = tier === '6.0' ? 't0' : (tier === '6.1' ? 't1' : (tier === '6.2' ? 't2' : 't3'));
        let opRow = opFeeData.find(d => charge_lb <= d.lb) || opFeeData[opFeeData.length-1];
        let outFee = opRow[tierKey].o;
        let selfFee = opRow[tierKey].s;

        let tbody = document.getElementById('resultTable').querySelector('tbody');
        tbody.innerHTML = '';

        // 模式A: 自提
        if (isSelfPickup) {
            let tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>自提服务 (Self-Pickup)</strong></td>
                <td><span style="color:${getComputedStyle(document.documentElement).getPropertyValue('--purple-color')}">无运费<br>客户自备账号</span></td>
            `;
            let totalSelfPrice = (outFee + selfFee).toFixed(2);
            for(let z=1; z<=9; z++) {
                tr.innerHTML += `<td style="font-weight:bold; color:#333">$${totalSelfPrice}</td>`;
            }
            tbody.appendChild(tr);
            return;
        }

        // 模式B: 代发
        const fuelRateFedEx = parseFloat(document.getElementById('fuelFedEx').value) / 100;
        const fuelRateUSPS = parseFloat(document.getElementById('fuelUSPS').value) / 100;

        // 仅“明确需要燃油叠加”的渠道才叠加燃油：
        // - FedEx：使用 FedEx 燃油
        // - USPS：使用 USPS 燃油
        // - UniUni/GOFO：视为报价已含燃油（不再叠加燃油）
        const CARRIER_RULES = {
            'FedEx': { fuel: () => fuelRateFedEx, applyFuel: true },
            'USPS': { fuel: () => fuelRateUSPS, applyFuel: true },
            'UniUni': { fuel: () => 0, applyFuel: false },
            'GOFO': { fuel: () => 0, applyFuel: false }
        };

        let surcharges = {
            usps_peak: 0.35,
            fedex_res: 5.50,
            fedex_res_peak: 1.10,
            ahs_size: 20.00,
            overweight: 25.00
        };

        const carriers = [
            { id: 'FedEx', name: 'FedEx Economy' },
            { id: 'USPS', name: 'USPS Ground Adv' },
            { id: 'UniUni', name: 'UniUni' },
            { id: 'GOFO', name: 'GOFO' }
        ];

        carriers.forEach(c => {
            let tr = document.createElement('tr');

            const rule = CARRIER_RULES[c.id] || { fuel: () => 0, applyFuel: false };
            const currentFuel = rule.fuel();
            const fuelText = rule.applyFuel ? `燃油:${(currentFuel*100).toFixed(1)}%` : `燃油: 已含/不叠加`;

            let desc = `<span style='font-size:11px'>${fuelText}</span>`;
            if (isPeakMode) desc += `<br><span style='color:red;font-size:11px'>+旺季费</span>`;
            desc += `<br><span style='font-size:11px; color:#666'>操作费:$${outFee.toFixed(2)}</span>`;

            tr.innerHTML += `<td><strong>${c.name}</strong></td><td>${desc}</td>`;

            for(let z=1; z<=9; z++) {
                let baseRate = getShippingRate(c.id, charge_lb, z, tier);
                let extra = 0;

                if (isPeakMode) {
                    if (c.id === 'FedEx') {
                        if (isRes) extra += (surcharges.fedex_res + surcharges.fedex_res_peak);
                        if (isAHS) extra += surcharges.ahs_size;
                        if (isOver50) extra += surcharges.overweight;
                    }
                    if (c.id === 'USPS') {
                        extra += surcharges.usps_peak;
                    }
                } else {
                    if (c.id === 'FedEx' && isRes) extra += surcharges.fedex_res;
                }

                // 计算规则：
                // - applyFuel=true： (运费+附加) * (1+燃油) + 操作费
                // - applyFuel=false： (运费+附加) + 操作费
                let sub = (baseRate + extra);
                let total = (rule.applyFuel ? (sub * (1 + currentFuel)) : sub) + outFee;

                let td = document.createElement('td');
                td.innerText = total.toFixed(2);
                if (targetZone && z === targetZone) td.className = 'highlight-zone';
                tr.appendChild(td);
            }

            tbody.appendChild(tr);
        });
    }
</script>

</body>
</html>
