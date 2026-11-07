import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts import r2_mirror

class MirrorTests(unittest.TestCase):
    def test_complete_inventory_does_not_launch_transfer(self):
        report = {'uploadedResources': 6793, 'missingResources': 0}
        with tempfile.TemporaryDirectory() as directory, patch.object(r2_mirror, 'FOLDER', Path(directory)), patch.object(r2_mirror, 'verify', return_value=report), patch.object(r2_mirror.subprocess, 'Popen') as launch, patch('sys.argv', ['mirror']), contextlib.redirect_stdout(io.StringIO()):
            r2_mirror.main()
            launch.assert_not_called()
            self.assertIn('"state": "complete"', (Path(directory)/'mirror-job.json').read_text())

    def test_retry_uses_frozen_missing_only_plan_and_verifies_completion(self):
        pending = {'uploadedResources': 6792, 'missingResources': 1}
        complete = {'uploadedResources': 6793, 'missingResources': 0}
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            (folder/'missing-resources.csv').write_text('https://example.org/source,raw/dataset/resource/source\n')
            child=MagicMock(); child.poll.return_value=0; child.returncode=0
            with patch.object(r2_mirror, 'FOLDER', folder), patch.object(r2_mirror, 'verify', side_effect=[pending, complete]), patch.object(r2_mirror.subprocess, 'Popen', return_value=child) as launch, patch('sys.argv', ['mirror', '--passes', '1']), contextlib.redirect_stdout(io.StringIO()):
                r2_mirror.main()
            command=launch.call_args.args[0]
            self.assertEqual(command[:3], ['rclone','copyurl','--urls'])
            self.assertEqual(Path(command[3]).read_text(), (folder/'missing-resources.csv').read_text())
            self.assertIn('--no-clobber',command)
            self.assertIn('"state": "complete"',(folder/'mirror-job.json').read_text())
