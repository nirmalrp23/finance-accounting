from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from finance_ledger.categories import CATEGORY_REPORTS, TRANSACTION_DETAILS
from finance_ledger.ledger import Ledger, TYPES
from finance_ledger.reports import CASHBOOK_REPORT, build_report, cashbook_balances, export_report
from finance_ledger.schema import APPLICATION_ID, MIGRATIONS
from finance_ledger.storage import Database


class CashbookCase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Database(self.temp.name,daily=False)
        self.ledger=Ledger(self.db)
        self.cash=self.ledger.add_cash('Cash','cash',10_000_000,'2026-01-01')
        self.request=dict(type_key='loan_disbursed',amount_paise=1_000_000,tx_date='2026-01-02',cash_id=self.cash,idempotency_key='intake-1',new_party={'name':'New borrower','phone':'1234567890'},new_finance={'reference':'STL-001','annual_rate':'12'},particulars='Business loan')

    def tearDown(self):
        self.db.close(); self.temp.cleanup()

    def test_inline_party_account_and_posting_are_atomic(self):
        group=self.ledger.post_cashbook(**self.request)
        entry=self.ledger.entries()[0]
        self.assertEqual(entry['group_id'],group)
        self.assertEqual(entry['particulars'],'Business loan')
        self.assertEqual(entry['party_name'],'New borrower')
        self.assertEqual(entry['finance_reference'],'STL-001')
        self.assertEqual(self.ledger.principal(entry['finance_id'],'2026-01-31'),1_000_000)
        self.assertEqual(self.ledger.cash_balance(self.cash,'2026-01-31'),9_000_000)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM audit_log')['n'],4)

    def test_entry_place_is_independent_audited_reversible_and_backed_up(self):
        request=self.request | {'place_name':'  Salem  '}
        group=self.ledger.post_cashbook(**request)
        self.assertEqual(self.ledger.post_cashbook(**request),group)
        with self.assertRaisesRegex(ValueError,'different values'):
            self.ledger.post_cashbook(**(request | {'place_name':'Chennai'}))
        self.assertEqual(self.ledger.entries()[0]['place_name'],'Salem')
        self.assertEqual(self.ledger.parties()[0]['address'],'')
        self.assertIn('Salem',self.db.one("SELECT after_json FROM audit_log WHERE entity='transaction' AND action='post'")['after_json'])
        self.ledger.reverse(group,'2026-01-03','Wrong entry','place-reverse')
        self.assertEqual([r['place_name'] for r in self.ledger.entries()],['Salem','Salem'])
        report=build_report(self.ledger,CATEGORY_REPORTS['stl'],'2026-01-01','2026-01-31')
        self.assertEqual([r[2] for r in report.rows[1:-1]],['Salem','Salem'])
        backup=Path(self.temp.name)/'with-place.sqlite3'
        self.db.backup(backup); self.db.restore(backup)
        self.assertEqual([r['place_name'] for r in self.ledger.entries()],['Salem','Salem'])

    def test_failed_posting_rolls_back_party_account_and_audits(self):
        request=self.request | {'type_key':'loan_repaid'}
        with self.assertRaisesRegex(ValueError,'negative'):
            self.ledger.post_cashbook(**request)
        for table in ('parties','finance_accounts','posting_groups','entries'):
            self.assertEqual(self.db.one(f'SELECT COUNT(*) n FROM {table}')['n'],0)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM audit_log')['n'],1)
        # The same form can be corrected and submitted using its original key.
        self.ledger.post_cashbook(**self.request)
        self.assertEqual(len(self.ledger.entries()),1)

    def test_retry_does_not_create_duplicate_names_or_accounts(self):
        group=self.ledger.post_cashbook(**self.request)
        self.assertEqual(self.ledger.post_cashbook(**self.request),group)
        self.assertEqual(len(self.ledger.parties()),1)
        self.assertEqual(len(self.ledger.finance_accounts()),1)
        self.assertEqual(len(self.ledger.entries()),1)
        with self.assertRaisesRegex(ValueError,'different values'):
            self.ledger.post_cashbook(**(self.request | {'particulars':'Altered'}))
        self.assertEqual(len(self.ledger.parties()),1)

    def test_existing_party_new_account_and_split_receipt(self):
        party=self.ledger.save_party({'name':'Existing borrower'})
        request=self.request | {'type_key':'loan_repaid','new_party':None,'party_id':party,'new_finance':{'reference':'OLD-STL','opening_paise':1_000_000},'amount_paise':200_000,'interest_paise':2000}
        group=self.ledger.post_cashbook(**request)
        entries=self.ledger.entries()
        self.assertEqual(len(entries),2)
        self.assertEqual({r['group_id'] for r in entries},{group})
        self.assertEqual(self.ledger.principal(entries[0]['finance_id'],'2026-01-31'),800_000)
        self.assertEqual(self.ledger.dashboard('2026-01-01','2026-01-31')['interest_received'],2000)
        self.ledger.reverse(group,'2026-01-03','Wrong receipt','reversal')
        self.assertTrue(all(r['particulars']=='Business loan' for r in self.ledger.entries()))
        self.assertEqual(self.ledger.principal(entries[0]['finance_id'],'2026-01-31'),1_000_000)

    def test_office_particulars_are_not_fictitious_parties(self):
        self.ledger.post_cashbook(type_key='general_expense',amount_paise=20_000,tx_date='2026-01-02',cash_id=self.cash,idempotency_key='expense',particulars='Water Can')
        self.assertEqual(self.ledger.parties(),[])
        row=self.ledger.entries()[0]
        self.assertEqual(row['particulars'],'Water Can')
        self.assertIsNone(row['party_id'])
        self.assertEqual(row['direction'],-1)
        report=build_report(self.ledger,CATEGORY_REPORTS['general_expense'],'2026-01-01','2026-01-31')
        self.assertEqual(report.rows[1][1],'Water Can')
        self.assertEqual(report.rows[-1][5],20_000)
        for suffix in ('.csv','.xlsx','.pdf'):
            export_report(report,Path(self.temp.name)/('office'+suffix))

    def test_reject_ambiguous_new_and_existing_selections(self):
        self.ledger.post_cashbook(**self.request)
        entry=self.ledger.entries()[0]
        variants=[{'party_id':entry['party_id']},{'finance_id':entry['finance_id']},{'new_finance':{'module':'fd'}},{'type_key':'general_income'},{'interest_paise':100}]
        for changes in variants:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.ledger.post_cashbook(**(self.request | {'idempotency_key':'invalid'} | changes))
        self.assertEqual(len(self.ledger.entries()),1)

    def test_duplicate_party_name_requires_existing_selection(self):
        self.ledger.save_party({'name':'New borrower'})
        with self.assertRaisesRegex(ValueError,'already exists'):
            self.ledger.post_cashbook(**self.request)
        self.assertEqual(len(self.ledger.parties()),1)
        self.assertEqual(self.ledger.finance_accounts(),[])

    def test_all_finance_families_use_correct_accounting(self):
        types=['fd_received','loan_disbursed','other_received','hand_given_disbursed','hand_taken_received']
        for index,key in enumerate(types):
            with self.subTest(type=key):
                self.ledger.post_cashbook(**(self.request | {'type_key':key,'idempotency_key':key,'new_party':{'name':key},'new_finance':{}}))
                row=self.ledger.entries()[-1]
                self.assertEqual(row['direction'],TYPES[key].direction)
                self.assertEqual(row['module'],TYPES[key].module)
                self.assertTrue(row['finance_reference'])
        self.assertEqual(len(self.ledger.finance_accounts()),5)

    def test_combined_reports_include_debit_credit_interest_without_double_counting(self):
        self.ledger.post_cashbook(**self.request)
        account=self.ledger.entries()[0]['finance_id']
        self.ledger.post_cashbook(type_key='loan_repaid',amount_paise=100_000,interest_paise=1000,tx_date='2026-01-03',cash_id=self.cash,idempotency_key='receipt',finance_id=account,particulars='Receipt')
        self.ledger.post_cashbook(type_key='general_expense',amount_paise=500,tx_date='2026-01-03',cash_id=self.cash,idempotency_key='office',particulars='Water')
        report=build_report(self.ledger,CATEGORY_REPORTS['stl'],'2026-01-01','2026-01-31',module='fd')
        self.assertEqual(len(report.rows),5)
        self.assertEqual(report.rows[-1][4:7],[101_000,1_000_000,-899_000])
        self.assertEqual(report.rows[2][4],100_000)  # principal repayment
        self.assertEqual(report.rows[3][4],1000)  # interest, included once
        self.assertEqual(report.rows[3][3],'STL INTEREST CREDIT')
        feb=build_report(self.ledger,CATEGORY_REPORTS['stl'],'2026-02-01','2026-02-28')
        self.assertEqual(feb.rows[0][6],-899_000)
        self.assertEqual(feb.rows[-1][6],-899_000)
        for key,name in CATEGORY_REPORTS.items():
            result=build_report(self.ledger,name,'2026-01-01','2026-01-31')
            self.assertTrue(all(len(r)==len(result.columns) for r in result.rows))
        self.assertEqual(len(CATEGORY_REPORTS),8)
        self.assertEqual(set(TRANSACTION_DETAILS),set(TYPES)-{'transfer_in'})

    def test_report_type_filter_matches_each_option_and_keeps_filtered_opening(self):
        from finance_ledger.categories import REPORT_TYPE_CHOICES
        self.ledger.post_cashbook(**self.request)
        account=self.ledger.entries()[0]['finance_id']
        self.ledger.post_cashbook(type_key='loan_repaid',amount_paise=100_000,interest_paise=1000,
            tx_date='2026-01-03',cash_id=self.cash,finance_id=account,idempotency_key='filter-receipt')
        self.assertEqual(len(REPORT_TYPE_CHOICES),12)
        self.assertEqual(REPORT_TYPE_CHOICES[0],(None,'All transaction'))
        for key,label in REPORT_TYPE_CHOICES[1:]:
            report=build_report(self.ledger,CASHBOOK_REPORT,'2026-01-01','2026-01-31',type=key)
            self.assertTrue(all(r[3]==TRANSACTION_DETAILS[key] for r in report.rows[1:-1]),label)
        filtered=build_report(self.ledger,CATEGORY_REPORTS['stl'],'2026-01-01','2026-01-31',type='loan_repaid')
        self.assertEqual(len(filtered.rows),3)
        self.assertEqual(filtered.rows[-1][4:7],[100_000,0,100_000])
        later=build_report(self.ledger,CATEGORY_REPORTS['stl'],'2026-01-04','2026-01-31',type='loan_repaid')
        self.assertEqual(later.rows[0][-1],100_000)
        self.assertEqual(later.rows[-1][-1],100_000)
        all_rows=build_report(self.ledger,CATEGORY_REPORTS['stl'],'2026-01-01','2026-01-31',type=None)
        self.assertEqual(len(all_rows.rows),5)

    def test_compact_report_columns_and_export_keep_location_and_balances(self):
        from openpyxl import load_workbook
        self.ledger.post_cashbook(**(self.request | {'place_name':'Salem'}))
        expected=['Date','Name','Place Name','Transaction Details','Amount In','Amount Out']
        for title in (CASHBOOK_REPORT,*CATEGORY_REPORTS.values(),'Overall Amount In / Amount Out'):
            with self.subTest(report=title):
                report=build_report(self.ledger,title,'2026-01-01','2026-01-31')
                self.assertEqual(report.columns[:6],expected)
                self.assertEqual(len(report.columns),7)
                self.assertTrue(all(len(row)==7 for row in report.rows))
                self.assertEqual(report.money_columns,{4,5,6})
        report=build_report(self.ledger,CATEGORY_REPORTS['stl'],'2026-01-01','2026-01-31')
        self.assertEqual(report.rows[1][1:4],['New borrower','Salem','STL LOAN DEBIT'])
        self.assertEqual(report.rows[-1][4:7],[0,1_000_000,-1_000_000])
        path=Path(self.temp.name)/'compact.xlsx'; export_report(report,path)
        workbook=load_workbook(path); sheet=workbook.active
        self.assertEqual(sheet.max_column,7)
        self.assertEqual(sheet['C6'].value,'Salem')
        self.assertEqual(sheet['F7'].value,10000)
        self.assertEqual(sheet['G7'].value,-10000)
        self.assertTrue(sheet['G7'].font.bold)
        workbook.close()

    def test_excel_cashbook_has_typed_dates_money_and_reference_layout(self):
        from datetime import datetime
        from openpyxl import load_workbook
        self.ledger.post_cashbook(**self.request)
        report=build_report(self.ledger,CATEGORY_REPORTS['stl'],'2026-01-01','2026-01-31')
        path=Path(self.temp.name)/'combined.xlsx'
        export_report(report,path)
        workbook=load_workbook(path); sheet=workbook.active
        self.assertEqual([sheet.cell(4,i).value for i in range(1,8)],report.columns)
        self.assertEqual(sheet['F6'].value,10000)
        self.assertEqual(sheet['G7'].value,-10000)
        self.assertIsInstance(sheet['A6'].value,datetime)
        self.assertEqual(sheet['A6'].number_format,'dd.mm.yyyy')
        self.assertEqual(sheet.freeze_panes,'E6')
        self.assertEqual(sheet['F6'].border.bottom.style,'thin')
        workbook.close()

    def test_each_finance_report_keeps_interest_direction_and_reversals(self):
        families=[('stl','loan_disbursed','loan_repaid','loan_interest',1),
                  ('fd','fd_received','fd_repaid','fd_interest',-1),
                  ('external','other_received','other_repaid','other_interest',-1),
                  ('hand_given','hand_given_disbursed','hand_given_repaid','hand_given_interest',1),
                  ('hand_taken','hand_taken_received','hand_taken_repaid','hand_taken_interest',-1)]
        for key,initial,repayment,interest,direction in families:
            with self.subTest(family=key):
                self.ledger.post_cashbook(**(self.request | {'type_key':initial,'idempotency_key':key,'new_party':{'name':key},'new_finance':{'reference':key}}))
                account=next(a['id'] for a in self.ledger.finance_accounts() if a['reference']==key)
                group=self.ledger.post_cashbook(type_key=repayment,amount_paise=100_000,tx_date='2026-01-03',cash_id=self.cash,idempotency_key=key+'-repay',finance_id=account)
                interest_group=self.ledger.post_cashbook(type_key=interest,amount_paise=1000,tx_date='2026-01-03',cash_id=self.cash,idempotency_key=key+'-interest',finance_id=account)
                self.ledger.reverse(group,'2026-02-01','Correction',key+'-reverse')
                self.ledger.reverse(interest_group,'2026-02-01','Correction',key+'-reverse-interest')
                jan=build_report(self.ledger,CATEGORY_REPORTS[key],'2026-01-01','2026-01-31')
                feb=build_report(self.ledger,CATEGORY_REPORTS[key],'2026-02-01','2026-02-28')
                self.assertEqual(len(jan.rows),5)
                self.assertEqual({r[3] for r in jan.rows[1:-1]}, {TRANSACTION_DETAILS[t] for t in (initial,repayment,interest)})
                self.assertEqual(sum(r[4]-r[5] for r in jan.rows[1:-1] if 'INTEREST' in r[3]),1000*direction)
                self.assertEqual(sum(r[4]-r[5] for r in feb.rows[1:-1] if 'INTEREST' in r[3]),-1000*direction)
                self.assertEqual(feb.rows[0][6],jan.rows[-1][6])
                self.assertEqual(feb.rows[-1][6],-1_000_000*direction)
                scoped=build_report(self.ledger,CATEGORY_REPORTS[key],'2026-01-01','2026-01-31',finance_id=account)
                self.assertEqual(scoped.rows,jan.rows)

    def test_running_cash_stays_chronological_and_includes_opening(self):
        self.ledger.post_cashbook(**self.request)
        self.ledger.post_cashbook(type_key='general_expense',amount_paise=1000,tx_date='2026-01-03',cash_id=self.cash,idempotency_key='rent',particulars='Rent')
        report=build_report(self.ledger,CASHBOOK_REPORT,'2026-01-01','2026-01-31')
        self.assertEqual(report.rows[-1][6],8_999_000)
        self.assertEqual(report.rows[-1][5],1_001_000)
        opening,closing,balances=cashbook_balances(self.ledger,'2026-01-03','2026-01-31')
        self.assertEqual((opening,closing),(9_000_000,8_999_000))
        self.assertEqual(balances[self.ledger.entries()[-1]['id']],8_999_000)
        historical=build_report(self.ledger,CASHBOOK_REPORT,'2026-01-01','2026-01-02')
        self.assertEqual(historical.rows[-1][6],9_000_000)

    def test_category_report_reversals_do_not_rewrite_previous_period(self):
        group=self.ledger.post_cashbook(**self.request)
        self.ledger.reverse(group,'2026-02-01','Correction','reverse')
        january=build_report(self.ledger,CATEGORY_REPORTS['stl'],'2026-01-01','2026-01-31')
        february=build_report(self.ledger,CATEGORY_REPORTS['stl'],'2026-02-01','2026-02-28')
        self.assertEqual(january.rows[-1][5],1_000_000)
        self.assertEqual(february.rows[-1][5],-1_000_000)
        self.assertEqual(february.rows[1][1],'New borrower')
        self.assertTrue(february.rows[1][3].startswith('Reversal:'))


