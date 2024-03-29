import argparse
import os
from simplenote_local import SimplenoteLocal


def minimum_interval(value):
    interval = int(value)
    if interval < 30:
        interval = 30
    return interval


def minimum_wait(value):
    wait = int(value)
    if wait < 1:
        # "can be 0" is a lie to make people feel better, always waits
        # at least 1 second to avoid slamming the Simperium API in the
        # event of repeated local changes
        wait = 1
    return wait


def main():
    local = SimplenoteLocal(
        directory = os.getenv(
            'SIMPLENOTE_LOCAL_DIR',
            os.path.expanduser('~/notes')
        ),
        user = os.getenv('SIMPLENOTE_LOCAL_USER'),
        password = os.getenv('SIMPLENOTE_LOCAL_PASSWORD'),
        editor = os.getenv(
            'SIMPLENOTE_LOCAL_EDITOR',
                os.getenv('VISUAL',
                    os.getenv('EDITOR', 'vi'),
        )),
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

    notes = parser.add_mutually_exclusive_group()
    notes.add_argument(
        '--list',
        action = 'store_true',
        help = 'List notes that contain any words in [matches ...]. Will list all notes if no list supplied.',
    )
    notes.add_argument(
        '--edit',
        action = 'store_true',
        help = 'Edit notes that contain any words in [matches ...]. Default option if no other flags given. To edit an exact note, spaces in the filename must be quoted.',
    )

    sync = parser.add_argument_group('Continual syncing')
    sync.add_argument(
        '--watch',
        action = 'store_true',
        help = 'Watch continually for local or remote changes',
    )
    sync.add_argument(
        '--fetch-interval',
        type = minimum_interval,
        help = 'Check for remote changes every INTERVAL seconds. Defaults to 600 (every 10 minutes), minimum is 30.',
        default = 600,
    )
    sync.add_argument(
        '--send-wait',
        type = minimum_wait,
        help = 'Wait for WAIT seconds before sending local changes to Simplenote, in case of further edits. Defaults to 60 (1 minute), can be 0 to send changes immediately.',
        default = 60,
    )

    parser.add_argument(
        'matches',
        nargs = '*',
        help = 'Words or word fragments that must appear in a note when listing or editing notes.',
    )

    args = parser.parse_args()

    if args.watch:
        local.watch_for_changes(args.fetch_interval, args.send_wait)
    elif args.send:
        local.send_changes()
    elif args.fetch:
        local.fetch_changes()
    elif args.list:
        local.list_matching_notes(args.matches)
    else:
        # --edit is the default
        local.edit_matching_notes(args.matches)


if __name__ == '__main__':
    main()
