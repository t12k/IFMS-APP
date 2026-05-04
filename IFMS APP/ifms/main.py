from datetime import datetime, timedelta
from typing import List
from collections import defaultdict
import os

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import models, schemas
from .database import engine
from .auth import (hash_password, verify_password, create_access_token,
                   get_current_user, get_db, log_activity, generate_mfa_code)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="IFMS", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def ip(r: Request): return r.client.host if r.client else "unknown"


# ── Serve Frontend ─────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def frontend():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "index.html"), encoding="utf-8") as f:
        return f.read()


# ── Register ───────────────────────────────────────────────────────────────────
@app.post("/register", response_model=schemas.Token, status_code=201)
def register(user: schemas.UserCreate, r: Request, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(400, "Email already registered")
    u = models.User(email=user.email, username=user.username,
                    hashed_password=hash_password(user.password))
    db.add(u); db.commit(); db.refresh(u)
    log_activity(db, u.id, "REGISTER", f"Account created: {user.email}", ip(r))
    return {"access_token": create_access_token({"sub": u.id}), "token_type": "bearer", "user": u}


# ── Login ──────────────────────────────────────────────────────────────────────
@app.post("/login")
def login(c: schemas.UserLogin, r: Request, db: Session = Depends(get_db)):
    u = db.query(models.User).filter(models.User.email == c.email).first()
    if not u or not verify_password(c.password, u.hashed_password):
        if u: log_activity(db, u.id, "LOGIN_FAILED", "Wrong password", ip(r))
        raise HTTPException(401, "Invalid email or password")
    if u.mfa_enabled:
        code = generate_mfa_code()
        u.mfa_code = code
        u.mfa_code_expiry = datetime.utcnow() + timedelta(minutes=10)
        db.commit()
        log_activity(db, u.id, "MFA_SENT", f"MFA code: {code}", ip(r))
        return {"mfa_required": True, "email": u.email, "message": f"Your MFA code is: {code}"}
    log_activity(db, u.id, "LOGIN", "Successful login", ip(r))
    return {"access_token": create_access_token({"sub": u.id}), "token_type": "bearer", "user": u}


# ── MFA Verify ─────────────────────────────────────────────────────────────────
@app.post("/mfa/verify", response_model=schemas.Token)
def mfa_verify(data: schemas.MFAVerify, r: Request, db: Session = Depends(get_db)):
    u = db.query(models.User).filter(models.User.email == data.email).first()
    if not u: raise HTTPException(404, "User not found")
    if not u.mfa_code or u.mfa_code != data.code:
        raise HTTPException(401, "Invalid MFA code")
    if u.mfa_code_expiry and datetime.utcnow() > u.mfa_code_expiry:
        raise HTTPException(401, "MFA code expired")
    u.mfa_code = None; u.mfa_code_expiry = None; db.commit()
    log_activity(db, u.id, "MFA_VERIFIED", "MFA login successful", ip(r))
    return {"access_token": create_access_token({"sub": u.id}), "token_type": "bearer", "user": u}


# ── MFA Toggle ─────────────────────────────────────────────────────────────────
@app.post("/mfa/toggle")
def mfa_toggle(r: Request, db: Session = Depends(get_db),
               cu: models.User = Depends(get_current_user)):
    cu.mfa_enabled = not cu.mfa_enabled; db.commit()
    s = "enabled" if cu.mfa_enabled else "disabled"
    log_activity(db, cu.id, "MFA_TOGGLE", f"MFA {s}", ip(r))
    return {"mfa_enabled": cu.mfa_enabled, "message": f"MFA {s}"}


# ── Profile ────────────────────────────────────────────────────────────────────
@app.get("/me", response_model=schemas.UserOut)
def get_me(cu: models.User = Depends(get_current_user)): return cu

@app.put("/me", response_model=schemas.UserOut)
def update_me(data: schemas.UserUpdate, r: Request,
              db: Session = Depends(get_db), cu: models.User = Depends(get_current_user)):
    if data.username: cu.username = data.username
    if data.salary is not None: cu.salary = data.salary
    db.commit(); db.refresh(cu)
    log_activity(db, cu.id, "PROFILE_UPDATE", "Profile updated", ip(r))
    return cu


# ── Transactions ───────────────────────────────────────────────────────────────
@app.post("/transactions", response_model=schemas.TransactionOut, status_code=201)
def create_tx(tx: schemas.TransactionCreate, r: Request,
              db: Session = Depends(get_db), cu: models.User = Depends(get_current_user)):
    if tx.type not in ("income", "expense", "saving"):
        raise HTTPException(400, "type must be income, expense, or saving")
    if tx.amount <= 0: raise HTTPException(400, "amount must be positive")
    t = models.Transaction(amount=tx.amount, type=tx.type, category=tx.category,
                           description=tx.description or "", date=tx.date or datetime.utcnow(),
                           user_id=cu.id)
    db.add(t); db.commit(); db.refresh(t)
    log_activity(db, cu.id, "TX_ADD", f"{tx.type.upper()} ZMW{tx.amount} – {tx.category}", ip(r))
    return t

@app.get("/transactions", response_model=List[schemas.TransactionOut])
def list_tx(db: Session = Depends(get_db), cu: models.User = Depends(get_current_user)):
    return db.query(models.Transaction).filter(models.Transaction.user_id == cu.id)\
             .order_by(models.Transaction.date.desc()).all()

@app.put("/transactions/{tid}", response_model=schemas.TransactionOut)
def update_tx(tid: int, data: schemas.TransactionUpdate, r: Request,
              db: Session = Depends(get_db), cu: models.User = Depends(get_current_user)):
    t = db.query(models.Transaction).filter(models.Transaction.id == tid,
                                             models.Transaction.user_id == cu.id).first()
    if not t: raise HTTPException(404, "Transaction not found")
    if data.amount is not None: t.amount = data.amount
    if data.category is not None: t.category = data.category
    if data.description is not None: t.description = data.description
    db.commit(); db.refresh(t)
    log_activity(db, cu.id, "TX_EDIT", f"Edited transaction {tid}", ip(r))
    return t

@app.delete("/transactions/{tid}", status_code=204)
def delete_tx(tid: int, r: Request, db: Session = Depends(get_db),
              cu: models.User = Depends(get_current_user)):
    t = db.query(models.Transaction).filter(models.Transaction.id == tid,
                                             models.Transaction.user_id == cu.id).first()
    if not t: raise HTTPException(404, "Transaction not found")
    db.delete(t); db.commit()
    log_activity(db, cu.id, "TX_DELETE", f"Deleted transaction {tid}", ip(r))


# ── Goals ──────────────────────────────────────────────────────────────────────
@app.post("/goals", response_model=schemas.GoalOut, status_code=201)
def create_goal(g: schemas.GoalCreate, db: Session = Depends(get_db),
                cu: models.User = Depends(get_current_user)):
    goal = models.FinancialGoal(name=g.name, target=g.target, saved=g.saved or 0,
                                deadline=g.deadline, user_id=cu.id)
    db.add(goal); db.commit(); db.refresh(goal); return goal

@app.get("/goals", response_model=List[schemas.GoalOut])
def list_goals(db: Session = Depends(get_db), cu: models.User = Depends(get_current_user)):
    return db.query(models.FinancialGoal).filter(models.FinancialGoal.user_id == cu.id).all()

@app.put("/goals/{gid}", response_model=schemas.GoalOut)
def update_goal(gid: int, data: schemas.GoalUpdate,
                db: Session = Depends(get_db), cu: models.User = Depends(get_current_user)):
    g = db.query(models.FinancialGoal).filter(models.FinancialGoal.id == gid,
                                               models.FinancialGoal.user_id == cu.id).first()
    if not g: raise HTTPException(404, "Goal not found")
    if data.name is not None: g.name = data.name
    if data.target is not None: g.target = data.target
    if data.saved is not None: g.saved = data.saved
    db.commit(); db.refresh(g); return g

@app.delete("/goals/{gid}", status_code=204)
def delete_goal(gid: int, db: Session = Depends(get_db),
                cu: models.User = Depends(get_current_user)):
    g = db.query(models.FinancialGoal).filter(models.FinancialGoal.id == gid,
                                               models.FinancialGoal.user_id == cu.id).first()
    if not g: raise HTTPException(404, "Goal not found")
    db.delete(g); db.commit()


# ── Summary ────────────────────────────────────────────────────────────────────
@app.get("/summary", response_model=schemas.Summary)
def summary(db: Session = Depends(get_db), cu: models.User = Depends(get_current_user)):
    txs = db.query(models.Transaction).filter(models.Transaction.user_id == cu.id).all()
    inc = sum(t.amount for t in txs if t.type == "income")
    exp = sum(t.amount for t in txs if t.type == "expense")
    sav = sum(t.amount for t in txs if t.type == "saving")
    sal = cu.salary or 0
    return {"total_income": inc, "total_expenses": exp, "total_savings": sav,
            "balance": inc - exp - sav, "transaction_count": len(txs),
            "salary": sal, "budget_used_pct": round(exp / sal * 100, 1) if sal else 0}


# ── Analytics ──────────────────────────────────────────────────────────────────
@app.get("/analytics/monthly", response_model=List[schemas.MonthSummary])
def monthly(db: Session = Depends(get_db), cu: models.User = Depends(get_current_user)):
    txs = db.query(models.Transaction).filter(models.Transaction.user_id == cu.id).all()
    m = defaultdict(lambda: {"income": 0.0, "expenses": 0.0, "savings": 0.0})
    for t in txs:
        k = t.date.strftime("%Y-%m")
        if t.type == "income": m[k]["income"] += t.amount
        elif t.type == "expense": m[k]["expenses"] += t.amount
        elif t.type == "saving": m[k]["savings"] += t.amount
    return [{"month": k, "income": v["income"], "expenses": v["expenses"],
             "savings": v["savings"], "balance": v["income"]-v["expenses"]-v["savings"]}
            for k, v in sorted(m.items())]


# ── AI Prediction & Advice ─────────────────────────────────────────────────────
@app.get("/analytics/predict", response_model=schemas.Prediction)
def predict(db: Session = Depends(get_db), cu: models.User = Depends(get_current_user)):
    txs = db.query(models.Transaction).filter(models.Transaction.user_id == cu.id).all()
    me = defaultdict(float)
    cats = defaultdict(float)
    for t in txs:
        if t.type == "expense":
            me[t.date.strftime("%Y-%m")] += t.amount
            cats[t.category] += t.amount
    vals = [me[k] for k in sorted(me)]
    avg = sum(vals) / len(vals) if vals else 0
    if len(vals) >= 3: pred = vals[-1]*.5 + vals[-2]*.3 + vals[-3]*.2
    elif len(vals) == 2: pred = vals[-1]*.6 + vals[-2]*.4
    elif len(vals) == 1: pred = vals[0]
    else: pred = 0
    if len(vals) >= 2:
        r = sum(vals[-2:])/2; o = sum(vals[:-2])/max(len(vals)-2,1)
        trend = "increasing" if r>o*1.1 else "decreasing" if r<o*.9 else "stable"
    else: trend = "insufficient data"
    advice = []
    top = sorted(cats.items(), key=lambda x: x[1], reverse=True)
    if top: advice.append(f"Your highest spending is '{top[0][0]}' at ZMW {top[0][1]:,.2f}. Try reducing it by 15-20%.")
    sal = cu.salary or 0
    if sal and avg:
        p = avg/sal*100
        if p > 80: advice.append(f"You spend {p:.0f}% of salary on expenses — aim below 50%.")
        elif p > 50: advice.append(f"You spend {p:.0f}% of salary. Try to save at least 20% monthly.")
        else: advice.append(f"Well done! You only spend {p:.0f}% of your salary on expenses.")
    if trend == "increasing": advice.append("Your spending is going up. Review and cut non-essentials.")
    elif trend == "decreasing": advice.append("Your spending is going down. Excellent discipline!")
    sav = sum(t.amount for t in txs if t.type=="saving")
    inc = sum(t.amount for t in txs if t.type=="income")
    if inc and sav/inc < .1: advice.append("You save less than 10% of income. Aim for 20%.")
    if not advice: advice.append("Add more transactions to get personalised advice.")
    bp = {}
    if sal: bp = {"salary": sal, "needs_50pct": round(sal*.5,2), "savings_20pct": round(sal*.2,2),
                  "wants_20pct": round(sal*.2,2), "invest_10pct": round(sal*.1,2),
                  "rule": "50/20/20/10: 50% needs, 20% savings, 20% wants, 10% investments"}
    return {"next_month_expenses": round(pred,2), "avg_monthly_expenses": round(avg,2),
            "trend": trend, "advice": advice, "budget_plan": bp}


# ── Activity Log ───────────────────────────────────────────────────────────────
@app.get("/activity", response_model=List[schemas.ActivityLogOut])
def activity(db: Session = Depends(get_db), cu: models.User = Depends(get_current_user)):
    return db.query(models.ActivityLog).filter(models.ActivityLog.user_id == cu.id)\
             .order_by(models.ActivityLog.timestamp.desc()).limit(50).all()


# ── Category Breakdown ─────────────────────────────────────────────────────────
@app.get("/analytics/categories")
def categories(db: Session = Depends(get_db), cu: models.User = Depends(get_current_user)):
    txs = db.query(models.Transaction).filter(
        models.Transaction.user_id == cu.id,
        models.Transaction.type == "expense"
    ).all()
    cats = defaultdict(float)
    for t in txs:
        cats[t.category] += t.amount
    total = sum(cats.values()) or 1
    return [{"category": k, "amount": round(v, 2), "percentage": round(v/total*100, 1)}
            for k, v in sorted(cats.items(), key=lambda x: x[1], reverse=True)]
