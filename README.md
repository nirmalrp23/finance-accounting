# Finance Ledger

An offline, single-business Windows desktop ledger built with Python 3, Tkinter/ttk and SQLite. There are no accounts to sign into, server processes, web dependencies or cloud services. The packaged application needs no Python installation or internet access. Dependencies are downloaded only when setting up a development environment or building the distribution; they are bundled for end users.

## Run from source

Use Python 3.11 or newer with Tk support (the standard python.org Windows installer includes Tcl/Tk). Python 3.13 is the development/test version used here.

Windows PowerShell, from this folder:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run_ledger.py
# Separate demonstration workspace:
.venv\Scripts\python.exe run_ledger.py --demo
```

After setup, `Start-FinanceLedger.bat` or `Start-Demo.bat` launches without a console. Python's standard library alone supports the app and CSV export; openpyxl and reportlab enable Excel and PDF exports. The Windows bundle includes both.

macOS/Linux development:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run_ledger.py --demo
```

Linux may require your distribution's `python3-tk` package. On macOS use Python with Tcl/Tk support. A display is required for the desktop interface; domain tests do not need one.

## Interface update (version 1.2)

A refreshed desktop theme adds a compact sidebar, grouped/searchable category reports, clearer amounts and flat table headers with sort indicators. Dashboard cards adapt to narrower desktop widths; principal and actual interest appear in separate panels. The single entry form uses labelled sections, side-by-side fields, **+ New name / + New account** actions and a collapsed **Additional details** section for references and notes. Required inputs remain visible and errors retain the form data. Mouse-wheel scrolling and keyboard focus scrolling are supported in long forms.

Cash Book filters now have explicit labels and **More filters** for amount limits and income/expense headings. **Reset** clears the filters without changing the selected dates. Reports use the same labelled filter layout. The update changes presentation only: the ledger calculations, stored postings, database version, backups and migration rules are unchanged from version 1.1.

## Single Cash Book entry (version 1.2)

All transaction entry is in **Cash Book Entry** (Ctrl+N or **Add Cash Book Entry**). Category is the **Transaction Details** from the reference cash book. It automatically determines Cash In / Cash Out; you enter one amount, not a conflicting direction. The form shows only the fields relevant to that category.

1. In **Settings**, enter the business name. In **Cash & Bank**, add the cash/bank accounts and money already held as an opening balance.
2. Open **Cash Book Entry**, choose a category and date, then select an existing name or click **+ New name** and fill in the name/contact details in this same form. For office expenses or general income, the name is optional; choose **No party (particulars only)** when appropriate.
3. For an FD/loan category, choose an existing matching finance account or click **+ New account**. The same form collects its reference (or generates one), opening date, annual interest rate, payout frequency and optional due/maturity date. Keep brought-forward principal at zero for a new deposit/disbursement; use it only for principal already outstanding before this entry.
4. Enter **Particulars / Description** separately from the party name. For example, Water Can, Salary or Rent describe an office expense without creating a fictitious party. Enter the amount, cash/bank account, method, optional external reference and notes. STL LOAN CREDIT also accepts a separate actual-interest amount for an atomic split receipt.
5. Save once. A new party, new account, posting components and their audit rows commit together. If validation fails, entered values remain and no unused party/account is left behind. Retrying the same successful submission cannot create duplicates.
6. The **Cash Book** lists S.No, Transaction Details, Date, Name, Particulars, Cash In, Cash Out, chronological Cash Balance, payment account and reference. Filter/search by name, particulars, date, account, category, heading, reference and amount; sort and page through 50 rows at a time. Actual running cash is calculated in date order across the selected payment accounts, including records hidden by category/search filters. Sorting does not recalculate cash balances. Internal transfers leave the overall business cash unchanged.
7. **Reports by category** in the sidebar groups the 18 report-only entries under STL loans, Fixed deposits, External loans, Hand loans given, Finance hand loans and General & transfers. Expand a group or type in the report search field to find an entry. These include STL LOAN DEBIT/CREDIT/INTEREST CREDIT, FD CREDIT/DEBIT/INTEREST DEBIT, EXTERNAL LOAN entries, HAND LOAN entries, FINANCE HAND LOAN entries, OFFICE EXPENSES, OTHER INCOME and CASH / BANK TRANSFER. These menus never open a creation form. **Reports** also keeps the overall cash book, grouped summaries, statements, principal, monthly and actual-interest reports. Export locally to CSV, Excel or PDF.

