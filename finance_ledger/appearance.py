"""Desktop presentation only. No ledger rules or financial storage."""
import sys
import tkinter as tk
from tkinter import ttk
from .money import money

BG = '#f4f7f6'
WHITE = '#ffffff'
GREEN = '#16745b'
NAV = '#142e29'
INK = '#172f28'
MUTED = '#6d7f77'
LINE = '#e0e9e4'
PALE = '#e9f5ee'
AMBER = '#a96c25'
FONT = 'Segoe UI' if sys.platform == 'win32' else ('Helvetica Neue' if sys.platform == 'darwin' else 'DejaVu Sans')


def configure_theme(root):
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=(FONT,10), background=BG, foreground=INK)
    for name,bg in [('TFrame',BG),('Card.TFrame',WHITE),('Nav.TFrame',NAV)]:
        style.configure(name,background=bg,borderwidth=0)
    for name,bg,fg,size,weight in [
        ('TLabel',BG,INK,10,'normal'),('Title.TLabel',BG,INK,25,'bold'),
        ('Section.TLabel',BG,INK,13,'bold'),('Muted.TLabel',BG,MUTED,9,'normal'),
        ('Kicker.TLabel',BG,MUTED,9,'bold'),('Card.TLabel',WHITE,INK,10,'normal'),
        ('CardMuted.TLabel',WHITE,MUTED,9,'normal'),('CardTitle.TLabel',WHITE,INK,12,'bold'),
        ('Field.TLabel',WHITE,MUTED,9,'bold'),('DialogTitle.TLabel',WHITE,INK,22,'bold'),
        ('Info.TLabel',PALE,GREEN,9,'normal'),('In.TLabel',PALE,GREEN,10,'bold'),
        ('Out.TLabel','#fff4e6',AMBER,10,'bold'),('Error.TLabel','#fff0ed','#aa4036',10,'normal')]:
        style.configure(name,background=bg,foreground=fg,font=(FONT,size,weight))
    style.layout('TButton',[('Button.padding',{'sticky':'nswe','children':[('Button.label',{'sticky':'nswe'})]})])
    style.configure('TButton',padding=(15,10),background='#e9efeb',foreground=INK,borderwidth=0,font=(FONT,10,'bold'),anchor='center')
    style.map('TButton',background=[('active','#dce8e0'),('disabled','#eef2ef')],foreground=[('disabled','#9aa99f')])
    style.configure('Primary.TButton',background=GREEN,foreground=WHITE,padding=(18,11))
    style.map('Primary.TButton',background=[('active','#115c48'),('disabled','#a3beb0')],foreground=[('disabled',WHITE)])
    for name,bg,fg in [('QuickIn.TButton',GREEN,WHITE),('QuickOut.TButton','#bd433c',WHITE),('QuickInactive.TButton','#edf2f0',MUTED)]:
        style.configure(name,background=bg,foreground=fg,padding=(18,12),font=(FONT,11,'bold'))
        style.map(name,background=[('active',bg)],foreground=[('active',fg)])
    style.configure('Subtle.TButton',background=WHITE,foreground=MUTED,padding=(10,7))
    style.map('Subtle.TButton',background=[('active',PALE)],foreground=[('active',GREEN)])
    for name,bg,fg in [('Nav.TButton',NAV,'#a9c4b8'),('NavActive.TButton','#254b3e',WHITE)]:
        style.configure(name,background=bg,foreground=fg,padding=(16,11),anchor='w',font=(FONT,10,'bold'))
        style.map(name,background=[('active','#254b3e')],foreground=[('active',WHITE)])
    style.configure('TEntry',padding=(10,8),fieldbackground=WHITE,foreground=INK,bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,borderwidth=1)
    style.map('TEntry',bordercolor=[('focus',GREEN)],lightcolor=[('focus',GREEN)],darkcolor=[('focus',GREEN)])
    style.configure('TCombobox',padding=(10,7),fieldbackground=WHITE,background=WHITE,foreground=INK,arrowcolor=MUTED,bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,borderwidth=1,arrowsize=12)
    style.map('TCombobox',fieldbackground=[('readonly',WHITE),('disabled','#f0f4f1')],background=[('readonly',WHITE)],foreground=[('readonly',INK),('disabled',MUTED)],selectbackground=[('readonly',WHITE)],selectforeground=[('readonly',INK)],bordercolor=[('focus',GREEN)])
    style.configure('Amount.TEntry',font=(FONT,15,'bold'),foreground=GREEN,padding=(10,9))
    style.configure('NavSearch.TEntry',fieldbackground='#203e34',foreground=WHITE,bordercolor='#35564a',lightcolor='#35564a',darkcolor='#35564a',insertcolor=WHITE,padding=(9,7))
    style.configure('Treeview',rowheight=39,background=WHITE,fieldbackground=WHITE,foreground=INK,borderwidth=0,font=(FONT,10))
    style.layout('Treeview',[('Treeview.treearea',{'sticky':'nswe'})])
    style.configure('Treeview.Heading',font=(FONT,9,'bold'),padding=(12,12),background='#edf3ef',foreground=MUTED,borderwidth=0,relief='flat',lightcolor='#edf3ef',darkcolor='#edf3ef',bordercolor='#edf3ef')
    style.map('Treeview',background=[('selected','#def0e5')],foreground=[('selected','#12513c')])
    style.configure('ReportNav.Treeview',background=NAV,fieldbackground=NAV,foreground='#b7cdc3',rowheight=31,font=(FONT,9),borderwidth=0,indent=12)
    style.map('ReportNav.Treeview',background=[('selected','#254b3e')],foreground=[('selected',WHITE)])
    style.configure('TNotebook',background=BG,borderwidth=0,tabmargins=(0,0,0,8),lightcolor=BG,darkcolor=BG,bordercolor=BG)
    style.configure('TNotebook.Tab',padding=(18,10),background=BG,foreground=MUTED,borderwidth=0,font=(FONT,10,'bold'),lightcolor=BG,darkcolor=BG,bordercolor=BG)
    style.map('TNotebook.Tab',background=[('selected',PALE)],foreground=[('selected',GREEN)],lightcolor=[('selected',PALE)],darkcolor=[('selected',PALE)],bordercolor=[('selected',PALE)])
    style.configure('Horizontal.TSeparator',background=LINE,lightcolor=LINE,darkcolor=LINE,bordercolor=LINE,borderwidth=0)
    for orient,short in [('Vertical','ns'),('Horizontal','ew')]:
        style.layout(f'{orient}.TScrollbar',[(f'{orient}.Scrollbar.trough',{'sticky':'nswe','children':[(f'{orient}.Scrollbar.thumb',{'sticky':'nswe'})]})])
        style.configure(f'{orient}.TScrollbar',background='#cbd8d0',troughcolor=WHITE,borderwidth=0,arrowsize=9,width=9,gripcount=0)
        style.map(f'{orient}.TScrollbar',background=[('active','#a6bdb0')])
    style.configure('Nav.Vertical.TScrollbar',background='#35564a',troughcolor=NAV,bordercolor=NAV,lightcolor=NAV,darkcolor=NAV)
    return style


