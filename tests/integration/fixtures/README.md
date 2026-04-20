# Integration fixtures

`short.mp3` is 5 seconds of silence generated with:

    ffmpeg -f lavfi -i anullsrc=r=16000:cl=mono -t 5 \
           -c:a libmp3lame -q:a 9 -y short.mp3

Kept under version control because at ~5 KB it's cheaper to commit than
to regenerate in CI. If you need a fixture with actual speech for a
specific regression, add it as a separate file and reference it explicitly
from the test.
