"""Run on a desktop (Windows or macOS): python scripts/gui_smoke.py.
Uses a temporary demo database, not production data. Tests real Tk widgets.
"""
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
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
        def no_dialog(title,message,**kwargs):
            errors.append((title,message))
        def forms():
            return [w for w in app.winfo_children() if isinstance(w,Form)]
        def close_popups():
            for w in app.winfo_children():
                if isinstance(w,tk.Toplevel): w.destroy()
            app.update()
        with patch('finance_ledger.ui.messagebox.showerror',no_dialog):
            for page in app.PAGES:
                app.show(page); app.update()
                assert not errors,errors
                print('PAGE OK:',page)
            app.show('Dashboard')
            for action in [app.party_form,lambda:app.finance_form('fd'),app.cash_form,app.transaction_form,lambda:app.transaction_form('transfer_out'),lambda:app.edit_finance(1),lambda:app.estimate_form(2),app.category_form]:
                action(); app.update()
                assert forms(),'Expected an input form'
                assert forms()[0].winfo_height()<=app.winfo_screenheight(), 'Form does not fit screen'
                close_popups()
            # A failed save retains entered values and shows an inline error.
            app.transaction_form(); app.update()
            form=forms()[0]
            form.fields['amount'].insert(0,'100')
            form.submit()
            assert form.winfo_exists()
            assert form.fields['amount'].get()=='100'
            assert form.error.cget('text')
            # Complete a real split payment through the desktop form.
            form.fields['date'].delete(0,'end'); form.fields['date'].insert(0,'2026-10-18')
            form.fields['finance'].select_key(2)
            form.fields['interest'].delete(0,'end'); form.fields['interest'].insert(0,'10')
            form.submit(); app.update()
            assert not forms(),'Successful transaction form should close'
            latest=app.ledger.entries()[-2:]
            assert {r['type'] for r in latest}=={'loan_repaid','loan_interest'}
            assert len({r['group_id'] for r in latest})==1
            for action in [lambda:app.party_detail(1),lambda:app.finance_detail(1),lambda:app.cash_detail(1),lambda:app.transaction_detail(latest[0]['group_id']),app.audit_window]:
                action(); app.update(); close_popups()
            assert not errors,errors
        print('GUI SMOKE PASSED: 10 pages, entry forms, validation retention, split posting, details, audit.')
        app.close()


if __name__=='__main__':
    run()
