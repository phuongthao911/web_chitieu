import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
# pyrefly: ignore [missing-import]
from sqlalchemy import text
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from database import engine, get_db, migrate_database_multi_tenant
from models import (
    Base,
    User,
    Expense,
    Category,
    Budget,
    RecurringTransaction,
    Note,
    DayCounter,
    get_vietnam_time,
)
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_current_user_optional,
    login_rate_limiter,
    IS_COOKIE_SECURE,
)

BASE_DIR = Path(__file__).resolve().parent

ALLOWED_WALLETS = {"Tiền mặt", "Tài khoản tiết kiệm", "TK ngân hàng"}

app = FastAPI()

# Run database schema migrations for multi-tenancy
migrate_database_multi_tenant()
Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

DEFAULT_USER_CATEGORIES = [
    # Income categories
    {"name": "Lương Ameno", "type": "income"},
    {"name": "Lương Winggo", "type": "income"},
    {"name": "Thu nhập khác", "type": "income"},
    {"name": "Other", "type": "income"},
    # Expense categories
    {"name": "Đổ xăng", "type": "expense"},
    {"name": "Ăn ngoài", "type": "expense"},
    {"name": "Đi chợ", "type": "expense"},
    {"name": "Chi phí phát sinh", "type": "expense"},
    {"name": "Gửi xe", "type": "expense"},
    {"name": "Đi chơi", "type": "expense"},
    {"name": "Trả nợ", "type": "expense"},
    {"name": "Quỹ Ameno", "type": "expense"},
    {"name": "Shopping online", "type": "expense"},
]


def seed_default_categories_for_user(db: Session, user_id: int):
    """Seed initial categories for newly registered user."""
    for cat in DEFAULT_USER_CATEGORIES:
        existing = (
            db.query(Category)
            .filter(Category.user_id == user_id, Category.name == cat["name"])
            .first()
        )
        if not existing:
            db.add(Category(user_id=user_id, name=cat["name"], type=cat["type"]))
    db.commit()


def serialize_expense(expense: Expense) -> dict:
    return {
        "id": expense.id,
        "type": expense.transaction_type,
        "category": expense.category,
        "wallet": expense.wallet,
        "destination_wallet": expense.destination_wallet,
        "amount": expense.amount,
        "note": expense.note,
        "created_at": expense.created_at.strftime("%Y-%m-%d %H:%M") if expense.created_at else None,
    }


# =========================================================
# HEALTH CHECK
# =========================================================
@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


# =========================================================
# HTML PAGES ROUTING
# =========================================================
@app.get("/")
def dashboard(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"current_user": current_user},
    )


@app.get("/login")
def login_page(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={},
    )


@app.get("/register")
def register_page(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={},
    )


# =========================================================
# AUTHENTICATION API
# =========================================================
@app.post("/api/auth/register")
async def api_register(request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Dữ liệu không hợp lệ.")

    username = str(payload.get("username", "")).strip().lower()
    password = str(payload.get("password", "")).strip()

    if not username or len(username) < 3:
        raise HTTPException(status_code=400, detail="Tên đăng nhập phải có ít nhất 3 ký tự.")
    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu phải có ít nhất 6 ký tự.")

    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại.")

    user = User(
        username=username,
        password_hash=hash_password(password),
        created_at=get_vietnam_time()
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Seed starter categories for new user
    seed_default_categories_for_user(db, user.id)

    # Create JWT token and set HttpOnly cookie
    token = create_access_token(user.id, user.username)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=IS_COOKIE_SECURE,
        max_age=7 * 24 * 3600
    )

    return {
        "status": "success",
        "message": "Đăng ký tài khoản thành công.",
        "user": {"id": user.id, "username": user.username}
    }


@app.post("/api/auth/login")
async def api_login(request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Dữ liệu không hợp lệ.")

    username = str(payload.get("username", "")).strip().lower()
    password = str(payload.get("password", "")).strip()

    client_ip = request.client.host if request.client else "unknown"

    # Brute-force rate limiting
    if login_rate_limiter.is_rate_limited(client_ip, username):
        raise HTTPException(
            status_code=429,
            detail="Bạn đã thử đăng nhập sai quá nhiều lần. Vui lòng thử lại sau 1 phút."
        )

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        login_rate_limiter.record_failure(client_ip, username)
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu.")

    # Success: reset rate limit attempts
    login_rate_limiter.reset(client_ip, username)

    token = create_access_token(user.id, user.username)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=IS_COOKIE_SECURE,
        max_age=7 * 24 * 3600
    )

    return {
        "status": "success",
        "message": "Đăng nhập thành công.",
        "user": {"id": user.id, "username": user.username}
    }


@app.post("/api/auth/logout")
def api_logout(response: Response):
    response.delete_cookie(key="access_token", httponly=True, samesite="lax")
    return {"status": "success", "message": "Đã đăng xuất."}


@app.get("/api/auth/me")
def api_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "created_at": current_user.created_at.strftime("%Y-%m-%d %H:%M:%S") if current_user.created_at else None
    }


