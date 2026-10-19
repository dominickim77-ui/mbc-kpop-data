"""MySQL 8.0 schema comparison. No data repair or production DDL is supported."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DB = re.compile(r'mbc_kpop_step19_test_[a-z0-9_]+\Z')
TABLES = ('tracks', 'spotify_chart', 'youtube_stats')
TARGETS = {'spotify_chart': 'uq_spotify_song_chart',
           'youtube_stats': 'uq_youtube_video_collected'}


class SchemaError(ValueError):
    """Stop before DDL when destination or existing structure is unsafe."""


def load_manifest():
    return json.loads((ROOT / 'db/schema_manifest.json').read_text(encoding='utf-8'))


def inspect_schema(connection):
    """SELECT metadata only; caller controls the connection/transaction."""
    queries = {
        'database': 'SELECT DATABASE() AS database_name, VERSION() AS server_version',
        'schema': 'SELECT DEFAULT_CHARACTER_SET_NAME,DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=DATABASE()',
        'tables': 'SELECT TABLE_NAME,TABLE_TYPE,ENGINE,TABLE_COLLATION FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME',
        'columns': 'SELECT TABLE_NAME,ORDINAL_POSITION,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA,CHARACTER_SET_NAME,COLLATION_NAME,DATETIME_PRECISION,GENERATION_EXPRESSION FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME,ORDINAL_POSITION',
        'indexes': 'SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME,SUB_PART,INDEX_TYPE,IS_VISIBLE,EXPRESSION,COLLATION FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX',
        'foreign_keys': 'SELECT k.TABLE_NAME,k.CONSTRAINT_NAME,k.ORDINAL_POSITION,k.COLUMN_NAME,k.REFERENCED_TABLE_SCHEMA,k.REFERENCED_TABLE_NAME,k.REFERENCED_COLUMN_NAME,r.UPDATE_RULE,r.DELETE_RULE FROM information_schema.KEY_COLUMN_USAGE k JOIN information_schema.REFERENTIAL_CONSTRAINTS r ON k.CONSTRAINT_SCHEMA=r.CONSTRAINT_SCHEMA AND k.TABLE_NAME=r.TABLE_NAME AND k.CONSTRAINT_NAME=r.CONSTRAINT_NAME WHERE k.CONSTRAINT_SCHEMA=DATABASE() ORDER BY k.TABLE_NAME,k.CONSTRAINT_NAME,k.ORDINAL_POSITION',
        'constraints': 'SELECT TABLE_NAME,CONSTRAINT_NAME,CONSTRAINT_TYPE,ENFORCED FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME,CONSTRAINT_NAME',
        'triggers': 'SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE()',
        'routines': 'SELECT ROUTINE_NAME FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=DATABASE()',
    }
    cursor = connection.cursor(dictionary=True)
    try:
        result = {}
        for name, query in queries.items():
            cursor.execute(query)
            result[name] = cursor.fetchall()
        return result
    finally:
        cursor.close()


def index_groups(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row['TABLE_NAME'], row['INDEX_NAME']), []).append(row)
    return {key: sorted(values, key=lambda r: r['SEQ_IN_INDEX']) for key, values in groups.items()}


def index_signature(rows):
    first = rows[0]
    return (int(first['NON_UNIQUE']), first['INDEX_TYPE'], first.get('IS_VISIBLE', 'YES'),
            tuple((r['COLUMN_NAME'], r['SUB_PART'], r.get('EXPRESSION'), r.get('COLLATION', 'A'))
                  for r in rows))


def fk_groups(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row['TABLE_NAME'], row['CONSTRAINT_NAME']), []).append(row)
    return {key: sorted(values, key=lambda r: r.get('ORDINAL_POSITION', 1))
            for key, values in groups.items()}


def fk_signature(rows):
    return (tuple((r['COLUMN_NAME'], r['REFERENCED_TABLE_NAME'], r['REFERENCED_COLUMN_NAME']) for r in rows),
            rows[0]['UPDATE_RULE'], rows[0]['DELETE_RULE'])


def compare_schema(actual, expected=None):
    expected = expected or load_manifest()
    errors, warnings, missing = [], [], []
    if actual['schema'] != expected['schema']:
        errors.append('Database charset/collation differs from the manifest')
    if actual['tables'] != expected['tables']:
        errors.append('Table inventory, engine, or collation differs from the manifest')
    # Counters, row counts and constraint names are not structural equivalence tests.
    column_keys = ('TABLE_NAME', 'ORDINAL_POSITION', 'COLUMN_NAME', 'COLUMN_TYPE',
                   'IS_NULLABLE', 'COLUMN_DEFAULT', 'EXTRA', 'CHARACTER_SET_NAME',
                   'COLLATION_NAME', 'DATETIME_PRECISION', 'GENERATION_EXPRESSION')
    canonical = lambda rows: [tuple(r.get(k, '' if k == 'GENERATION_EXPRESSION' else None)
                                   for k in column_keys) for r in rows]
    if canonical(actual['columns']) != canonical(expected['columns']):
        errors.append('Column definition/order differs from the manifest')
    actual_indexes, expected_indexes = index_groups(actual['indexes']), index_groups(expected['indexes'])
    for (table, name), rows in expected_indexes.items():
        signature = index_signature(rows)
        matches = [(key, values) for key, values in actual_indexes.items()
                   if key[0] == table and index_signature(values) == signature]
        if matches:
            if not any(key[1] == name for key, _ in matches):
                warnings.append(f'{table}: equivalent index has a different name ({name})')
        elif TARGETS.get(table) == name:
            missing.append({'table': table, 'index': name})
        else:
            errors.append(f'{table}: required index {name} is missing or incompatible')
        if (table, name) in actual_indexes and index_signature(actual_indexes[(table, name)]) != signature:
            errors.append(f'{table}: index name {name} exists with an incompatible definition')
    for (table, name), rows in actual_indexes.items():
        signature = index_signature(rows)
        if any(key[0] == table and index_signature(value) == signature
               for key, value in expected_indexes.items()):
            continue
        # Legacy FK support may survive adding the covering Spotify UNIQUE index.
        if table == 'spotify_chart' and signature == (1, 'BTREE', 'YES', (('song_id', None, None, 'A'),)):
            warnings.append(f'{table}: retained FK support index {name}')
        else:
            errors.append(f'{table}: unexpected or incompatible index {name}')
    actual_fks, expected_fks = fk_groups(actual['foreign_keys']), fk_groups(expected['foreign_keys'])
    fk_set = lambda groups: Counter((key[0], fk_signature(rows)) for key, rows in groups.items())
    if fk_set(actual_fks) != fk_set(expected_fks):
        errors.append('Foreign key relationship or ON UPDATE/DELETE rule differs')
    database = actual['database'][0]['database_name']
    if any(r.get('REFERENCED_TABLE_SCHEMA', database) != database for r in actual['foreign_keys']):
        errors.append('Cross-database foreign key is not allowed')
    for key, rows in actual_fks.items():
        if key not in expected_fks and any(key[0] == k[0] and fk_signature(rows) == fk_signature(v)
                                          for k, v in expected_fks.items()):
            warnings.append(f'{key[0]}: equivalent foreign key has a different name')
    if any(r['CONSTRAINT_TYPE'] not in {'PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY'}
           or r.get('ENFORCED', 'YES') != 'YES' for r in actual['constraints']):
        errors.append('Unexpected or unenforced constraint')
    if actual['triggers'] or actual['routines']:
        errors.append('Unexpected trigger/routine: manual review required')
    return {'compatible': not errors and not missing, 'errors': errors,
            'warnings': warnings, 'missing_unique_indexes': missing}


def read_data_checks(connection):
    queries = {
        'duplicate_tracks': 'SELECT COUNT(*) AS count FROM (SELECT artist,track FROM tracks GROUP BY artist,track HAVING COUNT(*)>1) d',
        'duplicate_spotify': 'SELECT COUNT(*) AS count FROM (SELECT song_id,chart_date FROM spotify_chart GROUP BY song_id,chart_date HAVING COUNT(*)>1) d',
        'duplicate_youtube': 'SELECT COUNT(*) AS count FROM (SELECT youtube_video_id,collected_at FROM youtube_stats GROUP BY youtube_video_id,collected_at HAVING COUNT(*)>1) d',
        'orphan_spotify': 'SELECT COUNT(*) AS count FROM spotify_chart s LEFT JOIN tracks t ON t.song_id=s.song_id WHERE t.song_id IS NULL',
        'orphan_youtube': 'SELECT COUNT(*) AS count FROM youtube_stats y LEFT JOIN tracks t ON t.song_id=y.song_id WHERE t.song_id IS NULL',
    }
    cursor = connection.cursor(dictionary=True)
    try:
        checks = {}
        for name, query in queries.items():
            cursor.execute(query)
            checks[name] = int(cursor.fetchone()['count'])
        return checks
    finally:
        cursor.close()


def migration_statements():
    path = ROOT / 'db/migrations/001_weekly_unique_indexes.sql'
    statements = [s.strip() for s in re.sub(r'--[^\n]*', '', path.read_text(encoding='utf-8')).split(';') if s.strip()]
    expected = load_manifest()
    groups = index_groups(expected['indexes'])
    result = {}
    for table, name in TARGETS.items():
        columns = ', '.join(r['COLUMN_NAME'] for r in groups[(table, name)])
        sql = f'ALTER TABLE {table} ADD UNIQUE KEY {name} ({columns})'
        if sql not in statements:
            raise SchemaError('Migration SQL differs from the manifest')
        result[table] = sql
    if len(statements) != len(result):
        raise SchemaError('Unexpected migration SQL statement')
    return result


def plan_migration(connection):
    actual = inspect_schema(connection)
    comparison = compare_schema(actual)
    if comparison['errors']:
        raise SchemaError('; '.join(comparison['errors']))
    checks = read_data_checks(connection)
    # Never repair data to make a constraint fit, including when no DDL is needed.
    if any(checks.values()):
        raise SchemaError('Duplicate/orphan data requires manual review: ' + json.dumps(checks))
    statements = migration_statements()
    return {**comparison, 'data_checks': checks,
            'statements': [statements[item['table']] for item in comparison['missing_unique_indexes']]}


def require_test_target(database, operational_database):
    if (not database or not operational_database or database.casefold() == operational_database.casefold()
        or not TEST_DB.fullmatch(database) or len(database) > 64):
        raise SchemaError('DDL is restricted to an explicitly named mbc_kpop_step19_test_* database; operational DDL is forbidden')


def apply_test_migration(connection, database, operational_database):
    require_test_target(database, operational_database)
    connection.start_transaction(readonly=True)
    try:
        actual_database = inspect_schema(connection)['database'][0]['database_name']
        if actual_database != database:
            raise SchemaError('Connected database differs from the explicit target')
        plan = plan_migration(connection)
    finally:
        connection.rollback()
    # MySQL DDL implicitly commits. Preflight the whole plan before the first ALTER.
    # Re-run after an interrupted DDL: existing equivalent indexes are skipped.
    cursor = connection.cursor()
    try:
        for sql in plan['statements']:
            cursor.execute(sql)
    finally:
        cursor.close()
    connection.start_transaction(readonly=True)
    try:
        after = plan_migration(connection)
        if after['statements']:
            raise SchemaError('Post-migration schema verification failed')
    finally:
        connection.rollback()
    return {**after, 'applied': plan['statements']}


def load_config(env_file=None):
    from dotenv import dotenv_values
    return dotenv_values(env_file or ROOT / '.env')


def connect_database(config, database):
    import mysql.connector
    return mysql.connector.connect(host=config.get('MYSQL_HOST'), port=int(config.get('MYSQL_PORT', '3306')),
                                   user=config.get('MYSQL_USER'), password=config.get('MYSQL_PASSWORD'),
                                   database=database, connection_timeout=5)
