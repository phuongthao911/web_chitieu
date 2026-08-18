from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
# pyrefly: ignore [missing-import]
from sqlalchemy import text
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from database import engine, get_db, reset_expenses_table_if_needed
from models import Base, Expense, Category, Budget, RecurringTransaction, get_vietnam_time


BASE_DIR = Path(__file__).resolve().parent

ALLOWED_WALLETS = {"Tiền mặt", "Tài khoản tiết kiệm", "TK ngân hàng"}

app = FastAPI()

reset_expenses_table_if_needed()
Base.metadata.create_all(bind=engine)

# Seed default categories if empty
def seed_default_categories():
    db = Session(bind=engine)
    try:
        if db.query(Category).count() == 0:
            default_categories = [
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
            for cat in default_categories:
                existing = db.query(Category).filter(Category.name == cat["name"]).first()
                if not existing:
                    db.add(Category(name=cat["name"], type=cat["type"]))
            db.commit()
    except Exception as e:
        print("Error seeding categories:", e)
        db.rollback()
    finally:
        db.close()

seed_default_categories()

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


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


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={},
    )


@app.get("/api/backup/json")
def backup_json(db: Session = Depends(get_db)):
    expenses = (
        db.query(Expense)
        .order_by(Expense.created_at.desc(), Expense.id.desc())
        .all()
    )
    categories = db.query(Category).all()
    budgets = db.query(Budget).all()
    recurring = db.query(RecurringTransaction).all()

    data = {
        "version": "2.0",
        "exported_at": get_vietnam_time().strftime("%Y-%m-%d %H:%M:%S"),
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
        ]
    }
    filename = f"expense_backup_full_{get_vietnam_time().strftime('%Y%m%d_%H%M%S')}.json"
    from fastapi.responses import JSONResponse
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return JSONResponse(content=data, headers=headers)


@app.get("/api/backup/csv")
def backup_csv(db: Session = Depends(get_db)):
    expenses = (
        db.query(Expense)
        .order_by(Expense.created_at.desc(), Expense.id.desc())
        .all()
    )
    categories = db.query(Category).all()
    budgets = db.query(Budget).all()
    recurring = db.query(RecurringTransaction).all()
    
    import csv
    import io
    from fastapi.responses import Response
    
    output = io.StringIO()
    # Write BOM for UTF-8 compatibility with Excel
    output.write('\ufeff')
    writer = csv.writer(output)
    
    # Section 1: Transactions
    writer.writerow(["=== GIAO DỊCH (TRANSACTIONS) ==="])
    writer.writerow(["ID", "Loại giao dịch", "Danh mục", "Ví nguồn", "Ví đích", "Số tiền (VND)", "Ghi chú", "Ngày tạo"])
    for expense in expenses:
        writer.writerow([
            expense.id,
            "Thu nhập" if expense.transaction_type == "Income" else ("Chi tiêu" if expense.transaction_type == "Expense" else "Chuyển ví"),
            expense.category,
            expense.wallet,
            expense.destination_wallet or "",
            expense.amount,
            expense.note,
            expense.created_at.strftime("%Y-%m-%d %H:%M") if expense.created_at else ""
        ])
    writer.writerow([])

    # Section 2: Categories
    writer.writerow(["=== DANH MỤC (CATEGORIES) ==="])
    writer.writerow(["ID", "Tên danh mục", "Loại danh mục"])
    for cat in categories:
        writer.writerow([cat.id, cat.name, "Thu nhập" if cat.type == "income" else "Chi tiêu"])
    writer.writerow([])

    # Section 3: Budgets
    writer.writerow(["=== NGÂN SÁCH (BUDGETS) ==="])
    writer.writerow(["ID", "Tên danh mục", "Hạn mức (VND)", "Tháng"])
    for b in budgets:
        writer.writerow([b.id, b.category_name, b.amount_limit, b.month])
    writer.writerow([])

    # Section 4: Recurring Transactions
    writer.writerow(["=== GIAO DỊCH ĐỊNH KỲ (RECURRING TRANSACTIONS) ==="])
    writer.writerow(["ID", "Loại giao dịch", "Số tiền (VND)", "Danh mục", "Ví nguồn", "Ví đích", "Ngày tự động (1-31)", "Tháng chạy gần nhất", "Ghi chú"])
    for r in recurring:
        writer.writerow([
            r.id,
            r.transaction_type,
            r.amount,
            r.category,
            r.wallet,
            r.destination_wallet or "",
            r.day_of_month,
            r.last_executed_month or "Chưa chạy",
            r.note
        ])

    filename = f"expense_backup_full_{get_vietnam_time().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return Response(content=output.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)


