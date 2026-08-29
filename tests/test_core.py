from pipeline.core import notice_once, reset_notices


def test_notice_once_prints_once_per_key(capsys):
    reset_notices()
    first = notice_once("headless here", "headless", "/p", "planning")
    second = notice_once("headless here", "headless", "/p", "planning")
    assert first is True
    assert second is False
    assert capsys.readouterr().out == "headless here\n"


def test_notice_once_prints_again_for_another_project_or_stage(capsys):
    reset_notices()
    notice_once("a", "headless", "/p1", "planning")
    notice_once("b", "headless", "/p2", "planning")
    notice_once("c", "headless", "/p1", "review")
    assert capsys.readouterr().out == "a\nb\nc\n"


def test_reset_notices_clears_the_keys(capsys):
    reset_notices()
    notice_once("a", "k")
    reset_notices()
    third = notice_once("a", "k")
    assert third is True
    assert capsys.readouterr().out == "a\na\n"
