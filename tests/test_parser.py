import unittest
from pgs import PGSParser, decode_pgs_rle, encode_pgs_rle
from pathlib import Path

class TestParser(unittest.TestCase):


	def test_simple(self):
		print(__file__)
		with open(Path(__file__).parent / 'simple.sup', 'rb') as f:
			contents = f.read()
		parsed = PGSParser.read_from_bytes(contents)
		rle_data = parsed.display_sets[0].ods[0].rle_data
		parsed.display_sets[0].ods[0].rle_data = encode_pgs_rle(decode_pgs_rle(rle_data))
		rewritten = parsed.write()
		self.assertEqual(contents, rewritten)

	def test_complex_file(self):
		print(__file__)
		with open(Path(__file__).parent / 'complex.sup', 'rb') as f:
			contents = f.read()
		parsed = PGSParser.read_from_bytes(contents)
		rle_data = parsed.display_sets[0].ods[0].rle_data
		parsed.display_sets[0].ods[0].rle_data = encode_pgs_rle(decode_pgs_rle(rle_data))
		rewritten = parsed.write()
		self.assertEqual(contents, rewritten)