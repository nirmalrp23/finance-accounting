@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
 start "Finance Ledger" ".venv\Scripts\pythonw.exe" run_ledger.py
) else (
 pyw -3 run_ledger.py
)
