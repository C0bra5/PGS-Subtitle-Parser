# BluRay PGS Subtitle Parser
A simple library for parsing, updating and creating [Presentation Graphic Stream (PGS)](https://en.wikipedia.org/wiki/Presentation_Graphic_Stream) subtitle files. These files are usually stored with a .sup extension. These subtiles are stored as bitmap, _not text_, so if you want to convert them to text, you'll need to use OCR. [Subtitle Edit](https://github.com/SubtitleEdit/subtitleedit) should be able to handle that natively as a command line tool if you want a quick solution for that.


## PGS library requirements:
These are just the versions I used to make this, you can probably go lower on some
- python >= 3.10.0
- numpy >= 2.2.0
- pillow >= 11.1.0

## Usage example
Extracting all the images out of a subtitle file to pngs
```py
from pgs import PGSParser

# read the subtitle contents
with open('./sample/sup1.sup', 'rb') as f:
	data = f.read()

# parse it
parsed = PGSParser.read_from_bytes(data)

# dumps all the images to a png
parsed.save_images('./out_images')
```

If you want to write a sup file, you're going to need to familiarize yourself with the format before hand, here is a good article about the gist of it: https://blog.thescorpius.com/index.php/2017/07/15/presentation-graphic-stream-sup-files-bluray-subtitle-format/

You'll need an rle compressed palette encoded image. The palette will use YCbCrA as it's color format. You can use encode_pgs_rle to encode an uncompressed list of bytestrings representing each line to get the compressed data.

The palette data will have to be stored into a PDS segment that is part of the same epoch or display set as the ODS.

If you need to edit an image while an other display object is visible, you'll need to  update create a new PDS segment for that display set since each PCS can only use 1 palette for both of the objects visible on screen.

## Example.py
If you want an example of the parser reading a file, doing some image processing and writing a new valid file, take a look at example.py

Software requirements to run example.py:
- [FFmpeg](https://ffmpeg.org/download.html)
- [FFprobe](https://ffmpeg.org/download.html)
- [mkvpropedit](https://mkvtoolnix.download/downloads.html)
- [ImageMagick](https://imagemagick.org/script/download.php)

before:  
![](./docs/before.gif)

after:  
![](./docs/after.gif)

## Folder contents
Folder  | Content Description
--------|-----------------------------------------
pgs     | The library used to parse PGS data
tests   | Unit tests for the parser
ffprobe | Quick parser/typing provider for ffprobe for the example script
sample  | Sample files used in example.py, only sample.mkv is actually used
docs    | Images for the readme