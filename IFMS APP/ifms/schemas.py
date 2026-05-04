from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class UserCreate(BaseModel):
    email: str
    username: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class UserUpdate(BaseModel):
    username: Optional[str] = None
    salary: Optional[float] = None

class UserOut(BaseModel):
    id: int
    email: str
    username: str
    salary: float
    mfa_enabled: bool
    created_at: datetime
    model_config = {"from_attributes": True}

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut

class MFAVerify(BaseModel):
    email: str
    code: str

class TransactionCreate(BaseModel):
    amount: float
    type: str
    category: str
    description: Optional[str] = ""
    date: Optional[datetime] = None

class TransactionUpdate(BaseModel):
    amount: Optional[float] = None
    category: Optional[str] = None
    description: Optional[str] = None

class TransactionOut(BaseModel):
    id: int
    amount: float
    type: str
    category: str
    description: str
    date: datetime
    user_id: int
    model_config = {"from_attributes": True}

class GoalCreate(BaseModel):
    name: str
    target: float
    saved: Optional[float] = 0.0
    deadline: Optional[datetime] = None

class GoalUpdate(BaseModel):
    name: Optional[str] = None
    target: Optional[float] = None
    saved: Optional[float] = None

class GoalOut(BaseModel):
    id: int
    name: str
    target: float
    saved: float
    deadline: Optional[datetime]
    created_at: datetime
    user_id: int
    model_config = {"from_attributes": True}

class Summary(BaseModel):
    total_income: float
    total_expenses: float
    total_savings: float
    balance: float
    transaction_count: int
    salary: float
    budget_used_pct: float

class MonthSummary(BaseModel):
    month: str
    income: float
    expenses: float
    savings: float
    balance: float

class Prediction(BaseModel):
    next_month_expenses: float
    avg_monthly_expenses: float
    trend: str
    advice: List[str]
    budget_plan: dict

class ActivityLogOut(BaseModel):
    id: int
    action: str
    detail: str
    timestamp: datetime
    ip_address: str
    model_config = {"from_attributes": True}
