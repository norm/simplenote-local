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


## Finding notes

To list all notes:

    simplenote --list

The notes are sorted with the most recently edited files first.

To list only those notes that contain one or more words either in the
filename, or in the file contents:

    simplenote --list recipe rice

Words are searched as fragments, not whole words. For example, `simplenote
--list recipe rice` would also find recipe notes that included the word
"ricer" or "liquorice".

To list notes that have a specific tag applied, you can use either `#tag`
or `%tag` notation. Hashes are more commonly used in social media, but
in the shell it starts a comment, so would need to be quoted.

    simplenote --list \#recipe
    simplenote --list %recipe pie

To list all available tags:

    simplenote --list-tags


## Editing notes

To edit all notes:

    simplenote --edit

**Note:** unless your editor is fast at loading multiple files, or loads
them one at a time (like vi), this could be painfully slow once you have
a lot of notes.

To override the editor your default `VISUAL` and/or `EDITOR` environment
variables would specify:

    export SIMPLENOTE_LOCAL_EDITOR=sublime
    simplenote --edit

To edit only those notes that would match using the same rules as `--list`:

    simplenote --edit key lime pie
    simplenote --edit "key lime pie"
    simplenote --edit %recipe pie

Editing is the default, so the flag can be omitted.

    simplenote key lime pie

To edit an individual file, the filename must contain at least one space
**and** the space(s) must be quoted in the command. The ".txt" extension
does not need to be included.

    simplenote "key lime pie"
    simplenote key\ lime\ pie

To pipe the output of a command into a note, creating it if it doesn't
already exist:

    pbpaste | simplenote "cake recipe"

**Notes:**
* If the argument(s) match more than one existing note, only the first match
  will be updated.
* If no match is given, the note will be named after the first line of the
  output.

If the input looks like HTML, it will be passed through
[markdownify](https://pypi.org/project/markdownify/) first. You can disable
this step with with the `--raw` option:

    curl https://.../cake-recipe.html | simplenote "cake recipe"
    curl https://.../cake-recipe.html | simplenote --raw "html cake recipe"


## Tagging notes

To add a tag to matching notes:

    simplenote --add-tag recipe key lime pie

To remove a tag from matching notes:

    simplenote --remove-tag recipe key lime pie

To remove a tag from all notes:

    simplenote --remove-tag recipe


## Removing notes

To move all matching notes to the Trash:

    simplenote --trash recipe

To restore a note from the Trash:

    simplenote --restore key lime pie

To permanently delete notes from the Trash:

    simplenote --purge key lime pie


## Pinning notes

**Note:** pinned notes appear at the top of the notes list in the Simplenote
interface. In the local copy, it will sort those notes to the top when using
`simplenote --list`, nothing else.

To pin all matching notes:

    simplenote --pin key lime pie

To unpin all matching notes:

    simplenote --unpin key lime pie


## Publishing notes

To tell Simplenote to publish notes to a web page:

    simplenote --publish key lime pie

To tell Simplenote to remove published notes:

    simplenote --unpublish key lime pie


## Collaborating on notes

To collaborate with others on notes, you can add a tag which is the
email address of another user:

    simplenote --add-tag norm@example.com key lime pie

To stop sharing notes with them, remove the tag again:

    simplenote --remove-tag norm@example.com key lime pie

**Note:** There are two wrinkles with this implementation of sharing:

1. If that email is not already registered with Simplenote there appears to be
   no notification to them that they could sign up to collaborate with you --
   that is, you either have to be sure they already use Simplenote, or inform
   them yourself to sign up in order to be able to work together on a note.

2. When you later unshare a note, the other account keeps a copy of the
   original note as it was immediately before unsharing, which may be
   unexpected behaviour and not what you want.


## Show a summary of the metadata stored about matching notes

    simplenote --info key lime pie


## Historical versions of notes

Simplenote keeps multiple versions of notes as they are updated, but not all.
The [Simperium documentation](https://simperium.com/overview/) states:

> Simperium stores up to 50 of your most recent versions, and then every
> 10th version beyond that.

Simperium is the name for the service backing the Simplenote app.

**Personal note:** I have some regularly edited notes with 1,500+ versions
where versions more than 1,000 back are not available; so there are more
possible expiry thresholds for historical versions than stated.

To get a list of the recent historical versions of matching notes:

    simplenote --history key lime pie

To get a list of all available historical versions of matching notes:

    simplenote --history --full key lime pie

To show the metadata and content of an older version of a single note:

    simplenote --show-version "key lime pie" 22

To restore the content and tags of an older version of a single note:

    simplenote --restore-version "key lime pie" 22

**Note:** In this instance, the name of the note needs to be quoted to make it
the first argument to the command, as the second argument is the version.


## Local changes

To list known local changes to notes:

    simplenote --list-changes

**Note:** this does not automatically fetch the current state of notes, so
it is not 100% authoritative.
