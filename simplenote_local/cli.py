import argparse
import os
from simplenote_local import SimplenoteLocal


def main():
    local = SimplenoteLocal(
        directory = os.getenv(
            'SIMPLENOTE_LOCAL_DIR',
            os.path.expanduser('~/notes')
        ),
        user = os.getenv('SIMPLENOTE_LOCAL_USER'),
        password = os.getenv('SIMPLENOTE_LOCAL_PASSWORD'),
    )

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--fetch',
        action = 'store_true',
        help = 'Fetch current notes from Simplenote',
    )
    parser.add_argument(
        '--send',
        action = 'store_true',
        help = 'Send local changes to notes to Simplenote',
    )

    args = parser.parse_args()

    if args.fetch:
        local.fetch_changes()
    if args.send:
        local.send_changes()


if __name__ == '__main__':
    main()
