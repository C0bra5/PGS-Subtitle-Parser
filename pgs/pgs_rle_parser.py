import struct


def encode_pgs_rle(decoded: list[bytes]) -> bytes:
	# empty results always return empty
	decoded = decoded.copy()
	if len(decoded) <= 0: return b'\x00\x00'

	writer = b''
	for line in decoded:
		x = 0
		while x < len(line):
			repeat = 1
			color = line[x]
			while (x + repeat) < len(line) and line[x + repeat] == color:
				repeat += 1
			
			if color == 0x00:
				# first palette is always length encoded even if len == 1 or 2
				if repeat >= 64:
					writer += b'\x00'
					writer += (0x4000 | (repeat & 0x3fff)).to_bytes(2, 'big', signed=False)
				else:
					writer += b'\x00'
					writer += (repeat & 0x3f).to_bytes(1, 'big', signed=False)
			else:
				if repeat >= 64:
					# 0b0000_0000 0b11LL_LLLL 0bLLLL_LLLL 0xCCCC_CCCC = L pixels in color C
					writer += b'\x00'
					writer += (0xc000 | (repeat & 0x3fff)).to_bytes(2, 'big', signed=False)
				elif repeat >= 3:
					# 0b0000_0000 0b10LL_LLLL 0xCCCC_CCCC = L pixels in color C
					writer += b'\x00'
					writer += (0x80 | (repeat & 0x3f)).to_bytes(1, 'big', signed=False)
				elif repeat == 2:
					# repeats of color under 3 are just written as is
					writer += color.to_bytes(1, 'big', signed=False)
				# color is always the termination of a color segment
				writer += color.to_bytes(1, 'big', signed=False)
				

			x += repeat
		writer += b'\x00\x00'

	return writer	

	
def encode_pgs_rle_old(decoded: list[bytes]) -> bytes:
	# empty results always return empty
	decoded = decoded.copy()
	if len(decoded) <= 0: return b'\x00\x00'

	writer = b''
	for line in decoded:
		end_at = len(line)
		at = 0
		while at < end_at:
			color = line[at]
			at += 1
			repeat = 1
			while at <= end_at and repeat < 16383:
				# try to read the new color
				new_color = None
				if (at < end_at):
					new_color = line[at]
					at += 1
				# increase repeat if repeat
				if new_color == color:
					repeat += 1
				else:
					if color == 0x00:
						# palette 0 is always length encoded even if len is 1 or 2
						if repeat > 63:
							writer += struct.pack('>BH', color, repeat | 0b01_000000_00000000)
						else:
							writer += struct.pack('>BB', color, repeat)
					else:
						if repeat > 63:
							# 0b0000_0000 0b11LL_LLLL 0bLLLL_LLLL 0xCCCC_CCCC = L pixels in color C
							writer += struct.pack('>BH', 0x00, repeat | 0b11_000000_00000000)
						elif repeat > 2:
							# 0b0000_0000 0b10LL_LLLL 0xCCCC_CCCC = L pixels in color C
							writer += struct.pack('>BB', 0x00, repeat | 0b10_000000)
						elif repeat > 1:
							# 0bCCCC_CCCC 0bCCCC_CCCC = 2 pixels of color C
							writer += struct.pack('>B', color)
						# 0bCCCC_CCCC = 1 pixel of color C
						writer += struct.pack('>B', color)
					repeat = 1
					color = new_color
				
		# always end with end marker
		writer += b'\x00\x00'
	return writer

def decode_pgs_rle(ods_bytes: bytes) -> list[bytes]:
	lines = []
	buffer = []

	i = 0
	while i < len(ods_bytes):
		if ods_bytes[i]:
			incr = 1
			color = ods_bytes[i]
			length = 1
		else:
			check = ods_bytes[i+1]
			if check == 0:
				incr = 2
				color = 0
				length = 0
				lines.append(buffer)
				buffer = []
			elif check < 64:
				incr = 2
				color = 0
				length = check
			elif check < 128:
				incr = 3
				color = 0
				length = ((check - 64) << 8) + ods_bytes[i + 2]
			elif check < 192:
				incr = 3
				color = ods_bytes[i+2]
				length = check - 128
			else:
				incr = 4
				color = ods_bytes[i+3]
				length = ((check - 192) << 8) + ods_bytes[i + 2]
		buffer.extend([color]*length)
		i += incr

	for i in range(0, len(lines)):
		lines[i] = bytes(lines[i])
	return lines