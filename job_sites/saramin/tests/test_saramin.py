"""`saramin.py` — 수집 흐름 전체.

여기가 **사용자가 정한 규칙이 지켜지는 자리**다.

1. **수집을 돌 때는 그림을 읽지 않는다.** 장당 40초라 389건이 몇 시간이 된다.
   본문이 이미지면 **주소만 기술스택 칸에 남기고** 넘어간다.
2. `ai_processed.csv` 는 **잘라내기가 아니라 복사다.** 나중에 그림을 읽는 단계가 쓴다.
3. **차단돼도 앞서 모은 것은 버리지 않는다.** 300번째에서 막혔다고 299건을 버리면
   다시 처음부터 받아야 하고, 그게 차단을 더 부른다.
4. **실패와 빈 결과를 섞지 않는다.**

네트워크를 안 탄다 — 가짜 클라이언트를 넣는다.
"""
from __future__ import annotations

import saramin
from tests.helpers import check, check_equal


def listing(rec_idx: str) -> dict:
    return {"rec_idx": rec_idx, "기업명": "회사", "근무지": "서울",
            "경력": "신입 · 정규직", "마감일": "~09.14(월)"}


def detail(inner: str, rec_idx: str = "1") -> str:
    return '<div class="user_content jobsViewDetail_%s">%s</div>' % (rec_idx, inner)


TEXT_BODY = detail("<p>자격요건</p><p>Java 와 Spring 으로 백엔드를 만듭니다. </p>"
                   "<p>" + "실제 공고는 이만큼 깁니다. " * 6 + "</p>")
IMAGE_BODY = detail('<img src="https://x.test/a.png">')
NO_SKILL_BODY = detail("<p>자격요건</p><p>" + "성실하고 책임감 있는 분을 찾습니다. " * 8 + "</p>")


class FakeClient:
    """rec_idx → 상세 HTML. `raises` 에 든 번호에서는 예외를 낸다."""

    def __init__(self, pages: dict, raises: dict | None = None):
        self.pages = pages
        self.raises = raises or {}
        self.asked: list[str] = []

    def get_html(self, path, params=None, referer=None):
        rec_idx = (params or {}).get("rec_idx")
        self.asked.append(rec_idx)
        if rec_idx in self.raises:
            raise self.raises[rec_idx]
        return self.pages.get(rec_idx, "")


def swap_image_reader(result):
    """이미지 판독을 정해진 결과로 바꿔 끼운다. `claude` 를 안 부른다."""
    original = saramin_skills.image_urls
    saramin_skills.image_urls = lambda page, **kwargs: result
    return original


def restore_image_reader(original):
    saramin_skills.image_urls = original


# ─────────────────────────────── 일반 ───────────────────────────────

def test_NORMAL_text_posting_becomes_a_row_without_ai():
    client = FakeClient({"1": TEXT_BODY})
    rows, ai_rows, stats = saramin._collect_details(client, [listing("1")])
    check_equal(len(rows), 1, "행 하나")
    check("Java" in rows[0]["기술스택"], "기술스택: %r" % rows[0]["기술스택"])
    check_equal(ai_rows, [], "글이 있는 공고는 AI 를 안 부른다")
    check_equal(stats["이미지본문"], 0, "이미지 본문이 아니다")





# ─────────────────────────────── 예외 ───────────────────────────────

def test_EXCEPTION_block_keeps_what_was_collected():
    # 결함이었던 곳: 300번째에서 막혔다고 앞의 299건을 버렸다.
    from lib.client import BlockedError

    client = FakeClient({"1": TEXT_BODY, "2": TEXT_BODY},
                        raises={"3": BlockedError("막힘")})
    rows, _, stats = saramin._collect_details(
        client, [listing("1"), listing("2"), listing("3"), listing("4")])
    check_equal(len(rows), 2, "막히기 전에 모은 것은 살아야 한다")
    check(stats["차단"], "막혔다는 사실이 남아야 한다")
    check_equal(client.asked, ["1", "2", "3"], "막힌 뒤로는 더 안 던진다")


def test_EXCEPTION_one_failed_detail_does_not_stop_the_rest():
    client = FakeClient({"1": TEXT_BODY, "3": TEXT_BODY},
                        raises={"2": ConnectionError("끊김")})
    rows, _, stats = saramin._collect_details(
        client, [listing("1"), listing("2"), listing("3")])
    check_equal(len(rows), 2, "한 건 실패로 나머지를 버리면 안 된다")
    check(not stats["차단"], "일시적 실패는 차단이 아니다")


