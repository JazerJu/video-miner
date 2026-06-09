# coding=utf-8
"""
llama.cpp ctypes bindings for MiniCPM-V ONNX + GGUF hybrid inference.

Adapted from Qwen3-ASR-GGUF/qwen_asr_gguf/inference/llama.py
Stripped ASR-specific logic, kept core: Model, Context, Batch (with embd), Sampler.
"""
import os
import sys
import time
import ctypes
from typing import List, Optional
from pathlib import Path

# =========================================================================
# Type Definitions
# =========================================================================

llama_token = ctypes.c_int32
llama_pos = ctypes.c_int32
llama_seq_id = ctypes.c_int32


class llama_model_params(ctypes.Structure):
    _fields_ = [
        ("devices", ctypes.POINTER(ctypes.c_void_p)),
        ("tensor_buft_overrides", ctypes.POINTER(ctypes.c_void_p)),
        ("n_gpu_layers", ctypes.c_int32),
        ("split_mode", ctypes.c_int32),
        ("main_gpu", ctypes.c_int32),
        ("tensor_split", ctypes.POINTER(ctypes.c_float)),
        ("progress_callback", ctypes.c_void_p),
        ("progress_callback_user_data", ctypes.c_void_p),
        ("kv_overrides", ctypes.POINTER(ctypes.c_void_p)),
        ("vocab_only", ctypes.c_bool),
        ("use_mmap", ctypes.c_bool),
        ("use_direct_io", ctypes.c_bool),
        ("use_mlock", ctypes.c_bool),
        ("check_tensors", ctypes.c_bool),
        ("use_extra_bufts", ctypes.c_bool),
        ("no_host", ctypes.c_bool),
        ("no_alloc", ctypes.c_bool),
    ]


class llama_context_params(ctypes.Structure):
    _fields_ = [
        ("n_ctx", ctypes.c_uint32),
        ("n_batch", ctypes.c_uint32),
        ("n_ubatch", ctypes.c_uint32),
        ("n_seq_max", ctypes.c_uint32),
        ("n_threads", ctypes.c_int32),
        ("n_threads_batch", ctypes.c_int32),
        ("rope_scaling_type", ctypes.c_int32),
        ("pooling_type", ctypes.c_int32),
        ("attention_type", ctypes.c_int32),
        ("flash_attn_type", ctypes.c_int32),
        ("rope_freq_base", ctypes.c_float),
        ("rope_freq_scale", ctypes.c_float),
        ("yarn_ext_factor", ctypes.c_float),
        ("yarn_attn_factor", ctypes.c_float),
        ("yarn_beta_fast", ctypes.c_float),
        ("yarn_beta_slow", ctypes.c_float),
        ("yarn_orig_ctx", ctypes.c_uint32),
        ("defrag_thold", ctypes.c_float),
        ("cb_eval", ctypes.c_void_p),
        ("cb_eval_user_data", ctypes.c_void_p),
        ("type_k", ctypes.c_int32),
        ("type_v", ctypes.c_int32),
        ("abort_callback", ctypes.c_void_p),
        ("abort_callback_data", ctypes.c_void_p),
        ("embeddings", ctypes.c_bool),
        ("offload_kqv", ctypes.c_bool),
        ("no_perf", ctypes.c_bool),
        ("op_offload", ctypes.c_bool),
        ("swa_full", ctypes.c_bool),
        ("kv_unified", ctypes.c_bool),
        ("samplers", ctypes.POINTER(ctypes.c_void_p)),
        ("n_samplers", ctypes.c_size_t),
    ]


class llama_sampler_chain_params(ctypes.Structure):
    _fields_ = [("no_perf", ctypes.c_bool)]


class llama_logit_bias(ctypes.Structure):
    _fields_ = [
        ("token", llama_token),
        ("bias", ctypes.c_float),
    ]


class llama_batch(ctypes.Structure):
    _fields_ = [
        ("n_tokens", ctypes.c_int32),
        ("token", ctypes.POINTER(llama_token)),
        ("embd", ctypes.POINTER(ctypes.c_float)),
        ("pos", ctypes.POINTER(llama_pos)),
        ("n_seq_id", ctypes.POINTER(ctypes.c_int32)),
        ("seq_id", ctypes.POINTER(ctypes.POINTER(llama_seq_id))),
        ("logits", ctypes.POINTER(ctypes.c_int8)),
    ]


# =========================================================================
# Library Binding
# =========================================================================

