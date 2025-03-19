import unittest
from pgs import decode_pgs_rle, encode_pgs_rle
from pathlib import Path

class TestRLE(unittest.TestCase):


	def test_decode_end(self):
		# 0b0000_0000 0b0000_0000 = end
		encoded = b'\x00\x00'
		expected = [b'']
		decoded = decode_pgs_rle(encoded)
		self.assertEqual(expected, decoded)

	def test_decode_0L(self):
		# 0b0000_0000 0b01LL_LLLL 0bLLLL_LLLL = L pixels in color 0
		encoded = b'\x00' + int.to_bytes(0b00_00_0111, 1, byteorder='big') + b'\x00\x00'
		expected = [b'\x00' * 0b00_00_0111]
		decoded = decode_pgs_rle(encoded)
		self.assertEqual(expected, decoded)

	def test_decode_0LL(self):
		# 0b0000_0000 0b01LL_LLLL 0bLLLL_LLLL = L pixels in color 0
		encoded = b'\x00' + int.to_bytes(0b01_00_0000_1111_1111, 2, byteorder='big') + b'\x00\x00'
		expected = [b'\x00' * 0b00_00_0000_1111_1111]
		decoded = decode_pgs_rle(encoded)
		self.assertEqual(expected, decoded)

	def test_decode_0LL_2(self):
		# 0b0000_0000 0b01LL_LLLL 0bLLLL_LLLL = L pixels in color 0
		encoded = b'\x00' + int.to_bytes(0b01_00_0011_1111_1111, 2, byteorder='big') + b'\x00\x00'
		expected = [b'\x00' * 0b00_00_0011_1111_1111]
		decoded = decode_pgs_rle(encoded)
		self.assertEqual(expected, decoded)

	def test_decode_0LC(self):
		# 0b0000_0000 0b01LL_LLLL 0bLLLL_LLLL = L pixels in color 0
		encoded = b'\x00' + int.to_bytes(0b10_11_1111, 1, byteorder='big') + b'P\x00\x00'
		expected = [b'P' * 0b00_11_1111]
		decoded = decode_pgs_rle(encoded)
		self.assertEqual(expected, decoded)

	def test_decode_0LLC(self):
		# 0b0000_0000 0b01LL_LLLL 0bLLLL_LLLL = L pixels in color 0
		encoded = b'\x00' + int.to_bytes(0b11_00_0000_0011_1111, 2, byteorder='big') + b'J\x00\x00'
		expected = [b'J' * 0b00_00_0000_0011_1111]
		decoded = decode_pgs_rle(encoded)
		self.assertEqual(expected, decoded)

	def test_decode_0LLC2(self):
		# 0b0000_0000 0b01LL_LLLL 0bLLLL_LLLL = L pixels in color 0
		encoded = b'\x00' + int.to_bytes(0b11_00_0110_0011_1111, 2, byteorder='big') + b'J\x00\x00'
		expected = [b'J' * 0b00_00_0110_0011_1111]
		decoded = decode_pgs_rle(encoded)
		self.assertEqual(expected, decoded)




	def test_encode_empty(self):
		decoded = [b'']
		expected = b'\x00\x00'
		encoded = encode_pgs_rle(decoded)
		self.assertEqual(expected, encoded)

		

	def test_encode_0L(self):
		decoded = [b'\x00']
		expected = b'\x00\x01' + b'\x00\x00'
		encoded = encode_pgs_rle(decoded)
		self.assertEqual(expected, encoded)

		

	def test_encode_0LL(self):
		decoded = [b'\x00' * 0xff]
		expected = b'\x00' + (0b01 << 14 | 0xff).to_bytes(2, 'big') + b'\x00\x00'
		encoded = encode_pgs_rle(decoded)
		self.assertEqual(
			' '.join(f'{b:02x}' for b in expected),
			' '.join(f'{b:02x}' for b in encoded)
		)

	def test_encode_C(self):
		decoded = [b'd']
		expected = b'd' + b'\x00\x00'
		encoded = encode_pgs_rle(decoded)
		self.assertEqual(
			' '.join(f'{b:02x}' for b in expected),
			' '.join(f'{b:02x}' for b in encoded)
		)

	def test_encode_CC(self):
		decoded = [b'JJ']
		expected = b'JJ' + b'\x00\x00'
		encoded = encode_pgs_rle(decoded)
		self.assertEqual(
			' '.join(f'{b:02x}' for b in expected),
			' '.join(f'{b:02x}' for b in encoded)
		)

	def test_encode_0LC(self):
		decoded = [b'555']
		expected = b'\x00' + (0b10 << 6 | 3).to_bytes(1, 'big') + b'5\x00\x00'
		encoded = encode_pgs_rle(decoded)
		self.assertEqual(
			' '.join(f'{b:02x}' for b in expected),
			' '.join(f'{b:02x}' for b in encoded)
		)

	def test_encode_0LLC(self):
		decoded = [b'y' * 64]
		expected = b'\x00' + (0b11 << 14 | 64).to_bytes(2, 'big') + b'y\x00\x00'
		encoded = encode_pgs_rle(decoded)
		self.assertEqual(
			' '.join(f'{b:02x}' for b in expected),
			' '.join(f'{b:02x}' for b in encoded)
		)



	def test_reencode(self):
		expected = \
			b'\x00\xa2\xff\x04\x05\x00\x84\x02\x05\x04\x00\xc1\x54\xff\x04\x05\x00\x85\x02\x05\x04\x00\xc0\x57\xff\x00\x00' \
			+ b'\x00\xa2\xff\x05\x06\x00\x84\x03\x07\x02\x04\x00\xc1\x53\xff\x05\x06\x00\x85\x03\x06\x05\x00\xc0\x57\xff\x00\x00' \
			+ b'\x00\xa2\xff\x02\x03\x9c\x00\x83\x1e\x5f\x07\x05\x00\xc1\x53\xff\x02\x03\x00\x00' 
		
		rewritten = encode_pgs_rle(decode_pgs_rle(expected))
		self.assertEqual(
			' '.join(f'{b:02x}' for b in expected),
			' '.join(f'{b:02x}' for b in rewritten)
		)