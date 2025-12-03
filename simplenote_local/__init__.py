from bs4 import BeautifulSoup
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
from markdownify import markdownify
import nltk
import os
import pickle
import random
import re
from simple_colors import *
from simplenote import Simplenote
import subprocess
import sys
import time
import toml


class Note:
    def __init__(self, note={}):
        self.tags = note.get('tags', [])
        self.deleted = note.get('deleted', False)
        self.share_url = note.get('shareURL', '')
        self.publish_url = note.get('publishURL', '')
        self.system_tags = note.get('systemTags', [])
        self.modified = int(note.get('modificationDate', '0'))
        self.created = int(note.get('creationDate', '0'))
        self.key = note.get('key', '')
        self.version = int(note.get('version', '0'))
        self.state = note.get('state', '')
        self.fingerprint = note.get('fingerprint', None)
        self.title = note.get('title', '')
        self.body = note.get('body', '')
        content = note.get('content', None)
        if content:
            self.title, self.body = self.title_and_body(content)
            self.fingerprint = hashlib.sha256(self.body.encode('utf-8')).hexdigest()
            self.content = content
        else:
            if not self.title:
                self.title = 'new note'
            self.content = self.title + "\n\n" + self.body
        self.filename = note.get('filename', '%s.txt' % self.title)

    @classmethod
    def title_and_body(cls, text):
        # fix problems with very old notes
        text = text.replace(u'\xa0', u' ')
        text = text.replace(u'\r', u'\n')

        first_line = text.split('\n')[0]
        first_line = re.sub(r'[/:\*«»]', '', first_line)
        first_line = re.sub(r'^#+', '', first_line)

        # trim filenames to max 60 chars, but on a word boundary
        title = first_line
        if len(first_line) > 60:
            trimmed = first_line[0:61]
            try:
                title = trimmed[0:trimmed.rindex(' ')]
            except ValueError:
                title = trimmed

        body = (
            first_line[len(title):].lstrip()
            + '\n'
            + '\n'.join(text.split('\n')[1:])
        )
        if body.startswith('\n\n'):
            body = body[2:]
        title = title.lstrip()

        return title, body

    def increment_filename(self):
        base = self.filename[:-4]
        increment = 0

        match = re.search(r'\.(\d+)$', base)
        if match:
            increment = int(match.group(1))
            base = re.sub(r'\.(\d+)$', '', base)

        increment = increment + 1
        self.filename = "%s.%d.txt" % (base, increment)

    @property
    def published_url(self):
        if self.publish_url:
            return 'https://app.simplenote.com/p/%s' % self.publish_url
        return ''

    @property
    def tag_list(self):
        list = []
        for tag in self.tags:
            # exclude tags matching a loose approximation of an email address
            if not re.match(r'.+@.+\..+', tag):
                list.append('#' + tag)
        return ' '.join(list)

    @property
    def share_list(self):
        list = []
        for tag in self.tags:
            # exclude tags matching a loose approximation of an email address
            if re.match(r'.+@.+\..+', tag):
                list.append(tag)
        return ' '.join(list)

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
            'title': self.title,
            'filename': self.filename,
            'fingerprint': self.fingerprint,
            # state is internal flag, not useful to preserve
            # body stored in file
            # content can be derived from filename and body
        }


