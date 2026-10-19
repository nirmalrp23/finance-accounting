import getpass
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from .money import timestamp, today
from .schema import APPLICATION_ID, MIGRATIONS


class AlreadyRunning(RuntimeError):
    pass


def data_directory(demo=False):
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return base / ('FinanceLedgerDemo' if demo else 'FinanceLedger')


class InstanceLock:
    """OS-owned lock: automatically released on crash; no stale PID guessing."""
    def __init__(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.file = open(Path(directory) / 'application.lock', 'a+b')
        self.file.seek(0)
        if not self.file.read(1):
            self.file.write(b'0')
            self.file.flush()
        self.file.seek(0)
        try:
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise AlreadyRunning('Finance Ledger is already running for this data folder. Close the other window first.') from None

    def close(self):
        if self.file.closed:
            return
        if sys.platform == 'win32':
            import msvcrt
            self.file.seek(0)
            msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        self.file.close()


class Database:
    def __init__(self, directory, daily=True):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = InstanceLock(self.directory)
        self.path = self.directory / 'ledger.sqlite3'
        self.conn = None
        try:
            self.conn = sqlite3.connect(self.path, isolation_level=None, timeout=10)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute('PRAGMA foreign_keys=ON')
            self.conn.execute('PRAGMA busy_timeout=10000')
            self.conn.execute('PRAGMA synchronous=FULL')
            self._migrate()
            self.conn.execute('PRAGMA journal_mode=WAL')
            if daily:
                self.daily_backup()
        except Exception:
            self.close()
            raise

    @contextmanager
    def atomic(self):
        self.conn.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.conn.execute('COMMIT')
        except BaseException:
            self.conn.execute('ROLLBACK')
            raise

    def _migrate(self):
        current = self.conn.execute('PRAGMA user_version').fetchone()[0]
        app_id = self.conn.execute('PRAGMA application_id').fetchone()[0]
        tables = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if tables and app_id != APPLICATION_ID:
            raise ValueError('This is not a Finance Ledger database.')
        if current > MIGRATIONS[-1][0]:
            raise ValueError('This database needs a newer version of Finance Ledger. No records were changed.')
        for version, sql in MIGRATIONS:
            if version <= current:
                continue
            if tables:
                self.backup(self.unique_backup_path('pre-migration'))
            try:
                self.conn.executescript(f'BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version={version};\nPRAGMA application_id={APPLICATION_ID};\nCOMMIT;')
            except BaseException:
                if self.conn.in_transaction:
                    self.conn.rollback()
                raise

    def all(self, sql, args=()):
        return [dict(row) for row in self.conn.execute(sql, args)]

    def one(self, sql, args=()):
        row = self.conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    def audit(self, entity, entity_id, action, before=None, after=None):
        self.conn.execute('INSERT INTO audit_log(entity,entity_id,action,before_json,after_json,actor,at) VALUES(?,?,?,?,?,?,?)',
                          (entity, str(entity_id), action, json.dumps(before), json.dumps(after), getpass.getuser(), timestamp()))

    def unique_backup_path(self, prefix):
        folder = self.directory / 'backups'
        folder.mkdir(exist_ok=True)
        return folder / f'{prefix}-{datetime.now().strftime("%Y%m%d-%H%M%S-%f")}.sqlite3'

    def backup(self, target):
        target = Path(target).resolve()
        if target == self.path:
            raise ValueError('Choose a backup file outside the live database.')
        if target.exists():
            raise ValueError('That file already exists. Choose a new backup filename.')
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(prefix='.backup-', suffix='.sqlite3', dir=target.parent)
        os.close(handle)
        temporary = Path(name)
        try:
            with closing(sqlite3.connect(temporary)) as destination:
                self.conn.backup(destination)
                destination.execute('PRAGMA journal_mode=DELETE')
            self.validate_backup(temporary)
            if target.exists():
                raise ValueError('That backup filename has been created by another process. Choose another.')
            # Publish only a complete, validated file, on the same filesystem.
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def daily_backup(self):
        folder = self.directory / 'backups'
        folder.mkdir(exist_ok=True)
        target = folder / f'daily-{today()}.sqlite3'
        if not target.exists():
            self.backup(target)
        else:
            self.validate_backup(target)
        for path in sorted(folder.glob('daily-????-??-??.sqlite3'), reverse=True)[30:]:
            path.unlink()

    @staticmethod
    def validate_backup(path):
        path = Path(path).resolve()
        if not path.is_file():
            raise ValueError('The backup file does not exist.')
        expected = sqlite3.connect(':memory:')
        source = None
        try:
            source = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
            source.execute('PRAGMA trusted_schema=OFF')
            if source.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID:
                raise ValueError('Not a Finance Ledger backup.')
            version = source.execute('PRAGMA user_version').fetchone()[0]
            if version not in {item[0] for item in MIGRATIONS}:
                raise ValueError('Backup version is unsupported. Use the matching application version first.')
            if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup failed database integrity validation.')
            if source.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Backup contains broken record links.')
            for migration_version, sql in MIGRATIONS:
                if migration_version <= version:
                    expected.executescript(sql)
            schema_query = "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
            if source.execute(schema_query).fetchall() != expected.execute(schema_query).fetchall():
                raise ValueError('Backup schema is not recognised; restore cancelled.')
        except sqlite3.Error as exc:
            raise ValueError(f'Invalid backup: {exc}') from exc
        finally:
            expected.close()
            if source:
                source.close()
        return True

    def restore(self, path):
        path = Path(path).resolve()
        if path == self.path:
            raise ValueError('Select a backup, not the live database.')
        self.validate_backup(path)
        safety = self.backup(self.unique_backup_path('pre-restore'))
        try:
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as source:
                source.backup(self.conn)
            self._migrate()
            self.conn.execute('PRAGMA journal_mode=WAL')
            self.conn.execute('PRAGMA foreign_keys=ON')
            self.conn.execute('PRAGMA synchronous=FULL')
            with self.atomic():
                self.audit('database', '1', 'restore', after={'source': path.name, 'safety_backup': str(safety)})
        except BaseException:
            # Recovery from a migration/audit error after copying a valid older backup.
            with closing(sqlite3.connect(safety.as_uri() + '?mode=ro', uri=True)) as original:
                original.backup(self.conn)
            self.conn.execute('PRAGMA journal_mode=WAL')
            raise
        return safety

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
        self.lock.close()