_llama_lib = None
_ggml_lib = None
_wrap_lib = None
_log_cb = None

_fn = {}


def _ensure_system_libstdcxx():
    """Re-exec with LD_PRELOAD to override conda's outdated libstdc++.
    
    conda's libstdc++.so.6 only has GLIBCXX up to 3.4.26, but libggml-cuda.so
    needs GLIBCXX_3.4.30+. Since the interpreter already loaded conda's version,
    the only way to override is LD_PRELOAD before process start.
    """
    if sys.platform != "linux":
        return
    target = "/usr/lib/x86_64-linux-gnu/libstdc++.so.6"
    if not Path(target).exists():
        return
    if target in os.environ.get("LD_PRELOAD", ""):
        return
    os.environ["LD_PRELOAD"] = f"{target}:{os.environ.get('LD_PRELOAD', '')}".rstrip(":")
    os.execv(sys.executable, [sys.executable] + sys.argv)


_ensure_system_libstdcxx()


def _bind_libs():
    global _llama_lib, _ggml_lib, _wrap_lib

    if _llama_lib is not None:
        return

    lib_dir = Path(__file__).parent / "bin"

    if sys.platform == "win32":
        _ggml_lib = ctypes.CDLL(str(lib_dir / "ggml.dll"))
        _llama_lib = ctypes.CDLL(str(lib_dir / "llama.dll"))
    elif sys.platform == "darwin":
        _ggml_lib = ctypes.CDLL(str(lib_dir / "libggml.dylib"))
        _llama_lib = ctypes.CDLL(str(lib_dir / "libllama.dylib"))
    else:
        _ggml_lib = ctypes.CDLL(str(lib_dir / "libggml.so"))
        _llama_lib = ctypes.CDLL(str(lib_dir / "libllama.so"))

    ggml_backend_load_all = _ggml_lib.ggml_backend_load_all
    ggml_backend_load_all.argtypes = []
    ggml_backend_load_all.restype = None
    ggml_backend_load_all()

    L = _llama_lib

    _fn["backend_init"] = L.llama_backend_init
    _fn["backend_init"].argtypes = []
    _fn["backend_init"].restype = None
    _fn["backend_init"]()

    _fn["backend_free"] = L.llama_backend_free
    _fn["backend_free"].argtypes = []
    _fn["backend_free"].restype = None

    _fn["log_set"] = L.llama_log_set

    _fn["model_free"] = L.llama_model_free
    _fn["model_free"].argtypes = [ctypes.c_void_p]
    _fn["model_free"].restype = None

    _fn["model_get_vocab"] = L.llama_model_get_vocab
    _fn["model_get_vocab"].argtypes = [ctypes.c_void_p]
    _fn["model_get_vocab"].restype = ctypes.c_void_p

    _fn["model_n_embd"] = L.llama_model_n_embd
    _fn["model_n_embd"].argtypes = [ctypes.c_void_p]
    _fn["model_n_embd"].restype = ctypes.c_int32

    _fn["free"] = L.llama_free
    _fn["free"].argtypes = [ctypes.c_void_p]
    _fn["free"].restype = None

    _fn["batch_init"] = L.llama_batch_init
    _fn["batch_init"].argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    _fn["batch_init"].restype = llama_batch

    _fn["get_logits"] = L.llama_get_logits
    _fn["get_logits"].argtypes = [ctypes.c_void_p]
    _fn["get_logits"].restype = ctypes.POINTER(ctypes.c_float)

    _fn["get_logits_ith"] = L.llama_get_logits_ith
    _fn["get_logits_ith"].argtypes = [ctypes.c_void_p, ctypes.c_int32]
    _fn["get_logits_ith"].restype = ctypes.POINTER(ctypes.c_float)

    _fn["tokenize"] = L.llama_tokenize
    _fn["tokenize"].argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int32,
        ctypes.POINTER(llama_token), ctypes.c_int32,
        ctypes.c_bool, ctypes.c_bool,
    ]
    _fn["tokenize"].restype = ctypes.c_int32

    _fn["vocab_n_tokens"] = L.llama_vocab_n_tokens
    _fn["vocab_n_tokens"].argtypes = [ctypes.c_void_p]
    _fn["vocab_n_tokens"].restype = ctypes.c_int32

    _fn["vocab_eos"] = L.llama_vocab_eos
    _fn["vocab_eos"].argtypes = [ctypes.c_void_p]
    _fn["vocab_eos"].restype = llama_token

    _fn["vocab_bos"] = L.llama_vocab_bos
    _fn["vocab_bos"].argtypes = [ctypes.c_void_p]
    _fn["vocab_bos"].restype = llama_token

    _fn["token_to_piece"] = L.llama_token_to_piece
    _fn["token_to_piece"].argtypes = [ctypes.c_void_p, llama_token, ctypes.c_char_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_bool]
    _fn["token_to_piece"].restype = ctypes.c_int

    _fn["get_memory"] = L.llama_get_memory
    _fn["get_memory"].argtypes = [ctypes.c_void_p]
    _fn["get_memory"].restype = ctypes.c_void_p

    _fn["memory_clear"] = L.llama_memory_clear
    _fn["memory_clear"].argtypes = [ctypes.c_void_p, ctypes.c_bool]
    _fn["memory_clear"].restype = None

    # Sampler functions (all use primitive/pointer args, safe for ctypes)
    _fn["sampler_chain_default_params"] = L.llama_sampler_chain_default_params
    _fn["sampler_chain_default_params"].argtypes = []
    _fn["sampler_chain_default_params"].restype = llama_sampler_chain_params

    _fn["sampler_chain_init"] = L.llama_sampler_chain_init
    _fn["sampler_chain_init"].argtypes = [llama_sampler_chain_params]
    _fn["sampler_chain_init"].restype = ctypes.c_void_p

    _fn["sampler_chain_add"] = L.llama_sampler_chain_add
    _fn["sampler_chain_add"].argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _fn["sampler_chain_add"].restype = None

    _fn["sampler_init_temp"] = L.llama_sampler_init_temp
    _fn["sampler_init_temp"].argtypes = [ctypes.c_float]
    _fn["sampler_init_temp"].restype = ctypes.c_void_p

    _fn["sampler_init_top_k"] = L.llama_sampler_init_top_k
    _fn["sampler_init_top_k"].argtypes = [ctypes.c_int32]
    _fn["sampler_init_top_k"].restype = ctypes.c_void_p

    _fn["sampler_init_top_p"] = L.llama_sampler_init_top_p
    _fn["sampler_init_top_p"].argtypes = [ctypes.c_float, ctypes.c_size_t]
    _fn["sampler_init_top_p"].restype = ctypes.c_void_p

    _fn["sampler_init_dist"] = L.llama_sampler_init_dist
    _fn["sampler_init_dist"].argtypes = [ctypes.c_uint32]
    _fn["sampler_init_dist"].restype = ctypes.c_void_p

    _fn["sampler_init_greedy"] = L.llama_sampler_init_greedy
    _fn["sampler_init_greedy"].argtypes = []
    _fn["sampler_init_greedy"].restype = ctypes.c_void_p

    _fn["sampler_init_penalties"] = L.llama_sampler_init_penalties
    _fn["sampler_init_penalties"].argtypes = [ctypes.c_int32, ctypes.c_float, ctypes.c_float, ctypes.c_float]
    _fn["sampler_init_penalties"].restype = ctypes.c_void_p

    _fn["sampler_sample"] = L.llama_sampler_sample
    _fn["sampler_sample"].argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32]
    _fn["sampler_sample"].restype = llama_token

    _fn["sampler_free"] = L.llama_sampler_free
    _fn["sampler_free"].argtypes = [ctypes.c_void_p]
    _fn["sampler_free"].restype = None

    _fn["sampler_accept"] = L.llama_sampler_accept
    _fn["sampler_accept"].argtypes = [ctypes.c_void_p, llama_token]
    _fn["sampler_accept"].restype = None

    # Load C wrapper for struct-by-value functions (ctypes can't pass >16-byte structs)
    if (lib_dir / "libllama_wrap.so").exists():
        _wrap_lib = ctypes.CDLL(str(lib_dir / "libllama_wrap.so"))
        _fn["model_load"] = _wrap_lib.wrap_model_load
        _fn["model_load"].argtypes = [ctypes.c_char_p, ctypes.c_int32, ctypes.c_int32]
        _fn["model_load"].restype = ctypes.c_void_p
        _fn["context_init"] = _wrap_lib.wrap_context_init
        _fn["context_init"].argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_uint32, ctypes.c_int32, ctypes.c_int32,
            ctypes.c_int32, ctypes.c_int32,
            ctypes.c_int32, ctypes.c_int32,
        ]
        _fn["context_init"].restype = ctypes.c_void_p
        _fn["decode"] = _wrap_lib.wrap_decode
        _fn["decode"].argtypes = [ctypes.c_void_p, ctypes.POINTER(llama_batch)]
        _fn["decode"].restype = ctypes.c_int32
        _fn["batch_free"] = _wrap_lib.wrap_batch_free
        _fn["batch_free"].argtypes = [ctypes.POINTER(llama_batch)]
        _fn["batch_free"].restype = None
    else:
        # Fallback: direct ctypes (may crash on some builds)
        _fn["model_load"] = L.llama_model_load_from_file
        _fn["model_load"].argtypes = [ctypes.c_char_p, llama_model_params]
        _fn["model_load"].restype = ctypes.c_void_p
        _fn["context_init"] = L.llama_init_from_model
        _fn["context_init"].argtypes = [ctypes.c_void_p, llama_context_params]
        _fn["context_init"].restype = ctypes.c_void_p
        _fn["decode"] = L.llama_decode
        _fn["decode"].argtypes = [ctypes.c_void_p, llama_batch]
        _fn["decode"].restype = ctypes.c_int32
        _fn["batch_free"] = L.llama_batch_free
        _fn["batch_free"].argtypes = [llama_batch]
        _fn["batch_free"].restype = None

    # Suppress llama.cpp info logs (keep ref to prevent GC of callback)
    global _log_cb
    _LOG_CB_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)
    _log_cb = _LOG_CB_TYPE(lambda l, m, u: None)
    _fn["log_set"](_log_cb, None)


