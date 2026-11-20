"""Membuat model ONNX sintetis kecil bergaya U2-Net tanpa paket onnx (protobuf dikodekan manual).

Model ini hanya menguji alur aplikasi. Ia bukan model AI: keluarannya hanya fungsi kecerahan piksel.
"""

from __future__ import annotations

import struct
from pathlib import Path


def _varint(value: int) -> bytes:
    out = bytearray()
    value &= (1 << 64) - 1
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _key(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def _f_varint(field: int, value: int) -> bytes:
    return _key(field, 0) + _varint(value)


def _f_bytes(field: int, data: bytes) -> bytes:
    return _key(field, 2) + _varint(len(data)) + data


def _f_str(field: int, text: str) -> bytes:
    return _f_bytes(field, text.encode("utf-8"))


def _value_info(name: str, dims: list[int]) -> bytes:
    shape = b"".join(_f_bytes(1, _f_varint(1, d)) for d in dims)
    tensor_type = _f_varint(1, 1) + _f_bytes(2, shape)  # elem_type FLOAT, shape
    return _f_str(1, name) + _f_bytes(2, _f_bytes(1, tensor_type))


def _scalar(name: str, value: float) -> bytes:
    return _f_varint(2, 1) + _f_str(8, name) + _f_bytes(9, struct.pack("<f", value))


def _node(op: str, inputs: list[str], outputs: list[str], attrs: bytes = b"") -> bytes:
    data = b"".join(_f_str(1, i) for i in inputs) + b"".join(_f_str(2, o) for o in outputs)
    return data + _f_str(4, op) + attrs


def _attr_ints(name: str, values: list[int]) -> bytes:
    body = _f_str(1, name) + _f_varint(20, 7) + b"".join(_f_varint(8, v) for v in values)
    return _f_bytes(5, body)


def _attr_int(name: str, value: int) -> bytes:
    return _f_bytes(5, _f_str(1, name) + _f_varint(20, 2) + _f_varint(3, value))


def build_saliency_model(
    path: Path,
    size: int = 320,
    outputs: int = 2,
    scale: float = 3.0,
    bias: float = -1.0,
    rank: int = 4,
    dynamic: bool = False,
) -> Path:
    """Model: sigmoid(scale * rata-rata kanal + bias). Objek terang menjadi foreground."""
    nodes = [
        _f_bytes(1, _node("ReduceMean", ["input.1"], ["m"], _attr_ints("axes", [1]) + _attr_int("keepdims", 1))),
        _f_bytes(1, _node("Mul", ["m", "scale"], ["ms"])),
        _f_bytes(1, _node("Add", ["ms", "bias"], ["mb"])),
        _f_bytes(1, _node("Sigmoid", ["mb"], ["d0"])),
    ]
    out_names = ["d0"]
    for i in range(1, outputs):
        nodes.append(_f_bytes(1, _node("Identity", ["d0"], [f"d{i}"])))
        out_names.append(f"d{i}")

    in_dims = [1, 3, size, size] if rank == 4 else [3, size, size]
    out_dims = [1, 1, size, size]
    graph = b"".join(nodes) + _f_str(2, "fake_u2net")
    graph += _f_bytes(5, _scalar("scale", scale)) + _f_bytes(5, _scalar("bias", bias))
    graph += _f_bytes(11, _value_info("input.1", in_dims))
    for name in out_names:
        graph += _f_bytes(12, _value_info(name, out_dims))

    model = _f_varint(1, 8) + _f_str(2, "creator-toolkit-tests")
    model += _f_bytes(7, graph) + _f_bytes(8, _f_varint(2, 13))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(model)
    return path
