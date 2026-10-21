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
                assert not forms(),'A report menu must not create an entry form'
                assert not errors,errors
            print('REPORT MENUS OK:',len(CATEGORY_REPORTS))
            app.report_search.set('FD'); app.update()
            assert app.report_nav.exists('fd_received') and not app.report_nav.exists('loan_disbursed')
            app.report_search.set(''); app.update()
            assert all(app.report_nav.exists(key) for key in CATEGORY_REPORTS)
            app.show('Dashboard')
            for action in [app.party_form,lambda:app.finance_form('fd'),app.cash_form,app.transaction_form,lambda:app.transaction_form('transfer_out'),lambda:app.edit_finance(1),lambda:app.estimate_form(2),app.category_form]:
                action(); app.update()
                assert forms(),'Expected an input form'
                assert forms()[0].winfo_height()<=app.winfo_screenheight(),'Form does not fit screen'
                close_popups()
            # Common-entry details stay compact; creation controls reveal fields in place.
            form=app.transaction_form(); app.update()
            def find_button(widget,phrase):
                for child in widget.winfo_children():
                    if isinstance(child,ttk.Button) and phrase in child.cget('text'): return child
                    found=find_button(child,phrase)
                    if found: return found
                return None
            assert not form.fields['notes'].winfo_ismapped()
            toggle=find_button(form,'Additional details'); assert toggle is not None
            toggle.invoke(); app.update(); assert form.fields['notes'].winfo_ismapped()
            new_name=find_button(form,'+ New name'); assert new_name is not None
            new_name.invoke(); app.update(); assert form.fields['party_name'].winfo_ismapped()
            find_button(form,'Use existing name').invoke(); app.update()
            assert not form.fields['party_name'].winfo_ismapped()
            close_popups()
            # Failed save retains data, then the same form posts an atomic split.
            form=app.transaction_form('loan_repaid'); app.update()
            put(form,'amount','100'); form.fields['finance'].set('')
            form.submit()
            assert form.winfo_exists() and form.fields['amount'].get()=='100'
            assert form.error.cget('text')
            put(form,'date','2026-10-18'); form.fields['finance'].select_key(2)
            put(form,'interest','10'); put(form,'particulars','Split receipt')
            form.submit(); app.update()
            assert not forms(),'Successful entry should close the form'
            latest=app.ledger.entries()[-2:]
            assert {r['type'] for r in latest}=={'loan_repaid','loan_interest'}
            assert len({r['group_id'] for r in latest})==1
            # New depositor, new FD and receipt are created in this same form.
            form=app.transaction_form('fd_received',new_party=True,new_finance=True); app.update()
            put(form,'party_name','GUI New Depositor')
            put(form,'account_reference','FD-GUI-NEW')
            put(form,'date','2026-10-18'); put(form,'account_date','2026-10-18')
            put(form,'amount','-1'); put(form,'particulars','New FD deposit')
            count=len(app.ledger.parties())
            form.submit(); app.update()
            assert form.winfo_exists()
            assert len(app.ledger.parties())==count
            put(form,'amount','1000'); form.submit(); app.update()
            assert not forms()
            assert len(app.ledger.parties())==count+1
            account=next(a for a in app.ledger.finance_accounts() if a['reference']=='FD-GUI-NEW')
            assert app.ledger.principal(account['id'],'2026-10-31')==100000
            # Office descriptions do not create parties or finance accounts.
            form=app.transaction_form('general_expense'); app.update()
            put(form,'date','2026-10-18'); put(form,'amount','200'); put(form,'particulars','Water Can')
            assert not form.fields['finance'].winfo_ismapped()
            form.submit(); app.update(); assert not forms()
            assert len(app.ledger.parties())==count+1
            expense=app.ledger.entries()[-1]
            assert expense['particulars']=='Water Can' and expense['party_id'] is None
            app.show('Cash Book'); app.update()
            app.tx_search.insert(0,'Water Can'); app.filter_transactions()
            assert len(app.tx_rows)==1 and app.tx_rows[0]['type']=='general_expense'
            app.toggle_transaction_filters(); app.update()
            assert app.tx_min.winfo_ismapped()
            app.tx_sort.set('Amount high to low'); app.filter_transactions()
            assert expense['id'] in app.tx_balances
            app.clear_transactions(); app.update(); assert len(app.tx_rows)>1
            for action in [lambda:app.party_detail(1),lambda:app.finance_detail(1),lambda:app.cash_detail(1),lambda:app.transaction_detail(latest[0]['group_id']),app.audit_window]:
                action(); app.update(); close_popups()
            assert not errors,errors
        print('GUI SMOKE PASSED: six pages, 18 report-only menus, unified form, atomic new party/account, split receipt, office particulars, search, audit.')
        app.close()


if __name__=='__main__':
    run()