STL loans and Hand Loans are money lent by this business. External Loans and Finance Hand Loans are money borrowed by this business. FD remains customer money deposited with the business. The fixed category names use CREDIT/DEBIT to match the reference, with explicit **Cash In / Amount In** and **Cash Out / Amount Out** explanations. Principal and interest accounting remain separate. Income/expense headings in Settings are optional reporting sub-classifications, distinct from the main Transaction Details category.

Type in selectors to narrow the dropdown. Tab/Shift+Tab navigate, Ctrl+Enter saves, Escape cancels, and F5 refreshes. Long forms scroll with keyboard focus. New names/accounts are created through this single entry form; existing party/contact details and existing finance terms/status can still be edited from their detail views. Cash/bank setup and Settings remain separate administrative screens.

Double-click a party for linked accounts and statements. Double-click an account in a grouped summary for its statement, editable terms/status and optional simple-interest estimate. Double-click a cash-book entry for linked components, audit details and reversal. Reversal requires a reason and explicit confirmation; it retains the original and reverses all split/transfer components together. Particulars are retained on the reversal. Post a replacement through the same Cash Book Entry form. Closed accounts must be explicitly reopened before posting/reversing; closing requires zero outstanding principal.

Updating an existing installation to 1.1 keeps the same data folder and installer identity. Database migration 2 adds Particulars and the unified-intake idempotency fingerprint, after creating a pre-migration backup. Existing postings, accounts, audit records and balances are preserved. Older version-1 backups are validated and upgraded when restored. No workbook data is imported automatically.

## Accounting conventions

- INR; amounts stored as **integer paise**. Entry parsing and interest calculations use Python Decimal; no float arithmetic in ledger calculations. Indian digit grouping is used on screen and in PDF. CSV has exact rupee decimals suitable for spreadsheets; Excel stores numeric rupee values so they can be analysed, with display grouping controlled by the workbook/viewer's number format.
- FD: a customer's money deposited with this business, hence a principal **liability**. Principal received is Amount In; principal repaid and FD interest paid are Amount Out.
- Loans: money lent by this business, hence a principal **receivable**. Disbursement is Amount Out; repayments and actual interest received are Amount In.
- Other finance: money borrowed from an external finance provider, hence a principal **liability**. Receipt is Amount In; repayment and interest paid are Amount Out.
- Hand loans given are receivables; hand loans taken are liabilities. Interest-free accounts use a zero agreed rate.
- Principal receipts are not income and principal payments are not expenses. Actual interest is reported separately from principal. **Net cash movement is not profit.** General income/expense has configurable categories.
- Transfers post linked Amount Out and Amount In atomically. They affect individual cash/bank ledgers but do not inflate overall Amount In/Out, general income/expense or interest reports.
- Opening cash and opening principal are dated non-cash introductions, never fictional period receipts or expenses. Balances are derived, never independently editable.
- Dates use ISO `YYYY-MM-DD`, SQLite TEXT with strict application validation and date comparisons; audit timestamps include a UTC offset. Default business date is Asia/Kolkata, independent of the PC's timezone.
- Principal checks replay **the entire dated timeline**, including later postings, so a backdated repayment or reversal cannot make a later day's principal negative. End-of-day principal cannot go below zero. Cash/bank overdrafts are allowed; they are shown as negative balances.
- Interest estimates use `sum(dated outstanding principal × actual days) × annual rate / 100 / 365`. Start is inclusive, end exclusive, and movements take effect on their transaction date. Round once to paise, half up. The estimate uses the currently agreed rate for the entire requested interval (rate edits remain in audit history). Estimates are labelled, never posted automatically and never included in actual-interest reports. No EMI, compounding, penalties or accruals are implemented.
- Reversals reduce the original direction's total on the **reversal date**. A reversal next month leaves the original month's historical report unchanged and appears as a negative Amount In/Out next month. Principal/interest components remain separate and original audit history is preserved.

## Reports

Complete cash-book layout and all 18 transaction-category reports; overall Amount In/Out; cash book and individual bank ledger; FD summary and individual statement; loan summary and individual statement; other finance summary and statement; hand loans given/taken; actual interest received; actual interest paid split by FD/other finance/hand loan; party statement; principal outstanding as of a date; monthly summary; general income/expense.

