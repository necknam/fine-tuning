"""Content equality is required; cache names are not assumed to be SHA-256."""
import hashlib,tempfile,unittest
from pathlib import Path
from consolidate_model_cache import verify_pair

class CacheContentVerificationTests(unittest.TestCase):
    def test_identical_content_with_non_content_address_filename_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'source';b=Path(folder)/'retained';a.mkdir();b.mkdir()
            name='0'*64;left=a/name;right=b/name
            left.write_bytes(b'valid cached model fragment');right.write_bytes(left.read_bytes())
            self.assertEqual(verify_pair(left,right),hashlib.sha256(left.read_bytes()).hexdigest())

    def test_same_name_and_size_with_different_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a';b=Path(folder)/'b';a.write_bytes(b'ABC');b.write_bytes(b'XYZ')
            with self.assertRaisesRegex(ValueError,'differ'):verify_pair(a,b)
            self.assertEqual(a.read_bytes(),b'ABC');self.assertEqual(b.read_bytes(),b'XYZ')

if __name__=='__main__':unittest.main()
