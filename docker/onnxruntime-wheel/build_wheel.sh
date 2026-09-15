#!/usr/bin/env bash
# Build the onnxruntime-gpu 1.30.0 wheel for CUDA 12.8 and Python 3.12.
#
# Why: WeMM's ONNX build needs the com.microsoft.GatedDeltaNet operator. This operator first shipped
# in onnxruntime 1.30. Every GPU wheel on PyPI since 1.28 targets CUDA 13. The VideoMiner image
# uses CUDA 12.8, and its llama.cpp libraries link cuBLAS 12.
#
# The arguments match the CUDA 12.8 branch of the official script
# tools/ci_build/github/linux/build_linux_python_package.sh.
#
# Requirements:
#   - A conda env at $ENV with: cuda-toolkit=12.8.1 (channel nvidia/label/cuda-12.8.1), python=3.12,
#     ninja, "cmake>=3.31" and "binutils>=2.40" (channel conda-forge), and the pip package
#     nvidia-cudnn-cu12==9.8.0.87.
#   - GCC 11 to 14 at $GCC. The build used GCC 12.3.
#   - A glibc that is not newer than the target system. The build used CentOS 8 (glibc 2.28).
#
# Problems that this script prevents:
#   - An old system assembler (binutils 2.30) cannot assemble AVX-VNNI instructions in MLAS.
#     The conda binutils must come first on PATH.
#   - If anaconda is on PATH, CMake links its protobuf, re2 and abseil shared libraries and writes a
#     fixed library path. The wheel then fails to import on other machines. Keep anaconda off PATH
#     and set FETCHCONTENT_TRY_FIND_PACKAGE_MODE=NEVER.
#   - Direct downloads from GitHub can fail during dependency fetch. Set a proxy if necessary.
#
# One build takes about 31 minutes on 384 threads.
set -eo pipefail
B=${B:-$HOME/ort-build}
SRC=${SRC:-$B/onnxruntime-1.30.0}      # git clone --branch v1.30.0 --recurse-submodules https://github.com/microsoft/onnxruntime
ENV=${ENV:-$B/env}
GCC=${GCC:-/opt/gcc-12.3}
PARALLEL=${PARALLEL:-128}
CUDNN_PIP=$ENV/lib/python3.12/site-packages/nvidia/cudnn

# cudnn_home needs include/ and lib/libcudnn*.so. The pip package only has the .so.9 names.
mkdir -p "$B/cudnn/lib"
ln -sfn "$CUDNN_PIP/include" "$B/cudnn/include"
for f in "$CUDNN_PIP"/lib/libcudnn*.so.9; do
  ln -sf "$f" "$B/cudnn/lib/$(basename "$f")"
  ln -sf "$f" "$B/cudnn/lib/$(basename "$f" .9)"
done

export PATH=$ENV/bin:$GCC/bin:/usr/local/bin:/usr/bin:/bin
export LD_LIBRARY_PATH=$GCC/lib64:$ENV/lib
export CUDA_HOME=$ENV ONNX_ML=1 CMAKE_ARGS="-DONNX_GEN_PB_TYPE_STUBS=ON -DONNX_WERROR=OFF"
unset OMP_NUM_THREADS

"$ENV/bin/pip" install -q -r "$SRC/tools/ci_build/github/linux/python/requirements.txt"
cd "$SRC"
"$ENV/bin/python" tools/ci_build/build.py --build_dir "$B/build" --config Release --update --build \
  --skip_submodule_sync --build_wheel --parallel "$PARALLEL" --skip_tests --compile_no_warning_as_error \
  --use_cuda --cuda_version=12.8 --cuda_home="$ENV" --cudnn_home="$B/cudnn" --nvcc_threads=1 --flash_nvcc_threads=1 \
  --cmake_extra_defines "CMAKE_CUDA_ARCHITECTURES=60-real;70-real;75-real;80-real;86-real;89-real;90-real;120-real" \
    onnxruntime_USE_FPA_INTB_GEMM=ON onnxruntime_BUILD_UNIT_TESTS=OFF \
    FETCHCONTENT_TRY_FIND_PACKAGE_MODE=NEVER \
    CMAKE_C_COMPILER="$GCC/bin/gcc" CMAKE_CXX_COMPILER="$GCC/bin/g++" CMAKE_CUDA_HOST_COMPILER="$GCC/bin/g++"

# Check that the core libraries only need system libraries.
for lib in "$B/build/Release/libonnxruntime.so.1.30.0" "$B/build/Release/onnxruntime_pybind11_state.so"; do
  if LD_LIBRARY_PATH= ldd "$lib" | grep -E "protobuf|absl|re2|not found"; then
    echo "ERROR: $lib links a non-system library" >&2
    exit 1
  fi
done
ls -la "$B/build/Release/dist/"
