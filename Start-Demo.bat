@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
 start "Finance Ledger Demo" ".venv\Scripts\pythonw.exe" run_ledger.py --demo
) else (
 pyw -3 run_ledger.py --demo
)
