import csv
import json
import sqlite3
import tkinter as tk
import uuid
from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from . import __version__
from .ledger import Ledger, METHODS, MODULES, TYPES
from .money import money, paise, today, valid_date
from .reports import REPORT_NAMES, Report, build_report, export_report

BG = '#f3f6f4'
GREEN = '#175749'
INK = '#182d28'
MUTED = '#62746d'


class SearchCombo(ttk.Combobox):
    """Type to narrow choices. IDs are resolved from a selected exact label."""
    def __init__(self, master, choices, **kwargs):
        self.choices = choices
        self.labels = [label for _,label in choices]
        super().__init__(master, values=self.labels, **kwargs)
        self.bind('<KeyRelease>',self.filter)

    def filter(self, event=None):
        if event and event.keysym in ('Up','Down','Return','Tab','Escape'):
            return
        term = self.get().casefold()
        self.configure(values=[label for label in self.labels if term in label.casefold()])

    def selected(self, required=False):
        value = self.get().strip()
        for key,label in self.choices:
            if label == value:
                return key
        if value or required:
            raise ValueError('Select a matching value from the searchable list.')
        return None

    def select_key(self, key):
        for candidate,label in self.choices:
            if candidate == key:
                self.set(label); return
        self.set('')


class Form(tk.Toplevel):
    def __init__(self, parent, title, on_save, button='Save', help_text=''):
        super().__init__(parent)
        self.title(title); self.transient(parent.winfo_toplevel()); self.resizable(True,True)
        self.configure(bg='white'); self.on_save = on_save; self.fields = {}; self.row = 0
        self.canvas = tk.Canvas(self,background=BG,highlightthickness=0)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        scrollbar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        scrollbar.grid(row=0,column=1,sticky='ns')
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.body = ttk.Frame(self.canvas,padding=24)
        self.body_window=self.canvas.create_window((0,0),window=self.body,anchor='nw')
        self.body.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.body_window,width=e.width))
        self.columnconfigure(0,weight=1); self.rowconfigure(0,weight=1)
        self.body.columnconfigure(1,weight=1)
        ttk.Label(self.body,text=title,style='Title.TLabel').grid(row=self.row,column=0,columnspan=2,sticky='w',pady=(0,12)); self.row+=1
        if help_text:
            ttk.Label(self.body,text=help_text,wraplength=610,style='Muted.TLabel').grid(row=self.row,column=0,columnspan=2,sticky='w',pady=(0,12)); self.row+=1
        self.bottom = ttk.Frame(self,padding=(24,0,24,20)); self.bottom.grid(row=1,column=0,sticky='ew')
        self.error = ttk.Label(self.bottom,text='',foreground='#aa3030',wraplength=620)
        self.error.pack(fill='x',pady=(0,10))
        ttk.Button(self.bottom,text=button+'  (Ctrl+Enter)',command=self.submit,style='Primary.TButton').pack(side='right')
        ttk.Button(self.bottom,text='Cancel',command=self.destroy).pack(side='right',padx=8)
        self.bind('<Control-Return>',lambda e:self.submit())
        self.bind('<Escape>',lambda e:self.destroy())
        self.protocol('WM_DELETE_WINDOW',self.destroy)
        self.after(30,self._focus)

    def _focus(self):
        self.update_idletasks()
        height=min(self.winfo_screenheight()-100,self.body.winfo_reqheight()+self.bottom.winfo_reqheight()+12)
        self.geometry(f'760x{max(300,height)}')
        if self.fields:
            next(iter(self.fields.values())).focus_set()
        self.grab_set()

    def add(self,key,label,value='',choices=None,search=False,readonly=False):
        ttk.Label(self.body,text=label).grid(row=self.row,column=0,sticky='w',padx=(0,18),pady=5)
        if search:
            widget = SearchCombo(self.body,choices or [],width=48)
            if value is not None: widget.select_key(value)
        elif choices is not None:
            widget = ttk.Combobox(self.body,values=choices,state='readonly',width=48)
            widget.set(value if value!='' else (choices[0] if choices else ''))
        else:
            widget = ttk.Entry(self.body,width=51)
            widget.insert(0,str(value))
            if readonly: widget.configure(state='readonly')
        widget.grid(row=self.row,column=1,sticky='ew',pady=5)
        widget.bind('<FocusIn>',lambda event:self.after_idle(lambda:self._ensure_visible(widget)),add='+')
        self.fields[key] = widget; self.row+=1
        return widget

    def _ensure_visible(self,widget):
        if not widget.winfo_exists(): return
        top=self.canvas.canvasy(0); height=self.canvas.winfo_height(); body_height=max(1,self.body.winfo_height())
        y=widget.winfo_y(); bottom=y+widget.winfo_height()
        if y<top: self.canvas.yview_moveto(max(0,(y-12)/body_height))
        elif bottom>top+height: self.canvas.yview_moveto((bottom-height+12)/body_height)

    def note(self,text):
        label = ttk.Label(self.body,text=text,wraplength=610,style='Muted.TLabel')
        label.grid(row=self.row,column=0,columnspan=2,sticky='w',pady=(8,6)); self.row+=1
        return label

    def values(self):
        return {key:widget.get().strip() for key,widget in self.fields.items()}

    def submit(self):
        try:
            self.on_save(self)
        except (ValueError, sqlite3.Error, OSError, ImportError) as exc:
            self.error.configure(text=str(exc)); self.bell()
            return
        self.destroy()