# =========================================================================
# High-Level API
# =========================================================================

def text_to_tokens(vocab, text, add_special=False, parse_special=True):
    text_bytes = text.encode("utf-8")
    n_max = len(text_bytes) + 32
    tokens = (llama_token * n_max)()
    n = _fn["tokenize"](vocab, text_bytes, len(text_bytes), tokens, n_max, add_special, parse_special)
    return [tokens[i] for i in range(n)] if n >= 0 else []


def token_to_piece(vocab, token_id):
    """Return raw bytes for a single token. Callers must collect bytes and
    decode the concatenated result as UTF-8, because multi-byte characters
    (e.g. CJK) may span multiple tokens."""
    buf = ctypes.create_string_buffer(256)
    n = _fn["token_to_piece"](vocab, token_id, buf, ctypes.sizeof(buf), 0, True)
    return buf.raw[:n] if n > 0 else b""


class LlamaModel:
    def __init__(self, path, n_gpu_layers=99, use_mmap=True):
        _bind_libs()
        self.ptr = _fn["model_load"](Path(path).as_posix().encode("utf-8"), n_gpu_layers, use_mmap)
        if not self.ptr:
            raise RuntimeError(f"Failed to load model: {path}")
        self.vocab = _fn["model_get_vocab"](self.ptr)
        self.n_embd = _fn["model_n_embd"](self.ptr)
        self.eos_token = _fn["vocab_eos"](self.vocab)
        self.bos_token = _fn["vocab_bos"](self.vocab)
        self.n_vocab = _fn["vocab_n_tokens"](self.vocab)

    def tokenize(self, text, add_special=False, parse_special=True):
        return text_to_tokens(self.vocab, text, add_special, parse_special)

    def detokenize(self, token_id):
        return token_to_piece(self.vocab, token_id)

    def __del__(self):
        if hasattr(self, "ptr") and self.ptr:
            _fn["model_free"](self.ptr)
            self.ptr = None


