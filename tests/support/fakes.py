"""Transaction fakes: no connection to MySQL."""
import app as site


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.lastrowid = 0
        self.result = None
        self.closed = False

    def execute(self, sql, params=()):
        if 'SELECT DISTINCT artist' in sql:
            self.result = [{'artist': f'Existing{i}'} for i in params]
        elif 'SELECT song_id' in sql:
            song_id = self.db.ids.get(tuple(params))
            self.result = {'song_id': song_id} if song_id is not None else None
        elif 'INSERT INTO tracks' in sql:
            self.lastrowid = self.db.next_id
            self.db.next_id += 1
            self.db.ids[tuple(params)] = self.lastrowid
        elif 'INSERT INTO spotify_chart' in sql:
            self.db.writes += 1
            if self.db.fail_write == self.db.writes:
                raise RuntimeError('TEST INSERT FAILURE')
        else:
            raise AssertionError('Unexpected SQL')

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result

    def close(self):
        self.closed = True


class FakeDB:
    def __init__(self, fail_commit=False, fail_write=None, next_id=100):
        self.fail_commit = fail_commit
        self.fail_write = fail_write
        self.next_id = next_id
        self.ids = {}
        self.writes = 0
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.selection_at_commit = None
        self.cur = FakeCursor(self)
        self.commit_hook = None

    def cursor(self, **kwargs):
        return self.cur

    def commit(self):
        self.selection_at_commit = list(site.analysis_song_ids)
        if self.commit_hook:
            self.commit_hook()
        if self.fail_commit:
            raise RuntimeError('TEST COMMIT FAILURE')
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True
