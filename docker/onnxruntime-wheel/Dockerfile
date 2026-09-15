# Carrier image for the onnxruntime-gpu 1.30.0 wheel that is built against CUDA 12.8.
# The main Dockerfile gets the wheel with COPY --from. This image has no OS and does not run.
#
# To publish a new wheel:
#   1. Build the wheel with build_wheel.sh.
#   2. Put the wheel file in this directory. Git ignores it.
#   3. docker build -t jaceju68/onnxruntime-gpu-wheel:1.30.0-cu128 docker/onnxruntime-wheel
#   4. docker push jaceju68/onnxruntime-gpu-wheel:1.30.0-cu128
#   5. Update the sha256 value in the main Dockerfile.
FROM scratch
LABEL org.opencontainers.image.title="onnxruntime-gpu 1.30.0 wheel for CUDA 12.8" \
      org.opencontainers.image.source="https://github.com/microsoft/onnxruntime/tree/v1.30.0" \
      org.opencontainers.image.revision="f2c39fe2f838cf35ce7da92824f5a5e3ee6e88a7" \
      org.opencontainers.image.licenses="MIT"
COPY onnxruntime_gpu-1.30.0-cp312-cp312-linux_x86_64.whl /wheels/