class SimplenoteLocal:
    def __init__(self, directory='.', user=False, password=False, editor='ed'):
        self.directory = directory
        self.editor = editor
        self.user = user
        self.password = password
        self.simplenote_api = Simplenote(self.user, self.password)
        self.reload_data()
        os.makedirs(self.directory, exist_ok=True)

    def reload_data(self):
        self.notes, self.cursor, self.words = self.load_data()

    def fetch_changes(self):
        received_change = False
        updates = self.get_note_updates()
        for entry in updates:
            update = Note(entry)
            current = None
            if update.key in self.notes:
                current = self.notes[update.key]


            if current and current.version >= update.version:
                # because of the stored cursor position, running fetch after
                # sending a local update will include the already known version
                continue

            if current and not current.deleted and current.title == update.title:
                # continue using the established filename
                update.filename = current.filename

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
                        update.increment_filename()

            if current and not current.deleted and current.filename != update.filename:
                os.rename(
                    os.path.join(self.directory, current.filename),
                    os.path.join(self.directory, update.filename),
                )
                print('  ', current.filename, green('->'), update.filename)

            if update.deleted:
                if current and not current.deleted:
                    self.remove_note_file(update)
                update.filename = ''
            else:
                self.add_to_words_cache(update.filename, update.content)
                self.save_note_file(update)

            self.notes[update.key] = update
            received_change = True
        if received_change:
            self.save_data()

    def send_changes(self):
        for note in self.list_changed_notes():
            self.send_one_change(note)
        self.save_data()

    def watch_for_changes(self, fetch_interval, send_wait):
        import threading
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class Changes(FileSystemEventHandler):
            def __init__(self, local):
                super().__init__()
                self.lock = threading.Lock()
                self.events = False

            def on_any_event(self, event):
                filename = os.path.basename(event.src_path)
                if filename.endswith('.txt') and not filename.startswith('.'):
                    with self.lock:
                        self.events = True

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
                    if changes.events:
                        # a slight pause to account for another
                        # command performing file changing actions
                        time.sleep(1)
                        self.reload_data()
                        for note in self.list_changed_notes():
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
                        if sent_change:
                            self.save_data()
                        if not self.list_changed_notes():
                            changes.events = False

        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    def list_matching_notes(self, matches):
        for note in self.find_matching_notes(matches):
            filename = note.filename.replace('"', '\\"')
            pinned = ''
            shared = ''
            tags = ''
            url = ''
            if 'pinned' in note.system_tags:
                pinned = blue(' pinned', 'bold')
            if note.share_list:
                shared = red(' shared ' + note.share_list)
            if note.tags:
                tags = ' ' + blue(note.tag_list)
            if 'published' in note.system_tags:
                url = yellow(' %s' % note.published_url)
            print(f'"{filename}"{pinned}{shared}{tags}{url}')

    def list_tags(self):
        tags = dict()
        for note in self.get_local_note_state():
            for tag in note.tags:
                if tag in tags:
                    tags[tag] += 1
                else:
                    tags[tag] = 1
        max_width = max(len(tag) for tag in tags)
        for tag in sorted(tags, key=lambda tag: tag.lower()):
            count = '  %d note' % tags[tag]
            if tags[tag] > 1:
                count = count + 's'
            print(tag.ljust(max_width), count)

    def add_tag(self, tag, matches):
        matching = self.find_matching_notes(matches)
        sent_change = False
        for match in matching:
            if tag not in match.tags:
                match.tags.append(tag)

                # touch the file even though the contents haven't changed
                pathname = os.path.join(self.directory, match.filename)
                now = int(datetime.now().timestamp())
                os.utime(pathname, (now, now))
                match.modified = now

                self.send_one_change(match)
                sent_change = True
        if sent_change:
            self.save_data()

    def remove_tag(self, tag, matches):
        matching = self.find_matching_notes(matches)
        sent_change = False
        for match in matching:
            if tag in match.tags:
                match.tags.remove(tag)

                # touch the file even though the contents haven't changed
                pathname = os.path.join(self.directory, match.filename)
                now = int(datetime.now().timestamp())
                os.utime(pathname, (now, now))
                match.modified = now

                self.send_one_change(match)
                sent_change = True
        if sent_change:
            self.save_data()

    def edit_matching_notes(self, matches):
        matching = self.find_matching_notes(matches)

        # double check we're not trying to create new file(s)
        if not matching:
            for match in matches:
                if ' ' in match:
                    matching.append(Note({
                        'filename': match + '.txt',
                        'state': 'new',
                    }))

        if matching:
            command = [self.editor]
            for note in matching:
                pathname = os.path.join(self.directory, note.filename)
                command.append(pathname)

            subprocess.run(command, check=True)

            changes = False
            for note in self.list_changed_notes():
                for match in matching:
                    if note.filename.lower() == match.filename.lower():
                        self.send_one_change(note)
                        changes = True
            if changes:
                self.save_data()
        else:
            print("""** No notes found matching all of: %s.

To edit an individual note using this tool, the filename must contain a space
and the space must be quoted in the command:

    simplenote --edit "key lime"

Otherwise, this tool is looking for files with both the words "key" and
"lime" in them, not a new file.""" % (
                    (', '.join('"' + match + '"' for match in matches)),
                ),
                file=sys.stderr
            )
            sys.exit(1)

    def capture_stdin(self, raw, matches):
        body = sys.stdin.read().replace('\r', '')
        title = ''
        now = int(datetime.now().timestamp())

        # if the input looks like HTML, markdownify it and extract the first
        # <h1> tag as the note title (which may not be the first line of text
        # given global nav etc appearing first in source order)
        soup = BeautifulSoup(body, 'html.parser')
        first_header = soup.find('h1')
        is_html = len(soup.find_all()) > 0
        if first_header:
            first_header = first_header.string
        if is_html and not raw:
            body = markdownify(body).lstrip().rstrip()
            body = re.sub('\n\n\n*', '\n\n', body)
        title, body = Note.title_and_body(body)
        if first_header:
            title = first_header

        if matches:
            matching = self.find_matching_notes(matches)
            if matching:
                note = matching[0]
                note.body = body
                note.modified = now
            else:
                note = Note({
                    'creationDate': now,
                    'modificationDate': now,
                    'content': matches[0] + "\n\n" + body,
                    'state': 'new',
                })
        else:
            if not title and not body.lstrip():
                # no completely empty notes
                title = 'new note'
            system_tags = []
            if is_html and not raw:
                system_tags = ['markdown',]
            note = Note({
                'creationDate': now,
                'modificationDate': now,
                'content': title + "\n\n" + body,
                'state': 'new',
                'systemTags': system_tags,
            })

        unique_filename = False
        while not unique_filename:
            by_filename = self.get_note_by_filename(note.filename)
            if not by_filename:
                unique_filename = True
            else:
                note.increment_filename()

        new_note = self.send_one_change(note)
        self.save_data()

    def trash_notes(self, matches):
        sent_change = False
        for match in self.find_matching_notes(matches):
            match.state = 'deleted'
            self.remove_note_file(match, 'quiet')
            self.send_one_change(match)
            sent_change = True

        if sent_change:
            self.save_data()

    def restore_notes(self, matches):
        sent_change = False
        for key in self.notes:
            note = self.notes[key]
            if note.deleted:
                for match in matches:
                    if match.lower() in note.title.lower():
                        latest, error = self.simplenote_api.get_note(note.key)
                        if error:
                            sys.exit(error)
                        latest = Note(latest)
                        latest.deleted = False
                        latest.modified = datetime.now().timestamp()
                        pathname = os.path.join(self.directory, latest.filename)
                        with open(pathname, 'w') as handle:
                            handle.write(latest.body)
                        os.utime(pathname, (latest.modified, latest.modified))
                        self.send_one_change(latest)
                        sent_change = True

        if sent_change:
            self.save_data()

    def purge_notes(self, matches):
        sent_change = False
        deleted = []
        for key in self.notes:
            note = self.notes[key]
            if note.deleted:
                for match in matches:
                    if match.lower() in note.title.lower():
                        _, error = self.simplenote_api.delete_note(note.key)
                        if error:
                            sys.exit(error)
                        sent_change = True
                        print(red('XX'), note.title)
                        deleted.append(note.key)

        if sent_change:
            for key in deleted:
                del self.notes[key]
            self.save_data()

    def pin_notes(self, matches):
        sent_change = False
        for match in self.find_matching_notes(matches):
            match.system_tags.append('pinned')
            self.send_one_change(match)
            sent_change = True

        if sent_change:
            self.save_data()

    def unpin_notes(self, matches):
        sent_change = False
        for match in self.find_matching_notes(matches):
            match.system_tags.remove('pinned')
            self.send_one_change(match)
            sent_change = True

        if sent_change:
            self.save_data()

    def publish_notes(self, matches):
        sent_change = False
        for match in self.find_matching_notes(matches):
            match.system_tags.append('published')
            self.send_one_change(match)
            key = match.key

            # sending an update with the 'published' tag also causes a second
            # change within Simplenote to generate and add the URL fragment,
            # so give that a little time to happen (but not forever)
            for _ in range(0, 10):
                time.sleep(1)
                self.fetch_changes()
                note = self.notes[key]
                if note.publish_url:
                    break

            if note.publish_url:
                print('   URL:', note.published_url)
            else:
                sys.exit('** Error publishing', note.filename)

    def unpublish_notes(self, matches):
        sent_change = False
        for match in self.find_matching_notes(matches):
            match.system_tags.remove('published')
            self.send_one_change(match)
            key = match.key

            # sending an update with the 'published' tag also causes a second
            # change within Simplenote to generate and add the URL fragment,
            # so give that a little time to happen (but not forever)
            for _ in range(0, 10):
                time.sleep(1)
                self.fetch_changes()
                note = self.notes[key]
                if not note.publish_url:
                    break

            if note.publish_url:
                sys.exit('** Error unpublishing', note.filename)

    def show_note_info(self, matches):
        for match in self.find_matching_notes(matches):
            self.show_note_metadata(match)

    def show_note_metadata(self, note):
        print(note.filename)
        print('  created  ', datetime.fromtimestamp(note.created).strftime('%A %d %B %Y %H:%M:%S'))
        print('  modified ', datetime.fromtimestamp(note.modified).strftime('%A %d %B %Y %H:%M:%S'))
        if note.tag_list:
            print('  tagged   ', note.tag_list)
        if note.share_list:
            print('  shared   ', note.share_list)
        if 'pinned' in note.system_tags:
            print('  pinned')
        if 'published' in note.system_tags:
            print('  published', note.published_url)
        print('  version  ', note.version)
        print()

    def show_note_history(self, matches, full=False):
        for match in self.find_matching_notes(matches):
            print(match.filename)
            current = match.version
            limit = 10
            if full:
                limit = current
            for i in range(0, limit):
                version = current - i
                if version < 1:
                    break
                note_version = self.get_note_version(match.key, version)
                if note_version:
                    print(
                        '%06s' % ('v%d' % note_version.version),
                        '  %-14s' % ('%d chars' % len(note_version.content)),
                        datetime.utcfromtimestamp(int(note_version.modified)),
                    )
                else:
                    print('%06s...' % ('v%d' % version), end="\r")
            print('          ')

    def show_note_version(self, show):
        match = self.find_matching_notes([show[0],])[0]
        version = int(show[1])
        note = self.get_note_version(match.key, version)
        self.show_note_metadata(note)
        print()
        print(note.body)

    def restore_note_version(self, restore):
        match = self.find_matching_notes([restore[0],])[0]
        version = int(restore[1])
        note = self.get_note_version(match.key, version)
        if not note:
            print("""
** Stored note "%s" version %d not found.

Simplenote does not keep every version of every note forever. Notes that
have received many edits will not have all historic versions available.
Every tenth version should be, so try version %d or %d.
""" % (
                    match.filename,
                    version,
                    ((version // 10) * 10 + 1),
                    ((version // 10) * 10 + 11),
                ),
                file=sys.stderr
            )
        else:
            note.state = 'restored'
            note.version = None
            self.send_one_change(note)
            self.save_data()

    def list_changes(self):
        for note in self.list_changed_notes():
            key = note.key
            if key:
                updated = False
                if note.modified != self.notes[key].modified:
                    updated = True
                if note.fingerprint != self.notes[key].fingerprint:
                    updated = True
                if updated:
                    print(blue('>>'), note.filename)
                else:
                    print(magenta('--'), note.filename, end='\n\n')
                    continue
            else:
                print(green('++'), note.filename)
            print(
                '   last updated:',
                datetime.utcfromtimestamp(int(note.modified)),
                end='\n\n',
            )

    def get_note_version(self, key, version):
        cache_file = os.path.join(
            '/tmp',
            'simplenote_local.%s.%d.pickle' % (key, version)
        )
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as handle:
                note = pickle.load(handle)
        else:
            note, error = self.simplenote_api.get_note(key, version)
            if error:
                if str(note) != "HTTP Error 404: Not Found":
                    sys.exit(str(note))
                note = None
        with open(cache_file, 'wb') as handle:
            pickle.dump(note, handle)
        if note:
            return Note(note)
        return None

    def find_matching_notes(self, matches):
        notes = set(self.get_local_note_state())
        for match in matches:
            matching = set()
            if match.startswith('#') or match.startswith('%'):
                for note in notes:
                    if match[1:] in note.tags:
                        matching.add(note)
            elif ' ' in match:
                for note in notes:
                    if match.lower() in note.filename.lower():
                        matching.add(note)
            else:
                for word in self.words:
                    if match in word:
                        for note in notes:
                            if note.filename in self.words[word]:
                                matching.add(note)
            notes = notes.intersection(matching)

        return sorted(
            notes,
            key=lambda note: ('pinned' in note.system_tags, note.modified),
            reverse=True,
        )

    def list_changed_notes(self):
        notes = self.get_local_note_state()
        return list(filter(
            lambda note: note.state != 'unchanged',
            notes
        ))

    def send_one_change(self, note):
        if note.state == 'deleted':
            new_note = self.trash_note(note)
            new_note = Note(new_note)
            print(magenta('--'), note.filename)
        elif note.state == 'new':
            new_note = self.send_note_update(note)
            pathname = os.path.join(self.directory, note.filename)
            with open(pathname, 'w') as handle:
                handle.write(new_note.body)
            os.utime(pathname, (new_note.modified, new_note.modified))
            print(green('++'), 'note "%s" (%s)' % (note.filename, new_note.key))
        else:
            note.content = note.title + "\n\n" + note.body
            new_note = self.send_note_update(note)
            self.save_note_file(new_note)
            print(blue('>>'), new_note.filename)

        if note.title == new_note.title:
            new_note.filename = note.filename
        self.notes[new_note.key] = new_note
        return new_note

    def get_note_updates(self):
        retries = 5
        while retries:
            notes, error = self.simplenote_api.get_note_list(since=self.cursor)
            if not error:
                self.cursor = self.simplenote_api.current
                return sorted(notes, key=lambda note: int(note['creationDate']))
            retries -= 1
            if retries:
                # exponential backoff 1-2s, 2-4s, 4-8s, 8-16s (15-30s total)
                power = 5 - retries
                time.sleep(random.randint(2 ** (power - 1), 2 ** power))
        raise Exception(f"Repeated simplenote API error {error}")

    def get_note_by_filename(self, filename):
        for key in self.notes:
            note = self.notes[key]
            if note.deleted:
                continue
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
        if note.version:
            update['version'] = note.version

        new_note, error = self.simplenote_api.update_note(update)
        if error:
            sys.exit('Error updating note "%s": %s.' % (note.filename, new_note))
        return Note(new_note)

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
                body = handle.read()
                sha = hashlib.sha256(body.encode('utf-8')).hexdigest()

            if filename in expected_files:
                note = deepcopy(self.notes[expected_files[filename]])
                note.body = body
                note.content = note.title + "\n\n" + note.body
                note.state = 'unchanged'
                if current != note.modified or sha != note.fingerprint:
                    note.modified = current
                    note.state = 'changed'
                    self.add_to_words_cache(filename, note.content)
                del expected_files[filename]
                local_notes.append(note)
            else:
                note = Note({
                    'creationDate': current,
                    'modificationDate': current,
                    'body': body,
                    'content': filename[:-4] + "\n\n" + body,
                    'filename': filename,
                    'state': 'new',
                })
                self.add_to_words_cache(filename, note.content)
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
            if not current:
                print(green('++'), note.filename)
            else:
                print(blue('<<'), note.filename)
        os.utime(pathname, (note.modified, note.modified))

    def remove_note_file(self, note, quiet=False):
        pathname = os.path.join(self.directory, note.filename)
        try:
            os.remove(pathname)
            if not quiet:
                print(magenta('--'), note.filename)
        except FileNotFoundError:
            # after deleting a file locally the next fetch will
            # include the state that the file has been removed,
            # but it has already been removed -- so, not an error
            pass
        self.remove_file_from_words_cache(note.filename)

    def remove_file_from_words_cache(self, filename):
        for word in self.words:
            try:
                self.words[word].remove(filename)
            except KeyError:
                pass
            except ValueError:
                pass

    def add_to_words_cache(self, filename, content):
        self.remove_file_from_words_cache(filename)
        words = set(
            word[:60] for word in [
                re.sub(r'[\W_]+', ' ', word.lower())
                    for word in re.split(r'\b', content)
                ] if word and len(word) > 2
        )
        for word in words:
            if word not in self.words:
                self.words[word] = [ filename, ]
            else:
                if filename not in self.words[word]:
                    self.words[word].append(filename)

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
            data = {'notes': {}, 'cursor': '', 'words': {}}

        # rehydrate the stored dicts as Note objects
        notes = {}
        words = {}
        for key in data['notes']:
            notes[key] = Note(data['notes'][key])

        return notes, data['cursor'], data['words']

    def save_data(self):
        tmp_file = os.path.join(self.directory, '.notes.save')
        with open(tmp_file, 'wb') as handle:
            pickle.dump({
                'notes': self.notes_as_dict(),
                'cursor': self.cursor,
                'words': self.words,
            }, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(tmp_file, os.path.join(self.directory, 'notes.data'))
        with open(tmp_file, 'w') as handle:
            toml.dump({
                'notes': self.notes_as_dict(),
                'cursor': self.cursor,
                'words': self.words,
            }, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(tmp_file, os.path.join(self.directory, 'notes.toml'))