def test_EXCEPTION_missing_rec_idx_is_counted_not_crashed():
    client = FakeClient({"1": TEXT_BODY})
    rows, _, stats = saramin._collect_details(client, [{"기업명": "회사"}, listing("1")])
    check_equal(len(rows), 1, "쓸 수 있는 것만 남긴다")
    check_equal(stats["번호없음"], 1, "몇 건을 뺐는지 알려야 한다")



# ─────────────────────────────── 경계 ───────────────────────────────

def test_BOUNDARY_posting_without_any_skill_is_dropped_and_counted():
    client = FakeClient({"1": NO_SKILL_BODY})
    rows, _, stats = saramin._collect_details(client, [listing("1")])
    check_equal(rows, [], "판단 재료가 없는 공고는 뺀다")
    check_equal(stats["기술없음"], 1, "뺀 개수를 알려야 한다")



def test_BOUNDARY_empty_listing_list_is_empty_result():
    rows, ai_rows, stats = saramin._collect_details(FakeClient({}), [])
    check_equal((rows, ai_rows), ([], []), "빈 입력")
    check(not stats["차단"], "막힌 것이 아니다")



def test_BOUNDARY_no_corpus_name_contains_a_comma():
    # 기술스택은 `", ".join` 으로 한 칸에 담고 콤마로 다시 쪼갠다.
    # 표준 이름에 콤마가 들어가면 **조용히 두 기술로 갈린다.**
    from _common import dictionaries

    offenders = [name for name in dictionaries.corpus_names() if "," in name]
    check_equal(offenders, [], "표준 이름에 콤마가 들어가면 안 된다")
    aliased = [name for name in dictionaries.aliases().values() if "," in name]
    check_equal(aliased, [], "별칭이 가리키는 이름도 마찬가지다")



# ────────────────────── 저장 · 누적 ──────────────────────

def _paths():
    import tempfile
    from pathlib import Path

    from _common.store import ai_csv_path
    base = Path(tempfile.mkdtemp())
    output = base / "saramin_post.csv"
    return output, ai_csv_path(output)


def store_save(rows, output, ai_rows=None):
    from _common.store import save
    return save(rows, output, ai_rows)


def _row(url: str, company: str = "회사", skills: str = "Java") -> dict:
    from _common.store import COLUMNS
    row = {column: "" for column in COLUMNS}
    row.update({"URL": url, "기업명": company, "기술스택": skills, "사이트명": "saramin"})
    return row


def test_NORMAL_ai_row_lands_in_both_files():
    from _common.store import read_csv

    output, ai_output = _paths()
    row = _row("https://x.test/1")
    store_save([row], output, [dict(row)])
    check_equal(len(read_csv(output)), 1, "본 CSV")
    check_equal(len(read_csv(ai_output)), 1, "AI 사본")
    check_equal(read_csv(output)[0]["URL"], read_csv(ai_output)[0]["URL"],
                "URL 로 맞춰 볼 수 있어야 한다")


def test_NORMAL_second_run_accumulates_instead_of_overwriting():
    from _common.store import read_csv

    output, ai_output = _paths()
    store_save([_row("https://x.test/1")], output)
    store_save([_row("https://x.test/2")], output)
    urls = {row["URL"] for row in read_csv(output)}
    check_equal(urls, {"https://x.test/1", "https://x.test/2"}, "덮어쓰지 않고 쌓는다")


def test_EXCEPTION_no_ai_rows_leaves_no_ai_file():
    output, ai_output = _paths()
    store_save([_row("https://x.test/1")], output)
    check(not ai_output.exists(), "AI 가 관여한 게 없으면 빈 파일도 안 만든다")


def test_BOUNDARY_same_posting_twice_stays_one_row():
    from _common.store import read_csv

    output, ai_output = _paths()
    row = _row("https://x.test/1")
    store_save([row], output, [dict(row)])
    store_save([row], output, [dict(row)])
    check_equal(len(read_csv(output)), 1, "같은 URL 은 한 행")
    check_equal(len(read_csv(ai_output)), 1, "사본도 한 행")