def card(parent, padding=18):
    return ttk.Frame(parent,style='Card.TFrame',padding=padding)


def metric_cards(parent, items):
    """Reflow at narrower desktop widths; amounts stay full INR values."""
    host=ttk.Frame(parent)
    host.pack(fill='x',pady=(4,18))
    panels=[]
    for title,value,subtitle,color in items:
        panel=tk.Frame(host,bg=WHITE,highlightbackground=LINE,highlightthickness=1)
        stripe=tk.Frame(panel,bg=color,height=3); stripe.pack(fill='x')
        tk.Label(panel,text=title,bg=WHITE,fg=MUTED,font=(FONT,10),anchor='w').pack(fill='x',padx=18,pady=(15,8))
        tk.Label(panel,text=money(value),bg=WHITE,fg=color,font=(FONT,22,'bold'),anchor='w').pack(fill='x',padx=18)
        tk.Label(panel,text=subtitle,bg=WHITE,fg=MUTED,font=(FONT,9),anchor='w').pack(fill='x',padx=18,pady=(8,16))
        panels.append(panel)
    state={'columns':0}
    def arrange(event=None):
        columns=4 if host.winfo_width()>=840 else 2
        if columns==state['columns']: return
        state['columns']=columns
        for i in range(4): host.columnconfigure(i,weight=1 if i<columns else 0,uniform='metrics')
        for i,panel in enumerate(panels):
            panel.grid(row=i//columns,column=i%columns,sticky='nsew',padx=(0,12 if i%columns<columns-1 else 0),pady=(0,10 if columns==2 else 0))
    host.bind('<Configure>',arrange)
    arrange()
    return host


def value_panel(parent,title,subtitle,values):
    panel=card(parent,20)
    ttk.Label(panel,text=title,style='CardTitle.TLabel').pack(anchor='w')
    ttk.Label(panel,text=subtitle,style='CardMuted.TLabel').pack(anchor='w',pady=(4,14))
    for index,(label,value,basis,color) in enumerate(values):
        if index: ttk.Separator(panel,orient='horizontal').pack(fill='x',pady=2)
        line=ttk.Frame(panel,style='Card.TFrame'); line.pack(fill='x',pady=9)
        left=ttk.Frame(line,style='Card.TFrame'); left.pack(side='left',fill='x',expand=True)
        ttk.Label(left,text=label,style='Card.TLabel').pack(anchor='w')
        if basis: ttk.Label(left,text=basis,style='CardMuted.TLabel').pack(anchor='w',pady=(3,0))
        tk.Label(line,text=money(value),bg=WHITE,fg=color,font=(FONT,13,'bold')).pack(side='right',padx=(12,0))
    return panel
