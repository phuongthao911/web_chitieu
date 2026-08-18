from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
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
                {"name": "Chi phí phát sinh", "type": "income"},
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
                {"name": "Other", "type": "expense"},
            ]
            for cat in default_categories:
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
    data = [serialize_expense(expense) for expense in expenses]
    filename = f"expense_backup_{get_vietnam_time().strftime('%Y%m%d_%H%M%S')}.json"
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
    
    import csv
    import io
    from fastapi.responses import Response
    
    output = io.StringIO()
    # Write BOM for UTF-8 compatibility with Excel
    output.write('\ufeff')
    writer = csv.writer(output)
    
    # Header row matching the fields
    writer.writerow(["ID", "Loại giao dịch", "Danh mục", "Ví", "Số tiền (VND)", "Ghi chú", "Ngày tạo"])
    
    for expense in expenses:
        writer.writerow([
            expense.id,
            "Thu nhập" if expense.transaction_type == "Income" else "Chi tiêu",
            expense.category,
            expense.wallet,
            expense.amount,
            expense.note,
            expense.created_at.strftime("%Y-%m-%d %H:%M") if expense.created_at else ""
        ])
    
    filename = f"expense_backup_{get_vietnam_time().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return Response(content=output.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)


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