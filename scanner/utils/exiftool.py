#!/usr/bin/env python
"""
This is a Python library to communicate with an instance of Phil
Harvey's excellent ExifTool_ command-line application. The library
provides the class :py:class:`ExifTool` that runs the command-line
tool in batch mode and features methods to send commands to that
program, including methods to extract meta-information from one or
more image files.  Since ``exiftool`` is run in batch mode, only a
single instance needs to be launched and can be reused for many
queries.  This is much more efficient than launching a separate
process for every single query.

.. _ExifTool: http://www.sno.phy.queensu.ca/~phil/exiftool/

This libary has been adapted from PyExifTool which can be found here:
https://github.com/smarnach/pyexiftool (licenced under the GNU GPLv3)

Example usage::

    from exiftool import ExifTool

    tags = ["EXIF:DateTimeOriginal", "EXIF:Flash"]
    files = ["a.jpg", "b.png", "c.tif"]
    with ExifTool() as e:
        metadata = e.process_files(files, tags=tags)
    for d in metadata:
        print("{:20.20} {:20.20}".format(d["SourceFile"],
                                         d["EXIF:DateTimeOriginal"]))
"""

import subprocess
from threading import Thread
import json


# Executable to use (it must exist on the PATH)
EXECUTABLE = "exiftool"

# Sentinel indicating the end of the output of a sequence of commands.
SENTINEL = "{ready}"


class ExifTool(object):
    """Run the `exiftool` command-line tool and communicate to it.

    The ``exiftool`` executable must be in your ``PATH`` for this to work.

    Most methods of this class are only available after calling
    :py:meth:`start()`, which will actually launch the subprocess.  To
    avoid leaving the subprocess running, make sure to call
    :py:meth:`terminate()` method when finished using the instance.
    This method will also be implicitly called when the instance is
    garbage collected, but there are circumstance when this won't ever
    happen, so you should not rely on the implicit process
    termination.  Subprocesses won't be automatically terminated if
    the parent process exits, so a leaked subprocess will stay around
    until manually killed.

    A convenient way to make sure that the subprocess is terminated is
    to use the :py:class:`ExifTool` instance as a context manager::

        with ExifTool() as et:
            ...

    .. warning:: Note that there is no error handling.  Nonsensical
       options will be silently ignored by exiftool, so there's not
       much that can be done in that regard.  You should avoid passing
       non-existent files to any of the methods, since this will lead
       to undefied behaviour.

    .. py:attribute:: running

       A Boolean value indicating whether this instance is currently
       associated with a running subprocess.
    """

    def __init__(self):
        self._process = None

    @property
    def running(self):
        return self._process is not None

    def run(self):
        """Start an ``exiftool`` process in batch mode for this instance.

        The process is started with the ``-G``, ``-n``, and ``-j`` as common
        arguments, which are automatically included in every command you run
        with :py:meth:`raw_execute()`.
        """
        if self.running:
            return
        self._process = subprocess.Popen(
            [EXECUTABLE, "-stay_open", "True",  "-@", "-", "-common_args",
             "-G", "-j"],
            universal_newlines=True,
            bufsize=1,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)

    def terminate(self):
        """Terminate the ``exiftool`` process of this instance.

        If the subprocess isn't running, this method will do nothing.
        """
        if not self.running:
            return
        self._process.stdin.write("-stay_open\nFalse\n")
        self._process.stdin.flush()

        # Give it 1 second to shut down nicely, otherwise just kill it
        try:
            self._process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self._process.terminate()

        del self._process
        self._process = None

    def __enter__(self):
        self.run()
        return self

    def __exit__(self, *_):
        self.terminate()

    def __del__(self):
        self.terminate()

    def _read_stdout(self, buff):
        """Read lines from the subpresses stdout into `buff` in-place until the
        SENTINEL is encountered"""
        while True:
            line = self._process.stdout.readline()
            if line.strip() == SENTINEL:
                break
            buff.append(line)

    def raw_execute(self, *params, timeout=10):
        """Execute the given batch of parameters with ``exiftool``.

        This method accepts any number of parameters and sends them to the
        attached ``exiftool`` process.  The process must be running, otherwise
        an error will be raised.

        The final ``-execute`` necessary to actually run the batch is appended
        automatically; see the documentation of :py:meth:`run()` for the
        common options. The ``exiftool`` output is read up to the
        end-of-output sentinel and returned as a string, excluding the
        sentinel.

        If the tool doesn't respond with the sentinel within the time alloted
        by the ``timeout`` parameter (10 seconds by default), a
        ``subprocess.TimeoutExpired`` exception will be raised. By specifying
        ``None`` as the timeout, the call will block forever.

        .. note:: This is considered a low-level method, and should rarely be
           needed by application developers. As a result, there is no real
           error handling in it.
        """
        self._process.stdin.write("\n".join(params + ("-execute\n",)))
        self._process.stdin.flush()

        buff = []
        # Use a thread to pull data into the buffer so we can use a timeout
        stdout_thread = Thread(target=self._read_stdout, args=(buff,),
                               daemon=True)
        stdout_thread.start()
        stdout_thread.join(timeout=timeout)
        if stdout_thread.is_alive():
            raise subprocess.TimeoutExpired(params, timeout)
        return "".join(buff)

    def process_files(self, files, *, tags=None, timeout=None):
        """Process a batch of files with ``exiftool``.

        This method processes a single file or a list of files with the
        ``exiftool`` subprocess and returns the results.

        The tags to extract can be specified with the ``tags`` parameter
        (single strig or a list of strings).

        By default, a ``subprocess.TimeoutExpired`` exception will be raised
        after 5 seconds * the number of files (ie. 10 seconds to process 2
        files) if the tool hasn't finished responding. An alternative timeout
        can be specified with the ``timeout`` parameter.

        The return value is a list of dictionaries, mapping tag names to the
        corresponding values. All keys are strings with the tag names including
        the ExifTool group name in the format <group>:<tag>. The values can
        have multiple types. Each dictionary contains the name of the file it
        corresponds to in the key ``"SourceFile"``. If multiple files are
        specified, they will be returned in the order they were specified.

        If the exiftool process isn't running, it will automatically be
        started, the commands will be run, then it will be stopped. To enable
        batch processing, use this class as a context manager or call
        `run()` and `terminate()` manually.
        """

        if not files:
            return []

        batch = self.running
        if not batch:
            self.run()

        # Handle single strings vs. lists
        if isinstance(tags, str):
            tags = [tags]
        if isinstance(files, str):
            files = [files]

        if not timeout:
            timeout = len(files) * 5

        params = ["-" + t for t in tags] if tags else []
        params.extend(files)

        data = json.loads(self.raw_execute(*params, timeout=timeout))

        if not batch:
            self.terminate()
        return data