def table(parent, columns, rows, money_cols=(), on_open=None, height=16, identifiers=None):
    frame = ttk.Frame(parent)
    frame.pack(fill='both',expand=True,pady=(8,0))
    ids = [f'c{i}' for i in range(len(columns))]
    tree = ttk.Treeview(frame,columns=ids,show='headings',height=height,selectmode='browse')
    scroll_y = ttk.Scrollbar(frame,orient='vertical',command=tree.yview)
    scroll_x = ttk.Scrollbar(frame,orient='horizontal',command=tree.xview)
    tree.configure(yscrollcommand=scroll_y.set,xscrollcommand=scroll_x.set)
    tree.grid(row=0,column=0,sticky='nsew'); scroll_y.grid(row=0,column=1,sticky='ns'); scroll_x.grid(row=1,column=0,sticky='ew')
    frame.columnconfigure(0,weight=1); frame.rowconfigure(0,weight=1)
    raw = {}
    for i,label in enumerate(columns):
        width = 155 if i in money_cols else (220 if any(term in label.lower() for term in ('name','type','notes','account')) else 150)
        tree.heading(ids[i],text=label)
        tree.column(ids[i],width=width,minwidth=90,anchor='e' if i in money_cols else 'w',stretch=True)
    for index,row in enumerate(rows):
        iid = str(identifiers[index]) if identifiers is not None else str(index)
        raw[iid] = row
        tree.insert('', 'end',iid=iid,values=[money(value) if i in money_cols and isinstance(value,int) else value for i,value in enumerate(row)],tags=('even' if index%2==0 else 'odd',))
    tree.tag_configure('even',background='#ffffff'); tree.tag_configure('odd',background='#f5f8f6')
    def sort_column(i, reverse=False):
        def key(iid):
            value = raw[iid][i]
            return (value is None,value if isinstance(value,(int,float)) else str(value or '').casefold())
        for index,iid in enumerate(sorted(tree.get_children(),key=key,reverse=reverse)):
            tree.move(iid,'',index)
        tree.heading(ids[i],command=lambda:sort_column(i,not reverse))
    for i in range(len(columns)):
        tree.heading(ids[i],command=lambda i=i:sort_column(i))
    if on_open:
        def opened(event=None):
            selection = tree.selection()
            if selection: on_open(selection[0])
        tree.bind('<Double-1>',opened); tree.bind('<Return>',opened)
    if not rows:
        ttk.Label(frame,text='No records match this view. Add a record or adjust the filters.',style='Muted.TLabel').grid(row=2,column=0,sticky='w',pady=10)
    return tree


