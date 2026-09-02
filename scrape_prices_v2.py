# -*- coding: utf-8 -*-
"""
scrape_prices_v2.py
====================
ดึงราคาผลไม้จาก 3 แหล่งข้อมูลจริงที่ตรวจสอบแล้วว่าเข้าถึงได้แบบสาธารณะ (ไม่ต้อง login,
ไม่มี CORS/anti-bot เข้มงวด) แล้วเขียนผลลัพธ์ลง prices.json ในรูปแบบเดียวกับที่เว็บ index.html
ใช้อยู่แล้ว (คีย์ "talaadthai", "simummuang", "makro")

แหล่งข้อมูลและวิธีที่ใช้ (ค้นพบและยืนยันด้วยตนเองผ่าน DevTools ระหว่างวันที่ 2026-08-28
ถึง 2026-08-30 ไม่ใช่ Public API ที่มีเอกสารทางการ โปรดใช้อย่างสุภาพ - หน่วงเวลาระหว่าง
request แต่ละครั้ง และหยุดใช้ทันทีถ้าพบว่าเว็บเปลี่ยนเงื่อนไข/บล็อกการเข้าถึง):

1. ตลาดไท (talaadthai.com)
   GET https://svc-center-ext-tlt-corp-prod-service.talaadthai.com/v1/ext/product/ProductsList
       ?offset=<n>&pageSize=25&categoryId=4&sort=recommended_asc
   -> คืน JSON รายการสินค้าหมวดผลไม้ (categoryId=4) พร้อม priceMinThb/priceMaxThb

2. ตลาดสี่มุมเมือง (simummuangmarket.com)
   GET https://api.simummuangmarket.com/api/app/products
       ?page=<n>&limit=20&prod_category_id=689c0d91e82dd5da9bb1ab63
   -> คืน JSON รายการสินค้าหมวดผลไม้ พร้อม price.small/medium/large (แต่ละไซส์มี min/max)

3. Makro PRO (makro.pro) - ราคาซูเปอร์มาร์เก็ต
   GET https://www.makro.pro/c/search?q=<ชื่อผลไม้>
   -> หน้า HTML (Next.js) มีราคาสินค้าฝังอยู่ในเนื้อหา ค้นหาทีละชื่อผลไม้จาก FRUITS

สำคัญมาก (อ่านก่อนใช้งานจริง):
- ราคาที่ได้มาจากทั้ง 3 แหล่งเป็นราคาจริงตรงจากเว็บ ไม่มีการสุ่ม/สร้างขึ้นเอง
- แต่การ "จับคู่ชื่อ" ระหว่างชื่อสินค้าบนเว็บกับชื่อผลไม้ 35 ชนิดในตาราง ใช้วิธีจับคู่แบบ
  ผิวเผิน (substring match) ซึ่งเคยพบปัญหาจับคู่ผิดมาแล้วจริง เช่น "ทับทิม" ไปจับกับ
  "ปลาทับทิม", "กีวี่" ไปเจอแต่ของนำเข้า/แช่แข็ง ฯลฯ -> ต้องมีคนตรวจทานผลลัพธ์ในไฟล์
  prices_v2_draft.json ก่อนนำไปใช้แทนไฟล์ prices.json จริงเสมอ
- หน่วย (กก./ลูก/หวี) ต้องเช็คเองด้วย สคริปต์นี้พยายามอ่านหน่วยจากข้อมูลต้นทางเท่าที่ทำได้
  แต่ไม่รับประกันว่าจะตรงกับหน่วยที่ตารางเว็บคาดไว้เสมอไป
- เว็บทั้ง 3 แห่งอาจเปลี่ยนโครงสร้าง/URL ได้ทุกเมื่อโดยไม่แจ้งล่วงหน้า ถ้าสคริปต์รันแล้ว
  error หรือได้ผลลัพธ์ 0 รายการ ให้กลับไปเช็ค DevTools ใหม่ (วิธีเดิมที่เคยทำกันมา)
"""

import json
import re
import time
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

try:
    import requests
except ImportError:
    print("ต้องติดตั้ง requests ก่อน: pip install requests --break-system-packages")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ต้องติดตั้ง beautifulsoup4 ก่อน: pip install beautifulsoup4 --break-system-packages")
    sys.exit(1)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
}

REQUEST_DELAY_SEC = 1.2  # หน่วงเวลาระหว่าง request แต่ละครั้ง กันถูกมองว่าถล่มเว็บ