def test_BOUNDARY_ai_file_keeps_a_row_the_main_file_no_longer_gets():
    # 다음 실행에서 그 공고가 글로 바뀌면 AI 사본에는 안 들어온다.
    # 그래도 **이전에 AI 가 관여했다는 기록은 남아야** 나중에 되짚을 수 있다.
    from _common.store import read_csv

    output, ai_output = _paths()
    row = _row("https://x.test/1")
    store_save([row], output, [dict(row)])
    store_save([row], output)
    check_equal(len(read_csv(ai_output)), 1, "기록은 남는다")


# ────────────────────── 보고 · 실행 잠금 ──────────────────────

def _config(**kwargs):
    from lib.config import Config
    return Config(**{"job_ids": [84], "yoe": 0, "home_locations": ["서울"], **kwargs})


def _stats(**kwargs):
    base = {"이미지본문": 0, "그림대기": 0, "기술없음": 0, "번호없음": 0, "차단": False}
    base.update(kwargs)
    return base


def _merge_result(rows):
    from _common.store import merge, read_csv
    import tempfile
    from pathlib import Path
    return merge(read_csv(Path(tempfile.mkdtemp()) / "none.csv"), rows)


def test_NORMAL_conditions_are_printed_before_collecting():
    # 무슨 조건으로 긁는지 안 보이면, 엉뚱한 걸 긁고도 한참 뒤에 안다.
    from lib import filters
    config = _config(job_ids=[84, 87], home_locations=["서울", "강남구"])
    saramin._print_conditions(config, filters.build_search_params(config))


def test_NORMAL_summary_prints_without_crashing():
    saramin._print_summary(_config(), _merge_result([_row("https://x.test/1")]),
                           [], _stats())


def test_EXCEPTION_summary_handles_every_stat_being_set():
    # 숫자가 0 일 때만 돌아가는 보고문은 정작 문제가 났을 때 터진다.
    saramin._print_summary(
        _config(tech_stacks=["Python"], hope_annual_salary="3300"),
        _merge_result([_row("https://x.test/1")]),
        [_row("https://x.test/1")],
        _stats(이미지본문=5, 그림대기=5, 기술없음=3, 번호없음=1, 차단=True))


def test_EXCEPTION_second_run_is_refused_while_one_is_running():
    # 파이프라인은 주기로 돈다. 겹쳐 돌면 두 실행이 같은 CSV 를 읽고-고치고-써서
    # 한쪽 결과가 조용히 사라진다.
    import tempfile
    from pathlib import Path

    from _common.runlock import LockedError, run_lock

    lock = Path(tempfile.mkdtemp()) / ".saramin.lock"
    with run_lock(lock):
        try:
            with run_lock(lock):
                raise AssertionError("겹쳐 도는 실행을 막지 못했다")
        except LockedError as error:
            check(str(error), "왜 막혔는지 알려야 한다")


def test_BOUNDARY_summary_with_no_rows_does_not_crash():
    saramin._print_summary(_config(), _merge_result([]), [], _stats())


# ────────────────────── 종료 코드 ──────────────────────
#
# 오케스트레이터가 읽는 값이다. 다 섞어서 0 을 주면 실패한 실행을 성공으로 기록한다.
#
#   0  정상        1  설정 오류        2  차단        3  이미 돌고 있음

def _run_with(monkey: dict):
    """`saramin` 모듈의 이름을 잠깐 바꿔 끼우고 `_run()` 을 부른다."""
    original = {name: getattr(saramin, name) for name in monkey}
    for name, value in monkey.items():
        setattr(saramin, name, value)
    try:
        return saramin._run()
    finally:
        for name, value in original.items():
            setattr(saramin, name, value)


def test_NORMAL_successful_run_returns_zero():
    listings = saramin.fetch_listings.__globals__["Listings"](
        rows=[listing("1")], pages=1, reported_total=1, stop_reason="다 모았다")
    code = _run_with({
        "load_config": lambda: _config(),
        "SaraminClient": lambda: FakeClient({"1": TEXT_BODY}),
        "fetch_listings": lambda client, params, **kwargs: listings,
        "fetch_detail": lambda client, rec_idx: TEXT_BODY,
        "save": lambda rows, output, ai_rows=None: _merge_result(rows),
    })
    check_equal(code, 0, "정상 종료")


