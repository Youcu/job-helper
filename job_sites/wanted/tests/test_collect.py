"""목록 페이지네이션과 상세 수집."""
from __future__ import annotations

import tempfile
from pathlib import Path

from lib.collect import MAX_OFFSET, build_listing_params, fetch_details, fetch_listings
from tests.helpers import FIXTURES, FakeClient, assert_raises, page


def test_BOUNDARY_multi_value_params_repeat_the_key():
    """API 는 dict 가 아니라 같은 키의 반복으로 OR 를 받는다."""
    params = build_listing_params(job_group_id=518, job_ids=[872, 873],
                               location_slugs=["seoul.all", "gyeonggi.yongin-si"],
                               employment_type_keys=["job.employment_type.regular"], yoe=0)
    assert [v for k, v in params if k == "job_ids"] == ["872", "873"]
    assert [v for k, v in params if k == "locations"] == ["seoul.all", "gyeonggi.yongin-si"]


def test_BOUNDARY_pagination_exactly_full_last_page():
    """실측: 전체가 페이지 크기의 배수여도 서버가 next=null 을 준다.

    (전체 49건에 limit=49 → 49건 + next 없음, limit=7&offset=42 → 7건 + next 없음)
    그래서 limit 을 동적으로 줄일 필요가 없다.
    """
    client = FakeClient(lambda o: page(range(0, 5), False) if o == 0 else page([], False))
    rows, reason = fetch_listings(client, [("job_group_id", "518")], group_label="t", page_size=5)
    assert len(rows) == 5 and client.calls == [0] and "links.next 없음" in reason


def test_BOUNDARY_pagination_offset_ceiling():
    """끝나지 않는 응답에서 영원히 돌지 않는다."""
    counter = {"n": 0}

    def pages(offset):
        counter["n"] += 1
        return page(range(offset, offset + 100), True)   # 늘 새 id, 늘 next 있음

    rows, reason = fetch_listings(FakeClient(pages), [("job_group_id", "518")], group_label="t")
    assert "안전 상한" in reason
    assert counter["n"] == MAX_OFFSET // 100 + 1


def test_BOUNDARY_pagination_overlapping_pages_dedupe():
    """수집 중 공고가 추가되면 경계가 밀려 같은 공고가 두 페이지에 걸친다."""
    pages = {0: page([1, 2, 3], True), 3: page([3, 4, 5], True), 6: page([], False)}
    rows, _ = fetch_listings(FakeClient(lambda o: pages[o]), [("job_group_id", "518")],
                           group_label="t", page_size=3)
    assert sorted(rows) == [1, 2, 3, 4, 5]


def test_BOUNDARY_pagination_server_ignores_offset():
    """같은 페이지를 계속 주면 무한루프 대신 멈춘다."""
    client = FakeClient(lambda o: page([1, 2, 3], True))
    rows, reason = fetch_listings(client, [("job_group_id", "518")], group_label="t", page_size=3)
    assert len(rows) == 3 and "같은 페이지 반복" in reason and len(client.calls) == 2


def test_BOUNDARY_pagination_single_result():
    client = FakeClient(lambda o: page([7], False) if o == 0 else page([], False))
    rows, _ = fetch_listings(client, [("job_group_id", "518")], group_label="t")
    assert list(rows) == [7]


def test_BOUNDARY_pagination_total_smaller_than_page_size():
    """limit 은 '최대'다. 남은 게 적으면 남은 만큼만 온다."""
    client = FakeClient(lambda o: page([1, 2, 3], False) if o == 0 else page([], False))
    rows, reason = fetch_listings(client, [("job_group_id", "518")], group_label="t", page_size=100)
    assert len(rows) == 3 and client.calls == [0]


def test_BOUNDARY_pagination_zero_results():
    client = FakeClient(lambda o: page([], False))
    rows, reason = fetch_listings(client, [("job_group_id", "518")], group_label="t")
    assert rows == {} and "빈 응답" in reason and client.calls == [0]


