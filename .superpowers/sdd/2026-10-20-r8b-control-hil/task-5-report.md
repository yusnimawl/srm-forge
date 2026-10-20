# Task 5 report: PC protocol

Status: DONE.

## Implemented
- hil/common/hil_proto.h/.c: COBS, CRC-16/CCITT-FALSE (type, seq, payload; before COBS), hil_frame/hil_unframe, hil_payload_size, packed structs, HIL_FRAME_MAX, HIL_PAYLOAD_MAX 1024. C99, no malloc.
- src/srmsil/hil/__init__.py (HilError), proto.py (mirror: Type, ProtoError(code), cobs/crc/frame/unframe, Structs, pack/unpack helpers, dataclasses, SAMPLE_DTYPE).
- hil/common/proto_vectors.json: 17 vectors (empty payload, zero bytes, 254- and 257-byte payloads, one of each fixed-size type), generated once from Python.
- tests/hil/c/proto_shim.c, tests/hil/test_hil_proto.py.

## Choices
- hil_emu_config_t: 33 floats (units in header comments), 5 u32, 7 u8; Python EMU_CONFIG_FIELDS mirrors it.
- hil_payload_size is 0 for empty and variable types (HELLO, START, STOP, CAPTURE_REQ, CAPTURE_DATA, CAPTURE_END, ERROR).
- hil_unframe accepts the trailing 0x00 or not; decoded data under 5 bytes gives -1; -3 for payload above cap.
- hil_table_chunk_t is full size (807 bytes) with n valid entries.

## TDD
- RED: `pytest tests/hil/test_hil_proto.py` -> collection error, no module srmsil.hil.proto.
- GREEN after fixing two of my own bugs (LIVE_EMU struct format, CRC ctypes restype in the test): 12 passed; with the strict-compile test added, 13 passed.

## Self-review / concerns
- compile_host has no -Werror, hence test_proto_compiles_strict.
- Vectors check C and Python framing, unframe, cap rejection and sizes (incl. hil_sample_t 36).
