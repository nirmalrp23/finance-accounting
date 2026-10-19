import argparse
import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description='Offline Finance Ledger')
    parser.add_argument('--demo',action='store_true',help='Use a separate demo database with labelled sample data')
    parser.add_argument('--data-dir',type=Path,help='Override data directory (testing or portable recovery only)')
    args=parser.parse_args()
    from .storage import Database, data_directory
    directory=args.data_dir or data_directory(args.demo)
    database=None
    try:
        directory.mkdir(parents=True,exist_ok=True)
        handler=RotatingFileHandler(directory/'application.log',maxBytes=1_000_000,backupCount=3,encoding='utf-8')
        logging.basicConfig(level=logging.ERROR,handlers=[handler])
        database=Database(directory)
        if args.demo:
            from .demo import seed_demo
            seed_demo(database)
        from .ui import Application
        app=Application(database,args.demo)
        def callback_error(kind,value,traceback):
            logging.error('Desktop action failed',exc_info=(kind,value,traceback))
            from tkinter import messagebox
            messagebox.showerror('Finance Ledger',f'The action failed: {value}\nYour entered values have been kept. See application.log for details.',parent=app)
        app.report_callback_exception=callback_error
        app.mainloop()
    except Exception as exc:
        logging.exception('Application startup failed')
        try:
            import tkinter as tk
            from tkinter import messagebox
            root=tk.Tk(); root.withdraw()
            messagebox.showerror('Finance Ledger could not start',str(exc),parent=root)
            root.destroy()
        except Exception:
            print(f'Finance Ledger could not start: {exc}',file=sys.stderr)
        return 1
    finally:
        if database: database.close()
    return 0


if __name__=='__main__':
    sys.exit(main())
