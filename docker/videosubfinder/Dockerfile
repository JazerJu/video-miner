# Carrier image for the VideoSubFinder CLI binary used by hard-subtitle extraction.
# The main Dockerfile gets the binary with COPY --from. This image has no OS and does not run.
#
# The binary is 45 MB, so it is not in git. It also lives in the model repositories
# (JazerJu/VideoMiner and modelmo/VideoMiner, path videosubfinder/), which is where a source
# install downloads it from.
#
# To publish it again:
#   1. Put VideoSubFinderCli in this directory. Git ignores it.
#   2. docker build -t jaceju68/videosubfinder:vse-2.2.0 docker/videosubfinder
#   3. docker push jaceju68/videosubfinder:vse-2.2.0
#   4. Update the sha256 value in the main Dockerfile.
FROM scratch
LABEL org.opencontainers.image.title="VideoSubFinder CLI (Linux, static)" \
      org.opencontainers.image.description="Copied from backend/subfinder/linux of video-subtitle-extractor 2.2.0" \
      org.opencontainers.image.source="https://sourceforge.net/projects/videosubfinder/" \
      org.opencontainers.image.licenses="GPL-2.0-only"
COPY VideoSubFinderCli /videosubfinder/
