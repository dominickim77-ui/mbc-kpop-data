"""Read-only MySQL schema check. An explicit target database is required."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db.schema_tools import connect_database, inspect_schema, compare_schema, read_data_checks, load_config


def main():
    parser = argparse.ArgumentParser(description='읽기 전용 DB 스키마/무결성 비교')
    parser.add_argument('--database', required=True)
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args()
    connection = None
    try:
        connection = connect_database(load_config(args.env_file), args.database)
        connection.start_transaction(readonly=True)
        comparison = compare_schema(inspect_schema(connection))
        checks = read_data_checks(connection) if not comparison['errors'] else None
        print(json.dumps({**comparison, 'data_checks': checks}, ensure_ascii=False, indent=2))
        return 0 if comparison['compatible'] and checks is not None and not any(checks.values()) else 1
    except Exception as exc:
        print('DB 검사 중단: ' + type(exc).__name__, file=sys.stderr)
        return 2
    finally:
        if connection is not None:
            connection.rollback()
            connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
