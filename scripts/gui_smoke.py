"""Desktop smoke check using temporary demo data; never production records."""
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from finance_ledger.categories import CATEGORY_REPORTS
from finance_ledger.demo import seed_demo
from finance_ledger.storage import Database
from finance_ledger.ui import Application, Form


def run():
    with tempfile.TemporaryDirectory() as directory:
        db=Database(directory)
        seed_demo(db)
        app=Application(db,demo=True)
        app.update()
        errors=[]
        app.report_callback_exception=lambda kind,value,trace:errors.append(str(value))
        def no_dialog(title,message,**kwargs):
            errors.append((title,message))
        def forms():
            return [w for w in app.winfo_children() if isinstance(w,Form)]
        def close_popups():
            for w in app.winfo_children():
                if isinstance(w,tk.Toplevel): w.destroy()
            app.update()
        def put(form,key,value):
            field=form.fields[key]; field.delete(0,'end'); field.insert(0,value)
        with patch('finance_ledger.ui.messagebox.showerror',no_dialog):
            for page in app.PAGES:
                app.show(page); app.update()
                assert not errors,errors
                print('PAGE OK:',page)
            for key,name in CATEGORY_REPORTS.items():
                app.report_nav.selection_set(key)
                app.report_nav.event_generate('<<TreeviewSelect>>'); app.update()
                assert app.page=='Reports'
                assert app.report_name.get()==name
                from finance_ledger.reports import build_report
                compact=build_report(app.ledger,name,app.start,app.end)
                assert compact.columns[:6]==['Date','Name','Place Name','Transaction Details','Amount In','Amount Out']
                assert len(compact.columns)==7
                assert app.report_type.selected() is None
                assert str(app.report_type.cget('state'))=='disabled'
                assert not forms(),'A report menu must not create an entry form'
                assert not errors,errors
            print('REPORT MENUS OK:',len(CATEGORY_REPORTS))
            app.report_search.set('Fixed'); app.update()
            assert app.report_nav.exists('fd') and not app.report_nav.exists('stl')
            app.report_search.set(''); app.update()
            assert all(app.report_nav.exists(key) for key in CATEGORY_REPORTS)
            app.show('Dashboard')
            for action in [app.party_form,lambda:app.finance_form('fd'),app.cash_form,app.transaction_form,lambda:app.transaction_form('transfer_out'),lambda:app.edit_finance(1),lambda:app.estimate_form(2),app.category_form]:
                action(); app.update()
                assert forms(),'Expected an input form'
                assert forms()[0].winfo_height()<=app.winfo_screenheight(),'Form does not fit screen'
                close_popups()
            # Only five inputs exist. Name is a plain Entry, with no selectors or hidden advanced controls.
            form=app.transaction_form(); app.update()
            assert list(form.fields)==['party','place_name','amount','direction','type']
            assert type(form.fields['party']) is ttk.Entry
            assert all(field.winfo_ismapped() for field in form.fields.values())
            form.fields['direction'].buttons['IN'].invoke(); app.update()
            assert form.fields['direction'].get()=='IN'
            assert 'STL LOAN DEBIT' not in form.fields['type'].cget('values')
            assert 'STL LOAN CREDIT' in form.fields['type'].cget('values')
            form.fields['direction'].buttons['OUT'].invoke(); app.update()
            assert 'STL LOAN CREDIT' not in form.fields['type'].cget('values')
            close_popups()
            # New name/account creation is automatic and atomic; invalid input retains all five values.
            form=app.transaction_form('fd_received'); app.update()
            put(form,'party','GUI New Depositor'); put(form,'place_name','Salem'); put(form,'amount','-1')
            count=len(app.ledger.parties()); form.submit(); app.update()
            assert forms() and len(app.ledger.parties())==count
            assert form.fields['place_name'].get()=='Salem'
            put(form,'amount','1000'); form.submit(); app.update(); assert not forms()
            entry=next(r for r in app.ledger.entries() if r['party_name']=='GUI New Depositor')
            assert entry['place_name']=='Salem' and entry['type']=='fd_received'
            assert app.ledger.principal(entry['finance_id'])==100000
            # An existing borrower is resolved from plain text, including case-insensitive matching.
            form=app.transaction_form('loan_repaid'); app.update()
            put(form,'party','ravi kumar'); put(form,'amount','100'); form.submit(); app.update()
            assert not forms(),'Existing principal receipt must save'
            receipt=next(r for r in app.ledger.entries() if r['party_name']=='ravi kumar')
            assert receipt['finance_id']==2 and receipt['type']=='loan_repaid'
            form=app.transaction_form('loan_interest'); app.update()
            put(form,'party','Ravi Kumar'); put(form,'amount','10'); form.submit(); app.update(); assert not forms()
            # Expense Name is free text, with no fabricated party or finance account.
            count=len(app.ledger.parties())
            form=app.transaction_form('general_expense'); app.update()
            put(form,'party','Water Can'); put(form,'place_name','Chennai'); put(form,'amount','200')
            form.submit(); app.update(); assert not forms()
            assert len(app.ledger.parties())==count
            expense=next(r for r in app.ledger.entries() if r['party_name']=='Water Can')
            assert expense['party_id'] is None and expense['place_name']=='Chennai'
            app.show('Cash Book'); app.update()
            app.tx_search.insert(0,'Water Can'); app.filter_transactions()
            assert len(app.tx_rows)==1 and app.tx_rows[0]['type']=='general_expense'
            app.clear_transactions(); app.tx_search.insert(0,'Chennai'); app.filter_transactions()
            assert len(app.tx_rows)==1
            app.toggle_transaction_filters(); app.update(); assert app.tx_min.winfo_ismapped()
            app.tx_sort.set('Amount high to low'); app.filter_transactions()
            assert expense['id'] in app.tx_balances
            app.clear_transactions(); app.update(); assert len(app.tx_rows)>1
            for action in [lambda:app.party_detail(1),lambda:app.finance_detail(1),lambda:app.cash_detail(1),lambda:app.transaction_detail(receipt['group_id']),app.audit_window]:
                action(); app.update(); close_popups()
            # Edit from the list, retain form data on failure, then post a linked correction.
            app.show('Cash Book'); app.update()
            app.tx_tree.selection_set(str(expense['id']))
            form=app.edit_selected_entry(); app.update()
            assert form.fields['party'].get()=='Water Can'
            put(form,'party','Water Can Refill'); put(form,'amount','250')
            before=len(app.ledger.entries()); cash_before=app.ledger.cash_balance(1)
            form.submit(); app.update()
            assert forms() and len(app.ledger.entries())==before
            assert form.fields['amount'].get()=='250' and 'reason' in form.error.cget('text')
            put(form,'reason','Correct the bill amount'); form.submit(); app.update(); assert not forms()
            replacement=next(r for r in app.ledger.entries() if r['party_name']=='Water Can Refill' and r['factor']==1)
            assert replacement['amount_paise']==25000 and replacement['place_name']=='Chennai'
            assert len(app.ledger.entries())==before+2
            assert app.ledger.cash_balance(1)==cash_before-5000
            app.transaction_detail(replacement['group_id']); app.update(); close_popups()
            try: app.edit_entry_form(expense['group_id'])
            except ValueError as exc: assert 'latest replacement' in str(exc)
            else: raise AssertionError('An already replaced entry cannot be edited again')
            # Transfers retain a dedicated linked-transfer form outside daily entry.
            form=app.transfer_form(); app.update()
            put(form,'amount','5'); form.fields['cash'].select_key(1); form.fields['target'].select_key(2)
            form.submit(); app.update(); assert not forms()
            form=app.transaction_form('loan_disbursed'); app.update()
            put(form,'party','Ravi Kumar'); put(form,'amount','100'); form.fields['direction'].set('IN')
            before=len(app.ledger.entries()); form.submit(); app.update()
            assert forms() and len(app.ledger.entries())==before
            assert 'matching IN/OUT' in form.error.cget('text')
            assert form.fields['amount'].get()=='100'
            close_popups()
            assert not errors,errors
        print('GUI SMOKE PASSED: six pages, eight reports, five-field text-name entry, direction buttons, automatic finance matching, free-text expenses, retention, audited editing, transfers and search.')
        app.close()


if __name__=='__main__':
    run()
