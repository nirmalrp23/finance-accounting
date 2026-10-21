"""Cash-book labels from the user's reference; accounting types remain stable."""

TRANSACTION_DETAILS = {
    'loan_disbursed': 'STL LOAN DEBIT',
    'loan_repaid': 'STL LOAN CREDIT',
    'loan_interest': 'STL INTEREST CREDIT',
    'fd_received': 'FD CREDIT',
    'fd_repaid': 'FD DEBIT',
    'fd_interest': 'FD INTEREST DEBIT',
    'other_received': 'EXTERNAL LOAN CREDIT',
    'other_repaid': 'EXTERNAL LOAN DEBIT',
    'other_interest': 'EXTERNAL LOAN INTEREST DEBIT',
    'hand_given_disbursed': 'HAND LOAN DEBIT',
    'hand_given_repaid': 'HAND LOAN CREDIT',
    'hand_given_interest': 'HAND LOAN INTEREST CREDIT',
    'hand_taken_received': 'FINANCE HAND LOAN CREDIT',
    'hand_taken_repaid': 'FINANCE HAND LOAN DEBIT',
    'hand_taken_interest': 'FINANCE HAND LOAN INTEREST DEBIT',
    'general_expense': 'OFFICE EXPENSES',
    'general_income': 'OTHER INCOME',
    'transfer_out': 'CASH / BANK TRANSFER',
}
CATEGORY_REPORTS = {key: label + ' report' for key, label in TRANSACTION_DETAILS.items()}


def transaction_detail(type_key):
    return TRANSACTION_DETAILS.get(type_key, 'CASH / BANK TRANSFER IN')