# ผลไม้ 35 ชนิดตามตารางในเว็บ (ต้องตรงกับ data-fruit ในไฟล์ index.html เป๊ะๆ)
FRUITS = [
    "ทุเรียนหมอนทอง", "มังคุด", "มะม่วงน้ำดอกไม้", "ลำไย", "ลิ้นจี่",
    "เงาะโรงเรียน", "ส้มโอ", "สับปะรด", "ลองกอง", "กล้วยหอม",
    "ส้มสายน้ำผึ้ง", "สตรอว์เบอร์รี", "ท้อ (พีช)", "บ๊วย", "มะขามหวานเพชรบูรณ์",
    "ทับทิม", "กีวี่", "เสาวรส", "ฝรั่งกิมจู", "มะละกอ",
    "แตงโมจินตหรา", "ชมพู่", "ชมพู่มะเหมี่ยว", "มะนาวไทย", "ขนุนทองประเสริฐ",
    "มะปรางหวาน", "สละอินโดนีเซีย", "กระท้อนบ้านบึง", "หนำเลี้ยบ (พุทรา)", "ระกำ",
    "มะพร้าวน้ำหอม", "เงาะสุราษฎร์ธานี", "ลางสาด", "ส้มแขก (มะดัน)", "กล้วยน้ำว้าใต้",
]

# คำที่ห้ามให้ผลลัพธ์ผ่าน แม้ชื่อจะจับคู่ได้ (กันเคสจับผิดแบบที่เคยเจอ: ของแช่แข็ง/แปรรูป/
# นำเข้า/คนละชนิดสินค้าโดยสิ้นเชิง)
BLOCK_KEYWORDS = [
    "แช่แข็ง", "แช่เย็น", "อบแห้ง", "อบกรอบ", "กระป๋อง", "ผง", "น้ำ", "ไซรัป",
    "ปลา", "หมู", "ไก่", "กุ้ง", "เนื้อ", "ปลอกเปลือก", "หั่น", "เต๋า", "สไลด์",
    "จีน", "ญี่ปุ่น", "นิวซีแลนด์", "ออสเตรเลีย", "เกาหลี", "ไต้หวัน", "อเมริกา",
    "Zespri", "aro", "Savepak", "freeze dried", "Freeze Dried",
]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def looks_blocked(name):
    return any(bad.lower() in name.lower() for bad in BLOCK_KEYWORDS)


def match_fruit(product_name, fruit_list=FRUITS):
    """จับคู่ชื่อสินค้ากับชื่อผลไม้ในตาราง แบบ substring คร่าวๆ
    (มีข้อจำกัดตามที่อธิบายไว้ด้านบนของไฟล์ - ต้องตรวจทานผลลัพธ์เอง)"""
    if looks_blocked(product_name):
        return None
    base = product_name.split(" – ")[0].split(" (")[0].strip()
    for fruit in fruit_list:
        fbase = fruit.split(" (")[0].strip()
        if fbase and (fbase in base or base in fbase):
            return fruit
    return None


