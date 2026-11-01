from audiotour.master import chapters_metadata


def test_chapters_run_back_to_back_and_escape_titles():
    meta = chapters_metadata("Gate Pā", [("Chapter 1: One", 10.0), ("Workshop 1: A; B", 2.5)])
    assert meta.splitlines() == [
        ";FFMETADATA1", "title=Gate Pā",
        "[CHAPTER]", "TIMEBASE=1/1000", "START=0", "END=10000", "title=Chapter 1: One",
        "[CHAPTER]", "TIMEBASE=1/1000", "START=10000", "END=12500", "title=Workshop 1: A\; B",
    ]