class QuickEntryCase(unittest.TestCase):
    setUp=CashbookCase.setUp
    tearDown=CashbookCase.tearDown
    def quick(self,**changes):
        values=dict(name='Quick borrower',place_name='Salem',amount_paise=100_000,direction='OUT',type_key='loan_disbursed',tx_date='2026-01-02',cash_id=self.cash,idempotency_key='quick')
        return self.ledger.post_quick_entry(**(values | changes))

    def test_quick_entry_is_atomic_idempotent_and_retains_typed_name(self):
        group=self.quick()
        self.assertEqual(self.quick(),group)
        self.assertEqual(len(self.ledger.parties()),1)
        self.assertEqual(len(self.ledger.finance_accounts()),1)
        with self.assertRaisesRegex(ValueError,'different values'): self.quick(place_name='Chennai')
        party=self.ledger.parties()[0]
        self.ledger.save_party({'name':'Renamed borrower'},party['id'])
        self.assertEqual(self.ledger.entries()[0]['party_name'],'Quick borrower')
        self.ledger.reverse(group,'2026-01-03','Correction','quick-reverse')
        self.assertEqual([r['party_name'] for r in self.ledger.entries()],['Quick borrower','Quick borrower'])
        self.assertEqual([r['place_name'] for r in self.ledger.entries()],['Salem','Salem'])
        backup=Path(self.temp.name)/'quick.sqlite3'; self.db.backup(backup); self.db.restore(backup)
        self.assertEqual(len(self.ledger.entries()),2)
        self.assertEqual(self.ledger.entries()[0]['party_name'],'Quick borrower')

    def test_failed_quick_post_does_not_leave_unused_master_records(self):
        with self.assertRaisesRegex(ValueError,'opening date'): self.quick(tx_date='2025-12-31')
        self.assertEqual(self.ledger.parties(),[])
        self.assertEqual(self.ledger.finance_accounts(),[])
        self.assertEqual(self.ledger.entries(),[])
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM audit_log')['n'],1)

    def test_expense_name_is_free_text_without_a_party(self):
        self.quick(name='Water Can',direction='OUT',type_key='general_expense')
        self.assertEqual(self.ledger.parties(),[])
        entry=self.ledger.entries()[0]
        self.assertEqual(entry['party_name'],'Water Can')
        self.assertIsNone(entry['party_id'])
        report=build_report(self.ledger,CATEGORY_REPORTS['general_expense'],'2026-01-01','2026-01-31')
        self.assertEqual(report.rows[1][1],'Water Can')
        from openpyxl import load_workbook
        path=Path(self.temp.name)/'quick.xlsx'; export_report(report,path)
        workbook=load_workbook(path)
        self.assertEqual(workbook.active['B6'].value,'Water Can'); workbook.close()

    def test_unique_existing_account_receives_principal_and_interest(self):
        self.quick()
        self.quick(name='quick BORROWER',type_key='loan_repaid',direction='IN',amount_paise=10_000,idempotency_key='receipt')
        self.quick(type_key='loan_interest',direction='IN',amount_paise=1000,idempotency_key='interest')
        self.assertEqual(len(self.ledger.finance_accounts()),1)
        self.assertEqual(self.ledger.principal(1,'2026-01-31'),90_000)
        self.assertEqual(self.ledger.dashboard('2026-01-01','2026-01-31')['interest_received'],1000)

    def test_ambiguous_or_missing_accounts_never_guess_or_create_opening_debt(self):
        self.quick()
        self.ledger.add_finance('SECOND',1,'loan','2026-01-01')
        with self.assertRaisesRegex(ValueError,'More than one finance account'):
            self.quick(type_key='loan_repaid',direction='IN',idempotency_key='ambiguous')
        self.assertEqual(len(self.ledger.entries()),1)

    def test_missing_fd_history_saves_cash_movement_without_inventing_principal(self):
        group=self.quick(name='Nirmal',place_name='Karur',type_key='fd_repaid',direction='OUT',amount_paise=1_000_000)
        self.assertEqual(self.quick(name='Nirmal',place_name='Karur',type_key='fd_repaid',direction='OUT',amount_paise=1_000_000),group)
        entry=self.ledger.entries()[0]
        self.assertEqual((entry['party_name'],entry['place_name'],entry['module']),('Nirmal','Karur','fd'))
        self.assertIsNone(entry['finance_id'])
        self.assertEqual(self.ledger.finance_accounts(),[])
        self.assertEqual(self.ledger.cash_balance(self.cash,'2026-01-31'),9_000_000)
        report=build_report(self.ledger,CATEGORY_REPORTS['fd'],'2026-01-01','2026-01-31',module='fd')
        self.assertEqual(report.rows[-1][5],1_000_000)
        self.quick(name='Nirmal',type_key='fd_interest',direction='OUT',amount_paise=2000,idempotency_key='unlinked-interest')
        self.assertEqual(self.ledger.dashboard('2026-01-01','2026-01-31')['fd_interest'],2000)
        replacement=self.ledger.edit_entry(group,name='Nirmal',place_name='Karur',amount_paise=1_100_000,
            direction='OUT',type_key='fd_repaid',tx_date='2026-02-01',reason='Correct amount',idempotency_key='unlinked-edit')
        self.assertIsNone(next(r for r in self.ledger.entries() if r['group_id']==replacement)['finance_id'])
        self.assertEqual(self.ledger.cash_balance(self.cash,'2026-02-01'),8_898_000)
        self.ledger.reverse(replacement,'2026-02-02','Correction','unlinked-reverse')
        self.assertEqual(self.ledger.cash_balance(self.cash,'2026-02-02'),9_998_000)
        self.assertEqual(self.ledger.finance_accounts(),[])

    def test_direction_mismatch_does_not_write(self):
        with self.assertRaisesRegex(ValueError,'matching IN/OUT'): self.quick(direction='IN')
        self.assertEqual(self.ledger.entries(),[])