@app.post("/api/backup/import")
async def import_backup(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON format.")
    
    # Support both full structured JSON dict and legacy transaction array
    if isinstance(body, list):
        tx_list = body
        cat_list = []
        budget_list = []
        recurring_list = []
    elif isinstance(body, dict):
        tx_list = body.get("transactions", [])
        cat_list = body.get("categories", [])
        budget_list = body.get("budgets", [])
        recurring_list = body.get("recurring", [])
    else:
        raise HTTPException(status_code=400, detail="Invalid backup payload structure.")
    
    imported_tx = 0
    imported_cats = 0
    imported_budgets = 0
    imported_recurring = 0

    # 1. Import Categories
    for item in cat_list:
        c_name = str(item.get("name", "")).strip()
        c_type = str(item.get("type", "")).strip().lower()
        if c_name and c_type in {"income", "expense"}:
            existing = db.query(Category).filter(Category.name == c_name).first()
            if not existing:
                db.add(Category(name=c_name, type=c_type))
                imported_cats += 1

    # 2. Import Budgets
    for item in budget_list:
        cat_name = str(item.get("category_name", "")).strip()
        month = str(item.get("month", "")).strip()
        try:
            limit = float(item.get("amount_limit", 0))
        except (TypeError, ValueError):
            continue
        if cat_name and month and limit >= 0:
            existing = db.query(Budget).filter(Budget.category_name == cat_name, Budget.month == month).first()
            if existing:
                existing.amount_limit = limit
            else:
                db.add(Budget(category_name=cat_name, month=month, amount_limit=limit))
            imported_budgets += 1

    # 3. Import Recurring Transactions
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
        if r_amount > 0 and 1 <= r_day <= 31 and r_wallet in ALLOWED_WALLETS:
            rec = RecurringTransaction(
                transaction_type=r_type if r_type in {"Income", "Expense", "Transfer"} else "Expense",
                amount=r_amount,
                category=r_cat or "Other",
                wallet=r_wallet,
                destination_wallet=r_dest,
                note=r_note or "-",
                day_of_month=r_day,
                last_executed_month=item.get("last_executed_month")
            )
            db.add(rec)
            imported_recurring += 1

    # 4. Import Transactions
    for item in tx_list:
        transaction_type = str(item.get("type", "")).strip()
        category = str(item.get("category", "")).strip()
        wallet = str(item.get("wallet", "")).strip()
        destination_wallet = str(item.get("destination_wallet", "")).strip() if item.get("destination_wallet") else None
        note = str(item.get("note", "")).strip()
        
        try:
            amount = float(item.get("amount", 0))
        except (TypeError, ValueError):
            continue
            
        if amount <= 0 or wallet not in ALLOWED_WALLETS:
            continue
            
        # Parse or default created_at
        created_at_str = item.get("created_at")
        try:
            if created_at_str:
                created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M")
            else:
                created_at = get_vietnam_time()
        except Exception:
            created_at = get_vietnam_time()

        # Build Expense object
        expense = Expense(
            transaction_type=transaction_type,
            category=category or ("Chuyển ví" if transaction_type == "Transfer" else "Other"),
            wallet=wallet,
            destination_wallet=destination_wallet,
            amount=amount,
            note=note or "-",
            created_at=created_at
        )
        db.add(expense)
        imported_tx += 1
        
    db.commit()
    
    summary_parts = []
    if imported_tx: summary_parts.append(f"{imported_tx} giao dịch")
    if imported_cats: summary_parts.append(f"{imported_cats} danh mục mới")
    if imported_budgets: summary_parts.append(f"{imported_budgets} ngân sách")
    if imported_recurring: summary_parts.append(f"{imported_recurring} giao dịch định kỳ")
    
    msg = "Đã nhập thành công: " + (", ".join(summary_parts) if summary_parts else "0 mục") + "."
    return {"status": "ok", "message": msg}


@app.post("/api/backup/import-csv")
async def import_csv_backup(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Vui lòng chọn file định dạng .csv")
    
    contents = (await file.read()).decode("utf-8-sig", errors="ignore")
    lines = [line.strip() for line in contents.splitlines() if line.strip()]
    
    import csv
    reader = csv.reader(lines)
    
    imported_tx = 0
    imported_cats = 0
    imported_budgets = 0
    imported_recurring = 0

    current_section = "transactions"
    header = None

    for row in reader:
        if not row or not any(row):
            continue
        
        first_cell = row[0].strip()

        # Detect Section Markers
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

        # If header not set for current block, set header
        if header is None:
            header = [c.strip().lower() for c in row]
            continue
        
        # Parse data row based on current_section
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

            if wallet not in ALLOWED_WALLETS:
                wallet = "Tiền mặt"
            if dest_wallet and dest_wallet not in ALLOWED_WALLETS:
                dest_wallet = None

            try:
                if date_raw:
                    created_at = datetime.strptime(date_raw, "%Y-%m-%d %H:%M")
                else:
                    created_at = get_vietnam_time()
            except Exception:
                created_at = get_vietnam_time()

            expense = Expense(
                transaction_type=t_type,
                category=category,
                wallet=wallet,
                destination_wallet=dest_wallet if t_type == "Transfer" else None,
                amount=clean_amount,
                note=note or "-",
                created_at=created_at
            )
            db.add(expense)
            imported_tx += 1

        elif current_section == "categories":
            data = dict(zip(header, [c.strip() for c in row]))
            c_name = data.get("tên danh mục") or data.get("name") or ""
            c_type_raw = data.get("loại danh mục") or data.get("type") or ""
            c_type = "income" if "thu" in c_type_raw.lower() or c_type_raw.lower() == "income" else "expense"
            if c_name:
                existing = db.query(Category).filter(Category.name == c_name).first()
                if not existing:
                    db.add(Category(name=c_name, type=c_type))
                    imported_cats += 1

        elif current_section == "budgets":
            data = dict(zip(header, [c.strip() for c in row]))
            c_name = data.get("tên danh mục") or data.get("danh mục") or data.get("category_name") or ""
            month = data.get("tháng") or data.get("month") or ""
            amount_raw = data.get("hạn mức (vnd)") or data.get("hạn mức") or data.get("amount_limit") or "0"
            try:
                limit = float(str(amount_raw).replace(",", "").replace("VND", "").strip())
            except (ValueError, TypeError):
                continue
            if c_name and month and limit >= 0:
                existing = db.query(Budget).filter(Budget.category_name == c_name, Budget.month == month).first()
                if existing:
                    existing.amount_limit = limit
                else:
                    db.add(Budget(category_name=c_name, month=month, amount_limit=limit))
                imported_budgets += 1

        elif current_section == "recurring":
            data = dict(zip(header, [c.strip() for c in row]))
            r_type_raw = data.get("loại giao dịch") or data.get("loại") or data.get("type") or "Expense"
            if "thu" in r_type_raw.lower() or r_type_raw.lower() == "income":
                r_type = "Income"
            elif "chuyển" in r_type_raw.lower() or r_type_raw.lower() == "transfer":
                r_type = "Transfer"
            else:
                r_type = "Expense"
            
            amount_raw = data.get("số tiền (vnd)") or data.get("số tiền") or data.get("amount") or "0"
            r_cat = data.get("danh mục") or data.get("category") or "Other"
            r_wallet = data.get("ví nguồn") or data.get("ví") or data.get("wallet") or "Tiền mặt"
            r_dest = data.get("ví đích") or data.get("destination_wallet") or None
            day_raw = data.get("ngày tự động (1-31)") or data.get("ngày tự động") or data.get("day_of_month") or "1"
            last_exec = data.get("tháng chạy gần nhất") or data.get("last_executed_month") or None
            if last_exec == "Chưa chạy":
                last_exec = None
            r_note = data.get("ghi chú") or data.get("note") or "-"

            try:
                r_amount = float(str(amount_raw).replace(",", "").replace("VND", "").strip())
                r_day = int(day_raw)
            except (ValueError, TypeError):
                continue

            if r_amount > 0 and 1 <= r_day <= 31:
                rec = RecurringTransaction(
                    transaction_type=r_type,
                    amount=r_amount,
                    category=r_cat,
                    wallet=r_wallet if r_wallet in ALLOWED_WALLETS else "Tiền mặt",
                    destination_wallet=r_dest if (r_dest and r_dest in ALLOWED_WALLETS) else None,
                    note=r_note,
                    day_of_month=r_day,
                    last_executed_month=last_exec
                )
                db.add(rec)
                imported_recurring += 1

    db.commit()

    summary_parts = []
    if imported_tx: summary_parts.append(f"{imported_tx} giao dịch")
    if imported_cats: summary_parts.append(f"{imported_cats} danh mục mới")
    if imported_budgets: summary_parts.append(f"{imported_budgets} ngân sách")
    if imported_recurring: summary_parts.append(f"{imported_recurring} giao dịch định kỳ")

    msg = "Đã nhập CSV thành công: " + (", ".join(summary_parts) if summary_parts else "0 mục") + "."
    return {"status": "ok", "message": msg}


@app.get("/api/transactions")
def list_transactions(db: Session = Depends(get_db)):
    expenses = (
        db.query(Expense)
        .order_by(Expense.created_at.desc(), Expense.id.desc())
        .all()
    )
    return [serialize_expense(expense) for expense in expenses]


@app.post("/api/transactions")
def create_transaction(payload: dict, db: Session = Depends(get_db)):
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
def update_transaction(expense_id: int, payload: dict, db: Session = Depends(get_db)):
    expense = db.query(Expense).filter(Expense.id == expense_id).first()

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
def delete_transaction(expense_id: int, db: Session = Depends(get_db)):
    expense = db.query(Expense).filter(Expense.id == expense_id).first()

    if expense is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    db.delete(expense)
    db.commit()

    return {"ok": True}


@app.get("/api/categories")
def list_categories(db: Session = Depends(get_db)):
    categories = db.query(Category).all()
    return [{"id": cat.id, "name": cat.name, "type": cat.type} for cat in categories]


@app.post("/api/categories")
def create_category(payload: dict, db: Session = Depends(get_db)):
    name = str(payload.get("name", "")).strip()
    cat_type = str(payload.get("type", "")).strip().lower()

    if not name:
        raise HTTPException(status_code=400, detail="Category name is required.")
    if cat_type not in {"income", "expense"}:
        raise HTTPException(status_code=400, detail="Category type must be income or expense.")

    # Check if category already exists
    existing = db.query(Category).filter(Category.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category already exists.")

    new_cat = Category(name=name, type=cat_type)
    db.add(new_cat)
    db.commit()
    db.refresh(new_cat)
    return {"id": new_cat.id, "name": new_cat.name, "type": new_cat.type}


@app.put("/api/categories/{category_id}")
def update_category(category_id: int, payload: dict, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found.")

    name = str(payload.get("name", "")).strip()
    cat_type = str(payload.get("type", "")).strip().lower()

    if not name:
        raise HTTPException(status_code=400, detail="Category name is required.")
    if cat_type not in {"income", "expense"}:
        raise HTTPException(status_code=400, detail="Category type must be income or expense.")

    # Check unique constraint if name changed
    if name != cat.name:
        existing = db.query(Category).filter(Category.name == name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Category name already exists.")

    cat.name = name
    cat.type = cat_type
    db.commit()
    db.refresh(cat)
    return {"id": cat.id, "name": cat.name, "type": cat.type}


@app.delete("/api/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found.")

    db.delete(cat)
    db.commit()
    return {"ok": True}


@app.get("/api/budgets")
def get_budgets(month: str, db: Session = Depends(get_db)):
    # Validate format YYYY-MM
    if len(month) != 7 or month[4] != "-":
        raise HTTPException(status_code=400, detail="Invalid month format. Expected YYYY-MM.")

    # Get all expense categories
    categories = db.query(Category).filter(Category.type == "expense").all()

    # Get budgets set for this month
    budgets = db.query(Budget).filter(Budget.month == month).all()
    budget_map = {b.category_name: b for b in budgets}

    # Calculate actual spending for each category in this month
    # Note: SQLite and Postgres have different date functions, but we can filter using string start
    # e.g., created_at starts with the 'month' string.
    # To be fully DB-agnostic, we can query transactions of this month and sum in Python,
    # since data volume is usually small, or filter date ranges.
    # Let's filter expenses in Python or simple like query:
    start_date = f"{month}-01 00:00:00"
    # We will find all expenses created in this month
    expenses = db.query(Expense).filter(
        Expense.transaction_type == "Expense"
    ).all()

    # Filter in memory to ensure complete database compatibility (Postgres/SQLite)
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
def save_budget(payload: dict, db: Session = Depends(get_db)):
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

    # Check if budget already exists for this category/month
    b = db.query(Budget).filter(Budget.category_name == category_name, Budget.month == month).first()
    if b:
        b.amount_limit = amount_limit
    else:
        b = Budget(category_name=category_name, month=month, amount_limit=amount_limit)
        db.add(b)

    db.commit()
    db.refresh(b)
    return {"category_name": b.category_name, "month": b.month, "amount_limit": b.amount_limit}


@app.get("/api/recurring")
def list_recurring(db: Session = Depends(get_db)):
    items = db.query(RecurringTransaction).all()
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
def create_recurring(payload: dict, db: Session = Depends(get_db)):
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
    
    # Run dynamic checker immediately to catch up if created on/after execution day in current month
    run_recurring_scheduler_on_db(db)
    
    return {"id": rec.id, "type": rec.transaction_type, "amount": rec.amount}


@app.delete("/api/recurring/{recurring_id}")
def delete_recurring(recurring_id: int, db: Session = Depends(get_db)):
    rec = db.query(RecurringTransaction).filter(RecurringTransaction.id == recurring_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recurring transaction config not found.")
    db.delete(rec)
    db.commit()
    return {"ok": True}


def run_recurring_scheduler_on_db(db: Session):
    """Safely processes and executes recurring transactions.
    
    Idempotency: Compares last_executed_month to ensure only 1 run per month.
    """
    now_vn = get_vietnam_time()
    current_month_str = now_vn.strftime("%Y-%m")
    current_day = now_vn.day

    configs = db.query(RecurringTransaction).all()
    for rec in configs:
        # Check if executed this month already
        if rec.last_executed_month == current_month_str:
            continue
        
        # Check if the day of execution has arrived or passed in the current month
        if current_day >= rec.day_of_month:
            # Execute transaction!
            try:
                # We construct the timestamp representing scheduled run date in current month
                execution_time = now_vn.replace(day=rec.day_of_month, hour=9, minute=0, second=0, microsecond=0)
                
                exp = Expense(
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


# Check and run recurring tasks on startup event
@app.on_event("startup")
def startup_event():
    db = Session(bind=engine)
    try:
        run_recurring_scheduler_on_db(db)
    except Exception as e:
        print("Error executing startup recurring tasks:", e)
    finally:
        db.close()