Statements include opening, movements, totals and closing with chronological running cash or principal balances as relevant. Summary reports separate receivables from liabilities and show opening/closing principal reconstructed at the selected date. Dates never substitute today's principal. Party statements include per-account principal and separate principal/actual-interest In/Out totals. Monthly reports include quiet months, opening, closing, net movement and actual-interest totals. Full-scope overall reports include cash opening balances and explicitly list non-cash opening introductions. When narrowed to a party/module/type, an overall report's running balance is cumulative filtered net movement, clearly explained in the report; use an individual statement for principal balances. Status filters refer to the account's current recorded status.

Payment-account ledgers should normally be run without module/type filters to show the full actual cash balance. Applying movement filters gives a filtered ledger against the actual opening balance, explained in its notes. Account statements deliberately use all that account's movements so opening-to-closing principal remains coherent. Transaction list CSV export includes all filtered pages, method, external reference, notes, creator, timestamp and reversal links. Settings provides the full audit CSV export. CSV/Excel text is escaped against spreadsheet formula injection. PDF uses `Rs` to avoid missing rupee glyphs in built-in PDF fonts.

## Storage, backups and updates

Production Windows data is always outside the installation folder:

```text
%LOCALAPPDATA%\FinanceLedger\
  ledger.sqlite3
  ledger.sqlite3-wal / ledger.sqlite3-shm   (SQLite-managed while running)
  application.lock
  application.log                         (rotated error log)
  backups\
    daily-YYYY-MM-DD.sqlite3
    pre-migration-<timestamp>.sqlite3
    pre-restore-<timestamp>.sqlite3
```

Demo uses `%LOCALAPPDATA%\FinanceLedgerDemo` instead. Production starts empty; no demo data is automatically inserted there. Demo seed rows are marked DEMO and match the supplied example. On macOS the corresponding folder is `~/Library/Application Support/FinanceLedger[Demo]`; on Linux it is `$XDG_DATA_HOME/FinanceLedger[Demo]` (default `~/.local/share`). `--data-dir PATH` overrides the location for explicit testing/recovery; never point multiple installations at a shared network or synchronised folder.

An OS-owned file lock prevents a second application instance using the same data folder; the OS releases it after a crash. SQLite foreign keys, full synchronous writes, a busy timeout, WAL, parameterised SQL and `BEGIN IMMEDIATE` transactions protect related writes. Unique database constraints enforce references/idempotency keys; repeated identical submissions return the first posting, while altered submissions using that key are rejected. Posted entries, groups and audit rows have database triggers blocking UPDATE/DELETE. A single central posting service derives directions and validates module/account links. The local database is not encrypted and relies on Windows user/file access; there is intentionally no login or user management.

**Backup Database:** select a folder or USB drive in Settings. A new timestamped, consistent, standalone SQLite file is produced with SQLite's backup API and validated before success is reported. The complete validated file is published atomically; a failed backup does not appear as a successful daily backup. Existing files are never overwritten. Do not copy the live SQLite file manually while the app is running.

**Daily backup:** on the first successful launch of each Asia/Kolkata day, take a consistent backup; keep the latest 30 daily files. Manual, pre-migration and pre-restore backups are retained until you remove them yourself. A failed automatic backup stops startup with an error so it cannot silently skip the protection.

**Restore Backup:** validates application ID, supported schema version, exact expected tables/indexes/triggers, SQLite integrity and foreign keys before asking for confirmation. After confirmation it creates a pre-restore backup, then restores through SQLite's backup API and records the restore. If restoration or its migration fails, it reinstates the pre-restore data. A newer/unknown/invalid backup is rejected. The single-instance lock covers restore, and the UI refreshes. A pre-restore file remains available to recover the replaced records.

**Backups on the same disk do not protect against disk failure.** Save regular manual backups to a USB drive or another physical disk. All copies contain personal and financial data; keep them under your control.

Updates replace only the application folder; never delete the separate data folder. Versioned forward migrations live in `finance_ledger/schema.py`. Existing databases are backed up **before** each migration. A failing migration rolls back its SQL transaction. Databases from a newer application version are rejected without migration. Keep old backups when upgrading; supported older backups are migrated after restoration. Restore cannot recover transactions entered after the selected backup.

## Windows packaging

