import os
import subprocess
import pandas as pd
import requests
import shutil
import json
from collections import defaultdict

# 📌 運輸署官方 MDB 檔案路徑
URL_ROUTE = "https://static.data.gov.hk/td/routes-and-fares/ROUTE_BUS.mdb"
URL_FARE = "https://static.data.gov.hk/td/routes-and-fares/FARE_BUS.mdb"
OUTPUT_DIR = "fares"

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}

def download_file(url, filename):
    print(f"📥 正在下載 {filename}...")
    res = requests.get(url, headers=headers)
    with open(filename, 'wb') as f:
        f.write(res.content)

def get_first_table(mdb_file):
    output = subprocess.check_output(["mdb-tables", "-1", mdb_file]).decode('utf-8')
    tables = [t.strip() for t in output.split('\n') if t.strip()]
    return tables[0] if tables else None

def main():
    print("🚀 [1/4] 開始獲取最新巴士數據...")
    download_file(URL_ROUTE, "ROUTE_BUS.mdb")
    download_file(URL_FARE, "FARE_BUS.mdb")

    route_table = get_first_table("ROUTE_BUS.mdb")
    fare_table = get_first_table("FARE_BUS.mdb")

    if not route_table or not fare_table:
        print("❌ 檔案內找不到資料表，請確認下載檔案沒有損毀。")
        return

    print("🔄 [2/4] 正在將 MDB 轉換並載入數據...")
    with open("routes_temp.csv", "w", encoding="utf-8") as f_route:
        subprocess.check_call(["mdb-export", "ROUTE_BUS.mdb", route_table], stdout=f_route)
    
    with open("fares_temp.csv", "w", encoding="utf-8") as f_fare:
        subprocess.check_call(["mdb-export", "FARE_BUS.mdb", fare_table], stdout=f_fare)

    df_routes = pd.read_csv("routes_temp.csv")
    df_fares = pd.read_csv("fares_temp.csv")
    df_routes.columns = df_routes.columns.str.upper()
    df_fares.columns = df_fares.columns.str.upper()

    print("🔄 [3/4] 正在整合分段收費並生成 Static API...")
    route_dict = {}
    for _, row in df_routes.iterrows():
        rid = str(row.get('ROUTE_ID', '')).strip()
        comp = str(row.get('COMPANY_CODE', '')).strip().upper()
        rname = str(row.get('ROUTE_NAMEC', '')).strip().upper()
        if rid and comp and rname:
            route_dict[rid] = {
                'companies': comp.split('+'),
                'route': rname
            }

    fares_db = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

    for _, row in df_fares.iterrows():
        rid = str(row.get('ROUTE_ID', '')).strip()
        rseq = str(row.get('ROUTE_SEQ', '1')).strip()
        on_seq = str(row.get('ON_SEQ', '')).strip()
        price = row.get('PRICE', 0.0)

        if rid not in route_dict or not on_seq or pd.isna(price):
            continue

        direction = "outbound" if rseq == '1' else "inbound"
        info = route_dict[rid]

        for comp in info['companies']:
            current_fare = fares_db[comp][info['route']][direction].get(on_seq, 0.0)
            if float(price) > current_fare:
                fares_db[comp][info['route']][direction][on_seq] = float(price)

    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    file_count = 0
    for comp, routes in fares_db.items():
        comp_dir = os.path.join(OUTPUT_DIR, comp)
        os.makedirs(comp_dir, exist_ok=True)
        for route, dirs_data in routes.items():
            file_path = os.path.join(comp_dir, f"{route}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(dirs_data, f, ensure_ascii=False, indent=2)
            file_count += 1

    print(f"📁 成功生成 {file_count} 個 JSON 檔案！")

    print("📦 [4/4] 清理暫存檔案...")
    for temp in ["ROUTE_BUS.mdb", "FARE_BUS.mdb", "routes_temp.csv", "fares_temp.csv"]:
        if os.path.exists(temp): os.remove(temp)
        
    print("🎉 更新完成！")

if __name__ == "__main__":
    main()