# =========================================================
# BACKUP & RESTORE API
# =========================================================
@app.get("/api/backup/json")
def backup_json(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    expenses = (
        db.query(Expense)
        .filter(Expense.user_id == current_user.id)
        .order_by(Expense.created_at.desc(), Expense.id.desc())
        .all()
    )
    categories = db.query(Category).filter(Category.user_id == current_user.id).all()
    budgets = db.query(Budget).filter(Budget.user_id == current_user.id).all()
    recurring = db.query(RecurringTransaction).filter(RecurringTransaction.user_id == current_user.id).all()
    notes = db.query(Note).filter(Note.user_id == current_user.id).order_by(Note.pinned.desc(), Note.id.desc()).all()
    counters = db.query(DayCounter).filter(DayCounter.user_id == current_user.id).order_by(DayCounter.id.desc()).all()

    data = {
        "version": "3.0",
        "exported_at": get_vietnam_time().strftime("%Y-%m-%d %H:%M:%S"),
        "user": current_user.username,
        "transactions": [serialize_expense(expense) for expense in expenses],
        "categories": [{"id": cat.id, "name": cat.name, "type": cat.type} for cat in categories],
        "budgets": [{"id": b.id, "category_name": b.category_name, "amount_limit": b.amount_limit, "month": b.month} for b in budgets],
        "recurring": [
            {
                "id": r.id,
                "type": r.transaction_type,
                "amount": r.amount,
                "category": r.category,
                "wallet": r.wallet,
                "destination_wallet": r.destination_wallet,
                "note": r.note,
                "day_of_month": r.day_of_month,
                "last_executed_month": r.last_executed_month
            }
            for r in recurring
        ],
        "notes": [
            {
                "id": n.id,
                "title": n.title,
                "content_html": n.content_html,
                "color": n.color,
                "pinned": bool(n.pinned),
                "updated_at": n.updated_at,
                "created_at": n.created_at.strftime("%Y-%m-%d %H:%M:%S") if n.created_at else ""
            }
            for n in notes
        ],
        "counters": [
            {
                "id": c.id,
                "title": c.title,
                "target_date": c.target_date,
                "mode": c.mode,
                "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else ""
            }
            for c in counters
        ]
    }
    filename = f"expense_backup_{current_user.username}_{get_vietnam_time().strftime('%Y%m%d_%H%M%S')}.json"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return Response(content=json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json", headers=headers)


@app.get("/api/backup/csv")
def backup_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    expenses = (
        db.query(Expense)
        .filter(Expense.user_id == current_user.id)
        .order_by(Expense.created_at.desc(), Expense.id.desc())
        .all()
    )
    categories = db.query(Category).filter(Category.user_id == current_user.id).all()
    budgets = db.query(Budget).filter(Budget.user_id == current_user.id).all()
    recurring = db.query(RecurringTransaction).filter(RecurringTransaction.user_id == current_user.id).all()
    notes = db.query(Note).filter(Note.user_id == current_user.id).order_by(Note.pinned.desc(), Note.id.desc()).all()
    counters = db.query(DayCounter).filter(DayCounter.user_id == current_user.id).order_by(DayCounter.id.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # 1. Transactions Block
    writer.writerow(["=== TRANSACTIONS / GIAO DỊCH ==="])
    writer.writerow(["ID", "Loại", "Danh mục", "Ví", "Ví đích", "Số tiền (VND)", "Ghi chú", "Ngày tạo"])
    for exp in expenses:
        writer.writerow([
            exp.id,
            exp.transaction_type,
            exp.category,
            exp.wallet,
            exp.destination_wallet or "",
            f"{exp.amount:,.0f}",
            exp.note,
            exp.created_at.strftime("%Y-%m-%d %H:%M") if exp.created_at else ""
        ])

    writer.writerow([])

    # 2. Categories Block
    writer.writerow(["=== CATEGORIES / DANH MỤC ==="])
    writer.writerow(["ID", "Tên danh mục", "Loại (income/expense)"])
    for cat in categories:
        writer.writerow([cat.id, cat.name, cat.type])

    writer.writerow([])

    # 3. Budgets Block
    writer.writerow(["=== BUDGETS / NGÂN SÁCH ==="])
    writer.writerow(["ID", "Danh mục", "Hạn mức (VND)", "Tháng (YYYY-MM)"])
    for b in budgets:
        writer.writerow([b.id, b.category_name, f"{b.amount_limit:,.0f}", b.month])

    writer.writerow([])

    # 4. Recurring Block
    writer.writerow(["=== RECURRING / GIAO DỊCH ĐỊNH KỲ ==="])
    writer.writerow(["ID", "Loại", "Số tiền (VND)", "Danh mục", "Ví", "Ví đích", "Ghi chú", "Ngày thực hiện", "Tháng chạy gần nhất"])
    for r in recurring:
        writer.writerow([
            r.id,
            r.transaction_type,
            f"{r.amount:,.0f}",
            r.category,
            r.wallet,
            r.destination_wallet or "",
            r.note,
            r.day_of_month,
            r.last_executed_month or ""
        ])

    writer.writerow([])

    # 5. Notes Block
    writer.writerow(["=== NOTES / GHI CHÚ ==="])
    writer.writerow(["ID", "Tiêu đề", "Nội dung", "Màu sắc", "Ghim", "Ngày cập nhật", "Ngày tạo"])
    for n in notes:
        writer.writerow([
            n.id,
            n.title,
            n.content_html,
            n.color,
            "Có" if n.pinned else "Không",
            n.updated_at,
            n.created_at.strftime("%Y-%m-%d %H:%M:%S") if n.created_at else ""
        ])

    writer.writerow([])

    # 6. Counters Block
    writer.writerow(["=== DAY COUNTERS / ĐẾM NGÀY ==="])
    writer.writerow(["ID", "Tiêu đề", "Ngày đích (YYYY-MM-DD)", "Chế độ (workday/calendar)", "Ngày tạo"])
    for c in counters:
        writer.writerow([
            c.id,
            c.title,
            c.target_date,
            c.mode,
            c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else ""
        ])

    filename = f"expense_backup_{current_user.username}_{get_vietnam_time().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return Response(content=output.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)


@app.post("/api/backup/import")
async def import_backup(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON format.")
    
    if isinstance(body, list):
        tx_list = body
        cat_list = []
        budget_list = []
        recurring_list = []
        notes_list = []
        counters_list = []
    elif isinstance(body, dict):
        tx_list = body.get("transactions", [])
        cat_list = body.get("categories", [])
        budget_list = body.get("budgets", [])
        recurring_list = body.get("recurring", [])
        notes_list = body.get("notes", [])
        counters_list = body.get("counters", [])
    else:
        raise HTTPException(status_code=400, detail="Invalid backup payload structure.")
    
    imported_tx = 0
    imported_cats = 0
    imported_budgets = 0
    imported_recurring = 0
    imported_notes = 0
    imported_counters = 0

    # 1. Import Categories - enforce current_user.id
    for item in cat_list:
        c_name = str(item.get("name", "")).strip()
        c_type = str(item.get("type", "")).strip().lower()
        if c_name and c_type in {"income", "expense"}:
            existing = db.query(Category).filter(
                Category.user_id == current_user.id,
                Category.name == c_name
            ).first()
            if not existing:
                db.add(Category(user_id=current_user.id, name=c_name, type=c_type))
                imported_cats += 1

    # 2. Import Budgets - enforce current_user.id
    for item in budget_list:
        cat_name = str(item.get("category_name", "")).strip()
        month = str(item.get("month", "")).strip()
        try:
            limit = float(item.get("amount_limit", 0))
        except (TypeError, ValueError):
            continue
        if cat_name and month and limit >= 0:
            existing = db.query(Budget).filter(
                Budget.user_id == current_user.id,
                Budget.category_name == cat_name,
                Budget.month == month
            ).first()
            if existing:
                existing.amount_limit = limit
            else:
                db.add(Budget(user_id=current_user.id, category_name=cat_name, month=month, amount_limit=limit))
                imported_budgets += 1

    # 3. Import Recurring Transactions - enforce current_user.id
    for item in recurring_list:
        r_type = str(item.get("type", "")).strip()
        r_cat = str(item.get("category", "")).strip()
        r_wallet = str(item.get("wallet", "")).strip()
        r_dest = str(item.get("destination_wallet", "")).strip() if item.get("destination_wallet") else None
        r_note = str(item.get("note", "")).strip()
        try:
            r_amount = float(item.get("amount", 0))
            r_day = int(item.get("day_of_month", 1))
        except (TypeError, ValueError):
            continue
        if r_type in {"Income", "Expense", "Transfer"} and r_amount > 0 and 1 <= r_day <= 31:
            rec = RecurringTransaction(
                user_id=current_user.id,
                transaction_type=r_type,
                amount=r_amount,
                category=r_cat,
                wallet=r_wallet,
                destination_wallet=r_dest,
                note=r_note,
                day_of_month=r_day,
                last_executed_month=item.get("last_executed_month")
            )
            db.add(rec)
            imported_recurring += 1

    # 4. Import Notes - enforce current_user.id
    for item in notes_list:
        n_title = str(item.get("title", "")).strip()
        n_html = str(item.get("content_html", "")).strip()
        n_color = str(item.get("color", "pink")).strip()
        n_pinned = 1 if item.get("pinned") else 0
        n_updated = str(item.get("updated_at") or get_vietnam_time().strftime("%d/%m/%Y")).strip()
        if n_title:
            db.add(Note(
                user_id=current_user.id,
                title=n_title,
                content_html=n_html,
                color=n_color,
                pinned=n_pinned,
                updated_at=n_updated
            ))
            imported_notes += 1

    # 5. Import Day Counters - enforce current_user.id
    for item in counters_list:
        c_title = str(item.get("title", "")).strip()
        c_date = str(item.get("target_date", "")).strip()
        c_mode = str(item.get("mode", "workday")).strip()
        if c_title and c_date:
            db.add(DayCounter(
                user_id=current_user.id,
                title=c_title,
                target_date=c_date,
                mode=c_mode
            ))
            imported_counters += 1

    # 6. Import Transactions - enforce current_user.id
    for item in tx_list:
        try:
            amount = float(item.get("amount", 0))
        except (TypeError, ValueError):
            continue

        if amount <= 0:
            continue

        raw_type = str(item.get("type", "")).strip().lower()
        if raw_type == "income":
            transaction_type = "Income"
        elif raw_type == "transfer":
            transaction_type = "Transfer"
        else:
            transaction_type = "Expense"

        category = str(item.get("category", "")).strip()
        wallet = str(item.get("wallet", "")).strip()
        destination_wallet = str(item.get("destination_wallet", "")).strip() if item.get("destination_wallet") else None
        note = str(item.get("note", "")).strip()
        created_at_str = item.get("created_at")

        if created_at_str:
            try:
                created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M")
            except ValueError:
                try:
                    created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    created_at = get_vietnam_time()
        else:
            created_at = get_vietnam_time()

        expense = Expense(
            user_id=current_user.id,
            transaction_type=transaction_type,
            category=category or ("Chuyển ví" if transaction_type == "Transfer" else "Other"),
            wallet=wallet if wallet in ALLOWED_WALLETS else "Tiền mặt",
            destination_wallet=destination_wallet if transaction_type == "Transfer" else None,
            amount=amount,
            note=note or "-",
            created_at=created_at,
        )
        db.add(expense)
        imported_tx += 1

    db.commit()

    return {
        "status": "ok",
        "imported_transactions": imported_tx,
        "imported_categories": imported_cats,
        "imported_budgets": imported_budgets,
        "imported_recurring": imported_recurring,
        "imported_notes": imported_notes,
        "imported_counters": imported_counters,
        "message": f"Khôi phục thành công cho {current_user.username}!"
    }


@app.post("/api/backup/import-csv")
async def import_backup_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Vui lòng tải lên tệp tin CSV hợp lệ.")

    content = await file.read()
    try:
        text_content = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text_content = content.decode("utf-8")
        except UnicodeDecodeError:
            text_content = content.decode("latin-1")

    reader = list(csv.reader(io.StringIO(text_content)))
    if not reader:
        raise HTTPException(status_code=400, detail="Tệp tin CSV rỗng.")

    imported_tx = 0
    imported_cats = 0
    imported_budgets = 0
    imported_recurring = 0
    imported_notes = 0
    imported_counters = 0

    current_section = "transactions"
    header = None

    for row in reader:
        if not row or not any(row):
            continue
        
        first_cell = row[0].strip()

        if "TRANSACTIONS" in first_cell or "=== GIAO DỊCH" in first_cell:
            current_section = "transactions"
            header = None
            continue
        elif "CATEGORIES" in first_cell or "=== DANH MỤC" in first_cell:
            current_section = "categories"
            header = None
            continue
        elif "BUDGETS" in first_cell or "=== NGÂN SÁCH" in first_cell:
            current_section = "budgets"
            header = None
            continue
        elif "RECURRING" in first_cell or "=== GIAO DỊCH ĐỊNH KỲ" in first_cell:
            current_section = "recurring"
            header = None
            continue
        elif "NOTES" in first_cell or "=== GHI CHÚ" in first_cell:
            current_section = "notes"
            header = None
            continue
        elif "DAY COUNTERS" in first_cell or "COUNTERS" in first_cell or "=== ĐẾM NGÀY" in first_cell:
            current_section = "counters"
            header = None
            continue

        if header is None:
            header = [c.strip().lower() for c in row]
            continue
        
        if current_section == "transactions":
            data = dict(zip(header, [c.strip() for c in row]))
            t_type_raw = data.get("loại giao dịch") or data.get("loại") or data.get("type") or ""
            if "thu" in t_type_raw.lower() or t_type_raw.lower() == "income":
                t_type = "Income"
            elif "chuyển" in t_type_raw.lower() or t_type_raw.lower() == "transfer":
                t_type = "Transfer"
            else:
                t_type = "Expense"

            category = data.get("danh mục") or data.get("category") or "Other"
            wallet = data.get("ví nguồn") or data.get("ví") or data.get("wallet") or "Tiền mặt"
            dest_wallet = data.get("ví đích") or data.get("destination_wallet") or None
            note = data.get("ghi chú") or data.get("note") or "-"
            amount_raw = data.get("số tiền (vnd)") or data.get("số tiền") or data.get("amount") or "0"
            date_raw = data.get("ngày tạo") or data.get("ngày") or data.get("created_at") or ""

            try:
                clean_amount = float(str(amount_raw).replace(",", "").replace("VND", "").replace("vnd", "").strip())
            except (ValueError, TypeError):
                continue

            if clean_amount <= 0:
                continue

            if date_raw:
                try:
                    created_at = datetime.strptime(date_raw, "%Y-%m-%d %H:%M")
                except ValueError:
                    try:
                        created_at = datetime.strptime(date_raw, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        created_at = get_vietnam_time()
            else:
                created_at = get_vietnam_time()

            expense = Expense(
                user_id=current_user.id,
                transaction_type=t_type,
                category=category or ("Chuyển ví" if t_type == "Transfer" else "Other"),
                wallet=wallet if wallet in ALLOWED_WALLETS else "Tiền mặt",
                destination_wallet=dest_wallet if t_type == "Transfer" else None,
                amount=clean_amount,
                note=note or "-",
                created_at=created_at,
            )
            db.add(expense)
            imported_tx += 1

        elif current_section == "categories":
            data = dict(zip(header, [c.strip() for c in row]))
            name = data.get("tên danh mục") or data.get("tên") or data.get("name")
            c_type = (data.get("loại") or data.get("type") or "expense").strip().lower()
            if name and c_type in {"income", "expense"}:
                existing = db.query(Category).filter(
                    Category.user_id == current_user.id,
                    Category.name == name
                ).first()
                if not existing:
                    db.add(Category(user_id=current_user.id, name=name, type=c_type))
                    imported_cats += 1

        elif current_section == "budgets":
            data = dict(zip(header, [c.strip() for c in row]))
            c_name = data.get("danh mục") or data.get("category_name")
            month = data.get("tháng (yyyy-mm)") or data.get("tháng") or data.get("month")
            amount_raw = data.get("hạn mức (vnd)") or data.get("hạn mức") or data.get("amount_limit")
            try:
                limit = float(str(amount_raw).replace(",", "").replace("VND", "").replace("vnd", "").strip())
            except (ValueError, TypeError):
                continue
            if c_name and month and limit >= 0:
                existing = db.query(Budget).filter(
                    Budget.user_id == current_user.id,
                    Budget.category_name == c_name,
                    Budget.month == month
                ).first()
                if existing:
                    existing.amount_limit = limit
                else:
                    db.add(Budget(user_id=current_user.id, category_name=c_name, month=month, amount_limit=limit))
                    imported_budgets += 1

        elif current_section == "recurring":
            data = dict(zip(header, [c.strip() for c in row]))
            r_type = data.get("loại") or data.get("type") or "Expense"
            r_cat = data.get("danh mục") or data.get("category") or "Other"
            r_wallet = data.get("ví") or data.get("wallet") or "Tiền mặt"
            r_dest = data.get("ví đích") or data.get("destination_wallet") or None
            r_note = data.get("ghi chú") or data.get("note") or "-"
            amount_raw = data.get("số tiền (vnd)") or data.get("số tiền") or data.get("amount") or "0"
            day_raw = data.get("ngày thực hiện") or data.get("day_of_month") or "1"
            try:
                r_amount = float(str(amount_raw).replace(",", "").replace("VND", "").replace("vnd", "").strip())
                r_day = int(str(day_raw).strip())
            except (ValueError, TypeError):
                continue
            if r_type in {"Income", "Expense", "Transfer"} and r_amount > 0 and 1 <= r_day <= 31:
                db.add(RecurringTransaction(
                    user_id=current_user.id,
                    transaction_type=r_type,
                    amount=r_amount,
                    category=r_cat,
                    wallet=r_wallet,
                    destination_wallet=r_dest,
                    note=r_note,
                    day_of_month=r_day
                ))
                imported_recurring += 1

        elif current_section == "notes":
            data = dict(zip(header, [c.strip() for c in row]))
            title = data.get("tiêu đề") or data.get("title")
            content_html = data.get("nội dung") or data.get("content_html") or ""
            color = data.get("màu sắc") or data.get("color") or "pink"
            pinned_raw = data.get("ghim") or data.get("pinned") or "Không"
            pinned = 1 if "có" in str(pinned_raw).lower() or str(pinned_raw) in ("1", "true") else 0
            updated_at = data.get("ngày cập nhật") or data.get("updated_at") or get_vietnam_time().strftime("%d/%m/%Y")
            if title:
                db.add(Note(
                    user_id=current_user.id,
                    title=title,
                    content_html=content_html,
                    color=color,
                    pinned=pinned,
                    updated_at=updated_at
                ))
                imported_notes += 1

        elif current_section == "counters":
            data = dict(zip(header, [c.strip() for c in row]))
            title = data.get("tiêu đề") or data.get("title")
            target_date = data.get("ngày đích (yyyy-mm-dd)") or data.get("ngày đích") or data.get("target_date")
            mode = data.get("chế độ (workday/calendar)") or data.get("chế độ") or data.get("mode") or "workday"
            if title and target_date:
                db.add(DayCounter(
                    user_id=current_user.id,
                    title=title,
                    target_date=target_date,
                    mode=mode
                ))
                imported_counters += 1

    db.commit()

    msg = f"Đã nhập thành công cho {current_user.username}: {imported_tx} giao dịch, {imported_cats} danh mục, {imported_budgets} ngân sách, {imported_recurring} định kỳ, {imported_notes} ghi chú, {imported_counters} đếm ngày."
    return {"status": "ok", "message": msg}


# =========================================================
# TRANSACTIONS API (CRUD)
# =========================================================
@app.get("/api/transactions")
def list_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    expenses = (
        db.query(Expense)
        .filter(Expense.user_id == current_user.id)
        .order_by(Expense.created_at.desc(), Expense.id.desc())
        .all()
    )
    return [serialize_expense(expense) for expense in expenses]


@app.post("/api/transactions")
def create_transaction(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    transaction_type = str(payload.get("type", "")).strip().lower()
    category = str(payload.get("category", "")).strip()
    wallet = str(payload.get("wallet", "")).strip()
    destination_wallet = str(payload.get("destination_wallet", "")).strip() if payload.get("destination_wallet") else None
    note = str(payload.get("note", "")).strip()

    try:
        amount = float(payload.get("amount"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Amount must be a number.")

    if transaction_type not in {"income", "expense", "transfer"}:
        raise HTTPException(status_code=400, detail="Type must be income, expense, or transfer.")

    if transaction_type == "transfer":
        category = "Chuyển ví"
        if not destination_wallet or destination_wallet not in ALLOWED_WALLETS:
            raise HTTPException(status_code=400, detail="Destination wallet is required and must be valid for transfer.")
        if wallet == destination_wallet:
            raise HTTPException(status_code=400, detail="Source and destination wallets cannot be the same.")
    else:
        if not category:
            raise HTTPException(status_code=400, detail="Category is required.")

    if wallet not in ALLOWED_WALLETS:
        raise HTTPException(status_code=400, detail="Wallet is required.")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")

    expense = Expense(
        user_id=current_user.id,
        transaction_type="Income" if transaction_type == "income" else ("Expense" if transaction_type == "expense" else "Transfer"),
        category=category,
        wallet=wallet,
        destination_wallet=destination_wallet if transaction_type == "transfer" else None,
        amount=amount,
        note=note or "-",
        created_at=get_vietnam_time(),
    )

    db.add(expense)
    db.commit()
    db.refresh(expense)

    return serialize_expense(expense)


@app.put("/api/transactions/{expense_id}")
def update_transaction(
    expense_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == current_user.id).first()

    if expense is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    transaction_type = str(payload.get("type", "")).strip().lower()
    category = str(payload.get("category", "")).strip()
    wallet = str(payload.get("wallet", "")).strip()
    destination_wallet = str(payload.get("destination_wallet", "")).strip() if payload.get("destination_wallet") else None
    note = str(payload.get("note", "")).strip()

    try:
        amount = float(payload.get("amount"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Amount must be a number.")

    if transaction_type not in {"income", "expense", "transfer"}:
        raise HTTPException(status_code=400, detail="Type must be income, expense, or transfer.")

    if transaction_type == "transfer":
        category = "Chuyển ví"
        if not destination_wallet or destination_wallet not in ALLOWED_WALLETS:
            raise HTTPException(status_code=400, detail="Destination wallet is required and must be valid for transfer.")
        if wallet == destination_wallet:
            raise HTTPException(status_code=400, detail="Source and destination wallets cannot be the same.")
    else:
        if not category:
            raise HTTPException(status_code=400, detail="Category is required.")

    if wallet not in ALLOWED_WALLETS:
        raise HTTPException(status_code=400, detail="Wallet is required.")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")

    expense.transaction_type = "Income" if transaction_type == "income" else ("Expense" if transaction_type == "expense" else "Transfer")
    expense.category = category
    expense.wallet = wallet
    expense.destination_wallet = destination_wallet if transaction_type == "transfer" else None
    expense.amount = amount
    expense.note = note or "-"

    db.commit()
    db.refresh(expense)

    return serialize_expense(expense)


@app.delete("/api/transactions/{expense_id}")
def delete_transaction(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == current_user.id).first()

    if expense is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    db.delete(expense)
    db.commit()

    return {"ok": True}


# =========================================================
# CATEGORIES API (CRUD)
# =========================================================
@app.get("/api/categories")
def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    categories = db.query(Category).filter(Category.user_id == current_user.id).all()
    return [{"id": cat.id, "name": cat.name, "type": cat.type} for cat in categories]


@app.post("/api/categories")
def create_category(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    name = str(payload.get("name", "")).strip()
    c_type = str(payload.get("type", "")).strip().lower()

    if not name:
        raise HTTPException(status_code=400, detail="Tên danh mục không được để trống.")
    if c_type not in {"income", "expense"}:
        raise HTTPException(status_code=400, detail="Loại danh mục phải là income hoặc expense.")

    existing = db.query(Category).filter(
        Category.user_id == current_user.id,
        Category.name == name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Danh mục này đã tồn tại trong tài khoản của bạn.")

    cat = Category(user_id=current_user.id, name=name, type=c_type)
    db.add(cat)
    db.commit()
    db.refresh(cat)

    return {"id": cat.id, "name": cat.name, "type": cat.type}


@app.put("/api/categories/{category_id}")
def update_category(
    category_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cat = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == current_user.id
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Không tìm thấy danh mục.")

    name = str(payload.get("name", "")).strip()
    c_type = str(payload.get("type", "")).strip().lower()

    if not name:
        raise HTTPException(status_code=400, detail="Tên danh mục không được để trống.")
    if c_type not in {"income", "expense"}:
        raise HTTPException(status_code=400, detail="Loại danh mục phải là income hoặc expense.")

    # Check duplicate
    existing = db.query(Category).filter(
        Category.user_id == current_user.id,
        Category.name == name,
        Category.id != category_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Danh mục với tên này đã tồn tại.")

    cat.name = name
    cat.type = c_type
    db.commit()
    db.refresh(cat)

    return {"id": cat.id, "name": cat.name, "type": cat.type}


@app.delete("/api/categories/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cat = db.query(Category).filter(
        Category.id == category_id,
        Category.user_id == current_user.id
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Không tìm thấy danh mục.")

    db.delete(cat)
    db.commit()
    return {"ok": True}


# =========================================================
# BUDGETS API
# =========================================================
@app.get("/api/budgets")
def get_budgets(
    month: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if len(month) != 7 or month[4] != "-":
        raise HTTPException(status_code=400, detail="Invalid month format. Expected YYYY-MM.")

    categories = (
        db.query(Category)
        .filter(Category.user_id == current_user.id, Category.type == "expense")
        .all()
    )
    budgets = (
        db.query(Budget)
        .filter(Budget.user_id == current_user.id, Budget.month == month)
        .all()
    )
    budget_map = {b.category_name: b for b in budgets}

    expenses = (
        db.query(Expense)
        .filter(Expense.user_id == current_user.id, Expense.transaction_type == "Expense")
        .all()
    )

    spending_map = {}
    for exp in expenses:
        exp_date_str = exp.created_at.strftime("%Y-%m") if exp.created_at else ""
        if exp_date_str == month:
            spending_map[exp.category] = spending_map.get(exp.category, 0.0) + exp.amount

    result = []
    for cat in categories:
        b = budget_map.get(cat.name)
        result.append({
            "category_name": cat.name,
            "amount_limit": b.amount_limit if b else 0.0,
            "actual_spending": spending_map.get(cat.name, 0.0),
            "month": month
        })

    return result


@app.post("/api/budgets")
def save_budget(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    category_name = str(payload.get("category_name", "")).strip()
    month = str(payload.get("month", "")).strip()
    try:
        amount_limit = float(payload.get("amount_limit"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Amount limit must be a number.")

    if not category_name or not month:
        raise HTTPException(status_code=400, detail="Category name and month are required.")
    if amount_limit < 0:
        raise HTTPException(status_code=400, detail="Amount limit cannot be negative.")

    b = (
        db.query(Budget)
        .filter(
            Budget.user_id == current_user.id,
            Budget.category_name == category_name,
            Budget.month == month
        )
        .first()
    )
    if b:
        b.amount_limit = amount_limit
    else:
        b = Budget(user_id=current_user.id, category_name=category_name, month=month, amount_limit=amount_limit)
        db.add(b)

    db.commit()
    db.refresh(b)
    return {"category_name": b.category_name, "month": b.month, "amount_limit": b.amount_limit}


# =========================================================
# RECURRING TRANSACTIONS API
# =========================================================
def run_recurring_scheduler_on_db(db: Session):
    now_vn = get_vietnam_time()
    current_month_str = now_vn.strftime("%Y-%m")
    current_day = now_vn.day

    configs = db.query(RecurringTransaction).all()
    for rec in configs:
        if rec.last_executed_month == current_month_str:
            continue
        
        if current_day >= rec.day_of_month:
            try:
                execution_time = now_vn.replace(day=rec.day_of_month, hour=9, minute=0, second=0, microsecond=0)
                exp = Expense(
                    user_id=rec.user_id,
                    transaction_type=rec.transaction_type,
                    category=rec.category,
                    wallet=rec.wallet,
                    destination_wallet=rec.destination_wallet,
                    amount=rec.amount,
                    note=f"[Định kỳ] {rec.note}",
                    created_at=execution_time
                )
                db.add(exp)
                rec.last_executed_month = current_month_str
                db.commit()
            except Exception as e:
                db.rollback()
                print("Error executing recurring transaction:", e)


@app.on_event("startup")
def startup_event():
    db = Session(bind=engine)
    try:
        run_recurring_scheduler_on_db(db)
    except Exception as e:
        print("Error executing startup recurring tasks:", e)
    finally:
        db.close()


@app.get("/api/recurring")
def list_recurring(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    items = db.query(RecurringTransaction).filter(RecurringTransaction.user_id == current_user.id).all()
    return [
        {
            "id": r.id,
            "type": r.transaction_type,
            "amount": r.amount,
            "category": r.category,
            "wallet": r.wallet,
            "destination_wallet": r.destination_wallet,
            "note": r.note,
            "day_of_month": r.day_of_month,
            "last_executed_month": r.last_executed_month
        }
        for r in items
    ]


@app.post("/api/recurring")
def create_recurring(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    t_type = str(payload.get("type", "")).strip()
    try:
        amount = float(payload.get("amount"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Amount must be a number.")
    
    category = str(payload.get("category", "")).strip()
    wallet = str(payload.get("wallet", "")).strip()
    destination_wallet = str(payload.get("destination_wallet", "")).strip() if payload.get("destination_wallet") else None
    note = str(payload.get("note", "")).strip()
    try:
        day_of_month = int(payload.get("day_of_month"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Day of month must be a number (1-31).")

    if t_type not in {"Income", "Expense", "Transfer"}:
        raise HTTPException(status_code=400, detail="Type must be Income, Expense, or Transfer.")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")
    if t_type != "Transfer" and not category:
        raise HTTPException(status_code=400, detail="Category is required.")
    if wallet not in ALLOWED_WALLETS:
        raise HTTPException(status_code=400, detail="Wallet is invalid.")
    if t_type == "Transfer":
        category = "Chuyển ví"
        if not destination_wallet or destination_wallet not in ALLOWED_WALLETS:
            raise HTTPException(status_code=400, detail="Destination wallet is required and must be valid.")
        if wallet == destination_wallet:
            raise HTTPException(status_code=400, detail="Source and destination wallets must differ.")
    if day_of_month < 1 or day_of_month > 31:
        raise HTTPException(status_code=400, detail="Day of month must be between 1 and 31.")

    rec = RecurringTransaction(
        user_id=current_user.id,
        transaction_type=t_type,
        amount=amount,
        category=category,
        wallet=wallet,
        destination_wallet=destination_wallet if t_type == "Transfer" else None,
        note=note or "-",
        day_of_month=day_of_month,
        last_executed_month=None
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    
    run_recurring_scheduler_on_db(db)
    
    return {"id": rec.id, "type": rec.transaction_type, "amount": rec.amount}


@app.delete("/api/recurring/{recurring_id}")
def delete_recurring(
    recurring_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rec = db.query(RecurringTransaction).filter(
        RecurringTransaction.id == recurring_id,
        RecurringTransaction.user_id == current_user.id
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recurring transaction config not found.")
    db.delete(rec)
    db.commit()
    return {"ok": True}


# =========================================================
# NOTES API (CRUD)
# =========================================================
def serialize_note(note: Note) -> dict:
    return {
        "id": note.id,
        "title": note.title,
        "content_html": note.content_html,
        "color": note.color,
        "pinned": bool(note.pinned),
        "updated_at": note.updated_at
    }


@app.get("/api/notes")
def get_notes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notes = (
        db.query(Note)
        .filter(Note.user_id == current_user.id)
        .order_by(Note.pinned.desc(), Note.id.desc())
        .all()
    )
    return [serialize_note(n) for n in notes]


@app.post("/api/notes")
async def create_note(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    title = str(payload.get("title", "")).strip()
    content_html = str(payload.get("content_html", "")).strip()
    color = str(payload.get("color", "pink")).strip()
    pinned = 1 if payload.get("pinned") else 0
    updated_at = str(payload.get("updated_at") or get_vietnam_time().strftime("%d/%m/%Y")).strip()

    if not title or not content_html:
        raise HTTPException(status_code=400, detail="Title and content are required.")

    note = Note(
        user_id=current_user.id,
        title=title,
        content_html=content_html,
        color=color,
        pinned=pinned,
        updated_at=updated_at
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return serialize_note(note)


@app.put("/api/notes/{note_id}")
async def update_note(
    note_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    note = db.query(Note).filter(Note.id == note_id, Note.user_id == current_user.id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found.")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    if "title" in payload:
        note.title = str(payload["title"]).strip()
    if "content_html" in payload:
        note.content_html = str(payload["content_html"]).strip()
    if "color" in payload:
        note.color = str(payload["color"]).strip()
    if "pinned" in payload:
        note.pinned = 1 if payload["pinned"] else 0
    if "updated_at" in payload:
        note.updated_at = str(payload["updated_at"]).strip()
    else:
        note.updated_at = get_vietnam_time().strftime("%d/%m/%Y")

    db.commit()
    db.refresh(note)
    return serialize_note(note)


@app.delete("/api/notes/{note_id}")
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    note = db.query(Note).filter(Note.id == note_id, Note.user_id == current_user.id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found.")
    db.delete(note)
    db.commit()
    return {"ok": True}


# =========================================================
# DAY COUNTER API (CRUD)
# =========================================================
def serialize_counter(counter: DayCounter) -> dict:
    return {
        "id": counter.id,
        "title": counter.title,
        "target_date": counter.target_date,
        "mode": counter.mode
    }


@app.get("/api/counters")
def get_counters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    today_str = get_vietnam_time().strftime("%Y-%m-%d")
    
    expired_counters = (
        db.query(DayCounter)
        .filter(DayCounter.user_id == current_user.id, DayCounter.target_date < today_str)
        .all()
    )
    deleted_items = []
    if expired_counters:
        for c in expired_counters:
            deleted_items.append({
                "id": c.id,
                "title": c.title,
                "target_date": c.target_date,
                "mode": c.mode
            })
            db.delete(c)
        db.commit()

    counters = (
        db.query(DayCounter)
        .filter(DayCounter.user_id == current_user.id)
        .order_by(DayCounter.id.desc())
        .all()
    )
    return {
        "counters": [serialize_counter(c) for c in counters],
        "deleted_expired": deleted_items
    }


@app.post("/api/counters")
async def create_counter(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    title = str(payload.get("title", "")).strip()
    target_date = str(payload.get("target_date", "")).strip()
    mode = str(payload.get("mode", "workday")).strip()

    if not title or not target_date:
        raise HTTPException(status_code=400, detail="Title and target date are required.")

    today_str = get_vietnam_time().strftime("%Y-%m-%d")
    if target_date < today_str:
        raise HTTPException(status_code=400, detail="Không thể chọn ngày trong quá khứ.")

    counter = DayCounter(
        user_id=current_user.id,
        title=title,
        target_date=target_date,
        mode=mode
    )
    db.add(counter)
    db.commit()
    db.refresh(counter)
    return serialize_counter(counter)


@app.put("/api/counters/{counter_id}")
async def update_counter(
    counter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    counter = db.query(DayCounter).filter(
        DayCounter.id == counter_id,
        DayCounter.user_id == current_user.id
    ).first()
    if not counter:
        raise HTTPException(status_code=404, detail="Day counter not found.")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    if "title" in payload:
        counter.title = str(payload["title"]).strip()
    if "target_date" in payload:
        new_date = str(payload["target_date"]).strip()
        today_str = get_vietnam_time().strftime("%Y-%m-%d")
        if new_date < today_str:
            raise HTTPException(status_code=400, detail="Không thể chọn ngày trong quá khứ.")
        counter.target_date = new_date
    if "mode" in payload:
        counter.mode = str(payload["mode"]).strip()

    db.commit()
    db.refresh(counter)
    return serialize_counter(counter)


@app.delete("/api/counters/{counter_id}")
def delete_counter(
    counter_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    counter = db.query(DayCounter).filter(
        DayCounter.id == counter_id,
        DayCounter.user_id == current_user.id
    ).first()
    if not counter:
        raise HTTPException(status_code=404, detail="Day counter not found.")
    db.delete(counter)
    db.commit()
    return {"ok": True}