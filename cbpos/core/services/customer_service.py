from typing import List, Optional, Dict, Any
from decimal import Decimal
from sqlalchemy import select, or_
from cbpos.core.database import Database
from cbpos.core.models import Customer


class CustomerService:
    def __init__(self):
        self.db = Database()

    def create_customer(self, data: Dict[str, Any]) -> Customer:
        with self.db.get_session() as session:
            customer = Customer(**data)
            session.add(customer)
            session.commit()
            session.refresh(customer)
            session.expunge(customer)
            return customer

    def update_customer(
        self, customer_id: int, data: Dict[str, Any]
    ) -> Optional[Customer]:
        with self.db.get_session() as session:
            customer = session.get(Customer, customer_id)
            if not customer:
                return None

            for key, value in data.items():
                if hasattr(customer, key):
                    setattr(customer, key, value)

            session.commit()
            session.refresh(customer)
            session.expunge(customer)
            return customer

    def update_balance(self, customer_id: int, amount_change: Decimal) -> bool:
        """
        Updates the customer's debt.
        Positive amount_change increases debt (credit sale).
        Negative amount_change decreases debt (payment).
        """
        with self.db.get_session() as session:
            customer = session.get(Customer, customer_id)
            if not customer:
                return False

            customer.current_debt += amount_change
            session.commit()
            return True

    def add_loyalty_points(self, customer_id: int, amount_spent: Decimal) -> int:
        """
        Adds loyalty points based on amount spent.
        Rule: 1 point per 100 currency units.
        """
        points_to_add = int(amount_spent // 100)
        if points_to_add <= 0:
            return 0

        with self.db.get_session() as session:
            customer = session.get(Customer, customer_id)
            if not customer:
                return 0

            customer.loyalty_points += points_to_add
            session.commit()
            return points_to_add

    def search_customers(self, query: str) -> List[Customer]:
        with self.db.get_session() as session:
            stmt = select(Customer).where(
                or_(
                    Customer.name.ilike(f"%{query}%"),
                    Customer.phone.ilike(f"%{query}%"),
                ),
                Customer.is_active.is_(True),
            )
            customers = list(session.scalars(stmt).all())
            for customer in customers:
                session.expunge(customer)
            return customers

    def get_customer(self, customer_id: int) -> Optional[Customer]:
        with self.db.get_session() as session:
            customer = session.get(Customer, customer_id)
            if customer:
                session.expunge(customer)
            return customer

    def get_all_customers(self) -> List[Customer]:
        with self.db.get_session() as session:
            stmt = select(Customer).where(Customer.is_active.is_(True))
            customers = list(session.scalars(stmt).all())
            for customer in customers:
                session.expunge(customer)
            return customers
