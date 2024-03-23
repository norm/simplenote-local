from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import os
import pickle
import re
from simplenote import Simplenote
import sys
import time
import toml

from pprint import pprint


class Note:
    def __init__(self, note={}):
        self.tags = note.get('tags', [])
        self.deleted = note.get('deleted', False)
        self.share_url = note.get('shareURL', '')
        self.publish_url = note.get('publishURL', '')
        self.content = self.fix_text_problems(note.get('content', ''))
        self.system_tags = note.get('systemTags', [])
        self.modified = int(note.get('modificationDate', '0'))
        self.created = int(note.get('creationDate', '0'))
        self.key = note.get('key', '')
        self.version = int(note.get('version', '0'))
        self.state = note.get('state', '')
        self.fingerprint = note.get('fingerprint', None)
        self.filename = note.get('filename', '')
        content = note.get('content', None)
        if content:
            self.filename, self.body, self.fingerprint = self.process_content()

    def fix_text_problems(self, text):
        text = text.replace(u'\xa0', u' ')
        text = text.replace(u'\r', u'\n')
        return text

    def process_content(self):
        content = self.content
        first_line = content.split('\n')[0]
        first_line = re.sub(r'[/:\*«»]', '', first_line)

        # trim filenames to max 60 chars, but on a word boundary
        filename = first_line
        if len(first_line) > 60:
            trimmed = first_line[0:61]
            try:
                filename = trimmed[0:trimmed.rindex(' ')]
            except ValueError:
                filename = trimmed

        # beware of first line being unusable
        if len(filename) == 0:
            filename = self.key

        body = (
            first_line[len(filename):].lstrip()
            + '\n'
            + '\n'.join(content.split('\n')[1:])
        )
        if body.startswith('\n\n'):
            body = body[2:]

        return(
            filename + '.txt',
            body,
            hashlib.sha256(body.encode('utf-8')).hexdigest(),
        )

    def increment_filename(self):
        base = self.filename[:-4]
        increment = 0

        match = re.search(r'\.(\d+)$', base)
        if match:
            increment = int(match.group(1))
            base = re.sub(r'\.(\d+)$', '', base)

        increment = increment + 1
        self.filename = "%s.%d.txt" % (base, increment)

    def as_dict(self):
        return {
            'tags': self.tags,
            'deleted': self.deleted,
            'shareURL': self.share_url,
            'publishURL': self.publish_url,
            'systemTags': self.system_tags,
            'modificationDate': self.modified,
            'creationDate': self.created,
            'key': self.key,
            'version': self.version,
            'filename': self.filename,
            'fingerprint': self.fingerprint,
            # state is internal flag, not useful to preserve
            # body stored in file
            # content can be derived from filename and body
        }


