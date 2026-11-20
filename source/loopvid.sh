#!/bin/sh
# Бесшовное кольцо: конец клипа плавно перетекает в начало (без реверса и без приближения).
# usage: loopvid.sh in.mp4 out.mp4 [crossfade_sec]
IN="$1"; OUT="$2"; X="${3:-1.2}"
D=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$IN")
OFF=$(python3 -c "print(round($D-2*$X,3))")
ffmpeg -v error -y -i "$IN" -i "$IN" -an -filter_complex "
[0:v]crop=iw-48:ih:24:0,trim=start=$X,setpts=PTS-STARTPTS,fps=24,format=yuv420p[a];
[1:v]crop=iw-48:ih:24:0,trim=end=$X,setpts=PTS-STARTPTS,fps=24,format=yuv420p[b];
[a][b]xfade=transition=fade:duration=$X:offset=$OFF,unsharp=5:5:0.35:5:5:0.0,setsar=1[o]" \
 -map "[o]" -c:v libx264 -preset slow -crf 20 -profile:v high -pix_fmt yuv420p -movflags +faststart "$OUT"
