"""
Safe atomic file write.

Saving the user's data is risky. If you write to a file directly, and an error occurs during the
write, you may corrupt the file and lose the user's data. One approach to prevent this is to write
to a temporary file, then only when you know the file has been written successfully, over-write the
original. This function returns a context manager which can make this more convenient.

Adapted from: https://github.com/ActiveState/code/blob/3b27230f418b714bc9a0f897cb8ea189c3515e99/
              recipes/Python/579097_Safely_atomically_write/recipe-579097.py

Original author: Steven D'Aprano

LICENCE
-------

Copyright 2016 Steven D'Aprano

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial
portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

import contextlib
import os
import stat
import tempfile


@contextlib.contextmanager
def atomic_write(filename, text=True, keep=True,
                 owner=None, group=None, perms=None,
                 suffix='.tmp', prefix='kaz'):
    """
    Context manager for overwriting a file atomically.

    Usage:

    >>> with atomic_write("myfile.txt") as f:  # doctest: +SKIP
    ...     f.write("data")

    The context manager opens a temporary file for writing in the same
    directory as `filename`. On cleanly exiting the with-block, the temp
    file is renamed to the given filename. If the original file already
    exists, it will be overwritten and any existing contents replaced.

    (On POSIX systems, the rename is atomic. Other operating systems may
    not support atomic renames, in which case the function name is
    misleading.)

    If an uncaught exception occurs inside the with-block, the original
    file is left untouched. By default the temporary file is also
    preserved, for diagnosis or data recovery. To delete the temp file,
    pass `keep=False`. Any errors in deleting the temp file are ignored.

    By default, the temp file is opened in text mode. To use binary mode,
    pass `text=False` as an argument. On some operating systems, this make
    no difference.

    The temporary file is readable and writable only by the creating user.
    By default, the original ownership and access permissions of `filename`
    are restored after a successful rename. If `owner`, `group` or `perms`
    are specified and are not None, the file owner, group or permissions
    are set to the given numeric value(s). If they are not specified, or
    are None, the appropriate value is taken from the original file (which
    must exist).

    By default, the temp file will have a name starting with "tmp" and
    ending with ".bak". You can vary that by passing strings as the
    `suffix` and `prefix` arguments.
    """
    t = (uid, gid, mod) = (owner, group, perms)
    if any(x is None for x in t):
        try:
            info = os.stat(filename)
            if uid is None:
                uid = info.st_uid
            if gid is None:
                gid = info.st_gid
            if mod is None:
                mod = stat.S_IMODE(info.st_mode)
        except FileNotFoundError:
            if uid is None:
                uid = -1
            if gid is None:
                gid = -1
    path = os.path.dirname(filename)
    fd, tmp = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=path, text=text)
    try:
        with os.fdopen(fd, 'w' if text else 'wb') as f:
            yield f
        # Perform an atomic rename (if possible). This will be atomic on
        # POSIX systems, and Windows for Python 3.3 or higher.
        os.replace(tmp, filename)
        tmp = None
        if mod is not None:
            os.chmod(filename, mod)
        try:
            os.chown(filename, uid, gid)
        except PermissionError:
            pass
    finally:
        if (tmp is not None) and (not keep):
            # Silently delete the temporary file. Ignore any errors.
            # noinspection PyBroadException
            try:
                os.unlink(tmp)
            except Exception:
                pass
