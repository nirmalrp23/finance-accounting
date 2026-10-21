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
from .categories import CATEGORY_REPORTS, TRANSACTION_DETAILS, transaction_detail
from .money import money, paise, today, valid_date
from .reports import CASHBOOK_REPORT, REPORT_NAMES, Report, build_report, cashbook_balances, export_report

from .appearance import BG, WHITE, GREEN, NAV, INK, MUTED, LINE, FONT, PALE, AMBER, configure_theme, card, metric_cards, value_panel


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
    """One keyboard-friendly dialog with compact, reflowing field sections."""
    def __init__(self,parent,title,on_save,button='Save',help_text=''):
        super().__init__(parent)
        self.title(title); self.transient(parent.winfo_toplevel()); self.resizable(True,True)
        self.configure(bg=BG); self.on_save=on_save; self.fields={}; self.labels={}
        self.field_frames={}; self.field_groups={}; self.field_visible={}; self.groups=[]; self.row=0
        self._positioned=False
        self.columnconfigure(0,weight=1); self.rowconfigure(1,weight=1)
        header=card(self,22); self.header=header; header.grid(row=0,column=0,columnspan=2,sticky='ew')
        ttk.Label(header,text=title,style='DialogTitle.TLabel').pack(anchor='w')
        if help_text:
            ttk.Label(header,text=help_text,style='CardMuted.TLabel',wraplength=790).pack(anchor='w',pady=(7,0))
        self.canvas=tk.Canvas(self,background=BG,highlightthickness=0,yscrollincrement=24)
        self.canvas.grid(row=1,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview); scroll.grid(row=1,column=1,sticky='ns')
        self.canvas.configure(yscrollcommand=scroll.set)
        self.body=ttk.Frame(self.canvas,padding=(20,16)); self.body.columnconfigure(0,weight=1); self.body.columnconfigure(1,weight=1)
        self.body_window=self.canvas.create_window((0,0),window=self.body,anchor='nw')
        self.body.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.body_window,width=e.width))
        self.bottom=card(self,18); self.bottom.grid(row=2,column=0,columnspan=2,sticky='ew')
        self.error=ttk.Label(self.bottom,text='',style='Error.TLabel',wraplength=790,padding=(12,8))
        actions=ttk.Frame(self.bottom,style='Card.TFrame'); actions.pack(side='bottom',fill='x')
        ttk.Label(actions,text='Ctrl+Enter to save   ·   Esc to cancel',style='CardMuted.TLabel').pack(side='left')
        ttk.Button(actions,text=button,command=self.submit,style='Primary.TButton').pack(side='right')
        ttk.Button(actions,text='Cancel',command=self.destroy,style='Subtle.TButton').pack(side='right',padx=10)
        self.bind('<Control-Return>',lambda e:self.submit()); self.bind('<Escape>',lambda e:self.destroy())
        self.bind('<MouseWheel>',self._wheel); self.bind('<Button-4>',lambda e:self._wheel(e,-1)); self.bind('<Button-5>',lambda e:self._wheel(e,1))
        self.protocol('WM_DELETE_WINDOW',self.destroy)
        self.section('Details')
        self.after(30,self._focus)

    def section(self,title,collapsible=False,expanded=True,columns=2):
        panel=card(self.body,14); panel.grid(row=self.row,column=0,columnspan=2,sticky='ew',pady=(0,12)); self.row+=1
        heading=ttk.Frame(panel,style='Card.TFrame'); heading.pack(fill='x')
        fields=ttk.Frame(panel,style='Card.TFrame'); fields.pack(fill='x',pady=(12,0))
        for index in range(columns): fields.columnconfigure(index,weight=1,uniform='fields')
        group={'panel':panel,'heading':heading,'fields':fields,'keys':[],'expanded':expanded,'collapsible':collapsible,'title':title,'columns':columns}
        if collapsible:
            def toggle():
                group['expanded']=not group['expanded']; self._layout_group(group)
            group['toggle']=ttk.Button(heading,text=title,style='Subtle.TButton',command=toggle)
            group['toggle'].pack(anchor='w')
        else:
            ttk.Label(heading,text=title,style='CardTitle.TLabel').pack(side='left')
        self.groups.append(group); self.group=group
        return group

    def _layout_group(self,group):
        keys=[key for key in group['keys'] if self.field_visible[key]]
        if not keys: group['panel'].grid_remove(); return
        group['panel'].grid()
        if group['collapsible']:
            group['toggle'].configure(text=('−  ' if group['expanded'] else '+  ')+group['title'])
        if group['expanded']:
            group['fields'].pack(fill='x',pady=(12,0))
        else: group['fields'].pack_forget()
        row=column=0
        columns=group['columns']
        for key in group['keys']:
            frame=self.field_frames[key]
            if not self.field_visible[key]: frame.grid_remove(); continue
            full=key in ('particulars','notes','address','party_address','reason')
            if full and column: row+=1; column=0
            frame.grid(row=row,column=column,columnspan=columns if full else 1,sticky='ew',padx=(0,12 if not full and column<columns-1 else 0),pady=(0,8))
            if full: row+=1; column=0
            elif column==columns-1: row+=1; column=0
            else: column+=1

    def add(self,key,label,value='',choices=None,search=False,readonly=False):
        group=self.group
        frame=ttk.Frame(group['fields'],style='Card.TFrame')
        self.labels[key]=ttk.Label(frame,text=label,style='Field.TLabel'); self.labels[key].pack(anchor='w',pady=(0,6))
        if search:
            widget=SearchCombo(frame,choices or [],width=18)
            if value is not None: widget.select_key(value)
        elif choices is not None:
            widget=ttk.Combobox(frame,values=choices,state='readonly',width=18)
            widget.set(value if value!='' else (choices[0] if choices else ''))
        else:
            widget=ttk.Entry(frame,width=18,style='Amount.TEntry' if key in ('amount','interest','opening') else 'TEntry')
            widget.insert(0,str(value))
            if readonly: widget.configure(state='readonly')
        widget.pack(fill='x')
        widget.bind('<FocusIn>',lambda e:self.after_idle(lambda:self._ensure_visible(widget)),add='+')
        widget.bind('<MouseWheel>',self._wheel)
        self.fields[key]=widget; self.field_frames[key]=frame; self.field_groups[key]=group; self.field_visible[key]=True
        group['keys'].append(key); self._layout_group(group)
        return widget

    def visible(self,keys,show):
        touched=[]
        for key in keys:
            self.field_visible[key]=show
            group=self.field_groups[key]
            if group not in touched: touched.append(group)
        for group in touched: self._layout_group(group)

    def fit(self):
        self.update_idletasks()
        if not self._positioned:
            width=min(900,self.winfo_screenwidth()-80)
            height=min(790,self.winfo_screenheight()-90,max(360,self.header.winfo_reqheight()+self.bottom.winfo_reqheight()+self.body.winfo_reqheight()+30))
            self.geometry(f'{width}x{height}')
            self.minsize(min(680,width),min(420,height))
            self._positioned=True
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _focus(self):
        self.fit()
        self.update_idletasks()
        root=self.master.winfo_toplevel()
        x=max(0,root.winfo_rootx()+(root.winfo_width()-self.winfo_width())//2)
        y=max(0,min(self.winfo_screenheight()-self.winfo_height()-50,root.winfo_rooty()+35))
        self.geometry(f'+{x}+{y}')
        for key,widget in self.fields.items():
            if self.field_visible[key]: widget.focus_set(); break
        self.grab_set()

    def _ensure_visible(self,widget):
        if not widget.winfo_exists(): return
        top=self.canvas.canvasy(0); height=self.canvas.winfo_height(); body_height=max(1,self.body.winfo_height())
        y=widget.winfo_rooty()-self.body.winfo_rooty(); bottom=y+widget.winfo_height()
        if y<top: self.canvas.yview_moveto(max(0,(y-18)/body_height))
        elif bottom>top+height: self.canvas.yview_moveto((bottom-height+18)/body_height)

    def _wheel(self,event,step=None):
        if step is None:
            delta=getattr(event,'delta',0)
            step=-int(delta/120) if abs(delta)>=120 else (-1 if delta>0 else 1)
        self.canvas.yview_scroll(step,'units')
        return 'break'

    def note(self,text):
        label=ttk.Label(self.body,text=text,style='Info.TLabel',padding=(14,10),wraplength=790)
        label.grid(row=self.row,column=0,columnspan=2,sticky='ew',pady=(0,12)); self.row+=1
        return label

    def values(self):
        return {key:widget.get().strip() for key,widget in self.fields.items()}

    def submit(self):
        self.error.configure(text=''); self.error.pack_forget()
        try: self.on_save(self)
        except (ValueError,sqlite3.Error,OSError,ImportError) as exc:
            self.error.configure(text=str(exc)); self.error.pack(fill='x',pady=(0,12)); self.bell(); return
        self.destroy()


def table(parent, columns, rows, money_cols=(), on_open=None, height=16, identifiers=None, widths=None):
    frame = tk.Frame(parent,bg=WHITE,highlightbackground=LINE,highlightthickness=1)
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
        if widths: width=widths[i]
        tree.heading(ids[i],text=label,anchor='e' if i in money_cols else 'w')
        tree.column(ids[i],width=width,minwidth=45 if widths else 90,anchor='e' if i in money_cols else 'w',stretch=True)
    for index,row in enumerate(rows):
        iid = str(identifiers[index]) if identifiers is not None else str(index)
        raw[iid] = row
        tree.insert('', 'end',iid=iid,values=[money(value) if i in money_cols and isinstance(value,int) else value for i,value in enumerate(row)],tags=('even' if index%2==0 else 'odd',))
    tree.tag_configure('even',background='#ffffff'); tree.tag_configure('odd',background='#f7faf8')
    tree.tag_configure('total',background=PALE,font=(FONT,10,'bold'))
    for iid,row in raw.items():
        if any(str(value) in ('TOTAL','Closing / totals','Opening balance') for value in row): tree.item(iid,tags=('total',))
    def sort_column(i, reverse=False):
        def key(iid):
            value = raw[iid][i]
            return (value is None,value if isinstance(value,(int,float)) else str(value or '').casefold())
        for index,iid in enumerate(sorted(tree.get_children(),key=key,reverse=reverse)):
            tree.move(iid,'',index)
        for number,label in enumerate(columns): tree.heading(ids[number],text=label+('  ↓' if reverse else '  ↑') if number==i else label)
        tree.heading(ids[i],command=lambda:sort_column(i,not reverse))
    for i in range(len(columns)):
        tree.heading(ids[i],command=lambda i=i:sort_column(i))
    if on_open:
        def opened(event=None):
            if event and getattr(event,'keysym','') not in ('Return','KP_Enter') and tree.identify_region(event.x,event.y) not in ('cell','tree'): return
            selection = tree.selection()
            if selection: on_open(selection[0])
        tree.bind('<Double-1>',opened); tree.bind('<Return>',opened)
    if not rows:
        empty=ttk.Frame(frame,style='Card.TFrame',padding=20); empty.place(relx=.5,rely=.52,anchor='center')
        ttk.Label(empty,text='No records to show',style='CardTitle.TLabel').pack()
        ttk.Label(empty,text='Try another period or adjust the filters.',style='CardMuted.TLabel').pack(pady=(8,0))
    return tree


class Application(tk.Tk):
    PAGES = ('Dashboard','Cash Book','Parties','Reports','Cash & Bank','Settings')
    def __init__(self,database,demo=False):
        super().__init__()
        self.db = database; self.ledger = Ledger(database); self.demo = demo
        self.page = 'Dashboard'; self.start = today()[:8]+'01'; self.end = today(); self.active_report = CASHBOOK_REPORT
        self.title('Finance Ledger '+__version__+(' — DEMO' if demo else '')); self.geometry('1280x820'); self.minsize(960,640)
        self.configure(bg=BG)
        self._style()
        self._build_sidebar()
        self.main=ttk.Frame(self,padding=(28,22)); self.main.pack(side='left',fill='both',expand=True)
        workspace=ttk.Frame(self.main); workspace.pack(fill='x',pady=(0,18))
        self.workspace_label=ttk.Label(workspace,text=self.business_name(),style='Kicker.TLabel'); self.workspace_label.pack(side='left')
        ttk.Label(workspace,text=date.fromisoformat(today()).strftime('%d %b %Y'),style='Muted.TLabel').pack(side='right',padx=(12,0))
        ttk.Label(workspace,text='DEMO DATA' if demo else 'LOCAL WORKSPACE',style='Info.TLabel',padding=(9,4)).pack(side='right')
        header=ttk.Frame(self.main); header.pack(fill='x',pady=(0,22))
        titles=ttk.Frame(header); titles.pack(side='left',fill='x',expand=True)
        self.heading=ttk.Label(titles,text='Dashboard',style='Title.TLabel'); self.heading.pack(anchor='w')
        self.subheading=ttk.Label(titles,text='',style='Muted.TLabel',wraplength=540); self.subheading.pack(anchor='w',pady=(5,0))
        ttk.Button(header,text='+  New cash book entry',style='Primary.TButton',command=self.transaction_form).pack(side='right',padx=(12,0))
        self.status=ttk.Label(self.main,text='',style='Muted.TLabel'); self.status.pack(side='bottom',fill='x',pady=(14,0))
        self.content=ttk.Frame(self.main); self.content.pack(fill='both',expand=True)
        self.bind('<Control-n>',lambda e:self.transaction_form()); self.bind('<F5>',lambda e:self.show(self.page))
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.show('Dashboard')

    def _build_sidebar(self):
        self.sidebar=tk.Frame(self,bg=NAV,width=250)
        self.sidebar.pack(side='left',fill='y'); self.sidebar.pack_propagate(False)
        brand=tk.Frame(self.sidebar,bg=NAV); brand.pack(fill='x',padx=20,pady=(26,28))
        tk.Label(brand,text='FL',bg=GREEN,fg=WHITE,font=(FONT,12,'bold'),padx=10,pady=10).pack(side='left',padx=(0,10))
        identity=tk.Frame(brand,bg=NAV); identity.pack(side='left')
        tk.Label(identity,text='Finance Ledger',bg=NAV,fg=WHITE,font=(FONT,14,'bold')).pack(anchor='w')
        tk.Label(identity,text='DESKTOP  /  '+__version__,bg=NAV,fg='#88ab99',font=(FONT,8)).pack(anchor='w',pady=(4,0))
        self.nav={}
        for page in self.PAGES:
            button=ttk.Button(self.sidebar,text=page,style='Nav.TButton',cursor='hand2',command=lambda page=page:self.show(page))
            button.pack(fill='x',padx=14,pady=2); self.nav[page]=button
        footer=tk.Frame(self.sidebar,bg=NAV); footer.pack(side='bottom',fill='x',padx=22,pady=22)
        tk.Label(footer,text='●  Saved on this device',bg=NAV,fg='#a8c6b6',font=(FONT,9)).pack(anchor='w')
        tk.Label(footer,text='INR  ·  Asia/Kolkata',bg=NAV,fg='#759b87',font=(FONT,8)).pack(anchor='w',pady=(7,0))
        tk.Label(self.sidebar,text='REPORTS BY CATEGORY',bg=NAV,fg='#87ab98',font=(FONT,8,'bold'),anchor='w').pack(fill='x',padx=23,pady=(24,10))
        search=tk.Frame(self.sidebar,bg=NAV); search.pack(fill='x',padx=20,pady=(0,8))
        self.report_search=tk.StringVar()
        ttk.Entry(search,textvariable=self.report_search,style='NavSearch.TEntry').pack(fill='x')
        self.report_count=tk.Label(search,text='',bg=NAV,fg='#759b87',font=(FONT,8),anchor='w'); self.report_count.pack(fill='x',pady=(6,0))
        menu=tk.Frame(self.sidebar,bg=NAV); menu.pack(fill='both',expand=True,padx=(15,10))
        self.report_nav=ttk.Treeview(menu,show='tree',height=5,style='ReportNav.Treeview',selectmode='browse')
        self.report_nav.column('#0',width=212,minwidth=160,stretch=True)
        scroll=ttk.Scrollbar(menu,orient='vertical',command=self.report_nav.yview,style='Nav.Vertical.TScrollbar')
        self.report_nav.configure(yscrollcommand=scroll.set); scroll.pack(side='right',fill='y'); self.report_nav.pack(fill='both',expand=True)
        self.report_nav.tag_configure('group',foreground='#dcebe2',font=(FONT,9,'bold'))
        self.report_nav.bind('<<TreeviewSelect>>',self.open_category_report)
        self.report_search.trace_add('write',lambda *args:self._filter_report_nav())
        self._filter_report_nav()

    def _filter_report_nav(self):
        for iid in self.report_nav.get_children(): self.report_nav.delete(iid)
        term=self.report_search.get().casefold().strip(); count=0
        groups=[('STL loans',['loan_disbursed','loan_repaid','loan_interest']),
                ('Fixed deposits',['fd_received','fd_repaid','fd_interest']),
                ('External loans',['other_received','other_repaid','other_interest']),
                ('Hand loans given',['hand_given_disbursed','hand_given_repaid','hand_given_interest']),
                ('Finance hand loans',['hand_taken_received','hand_taken_repaid','hand_taken_interest']),
                ('General & transfers',['general_expense','general_income','transfer_out'])]
        for index,(title,keys) in enumerate(groups):
            matches=[key for key in keys if not term or term in TRANSACTION_DETAILS[key].casefold() or term in title.casefold()]
            if not matches: continue
            parent=self.report_nav.insert('', 'end',iid='group:'+str(index),text=title,open=bool(term),tags=('group',))
            for key in matches:
                label=TRANSACTION_DETAILS[key].title().replace('Stl','STL').replace('Fd','FD')
                self.report_nav.insert(parent,'end',iid=key,text=label); count+=1
        self.report_count.configure(text=f'{count} categories · type to find a report')

    def _style(self):
        configure_theme(self)

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
        descriptions={'Dashboard':'Cash, principal and actual interest at a glance.','Cash Book':'Your complete cash record, with one form for every entry.','Parties':'Customer and provider contacts, accounts and statements.','Reports':'Choose a report, set a period and save a local copy.','Cash & Bank':'Manage where your business holds its money.','Settings':'Business details, local backups and audit history.'}
        self.subheading.configure(text=descriptions[page]); self.workspace_label.configure(text=self.business_name())
        self.status.configure(text='Ctrl+N  New entry       F5  Refresh       •       All records stay on this device')
        render = {'Dashboard':self.dashboard,'Parties':self.parties_page,'Cash & Bank':self.cash_page,'Cash Book':self.transactions_page,'Reports':self.reports_page,'Settings':self.settings_page}[page]
        self.guard(render)

    def open_category_report(self,event=None):
        selected=self.report_nav.selection()
        if selected and selected[0] in CATEGORY_REPORTS:
            self.active_report=CATEGORY_REPORTS[selected[0]]
            self.show('Reports')

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
        metric_cards(self.content,[
            ('Amount In',stats['amount_in'],'Money received this period',GREEN),
            ('Amount Out',stats['amount_out'],'Money paid this period',AMBER),
            ('Net cash movement',stats['net_cash'],'Amount In less Amount Out',INK),
            ('Cash & bank balance',stats['cash'],'Balance as of '+self.end,GREEN)])
        ttk.Label(self.content,text='Net cash movement includes principal. It is not profit.',style='Muted.TLabel').pack(anchor='w',pady=(0,14))
        notebook=ttk.Notebook(self.content); notebook.pack(fill='both',expand=True)
        overview=ttk.Frame(notebook); due=ttk.Frame(notebook,padding=(0,8)); activity=ttk.Frame(notebook,padding=(0,8))
        notebook.add(overview,text='Principal & interest'); notebook.add(due,text='Maturities & overdue'); notebook.add(activity,text='Recent activity')
        viewport=tk.Canvas(overview,bg=BG,highlightthickness=0,yscrollincrement=24)
        scrollbar=ttk.Scrollbar(overview,orient='vertical',command=viewport.yview)
        viewport.configure(yscrollcommand=scrollbar.set); scrollbar.pack(side='right',fill='y'); viewport.pack(fill='both',expand=True)
        panels=ttk.Frame(viewport); panel_window=viewport.create_window((0,0),window=panels,anchor='nw')
        panels.bind('<Configure>',lambda e:viewport.configure(scrollregion=viewport.bbox('all')))
        principal=value_panel(panels,'Principal outstanding','As of '+self.end,[
            ('Fixed deposits',stats['principal']['fd'],'Payable',INK),
            ('STL loans',stats['principal']['loan'],'Receivable',GREEN),
            ('External loans',stats['principal']['other'],'Payable',INK),
            ('Hand loans given',stats['principal']['hand_given'],'Receivable',GREEN),
            ('Finance hand loans',stats['principal']['hand_taken'],'Payable',INK)])
        interest=value_panel(panels,'Actual interest','Posted amounts for the selected period',[
            ('Interest received',stats['interest_received'],'',GREEN),
            ('FD interest paid',stats['fd_interest'],'',AMBER),
            ('External loan interest paid',stats['other_interest'],'',AMBER),
            ('Hand loan interest paid',stats['hand_interest'],'',AMBER),
            ('Net interest income',stats['net_interest'],'Actual received less actual paid',GREEN)])
        def resize_panels(event):
            viewport.itemconfigure(panel_window,width=event.width)
            wide=event.width>=720
            panels.columnconfigure(0,weight=1,uniform='panels'); panels.columnconfigure(1,weight=1 if wide else 0,uniform='panels')
            principal.grid(row=0,column=0,sticky='nsew',padx=(0,12 if wide else 0),pady=(0,12))
            interest.grid(row=0 if wide else 1,column=1 if wide else 0,sticky='nsew',pady=(0,12))
        viewport.bind('<Configure>',resize_panels)
        def scroll_overview(event):
            step=-int(event.delta/120) if abs(event.delta)>=120 else (-1 if event.delta>0 else 1)
            viewport.yview_scroll(step,'units'); return 'break'
        def attach_wheel(widget):
            widget.bind('<MouseWheel>',scroll_overview)
            for child in widget.winfo_children(): attach_wheel(child)
        attach_wheel(viewport)
        horizon = (date.fromisoformat(self.end)+timedelta(days=30)).isoformat()
        upcoming = []
        for a in self.ledger.finance_accounts():
            outstanding = self.ledger.principal(a['id'],self.end)
            if a['due_date'] and outstanding>0 and (a['due_date']<self.end or (a['module']=='fd' and a['due_date']<=horizon)):
                upcoming.append([a['reference'],a['party_name'],a['due_date'],'Past recorded due date' if a['due_date']<self.end else 'FD maturity within 30 days',outstanding])
        notebook.tab(due,text=f'Maturities & overdue ({len(upcoming)})')
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
        self.toolbar('Names are created in the single Cash Book Entry form. Double-click for accounts and statements.',[('+ Entry for new party',self.party_form)])
        parties = self.ledger.parties()
        table(self.content,['Name','Phone','Roles','Email','Status'],[[p['name'],p['phone'],p['roles'],p['email'],'Active' if p['active'] else 'Inactive'] for p in parties],on_open=lambda iid:self.party_detail(int(iid)),identifiers=[p['id'] for p in parties])

    def party_form(self,party_id=None):
        if party_id is None:
            return self.transaction_form(new_party=True)
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

    def finance_form(self,module):
        initial={'fd':'fd_received','loan':'loan_disbursed','other':'other_received','hand_given':'hand_given_disbursed','hand_taken':'hand_taken_received'}[module]
        return self.transaction_form(initial,new_finance=True)

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

    def transaction_form(self,initial=None,new_party=False,new_finance=False):
        if not self.ledger.cash_accounts():
            messagebox.showinfo('Add a payment account','Add a Cash or Bank account before entering money received or paid.',parent=self)
            self.cash_form(); return
        key=str(uuid.uuid4())
        options=TRANSACTION_DETAILS
        finance_accounts={a['id']:a for a in self.ledger.finance_accounts()}
        initial=initial or 'loan_disbursed'
        def save(form):
            v=form.values()
            type_key=next(k for k,label in options.items() if label==v['type'])
            spec=TYPES[type_key]
            transfer=type_key=='transfer_out'
            creating_account=bool(spec.module and v['finance_mode']=='Create new account')
            creating_party=not transfer and v['party_mode']=='Create new party'
            finance_id=form.fields['finance'].selected(True) if spec.module and not creating_account else None
            party_id=None
            if not transfer and not creating_party and v['party_mode']=='Existing party':
                party_id=form.fields['party'].selected(required=creating_account)
            party_values=None
            if creating_party:
                party_values={k:v['party_'+k] for k in ('name','phone','address','email')}
                party_values['roles']=MODULES.get(spec.module,'General party')
            terms=None
            if creating_account:
                terms=dict(reference=v['account_reference'],start_date=v['account_date'],opening_paise=paise(v['opening']),annual_rate=v['rate'],frequency=v['frequency'],due_date=v['due_date'] or None)
            self.ledger.post_cashbook(type_key=type_key,amount_paise=paise(v['amount']),tx_date=v['date'],
                cash_id=form.fields['cash'].selected(True),idempotency_key=key,party_id=party_id,
                finance_id=finance_id,new_party=party_values,new_finance=terms,particulars=v['particulars'],
                interest_paise=paise(v['interest']) if type_key=='loan_repaid' else 0,
                method=v['method'],external_ref=v['external'],notes=v['notes'],
                transfer_to=form.fields['target'].selected(True) if transfer else None)
            self.show(self.page)
        form=Form(self,'Cash Book Entry',save,button='Save entry',help_text='Choose the transaction details, enter the name and amount, then select the cash or bank account.')
        type_widget=form.add('type','Category / Transaction Details *',options[initial],choices=list(options.values()))
        form.add('date','Date *',today())
        direction=form.note('')
        party_section=form.section('Party & account')
        party_mode=form.add('party_mode','Name / party','Create new party' if new_party else 'Existing party',choices=['Existing party','Create new party','No party (particulars only)'])
        party=form.add('party','Existing name',None,choices=self.party_choices(),search=True)
        form.add('party_name','New name *')
        form.add('party_phone','Phone (optional)')
        form.add('party_address','Address (optional)')
        form.add('party_email','Email (optional)')
        finance_mode=form.add('finance_mode','Finance account','Create new account' if new_finance or new_party else 'Existing account',choices=['Existing account','Create new account'])
        finance=form.add('finance','Existing FD / loan account',None,choices=self.finance_choices(),search=True)
        form.add('account_reference','New account reference (or auto)')
        form.add('account_date','Account opening date',today())
        form.add('opening','Brought-forward principal (₹)','0.00')
        form.add('rate','Annual interest rate %','0')
        form.add('frequency','Interest payout frequency','Monthly',choices=['Monthly','Quarterly','Half-yearly','Yearly','At maturity','On demand','Interest-free'])
        form.add('due_date','Due / maturity date (optional)')
        form.section('Payment details',columns=3)
        form.add('amount','Amount / principal (₹) *')
        form.add('interest','Additional STL interest (₹)','0.00')
        form.add('cash','Cash / Bank account *',next((a['id'] for a in self.ledger.cash_accounts() if a['kind']=='cash'),self.ledger.cash_accounts()[0]['id']),choices=self.cash_choices(),search=True)
        form.add('method','Payment method *','cash',choices=list(METHODS))
        form.add('target','Transfer destination *',None,choices=self.cash_choices(),search=True)
        form.add('particulars','Particulars / Description')
        account_note=ttk.Label(party_section['panel'],text='',style='CardMuted.TLabel',wraplength=790)
        account_note.pack(side='bottom',anchor='w',pady=(5,0))
        form.section('Additional details (optional)',collapsible=True,expanded=False)
        form.add('external','External reference')
        form.add('notes','Notes')
        party_keys=['party_name','party_phone','party_address','party_email']
        account_keys=['account_reference','account_date','opening','rate','frequency','due_date']
        def selected_type():
            return next(k for k,label in options.items() if label==type_widget.get())
        def refresh_choices():
            spec=TYPES[selected_type()]
            previous=next((key for key,label in finance.choices if label==finance.get()),None)
            party_id=next((key for key,label in party.choices if label==party.get()),None) if party_mode.get()=='Existing party' else None
            choices=[(a['id'],f'{a["reference"]} · {a["party_name"]}') for a in finance_accounts.values() if a['module']==spec.module and a['status']!='closed' and (not party_id or a['party_id']==party_id)]
            finance.choices=choices; finance.labels=[label for _,label in choices]; finance.configure(values=finance.labels)
            if previous in {key for key,_ in choices}: finance.select_key(previous)
            elif len(choices)==1: finance.select_key(choices[0][0])
            else: finance.set('')
            if finance_mode.get()=='Existing account' and party_mode.get()=='Existing party' and not party.get():
                account_id=next((key for key,label in choices if label==finance.get()),None)
                if account_id: party.select_key(finance_accounts[account_id]['party_id'])
        form.last_date=today()
        def update(event=None):
            entered_date=form.fields['date'].get()
            if entered_date!=form.last_date and form.fields['account_date'].get()==form.last_date:
                form.fields['account_date'].delete(0,'end'); form.fields['account_date'].insert(0,entered_date)
            form.last_date=entered_date
            type_key=selected_type(); spec=TYPES[type_key]; transfer=type_key=='transfer_out'
            if spec.module and party_mode.get()=='No party (particulars only)': party_mode.set('Existing party')
            if spec.module and party_mode.get()=='Create new party': finance_mode.set('Create new account')
            creating_party=party_mode.get()=='Create new party' and not transfer
            creating_account=bool(spec.module and finance_mode.get()=='Create new account')
            form.visible(['party_mode'],not transfer)
            form.visible(['party'],not transfer and party_mode.get()=='Existing party')
            form.visible(party_keys,creating_party)
            form.visible(['finance_mode'],bool(spec.module))
            form.visible(['finance'],bool(spec.module) and not creating_account)
            form.visible(account_keys,creating_account)
            form.visible(['interest'],type_key=='loan_repaid')
            form.visible(['target'],transfer)
            form.visible(['party_mode','finance_mode'],False)
            party_new.configure(text='Use existing name' if creating_party else '+ New name')
            account_new.configure(text='Use existing account' if creating_account else '+ New account')
            if transfer: party_new.pack_forget()
            elif not party_new.winfo_manager(): party_new.pack(side='right',padx=(8,0))
            if spec.module and not account_new.winfo_manager(): account_new.pack(side='right',padx=(8,0))
            elif not spec.module: account_new.pack_forget()
            refresh_choices()
            account_id=next((key for key,label in finance.choices if label==finance.get()),None)
            if transfer:
                direction.configure(text='Internal transfer · Cash Out and Cash In are linked. Overall totals exclude transfers.',style='Info.TLabel')
                account_note.configure(text='Choose two different Cash / Bank accounts. No party or finance account is linked.')
            else:
                direction.configure(text=('Cash In / Amount In  ·  ' if spec.direction==1 else 'Cash Out / Amount Out  ·  ')+TYPES[type_key].label,style='In.TLabel' if spec.direction==1 else 'Out.TLabel')
                if creating_account:
                    account_note.configure(text='Leave opening principal at zero for a new deposit or disbursement. Use brought-forward principal only for money already outstanding.')
                elif account_id and spec.module:
                    outstanding=self.ledger.principal(account_id,form.fields['date'].get()) if self._is_date(form.fields['date'].get()) else 0
                    account_note.configure(text=f'Principal outstanding on the entered date: {money(outstanding)}. Interest is recorded separately.')
                else:
                    account_note.configure(text='For office expenses, use Particulars for Water Can, Salary, Rent, etc. Party/Name is optional.' if not spec.module else 'Select an existing account, or create a new one here. No separate account-opening screen is needed.')
            form.fit()
        def account_changed(event=None):
            account_id=next((key for key,label in finance.choices if label==finance.get()),None)
            if account_id:
                party_mode.set('Existing party'); party.select_key(finance_accounts[account_id]['party_id'])
            update()
        def toggle_party():
            party_mode.set('Existing party' if party_mode.get()=='Create new party' else 'Create new party'); update()
        def toggle_account():
            if finance_mode.get()=='Create new account':
                finance_mode.set('Existing account')
                if party_mode.get()=='Create new party': party_mode.set('Existing party')
            else: finance_mode.set('Create new account')
            update()
        party_new=ttk.Button(party_section['heading'],text='+ New name',style='Subtle.TButton',command=toggle_party)
        account_new=ttk.Button(party_section['heading'],text='+ New account',style='Subtle.TButton',command=toggle_account)
        type_widget.bind('<<ComboboxSelected>>',update)
        party_mode.bind('<<ComboboxSelected>>',update)
        party.bind('<<ComboboxSelected>>',update)
        finance_mode.bind('<<ComboboxSelected>>',update)
        finance.bind('<<ComboboxSelected>>',account_changed)
        form.fields['date'].bind('<FocusOut>',update)
        if not any(a['module']==TYPES[initial].module and a['status']!='closed' for a in finance_accounts.values()): finance_mode.set('Create new account')
        update()
        return form

    @staticmethod
    def _is_date(value):
        try: valid_date(value); return True
        except ValueError: return False

    @staticmethod
    def filter_field(parent,title,choices,column,row=0):
        frame=ttk.Frame(parent,style='Card.TFrame'); frame.grid(row=row,column=column,sticky='ew',padx=(0,12),pady=(0,10))
        ttk.Label(frame,text=title,style='Field.TLabel').pack(anchor='w',pady=(0,6))
        combo=SearchCombo(frame,choices,width=18); combo.select_key(None); combo.pack(fill='x')
        parent.columnconfigure(column,weight=1)
        return combo

    def transactions_page(self):
        self.date_bar(self.content,lambda:self.show('Cash Book'))
        filters=card(self.content,16); filters.pack(fill='x',pady=(0,12))
        search=ttk.Frame(filters,style='Card.TFrame'); search.grid(row=0,column=0,sticky='ew',padx=(0,12),pady=(0,10))
        ttk.Label(search,text='Search entries',style='Field.TLabel').pack(anchor='w',pady=(0,6))
        self.tx_search=ttk.Entry(search,width=25); self.tx_search.pack(fill='x'); filters.columnconfigure(0,weight=2)
        self.tx_type=self.filter_field(filters,'Transaction category',[(None,'All categories')]+list(TRANSACTION_DETAILS.items()),1)
        self.tx_party=self.filter_field(filters,'Party / Name',[(None,'All parties')]+self.party_choices(),2)
        self.tx_cash=self.filter_field(filters,'Cash / Bank',[(None,'All payment accounts')]+self.cash_choices(),3)
        self.tx_extra=ttk.Frame(filters,style='Card.TFrame')
        for column,(key,title) in enumerate([('tx_min','Minimum amount (₹)'),('tx_max','Maximum amount (₹)')]):
            frame=ttk.Frame(self.tx_extra,style='Card.TFrame'); frame.grid(row=0,column=column,sticky='ew',padx=(0,12),pady=(0,10))
            ttk.Label(frame,text=title,style='Field.TLabel').pack(anchor='w',pady=(0,6))
            entry=ttk.Entry(frame,width=15); entry.pack(fill='x'); setattr(self,key,entry); self.tx_extra.columnconfigure(column,weight=1)
        cats=self.db.all('SELECT * FROM categories ORDER BY name')
        self.tx_category=self.filter_field(self.tx_extra,'Income / expense heading',[(None,'All headings')]+[(c['id'],c['name']) for c in cats],2)
        actions=ttk.Frame(filters,style='Card.TFrame'); actions.grid(row=2,column=0,columnspan=4,sticky='ew')
        ttk.Button(actions,text='Apply filters',style='Primary.TButton',command=lambda:self.guard(self.filter_transactions)).pack(side='left')
        ttk.Button(actions,text='Reset',style='Subtle.TButton',command=self.clear_transactions).pack(side='left',padx=5)
        self.tx_more=ttk.Button(actions,text='+ More filters',style='Subtle.TButton',command=self.toggle_transaction_filters); self.tx_more.pack(side='left')
        ttk.Button(actions,text='Export CSV',style='Subtle.TButton',command=lambda:self.guard(self.export_transactions)).pack(side='right')
        ttk.Button(actions,text='Cash book report',style='Subtle.TButton',command=self.open_cashbook_report).pack(side='right',padx=5)
        bar=ttk.Frame(self.content); bar.pack(fill='x',pady=(4,4))
        ttk.Label(bar,text='Entries',style='Section.TLabel').pack(side='left')
        self.tx_info=ttk.Label(bar,text='',style='Muted.TLabel'); self.tx_info.pack(side='left',padx=12)
        self.tx_sort=ttk.Combobox(bar,values=['Newest first','Oldest first','Amount low to high','Amount high to low','Party','Reference'],state='readonly',width=20); self.tx_sort.set('Oldest first'); self.tx_sort.pack(side='right')
        ttk.Label(bar,text='Sort by',style='Muted.TLabel').pack(side='right',padx=8)
        self.tx_sort.bind('<<ComboboxSelected>>',lambda e:self.guard(self.filter_transactions))
        pagination=ttk.Frame(self.content); pagination.pack(side='bottom',fill='x',pady=(12,0))
        ttk.Button(pagination,text='Previous',command=lambda:self.tx_move(-1)).pack(side='left')
        ttk.Button(pagination,text='Next',command=lambda:self.tx_move(1)).pack(side='left',padx=8)
        ttk.Label(pagination,text='50 entries per page · Double-click for details',style='Muted.TLabel').pack(side='right')
        self.tx_body=ttk.Frame(self.content); self.tx_body.pack(fill='both',expand=True)
        self.tx_search.bind('<Return>',lambda e:self.guard(self.filter_transactions))
        self.filter_transactions()

    def toggle_transaction_filters(self):
        if self.tx_extra.winfo_manager():
            self.tx_extra.grid_remove(); self.tx_more.configure(text='+ More filters')
        else:
            self.tx_extra.grid(row=1,column=0,columnspan=4,sticky='ew'); self.tx_more.configure(text='− Fewer filters')

    def clear_transactions(self):
        for entry in (self.tx_search,self.tx_min,self.tx_max): entry.delete(0,'end')
        for combo in (self.tx_type,self.tx_party,self.tx_cash,self.tx_category): combo.select_key(None)
        self.tx_sort.set('Oldest first'); self.guard(self.filter_transactions)

    def filter_transactions(self):
        rows=self.ledger.entries(self.start,self.end,cash_id=self.tx_cash.selected(),party_id=self.tx_party.selected(),type=self.tx_type.selected(),category_id=self.tx_category.selected())
        term=self.tx_search.get().casefold().strip()
        minimum=paise(self.tx_min.get()) if self.tx_min.get().strip() else None
        maximum=paise(self.tx_max.get()) if self.tx_max.get().strip() else None
        if minimum is not None and maximum is not None and minimum>maximum: raise ValueError('Minimum amount exceeds maximum.')
        self.tx_rows=[r for r in rows if (not term or term in ' '.join(str(r.get(k) or '') for k in ('reference','external_ref','party_name','finance_reference','notes','particulars','category_name')).casefold() or term in transaction_detail(r['type']).casefold() or term in TYPES[r['type']].label.casefold()) and (minimum is None or r['amount_paise']>=minimum) and (maximum is None or r['amount_paise']<=maximum)]
        sorting=self.tx_sort.get()
        if sorting in ('Newest first','Oldest first'): self.tx_rows.sort(key=lambda r:(r['tx_date'],r['created_at'],r['id']),reverse=sorting=='Newest first')
        elif sorting.startswith('Amount'): self.tx_rows.sort(key=lambda r:r['amount_paise'],reverse=sorting=='Amount high to low')
        elif sorting=='Party': self.tx_rows.sort(key=lambda r:(r['party_name'] or '').casefold())
        else: self.tx_rows.sort(key=lambda r:r['reference'])
        _,_,self.tx_balances=cashbook_balances(self.ledger,self.start,self.end,self.tx_cash.selected())
        self.tx_page=0; self.render_transactions()

    def tx_move(self,delta):
        if 0<=self.tx_page+delta<max(1,(len(self.tx_rows)+49)//50): self.tx_page+=delta; self.render_transactions()

    def render_transactions(self):
        for child in self.tx_body.winfo_children(): child.destroy()
        rows=self.tx_rows[self.tx_page*50:self.tx_page*50+50]
        table(self.tx_body,['S.No','Transaction Details / Category','Date','Name','Particulars','Cash In','Cash Out','Cash Balance'],[[self.tx_page*50+i+1,('Reversal: ' if r['factor']==-1 else '')+transaction_detail(r['type']),r['tx_date'],r['party_name'] or '',r['particulars'],r['amount_paise']*r['factor'] if r['direction']==1 else 0,r['amount_paise']*r['factor'] if r['direction']==-1 else 0,self.tx_balances.get(r['id'],'')] for i,r in enumerate(rows)],{5,6,7},identifiers=[r['id'] for r in rows],widths=[50,190,100,120,140,100,100,120],on_open=lambda iid:self.transaction_detail(next(r['group_id'] for r in rows if r['id']==int(iid))))
        self.tx_info.configure(text=f'{len(self.tx_rows)} entries · page {self.tx_page+1} / {max(1,(len(self.tx_rows)+49)//50)}')

    def export_transactions(self):
        self.filter_transactions()
        report=Report('Filtered Cash Book',f'{self.start} to {self.end}', ['S.No','Transaction Details / Category','Date','Name','Particulars','Cash In','Cash Out','Cash Balance','Cash / Bank','Finance account','Reference','Method','External reference','Notes','Created by','Created at UTC','Reversal of'],[[i+1,transaction_detail(r['type']),r['tx_date'],r['party_name'] or '',r['particulars'],r['amount_paise']*r['factor'] if r['direction']==1 else 0,r['amount_paise']*r['factor'] if r['direction']==-1 else 0,self.tx_balances.get(r['id'],''),r['cash_name'],r['finance_reference'] or '',r['reference'],r['method'],r['external_ref'],r['notes'],r['created_by'],r['created_at'],r['reversal_of'] or ''] for i,r in enumerate(self.tx_rows)],{5,6,7},['Cash balance is actual chronological cash across the selected payment accounts, including entries hidden by category/search filters. It is not recomputed by sort order.'])
        self.save_report(report,'.csv')

    def transaction_detail(self,group_id):
        group=self.db.one('SELECT * FROM posting_groups WHERE id=?',(group_id,))
        rows=[r for r in self.ledger.entries() if r['group_id']==group_id]
        window=tk.Toplevel(self); window.title(group['reference']); window.geometry('1000x540')
        body=ttk.Frame(window,padding=20); body.pack(fill='both',expand=True)
        ttk.Label(body,text=group['reference'],style='Title.TLabel').pack(anchor='w')
        ttk.Label(body,text=f'Date: {group["tx_date"]}   Method: {group["method"]}\nCreated by {group["created_by"]} at {group["created_at"]} (UTC)\nExternal reference: {group["external_ref"]}\nParticulars: {group["particulars"]}\nNotes: {group["notes"]}\nReversal of: {group["reversal_of"] or "—"}',wraplength=900).pack(anchor='w',pady=12)
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
        self.report_name=ttk.Combobox(bar,values=REPORT_NAMES,state='readonly',width=42); self.report_name.set(self.active_report); self.report_name.pack(side='left')
        ttk.Button(bar,text='Generate report',style='Primary.TButton',command=lambda:self.guard(self.generate_report)).pack(side='left',padx=10)
        filters=card(self.content,16); filters.pack(fill='x',pady=(8,8))
        self.report_party=self.filter_field(filters,'Party / Name',[(None,'All parties')]+self.party_choices(),0)
        self.report_finance=self.filter_field(filters,'Finance account',[(None,'All finance accounts')]+self.finance_choices(),1)
        self.report_cash=self.filter_field(filters,'Cash / Bank',[(None,'All payment accounts')]+self.cash_choices(),2)
        self.report_module=self.filter_field(filters,'Module',[(None,'All modules')]+list(MODULES.items()),0,1)
        self.report_status=self.filter_field(filters,'Account status',[(None,'All statuses')]+[(s,s.title()) for s in ('active','matured','closed')],1,1)
        self.report_type=self.filter_field(filters,'Transaction category',[(None,'All transaction categories')]+list(TRANSACTION_DETAILS.items()),2,1)
        self.report_body=ttk.Frame(self.content); self.report_body.pack(fill='both',expand=True,pady=10)
        self.generate_report()

    def open_cashbook_report(self):
        self.active_report=CASHBOOK_REPORT
        self.show('Reports')

    def generate_report(self):
        self.active_report=self.report_name.get()
        category=next((key for key,label in CATEGORY_REPORTS.items() if label==self.active_report),None)
        if category:
            self.report_type.select_key(category); self.report_type.configure(state='disabled')
        elif self.report_type.cget('state')=='disabled':
            self.report_type.configure(state='normal'); self.report_type.select_key(None)
        report=build_report(self.ledger,self.report_name.get(),self.start,self.end,party_id=self.report_party.selected(),finance_id=self.report_finance.selected(),cash_id=self.report_cash.selected(),module=self.report_module.selected(),status=self.report_status.selected(),type=self.report_type.selected())
        for child in self.report_body.winfo_children(): child.destroy()
        self.report_widget(self.report_body,report)

    def report_widget(self,parent,report):
        header=ttk.Frame(parent); header.pack(fill='x')
        ttk.Label(header,text=report.title,style='Section.TLabel',wraplength=440).pack(side='left')
        for label,suffix in [('CSV','.csv'),('Excel','.xlsx'),('PDF / Print','.pdf')]:
            ttk.Button(header,text=label,command=lambda suffix=suffix:self.guard(lambda:self.save_report(report,suffix))).pack(side='right',padx=4)
        ttk.Label(parent,text=report.period,style='Muted.TLabel').pack(anchor='w',pady=6)
        def open_account(index):
            if report.columns and report.columns[0]=='Account':
                reference=report.rows[int(index)][0]
                account=next((a for a in self.ledger.finance_accounts() if a['reference']==reference),None)
                if account: self.finance_detail(account['id'])
        table(parent,report.columns,report.rows,report.money_columns,on_open=open_account if report.columns and report.columns[0]=='Account' else None)
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
        ttk.Label(area,text='General income & expense headings',style='Section.TLabel').pack(anchor='w',pady=(24,8))
        cats=self.db.all('SELECT * FROM categories ORDER BY name')
        ttk.Label(area,text=' · '.join(c['name']+' ('+c['kind']+')' for c in cats),wraplength=850).pack(anchor='w')
        ttk.Button(area,text='+ Add income / expense heading',command=self.category_form).pack(anchor='w',pady=10)
        ttk.Label(area,text='Audit history',style='Section.TLabel').pack(anchor='w',pady=(15,5))
        ttk.Label(area,text='Posted records cannot be edited or deleted. Corrections use linked reversals and replacement postings.',style='Muted.TLabel').pack(anchor='w')
        ttk.Button(area,text='View audit history',command=self.audit_window).pack(anchor='w',pady=10)

    def category_form(self):
        def save(form):
            v=form.values(); self.ledger.add_category(v['name'],v['kind']); self.show(self.page)
        form=Form(self,'Add Income / Expense Heading',save)
        form.add('name','Heading name *'); form.add('kind','Kind','expense',choices=['income','expense'])

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
