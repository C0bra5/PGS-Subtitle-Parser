@echo off
rem the warns here are expected and i have no idea what's causing them
ffmpeg -i ".\video.mkv" -i ".\audio.wav" -i ".\sup1.sup" -i ".\sup2.sup" -i ".\ass1.ass" ^
	-map 0 -map 1 -map 2 -map 3 -map 4 -c copy ^
	-avoid_negative_ts make_zero ^
	-metadata:s:3 title="sub to edit #2" -metadata:s:3 language=eng ^
	-metadata:s:4 title="non PGS sub" -metadata:s:4 language=eng ^
	sample.mkv

mkvpropedit ".\sample.mkv" ^
	--edit track:1 --set flag-default=0 ^
	--edit track:2 --set flag-default=0 ^
	--edit track:3 --set flag-default=0 ^
	--edit track:4 --set flag-default=1 ^
	--edit track:5 --set flag-default=0