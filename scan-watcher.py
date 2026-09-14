# -*- coding: utf-8 -*-
"""
مراقب السكانر — بيت الخبرة
بيراقب الفولدر اللي الريكو بتحفظ فيه، ويرفع أي PDF جديد للنظام.

التشغيل:  python scan-watcher.py
الإيقاف:  Ctrl+C

قبل أول تشغيل عدّل الإعدادات تحت (SCAN_DIR و EMAIL و PASSWORD).
"""

import os, sys, time, json, mimetypes, unicodedata
from datetime import datetime
from urllib import request as urlreq
from urllib.error import HTTPError, URLError

# ═════════════════ الإعدادات ═════════════════

SCAN_DIR = r"C:\Scans"                    # الفولدر اللي الريكو بتحفظ فيه
EMAIL    = "scanner@beit-alkhibra.com"    # حساب السكانر في النظام
PASSWORD = "غيّرها"                        # الباسورد بتاعه

SUPABASE_URL = "https://uwwjzxzkdxerloiqpykj.supabase.co"
ANON_KEY     = "ضع_المفتاح_هنا"           # من إعدادات Supabase → API → anon key
BUCKET       = "os-documents"

CHECK_EVERY   = 10          # يفحص كل كام ثانية
SETTLE_WAIT   = 6           # يستنى كام ثانية بعد ما حجم الملف يثبت (عشان السكان يخلص)
MAX_MB        = 30          # أكبر ملف مسموح
EXTENSIONS    = (".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff")
DONE_DIR_NAME = "_تم_الرفع"
FAIL_DIR_NAME = "_فشل"
STATE_FILE    = ".scan-watcher-state.json"

# ═════════════════════════════════════════════

def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)

def api(path, data=None, token=None, method=None, raw=None, ctype=None):
    url = f"{SUPABASE_URL}{path}"
    body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
    req = urlreq.Request(url, data=body, method=method or ("POST" if body else "GET"))
    req.add_header("apikey", ANON_KEY)
    req.add_header("Authorization", f"Bearer {token or ANON_KEY}")
    if ctype:
        req.add_header("Content-Type", ctype)
    elif body is not None and raw is None:
        req.add_header("Content-Type", "application/json")
    with urlreq.urlopen(req, timeout=180) as r:
        txt = r.read().decode("utf-8", "replace")
        return json.loads(txt) if txt.strip() else {}

def login():
    r = api("/auth/v1/token?grant_type=password",
            {"email": EMAIL, "password": PASSWORD})
    if "access_token" not in r:
        raise RuntimeError("الدخول فشل — راجع الإيميل والباسورد")
    return r["access_token"]

def safe_name(name):
    """اسم آمن للتخزين مع الحفاظ على الكود"""
    base = unicodedata.normalize("NFKD", name)
    out = "".join(c if (c.isalnum() or c in "._-") else "_" for c in base)
    return out[:120] or "scan.pdf"

def pdf_pages(path):
    """عدد الصفحات — تقدير سريع من غير مكتبات"""
    try:
        with open(path, "rb") as f:
            data = f.read()
        n = data.count(b"/Type/Page") - data.count(b"/Type/Pages")
        return n if n > 0 else None
    except Exception:
        return None

def stable(path):
    """الملف خلص كتابة؟"""
    try:
        s1 = os.path.getsize(path)
        time.sleep(SETTLE_WAIT)
        return s1 > 0 and s1 == os.path.getsize(path)
    except OSError:
        return False

