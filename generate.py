def load_fedex_peak_tables(excel_path: str, tier_name: str):
    """
    按你最新确认的实际结构：
    - FedEx-YSD 旺季表：在 sheet = "FedEx-YSD-报价" 内部，区块 188-201 行，项目名 I 列
    - FedEx-632 旺季表：在 sheet = "FedEx-632-MT-报价" 内部，区块 188-201 行，项目名 I 列
    """
    result = {}

    # 1) FedEx-YSD 旺季（在 FedEx-YSD-报价 sheet 内）
    df_ysd = get_sheet_by_name(excel_path, ["FedEx", "YSD"])  # ✅ 改这里：不再找“旺季sheet”
    if df_ysd is not None:
        blk = df_ysd.iloc[187:201].copy().fillna("")  # Excel 188-201 => 0-based 187-200（切片到201不含）
        item_col = excel_col_to_idx("I")
        zone_cols = _detect_fedex_peak_zone_cols(blk)

        items = {}
        for i in range(len(blk)):
            name = str(blk.iat[i, item_col]).strip()
            if not name or name.lower() in ('nan', 'none'):
                continue
            row_fee = {}
            for bucket, cidx in zone_cols.items():
                row_fee[bucket] = safe_float(blk.iat[i, cidx])
            if any(v > 0 for v in row_fee.values()):
                items[name] = row_fee

        result["FedEx-YSD-报价"] = {"zones": list(zone_cols.keys()), "items": items}

        # ✅ 你要的：排查日志 1 行
        print(f"    > {tier_name}/FedEx-YSD 旺季区块@FedEx-YSD-报价: items={len(items)}, buckets={list(zone_cols.keys())}")

    # 2) FedEx-632 旺季（在 FedEx-632-MT-报价 sheet 内）
    df_632 = get_sheet_by_name(excel_path, ["FedEx", "632"])
    if df_632 is not None:
        blk = df_632.iloc[187:201].copy().fillna("")
        item_col = excel_col_to_idx("I")
        zone_cols = _detect_fedex_peak_zone_cols(blk)

        items = {}
        for i in range(len(blk)):
            name = str(blk.iat[i, item_col]).strip()
            if not name or name.lower() in ('nan', 'none'):
                continue
            row_fee = {}
            for bucket, cidx in zone_cols.items():
                row_fee[bucket] = safe_float(blk.iat[i, cidx])
            if any(v > 0 for v in row_fee.values()):
                items[name] = row_fee

        result["FedEx-632-MT-报价"] = {"zones": list(zone_cols.keys()), "items": items}

        # ✅ 你要的：排查日志 1 行
        print(f"    > {tier_name}/FedEx-632 旺季区块@FedEx-632-MT-报价: items={len(items)}, buckets={list(zone_cols.keys())}")

    return result
