"""공고 상세 JSON → CSV 한 줄.

`최초수집일` `최종확인일` 은 여기서 채우지 않는다. 한 실행 안에서 알 수 있는 값이 아니라
쌓아 둔 파일과 맞대 봐야 나오는 값이라, `_common/store.merge()` 가 채운다.
"""
from __future__ import annotations

from _common.store import COLUMNS  # noqa: F401  (사이트 공통 스키마. 다시 내보낸다)

from .skills import find_skills_in_text, normalize_tag

SITE_NAME = "wanted"
JOB_URL = "https://www.wanted.co.kr/wd/{job_id}"

# annual_to 가 100 이면 상한이 없다는 뜻으로 쓰인다 (실측: 5~100, 3~100 …).
UNBOUNDED_YEARS = 100


def format_deadline(due_time: str | None) -> str:
    """'2026-09-30T00:00:00' → '2026-09-30'. 없으면 상시채용."""
    if not due_time:
        return "상시채용"
    return str(due_time)[:10]


def format_career(annual_from: int | None, annual_to: int | None) -> str:
    """경력 범위를 사람이 읽는 문구로.

    API 가 늘 곱게 주지는 않는다고 보고 방어한다 — 음수는 없는 값으로 보고,
    상하한이 뒤집혀 있으면 바로잡는다. 안 그러면 `10~3년`, `신입~-1년` 같은
    말이 안 되는 문구가 CSV 에 그대로 실린다.
    """
    if annual_from is not None and annual_from < 0:
        annual_from = None
    if annual_to is not None and annual_to < 0:
        annual_to = None
    if annual_from is not None and annual_to is not None and annual_from > annual_to:
        annual_from, annual_to = annual_to, annual_from
    if annual_from is None and annual_to is None:
        return "경력무관"
    if annual_from is None:
        annual_from = 0
    if annual_to is None or annual_to >= UNBOUNDED_YEARS:
        return "신입" if annual_from == 0 else f"{annual_from}년 이상"
    if annual_from == 0:
        return "신입" if annual_to == 0 else f"신입~{annual_to}년"
    if annual_from == annual_to:
        return f"{annual_from}년"
    return f"{annual_from}~{annual_to}년"


def format_workplace(address: dict | None) -> str:
    """정리된 '시도 구' 를 먼저 놓고, 회사가 적은 상세 주소를 뒤에 붙인다.

    `full_location` 은 회사 자유 입력이라 구 이름이 빠지거나('테헤란로 201')
    다른 구가 적히기도 한다('서초구 …' 인데 등록 구는 강남구). 그대로 쓰면
    근무지로 거른 결과를 CSV 에서 다시 확인할 수 없어서, 구조화된 값을 앞세운다.
    """
    address = address or {}
    full = (address.get("full_location") or "").strip()
    district = (address.get("district") or "").strip()
    structured = " ".join(p for p in [address.get("location"), district] if p).strip()

    if not full:
        return structured
    if not structured or (district and district in full):
        return full
    return f"{structured} · {full}"


def skill_body_text(job: dict) -> str:
    """기술 이름을 찾을 산문. 회사가 직접 쓴 세 항목만 본다."""
    detail = job.get("detail") or {}
    return "\n".join(
        filter(
            None,
            [
                detail.get("requirements"),
                detail.get("preferred_points"),
                detail.get("main_tasks"),
            ],
        )
    )


def extract_skills(job: dict) -> list[str]:
    """상세 응답 한 벌에서 기술 이름을 모은다.

    ① `skill_tags` — 회사가 목록에서 골라 체크한 것. 먼저 놓는다.
    ② 산문 — 회사가 문장으로 쓴 것.

    둘은 서로를 포함하지 않는다(실측 122건: ①에만 있는 기술 81개, ①이 비고
    ②에만 있는 공고 87건). 표기는 양쪽 다 `tags/wanted_skill.json` 의 표준으로
    맞춰 두므로 그대로 합칠 수 있다.
    """
    skills: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        name = name.strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            skills.append(name)

    for tag in job.get("skill_tags") or []:
        add(normalize_tag(tag))
    for name in find_skills_in_text(skill_body_text(job)):
        add(name)
    return skills


def to_row(job: dict) -> dict:
    """공고 하나를 CSV 한 줄로. 공고번호가 없으면 만들지 않는다.

    번호가 없으면 URL 이 `.../wd/None` 이 된다. 열리지 않는 주소를 조용히 내보내느니
    호출하는 쪽에서 세고 알리게 한다.
    """
    job_id = job.get("id")
    if job_id is None:
        raise ValueError("공고 id 가 없어 행을 만들 수 없습니다")
    detail = job.get("detail") or {}
    return {
        "기업명": (job.get("company") or {}).get("name") or "",
        # 공고 제목은 상세의 `position` 이다. 목록 응답에는 없다 — 상세를 안 받은
        # 공고는 빈칸이 되고, 그건 사실대로 빈 것이지 못 읽은 것이 아니다.
        "공고명": (detail.get("position") or "").strip(),
        "마감일": format_deadline(job.get("due_time")),
        "지원자격": (detail.get("requirements") or "").strip(),
        "우대사항": (detail.get("preferred_points") or "").strip(),
        "경력": format_career(job.get("annual_from"), job.get("annual_to")),
        "URL": JOB_URL.format(job_id=job_id),
        # Wanted 는 연봉을 공개하지 않는다 (상세 API 에 필드 자체가 없음).
        # 다른 사이트 CSV 와 스키마를 맞추려고 칸만 남겨 둔다.
        "연봉": "",
        "기술스택": ", ".join(extract_skills(job)),
        "근무지": format_workplace(job.get("address")),
        "사이트명": SITE_NAME,
    }
