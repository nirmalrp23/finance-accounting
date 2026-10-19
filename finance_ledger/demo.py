from .ledger import Ledger


def seed_demo(database):
    """Called only in the separate --demo data directory, never production."""
    ledger = Ledger(database)
    if database.one('SELECT id FROM cash_accounts LIMIT 1'):
        return
    cash = ledger.add_cash('Cash in hand','cash',10_000_000,'2026-10-01')
    ledger.add_cash('Business bank account','bank',0,'2026-10-01')
    depositor = ledger.save_party({'name':'Anita Sharma','phone':'98765 43210','roles':'FD depositor','notes':'DEMO DATA'})
    borrower = ledger.save_party({'name':'Ravi Kumar','phone':'98765 12345','roles':'Loan borrower','notes':'DEMO DATA'})
    fd = ledger.add_finance('FD-DEMO-001',depositor,'fd','2026-10-01',annual_rate='8',due_date='2027-10-01')
    loan = ledger.add_finance('LN-DEMO-001',borrower,'loan','2026-10-01',annual_rate='12',due_date='2026-12-31')
    ledger.post(tx_date='2026-10-02',components=[('fd_received',5_000_000)],cash_id=cash,finance_id=fd,idempotency_key='demo-fd')
    ledger.post(tx_date='2026-10-03',components=[('loan_disbursed',2_000_000)],cash_id=cash,finance_id=loan,idempotency_key='demo-loan')
    ledger.post(tx_date='2026-10-10',components=[('loan_repaid',500_000),('loan_interest',50_000)],cash_id=cash,finance_id=loan,idempotency_key='demo-split')
    ledger.post(tx_date='2026-10-15',components=[('fd_interest',30_000)],cash_id=cash,finance_id=fd,idempotency_key='demo-interest')
