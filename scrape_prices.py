#!/usr/bin/env python3
"""
scrape_prices.py
=================
สคริปต์ดึงราคาผลไม้จริงจาก 2 ตลาดกลาง:
  - ตลาดไท        : https://talaadthai.com/products
  - ตลาดสี่มุมเมือง : https://www.simummuangmarket.com/pricing

แล้วเขียนออกมาเป็นไฟล์ prices.json ที่หน้าเว็บ (index.html) จะดึงไปแสดงผล
แบบ "เกือบเรียลไทม์" (near real-time) โดยการรัน cron job ทุก 30-60 นาที

============================================================================
⚠️ อัปเดตสำคัญ (แก้จากเวอร์ชันก่อนหน้า):
============================================================================
เวอร์ชันก่อนหน้าของสคริปต์นี้ "ไม่เคยดึงราคาได้จริง" เพราะโค้ด selector
ทั้งหมดถูกคอมเมนต์ทิ้งไว้เป็น placeholder — รันกี่ครั้งก็ได้ prices = {}
เสมอ นี่คือสาเหตุที่ prices.json บนเว็บค้างวันที่เดิมมาหลายวัน (เพราะไฟล์ที่
ใช้งานจริงเป็นไฟล์ demo ที่พิมพ์มือไว้ครั้งเดียว ไม่เคยมีอะไรมาเขียนทับ)

เมื่อลองเปิดหน้า talaadthai.com/products และหน้ารายละเอียดสินค้าจริง พบว่า
**ไม่มีราคาปรากฏอยู่ใน HTML ที่ได้จาก request ธรรมดาเลย** แปลว่าเว็บนี้โหลด
ราคาด้วย JavaScript หลัง initial load (Next.js app) ดังนั้น requests +
BeautifulSoup ธรรมดาจะดึงราคาไม่ได้ — ต้องใช้เบราว์เซอร์จริง (Playwright)
รัน JavaScript ก่อนแล้วค่อยอ่านค่าจาก DOM

สคริปต์นี้จึงเปลี่ยนมาใช้ Playwright และลองดึงข้อมูลด้วย 3 กลยุทธ์เรียงลำดับ
(ตัวไหนเจอก่อนก็ใช้ตัวนั้น) ต่อ 1 หน้า:
  1) JSON-LD (<script type="application/ld+json"> ...Product/Offer/price)
  2) Next.js __NEXT_DATA__ (<script id="__NEXT_DATA__"> เก็บ props ทั้งหน้า)
  3) DOM selector หลัง render จริง (ต้องเปิด browser devtools ไปหาของจริง)

⚠️ สำคัญ: ผมไม่มีสิทธิ์เข้าถึงโดเมน talaadthai.com / simummuangmarket.com
จาก sandbox ที่ใช้พัฒนาสคริปต์นี้ (network allowlist ไม่รวมโดเมนนี้)
จึงยืนยัน selector ของกลยุทธ์ที่ 3 ให้แบบเป๊ะๆ ไม่ได้ ต้องให้คุณ:
  1. เปิด https://talaadthai.com/products ด้วย browser จริง
  2. กด F12 -> แท็บ Network -> กรอง Fetch/XHR -> รีเฟรชหน้า
  3. หา request ที่ตอบกลับเป็น JSON ที่มีชื่อสินค้า+ราคา (มักจะเจอง่ายกว่า
     การไล่ selector ใน DOM) แล้วเอา URL นั้นมาใส่แทนใน parse_talaadthai()
     โดยตรง (ยิงตรงไปที่ API endpoint จะเร็วและเสถียรกว่าการ render หน้าเว็บ)
  4. ถ้าหา API ไม่เจอจริงๆ ค่อยใช้แผน DOM selector ที่เตรียมโครงไว้ให้ด้านล่าง
     (ต้องกด Inspect บนตัวเลขราคาแล้วดูว่า container/class ชื่ออะไร)

การติดตั้ง:
  pip install playwright beautifulsoup4
  playwright install chromium

การใช้งาน:
  python3 scrape_prices.py
  -> จะสร้าง/อัปเดตไฟล์ prices.json ในโฟลเดอร์เดียวกัน

การตั้งให้รันอัตโนมัติ (Linux/macOS, ทุก 30 นาที):
  crontab -e
  */30 * * * * /usr/bin/python3 /path/to/scrape_prices.py >> /path/to/scrape.log 2>&1

จากนั้นวางไฟล์ prices.json ไว้ตำแหน่งเดียวกับ index.html บนเว็บเซิร์ฟเวอร์
(ต้องเป็นเซิร์ฟเวอร์เดียวกัน หรือเปิด CORS ให้ถ้าคนละโดเมน)

⚠️ ตรวจสอบไฟล์ prices.json หลังรันทุกครั้งช่วงแรก ว่า "updated_at" ขยับจริง
และค่า talaadthai/simummuang ไม่ใช่ {} ว่างเปล่า — ถ้าว่างแปลว่ากลยุทธ์ทั้ง 3
ยังหาไม่เจอ ต้องกลับไปทำตามขั้นตอนด้านบน
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta

from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

BANGKOK_TZ = timezone(timedelta(hours=7))

# รายชื่อผลไม้ที่ต้องการเก็บราคา — ต้องตรงกับ data-fruit ในตาราง index.html เป๊ะๆ
# (ลิสต์นี้ sync กับ data-fruit="..." ในตาราง "ราคาผลไม้วันนี้" ของ index.html แล้ว
#  เวอร์ชันก่อนหน้ามี 3 รายการเกินมาที่ไม่มีอยู่จริงในตาราง — ตัดออกแล้ว:
#  มังคุดภาคใต้, ทุเรียนภาคใต้, เสาวรสภาคใต้ — ตารางใช้ราคาร่วมกับ
#  มังคุด / ทุเรียนหมอนทอง / เสาวรส อยู่แล้ว)
FRUITS = [
    "ทุเรียนหมอนทอง", "มังคุด", "มะม่วงน้ำดอกไม้", "ลำไย", "ลิ้นจี่",
    "เงาะโรงเรียน", "ส้มโอ", "สับปะรด", "ลองกอง", "กล้วยหอม",
    "ส้มสายน้ำผึ้ง", "สตรอว์เบอร์รี", "ท้อ (พีช)", "บ๊วย",
    "มะขามหวานเพชรบูรณ์", "ทับทิม", "กีวี่", "เสาวรส", "ฝรั่งกิมจู",
    "มะละกอ", "แตงโมจินตหรา", "ชมพู่", "ชมพู่มะเหมี่ยว", "มะนาวไทย",
    "ขนุนทองประเสริฐ", "มะปรางหวาน", "สละอินโดนีเซีย", "กระท้อนบ้านบึง",
    "หนำเลี้ยบ (พุทรา)", "ระกำ", "มะพร้าวน้ำหอม",
    "เงาะสุราษฎร์ธานี", "ลางสาด",
    "ส้มแขก (มะดัน)", "กล้วยน้ำว้าใต้",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ThaiFruitPriceBot/1.0; +https://example.com/bot)"
}

PRICE_RE = re.compile(r"(\d{1,4}(?:[.,]\d+)?)\s*(?:[-–—~]|to)\s*(\d{1,4}(?:[.,]\d+)?)\s*บ")
SINGLE_PRICE_RE = re.compile(r"(\d{1,4}(?:[.,]\d+)?)\s*บาท")


def _match_fruit_name(text, fruit_list):
    """หาว่าข้อความ (เช่น ชื่อสินค้าในหน้าเว็บ) ตรงกับผลไม้ตัวไหนใน fruit_list
    ใช้ 'contains' แบบหลวมๆ เพราะชื่อสินค้าจริงบนเว็บมักมีคำต่อท้าย
    เช่น '– เบอร์ใหญ่', '(คละ)' ที่ไม่ตรงกับชื่อใน FRUITS เป๊ะๆ"""
    for fruit in fruit_list:
        base = fruit.split(" (")[0].strip()
        if base and base in text:
            return fruit
    return None


def _extract_from_jsonld(soup):
    """กลยุทธ์ 1: หาแท็ก JSON-LD ที่มี schema.org Product/Offer + price"""
    result = {}
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            offers = item.get("offers")
            if not name or not offers:
                continue
            price = None
            if isinstance(offers, dict):
                price = offers.get("price") or offers.get("lowPrice")
            elif isinstance(offers, list) and offers:
                price = offers[0].get("price")
            if price:
                result[name] = f"{price} บ."
    return result


def _extract_from_next_data(soup):
    """กลยุทธ์ 2: หาแท็ก <script id="__NEXT_DATA__"> ของ Next.js
    ซึ่งมักฝัง props เริ่มต้นของหน้า (รวมถึงราคาสินค้า) ไว้เป็น JSON
    โครงสร้างจริงข้างในต่างกันไปตามแต่ละเว็บ ต้อง inspect เพื่อหา path
    ที่ถูกต้อง (ตัวอย่าง path ด้านล่างเป็นเพียงจุดเริ่มค้นหา ไม่ใช่ของจริง)"""
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return {}
    try:
        data = json.loads(tag.string)
    except json.JSONDecodeError:
        return {}

    result = {}
    # เดินไล่ทุก dict/list แบบ recursive หา key ที่หน้าตาเหมือนชื่อ+ราคาสินค้า
    # (ทั่วไป: name/title/productName คู่กับ price/salePrice/unitPrice)
    def walk(node):
        if isinstance(node, dict):
            name = node.get("name") or node.get("title") or node.get("productName")
            price = node.get("price") or node.get("salePrice") or node.get("unitPrice")
            if name and price and isinstance(name, str):
                result[name] = f"{price} บ."
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data.get("props", data))
    return result


def _extract_from_dom_fallback(page):
    """กลยุทธ์ 3: อ่านค่าตรงจาก DOM หลัง JavaScript render เสร็จแล้ว
    *** ต้องแก้ selector ให้ตรงกับของจริงก่อนใช้งาน ***
    เปิด browser จริง -> คลิกขวาที่ตัวเลขราคา -> Inspect -> ดูว่า
    การ์ดสินค้าทั้งใบ (ชื่อ+ราคาอยู่ด้วยกัน) ใช้ class/attribute อะไร
    แล้วแทนที่ selector ตัวอย่างด้านล่าง"""
    result = {}
    try:
        # ตัวอย่างโครงร่าง (ต้องแก้ selector จริง):
        # cards = page.query_selector_all('[class*="product-card"]')
        # for card in cards:
        #     name_el = card.query_selector('[class*="product-name"]')
        #     price_el = card.query_selector('[class*="product-price"]')
        #     if name_el and price_el:
        #         result[name_el.inner_text().strip()] = price_el.inner_text().strip()
        pass
    except Exception as e:
        print(f"[dom-fallback] ล้มเหลว: {e}", file=sys.stderr)
    return result


def _scrape_page_with_playwright(url, wait_selector=None):
    """เปิดหน้าเว็บด้วย Chromium จริง รอ JS render เสร็จ แล้วคืน
    (BeautifulSoup ของ HTML สุดท้าย, page object สำหรับกลยุทธ์ที่ 3)"""
    if sync_playwright is None:
        raise RuntimeError(
            "ยังไม่ได้ติดตั้ง playwright — รัน: pip install playwright && playwright install chromium"
        )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.goto(url, wait_until="networkidle", timeout=30000)
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=10000)
            except Exception:
                pass  # ไม่มี selector นี้จริง ปล่อยผ่านไปลอง fallback อื่น
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        dom_prices = _extract_from_dom_fallback(page)
        browser.close()
        return soup, dom_prices


def parse_talaadthai():
    """ดึงราคาจากตลาดไท (talaadthai.com/products) ด้วย 3 กลยุทธ์เรียงลำดับ"""
    url = "https://talaadthai.com/products"
    raw_prices = {}
    try:
        soup, dom_prices = _scrape_page_with_playwright(url)

        raw_prices = _extract_from_jsonld(soup)
        if not raw_prices:
            raw_prices = _extract_from_next_data(soup)
        if not raw_prices:
            raw_prices = dom_prices

        if not raw_prices:
            print(
                "[talaadthai] ทั้ง 3 กลยุทธ์หาราคาไม่เจอ — เว็บอาจเปลี่ยนโครงสร้าง "
                "หรือต้องหา API endpoint จริงจาก Network tab ด้วยตัวเอง (ดูคอมเมนต์บนสุดของไฟล์)",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"[talaadthai] ดึงข้อมูลไม่สำเร็จ: {e}", file=sys.stderr)
        return {}

    # จับคู่ชื่อสินค้าจริงบนเว็บ (เช่น 'ทุเรียนหมอนทอง – เบอร์ใหญ่') เข้ากับชื่อใน FRUITS
    matched = {}
    for raw_name, price in raw_prices.items():
        fruit = _match_fruit_name(raw_name, FRUITS)
        if fruit and fruit not in matched:
            matched[fruit] = price
    return matched


def parse_simummuang():
    """ดึงราคาจากตลาดสี่มุมเมือง (simummuangmarket.com/pricing) ด้วย 3 กลยุทธ์เรียงลำดับ"""
    url = "https://www.simummuangmarket.com/pricing"
    raw_prices = {}
    try:
        soup, dom_prices = _scrape_page_with_playwright(url)

        raw_prices = _extract_from_jsonld(soup)
        if not raw_prices:
            raw_prices = _extract_from_next_data(soup)
        if not raw_prices:
            raw_prices = dom_prices

        if not raw_prices:
            print(
                "[simummuang] ทั้ง 3 กลยุทธ์หาราคาไม่เจอ — เว็บอาจเปลี่ยนโครงสร้าง "
                "หรือต้องหา API endpoint จริงจาก Network tab ด้วยตัวเอง (ดูคอมเมนต์บนสุดของไฟล์)",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"[simummuang] ดึงข้อมูลไม่สำเร็จ: {e}", file=sys.stderr)
        return {}

    matched = {}
    for raw_name, price in raw_prices.items():
        fruit = _match_fruit_name(raw_name, FRUITS)
        if fruit and fruit not in matched:
            matched[fruit] = price
    return matched


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
    if total == 0:
        print(
            "⚠️  พบราคา 0 รายการ — updated_at จะขยับแต่หน้าเว็บจะยังโชว์สถานะ "
            "'stale' อยู่ดี (เพราะไม่มีราคาตรงกับตาราง) ต้องแก้ selector ก่อน "
            "อ่านคอมเมนต์ด้านบนของไฟล์นี้",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