# ---------------------------------------------------------------------------
# 1) ตลาดไท
# ---------------------------------------------------------------------------
def fetch_talaadthai(max_pages=30, page_size=25):
    """ไล่ดึงสินค้าหมวดผลไม้ (categoryId=4) ทีละหน้า จนครบหรือถึง max_pages"""
    base_url = "https://svc-center-ext-tlt-corp-prod-service.talaadthai.com/v1/ext/product/ProductsList"
    results = {}
    offset = 0
    for page in range(max_pages):
        params = {
            "offset": offset,
            "pageSize": page_size,
            "keyword": "",
            "categoryId": 4,
            "market": "",
            "tags": "",
            "sort": "recommended_asc",
        }
        try:
            resp = requests.get(base_url, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log(f"[talaadthai] offset={offset} error: {e}")
            break

        items = data.get("data") or data.get("items") or []
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
            items = data["data"].get("items", [])
        if not items:
            log(f"[talaadthai] offset={offset} ไม่มีรายการเพิ่มแล้ว หยุดไล่หน้า")
            break

        for item in items:
            title = item.get("title") or {}
            name_th = title.get("th") if isinstance(title, dict) else None
            if not name_th:
                continue
            price_min = item.get("priceMinThb")
            price_max = item.get("priceMaxThb")
            unit = item.get("unit", "กิโลกรัม")
            if price_min in (None, 0) and price_max in (None, 0):
                continue  # ไม่มีราคา/หมดสต็อก
            fruit = match_fruit(name_th)
            if not fruit:
                continue
            if unit not in ("กิโลกรัม", "กก."):
                log(f"[talaadthai] ข้าม '{name_th}' -> หน่วยเป็น '{unit}' ไม่ใช่กก. ต้องเช็คเองก่อนใช้")
                continue
            price_str = f"{price_min}–{price_max} บ." if price_min != price_max else f"{price_min} บ."
            results.setdefault(fruit, []).append((name_th, price_str))
            log(f"[talaadthai] เจอ '{name_th}' -> {fruit}: {price_str}")

        log(f"[talaadthai] ดึงหน้า offset={offset} แล้ว ({len(items)} รายการ)")
        offset += page_size
        time.sleep(REQUEST_DELAY_SEC)

    # ถ้าผลไม้หนึ่งชนิดเจอหลายรายการ (เช่น เบอร์เล็ก/เบอร์ใหญ่) ให้รวมเป็นช่วงราคาเดียว
    final = {}
    for fruit, matches in results.items():
        all_nums = []
        for _, price_str in matches:
            all_nums += [int(n) for n in re.findall(r"\d+", price_str)]
        if all_nums:
            lo, hi = min(all_nums), max(all_nums)
            final[fruit] = f"{lo}–{hi} บ." if lo != hi else f"{lo} บ."
    return final


# ---------------------------------------------------------------------------
# 2) ตลาดสี่มุมเมือง
# ---------------------------------------------------------------------------
def _extract_items_list(data):
    """หา list ของสินค้าจาก JSON response ของ simummuang อย่างทนทาน
    (โครงสร้างจริงอาจซ้อนอยู่หลายชั้น เช่น data.data, data.data.items, data.data.lists ฯลฯ)
    คืนค่า (items, path_ที่เจอ) เพื่อ debug ง่ายถ้ายังหาไม่เจอ"""
    candidates = [
        ("data", data.get("data") if isinstance(data, dict) else None),
        ("data.items", (data.get("data") or {}).get("items") if isinstance(data.get("data"), dict) else None),
        ("data.lists", (data.get("data") or {}).get("lists") if isinstance(data.get("data"), dict) else None),
        ("data.data", (data.get("data") or {}).get("data") if isinstance(data.get("data"), dict) else None),
        ("lists", data.get("lists") if isinstance(data, dict) else None),
        ("items", data.get("items") if isinstance(data, dict) else None),
        ("results", data.get("results") if isinstance(data, dict) else None),
    ]
    for path, val in candidates:
        if isinstance(val, list) and (len(val) == 0 or isinstance(val[0], dict)):
            return val, path
    return [], None


def fetch_simummuang(max_pages=9, page_size=20):
    base_url = "https://api.simummuangmarket.com/api/app/products"
    fruit_category_id = "689c0d91e82dd5da9bb1ab63"
    results = {}

    for page in range(1, max_pages + 1):
        params = {
            "page": page,
            "limit": page_size,
            "prod_category_id": fruit_category_id,
        }
        try:
            resp = requests.get(base_url, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log(f"[simummuang] page={page} error: {e}")
            break

        items, found_path = _extract_items_list(data)
        if not items and found_path is None:
            # หา list สินค้าไม่เจอเลย -> พิมพ์โครงสร้างคร่าวๆ ออกมาช่วย debug แล้วหยุด
            log(f"[simummuang] page={page} หา list สินค้าไม่เจอ! โครงสร้าง JSON ที่ได้คือ:")
            try:
                keys_preview = json.dumps(data, ensure_ascii=False)[:500]
            except Exception:
                keys_preview = str(data)[:500]
            log(f"[simummuang] ตัวอย่างข้อมูลดิบ (500 ตัวอักษรแรก): {keys_preview}")
            log("[simummuang] ส่งข้อความข้างบนนี้กลับไปให้ผู้ช่วยดู เพื่อแก้โค้ดให้ตรงโครงสร้างจริง")
            break

        if not items:
            log(f"[simummuang] page={page} ไม่มีรายการ หยุด")
            break

        for item in items:
            th = item.get("th") or {}
            name_th = th.get("name") if isinstance(th, dict) else None
            if not name_th:
                continue
            price = item.get("price") or {}
            large = price.get("large") or {}
            p_min, p_max = large.get("min"), large.get("max")
            if p_max in (None, 0):
                continue  # หมดสต็อก/ไม่มีราคา
            prod_unit = (item.get("prod_unit_id") or {}).get("th", {}).get("name", "กิโลกรัม")
            if prod_unit not in ("กิโลกรัม", "กก."):
                log(f"[simummuang] ข้าม '{name_th}' -> หน่วยเป็น '{prod_unit}' ต้องเช็คเองก่อนใช้")
                continue
            fruit = match_fruit(name_th)
            if not fruit:
                continue
            price_str = f"{p_min}–{p_max} บ." if p_min != p_max else f"{p_max} บ."
            results[fruit] = price_str
            log(f"[simummuang] เจอ '{name_th}' -> {fruit}: {price_str}")

        log(f"[simummuang] ดึงหน้า {page}/{max_pages} แล้ว ({len(items)} รายการ)")
        time.sleep(REQUEST_DELAY_SEC)

    return results


# ---------------------------------------------------------------------------
# 3) Makro PRO (ราคาซูเปอร์มาร์เก็ต)
# ---------------------------------------------------------------------------
PRICE_RE = re.compile(r"฿?\s*(\d[\d,]*(?:\.\d+)?)\s*(?:/\s*(กก\.|กก|kg|ลูก|หวี))?")


def fetch_makro(fruit_list=FRUITS):
    """ค้นหาทีละชื่อผลไม้ใน Makro PRO แล้วพยายามอ่านราคาต่อกก./ลูก/หวี จากผลลัพธ์แรกๆ
    ข้ามสินค้าที่ดูเป็นของแช่แข็ง/แปรรูป/นำเข้า/แบรนด์ (ตาม BLOCK_KEYWORDS)"""
    results = {}
    base_url = "https://www.makro.pro/c/search"

    for fruit in fruit_list:
        query = fruit.split(" (")[0].strip()
        try:
            resp = requests.get(base_url, params={"q": query}, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            log(f"[makro] '{query}' error: {e}")
            time.sleep(REQUEST_DELAY_SEC)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        # การ์ดสินค้าบน Makro PRO แต่ละใบมักมีชื่อสินค้าในแท็ก <p>/<h3> ใกล้ๆ ราคา
        # โครงสร้างหน้าเว็บอาจเปลี่ยนได้ - ถ้าดึงไม่ได้ผล ให้กลับไปเปิด F12 เช็คใหม่
        text_blocks = soup.get_text("\n", strip=True).split("\n")

        found_price = None
        found_unit = "กก."
        for i, line in enumerate(text_blocks):
            if looks_blocked(line):
                continue
            m = PRICE_RE.search(line)
            if m and query in " ".join(text_blocks[max(0, i - 2):i + 1]):
                num = m.group(1).replace(",", "")
                unit_raw = m.group(2) or "กก."
                unit_map = {"kg": "กก.", "กก": "กก."}
                found_unit = unit_map.get(unit_raw, unit_raw)
                found_price = num
                break

        if found_price:
            price_str = f"{found_price} บ./{found_unit}"
            results[fruit] = price_str
            log(f"[makro] '{query}' -> {price_str} (ตรวจสอบหน่วย/รายการซ้ำเองอีกครั้งก่อนใช้จริง)")
        else:
            log(f"[makro] '{query}' -> ไม่พบราคาที่อ่านได้ชัดเจน ข้าม")

        time.sleep(REQUEST_DELAY_SEC)

    return results


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    log("เริ่มดึงราคาจากตลาดไท ...")
    talaadthai = fetch_talaadthai()

    log("เริ่มดึงราคาจากตลาดสี่มุมเมือง ...")
    simummuang = fetch_simummuang()

    log("เริ่มดึงราคาจาก Makro PRO (ค้นหาทีละชื่อ 35 ครั้ง อาจใช้เวลาสักครู่) ...")
    makro = fetch_makro()

    tz = timezone(timedelta(hours=7))
    now = datetime.now(tz).isoformat()

    output = {
        "updated_at": now,
        "source_note": (
            "talaadthai: API ProductsList (categoryId=4) | "
            "simummuang: API products (prod_category_id ผลไม้) | "
            "makro: makro.pro/c/search ค้นหาทีละชื่อ — ดึงโดยสคริปต์ scrape_prices_v2.py "
            f"เมื่อ {now} — ยังไม่ผ่านการตรวจทานโดยคน โปรดเช็คก่อนใช้แทน prices.json จริง"
        ),
        "talaadthai": talaadthai,
        "simummuang": simummuang,
        "makro": makro,
        "note": (
            "ไฟล์นี้คือผลลัพธ์ดิบจากสคริปต์ (prices_v2_draft.json) ยังไม่ได้ตรวจทานโดยคน "
            "ห้ามเอาไปทับ prices.json ตรงๆ โดยไม่เช็คก่อน — ให้เปิดดูทีละรายการ เทียบกับ "
            "เว็บจริงอย่างน้อยสัก 5-10 รายการแบบสุ่ม ก่อนค่อยรวมเข้ากับไฟล์ prices.json จริง"
        ),
    }

    out_path = "prices_v2_draft.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log(f"เขียนไฟล์ {out_path} สำเร็จ")
    log(f"สรุป: ตลาดไท {len(talaadthai)} ชนิด | สี่มุมเมือง {len(simummuang)} ชนิด | Makro {len(makro)} ชนิด")
    log("*** อย่าลืมตรวจทานผลลัพธ์ก่อนนำไปรวมกับ prices.json จริง ***")


if __name__ == "__main__":
    main()