class SimplenoteLocal:
    def __init__(self, directory='.', user=False, password=False):
        self.directory = directory
        self.user = user
        self.password = password
        self.simplenote_api = Simplenote(self.user, self.password)
        self.notes, self.cursor = self.load_data()
        os.makedirs(self.directory, exist_ok=True)

    def fetch_changes(self):
        updates = self.get_note_updates()
        for entry in updates:
            update = Note(entry)
            current = None
            if update.key in self.notes:
                current = self.notes[update.key]

            # if a new file, or the filename has changed, ensure that the
            # filename remains unique (there is nothing to stop you creating
            # multiple notes with the same exact text/first line)
            if not current or current.filename != update.filename:
                unique_filename = False
                while not unique_filename:
                    by_filename = self.get_note_by_filename(update.filename)
                    if not by_filename:
                        unique_filename = True
                    else:
                        if by_filename.deleted:
                            unique_filename = True
                        else:
                            update.increment_filename()

            if update.deleted:
                if current and not current.deleted:
                    self.remove_note_file(update)
            else:
                self.save_note_file(update)

            self.notes[update.key] = update
        self.save_data()

    def send_changes(self):
        for note in self.list_changed_notes():
            self.send_one_change(note)
        self.fetch_changes()

    def watch_for_changes(self, fetch_interval, send_wait):
        import threading
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class Changes(FileSystemEventHandler):
            def __init__(self, local):
                super().__init__()
                self.local = local
                self.lock = threading.Lock()
                self.found = self.local.list_changed_notes()

            def on_any_event(self, event):
                filename = os.path.basename(event.src_path)
                if filename.endswith('.txt') and not filename.startswith('.'):
                    with self.lock:
                        self.found = self.local.list_changed_notes()

        changes = Changes(self)
        observer = Observer()
        observer.schedule(changes, path=self.directory, recursive=True)
        observer.start()

        fetch_interval = timedelta(seconds=fetch_interval)
        send_wait = timedelta(seconds=send_wait)
        last_fetch = datetime.now() - fetch_interval

        try:
            while True:
                time.sleep(1)

                if datetime.now() - fetch_interval >= last_fetch:
                    self.fetch_changes()
                    last_fetch = datetime.now()

                sent_change = False
                with changes.lock:
                    if changes.found:
                        for note in changes.found:
                            send = False
                            filename = note.filename
                            pathname = os.path.join(self.directory, filename)
                            if os.path.exists(pathname):
                                stamp = datetime.fromtimestamp(
                                    os.path.getmtime(pathname)
                                )
                                if stamp + send_wait < datetime.now():
                                    send = True
                            else:
                                send = True
                            if send:
                                self.send_one_change(note)
                                sent_change = True
                        changes.found = self.list_changed_notes()
                if sent_change:
                    self.fetch_changes()

        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    def list_changed_notes(self):
        notes = self.get_local_note_state()
        return list(filter(
            lambda note: note.state != 'unchanged',
            notes
        ))

    def send_one_change(self, note):
        if note.state == 'deleted':
            self.trash_note(note)
            print('XX', note.filename)
        elif note.state == 'new':
            new_note = self.send_note_update(note)
            print('++ note "%s" (%s)' % (note.filename, new_note['key']))
        else:
            note.content = note.filename[:-4] + "\n\n" + note.body
            new_note = self.send_note_update(note)
            self.notes[note.key] = Note(new_note)
            print('>>', note.filename)

    def get_note_updates(self):
        notes, error = self.simplenote_api.get_note_list(since=self.cursor)
        if error:
            sys.exit(error)
        self.cursor = self.simplenote_api.current
        return sorted(notes, key=lambda note: int(note['creationDate']))

    def get_note_by_filename(self, filename):
        for key in self.notes:
            note = self.notes[key]
            if note.filename.lower() == filename.lower():
                return note
        return None

    def send_note_update(self, note):
        update = {
            'content': note.content,
            'modificationDate': note.modified,
            'creationDate': note.created,
            'tags': note.tags,
            'systemTags': note.system_tags,
        }

        if note.key:
            update['key'] = note.key
            update['version'] = note.version

        new_note, error = self.simplenote_api.update_note(update)
        if error:
            sys.exit('Error updating note "%s": %s.' % (note.filename, new_note))
        return new_note

    def trash_note(self, note):
        new_note, error = self.simplenote_api.trash_note(note.key)
        if error:
            sys.exit('Error deleting "%s": %s.' % (note.filename, new_note))
        return new_note

    def get_local_note_state(self):
        expected_files = {}
        local_notes = []

        # compile a list of the notes already known
        for key in self.notes:
            note = self.notes[key]
            if note.deleted:
                continue
            expected_files[note.filename] = key

        # check known notes against the actual local notes
        for filename in os.listdir(self.directory):
            if filename.startswith('.'):
                continue
            if not filename.endswith('.txt'):
                continue

            pathname = os.path.join(self.directory, filename)
            current = int(os.path.getmtime(pathname))
            with open(pathname, 'r') as handle:
                content = handle.read()
                sha = hashlib.sha256(content.encode('utf-8')).hexdigest()

            if filename in expected_files:
                note = deepcopy(self.notes[expected_files[filename]])
                note.state = 'unchanged'
                if current != note.modified or sha != note.fingerprint:
                    note.body = content
                    note.modified = current
                    note.state = 'changed'
                del expected_files[filename]
                local_notes.append(note)
            else:
                note = Note({
                    'creationDate': current,
                    'modificationDate': current,
                    'content': filename[:-4] + "\n\n" + content,
                    'filename': filename,
                    'state': 'new',
                })
                local_notes.append(note)

        # deal with any known notes now removed
        for filename in expected_files:
            note = deepcopy(self.notes[expected_files[filename]])
            note.state = 'deleted'
            local_notes.append(note)

        return local_notes

    def save_note_file(self, note):
        pathname = os.path.join(self.directory, note.filename)

        try:
            with open(pathname, 'r') as handle:
                current = handle.read()
        except FileNotFoundError:
            current = None

        if note.body != current:
            with open(pathname, 'w') as handle:
                handle.write(note.body)
            os.utime(pathname, (note.modified, note.modified))
            if not current:
                print('++', note.filename)
            else:
                print('<<', note.filename)

    def remove_note_file(self, note):
        pathname = os.path.join(self.directory, note.filename)
        try:
            os.remove(pathname)
            print('--', note.filename)
        except FileNotFoundError:
            # after deleting a file locally the next fetch will
            # include the state that the file has been removed,
            # but it has already been removed -- so, not an error
            pass

    def notes_as_dict(self):
        dict = {}
        for key in self.notes:
            dict[key] = self.notes[key].as_dict()
        return dict

    def load_data(self):
        try:
            with open(os.path.join(self.directory, 'notes.data'), 'rb') as handle:
                data = pickle.load(handle)
        except FileNotFoundError:
            data = {'notes': {}, 'cursor': ''}

        # rehydrate the stored dicts as Note objects
        notes = {}
        for key in data['notes']:
            notes[key] = Note(data['notes'][key])

        return notes, data['cursor']

    def save_data(self):
        with open(os.path.join(self.directory, 'notes.data'), 'wb') as handle:
            pickle.dump({
                'notes': self.notes_as_dict(),
                'cursor': self.cursor,
            }, handle)
        with open(os.path.join(self.directory, 'notes.toml'), 'w') as handle:
            toml.dump({
                'notes': self.notes_as_dict(),
                'cursor': self.cursor,
            }, handle)