class Application(tk.Tk):
    PAGES = ('Dashboard','Parties','Fixed Deposits','Loans','Other Finance','Hand Loans','Transactions','Cash & Bank','Reports','Settings')
    def __init__(self,database,demo=False):
        super().__init__()
        self.db = database; self.ledger = Ledger(database); self.demo = demo
        self.page = 'Dashboard'; self.start = today()[:8]+'01'; self.end = today()
        self.title('Finance Ledger'+(' — DEMO' if demo else '')); self.geometry('1280x820'); self.minsize(960,640)
        self.configure(bg=BG)
        self._style()
        self.sidebar = tk.Frame(self,bg=GREEN,width=205)
        self.sidebar.pack(side='left',fill='y'); self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar,text='▤  Finance Ledger',fg='white',bg=GREEN,font=('Segoe UI',17,'bold'),anchor='w').pack(fill='x',padx=18,pady=(28,3))
        tk.Label(self.sidebar,text='YOUR BUSINESS, IN BALANCE',fg='#b8d3c8',bg=GREEN,font=('Segoe UI',8),anchor='w').pack(fill='x',padx=18,pady=(0,28))
        self.nav = {}
        for page in self.PAGES:
            button = ttk.Button(self.sidebar,text=page,style='Nav.TButton',cursor='hand2',command=lambda page=page:self.show(page))
            button.pack(fill='x',padx=10,pady=2); self.nav[page]=button
        tk.Label(self.sidebar,text='●  OFFLINE  ·  SINGLE DEVICE\n\nINR / Asia/Kolkata\nv'+__version__,justify='left',fg='#b8d3c8',bg=GREEN,font=('Segoe UI',9),anchor='w').pack(side='bottom',fill='x',padx=20,pady=25)
        self.main = ttk.Frame(self,padding=(28,22)); self.main.pack(side='left',fill='both',expand=True)
        if demo:
            ttk.Label(self.main,text='DEMO WORKSPACE  ·  Sample records are stored separately from your real business.',background='#fff0c8',foreground='#806022',padding=10).pack(fill='x',pady=(0,12))
        header = ttk.Frame(self.main); header.pack(fill='x',pady=(0,20))
        self.heading = ttk.Label(header,text='Dashboard',style='Title.TLabel'); self.heading.pack(side='left')
        ttk.Button(header,text='+  Add Transaction',style='Primary.TButton',command=self.transaction_form).pack(side='right')
        self.status = ttk.Label(self.main,text='',style='Muted.TLabel'); self.status.pack(side='bottom',fill='x',pady=(12,0))
        self.content = ttk.Frame(self.main); self.content.pack(fill='both',expand=True)
        self.bind('<Control-n>',lambda e:self.transaction_form()); self.bind('<F5>',lambda e:self.show(self.page))
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.show('Dashboard')

    def _style(self):
        style = ttk.Style(self); style.theme_use('clam')
        style.configure('.',font=('Segoe UI',10),background=BG,foreground=INK)
        style.configure('TFrame',background=BG)
        style.configure('TLabel',background=BG)
        style.configure('Title.TLabel',font=('Segoe UI',23,'bold'),foreground=INK)
        style.configure('Section.TLabel',font=('Segoe UI',13,'bold'))
        style.configure('Muted.TLabel',foreground=MUTED,font=('Segoe UI',9))
        style.configure('TButton',padding=(13,8),background='#e6eee9',borderwidth=0)
        style.map('TButton',background=[('active','#d3e2d9')])
        style.configure('Primary.TButton',background=GREEN,foreground='white',font=('Segoe UI',10,'bold'))
        style.map('Primary.TButton',background=[('active','#267362'),('disabled','#99aaa3')])
        style.configure('Nav.TButton',background=GREEN,foreground='#e4eee9',font=('Segoe UI',10),padding=(14,11),anchor='w',borderwidth=0,relief='flat')
        style.map('Nav.TButton',background=[('active','#2d6d5c')],foreground=[('active','white')])
        style.configure('NavActive.TButton',background='#32725f',foreground='white',font=('Segoe UI',10,'bold'),padding=(14,11),anchor='w',borderwidth=0,relief='flat')
        style.map('NavActive.TButton',background=[('active','#3e816d')])
        style.configure('TEntry',padding=6,fieldbackground='white')
        style.configure('TCombobox',padding=5,fieldbackground='white')
        style.configure('Treeview',rowheight=34,background='white',fieldbackground='white',borderwidth=0,font=('Segoe UI',10))
        style.configure('Treeview.Heading',font=('Segoe UI',9,'bold'),padding=10,background='#e5ede8',foreground=MUTED)
        style.map('Treeview',background=[('selected',GREEN)],foreground=[('selected','white')])

    def close(self):
        self.db.close(); self.destroy()

    def guard(self,callback):
        try: return callback()
        except (ValueError,sqlite3.Error,OSError,ImportError) as exc:
            messagebox.showerror('Finance Ledger',str(exc),parent=self)

    def show(self,page):
        self.page = page
        for child in self.content.winfo_children(): child.destroy()
        for name,button in self.nav.items(): button.configure(style='NavActive.TButton' if name==page else 'Nav.TButton')
        self.heading.configure(text=page)
        self.status.configure(text=f'{self.business_name()}   ·   {"Demo" if self.demo else "Local records"}   ·   Ctrl+N: transaction   ·   F5: refresh')
        render = {'Dashboard':self.dashboard,'Parties':self.parties_page,'Cash & Bank':self.cash_page,'Transactions':self.transactions_page,'Reports':self.reports_page,'Settings':self.settings_page}.get(page)
        self.guard(render if render else self.finance_page)

    def business_name(self):
        return self.db.one("SELECT value FROM settings WHERE key='business_name'")['value']

    def toolbar(self,help_text='',buttons=()):
        bar = ttk.Frame(self.content); bar.pack(fill='x',pady=(0,12))
        if help_text: ttk.Label(bar,text=help_text,style='Muted.TLabel',wraplength=680).pack(side='left')
        for label,command in buttons:
            ttk.Button(bar,text=label,command=command).pack(side='right',padx=(8,0))
        return bar

    def date_bar(self,parent,callback):
        bar = ttk.Frame(parent); bar.pack(fill='x',pady=(0,12))
        ttk.Label(bar,text='Period').pack(side='left',padx=(0,8))
        a = ttk.Entry(bar,width=12); a.insert(0,self.start); a.pack(side='left')
        ttk.Label(bar,text=' to ').pack(side='left')
        b = ttk.Entry(bar,width=12); b.insert(0,self.end); b.pack(side='left',padx=(0,8))
        def apply():
            def work():
                valid_date(a.get()); valid_date(b.get())
                if a.get()>b.get(): raise ValueError('Start date must precede end date.')
                self.start=a.get(); self.end=b.get(); callback()
            self.guard(work)
        ttk.Button(bar,text='Apply dates',command=apply).pack(side='left')
        ttk.Label(bar,text='YYYY-MM-DD',style='Muted.TLabel').pack(side='left',padx=12)
        return bar

    def dashboard(self):
        self.date_bar(self.content,lambda:self.show('Dashboard'))
        stats = self.ledger.dashboard(self.start,self.end)
        cards = ttk.Frame(self.content); cards.pack(fill='x',pady=(2,16))
        primary = [('Amount In',stats['amount_in'],'Money received'),('Amount Out',stats['amount_out'],'Money paid'),('Net cash movement',stats['net_cash'],'Amount In − Amount Out'),('Cash & bank balance',stats['cash'],'As of '+self.end)]
        for index,(title,value,subtitle) in enumerate(primary):
            cards.columnconfigure(index,weight=1)
            card = tk.Frame(cards,bg='white',highlightbackground='#dde7e0',highlightthickness=1)
            card.grid(row=0,column=index,sticky='nsew',padx=(0,10 if index<3 else 0))
            tk.Label(card,text=title,bg='white',fg=MUTED,font=('Segoe UI',10),anchor='w').pack(fill='x',padx=16,pady=(16,6))
            tk.Label(card,text=money(value),bg='white',fg=GREEN,font=('Segoe UI',18,'bold'),anchor='w').pack(fill='x',padx=16)
            tk.Label(card,text=subtitle,bg='white',fg=MUTED,font=('Segoe UI',8),anchor='w').pack(fill='x',padx=16,pady=(7,16))
        ttk.Label(self.content,text='Net cash movement includes principal and is not profit. Internal transfers are excluded from Amount In / Out.',style='Muted.TLabel').pack(anchor='w',pady=(0,16))
        notebook = ttk.Notebook(self.content); notebook.pack(fill='both',expand=True)
        overview = ttk.Frame(notebook,padding=12); due = ttk.Frame(notebook,padding=12); activity=ttk.Frame(notebook,padding=12)
        notebook.add(overview,text='  Principal & interest  '); notebook.add(due,text='  Maturities & overdue  '); notebook.add(activity,text='  Recent activity  ')
        positions = [('FD principal owed',stats['principal']['fd'],'Liability'),('Loan principal outstanding',stats['principal']['loan'],'Receivable'),('Other finance principal owed',stats['principal']['other'],'Liability'),('Hand loans given',stats['principal']['hand_given'],'Receivable'),('Hand loans taken',stats['principal']['hand_taken'],'Liability'),('Interest received',stats['interest_received'],'Actual · selected period'),('FD interest paid',stats['fd_interest'],'Actual expense'),('Other finance interest paid',stats['other_interest'],'Actual expense'),('Hand loan interest paid',stats['hand_interest'],'Actual expense'),('Net interest income',stats['net_interest'],'Actual interest received − paid')]
        table(overview,['Position / measure','Amount','Basis'],positions,{1},height=11)
        horizon = (date.fromisoformat(self.end)+timedelta(days=30)).isoformat()
        upcoming = []
        for a in self.ledger.finance_accounts():
            outstanding = self.ledger.principal(a['id'],self.end)
            if a['due_date'] and outstanding>0 and (a['due_date']<self.end or (a['module']=='fd' and a['due_date']<=horizon)):
                upcoming.append([a['reference'],a['party_name'],a['due_date'],'Past recorded due date' if a['due_date']<self.end else 'FD maturity within 30 days',outstanding])
        table(due,['Reference','Party','Due / maturity','Attention','Outstanding principal'],upcoming,{4})
        recent = list(reversed(self.ledger.entries(self.start,self.end)))[:12]
        table(activity,['Date','Reference','Party','Transaction type','Amount'],[[r['tx_date'],r['reference'],r['party_name'] or '',('Reversal · ' if r['factor']==-1 else '')+TYPES[r['type']].label,r['amount_paise']*r['factor']] for r in recent],{4})

    def party_choices(self):
        return [(p['id'],f'{p["id"]} · {p["name"]}') for p in self.ledger.parties()]

    def finance_choices(self,module=None):
        return [(a['id'],f'{a["reference"]} · {a["party_name"]}') for a in self.ledger.finance_accounts() if not module or a['module']==module]

    def cash_choices(self):
        return [(a['id'],f'{a["id"]} · {a["name"]}') for a in self.ledger.cash_accounts()]

    def parties_page(self):
        self.toolbar('Double-click a party for linked accounts, principal totals and transaction history.',[('+ Add Party',self.party_form)])
        parties = self.ledger.parties()
        table(self.content,['Name','Phone','Roles','Email','Status'],[[p['name'],p['phone'],p['roles'],p['email'],'Active' if p['active'] else 'Inactive'] for p in parties],on_open=lambda iid:self.party_detail(int(iid)),identifiers=[p['id'] for p in parties])

    def party_form(self,party_id=None):
        p = self.db.one('SELECT * FROM parties WHERE id=?',(party_id,)) or {}
        def save(form):
            values=form.values(); values['active']=values['active']=='Active'
            self.ledger.save_party(values,party_id); self.show(self.page)
        form=Form(self,'Edit Party' if p else 'Add Party',save,help_text='One party may have several roles and multiple finance accounts. Comma-separate roles.')
        for key,label in [('name','Name *'),('phone','Phone'),('address','Address'),('email','Email (optional)'),('roles','Roles'),('notes','Notes')]: form.add(key,label,p.get(key,''))
        form.add('active','Status','Active' if p.get('active',1) else 'Inactive',choices=['Active','Inactive'])

    def party_detail(self,party_id):
        p=self.db.one('SELECT * FROM parties WHERE id=?',(party_id,))
        window=tk.Toplevel(self); window.title(p['name']+' · Party'); window.geometry('1050x700')
        head=ttk.Frame(window,padding=20); head.pack(fill='x')
        ttk.Label(head,text=p['name'],style='Title.TLabel').pack(side='left')
        ttk.Button(head,text='Edit party',command=lambda:self.party_form(party_id)).pack(side='right')
        ttk.Label(window,text=f'{p["phone"]}   {p["email"]}   {p["address"]}\nRoles: {p["roles"]}\n{p["notes"]}',padding=(20,0)).pack(anchor='w')
        tabs=ttk.Notebook(window); tabs.pack(fill='both',expand=True,padx=20,pady=20)
        linked=ttk.Frame(tabs,padding=10); history=ttk.Frame(tabs,padding=10)
        tabs.add(linked,text='Linked accounts & principal'); tabs.add(history,text='Transactions & interest')
        accounts=[a for a in self.ledger.finance_accounts() if a['party_id']==party_id]
        table(linked,['Reference','Module','Status','Principal as of '+self.end],[[a['reference'],MODULES[a['module']],a['status'],self.ledger.principal(a['id'],self.end)] for a in accounts],{3},on_open=lambda iid:self.finance_detail(int(iid)),identifiers=[a['id'] for a in accounts])
        report=build_report(self.ledger,'Party statement',self.start,self.end,party_id=party_id)
        self.report_widget(history,report)

    def finance_page(self):
        modules={'Fixed Deposits':{'fd'},'Loans':{'loan'},'Other Finance':{'other'},'Hand Loans':{'hand_given','hand_taken'}}[self.page]
        self.toolbar('Opening principal is a brought-forward balance only. Use Add Transaction for new money received or paid.',[('+ Open account',lambda:self.finance_form(next(iter(sorted(modules)))))])
        accounts=[a for a in self.ledger.finance_accounts() if a['module'] in modules]
        table(self.content,['Reference','Party','Module','Start date','Rate % p.a.','Due / maturity','Status','Principal outstanding'],[[a['reference'],a['party_name'],MODULES[a['module']],a['start_date'],a['annual_rate'],a['due_date'] or '—',a['status'].title(),self.ledger.principal(a['id'],today())] for a in accounts],{7},on_open=lambda iid:self.finance_detail(int(iid)),identifiers=[a['id'] for a in accounts])

    def finance_form(self,module):
        def save(form):
            v=form.values()
            selected_module=next(key for key,label in MODULES.items() if label==v['module'])
            self.ledger.add_finance(v['reference'],form.fields['party'].selected(True),selected_module,v['start_date'],paise(v['opening']),v['rate'],v['frequency'],v['due_date'] or None,v['notes'])
            self.show(self.page)
        form=Form(self,'Open Finance Account',save,help_text='Record the agreed terms. Opening principal does not create cash movement. For a new deposit or disbursement, leave opening principal at zero and post a transaction.')
        form.add('module','Module / direction *',MODULES[module],choices=list(MODULES.values()))
        form.add('reference','Unique reference *')
        form.add('party','Party *',None,choices=self.party_choices(),search=True)
        form.add('start_date','Opening / start date *',today())
        form.add('opening','Brought-forward principal (₹)','0.00')
        form.add('rate','Annual simple interest rate %','0')
        form.add('frequency','Interest payout frequency','Monthly',choices=['Monthly','Quarterly','Half-yearly','Yearly','At maturity','On demand','Interest-free'])
        form.add('due_date','Due / maturity date (optional)')
        form.add('notes','Notes')

    def finance_detail(self,account_id):
        a=self.db.one('SELECT f.*,p.name party_name FROM finance_accounts f JOIN parties p ON p.id=f.party_id WHERE f.id=?',(account_id,))
        window=tk.Toplevel(self); window.title(a['reference']); window.geometry('1100x720')
        head=ttk.Frame(window,padding=20); head.pack(fill='x')
        ttk.Label(head,text=a['reference']+'  ·  '+a['party_name'],style='Title.TLabel').pack(side='left')
        ttk.Button(head,text='Edit / reopen',command=lambda:self.edit_finance(account_id)).pack(side='right')
        ttk.Button(head,text='Interest estimate',command=lambda:self.estimate_form(account_id)).pack(side='right',padx=8)
        ttk.Label(window,text=f'{MODULES[a["module"]]}   |   {a["status"].upper()}   |   Agreed rate {a["annual_rate"]}% p.a.   |   Principal as of {self.end}: {money(self.ledger.principal(account_id,self.end))}',padding=(20,0)).pack(anchor='w')
        body=ttk.Frame(window,padding=20); body.pack(fill='both',expand=True)
        name={'fd':'Individual FD statement','loan':'Individual loan statement','other':'Other finance statement'}.get(a['module'],'Overall Amount In / Amount Out')
        report=build_report(self.ledger,name,self.start,self.end,finance_id=account_id)
        self.report_widget(body,report)

    def edit_finance(self,account_id):
        a=self.db.one('SELECT * FROM finance_accounts WHERE id=?',(account_id,))
        def save(form):
            v=form.values(); self.ledger.update_finance(account_id,v['status'],v['rate'],v['due_date'],v['frequency'],v['notes']); self.show(self.page)
        form=Form(self,'Edit '+a['reference'],save,help_text='Posted amounts and opening balances cannot be edited. Reopen explicitly before posting to a closed account. Rate changes affect estimates only; the previous rate is retained in audit history.')
        form.add('status','Status',a['status'],choices=['active','matured','closed'])
        form.add('rate','Annual rate %',a['annual_rate'])
        form.add('due_date','Due / maturity date',a['due_date'] or '')
        form.add('frequency','Payout frequency',a['frequency'],choices=['Monthly','Quarterly','Half-yearly','Yearly','At maturity','On demand','Interest-free'])
        form.add('notes','Notes',a['notes'])

    def estimate_form(self,account_id):
        def calculate(form):
            v=form.values(); result=self.ledger.estimate(account_id,v['start'],v['end'])
            output.configure(text=f'ESTIMATE ONLY: {money(result["paise"])}\nPeriod: {result["start"]} inclusive to {result["end"]} exclusive.\nFormula: sum(outstanding principal × days) × {result["rate"]}% ÷ 365.\nDated principal movements change subsequent daily balances.\nUses the current agreed rate for this entire calculation. No entry is posted.')
        form=Form(self,'Simple Interest Estimate',lambda f:None,button='Close',help_text='Actual interest is recorded manually. This estimate uses actual days/365 and is never included in posted interest reports.')
        form.add('start','Start date (inclusive)',self.start); form.add('end','End date (exclusive)',self.end)
        output=form.note('Choose dates and calculate.')
        ttk.Button(form.body,text='Calculate estimate',command=lambda:self.guard(lambda:calculate(form))).grid(row=form.row,column=1,sticky='e',pady=8)

    def cash_page(self):
        self.toolbar('Balances include opening balances and all linked transfers, as of today.',[('+ Add Cash / Bank',self.cash_form),('Transfer',lambda:self.transaction_form('transfer_out'))])
        accounts=self.ledger.cash_accounts()
        table(self.content,['Account name','Kind','Opening date','Opening balance','Current balance'],[[a['name'],a['kind'].title(),a['opening_date'],a['opening_paise'],self.ledger.cash_balance(a['id'])] for a in accounts],{3,4},on_open=lambda iid:self.cash_detail(int(iid)),identifiers=[a['id'] for a in accounts])

    def cash_form(self):
        def save(form):
            v=form.values(); self.ledger.add_cash(v['name'],v['kind'],paise(v['opening']),v['date'],v['notes']); self.show(self.page)
        form=Form(self,'Add Cash / Bank Account',save,help_text='An opening balance represents money already held as of the opening date. It does not count as period Amount In.')
        form.add('name','Account name *'); form.add('kind','Kind','cash',choices=['cash','bank']); form.add('opening','Opening balance (₹)','0.00'); form.add('date','Opening date',today()); form.add('notes','Notes')

    def cash_detail(self,cash_id):
        window=tk.Toplevel(self); window.title('Cash / Bank Ledger'); window.geometry('1100x700')
        body=ttk.Frame(window,padding=20); body.pack(fill='both',expand=True)
        self.report_widget(body,build_report(self.ledger,'Cash book / Bank ledger',self.start,self.end,cash_id=cash_id))

    def transaction_form(self,initial=None):
        if not self.ledger.cash_accounts():
            messagebox.showinfo('Add a payment account','Add a Cash or Bank account before posting a transaction.',parent=self); self.cash_form(); return
        key=str(uuid.uuid4())
        options={k:spec.label for k,spec in TYPES.items() if k!='transfer_in'}
        options['transfer_out']='Internal transfer between Cash / Bank'
        def save(form):
            v=form.values(); type_key=next(k for k,label in options.items() if label==v['type'])
            spec=TYPES[type_key]
            account=form.fields['finance'].selected(bool(spec.module)) if spec.module else None
            party=form.fields['party'].selected() if not spec.module and type_key!='transfer_out' else None
            category=form.fields['category'].selected(True) if type_key.startswith('general') else None
            target=form.fields['target'].selected(True) if type_key=='transfer_out' else None
            parts=[(type_key,paise(v['amount']))]
            if type_key=='loan_repaid' and paise(v['interest'])>0: parts.append(('loan_interest',paise(v['interest'])))
            if paise(v['interest'])<0: raise ValueError('Split interest cannot be negative.')
            self.ledger.post(tx_date=v['date'],components=parts,cash_id=form.fields['cash'].selected(True),idempotency_key=key,party_id=party,finance_id=account,category_id=category,method=v['method'],external_ref=v['external'],notes=v['notes'],transfer_to=target)
            self.show(self.page)
        form=Form(self,'Add Transaction',save,button='Post transaction',help_text='Direction is determined by the explicit transaction type. Tab moves between fields. Type in selectors to narrow results. Required fields are marked *.')
        type_widget=form.add('type','Transaction type *',options[initial or 'loan_repaid'],choices=list(options.values()))
        direction=form.note('')
        form.add('date','Transaction date *',today())
        finance=form.add('finance','Finance account',None,choices=self.finance_choices(),search=True)
        party=form.add('party','Party (general entry only)',None,choices=self.party_choices(),search=True)
        categories=self.db.all('SELECT * FROM categories ORDER BY name')
        category=form.add('category','Category (general entry)',None,choices=[(c['id'],f'{c["name"]} ({c["kind"]})') for c in categories],search=True)
        amount=form.add('amount','Amount / principal (₹) *','')
        interest=form.add('interest','Additional loan interest (₹)','0.00')
        cash=form.add('cash','Cash / Bank account *',self.ledger.cash_accounts()[0]['id'],choices=self.cash_choices(),search=True)
        target=form.add('target','Transfer destination',None,choices=self.cash_choices(),search=True)
        form.add('method','Payment method *','cash',choices=list(METHODS))
        form.add('external','External reference'); form.add('notes','Notes')
        def changed(event=None):
            selected=next(k for k,label in options.items() if label==type_widget.get()); spec=TYPES[selected]
            direction.configure(text='Linked Amount Out + Amount In · excluded from overall movement totals' if selected=='transfer_out' else ('Amount In · money received' if spec.direction==1 else 'Amount Out · money paid'))
            finance.configure(state='normal' if spec.module else 'disabled'); finance.set('')
            finance.choices=self.finance_choices(spec.module) if spec.module else []; finance.labels=[label for _,label in finance.choices]; finance.configure(values=finance.labels)
            party.configure(state='normal' if not spec.module and selected!='transfer_out' else 'disabled'); party.set('')
            category.configure(state='normal' if selected.startswith('general') else 'disabled'); category.set('')
            interest.configure(state='normal'); interest.delete(0,'end'); interest.insert(0,'0.00'); interest.configure(state='normal' if selected=='loan_repaid' else 'disabled')
            target.configure(state='normal' if selected=='transfer_out' else 'disabled'); target.set('')
        type_widget.bind('<<ComboboxSelected>>',changed); changed()

    def transactions_page(self):
        self.toolbar('Double-click a row for its audit details or to reverse every linked component.',[('Export filtered CSV',lambda:self.guard(self.export_transactions))])
        self.date_bar(self.content,lambda:self.show('Transactions'))
        filters=ttk.Frame(self.content); filters.pack(fill='x',pady=(0,6))
        self.tx_search=ttk.Entry(filters,width=26); self.tx_search.pack(side='left',padx=(0,6)); self.tx_search.insert(0,'')
        ttk.Label(filters,text='Search reference, party, notes, type',style='Muted.TLabel').pack(side='left')
        self.tx_min=ttk.Entry(filters,width=11); self.tx_min.pack(side='right',padx=4)
        ttk.Label(filters,text='Min ₹').pack(side='right')
        self.tx_max=ttk.Entry(filters,width=11); self.tx_max.pack(side='right',padx=4)
        ttk.Label(filters,text='Max ₹').pack(side='right')
        selectors=ttk.Frame(self.content); selectors.pack(fill='x',pady=6)
        self.tx_cash=SearchCombo(selectors,[(None,'All payment accounts')]+self.cash_choices(),width=18); self.tx_cash.select_key(None); self.tx_cash.pack(side='left',padx=(0,6))
        self.tx_party=SearchCombo(selectors,[(None,'All parties')]+self.party_choices(),width=18); self.tx_party.select_key(None); self.tx_party.pack(side='left',padx=6)
        self.tx_type=SearchCombo(selectors,[(None,'All types')]+[(k,s.label) for k,s in TYPES.items()],width=22); self.tx_type.select_key(None); self.tx_type.pack(side='left',padx=6)
        cats=self.db.all('SELECT * FROM categories ORDER BY name')
        self.tx_category=SearchCombo(selectors,[(None,'All categories')]+[(c['id'],c['name']) for c in cats],width=18); self.tx_category.select_key(None); self.tx_category.pack(side='left',padx=6)
        bar=ttk.Frame(self.content); bar.pack(fill='x',pady=8)
        ttk.Button(bar,text='Apply filters',command=lambda:self.guard(self.filter_transactions)).pack(side='left')
        ttk.Label(bar,text='Sort all filtered rows by',style='Muted.TLabel').pack(side='left',padx=(14,5))
        self.tx_sort=ttk.Combobox(bar,values=['Newest first','Oldest first','Amount low to high','Amount high to low','Party','Reference'],state='readonly',width=19); self.tx_sort.set('Newest first'); self.tx_sort.pack(side='left')
        self.tx_sort.bind('<<ComboboxSelected>>',lambda e:self.guard(self.filter_transactions))
        self.tx_info=ttk.Label(bar,text='',style='Muted.TLabel'); self.tx_info.pack(side='right')
        self.tx_body=ttk.Frame(self.content); self.tx_body.pack(fill='both',expand=True)
        pagination=ttk.Frame(self.content); pagination.pack(fill='x',pady=(12,0))
        ttk.Button(pagination,text='← Previous',command=lambda:self.tx_move(-1)).pack(side='left')
        ttk.Button(pagination,text='Next →',command=lambda:self.tx_move(1)).pack(side='left',padx=8)
        ttk.Label(pagination,text='50 entries per page · linked split components share a reference',style='Muted.TLabel').pack(side='right')
        self.tx_search.bind('<Return>',lambda e:self.guard(self.filter_transactions))
        self.filter_transactions()

    def filter_transactions(self):
        rows=self.ledger.entries(self.start,self.end,cash_id=self.tx_cash.selected(),party_id=self.tx_party.selected(),type=self.tx_type.selected(),category_id=self.tx_category.selected())
        term=self.tx_search.get().casefold().strip()
        minimum=paise(self.tx_min.get()) if self.tx_min.get().strip() else None
        maximum=paise(self.tx_max.get()) if self.tx_max.get().strip() else None
        if minimum is not None and maximum is not None and minimum>maximum: raise ValueError('Minimum amount exceeds maximum.')
        self.tx_rows=[r for r in rows if (not term or term in ' '.join(str(r.get(k) or '') for k in ('reference','external_ref','party_name','finance_reference','notes','category_name')).casefold() or term in TYPES[r['type']].label.casefold()) and (minimum is None or r['amount_paise']>=minimum) and (maximum is None or r['amount_paise']<=maximum)]
        sorting=self.tx_sort.get()
        if sorting in ('Newest first','Oldest first'): self.tx_rows.sort(key=lambda r:(r['tx_date'],r['created_at'],r['id']),reverse=sorting=='Newest first')
        elif sorting.startswith('Amount'): self.tx_rows.sort(key=lambda r:r['amount_paise'],reverse=sorting=='Amount high to low')
        elif sorting=='Party': self.tx_rows.sort(key=lambda r:(r['party_name'] or '').casefold())
        else: self.tx_rows.sort(key=lambda r:r['reference'])
        self.tx_page=0; self.render_transactions()

    def tx_move(self,delta):
        if 0<=self.tx_page+delta<max(1,(len(self.tx_rows)+49)//50): self.tx_page+=delta; self.render_transactions()

    def render_transactions(self):
        for child in self.tx_body.winfo_children(): child.destroy()
        rows=self.tx_rows[self.tx_page*50:self.tx_page*50+50]
        table(self.tx_body,['Date','Reference','Party / account','Transaction type','Amount In','Amount Out','Cash / Bank'],[[r['tx_date'],r['reference'],r['party_name'] or r['finance_reference'] or '',('Reversal: ' if r['factor']==-1 else '')+TYPES[r['type']].label,r['amount_paise']*r['factor'] if r['direction']==1 else 0,r['amount_paise']*r['factor'] if r['direction']==-1 else 0,r['cash_name']] for r in rows],{4,5},identifiers=[r['id'] for r in rows],on_open=lambda iid:self.transaction_detail(next(r['group_id'] for r in rows if r['id']==int(iid))))
        self.tx_info.configure(text=f'{len(self.tx_rows)} entries · page {self.tx_page+1} / {max(1,(len(self.tx_rows)+49)//50)}')

    def export_transactions(self):
        self.filter_transactions()
        report=Report('Filtered Transactions',f'{self.start} to {self.end}', ['Date','Reference','Party','Finance account','Type','Amount In','Amount Out','Cash / Bank','Method','External reference','Notes','Created by','Created at UTC','Reversal of'],[[r['tx_date'],r['reference'],r['party_name'] or '',r['finance_reference'] or '',TYPES[r['type']].label,r['amount_paise']*r['factor'] if r['direction']==1 else 0,r['amount_paise']*r['factor'] if r['direction']==-1 else 0,r['cash_name'],r['method'],r['external_ref'],r['notes'],r['created_by'],r['created_at'],r['reversal_of'] or ''] for r in self.tx_rows],{5,6})
        self.save_report(report,'.csv')

    def transaction_detail(self,group_id):
        group=self.db.one('SELECT * FROM posting_groups WHERE id=?',(group_id,))
        rows=[r for r in self.ledger.entries() if r['group_id']==group_id]
        window=tk.Toplevel(self); window.title(group['reference']); window.geometry('1000x540')
        body=ttk.Frame(window,padding=20); body.pack(fill='both',expand=True)
        ttk.Label(body,text=group['reference'],style='Title.TLabel').pack(anchor='w')
        ttk.Label(body,text=f'Date: {group["tx_date"]}   Method: {group["method"]}\nCreated by {group["created_by"]} at {group["created_at"]} (UTC)\nExternal reference: {group["external_ref"]}\nNotes: {group["notes"]}\nReversal of: {group["reversal_of"] or "—"}',wraplength=900).pack(anchor='w',pady=12)
        table(body,['Type','Finance account','Cash / Bank','Amount','Factor'],[[TYPES[r['type']].label,r['finance_reference'] or '',r['cash_name'],r['amount_paise'],r['factor']] for r in rows],{3},height=4)
        reversed_group=self.db.one('SELECT reference FROM posting_groups WHERE reversal_of=?',(group_id,))
        if reversed_group: ttk.Label(body,text='Reversed by '+reversed_group['reference'],foreground='#a23a30').pack(anchor='w',pady=10)
        elif not group['reversal_of']: ttk.Button(body,text='Reverse all linked components…',command=lambda:self.reversal_form(group_id,window)).pack(anchor='e',pady=12)

    def reversal_form(self,group_id,detail_window):
        key=str(uuid.uuid4())
        def save(form):
            v=form.values()
            valid_date(v['date'])
            if not v['reason']: raise ValueError('Enter a reason for the audit history.')
            if not messagebox.askyesno('Confirm reversal','Reverse every component of this posting?\nThe original stays in audit history. Post any replacement separately with a new reference.',parent=form): return self._keep_form()
            self.ledger.reverse(group_id,v['date'],v['reason'],key); detail_window.destroy(); self.show(self.page)
        form=Form(self,'Reverse Transaction',save,button='Reverse posting',help_text='A reversal reduces the original Amount In or Amount Out on its own date. Split receipts and internal transfers are reversed together.')
        form.add('date','Reversal date',today()); form.add('reason','Reason *')

    @staticmethod
    def _keep_form():
        raise ValueError('Reversal cancelled. Your entered values are retained.')

    def reports_page(self):
        self.toolbar('Historical balances are reconstructed at the selected end date. Exports are generated locally.')
        self.date_bar(self.content,lambda:self.show('Reports'))
        bar=ttk.Frame(self.content); bar.pack(fill='x',pady=6)
        self.report_name=ttk.Combobox(bar,values=REPORT_NAMES,state='readonly',width=42); self.report_name.set(REPORT_NAMES[0]); self.report_name.pack(side='left')
        ttk.Button(bar,text='Generate report',command=lambda:self.guard(self.generate_report)).pack(side='left',padx=10)
        filters=ttk.Frame(self.content); filters.pack(fill='x',pady=6)
        self.report_party=SearchCombo(filters,[(None,'All parties')]+self.party_choices(),width=27); self.report_party.select_key(None); self.report_party.grid(row=0,column=0,padx=(0,6),pady=4,sticky='ew')
        self.report_finance=SearchCombo(filters,[(None,'All finance accounts')]+self.finance_choices(),width=32); self.report_finance.select_key(None); self.report_finance.grid(row=0,column=1,padx=6,pady=4,sticky='ew')
        self.report_cash=SearchCombo(filters,[(None,'All payment accounts')]+self.cash_choices(),width=27); self.report_cash.select_key(None); self.report_cash.grid(row=0,column=2,padx=6,pady=4,sticky='ew')
        self.report_module=SearchCombo(filters,[(None,'All modules')]+list(MODULES.items()),width=27); self.report_module.select_key(None); self.report_module.grid(row=1,column=0,padx=(0,6),pady=4,sticky='ew')
        self.report_status=SearchCombo(filters,[(None,'All statuses')]+[(s,s.title()) for s in ('active','matured','closed')],width=32); self.report_status.select_key(None); self.report_status.grid(row=1,column=1,padx=6,pady=4,sticky='ew')
        self.report_type=SearchCombo(filters,[(None,'All transaction types')]+[(k,v.label) for k,v in TYPES.items()],width=27); self.report_type.select_key(None); self.report_type.grid(row=1,column=2,padx=6,pady=4,sticky='ew')
        for i in range(3): filters.columnconfigure(i,weight=1)
        self.report_body=ttk.Frame(self.content); self.report_body.pack(fill='both',expand=True,pady=10)
        self.generate_report()

    def generate_report(self):
        report=build_report(self.ledger,self.report_name.get(),self.start,self.end,party_id=self.report_party.selected(),finance_id=self.report_finance.selected(),cash_id=self.report_cash.selected(),module=self.report_module.selected(),status=self.report_status.selected(),type=self.report_type.selected())
        for child in self.report_body.winfo_children(): child.destroy()
        self.report_widget(self.report_body,report)

    def report_widget(self,parent,report):
        header=ttk.Frame(parent); header.pack(fill='x')
        ttk.Label(header,text=report.title,style='Section.TLabel').pack(side='left')
        for label,suffix in [('CSV','.csv'),('Excel','.xlsx'),('PDF / Print','.pdf')]:
            ttk.Button(header,text=label,command=lambda suffix=suffix:self.guard(lambda:self.save_report(report,suffix))).pack(side='right',padx=4)
        ttk.Label(parent,text=report.period,style='Muted.TLabel').pack(anchor='w',pady=6)
        table(parent,report.columns,report.rows,report.money_columns)
        notes=tk.Text(parent,height=4,wrap='word',font=('Segoe UI',9),bg=BG,fg=MUTED,relief='flat')
        notes.pack(fill='x',pady=(8,0)); notes.insert('1.0','\n'.join(report.notes)); notes.configure(state='disabled')

    def save_report(self,report,suffix):
        path=filedialog.asksaveasfilename(parent=self,title='Save local report',initialfile='FinanceLedger-report'+suffix,defaultextension=suffix,filetypes=[({'.csv':'CSV','.xlsx':'Excel workbook','.pdf':'PDF document'}[suffix],'*'+suffix)])
        if path:
            export_report(report,path,self.business_name())
            messagebox.showinfo('Report saved',f'Saved to:\n{path}'+ ('\n\nOpen the PDF in your local PDF viewer to print.' if suffix=='.pdf' else ''),parent=self)

    def settings_page(self):
        container=ttk.Frame(self.content); container.pack(fill='both',expand=True)
        canvas=tk.Canvas(container,background=BG,highlightthickness=0)
        scrollbar=ttk.Scrollbar(container,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right',fill='y'); canvas.pack(side='left',fill='both',expand=True)
        area=ttk.Frame(canvas)
        inner=canvas.create_window((0,0),window=area,anchor='nw')
        area.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(inner,width=e.width))
        ttk.Label(area,text='Business',style='Section.TLabel').pack(anchor='w',pady=(12,8))
        line=ttk.Frame(area); line.pack(fill='x')
        name=ttk.Entry(line,width=45); name.insert(0,self.business_name()); name.pack(side='left')
        def save_name():
            value=name.get().strip()
            if not value: raise ValueError('Business name is required.')
            with self.db.atomic():
                before=self.business_name(); self.db.conn.execute("UPDATE settings SET value=? WHERE key='business_name'",(value,)); self.db.audit('settings','business_name','update',before,value)
            self.show('Settings')
        ttk.Button(line,text='Save business name',command=lambda:self.guard(save_name)).pack(side='left',padx=10)
        ttk.Label(area,text='Data & backups',style='Section.TLabel').pack(anchor='w',pady=(24,8))
        ttk.Label(area,text=f'Database: {self.db.path}\nAutomatic backups: {self.db.directory / "backups"}\nCurrency: INR · integer paise · Business dates: Asia/Kolkata\nAutomatic backup: first launch each day; latest 30 daily backups retained.',wraplength=850).pack(anchor='w')
        ttk.Label(area,text='Backups on the same disk do not protect against disk failure. Regularly copy a manual backup to a USB drive or another physical disk.',foreground='#9b6024',wraplength=800).pack(anchor='w',pady=14)
        actions=ttk.Frame(area); actions.pack(fill='x',pady=5)
        ttk.Button(actions,text='Backup Database…',command=lambda:self.guard(self.manual_backup)).pack(side='left')
        ttk.Button(actions,text='Restore Backup…',command=lambda:self.guard(self.restore_backup)).pack(side='left',padx=10)
        ttk.Label(area,text='General income & expense categories',style='Section.TLabel').pack(anchor='w',pady=(24,8))
        cats=self.db.all('SELECT * FROM categories ORDER BY name')
        ttk.Label(area,text=' · '.join(c['name']+' ('+c['kind']+')' for c in cats),wraplength=850).pack(anchor='w')
        ttk.Button(area,text='+ Add category',command=self.category_form).pack(anchor='w',pady=10)
        ttk.Label(area,text='Audit history',style='Section.TLabel').pack(anchor='w',pady=(15,5))
        ttk.Label(area,text='Posted records cannot be edited or deleted. Corrections use linked reversals and replacement postings.',style='Muted.TLabel').pack(anchor='w')
        ttk.Button(area,text='View audit history',command=self.audit_window).pack(anchor='w',pady=10)

    def category_form(self):
        def save(form):
            v=form.values(); self.ledger.add_category(v['name'],v['kind']); self.show(self.page)
        form=Form(self,'Add Category',save)
        form.add('name','Category name *'); form.add('kind','Kind','expense',choices=['income','expense'])

    def manual_backup(self):
        folder=filedialog.askdirectory(parent=self,title='Choose backup folder or USB drive')
        if not folder: return
        from datetime import datetime
        path=Path(folder)/('FinanceLedger-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
        self.db.backup(path)
        messagebox.showinfo('Backup complete',f'Consistent database backup saved to:\n{path}\n\nA backup on the same disk does not protect against disk failure.',parent=self)

    def restore_backup(self):
        path=filedialog.askopenfilename(parent=self,title='Select Finance Ledger backup',filetypes=[('SQLite backup','*.sqlite3'),('All files','*')])
        if not path: return
        self.db.validate_backup(path)
        if not messagebox.askyesno('Replace all current data?',f'Validated backup:\n{path}\n\nThis will replace ALL records in the {"DEMO" if self.demo else "PRODUCTION"} workspace. A pre-restore backup will be created automatically.\n\nContinue?',icon='warning',parent=self): return
        safety=self.db.restore(path); self.show('Settings')
        messagebox.showinfo('Restore complete',f'Backup restored. Previous data saved to:\n{safety}',parent=self)

    def audit_window(self):
        window=tk.Toplevel(self); window.title('Audit History'); window.geometry('1100x700')
        body=ttk.Frame(window,padding=20); body.pack(fill='both',expand=True)
        ttk.Label(body,text='Audit History · most recent 1,000 changes',style='Section.TLabel').pack(anchor='w')
        rows=self.db.all('SELECT * FROM audit_log ORDER BY id DESC LIMIT 1000')
        def detail(iid):
            row=next(r for r in rows if r['id']==int(iid))
            view=tk.Toplevel(window); view.title('Audit detail'); view.geometry('850x550')
            text=tk.Text(view,wrap='word',font=('Consolas',11)); text.pack(fill='both',expand=True,padx=15,pady=15)
            text.insert('1.0',json.dumps(row,indent=2,ensure_ascii=False)); text.configure(state='disabled')
        table(body,['At (UTC)','Entity','ID','Action','Actor'],[[r['at'],r['entity'],r['entity_id'],r['action'],r['actor']] for r in rows],on_open=detail,identifiers=[r['id'] for r in rows])
        ttk.Button(body,text='Export complete audit CSV…',command=lambda:self.guard(self.export_audit)).pack(anchor='e',pady=10)

    def export_audit(self):
        path=filedialog.asksaveasfilename(parent=self,title='Export full audit history',defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if path:
            from .reports import safe_text
            rows=self.db.all('SELECT * FROM audit_log ORDER BY id')
            with open(path,'w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.writer(stream); writer.writerow(['ID','Entity','Entity ID','Action','Before','After','Actor','Timestamp UTC'])
                writer.writerows([[safe_text(row[k] or '') for k in ('id','entity','entity_id','action','before_json','after_json','actor','at')] for row in rows])
            messagebox.showinfo('Audit exported',f'Saved to {path}',parent=self)