class LlamaContext:
    def __init__(self, model, n_ctx=4096, n_batch=512, n_ubatch=512, flash_attn=True, cache_type_k=0, cache_type_v=0):
        cpu_count = os.cpu_count() or 4
        self.model = model
        self.ptr = _fn["context_init"](
            model.ptr,
            n_ctx, n_batch, n_ubatch, 1,
            1 if flash_attn else 0, 0,
            cpu_count // 2, cpu_count,
            cache_type_k, cache_type_v,
        )
        if not self.ptr:
            raise RuntimeError("Failed to create context")

    def decode(self, batch):
        s = batch.struct if hasattr(batch, "struct") else batch
        return _fn["decode"](self.ptr, ctypes.byref(s))

    def decode_token(self, token_id, pos=0):
        batch = _fn["batch_init"](1, 0, 1)
        batch.n_tokens = 1
        batch.token[0] = token_id
        batch.pos[0] = pos
        batch.n_seq_id[0] = 1
        batch.seq_id[0][0] = 0
        batch.logits[0] = 1
        ret = _fn["decode"](self.ptr, ctypes.byref(batch))
        _fn["batch_free"](ctypes.byref(batch))
        return ret

    def get_logits(self):
        return _fn["get_logits"](self.ptr)

    def clear_kv(self):
        mem = _fn["get_memory"](self.ptr)
        _fn["memory_clear"](mem, True)

    def __del__(self):
        if hasattr(self, "ptr") and self.ptr:
            _fn["free"](self.ptr)
            self.ptr = None