class EditEntryCase(unittest.TestCase):
    setUp=CashbookCase.setUp
    tearDown=CashbookCase.tearDown

    def prepare(self):
        group=self.ledger.post_cashbook(**self.request)
        account=self.ledger.entries()[0]['finance_id']
        self.ledger.post_cashbook(type_key='loan_repaid',amount_paise=900_000,tx_date='2026-01-03',cash_id=self.cash,finance_id=account,idempotency_key='repayment')
        return group,account

    def edit(self,group,**changes):
        values=dict(name='Corrected label',place_name='Chennai',amount_paise=1_200_000,direction='OUT',type_key='loan_disbursed',tx_date='2026-02-01',reason='Correct amount and label',idempotency_key='edit-1')
        return self.ledger.edit_entry(group,**(values | changes))

    def test_edit_is_linked_atomic_idempotent_and_historical(self):
        group,account=self.prepare()
        original=dict(self.db.one('SELECT * FROM posting_groups WHERE id=?',(group,)))
        replacement=self.edit(group)
        self.assertEqual(self.edit(group),replacement)
        self.assertEqual(self.db.one('SELECT * FROM posting_groups WHERE id=?',(group,)),original)
        self.assertEqual(self.ledger.principal(account,'2026-01-31'),100_000)
        self.assertEqual(self.ledger.principal(account,'2026-02-01'),300_000)
        january=build_report(self.ledger,CATEGORY_REPORTS['stl'],'2026-01-01','2026-01-31')
        february=build_report(self.ledger,CATEGORY_REPORTS['stl'],'2026-02-01','2026-02-28')
        self.assertEqual(january.rows[-1][-1],-100_000)
        self.assertEqual(february.rows[-1][-1],-300_000)
        reversal=self.db.one('SELECT * FROM posting_groups WHERE reversal_of=?',(group,))
        self.assertEqual(reversal['tx_date'],'2026-02-01')
        row=next(r for r in self.ledger.entries() if r['group_id']==replacement)
        self.assertEqual((row['party_name'],row['place_name'],row['finance_id']),('Corrected label','Chennai',account))
        self.assertIsNotNone(self.db.one("SELECT * FROM audit_log WHERE action='edit' AND entity_id=?",(replacement,)))
        with self.assertRaisesRegex(ValueError,'different values'): self.edit(group,place_name='Salem')
        with self.assertRaisesRegex(ValueError,'latest replacement'): self.edit(group,idempotency_key='second-edit')

    def test_invalid_final_principal_rolls_back_reversal_replacement_and_audit(self):
        group,account=self.prepare()
        counts=[self.db.one(f'SELECT COUNT(*) n FROM {table}')['n'] for table in ('posting_groups','entries','audit_log')]
        with self.assertRaisesRegex(ValueError,'negative'):
            self.edit(group,amount_paise=800_000)
        self.assertEqual([self.db.one(f'SELECT COUNT(*) n FROM {table}')['n'] for table in ('posting_groups','entries','audit_log')],counts)
        self.assertEqual(self.ledger.principal(account,'2026-02-01'),100_000)
        self.assertFalse(hasattr(self.ledger,'_pending_edit_checks'))
        self.edit(group)  # original key can be retried after correcting input

    def test_split_receipt_edit_keeps_both_components_and_actual_interest(self):
        self.ledger.post_cashbook(**self.request)
        account=self.ledger.entries()[0]['finance_id']
        group=self.ledger.post_cashbook(type_key='loan_repaid',amount_paise=100_000,interest_paise=1000,tx_date='2026-01-03',cash_id=self.cash,finance_id=account,idempotency_key='split')
        replacement=self.edit(group,type_key='loan_repaid',direction='IN',amount_paise=200_000,interest_paise=2000)
        self.assertEqual(len([r for r in self.ledger.entries() if r['group_id']==replacement]),2)
        self.assertEqual(self.ledger.principal(account,'2026-02-01'),800_000)
        self.assertEqual(self.ledger.dashboard('2026-01-01','2026-01-31')['interest_received'],1000)
        self.assertEqual(self.ledger.dashboard('2026-01-01','2026-02-28')['interest_received'],2000)

    def test_transfer_edit_keeps_linked_cash_balances(self):
        bank=self.ledger.add_cash('Bank','bank',0,'2026-01-01')
        group=self.ledger.post_cashbook(type_key='transfer_out',amount_paise=10_000,tx_date='2026-01-03',cash_id=self.cash,transfer_to=bank,idempotency_key='transfer')
        replacement=self.edit(group,type_key='transfer_out',direction='OUT',amount_paise=15_000,transfer_to=bank)
        self.assertEqual(len([r for r in self.ledger.entries() if r['group_id']==replacement]),2)
        self.assertEqual(self.ledger.cash_balance(bank,'2026-01-31'),10_000)
        self.assertEqual(self.ledger.cash_balance(bank,'2026-02-01'),15_000)
        self.assertEqual(self.ledger.cash_balance(self.cash,'2026-02-01'),9_985_000)

    def test_edit_requires_reason_and_valid_direction(self):
        group,_=self.prepare()
        with self.assertRaisesRegex(ValueError,'reason'): self.edit(group,reason='')
        with self.assertRaisesRegex(ValueError,'matching IN/OUT'): self.edit(group,direction='IN')
        with self.assertRaisesRegex(ValueError,'precede'): self.edit(group,tx_date='2026-01-01')


