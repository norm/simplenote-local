# simplenote-local

A command-line tool to fetch, edit, and synchronise local notes files with
[Simplenote](https://simplenote.com).


## Synchronising notes

Set the username and password for your Simplenote account in the environment.

    export SIMPLENOTE_LOCAL_USER=user@example.com
    export SIMPLENOTE_LOCAL_PASSWORD=sekr1tp@ss

Then fetch the latest notes state from Simplenote. 

    simplenote --fetch

Notes are kept in `$HOME/Notes` by default, but this can be overridden.

    export SIMPLENOTE_LOCAL_DIR=$HOME/simplenotes
    simplenote --fetch

Send any local changes to Simplenote. Although notes are automatically sent to
Simplenote when changed using `simplenote --edit`, this will send any changes
made by other commands.

    simplenote --send

Loop forever sending any local updates to Simplenote, and regularly checking
Simplenote for updates to fetch.

    simplenote --watch

By default this will check Simplenote for new changes every 10 minutes, and
wait one minute after detecting local changes before sending (in case the same
file is changed again in quick succession). These timings can be overridden.

    simplenote --fetch-interval 60 --send-wait 0 --watch


## Finding and editing notes

List all notes.

    simplenote --list

List only those notes that contain one or more words either in the filename,
or in the file contents. The notes are sorted with the most recently edited
files first.

    simplenote --list recipe rice

Words are searched as fragments, not whole words. For example, `simplenote
--list recipe rice` would also find recipe notes that included the word
"ricer" or "liquorice".

Edit all notes. **Note:** unless your editor is fast at loading multiple
files, or loads them one at a time (like vi), this could be painfully slow
once you have a lot of notes.

    simplenote --edit

Override your default `VISUAL` and/or `EDITOR` environment variables.

    export SIMPLENOTE_LOCAL_EDITOR=sublime
    simplenote --edit

Edit only those notes that would match using the same rules as `--list`.

    simplenote --edit key lime pie

Editing is the default, so the flag can be omitted.

    simplenote key lime pie

To edit an individual file, the filename must contain at least one space
**and** the space(s) must be quoted in the command. The ".txt" extension
does not need to be included.

    simplenote "key lime pie"
    simplenote key\ lime\ pie