def test_EXCEPTION_config_error_returns_one():
    from _common.env import ConfigError

    def boom():
        raise ConfigError("JOB_ROLES 가 비어 있습니다")

    check_equal(_run_with({"load_config": boom}), 1, "설정 오류는 1")


def test_EXCEPTION_unknown_location_returns_one():
    check_equal(_run_with({"load_config": lambda: _config(home_locations=["없는동네"])}),
                1, "근무지를 못 옮기면 1 — 조용히 전국을 긁지 않는다")


def test_EXCEPTION_block_returns_two_but_still_saves():
    from lib.client import BlockedError

    saved = []
    listings = saramin.fetch_listings.__globals__["Listings"](
        rows=[listing("1"), listing("2")], pages=1, reported_total=2, stop_reason="")

    def blocked_detail(client, rec_idx):
        if rec_idx == "2":
            raise BlockedError("막힘")
        return TEXT_BODY

    code = _run_with({
        "load_config": lambda: _config(),
        "SaraminClient": lambda: FakeClient({}),
        "fetch_listings": lambda client, params, **kwargs: listings,
        "fetch_detail": blocked_detail,
        "save": lambda rows, output, ai_rows=None: saved.append(rows) or _merge_result(rows),
    })
    check_equal(code, 2, "차단은 2")
    check_equal(len(saved[0]), 1, "막히기 전에 모은 것은 저장해야 한다")


def test_BOUNDARY_no_matching_posting_is_zero_not_an_error():
    listings = saramin.fetch_listings.__globals__["Listings"](
        rows=[], pages=1, reported_total=0, stop_reason="비었다")
    code = _run_with({
        "load_config": lambda: _config(),
        "SaraminClient": lambda: FakeClient({}),
        "fetch_listings": lambda client, params, **kwargs: listings,
    })
    check_equal(code, 0, "조건에 맞는 공고가 없는 것은 실패가 아니다")


# ────────────────────── 판독 예산 ──────────────────────
#
# 파이프라인은 주기로 돈다. 첫 실행이 몇 시간 걸리면 못 쓴다 —
# 실측 장당 40초라 389건 중 이미지 70건이면 판독만 50분이다.
# 못 읽은 것은 **버리지 않고 다음 실행으로 미룬다.** 캐시가 남아 이어진다.




def test_NORMAL_location_codes_print_as_one_string_not_characters():
    # 결함: 값이 콤마로 이은 **문자열**인데 그냥 순회해서 `1, 0, 1, 0, 0, 0` 로 찍혔다.
    from lib import filters
    config = _config(home_locations=["서울", "성남시"])
    saramin._print_conditions(config, filters.build_search_params(config))




# ────────────────── 이미지는 주소만 남긴다 ──────────────────
#
# 수집을 돌 때 그림을 읽으면 장당 40초라 389건이 몇 시간이 된다. 전량을 먼저 걷고
# 그림은 따로 한 번에 읽는다. 그래서 수집 단계는 **순수 HTTP** 만 한다.

def test_NORMAL_image_body_leaves_urls_in_the_skill_column():
    client = FakeClient({"1": IMAGE_BODY})
    rows, ai_rows, stats = saramin._collect_details(client, [listing("1")])
    check_equal(len(rows), 1, "그림 공고도 행으로 남긴다")
    check("https://x.test/a.png" in rows[0]["기술스택"],
          "그림 주소를 남겨야 나중에 읽을 대상을 안다: %r" % rows[0]["기술스택"])
    check_equal(stats["그림대기"], 1, "몇 건이 기다리는지 알려야 한다")
    check_equal(ai_rows, [], "이 단계에서는 AI 가 관여하지 않는다")


def test_NORMAL_collection_makes_no_external_call():
    # 수집 단계는 **순수 HTTP** 다. 그림을 읽는 코드가 여기 있으면 안 된다 —
    # 실제로 그것 때문에 첫 실행이 4시간이었다.
    import lib.skills as site_skills
    forbidden = [n for n in dir(site_skills)
                 if n.startswith(("extract_from_images", "_ask_", "_download"))]
    check_equal(forbidden, [], "판독 코드가 수집 계층에 남아 있다: %r" % forbidden)
    client = FakeClient({"1": IMAGE_BODY})
    rows, ai_rows, _ = saramin._collect_details(client, [listing("1")])
    check_equal(ai_rows, [], "이 단계에서는 AI 가 관여하지 않는다")
    check(rows[0]["기술스택"].startswith("http"), "주소만 남는다")


