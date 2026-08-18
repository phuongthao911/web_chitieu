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
from models import Base, Expense, get_vietnam_time


BASE_DIR = Path(__file__).resolve().parent

ALLOWED_WALLETS = {"Tiền mặt", "Tài khoản tiết kiệm", "TK ngân hàng"}

app = FastAPI()

reset_expenses_table_if_needed()
Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def serialize_expense(expense: Expense) -> dict:
    return {
        "id": expense.id,
        "type": expense.transaction_type,
        "category": expense.category,
        "wallet": expense.wallet,
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
    note = str(payload.get("note", "")).strip()

    try:
        amount = float(payload.get("amount"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Amount must be a number.")

    if transaction_type not in {"income", "expense"}:
        raise HTTPException(status_code=400, detail="Type must be income or expense.")

    if not category:
        raise HTTPException(status_code=400, detail="Category is required.")

    if wallet not in ALLOWED_WALLETS:
        raise HTTPException(status_code=400, detail="Wallet is required.")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")

    expense = Expense(
        transaction_type="Income" if transaction_type == "income" else "Expense",
        category=category,
        wallet=wallet,
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
    note = str(payload.get("note", "")).strip()

    try:
        amount = float(payload.get("amount"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Amount must be a number.")

    if transaction_type not in {"income", "expense"}:
        raise HTTPException(status_code=400, detail="Type must be income or expense.")

    if not category:
        raise HTTPException(status_code=400, detail="Category is required.")

    if wallet not in ALLOWED_WALLETS:
        raise HTTPException(status_code=400, detail="Wallet is required.")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")

    expense.transaction_type = "Income" if transaction_type == "income" else "Expense"
    expense.category = category
    expense.wallet = wallet
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