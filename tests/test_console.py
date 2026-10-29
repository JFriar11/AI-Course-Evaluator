import errno
import unittest
from unittest.mock import patch

from console import safe_print
import watcher


class ConsoleTests(unittest.TestCase):
    def test_disconnected_console_does_not_interrupt_evaluation(self):
        for code in (errno.EIO, errno.EPIPE, errno.EBADF):
            with patch('builtins.print', side_effect=OSError(code, 'terminal unavailable')):
                watcher.print('Evaluation progress', flush=True)

    def test_other_io_errors_are_preserved(self):
        with patch('builtins.print', side_effect=OSError(errno.ENOSPC, 'disk full')):
            with self.assertRaises(OSError):
                safe_print('progress')

    def test_output_still_prints_normally(self):
        with patch('builtins.print') as output:
            safe_print('progress', flush=True)
            output.assert_called_once_with('progress', flush=True)
