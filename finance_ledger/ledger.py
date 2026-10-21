"""The only posting boundary. All related writes and validation run atomically."""
import getpass
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date
from .money import MAX_PAISE, interest_paise, rate, timestamp, today, valid_date


@dataclass(frozen=True)
class TransactionType:
    label: str
    module: str | None
    direction: int
    principal: int = 0
    interest: bool = False


TYPES = {
 'fd_received': TransactionType('FD principal received', 'fd', 1, 1),
 'fd_repaid': TransactionType('FD principal repaid', 'fd', -1, -1),
 'fd_interest': TransactionType('FD interest paid', 'fd', -1, 0, True),
 'loan_disbursed': TransactionType('Loan disbursement', 'loan', -1, 1),
 'loan_repaid': TransactionType('Loan principal repayment', 'loan', 1, -1),
 'loan_interest': TransactionType('Loan interest received', 'loan', 1, 0, True),
 'other_received': TransactionType('External Loan principal received', 'other', 1, 1),
 'other_repaid': TransactionType('External Loan principal repaid', 'other', -1, -1),
 'other_interest': TransactionType('External Loan interest paid', 'other', -1, 0, True),
 'hand_given_disbursed': TransactionType('Hand loan', 'hand_given', -1, 1),
 'hand_given_repaid': TransactionType('Hand loan principal received', 'hand_given', 1, -1),
 'hand_given_interest': TransactionType('Hand loan interest received', 'hand_given', 1, 0, True),
 'hand_taken_received': TransactionType('Hand loan taken', 'hand_taken', 1, 1),
 'hand_taken_repaid': TransactionType('Hand loan principal paid', 'hand_taken', -1, -1),
 'hand_taken_interest': TransactionType('Hand loan interest paid', 'hand_taken', -1, 0, True),
 'general_income': TransactionType('General income', None, 1),
 'general_expense': TransactionType('General expense', None, -1),
 'transfer_in': TransactionType('Internal transfer in', None, 1),
 'transfer_out': TransactionType('Internal transfer out', None, -1),
}
MODULES = {'fd':'Fixed Deposits','loan':'Loans','other':'External Loan','hand_given':'Hand Loan','hand_taken':'Hand Loans Taken'}
ENTRY_MODULE_SQL = "COALESCE(f.module,CASE e.type " + ' '.join("WHEN '"+key+"' THEN '"+spec.module+"'" for key,spec in TYPES.items() if spec.module) + " END)"

METHODS = ('cash', 'bank transfer', 'UPI', 'cheque', 'other')


