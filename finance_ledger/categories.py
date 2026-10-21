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
# Historical labels stay available to reports, filters and audit history.
ENTRY_DETAILS = {key: label for key, label in TRANSACTION_DETAILS.items() if key not in ('hand_taken_interest', 'hand_given_interest')}

REPORT_TYPE_CHOICES = (
    (None, 'All transaction'),
    ('loan_repaid', 'STL LOAN CREDIT'),
    ('loan_disbursed', 'STL LOAN DEBIT'),
    ('loan_interest', 'STL LOAN INTEREST CREDIT'),
    ('fd_received', 'FD CREDIT'),
    ('fd_repaid', 'FD DEBIT'),
    ('fd_interest', 'FD INTEREST DEBIT'),
    ('other_received', 'EXTERNAL LOAN CREDIT'),
    ('other_repaid', 'EXTERNAL LOAN DEBIT'),
    ('other_interest', 'EXTERNAL LOAN INTEREST DEBIT'),
    ('general_expense', 'EXPENCE'),
    ('general_income', 'OTHER INCOME'),
)

# Report families combine principal debit/credit and actual interest.
CATEGORY_TYPES = {
    'stl': ('loan_disbursed', 'loan_repaid', 'loan_interest'),
    'fd': ('fd_received', 'fd_repaid', 'fd_interest'),
    'external': ('other_received', 'other_repaid', 'other_interest'),
    'hand_given': ('hand_given_disbursed', 'hand_given_repaid', 'hand_given_interest'),
    'hand_taken': ('hand_taken_received', 'hand_taken_repaid', 'hand_taken_interest'),
    'general_expense': ('general_expense',),
    'general_income': ('general_income',),
    'transfers': ('transfer_out', 'transfer_in'),
}
CATEGORY_REPORTS = dict(zip(CATEGORY_TYPES, (
    'STL Loans report', 'Fixed Deposits report', 'External Loan report',
    'Hand Loan report', 'Finance Hand Loans report',
    'Office Expenses report', 'Other Income report', 'Cash / Bank Transfers report',
)))


def transaction_detail(type_key):
    return TRANSACTION_DETAILS.get(type_key, 'CASH / BANK TRANSFER IN')
