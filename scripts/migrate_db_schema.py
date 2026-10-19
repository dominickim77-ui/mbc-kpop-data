"""Default dry-run; --apply is supported only for isolated STEP19 test databases."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db.schema_tools import (SchemaError, connect_database, load_config, plan_migration,
                             require_test_target, apply_test_migration)


def main():
    parser = argparse.ArgumentParser(description='스키마 보완 계획(기본 읽기 전용), 테스트 DB만 적용 가능')
    parser.add_argument('--database', required=True)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    connection = None
    try:
        config = load_config(args.env_file)
        if args.apply:
            # Reject before connecting, even when operational schema already matches.
            require_test_target(args.database, config.get('MYSQL_DATABASE'))
        connection = connect_database(config, args.database)
        if args.apply:
            result = apply_test_migration(connection, args.database, config.get('MYSQL_DATABASE'))
        else:
            connection.start_transaction(readonly=True)
            result = plan_migration(connection)
        print(json.dumps({'mode': 'test_apply' if args.apply else 'read_only_plan', **result},
                         ensure_ascii=False, indent=2))
        return 0
    except SchemaError as exc:
        print('보완 중단: ' + str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print('보완 중단: ' + type(exc).__name__ + '; DDL 결과는 재점검 후 판단하세요.', file=sys.stderr)
        return 2
    finally:
        if connection is not None:
            connection.rollback()
            connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