class Ledger:
    def __init__(self, database):
        self.db = database

    def parties(self):
        return self.db.all('SELECT * FROM parties ORDER BY name COLLATE NOCASE')

    def finance_accounts(self):
        return self.db.all('SELECT f.*,p.name party_name FROM finance_accounts f JOIN parties p ON p.id=f.party_id ORDER BY f.reference')

    def cash_accounts(self):
        return self.db.all('SELECT * FROM cash_accounts ORDER BY kind,name')

    def save_party(self, values, party_id=None):
        values = {k: str(values.get(k, '')).strip() for k in ('name','phone','address','email','notes','roles')} | {'active':int(values.get('active', 1))}
        if not values['name']:
            raise ValueError('Party name is required.')
        if values['email'] and ('@' not in values['email'] or '.' not in values['email'].split('@')[-1]):
            raise ValueError('Enter a valid email address or leave it empty.')
        with self.db.atomic():
            before = self.db.one('SELECT * FROM parties WHERE id=?', (party_id,))
            if party_id and not before:
                raise ValueError('Party does not exist.')
            now = timestamp()
            if party_id:
                self.db.conn.execute('UPDATE parties SET name=:name,phone=:phone,address=:address,email=:email,notes=:notes,roles=:roles,active=:active,updated_at=:at WHERE id=:id', values | {'at':now,'id':party_id})
            else:
                party_id = self.db.conn.execute('INSERT INTO parties(name,phone,address,email,notes,roles,active,created_at,updated_at) VALUES(:name,:phone,:address,:email,:notes,:roles,:active,:at,:at)', values | {'at':now}).lastrowid
            self.db.audit('party', party_id, 'update' if before else 'create', before, values)
        return party_id

    def add_cash(self, name, kind, opening_paise, opening_date, notes=''):
        if not name.strip() or kind not in ('cash','bank'):
            raise ValueError('Provide an account name and select Cash or Bank.')
        self._integer(opening_paise, positive=False)
        valid_date(opening_date)
        with self.db.atomic():
            cash_id = self.db.conn.execute('INSERT INTO cash_accounts(name,kind,opening_paise,opening_date,notes) VALUES(?,?,?,?,?)', (name.strip(),kind,opening_paise,opening_date,notes)).lastrowid
            self.db.audit('cash_account', cash_id, 'create', after={'name':name,'opening_paise':opening_paise,'opening_date':opening_date})
        return cash_id

    def add_finance(self, reference, party_id, module, start_date, opening_paise=0, annual_rate='0', frequency='Monthly', due_date=None, notes=''):
        if module not in MODULES or not reference.strip():
            raise ValueError('Select a valid module and enter a reference.')
        valid_date(start_date)
        if due_date:
            valid_date(due_date)
            if due_date < start_date:
                raise ValueError('Due/maturity date cannot precede the start date.')
        self._integer(opening_paise, positive=False)
        if opening_paise < 0:
            raise ValueError('Opening principal cannot be negative.')
        annual_rate = rate(annual_rate)
        with self.db.atomic():
            party = self.db.one('SELECT * FROM parties WHERE id=? AND active=1', (party_id,))
            if not party:
                raise ValueError('Select an active party.')
            account_id = self.db.conn.execute('INSERT INTO finance_accounts(reference,party_id,module,start_date,opening_paise,annual_rate,frequency,due_date,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)', (reference.strip(),party_id,module,start_date,opening_paise,annual_rate,frequency,due_date or None,notes,timestamp())).lastrowid
            self.db.audit('finance_account', account_id, 'create', after={'reference':reference,'module':module,'opening_paise':opening_paise})
        return account_id

    def update_finance(self, account_id, status, annual_rate, due_date, frequency, notes):
        if status not in ('active','matured','closed'):
            raise ValueError('Invalid account status.')
        annual_rate = rate(annual_rate)
        if due_date:
            valid_date(due_date)
        with self.db.atomic():
            before = self.db.one('SELECT * FROM finance_accounts WHERE id=?', (account_id,))
            if not before:
                raise ValueError('Account not found.')
            if due_date and due_date < before['start_date']:
                raise ValueError('Due date cannot precede the start date.')
            if status == 'closed' and self.principal(account_id, '9999-12-31') != 0:
                raise ValueError('Repay all principal before closing the account.')
            self.db.conn.execute('UPDATE finance_accounts SET status=?,annual_rate=?,due_date=?,frequency=?,notes=? WHERE id=?', (status,annual_rate,due_date or None,frequency,notes,account_id))
            self.db.audit('finance_account', account_id, 'update', before, {'status':status,'annual_rate':annual_rate,'due_date':due_date,'frequency':frequency,'notes':notes})

    def add_category(self, name, kind):
        if not name.strip() or kind not in ('income','expense'):
            raise ValueError('Enter a category name and choose income or expense.')
        with self.db.atomic():
            category_id = self.db.conn.execute('INSERT INTO categories(name,kind) VALUES(?,?)', (name.strip(),kind)).lastrowid
            self.db.audit('category',category_id,'create',after={'name':name,'kind':kind})
        return category_id

    @staticmethod
    def _integer(amount, positive=True):
        if type(amount) is not int or abs(amount) > MAX_PAISE or (positive and amount <= 0):
            raise ValueError('Enter a positive amount with at most two decimal places (within the supported range).')

    def principal(self, account_id, as_of=None):
        as_of = valid_date(as_of or today())
        account = self.db.one('SELECT * FROM finance_accounts WHERE id=?', (account_id,))
        if not account:
            raise ValueError('Finance account not found.')
        if as_of < account['start_date']:
            return 0
        movements = self.db.one('SELECT COALESCE(SUM(e.amount_paise*e.principal_delta*e.factor),0) amount FROM entries e JOIN posting_groups g ON g.id=e.group_id WHERE e.finance_id=? AND g.tx_date<=?', (account_id,as_of))
        return account['opening_paise'] + movements['amount']

    def cash_balance(self, cash_id, as_of=None):
        as_of = valid_date(as_of or today())
        account = self.db.one('SELECT * FROM cash_accounts WHERE id=?', (cash_id,))
        if not account:
            raise ValueError('Payment account not found.')
        if as_of < account['opening_date']:
            return 0
        amount = self.db.one('SELECT COALESCE(SUM(e.amount_paise*e.direction*e.factor),0) amount FROM entries e JOIN posting_groups g ON g.id=e.group_id WHERE e.cash_id=? AND g.tx_date<=?', (cash_id,as_of))['amount']
        return account['opening_paise'] + amount

    def _validate_principal_timeline(self, account_id):
        if hasattr(self,'_pending_edit_checks'):
            self._pending_edit_checks.add(account_id)
            return
        account = self.db.one('SELECT * FROM finance_accounts WHERE id=?', (account_id,))
        balance = account['opening_paise']
        # End-of-day checks allow linked reversal/replacement on one business date.
        for event in self.db.all('SELECT g.tx_date,SUM(e.amount_paise*e.principal_delta*e.factor) delta FROM entries e JOIN posting_groups g ON g.id=e.group_id WHERE e.finance_id=? GROUP BY g.tx_date ORDER BY g.tx_date', (account_id,)):
            balance += event['delta']
            if balance < 0:
                raise ValueError(f'Principal would be negative on {event["tx_date"]}. Repayment exceeds outstanding principal, including later dated records.')
            if balance > MAX_PAISE:
                raise ValueError('Principal exceeds the supported amount range.')

    def post_quick_entry(self, *, name, place_name, amount_paise, direction,
                         type_key, tx_date, cash_id, idempotency_key):
        """Five-field intake; resolve a unique account without guessing allocations."""
        spec=TYPES.get(type_key)
        if not spec or type_key.startswith('transfer'):
            raise ValueError('Use Cash & Bank → Transfer for linked transfers.')
        if direction not in ('IN','OUT') or direction != ('IN' if spec.direction==1 else 'OUT'):
            raise ValueError('Choose Transaction details matching IN/OUT.')
        name=name.strip(); place_name=place_name.strip()
        self._integer(amount_paise); valid_date(tx_date)
        request=dict(name=name,place_name=place_name,amount_paise=amount_paise,
                     direction=direction,type_key=type_key,tx_date=tx_date,cash_id=cash_id)
        fingerprint=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
        with self.db.atomic():
            existing=self.db.one('SELECT id FROM posting_groups WHERE idempotency_key=?',(idempotency_key,))
            if existing:
                audit=self.db.one("SELECT after_json FROM audit_log WHERE entity='transaction' AND entity_id=? AND action='quick_entry'",(existing['id'],))
                if not audit or json.loads(audit['after_json']).get('fingerprint')!=fingerprint:
                    raise ValueError('This submission key was already used for different values.')
                return existing['id']
            matches=[p for p in self.parties() if p['name'].casefold()==name.casefold()]
            party_id=matches[0]['id'] if len(matches)==1 else None
            finance_id=None
            if spec.module:
                if not name: raise ValueError('Enter Name for this finance entry.')
                if len(matches)>1:
                    raise ValueError('More than one party has this name. Give the parties distinct names before posting.')
                if matches and not matches[0]['active']:
                    raise ValueError('This party is inactive. Reactivate it before posting.')
                accounts=[a for a in self.finance_accounts() if a['party_id']==party_id and a['module']==spec.module]
                active=[a for a in accounts if a['status']!='closed']
                if len(active)>1:
                    raise ValueError('More than one finance account matches this name and category. Quick entry cannot choose an account safely; no entry was saved.')
                if active:
                    finance_id=active[0]['id']
                elif accounts:
                    raise ValueError('The matching finance account is closed. Reopen it before posting.')
                elif spec.principal==1:
                    if party_id is None:
                        party_id=self.save_party({'name':name,'roles':MODULES[spec.module]})
                    finance_id=self.add_finance(spec.module.upper()+'-'+uuid.uuid4().hex[:10].upper(),party_id,spec.module,tx_date)
                # A missing account is allowed: record the cash movement without inventing principal history.
            cash=self.db.one('SELECT kind FROM cash_accounts WHERE id=?',(cash_id,))
            category_id=None
            if type_key.startswith('general'):
                category=self.db.one('SELECT id FROM categories WHERE kind=? ORDER BY id LIMIT 1',('income' if spec.direction==1 else 'expense',))
                if not category: raise ValueError('Add an income/expense heading in Settings first.')
                category_id=category['id']
            group=self.post(tx_date=tx_date,components=[(type_key,amount_paise)],cash_id=cash_id,
                            idempotency_key=idempotency_key,party_id=party_id,finance_id=finance_id,
                            category_id=category_id,method='cash' if cash and cash['kind']=='cash' else 'bank transfer',
                            place_name=place_name,entry_name=name,allow_unallocated=bool(spec.module and finance_id is None))
            self.db.audit('transaction',group,'quick_entry',after=request | {'fingerprint':fingerprint})
            return group

    def post_cashbook(self, *, type_key, amount_paise, tx_date, cash_id,
                      idempotency_key, particulars='', party_id=None,
                      finance_id=None, new_party=None, new_finance=None,
                      interest_paise=0, category_id=None, method='cash',
                      external_ref='', notes='', transfer_to=None, place_name=''):
        """One intake: party, finance account and posting commit or roll back together.

        The intake fingerprint is checked before any master records are created,
        so retrying a successful form cannot create duplicate parties/accounts.
        """
        spec = TYPES.get(type_key)
        if not spec or type_key == 'transfer_in':
            raise ValueError('Select an explicit transaction-details category.')
        self._integer(amount_paise)
        self._integer(interest_paise, positive=False)
        if interest_paise < 0 or (interest_paise and type_key != 'loan_repaid'):
            raise ValueError('Additional interest is only available for an STL loan principal receipt.')
        if party_id and new_party is not None:
            raise ValueError('Choose an existing party or create a new party, not both.')
        if finance_id and new_finance is not None:
            raise ValueError('Choose an existing finance account or create a new one, not both.')
        if new_finance is not None and not spec.module:
            raise ValueError('This category cannot open a finance account.')
        if finance_id and new_party is not None:
            raise ValueError('An existing finance account already belongs to a party.')
        if type_key == 'transfer_out' and (party_id or new_party is not None):
            raise ValueError('Transfers cannot create or link a party.')
        request = dict(type_key=type_key, amount_paise=amount_paise, tx_date=tx_date,
                       cash_id=cash_id, particulars=particulars.strip(), party_id=party_id,
                       finance_id=finance_id, new_party=new_party, new_finance=new_finance,
                       interest_paise=interest_paise, category_id=category_id,
                       method=method, external_ref=external_ref, notes=notes, transfer_to=transfer_to)
        if place_name.strip(): request['place_name'] = place_name.strip()
        fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        with self.db.atomic():
            existing = self.db.one('SELECT * FROM posting_groups WHERE idempotency_key=?', (idempotency_key,))
            if existing:
                if existing['intake_fingerprint'] != fingerprint:
                    raise ValueError('This submission key was already used for different values.')
                return existing['id']
            if new_party is not None:
                name = str(new_party.get('name', '')).strip()
                if self.db.one('SELECT id FROM parties WHERE lower(trim(name))=lower(?)', (name,)):
                    raise ValueError('A party with this name already exists. Select that party or enter a distinct name.')
                party_id = self.save_party(new_party)
            if new_finance is not None:
                terms = dict(new_finance)
                if terms.pop('module', spec.module) != spec.module:
                    raise ValueError('New account module must match the transaction category.')
                if not terms.get('reference', '').strip():
                    terms['reference'] = spec.module.upper() + '-' + uuid.uuid4().hex[:10].upper()
                terms.setdefault('start_date', tx_date)
                finance_id = self.add_finance(party_id=party_id, module=spec.module, **terms)
            if spec.module and not finance_id:
                raise ValueError('Select a matching finance account or choose Create new account in this form.')
            if type_key.startswith('general') and category_id is None:
                kind = 'income' if spec.direction == 1 else 'expense'
                category = self.db.one('SELECT id FROM categories WHERE kind=? ORDER BY id LIMIT 1', (kind,))
                if not category:
                    raise ValueError('Add an income/expense heading in Settings first.')
                category_id = category['id']
            components = [(type_key, amount_paise)]
            if interest_paise:
                components.append(('loan_interest', interest_paise))
            return self.post(tx_date=tx_date, components=components, cash_id=cash_id,
                             idempotency_key=idempotency_key, party_id=party_id,
                             finance_id=finance_id, category_id=category_id, method=method,
                             external_ref=external_ref, notes=notes, transfer_to=transfer_to,
                             particulars=particulars.strip(), intake_fingerprint=fingerprint, place_name=place_name.strip())

    def post(self, *, tx_date, components, cash_id, idempotency_key, party_id=None, finance_id=None, category_id=None, method='cash', external_ref='', notes='', transfer_to=None, particulars='', intake_fingerprint='', place_name='', entry_name='', allow_unallocated=False):
        valid_date(tx_date)
        if not components or not idempotency_key or method not in METHODS:
            raise ValueError('Choose a transaction type, payment method and a submission key.')
        if len(components) > 2:
            raise ValueError('At most two linked payment components are allowed.')
        payload = dict(tx_date=tx_date,components=components,cash_id=cash_id,party_id=party_id,finance_id=finance_id,category_id=category_id,method=method,external_ref=external_ref,notes=notes,transfer_to=transfer_to,particulars=particulars,intake_fingerprint=intake_fingerprint)
        if place_name.strip(): payload['place_name'] = place_name.strip()
        if entry_name.strip(): payload['entry_name'] = entry_name.strip()
        if allow_unallocated: payload['allow_unallocated'] = True
        fingerprint = hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        with self.db.atomic():
            existing = self.db.one('SELECT * FROM posting_groups WHERE idempotency_key=?', (idempotency_key,))
            if existing:
                if existing['fingerprint'] != fingerprint:
                    raise ValueError('This submission key was already used for different values.')
                return existing['id']
            cash = self.db.one('SELECT * FROM cash_accounts WHERE id=? AND active=1', (cash_id,))
            if not cash or tx_date < cash['opening_date']:
                raise ValueError('Select an active cash/bank account whose opening date is on or before the transaction date.')
            finance = None
            if finance_id:
                finance = self.db.one('SELECT * FROM finance_accounts WHERE id=?', (finance_id,))
                if not finance or finance['status'] == 'closed':
                    raise ValueError('Account is closed or missing. Explicitly reopen it before posting.')
                if tx_date < finance['start_date']:
                    raise ValueError('Transaction date precedes the finance account start date.')
                if party_id and party_id != finance['party_id']:
                    raise ValueError('Party does not match the finance account.')
                party_id = finance['party_id']
            if party_id and not self.db.one('SELECT id FROM parties WHERE id=?', (party_id,)):
                raise ValueError('Party not found.')
            types = [c[0] for c in components]
            if len(types) != len(set(types)):
                raise ValueError('Duplicate component types are not allowed.')
            if len(types) == 2 and set(types) != {'loan_repaid','loan_interest'}:
                raise ValueError('Only a loan receipt may split principal and interest in one posting.')
            if transfer_to:
                if types != ['transfer_out'] or transfer_to == cash_id or finance_id or party_id or category_id:
                    raise ValueError('A transfer requires two different payment accounts and no finance, party or category.')
                target = self.db.one('SELECT * FROM cash_accounts WHERE id=? AND active=1', (transfer_to,))
                if not target or tx_date < target['opening_date']:
                    raise ValueError('Transfer destination is unavailable on this date.')
            group_id = str(uuid.uuid4())
            self.db.conn.execute('INSERT INTO posting_groups(id,reference,idempotency_key,fingerprint,tx_date,method,external_ref,notes,created_by,created_at,particulars,intake_fingerprint,place_name,entry_name) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (group_id, 'TX-'+uuid.uuid4().hex[:12].upper(),idempotency_key,fingerprint,tx_date,method,external_ref,notes,getpass.getuser(),timestamp(),particulars,intake_fingerprint,place_name.strip(),entry_name.strip()))
            for type_key, amount in components:
                self._integer(amount)
                spec = TYPES.get(type_key)
                if not spec:
                    raise ValueError('Unknown transaction type.')
                if spec.module:
                    if (not finance and not allow_unallocated) or (finance and spec.module != finance['module']):
                        raise ValueError('Transaction type does not match the linked finance account.')
                    if category_id:
                        raise ValueError('Finance entries cannot have a general income/expense category.')
                elif finance:
                    raise ValueError('This transaction type cannot link a finance account.')
                if type_key.startswith('transfer') and not transfer_to:
                    raise ValueError('Use an internal transfer with a destination account.')
                if type_key.startswith('general'):
                    category = self.db.one('SELECT * FROM categories WHERE id=?', (category_id,))
                    if not category or category['kind'] != ('income' if spec.direction == 1 else 'expense'):
                        raise ValueError('Choose a matching income or expense category.')
                self._entry(group_id,cash_id,party_id,finance_id,category_id,type_key,amount,1)
                if transfer_to:
                    self._entry(group_id,transfer_to,None,None,None,'transfer_in',amount,1)
            if finance:
                self._validate_principal_timeline(finance_id)
            self.db.audit('transaction',group_id,'post',after=payload)
        return group_id

    def _entry(self, group_id, cash_id, party_id, finance_id, category_id, type_key, amount, factor):
        spec = TYPES[type_key]
        self.db.conn.execute('INSERT INTO entries(group_id,cash_id,party_id,finance_id,category_id,type,amount_paise,direction,principal_delta,interest,factor) VALUES(?,?,?,?,?,?,?,?,?,?,?)', (group_id,cash_id,party_id,finance_id,category_id,type_key,amount,spec.direction,spec.principal,int(spec.interest),factor))

    def edit_entry(self, group_id, *, name, place_name, amount_paise, direction,
                   type_key, tx_date, reason, idempotency_key, interest_paise=0, transfer_to=None):
        """Atomic, audit-preserving correction effective on the chosen correction date."""
        valid_date(tx_date); self._integer(amount_paise)
        self._integer(interest_paise,positive=False)
        spec=TYPES.get(type_key)
        if not spec or direction!=('IN' if spec.direction==1 else 'OUT'):
            raise ValueError('Choose Transaction details matching IN/OUT.')
        if not reason.strip(): raise ValueError('Enter a reason for the edit.')
        request=dict(original=group_id,name=name.strip(),place_name=place_name.strip(),
                     amount_paise=amount_paise,direction=direction,type_key=type_key,tx_date=tx_date,
                     reason=reason.strip(),interest_paise=interest_paise,transfer_to=transfer_to)
        fingerprint=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
        with self.db.atomic():
            existing=self.db.one('SELECT id FROM posting_groups WHERE idempotency_key=?',(idempotency_key,))
            if existing:
                audit=self.db.one("SELECT after_json FROM audit_log WHERE entity='transaction' AND entity_id=? AND action='edit'",(existing['id'],))
                if audit and json.loads(audit['after_json']).get('fingerprint')==fingerprint: return existing['id']
                raise ValueError('This submission key was already used for different values.')
            original=self.db.one('SELECT * FROM posting_groups WHERE id=?',(group_id,))
            if not original or original['reversal_of'] or self.db.one('SELECT id FROM posting_groups WHERE reversal_of=?',(group_id,)):
                raise ValueError('Only a current original entry can be edited. Open its latest replacement instead.')
            if tx_date<original['tx_date']: raise ValueError('Edit date cannot precede the original entry.')
            entries=self.db.all('SELECT * FROM entries WHERE group_id=? ORDER BY id',(group_id,))
            main=next((e for e in entries if not e['interest'] and e['type']!='transfer_in'),entries[0])
            transfer=main['type']=='transfer_out'
            if transfer!=(type_key=='transfer_out'):
                raise ValueError('Keep linked transfers as transfers; reverse and enter separately to change their kind.')
            if interest_paise<0 or (interest_paise and type_key!='loan_repaid'):
                raise ValueError('A linked interest amount requires STL LOAN CREDIT.')
            if len(entries)==2 and not transfer and type_key!='loan_repaid':
                raise ValueError('Keep the split receipt as STL LOAN CREDIT or reverse it and enter separate components.')
            self._pending_edit_checks=set()
            try:
                reversal=self.reverse(group_id,tx_date,'Edit: '+reason.strip(),idempotency_key+'-reversal')
                if transfer:
                    target=transfer_to or next(e['cash_id'] for e in entries if e['type']=='transfer_in')
                    replacement=self.post(tx_date=tx_date,components=[('transfer_out',amount_paise)],cash_id=main['cash_id'],
                        transfer_to=target,idempotency_key=idempotency_key,method=original['method'],
                        entry_name=name.strip(),place_name=place_name.strip(),notes=original['notes'])
                elif spec.module==TYPES[main['type']].module:
                    category_id=main['category_id']
                    if type_key.startswith('general'):
                        category=self.db.one('SELECT id FROM categories WHERE kind=? ORDER BY id LIMIT 1',('income' if spec.direction==1 else 'expense',))
                        if not category: raise ValueError('Add a matching income/expense heading first.')
                        category_id=category['id']
                    components=[(type_key,amount_paise)]+([('loan_interest',interest_paise)] if interest_paise else [])
                    replacement=self.post(tx_date=tx_date,components=components,cash_id=main['cash_id'],
                        finance_id=main['finance_id'],party_id=main['party_id'],category_id=category_id,
                        idempotency_key=idempotency_key,method=original['method'],external_ref=original['external_ref'],
                        notes=original['notes'],particulars=original['particulars'],entry_name=name.strip(),place_name=place_name.strip(),
                        allow_unallocated=bool(spec.module and main['finance_id'] is None))
                else:
                    replacement=self.post_quick_entry(name=name,place_name=place_name,amount_paise=amount_paise,
                        direction=direction,type_key=type_key,tx_date=tx_date,cash_id=main['cash_id'],idempotency_key=idempotency_key)
                pending=self._pending_edit_checks
            finally:
                del self._pending_edit_checks
            for account_id in pending: self._validate_principal_timeline(account_id)
            self.db.audit('transaction',replacement,'edit',before={'original':group_id},
                          after=request | {'reversal':reversal,'replacement':replacement,'fingerprint':fingerprint})
            return replacement

    def reverse(self, group_id, tx_date, reason, idempotency_key):
        valid_date(tx_date)
        if not reason.strip() or not idempotency_key:
            raise ValueError('A reversal reason and submission key are required.')
        with self.db.atomic():
            original = self.db.one('SELECT * FROM posting_groups WHERE id=?', (group_id,))
            if not original or original['reversal_of']:
                raise ValueError('Only an original posting can be reversed.')
            if tx_date < original['tx_date']:
                raise ValueError('Reversal date cannot precede the original transaction.')
            existing = self.db.one('SELECT * FROM posting_groups WHERE idempotency_key=?', (idempotency_key,))
            if existing:
                if existing['reversal_of'] == group_id and existing['tx_date'] == tx_date and existing['notes'] == reason:
                    return existing['id']
                raise ValueError('Submission key already used.')
            if self.db.one('SELECT id FROM posting_groups WHERE reversal_of=?', (group_id,)):
                raise ValueError('This posting has already been reversed.')
            entries = self.db.all('SELECT * FROM entries WHERE group_id=?', (group_id,))
            finance_ids = {e['finance_id'] for e in entries if e['finance_id']}
            for account_id in finance_ids:
                if self.db.one('SELECT status FROM finance_accounts WHERE id=?', (account_id,))['status'] == 'closed':
                    raise ValueError('Reopen the closed finance account before reversing.')
            reversal_id = str(uuid.uuid4())
            self.db.conn.execute('INSERT INTO posting_groups(id,reference,idempotency_key,fingerprint,tx_date,method,notes,reversal_of,created_by,created_at,particulars,place_name,entry_name) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (reversal_id,'RV-'+uuid.uuid4().hex[:12].upper(),idempotency_key,group_id,tx_date,original['method'],reason,group_id,getpass.getuser(),timestamp(),original['particulars'],original['place_name'],original['entry_name']))
            for e in entries:
                self._entry(reversal_id,e['cash_id'],e['party_id'],e['finance_id'],e['category_id'],e['type'],e['amount_paise'],-1)
            for account_id in finance_ids:
                self._validate_principal_timeline(account_id)
            self.db.audit('transaction',reversal_id,'reverse',after={'original':group_id,'reason':reason})
        return reversal_id

    def entries(self, start='0001-01-01', end='9999-12-31', **filters):
        valid_date(start); valid_date(end)
        if start > end:
            raise ValueError('Start date must be on or before end date.')
        where, args = ['g.tx_date BETWEEN ? AND ?'], [start,end]
        for key, column in {'party_id':'e.party_id','finance_id':'e.finance_id','cash_id':'e.cash_id','type':'e.type','category_id':'e.category_id','module':ENTRY_MODULE_SQL,'status':'f.status'}.items():
            if filters.get(key) not in (None,''):
                where.append(column+'=?'); args.append(filters[key])
        query = f'''SELECT e.*, g.reference,g.tx_date,g.method,g.external_ref,g.notes,g.particulars,g.place_name,g.created_by,g.created_at,g.reversal_of,
        COALESCE(NULLIF(g.entry_name,''),p.name) party_name,f.reference finance_reference,{ENTRY_MODULE_SQL} module,f.status,c.name cash_name,cat.name category_name,
        (SELECT r.reference FROM posting_groups r WHERE r.reversal_of=g.id) reversed_by
        FROM entries e JOIN posting_groups g ON g.id=e.group_id
        LEFT JOIN parties p ON p.id=e.party_id LEFT JOIN finance_accounts f ON f.id=e.finance_id
        JOIN cash_accounts c ON c.id=e.cash_id LEFT JOIN categories cat ON cat.id=e.category_id WHERE '''
        return self.db.all(query+' AND '.join(where)+' ORDER BY g.tx_date,g.created_at,e.id',args)

    def estimate(self, account_id, start, end):
        valid_date(start); valid_date(end)
        if start > end:
            raise ValueError('Estimate start date must precede end date.')
        account = self.db.one('SELECT * FROM finance_accounts WHERE id=?', (account_id,))
        if not account:
            raise ValueError('Finance account not found.')
        start = max(start, account['start_date'])
        if start > end:
            return {'paise':0,'start':start,'end':end,'principal_days':0,'rate':account['annual_rate']}
        balance = self.principal(account_id,start)
        cursor = date.fromisoformat(start)
        principal_days = 0
        events = self.db.all('SELECT g.tx_date,SUM(e.amount_paise*e.principal_delta*e.factor) delta FROM entries e JOIN posting_groups g ON g.id=e.group_id WHERE e.finance_id=? AND g.tx_date>? AND g.tx_date<? GROUP BY g.tx_date ORDER BY g.tx_date', (account_id,start,end))
        for event in events:
            day = date.fromisoformat(event['tx_date'])
            principal_days += balance * (day-cursor).days
            balance += event['delta']; cursor = day
        principal_days += balance * (date.fromisoformat(end)-cursor).days
        return {'paise':interest_paise(principal_days, account['annual_rate']), 'start':start,'end':end,'principal_days':principal_days,'rate':account['annual_rate']}

    def dashboard(self, start, end):
        rows = [r for r in self.entries(start,end) if not r['type'].startswith('transfer')]
        result = {'amount_in':0,'amount_out':0,'interest_received':0,'interest_paid':0,'general_income':0,'general_expense':0,'fd_interest':0,'other_interest':0,'hand_interest':0}
        for row in rows:
            amount = row['amount_paise']*row['factor']
            result['amount_in' if row['direction']==1 else 'amount_out'] += amount
            if row['interest']:
                result['interest_received' if row['direction']==1 else 'interest_paid'] += amount
                if row['direction']==-1:
                    result[{'fd':'fd_interest','other':'other_interest','hand_taken':'hand_interest'}[row['module']]] += amount
            if row['type'].startswith('general'):
                result[row['type']] += amount
        result['net_cash'] = result['amount_in']-result['amount_out']
        result['net_interest'] = result['interest_received']-result['interest_paid']
        result['principal'] = {module:sum(self.principal(a['id'],end) for a in self.finance_accounts() if a['module']==module) for module in MODULES}
        result['cash'] = sum(self.cash_balance(a['id'],end) for a in self.cash_accounts())
        return result