def load_state():
    p = os.path.join(SCAN_DIR, STATE_FILE)
    try:
        with open(p, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_state(done):
    p = os.path.join(SCAN_DIR, STATE_FILE)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(sorted(done)[-2000:], f)
    except Exception as e:
        log(f"تحذير: معرفناش نحفظ الحالة ({e})")

def upload_one(path, token):
    name = os.path.basename(path)
    size = os.path.getsize(path)
    if size > MAX_MB * 1024 * 1024:
        raise RuntimeError(f"الملف {size/1048576:.1f} ميجا — أكبر من الحد ({MAX_MB})")

    mime = mimetypes.guess_type(name)[0] or "application/pdf"
    key = f"scans/{datetime.now():%Y/%m}/{datetime.now():%Y%m%d-%H%M%S}_{safe_name(name)}"

    with open(path, "rb") as f:
        blob = f.read()

    api(f"/storage/v1/object/{BUCKET}/{key}", raw=blob, token=token,
        ctype=mime, method="POST")

    url = f"{SUPABASE_URL}/storage/v1/object/authenticated/{BUCKET}/{key}"
    res = api("/rest/v1/rpc/os_scan_arrive", {
        "p_file_name": name, "p_path": key, "p_url": url,
        "p_size": size, "p_mime": mime, "p_pages": pdf_pages(path)
    }, token=token)
    return res

def move_to(path, folder):
    d = os.path.join(SCAN_DIR, folder)
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, os.path.basename(path))
    i = 1
    while os.path.exists(dest):
        b, e = os.path.splitext(os.path.basename(path))
        dest = os.path.join(d, f"{b}_{i}{e}")
        i += 1
    try:
        os.replace(path, dest)
    except OSError as e:
        log(f"تحذير: معرفناش ننقل الملف ({e})")

def main():
    if not os.path.isdir(SCAN_DIR):
        log(f"الفولدر مش موجود: {SCAN_DIR}")
        sys.exit(1)
    if "ضع_المفتاح" in ANON_KEY or PASSWORD == "غيّرها":
        log("لسه محطتش المفتاح أو الباسورد — افتح الملف وعدّل الإعدادات فوق")
        sys.exit(1)

    log("بيدخل النظام…")
    token = login()
    tok_at = time.time()
    log(f"تمام. بيراقب: {SCAN_DIR}")
    log("سيبه شغّال. للإيقاف اضغط Ctrl+C")

    done = load_state()

    while True:
        try:
            # التوكن بيخلص بعد ساعة
            if time.time() - tok_at > 2700:
                token = login(); tok_at = time.time()
                log("جدّد الدخول")

            for name in sorted(os.listdir(SCAN_DIR)):
                path = os.path.join(SCAN_DIR, name)
                if not os.path.isfile(path):
                    continue
                if name.startswith(".") or name in (STATE_FILE,):
                    continue
                if not name.lower().endswith(EXTENSIONS):
                    continue
                sig = f"{name}|{os.path.getsize(path)}"
                if sig in done:
                    continue
                if not stable(path):
                    continue

                log(f"بيرفع: {name} ({os.path.getsize(path)/1048576:.1f} ميجا)")
                try:
                    res = upload_one(path, token)
                    guess = (res or {}).get("guess")
                    log(f"  اترفع ✓ " + (f"— اتخمّن: {guess}" if guess else "— محتاج توجيه"))
                    done.add(sig); save_state(done)
                    move_to(path, DONE_DIR_NAME)
                except HTTPError as e:
                    detail = e.read().decode("utf-8", "replace")[:200]
                    log(f"  فشل ({e.code}): {detail}")
                    if e.code in (401, 403):
                        token = login(); tok_at = time.time()
                        log("  جدّد الدخول — هيجرّب تاني الدورة الجاية")
                    else:
                        move_to(path, FAIL_DIR_NAME)
                        done.add(sig); save_state(done)
                except Exception as e:
                    log(f"  فشل: {e}")
                    move_to(path, FAIL_DIR_NAME)
                    done.add(sig); save_state(done)

            time.sleep(CHECK_EVERY)

        except KeyboardInterrupt:
            log("اتقفل.")
            return
        except (URLError, OSError) as e:
            log(f"مشكلة اتصال: {e} — هيجرّب تاني بعد شوية")
            time.sleep(30)

if __name__ == "__main__":
    main()
