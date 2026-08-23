#!/usr/bin/env python3
"""
scrape_prices.py
=================
สคริปต์ต้นแบบสำหรับดึงราคาผลไม้จริงจาก 2 ตลาดกลาง:
  - ตลาดไท        : https://talaadthai.com/products
  - ตลาดสี่มุมเมือง : https://www.simummuangmarket.com/pricing

แล้วเขียนออกมาเป็นไฟล์ prices.json ที่หน้าเว็บ (index.html) จะดึงไปแสดงผล
แบบ "เกือบเรียลไทม์" (near real-time) โดยการรัน cron job ทุก 30-60 นาที

⚠️ สำคัญ: เว็บทั้งสองแห่งไม่มี public API และ HTML/selector ของแต่ละเว็บ
อาจเปลี่ยนแปลงได้ตลอดเวลา สคริปต์นี้จึงเป็น "โครงเริ่มต้น" ที่คุณต้อง:
  1. เปิดเว็บจริงด้วย browser -> คลิกขวา "Inspect" / "View Page Source"
  2. หาว่าราคาผลไม้แต่ละชนิดอยู่ใน HTML tag ไหน (table? div? มี class อะไร?)
  3. แก้ฟังก์ชัน parse_talaadthai() และ parse_simummuang() ให้ตรงกับ
     โครงสร้างจริงที่เจอ (ตัวอย่างด้านล่างเป็นแค่ placeholder)
  4. ถ้าเว็บโหลดราคาด้วย JavaScript (ไม่ใช่ HTML ตรงๆ) อาจต้องใช้
     Selenium / Playwright แทน requests+BeautifulSoup ธรรมดา

การติดตั้ง:
  pip install requests beautifulsoup4

การใช้งาน:
  python3 scrape_prices.py
  -> จะสร้าง/อัปเดตไฟล์ prices.json ในโฟลเดอร์เดียวกัน

การตั้งให้รันอัตโนมัติ (Linux/macOS, ทุก 30 นาที):
  crontab -e
  */30 * * * * /usr/bin/python3 /path/to/scrape_prices.py >> /path/to/scrape.log 2>&1

จากนั้นวางไฟล์ prices.json ไว้ตำแหน่งเดียวกับ index.html บนเว็บเซิร์ฟเวอร์
(ต้องเป็นเซิร์ฟเวอร์เดียวกัน หรือเปิด CORS ให้ถ้าคนละโดเมน)
"""

import json
import sys
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

BANGKOK_TZ = timezone(timedelta(hours=7))

# รายชื่อผลไม้ที่ต้องการเก็บราคา (ต้องตรงกับ data-fruit ในตาราง index.html เป๊ะๆ)
FRUITS = [
    "ทุเรียนหมอนทอง", "มังคุด", "มะม่วงน้ำดอกไม้", "ลำไย", "ลิ้นจี่",
    "เงาะโรงเรียน", "ส้มโอ", "สับปะรด", "ลองกอง", "กล้วยหอม",
    "ส้มสายน้ำผึ้ง", "สตรอว์เบอร์รี", "ท้อ (พีช)", "บ๊วย",
    "มะขามหวานเพชรบูรณ์", "ทับทิม", "กีวี่", "เสาวรส", "ฝรั่งกิมจู",
    "มะละกอ", "แตงโมจินตหรา", "ชมพู่", "ชมพู่มะเหมี่ยว", "มะนาวไทย",
    "ขนุนทองประเสริฐ", "มะปรางหวาน", "สละอินโดนีเซีย", "กระท้อนบ้านบึง",
    "หนำเลี้ยบ (พุทรา)", "ระกำ", "มะพร้าวน้ำหอม", "ทุเรียนภาคใต้",
    "เงาะสุราษฎร์ธานี", "มังคุดภาคใต้", "ลางสาด", "เสาวรสภาคใต้",
    "ส้มแขก (มะดัน)", "กล้วยน้ำว้าใต้",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ThaiFruitPriceBot/1.0; +https://example.com/bot)"
}


def parse_talaadthai():
    """
    TODO: แก้ให้ตรงกับโครงสร้างหน้าเว็บจริงของ talaadthai.com/products
    ตอนนี้เป็นแค่ตัวอย่างโครงร่าง (ต้อง inspect หน้าเว็บจริงก่อนใช้งาน)
    """
    url = "https://talaadthai.com/products"
    prices = {}
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # ---- ตัวอย่าง placeholder: สมมติว่าราคาอยู่ใน <tr> ของตาราง ----
        # for row in soup.select("table.product-price-table tbody tr"):
        #     cells = row.find_all("td")
        #     if len(cells) >= 2:
        #         name = cells[0].get_text(strip=True)
        #         price = cells[1].get_text(strip=True)
        #         prices[name] = price

        if not prices:
            print("[talaadthai] ยังไม่ได้ตั้งค่า selector จริง — ข้าม (ใช้ placeholder)", file=sys.stderr)
    except Exception as e:
        print(f"[talaadthai] ดึงข้อมูลไม่สำเร็จ: {e}", file=sys.stderr)
    return prices


def parse_simummuang():
    """
    TODO: แก้ให้ตรงกับโครงสร้างหน้าเว็บจริงของ simummuangmarket.com/pricing
    """
    url = "https://www.simummuangmarket.com/pricing"
    prices = {}
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # ---- ตัวอย่าง placeholder ----
        # for row in soup.select(".price-list .price-row"):
        #     name = row.select_one(".fruit-name").get_text(strip=True)
        #     price = row.select_one(".fruit-price").get_text(strip=True)
        #     prices[name] = price

        if not prices:
            print("[simummuang] ยังไม่ได้ตั้งค่า selector จริง — ข้าม (ใช้ placeholder)", file=sys.stderr)
    except Exception as e:
        print(f"[simummuang] ดึงข้อมูลไม่สำเร็จ: {e}", file=sys.stderr)
    return prices


def main():
    talaadthai_prices = parse_talaadthai()
    simummuang_prices = parse_simummuang()

    output = {
        "updated_at": datetime.now(BANGKOK_TZ).isoformat(),
        "talaadthai": talaadthai_prices,
        "simummuang": simummuang_prices,
        "note": "ราคาจากการ scrape อัตโนมัติ — ตรวจสอบกับเว็บต้นทางก่อนใช้อ้างอิงจริง",
    }

    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = len(talaadthai_prices) + len(simummuang_prices)
    print(f"เขียน prices.json สำเร็จ — พบราคาทั้งหมด {total} รายการ")


if __name__ == "__main__":
    main()
