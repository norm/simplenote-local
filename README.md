# simplenote-local

A command-line tool to fetch, edit, and synchronise local notes files with
[Simplenote](https://simplenote.com).


## Basic usage

Set the username and password for your Simplenote account in the environment.

    export SIMPLENOTE_LOCAL_USER=user@example.com
    export SIMPLENOTE_LOCAL_PASSWORD=sekr1tp@ss

Then fetch the latest notes state from Simplenote. 

    simplenote --fetch

Notes are kept in `$HOME/Notes` by default, but this can be overridden.

    export SIMPLENOTE_LOCAL_DIR=$HOME/simplenotes
    simplenote --fetch

Send any local changes to Simplenote.

    simplenote --send
