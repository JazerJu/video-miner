# glm-asr-stack

Packaged runtime layout for GLM-ASR Infer-engine + ForceAligner.

## Layout

```text
bin/
  orchestrator.py        # long audio / queue / live session orchestration
  glm_asr_infer          # wrapper: selects arch binary + FA2 bridge
  force_aligner          # wrapper: selects arch binary
  detect_arch            # maps GPU compute capability to sm86/sm89/sm120
  select_fa2_bridge      # selects cutedsl_fa/fa2_bridge.so symlink
  glm-asr-doctor         # runtime diagnostics
Infer-engine/
  glm_asr_infer_sm120    # local build; add sm86/sm89 via scripts
forcealigner-engine/
  force_aligner_sm120    # local build; add sm86/sm89 via scripts
  mel_filterbank.bin
cutedsl_fa/
  fa2_bridge_sm86.so
  fa2_bridge_sm89.so
  fa2_bridge_sm120.so
lib/
  libtvm_ffi.so
resources/
  mel_filters.bin
models/
  glm-asr-bf16/
  qwen3-forcealigner-0.6b/
runtime/
```

## Model repos

- `zai-org/GLM-ASR-Nano-2512`
- `Qwen/Qwen3-ForcedAligner-0.6B`

Models are not included in release tarballs. Put or symlink them under `models/`.

## Smoke test

```bash
cd /path/to/glm-asr-stack
bin/glm-asr-doctor
python3 bin/orchestrator.py \
  --audio /path/to/input.mp3 \
  --model models/glm-asr-bf16 \
  --mel resources/mel_filters.bin \
  --fa-model models/qwen3-forcealigner-0.6b \
  --subtitle-mode sentence \
  --output runtime/output/input_sentence.srt
```

Use `--asr-only` to skip ForceAligner.

## Build arch binaries

Run from this stack after the source repos are available:

```bash
scripts/build_infer_arch.sh sm86
scripts/build_forcealigner_arch.sh sm86
scripts/build_infer_arch.sh sm89
scripts/build_forcealigner_arch.sh sm89
scripts/build_infer_arch.sh sm120
scripts/build_forcealigner_arch.sh sm120
```

Default source paths:

- `/data/fwsr/glm-asr/Infer-engine`
- `/data/fwsr/glm-asr/forcealigner-engine`

Override with:

```bash
GLM_ASR_INFER_SRC=/path/to/Infer-engine \
GLM_ASR_FORCEALIGNER_SRC=/path/to/forcealigner-engine \
CUDA_HOME=/usr/local/cuda-12.8 \
scripts/build_infer_arch.sh sm120
```

## Package

```bash
scripts/package_stack.sh /tmp/glm-asr-stack.tar.gz
```

The package excludes model weights and runtime outputs.