class LlamaBatch:
    def __init__(self, n_tokens, embd_dim=0, n_seq_max=1):
        _bind_libs()
        self.struct = _fn["batch_init"](n_tokens, embd_dim, n_seq_max)
        self.n_tokens_max = n_tokens

    @property
    def n_tokens(self): return self.struct.n_tokens
    @n_tokens.setter
    def n_tokens(self, val): self.struct.n_tokens = val

    @property
    def token(self): return self.struct.token
    @property
    def embd(self): return self.struct.embd
    @property
    def pos(self): return self.struct.pos
    @property
    def n_seq_id(self): return self.struct.n_seq_id
    @property
    def seq_id(self): return self.struct.seq_id
    @property
    def logits(self): return self.struct.logits

    def set_embd(self, data, pos_offset=0, seq_id=0):
        """Inject embedding data [n_tokens, dim] into batch.
        
        data: numpy float32 array [n_tokens, dim]
        pos_offset: starting position index
        """
        import numpy as np
        n_tokens = data.shape[0]
        if n_tokens > self.n_tokens_max:
            raise ValueError(f"Batch overflow: {n_tokens} > {self.n_tokens_max}")

        if not data.flags["C_CONTIGUOUS"]:
            data = np.ascontiguousarray(data)
        ctypes.memmove(self.embd, data.ctypes.data, data.nbytes)

        for i in range(n_tokens):
            self.pos[i] = pos_offset + i
            self.n_seq_id[i] = 1
            self.seq_id[i][0] = seq_id
            self.logits[i] = 1 if i == n_tokens - 1 else 0
        self.n_tokens = n_tokens
        return self

    def set_tokens(self, token_ids, pos_offset=0, seq_id=0):
        """Set token IDs (no embeddings, uses embedding table lookup)."""
        n_tokens = len(token_ids)
        if n_tokens > self.n_tokens_max:
            raise ValueError(f"Batch overflow: {n_tokens} > {self.n_tokens_max}")

        for i, tid in enumerate(token_ids):
            self.token[i] = tid
            self.pos[i] = pos_offset + i
            self.n_seq_id[i] = 1
            self.seq_id[i][0] = seq_id
            self.logits[i] = 1 if i == n_tokens - 1 else 0
        self.n_tokens = n_tokens
        return self

    def __del__(self):
        if hasattr(self, "struct"):
            _fn["batch_free"](ctypes.byref(self.struct))


class LlamaSampler:
    def __init__(self, temperature=0.7, top_k=40, top_p=0.9, seed=None,
                 repeat_penalty=1.0, repeat_last_n=64):
        _bind_libs()
        if seed is None:
            seed = int(time.time())
        sparams = _fn["sampler_chain_default_params"]()
        self.ptr = _fn["sampler_chain_init"](sparams)

        if repeat_penalty > 1.0:
            _fn["sampler_chain_add"](self.ptr, _fn["sampler_init_penalties"](repeat_last_n, repeat_penalty, 0.0, 0.0))

        if temperature > 0:
            if top_k > 0:
                _fn["sampler_chain_add"](self.ptr, _fn["sampler_init_top_k"](top_k))
            if top_p < 1.0:
                _fn["sampler_chain_add"](self.ptr, _fn["sampler_init_top_p"](top_p, 1))
            _fn["sampler_chain_add"](self.ptr, _fn["sampler_init_temp"](temperature))
            _fn["sampler_chain_add"](self.ptr, _fn["sampler_init_dist"](seed))
        else:
            _fn["sampler_chain_add"](self.ptr, _fn["sampler_init_greedy"]())

    def sample(self, ctx, idx=-1):
        ctx_ptr = ctx.ptr if hasattr(ctx, "ptr") else ctx
        return _fn["sampler_sample"](self.ptr, ctx_ptr, idx)

    def accept(self, token_id):
        _fn["sampler_accept"](self.ptr, token_id)

    def free(self):
        if hasattr(self, "ptr") and self.ptr:
            _fn["sampler_free"](self.ptr)
            self.ptr = None

    def __del__(self):
        self.free()
