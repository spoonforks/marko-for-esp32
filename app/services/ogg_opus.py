from __future__ import annotations

import random
import struct
from pathlib import Path

import av


OPUS_GRANULE_RATE = 48_000


def _ogg_crc(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc


def _lacing_values(packet_size: int) -> list[int]:
    values: list[int] = []
    while packet_size >= 255:
        values.append(255)
        packet_size -= 255
    values.append(packet_size)
    return values


def _ogg_page(
    *,
    packet: bytes,
    serial: int,
    sequence: int,
    granule_position: int,
    flags: int,
) -> bytes:
    lacing = _lacing_values(len(packet))
    header = bytearray()
    header += b"OggS"
    header += bytes([0, flags])
    header += struct.pack("<Q", granule_position)
    header += struct.pack("<I", serial)
    header += struct.pack("<I", sequence)
    header += b"\x00\x00\x00\x00"
    header += bytes([len(lacing)])
    header += bytes(lacing)

    page = bytes(header) + packet
    header[22:26] = struct.pack("<I", _ogg_crc(page))
    return bytes(header) + packet


def write_ogg_opus(
    *,
    packets: list[bytes],
    output_path: Path,
    sample_rate: int,
    channels: int = 1,
    frame_duration_ms: int = 60,
) -> None:
    serial = random.getrandbits(32)
    sequence = 0
    pages: list[bytes] = []

    opus_head = (
        b"OpusHead"
        + bytes([1, channels])
        + struct.pack("<H", 312)
        + struct.pack("<I", sample_rate)
        + struct.pack("<h", 0)
        + bytes([0])
    )
    opus_tags = b"OpusTags" + struct.pack("<I", 5) + b"Marko" + struct.pack("<I", 0)

    pages.append(
        _ogg_page(
            packet=opus_head,
            serial=serial,
            sequence=sequence,
            granule_position=0,
            flags=0x02,
        )
    )
    sequence += 1
    pages.append(
        _ogg_page(
            packet=opus_tags,
            serial=serial,
            sequence=sequence,
            granule_position=0,
            flags=0,
        )
    )
    sequence += 1

    granule_step = OPUS_GRANULE_RATE * frame_duration_ms // 1000
    granule_position = 0
    for index, packet in enumerate(packets):
        granule_position += granule_step
        pages.append(
            _ogg_page(
                packet=packet,
                serial=serial,
                sequence=sequence,
                granule_position=granule_position,
                flags=0x04 if index == len(packets) - 1 else 0,
            )
        )
        sequence += 1

    output_path.write_bytes(b"".join(pages))


def wav_to_opus_packets(
    wav_path: Path,
    *,
    sample_rate: int = 16_000,
    frame_duration_ms: int = 60,
    bit_rate: int = 16_000,
) -> list[bytes]:
    temp_ogg = wav_path.with_suffix(".device.opus.ogg")
    input_container = av.open(str(wav_path))
    output_container = av.open(str(temp_ogg), "w", format="ogg")
    stream = output_container.add_stream(
        "libopus",
        rate=sample_rate,
        options={
            "application": "voip",
            "frame_duration": str(frame_duration_ms),
        },
    )
    stream.layout = "mono"
    stream.bit_rate = bit_rate
    resampler = av.audio.resampler.AudioResampler(
        format="s16",
        layout="mono",
        rate=sample_rate,
    )

    try:
        for frame in input_container.decode(audio=0):
            resampled_frames = resampler.resample(frame)
            if resampled_frames is None:
                continue
            if not isinstance(resampled_frames, list):
                resampled_frames = [resampled_frames]
            for resampled_frame in resampled_frames:
                for packet in stream.encode(resampled_frame):
                    output_container.mux(packet)

        for packet in stream.encode(None):
            output_container.mux(packet)
    finally:
        output_container.close()
        input_container.close()

    try:
        packet_container = av.open(str(temp_ogg))
        try:
            audio_stream = packet_container.streams.audio[0]
            return [
                packet_bytes
                for packet in packet_container.demux(audio_stream)
                if (packet_bytes := bytes(packet))
                and not packet_bytes.startswith(b"OpusHead")
                and not packet_bytes.startswith(b"OpusTags")
            ]
        finally:
            packet_container.close()
    finally:
        temp_ogg.unlink(missing_ok=True)