Build **on Windows**, with a matching Python architecture (64-bit Python recommended):

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts\gui_smoke.py
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm FinanceLedger.spec
.\dist\FinanceLedger\FinanceLedger.exe --demo
```

Or run `powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1` for dependency installation, domain tests and packaging. Run the GUI smoke check separately on an interactive Windows desktop.

`FinanceLedger.spec` creates a **one-folder**, windowed (`console=False`) build with Tcl/Tk, SQLite and export libraries. Distribute the **entire** `dist\FinanceLedger` folder, including `_internal`; do not copy just the EXE. For a shortcut, right-click `FinanceLedger.exe` → Send to → Desktop (create shortcut). An optional Inno Setup script is at `packaging\installer.iss`; after building, compile it with Inno Setup 6 (`ISCC.exe packaging\installer.iss`). It installs to the current user's Programs folder, offers a desktop shortcut and leaves business data/backups intact on uninstall. Close the app before an update. Keep the stable AppId for subsequent installers.

PyInstaller's output is specific to the build OS; build the Windows executable on Windows, not from this macOS checkout. See the [official PyInstaller operating-mode documentation](https://pyinstaller.org/en/stable/operating-mode.html).

For a build machine without internet, prepare wheels on an internet-connected Windows machine of the same Python version/architecture with `py -m pip download -r requirements-build.txt -d wheels`, transfer them with the source, then install with `.venv\Scripts\python.exe -m pip install --no-index --find-links wheels -r requirements-build.txt`.

## Build with GitHub Actions (no Windows development PC needed)

A Windows build workflow that runs on pushes to `master` and can also be triggered manually is included at `.github/workflows/windows-build.yml`. Put the source in a GitHub repository, including this hidden `.github` directory. In GitHub select **Actions → Build Finance Ledger for Windows → Run workflow**. The workflow runs the financial and desktop smoke tests on Windows, builds the one-folder executable, compiles the Inno Setup installer and uploads two downloadable artifacts:

- **FinanceLedger-Windows-Installer** contains `FinanceLedger-Setup.exe`.
- **FinanceLedger-Windows-Portable** contains the full application folder; extract everything before running `FinanceLedger.exe`.

This workflow has been prepared but has not been executed from this environment, which has no connected GitHub repository or Windows runner. A successful workflow run still needs a manual check of the packaged application and installer on the intended Windows PC. Build artifacts expire after 30 days; download and keep your distribution. The build uses GitHub-hosted infrastructure, but the installed application remains fully offline. See the [Windows runner software inventory](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md) and [artifact download documentation](https://github.com/actions/upload-artifact).

## Verification and limits

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q finance_ledger scripts run_ledger.py
.venv/bin/python scripts/gui_smoke.py   # requires a desktop display
```

Tests exercise direction mappings, all finance modules, exact integer/Decimal calculations, partial repayments, the supplied example, linked split receipts, reversals, historical/backdated balances, duplicate submissions, transfers, opening balances, closed accounts, constraints, immutable audit records, CSV safety, Excel/PDF generation, backups, restore, corruption/schema rejection, 30-day retention, cross-process locking and migration preservation/rollback. The GUI smoke uses only temporary sample data and exercises six main pages, all 18 report-only menus, the unified entry form, atomic new party/account creation, validation without data loss, a real split posting, office particulars without a party, search and detail windows.

The sample closes at **₹1,35,200**, with **₹50,000 FD owed**, **₹15,000 loan outstanding**, **₹500 actual interest received**, **₹300 actual interest paid** and **₹200 net interest income**.

Verification for version 1.2: **51 domain/export tests pass locally and on Windows**, including version-1 database/backup upgrades, unified-intake rollback/idempotency, separate category reports and particulars. The expanded six-page/18-report Tkinter GUI smoke also passes on both platforms, including report search, creation toggles, optional details, filters and data retention. The [Windows 1.2 build](https://github.com/nirmalrp23/finance-accounting/actions/runs/39566267050) for commit `194a1a4` successfully produced the one-folder executable and installer. Python compilation passes locally. Manual installation/startup checks of the packaged executable on the target PC are still required, including display scaling, antivirus interaction and printing. Source GUI smoke tests do not replace testing the frozen application. The interface is intended for a desktop of at least 960×640 logical pixels; larger tables scroll horizontally. Reports and filters run locally in memory, suitable for a small finance business; very large datasets will need query-backed pagination. PDF's bundled standard fonts support Latin text; full Indic-script PDF font shaping is not included. Excel numeric grouping may follow viewer locale. The app intentionally does not include networking, multi-user permissions, automatic interest posting, accrual accounting or EMI schedules.
