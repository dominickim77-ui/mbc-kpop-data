import unittest
from types import SimpleNamespace

from db.postgres_test_loader import load


class LoaderGuardTests(unittest.TestCase):
    def test_rejects_without_permission_before_connecting(self):
        with self.assertRaises(ValueError):
            load(object(), {})

    def test_rejects_remote_production_or_active_transaction(self):
        for host, name, status in [('supabase.com', 'kpop_step24_test_a', 0),
                                   ('localhost', 'production', 0),
                                   ('localhost', 'kpop_step24_test_a', 2)]:
            with self.subTest(host=host, name=name, status=status):
                conn = SimpleNamespace(info=SimpleNamespace(
                    host=host, dbname=name, transaction_status=status))
                with self.assertRaises(ValueError):
                    load(conn, {}, allow_test_database=True)
