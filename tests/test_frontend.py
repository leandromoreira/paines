from array import array

from paines.apu.apu import SAMPLE_RATE
from paines.frontend import (
    FRAME_SECONDS,
    MAX_BUFFER_SAMPLES,
    TARGET_BUFFER_SAMPLES,
    AudioBuffer,
    audio_target_length,
    resample,
)


def pcm(values: list[int]) -> bytes:
    return array("h", values).tobytes()


def values(data: bytes) -> list[int]:
    out = array("h")
    out.frombytes(data)
    return list(out)


def test_resample_returns_the_requested_length_and_keeps_the_endpoints() -> None:
    result = values(resample(pcm([0, 100, 200, 300]), 10))
    assert len(result) == 10
    assert result[0] == 0
    assert result[-1] == 300
    assert result == sorted(result)


def test_resample_to_the_same_length_is_a_no_op() -> None:
    data = pcm([1, 2, 3])
    assert resample(data, 3) == data


def test_resample_can_shrink() -> None:
    assert len(values(resample(pcm(list(range(100))), 40))) == 40


def test_target_length_matches_the_frame_period_at_the_desired_fill() -> None:
    length = audio_target_length(FRAME_SECONDS, TARGET_BUFFER_SAMPLES)
    assert length == round(FRAME_SECONDS * SAMPLE_RATE)


def test_target_length_grows_with_slower_frames() -> None:
    slow = audio_target_length(0.020, TARGET_BUFFER_SAMPLES)
    assert slow == round(0.020 * SAMPLE_RATE)


def test_target_length_nudges_the_buffer_towards_its_desired_fill() -> None:
    base = audio_target_length(FRAME_SECONDS, TARGET_BUFFER_SAMPLES)
    assert audio_target_length(FRAME_SECONDS, 0) > base
    assert audio_target_length(FRAME_SECONDS, 2 * TARGET_BUFFER_SAMPLES) < base


def test_buffer_is_silent_until_the_cushion_is_filled() -> None:
    buffer = AudioBuffer()
    buffer.push(pcm([5] * 100))
    assert buffer.pull(8) == bytes(8)
    buffer.push(pcm([5] * TARGET_BUFFER_SAMPLES))
    assert values(buffer.pull(8)) == [5, 5, 5, 5]


def test_buffer_holds_the_last_sample_on_underrun_and_rebuffers() -> None:
    buffer = AudioBuffer()
    buffer.push(pcm([7] * TARGET_BUFFER_SAMPLES))
    out = values(buffer.pull(2 * (TARGET_BUFFER_SAMPLES + 4)))
    assert out[:TARGET_BUFFER_SAMPLES] == [7] * TARGET_BUFFER_SAMPLES
    assert out[TARGET_BUFFER_SAMPLES:] == [7] * 4  # no click: the last value is held

    buffer.push(pcm([9] * 10))
    assert values(buffer.pull(4)) == [7, 7]  # still refilling


def test_buffer_drops_the_oldest_audio_when_full() -> None:
    buffer = AudioBuffer()
    buffer.push(pcm([1] * MAX_BUFFER_SAMPLES))
    buffer.push(pcm([2] * 100))
    assert buffer.samples == MAX_BUFFER_SAMPLES
    out = values(buffer.pull(2 * MAX_BUFFER_SAMPLES))
    assert out[-100:] == [2] * 100
