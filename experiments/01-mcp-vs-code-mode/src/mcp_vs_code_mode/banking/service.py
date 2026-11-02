"""Banking service: the only component that reads data.

Authorization is enforced here, independently of any LLM. Every call writes
exactly one audit record, whether it succeeds or fails.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from mcp_vs_code_mode.banking.audit import AuditLog, AuditOutcome, AuditRecord, Channel
from mcp_vs_code_mode.banking.auth import Principal
from mcp_vs_code_mode.banking.errors import (
    AuthorizationError,
    InvalidRequestError,
    NotFoundError,
)
from mcp_vs_code_mode.banking.models import (
    Account,
    Balance,
    Customer,
    Dataset,
    SpendingSummary,
    Transaction,
)


def _transaction_order(txn: Transaction) -> tuple[date, str]:
    """Sort key: date, then transaction id."""
    return (txn.date, txn.transaction_id)


class BankingService:
    """Read-only banking operations with authorization and auditing."""

    def __init__(self, dataset: Dataset, audit_log: AuditLog) -> None:
        self._audit_log = audit_log
        self._customers: dict[str, Customer] = {c.customer_id: c for c in dataset.customers}
        self._accounts: dict[str, Account] = {a.account_id: a for a in dataset.accounts}
        self._balances: dict[str, Balance] = {b.account_id: b for b in dataset.balances}
        self._accounts_by_customer: dict[str, list[Account]] = {}
        for account in dataset.accounts:
            self._accounts_by_customer.setdefault(account.customer_id, []).append(account)
        self._transactions_by_account: dict[str, list[Transaction]] = {}
        for txn in dataset.transactions:
            self._transactions_by_account.setdefault(txn.account_id, []).append(txn)

    @contextmanager
    def _audited(
        self,
        principal: Principal,
        channel: Channel,
        operation: str,
        arguments: dict[str, str],
    ) -> Iterator[None]:
        """Write exactly one audit record for the wrapped call."""
        started = time.perf_counter()
        outcome: AuditOutcome = "allowed"
        try:
            yield
        except AuthorizationError:
            outcome = "denied"
            raise
        except NotFoundError:
            outcome = "not_found"
            raise
        except InvalidRequestError:
            outcome = "invalid"
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            self._audit_log.record(
                AuditRecord(
                    timestamp=datetime.now(UTC),
                    principal_id=principal.principal_id,
                    channel=channel,
                    operation=operation,
                    arguments=arguments,
                    outcome=outcome,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                )
            )

    def _require_customer(self, principal: Principal, customer_id: str) -> Customer:
        customer = self._customers.get(customer_id)
        if customer is None:
            raise NotFoundError(f"Customer {customer_id} not found")
        if customer_id not in principal.allowed_customer_ids:
            raise AuthorizationError("Access denied")
        return customer

    def _require_account(self, principal: Principal, account_id: str) -> Account:
        account = self._accounts.get(account_id)
        if account is None:
            raise NotFoundError(f"Account {account_id} not found")
        if account.customer_id not in principal.allowed_customer_ids:
            raise AuthorizationError("Access denied")
        return account

    def get_customer(self, principal: Principal, customer_id: str, *, channel: Channel) -> Customer:
        """Return a customer profile."""
        with self._audited(principal, channel, "get_customer", {"customer_id": customer_id}):
            return self._require_customer(principal, customer_id)

    def list_accounts(
        self, principal: Principal, customer_id: str, *, channel: Channel
    ) -> tuple[Account, ...]:
        """Return a customer's accounts."""
        with self._audited(principal, channel, "list_accounts", {"customer_id": customer_id}):
            self._require_customer(principal, customer_id)
            return tuple(self._accounts_by_customer.get(customer_id, ()))

    def get_balance(self, principal: Principal, account_id: str, *, channel: Channel) -> Balance:
        """Return an account balance."""
        with self._audited(principal, channel, "get_balance", {"account_id": account_id}):
            self._require_account(principal, account_id)
            return self._balances[account_id]

    def get_transactions(
        self,
        principal: Principal,
        account_id: str,
        start_date: date,
        end_date: date,
        *,
        channel: Channel,
    ) -> tuple[Transaction, ...]:
        """Return transactions with ``start_date <= date <= end_date``."""
        arguments = {
            "account_id": account_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        with self._audited(principal, channel, "get_transactions", arguments):
            self._require_account(principal, account_id)
            if start_date > end_date:
                raise InvalidRequestError("start_date must not be after end_date")
            selected = [
                t
                for t in self._transactions_by_account.get(account_id, ())
                if start_date <= t.date <= end_date
            ]
            return tuple(sorted(selected, key=_transaction_order))

    def summarise_spending(
        self,
        principal: Principal,
        account_id: str,
        start_date: date,
        end_date: date,
        large_debit_threshold: float,
        *,
        channel: Channel,
    ) -> SpendingSummary:
        """Aggregate debits in the window: spend per category and large-debit ids."""
        arguments = {
            "account_id": account_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "large_debit_threshold": str(large_debit_threshold),
        }
        with self._audited(principal, channel, "summarise_spending", arguments):
            self._require_account(principal, account_id)
            if start_date > end_date:
                raise InvalidRequestError("start_date must not be after end_date")
            if large_debit_threshold <= 0:
                raise InvalidRequestError("large_debit_threshold must be greater than 0")
            threshold = Decimal(str(large_debit_threshold))
            totals: dict[str, Decimal] = {}
            large: list[str] = []
            count = 0
            for txn in self._transactions_by_account.get(account_id, ()):
                if not start_date <= txn.date <= end_date or txn.amount >= 0:
                    continue
                absolute = abs(Decimal(str(txn.amount)))
                count += 1
                totals[txn.category] = totals.get(txn.category, Decimal(0)) + absolute
                if absolute > threshold:
                    large.append(txn.transaction_id)
            cent = Decimal("0.01")
            return SpendingSummary(
                account_id=account_id,
                start_date=start_date,
                end_date=end_date,
                spend_by_category={
                    category: float(total.quantize(cent, rounding=ROUND_HALF_UP))
                    for category, total in sorted(totals.items())
                },
                large_debit_ids=sorted(large),
                debit_count=count,
            )