class VersionOneMigrationCase(unittest.TestCase):
    def test_old_database_and_backup_upgrade_preserve_every_posting(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ledger.sqlite3'
            with closing(sqlite3.connect(path)) as conn:
                conn.executescript(MIGRATIONS[0][1])
                conn.execute(f'PRAGMA application_id={APPLICATION_ID}')
                conn.execute('PRAGMA user_version=1')
                conn.execute("INSERT INTO cash_accounts(name,kind,opening_paise,opening_date) VALUES('Cash','cash',100000,'2026-01-01')")
                conn.execute("INSERT INTO parties(name,created_at,updated_at) VALUES('Old party','2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00')")
                conn.execute("INSERT INTO finance_accounts(reference,party_id,module,start_date,opening_paise,created_at) VALUES('OLD-FD',1,'fd','2026-01-01',0,'2026-01-01T00:00:00+00:00')")
                conn.execute("INSERT INTO posting_groups(id,reference,idempotency_key,fingerprint,tx_date,method,created_by,created_at) VALUES('old','TX-OLD','old-key','old-fingerprint','2026-01-02','cash','Old user','2026-01-02T00:00:00+00:00')")
                conn.execute("INSERT INTO entries(group_id,cash_id,party_id,finance_id,type,amount_paise,direction,principal_delta,interest,factor) VALUES('old',1,1,1,'fd_received',50000,1,1,0,1)")
                conn.commit()
            db=Database(folder,daily=False)
            try:
                ledger=Ledger(db)
                self.assertEqual(db.conn.execute('PRAGMA user_version').fetchone()[0],MIGRATIONS[-1][0])
                self.assertEqual(ledger.cash_balance(1,'2026-01-31'),150000)
                self.assertEqual(ledger.principal(1,'2026-01-31'),50000)
                self.assertEqual(ledger.entries()[0]['particulars'],'')
                backups=list((Path(folder)/'backups').glob('pre-migration-*.sqlite3'))
                self.assertEqual(len(backups),len(MIGRATIONS)-1)
                db.validate_backup(backups[0])
                ledger.post_cashbook(type_key='fd_interest',amount_paise=100,tx_date='2026-01-03',cash_id=1,finance_id=1,idempotency_key='new',particulars='Interest')
                self.assertEqual(len(ledger.entries()),2)
                db.restore(backups[0])
                self.assertEqual(len(ledger.entries()),1)
                self.assertEqual(ledger.principal(1,'2026-01-31'),50000)
                self.assertEqual(db.conn.execute('PRAGMA user_version').fetchone()[0],MIGRATIONS[-1][0])
            finally:
                db.close()