def test_BOUNDARY_urls_are_distinguishable_from_skill_names():
    # 한 칸에 섞여 들어가지만 `http` 로 시작해 구분된다. 나중 단계가 이걸로 고른다.
    body_with_tag = (IMAGE_BODY
                     + '<a href="/zf_user/jobs/list/job-category?cat_kewd=235">#Java</a>')
    client = FakeClient({"1": body_with_tag})
    rows, _, _ = saramin._collect_details(client, [listing("1")])
    parts = [p.strip() for p in rows[0]["기술스택"].split(",")]
    urls = [p for p in parts if p.startswith("http")]
    names = [p for p in parts if not p.startswith("http")]
    check_equal(names, ["Java"], "구조화 태그로 얻은 기술은 그대로 남는다")
    check_equal(len(urls), 1, "그림 주소도 함께 남는다")


def test_BOUNDARY_image_body_is_no_longer_dropped_for_having_no_skill():
    # 전에는 기술이 없어 빠졌다. 이제 주소가 있으니 남고, 나중 단계가 채운다.
    client = FakeClient({"1": IMAGE_BODY})
    rows, _, stats = saramin._collect_details(client, [listing("1")])
    check_equal(len(rows), 1, "그림 공고를 잃으면 나중에 읽을 대상도 사라진다")
    check_equal(stats["기술없음"], 0, "빈 것으로 세면 안 된다")


def test_BOUNDARY_image_body_without_any_image_tag_is_still_dropped():
    # 글도 그림도 없는 공고. 나중에 읽을 것도 없으니 판단 재료가 없다.
    client = FakeClient({"1": detail("<p>짧은 글</p>")})
    rows, _, stats = saramin._collect_details(client, [listing("1")])
    check_equal(rows, [], "읽을 것이 아무것도 없으면 뺀다")
    check_equal(stats["기술없음"], 1, "뺀 개수를 알려야 한다")


def test_BOUNDARY_text_body_with_an_image_but_no_skill_keeps_the_url():
    # **결함이었던 곳.** 짧은 글 + 그림인 공고는 "이미지 본문" 으로 안 잡혀서
    # 그림 주소를 안 남겼고, 기술이 없다는 이유로 **통째로 버려졌다** (142건 중 4건).
    long_text = "우리 회사를 소개합니다. " * 20          # 기술 이름은 하나도 없다
    page = detail("<p>%s</p><img src=\"https://x.test/a.png\">" % long_text)
    client = FakeClient({"1": page})
    rows, _, stats = saramin._collect_details(client, [listing("1")])
    check_equal(len(rows), 1, "그림이 있으면 버리면 안 된다 — 나중에 읽을 대상이다")
    check("https://x.test/a.png" in rows[0]["기술스택"], "주소를 남겨야 한다")
    check_equal(stats["기술없음"], 0, "빈 것으로 세면 안 된다")


def test_BOUNDARY_text_body_with_skills_does_not_get_urls():
    # 그림 있는 공고가 142건 중 129건이다. 아무 때나 남기면 기술스택 칸이 주소로 덮인다.
    page = detail("<p>자격요건</p><p>Java 와 Spring 경험. " + "본문이 충분히 깁니다. " * 10
                  + "</p><img src=\"https://x.test/a.png\">")
    client = FakeClient({"1": page})
    rows, _, _ = saramin._collect_details(client, [listing("1")])
    check("http" not in rows[0]["기술스택"],
          "재료가 이미 있으면 주소를 안 남긴다: %r" % rows[0]["기술스택"])
    check("Java" in rows[0]["기술스택"], "기술은 그대로")


def test_BOUNDARY_neither_skill_nor_image_is_still_dropped():
    # 기술도 그림도 없으면 판단할 재료가 아무것도 없다. 그건 빼는 게 맞다.
    page = detail("<p>" + "회사 소개만 있습니다. " * 15 + "</p>")
    client = FakeClient({"1": page})
    rows, _, stats = saramin._collect_details(client, [listing("1")])
    check_equal(rows, [], "재료가 없으면 뺀다")
    check_equal(stats["기술없음"], 1, "뺀 개수를 알린다")
