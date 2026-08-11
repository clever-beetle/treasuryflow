from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy_utils import EncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine
import os

SECRET_KEY = os.environ.get('SECRET_KEY', 'finance-tracker-static-secret-key-fallback')

class Base(DeclarativeBase):
    def __getitem__(self, key):
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)
        
    def keys(self):
        return [c.name for c in self.__table__.columns]

db = SQLAlchemy(model_class=Base)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fullname = db.Column(db.String(100))
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(255), nullable=False)
    reset_token = db.Column(db.String(255))
    token_expiry = db.Column(db.String(50))
    role = db.Column(db.String(20), default='user')

class FeatureFlag(db.Model):
    __tablename__ = 'feature_flags'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=False)

class Account(db.Model):
    __tablename__ = 'accounts'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    initial_balance = db.Column(db.Float, nullable=False, default=0.0)
    current_balance = db.Column(db.Float, nullable=False, default=0.0)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.String(20), nullable=False) 
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False) 
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255))
    category = db.Column(db.String(100))
    linked_transaction_id = db.Column(db.Integer)

class CreditCard(db.Model):
    __tablename__ = 'credit_cards'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(EncryptedType(db.String(100), SECRET_KEY, AesEngine, 'pkcs5'), nullable=False)
    limit_amount = db.Column(db.Float, nullable=False)
    current_usage = db.Column(db.Float, nullable=False, default=0.0)

class UserCategory(db.Model):
    __tablename__ = 'user_categories'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)

class DebtReceivable(db.Model):
    __tablename__ = 'debts_receivables'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    person_name = db.Column(db.String(100), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    remaining_amount = db.Column(db.Float, nullable=False)
    due_date = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='BELUM LUNAS')
    notes = db.Column(db.String(255))
    created_at = db.Column(db.String(50), default=datetime.utcnow)

class DebtPayment(db.Model):
    __tablename__ = 'debt_payments'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    debt_id = db.Column(db.Integer, db.ForeignKey('debts_receivables.id'), nullable=False)
    account_name = db.Column(db.String(100), nullable=False)
    amount_paid = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.String(50), default=datetime.utcnow)
    notes = db.Column(db.String(255))

class RecurringInstallment(db.Model):
    __tablename__ = 'recurring_installments'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    amount_per_cycle = db.Column(db.Float, nullable=False)
    due_day_of_month = db.Column(db.Integer, nullable=False)
    is_temporary_tenor = db.Column(db.Integer, default=0)
    total_tenor = db.Column(db.Integer, nullable=True)
    current_tenor = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.String(50), default=datetime.utcnow)

class Asset(db.Model):
    __tablename__ = 'assets'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    asset_name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    purchase_date = db.Column(db.String(50), nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.String(100))
    notes = db.Column(db.String(255))
    created_at = db.Column(db.String(50), default=datetime.utcnow)

class FinancialGoal(db.Model):
    __tablename__ = 'financial_goals'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, nullable=False, default=0.0)
    due_date = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(50), default='In Progress')

class Budget(db.Model):
    __tablename__ = 'budgets'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_name = db.Column(db.String(100), nullable=False)
    limit_amount = db.Column(db.Float, nullable=False)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'category_name', name='uq_user_category_budget'),
    )
