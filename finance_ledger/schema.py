APPLICATION_ID = 0x464C4544
MIGRATIONS = [(1, '''
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO settings VALUES('business_name','Finance Ledger');
CREATE TABLE parties(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL CHECK(length(trim(name))>0), phone TEXT NOT NULL DEFAULT '',
 address TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
 roles TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE cash_accounts(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE CHECK(length(trim(name))>0),
 kind TEXT NOT NULL CHECK(kind IN ('cash','bank')), opening_paise INTEGER NOT NULL CHECK(typeof(opening_paise)='integer' AND abs(opening_paise)<=9000000000000000),
 opening_date TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE finance_accounts(
 id INTEGER PRIMARY KEY, reference TEXT NOT NULL UNIQUE CHECK(length(trim(reference))>0),
 party_id INTEGER NOT NULL REFERENCES parties(id),
 module TEXT NOT NULL CHECK(module IN ('fd','loan','other','hand_given','hand_taken')),
 start_date TEXT NOT NULL, opening_paise INTEGER NOT NULL CHECK(typeof(opening_paise)='integer' AND opening_paise>=0 AND opening_paise<=9000000000000000),
 annual_rate TEXT NOT NULL DEFAULT '0', frequency TEXT NOT NULL DEFAULT 'Monthly', due_date TEXT,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','matured','closed')),
 notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE categories(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE CHECK(length(trim(name))>0),
 kind TEXT NOT NULL CHECK(kind IN ('income','expense'))
);
INSERT INTO categories(name,kind) VALUES('Miscellaneous income','income'),('Operating expenses','expense');
CREATE TABLE posting_groups(
 id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE, idempotency_key TEXT NOT NULL UNIQUE,
 fingerprint TEXT NOT NULL, tx_date TEXT NOT NULL,
 method TEXT NOT NULL CHECK(method IN ('cash','bank transfer','UPI','cheque','other')),
 external_ref TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
 reversal_of TEXT UNIQUE REFERENCES posting_groups(id), created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE entries(
 id INTEGER PRIMARY KEY, group_id TEXT NOT NULL REFERENCES posting_groups(id),
 cash_id INTEGER NOT NULL REFERENCES cash_accounts(id), party_id INTEGER REFERENCES parties(id),
 finance_id INTEGER REFERENCES finance_accounts(id), category_id INTEGER REFERENCES categories(id),
 type TEXT NOT NULL CHECK(type IN ('fd_received','fd_repaid','fd_interest','loan_disbursed','loan_repaid','loan_interest',
 'other_received','other_repaid','other_interest','hand_given_disbursed','hand_given_repaid','hand_given_interest',
 'hand_taken_received','hand_taken_repaid','hand_taken_interest','general_income','general_expense','transfer_in','transfer_out')),
 amount_paise INTEGER NOT NULL CHECK(typeof(amount_paise)='integer' AND amount_paise>0 AND amount_paise<=9000000000000000),
 direction INTEGER NOT NULL CHECK(direction IN (-1,1)), principal_delta INTEGER NOT NULL CHECK(principal_delta IN (-1,0,1)),
 interest INTEGER NOT NULL CHECK(interest IN (0,1)), factor INTEGER NOT NULL CHECK(factor IN (-1,1))
);
CREATE TABLE audit_log(id INTEGER PRIMARY KEY, entity TEXT NOT NULL, entity_id TEXT NOT NULL, action TEXT NOT NULL,
 before_json TEXT, after_json TEXT, actor TEXT NOT NULL, at TEXT NOT NULL);
CREATE INDEX entries_finance ON entries(finance_id);
CREATE INDEX entries_cash ON entries(cash_id);
CREATE INDEX entries_party ON entries(party_id);
CREATE INDEX entries_group ON entries(group_id);
CREATE INDEX groups_date ON posting_groups(tx_date,created_at);
CREATE INDEX finance_party ON finance_accounts(party_id);
CREATE TRIGGER entries_no_update BEFORE UPDATE ON entries BEGIN SELECT RAISE(ABORT,'Posted entries are immutable. Use a reversal.'); END;
CREATE TRIGGER entries_no_delete BEFORE DELETE ON entries BEGIN SELECT RAISE(ABORT,'Posted entries cannot be deleted.'); END;
CREATE TRIGGER groups_no_update BEFORE UPDATE ON posting_groups BEGIN SELECT RAISE(ABORT,'Posted transactions are immutable.'); END;
CREATE TRIGGER groups_no_delete BEFORE DELETE ON posting_groups BEGIN SELECT RAISE(ABORT,'Posted transactions cannot be deleted.'); END;
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT,'Audit history is immutable.'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT,'Audit history cannot be deleted.'); END;
''')]