def test_BOUNDARY_years_parameter_omitted_for_all():
    """YOE=-1(전체)이면 years 를 빼야 전체가 나온다. 넣으면 필터가 걸린다."""
    with_yoe = build_listing_params(job_group_id=518, job_ids=[], location_slugs=["all"],
                                 employment_type_keys=[], yoe=0)
    without = build_listing_params(job_group_id=518, job_ids=[], location_slugs=["all"],
                                employment_type_keys=[], yoe=-1)
    assert ("years", "0") in with_yoe
    assert not [k for k, _ in without if k == "years"]


def test_EXCEPTION_detail_failure_does_not_stop_the_run():
    """한 건이 실패해도 나머지는 가져와야 한다."""
    class C:
        def get_json(self, path, *, referer):
            job_id = int(path.split("/")[-2])
            if job_id == 2:
                raise RuntimeError("타임아웃")
            return {"job": {"id": job_id}}

    got = fetch_details(C(), [1, 2, 3], workers=2)
    assert sorted(got) == [1, 3]


def test_EXCEPTION_list_items_without_id_are_skipped():
    """id 없는 항목은 상세를 부를 수도, URL 을 만들 수도 없다."""
    def pages(offset):
        if offset == 0:
            return {"data": [{"id": 1}, {"no_id": True}, {"id": None}, {"id": 2}],
                    "links": {"next": None}}
        return page([], False)

    rows, _ = fetch_listings(FakeClient(pages), [("job_group_id", "518")], group_label="t")
    assert sorted(rows) == [1, 2]


def test_EXCEPTION_list_request_failure_keeps_what_was_collected():
    """결함이 될 뻔한 곳: 3페이지째에서 죽으면 앞 2페이지도 통째로 잃는다."""
    def pages(offset):
        if offset == 0:
            return page(range(0, 100), True)
        if offset == 100:
            return page(range(100, 200), True)
        return RuntimeError("서버가 끊었다")

    rows, reason = fetch_listings(FakeClient(pages), [("job_group_id", "518")], group_label="t")
    assert len(rows) == 200, "실패 직전까지 모은 것을 잃었다"
    assert "요청 실패" in reason and "RuntimeError" in reason


def test_EXCEPTION_malformed_list_response():
    """JSON 이 오긴 왔는데 모양이 다를 때 크래시 대신 이유를 남기고 멈춘다."""
    rows, reason = fetch_listings(FakeClient(lambda o: ["배열이 왔다"]),
                                [("job_group_id", "518")], group_label="t")
    assert rows == {} and "JSON 객체가 아님" in reason

    rows, reason = fetch_listings(FakeClient(lambda o: {"data": {"id": 1}, "links": {}}),
                                [("job_group_id", "518")], group_label="t")
    assert rows == {} and "목록이 아님" in reason


def test_EXCEPTION_many_detail_failures_are_summarized():
    """실패가 쏟아질 때 터미널을 수백 줄로 덮지 않는다."""
    class C:
        def get_json(self, path, *, referer):
            raise RuntimeError("전부 실패")

    assert fetch_details(C(), list(range(20)), workers=2) == {}


def test_NORMAL_details_collected_in_parallel():
    jobs = {int(k): v["job"] for k, v in FIXTURES.items()}

    class C:
        def get_json(self, path, *, referer):
            job_id = int(path.split("/")[-2])
            return {"job": jobs[job_id]}

    got = fetch_details(C(), sorted(jobs), workers=2)
    assert set(got) == set(jobs)


def test_NORMAL_pagination_walks_every_page():
    pages = {0: page(range(0, 100), True), 100: page(range(100, 122), False)}
    client = FakeClient(lambda o: pages[o])
    rows, reason = fetch_listings(client, [("job_group_id", "518")], group_label="t")
    assert len(rows) == 122
    assert client.calls == [0, 100]
    assert "links.next 없음" in reason
