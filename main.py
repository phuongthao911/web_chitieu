from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import engine, get_db, reset_expenses_table_if_needed
from models import Base, Expense


BASE_DIR = Path(__file__).resolve().parent

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
        "amount": expense.amount,
        "note": expense.note,
        "created_at": expense.created_at.strftime("%Y-%m-%d %H:%M") if expense.created_at else None,
    }


@app.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={},
    )


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
    note = str(payload.get("note", "")).strip()

    try:
        amount = float(payload.get("amount"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Amount must be a number.")

    if transaction_type not in {"income", "expense"}:
        raise HTTPException(status_code=400, detail="Type must be income or expense.")

    if not category:
        raise HTTPException(status_code=400, detail="Category is required.")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")

    expense = Expense(
        transaction_type="Income" if transaction_type == "income" else "Expense",
        category=category,
        amount=amount,
        note=note or "-",
        created_at=datetime.now(),
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
    note = str(payload.get("note", "")).strip()

    try:
        amount = float(payload.get("amount"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Amount must be a number.")

    if transaction_type not in {"income", "expense"}:
        raise HTTPException(status_code=400, detail="Type must be income or expense.")

    if not category:
        raise HTTPException(status_code=400, detail="Category is required.")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")

    expense.transaction_type = "Income" if transaction_type == "income" else "Expense"
    expense.category = category
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