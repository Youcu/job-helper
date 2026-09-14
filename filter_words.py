"""거르기의 **말 규칙**만 모은다 — 공고를 묶는 키와, 빼는 낱말.

`filter.py` 에서 떼어 낸 이유는 줄 수가 아니라 **바뀌는 이유가 다르기** 때문이다.
`filter.py` 는 파일을 읽고 쓰고 보고하는 절차라 거의 안 바뀌지만, 여기 있는 낱말표와
경계 규칙은 실제 공고를 보다가 "이건 오탐이다" 를 만날 때마다 손댄다.

    company_key(name) / title_key(name)   같은 공고인지 가리는 키
    banned_words(text)                    걸린 낱말들 (없으면 빈 리스트)
"""
from __future__ import annotations

import re
import unicodedata

# 낱말을 찾을 칸. **사용자가 지정한 셋뿐이다.**
#
# `기술스택`·`근무지`·`기업명` 에는 걸지 않는다 — 회사 이름과 지역명이 낱말을 품는다.
# 실측으로 `에스아이알소프트`·`넥스에스아이` 같은 기업명이 있고, 이런 회사의 공고가
# 본문에는 SI 를 한 번도 안 쓰는 경우가 있다. 이름만으로 자르면 근거 없이 자르는 것이다.
TEXT_COLUMNS = ("공고명", "지원자격", "우대사항")

# 법인 표기. 사이트마다 다르게 적는다 — 실측 710행에서 같은 공고명을 쓴 37개 그룹 중
# **27개가 이 표기 차이 하나로 갈렸다.** `(주)안랩` vs `㈜안랩`,
# `뱅크웨어글로벌(주)` vs `뱅크웨어글로벌㈜`, `아이낸스(주)` vs `아이낸스㈜`.
LEGAL_FORM = re.compile(r"주식회사|㈜|\(주\)|\(유\)|\(재\)|\(사\)|유한책임회사|유한회사")

_SPACES = re.compile(r"\s+")

# **바꿔 써도 같은 뜻인 기호.** 같은 공고가 사이트마다 다른 기호로 올라온다 —
# 실측(2026-09-11, 707행)에서 세 쌍이 이것 하나로 갈렸다.
#
#     백엔드 개발자 (신입 **-** 3년)          사람인
#     백엔드 개발자 (신입 **~** 3년)          잡코리아
#     … (LLM 파이프라인 **·** 대규모 …)      원티드
#     … (LLM파이프라인**/**대규모 …)          사람인
#     **IT** 해내는 개발자 …                  사람인
#     **[IT]** 해내는 개발자 …                잡코리아
#
# **괄호는 문자만 지우고 안쪽 글은 남긴다.** 통째로 떼면 `[인턴] Backend Engineer` 가
# `Backend Engineer` 와 같아져 **다른 자리를 하나로 뭉갠다.** 안쪽 글을 남기면
# `인턴backendengineer` vs `backendengineer` 라 여전히 다르고, 위의 `IT` 처럼
# 안쪽이 같은 경우만 묶인다.
#
# 이 표를 넓힐 때는 **실제 데이터로 새로 묶이는 짝을 전부 눈으로 보라.** 기호 하나를
# 더할 때마다 없는 중복을 만들 수 있고, 그렇게 지운 공고는 흔적이 안 남는다.
INTERCHANGEABLE = re.compile(
    r"[\[\]()（）{}<>〈〉《》「」『』~〜\-‐‑‒–—―/／·・,，:：|｜]")


def company_key(name: str | None) -> str:
    """같은 회사인가를 가리는 키. 법인 표기와 공백을 지우고 대소문자를 눌러 맞춘다."""
    return _SPACES.sub("", LEGAL_FORM.sub("", name or "")).lower()


def title_key(name: str | None) -> str:
    """같은 자리인가를 가리는 키.

    **대괄호 안의 글은 떼지 않는다.** `[인턴] Backend Engineer` 와 `Backend Engineer` 는
    다른 자리다. 대괄호를 통째로 떼면 없는 중복을 만들어 멀쩡한 공고를 지운다 —
    지우는 판단에 "모르겠으면 지운다" 는 없다.

    다만 **기호 자체는 사이트마다 흔들린다.** 위 `INTERCHANGEABLE` 주석을 보라.
    """
    text = unicodedata.normalize("NFKC", name or "")
    return _SPACES.sub("", INTERCHANGEABLE.sub("", text)).lower()


def key(row: dict) -> tuple[str, str]:
    """공고 하나의 중복 키. **기업명과 공고명이 둘 다 같아야 같은 공고다.**

    공고명 하나만 쓰면 다른 회사가 같은 제목을 쓴 것까지 묶인다. 실측 4건이 그랬다 —
    `SW Engineer`(비햅틱스 / 퀄리타스반도체), `각 부문별 채용`(웨어밸리 / 형원이엔지),
    `백엔드 개발자 (신입)`(이너버스 / 티엔에이치),
    `입찰 조달 데이터 기반 웹서비스 개발 및 운영자 모집`(케이비드 / 한국전자입찰연구소).
    """
    return company_key(row.get("기업명")), title_key(row.get("공고명"))


# **뺄 낱말.** 사용자가 정한 목록이다 (2026-09-10).
#
# ## 왜 대소문자를 구분하고, 왜 ASCII 경계인가 — 실측 710행 기준
#
#   소문자까지 받으면(`re.I`)   si → 110행이 걸린다. vision · design · business · size ·
#                              extension · assignment · physics · ansible · simulation ·
#                              version 이 전부 SI 가 된다
#                              sm →  35행. isms · smart · smoothing · prisma · langsmith ·
#                              plasma · parallelism
#   대소문자만 구분하면        SI 에 SIEMENS · SIEM · SIMPAC · ASIC · SSIM · VLSI · WSI 가 남고
#                              SM 에 ISMS · HSM · SMS 가 남는다
#
# 그래서 **앞뒤에 ASCII 영숫자가 없을 때만** 낱말로 본다. 한글은 경계로 치지 않는다 —
# `SI프로젝트` 는 붙여 써도 SI 다.
#
# `\bSI\b` 는 쓰지 않는다. 파이썬의 `\b` 는 **한글도 낱말 문자로 보므로** `SI프로젝트` ·
# `SI업체` · `SM사업부` · `ㆍSI &` 앞뒤에 경계가 없어 **놓친다** (실측 SI 3행 · SM 1행).
# 아래 규칙은 `\b` 가 잡는 것을 하나도 안 놓치면서 그 넷을 더 잡는다.
#
# ## 한글 낱말은 경계를 두지 않는다
#
# 실측으로 이것들을 부분으로 품은 다른 말이 없었다.
#   현역   → 현역 · 현역전직 · 현역x
#   파견   → 파견 · 파견근무 · 단기파견
#   고객사 → 고객사 · 고객사와 · 고객사에서 · 신규고객사
# 전부 같은 뜻이라 경계를 두면 오히려 놓친다.
#
# ## 이 표가 **잡지 못하는 것** (실측)
#
#   · `SI 개발자 성향이 아닌 애자일 방식…` — SI 를 **부정**하는 문장인데 걸린다. 3행.
#   · 패션 VMD 공고의 `SI 채용` — 여기서 SI 는 Store Identity 다. 1행.
#   · `글로벌 고객사와 영어로 소통` 처럼 자체 제품 회사의 평범한 `고객사` 언급.
# 낱말만 보고는 이것을 가릴 수 없다. 그래서 **뺀 행을 전량 보고 CSV 에 남긴다** —
# 사람이 파일 하나로 되짚을 수 있어야 한다.
#
# 되돌리려면 이 표에서 줄을 빼면 된다. 실측 건수는 실행할 때마다 화면에 찍힌다.
BANNED = (
    ("SI", re.compile(r"(?<![A-Za-z0-9])SI(?![A-Za-z0-9])")),
    ("SM", re.compile(r"(?<![A-Za-z0-9])SM(?![A-Za-z0-9])")),
    # `병영특례` 가 아니라 `병역특례` 다. 사용자가 적어 준 표기는 데이터에 0건이고,
    # 실제로 쓰이는 말은 `병역특례` 로 25행이었다 (2026-09-10 확인).
    ("병역특례", re.compile(r"병역\s*특례")),
    ("현역", re.compile(r"현역")),
    ("보충역", re.compile(r"보충역")),
    ("산업기능요원", re.compile(r"산업\s*기능\s*요원")),
    # 병역특례 제도의 나머지 반쪽. 목록에 없었지만 같은 자리라 사용자가 넣기로 했다.
    ("전문연구요원", re.compile(r"전문\s*연구\s*요원")),
    ("고객사", re.compile(r"고객사")),
    ("파견", re.compile(r"파견")),
)

# 걸린 낱말 앞뒤로 이만큼을 보고에 함께 적는다. 짧으면 왜 걸렸는지 알 수 없고,
# 길면 보고 CSV 가 눈으로 못 읽을 만큼 넓어진다.
CONTEXT = 24


def text_of(row: dict) -> str:
    return "\n".join((row.get(column) or "") for column in TEXT_COLUMNS)


def banned_words(text: str) -> list[tuple[str, str]]:
    """걸린 (낱말, 근거) 들. 하나도 없으면 빈 리스트.

    근거는 **처음 걸린 자리의 앞뒤 글**이다. 같은 낱말이 여러 번 나와도 하나만 적는다 —
    사람이 확인할 때 필요한 것은 "어디서 걸렸나" 한 군데다.
    """
    found = []
    for name, pattern in BANNED:
        match = pattern.search(text)
        if match:
            found.append((name, _around(text, match)))
    return found


def _around(text: str, match: re.Match) -> str:
    start = max(0, match.start() - CONTEXT)
    end = min(len(text), match.end() + CONTEXT)
    return " ".join(text[start:end].split())


# ── 기술스택으로 빼기 ────────────────────────────────────────────────────
#
# **`.env` 의 `EXCLUDE_TECH_STACKS` 가 정한다.** 위의 `BANNED` 와 세 가지가 다르다.
#
#   보는 칸    `기술스택` 하나뿐. 산문에서 보면 "PHP 경험 있으면 좋지만 필수 아님"
#              같은 문장에도 걸린다
#   정하는 곳  사람이 `.env` 에 적는다. `BANNED` 는 낱말마다 규칙이 달라(ASCII 경계·
#              띄어쓰기 허용) 평문으로 옮길 수 없다 — `SI` 를 평문으로 두면
#              `Vision`·`Design` 이 걸려 실측 110행이 날아간다
#   찾는 법    `core_stack.py` 와 같은 ASCII 경계. `CORE_TECH_STACKS` 의 반대라
#              규칙도 대칭이어야 한다
#
# 실측(2026-09-14, `EXCLUDE_TECH_STACKS=PHP, jQuery`): `merged_read` 676행에서
# PHP 41행 · jQuery 49행. 일찍 뺄수록 잡플래닛에 물어볼 회사가 준다.
TECH_COLUMN = "기술스택"


def tech_pattern(name: str) -> re.Pattern[str]:
    """이름 하나를 **낱말로** 찾는 정규식.

    앞뒤에 ASCII 영숫자가 붙으면 다른 낱말이다 — `PHP` 는 `PHPStorm` 이 아니고
    `jQuery` 는 `Query` 가 아니다. 한글은 경계로 안 친다. 대소문자는 안 가린다.
    """
    return re.compile(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(name),
                      re.IGNORECASE)


def build_excluded(names: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    """`.env` 에 적힌 이름들 → (이름, 정규식). 빈 이름은 버린다."""
    return [(name, tech_pattern(name)) for name in names if name.strip()]


def excluded_techs(row: dict, rules: list) -> list[str]:
    """이 공고의 `기술스택` 칸에서 걸린 이름들. 없으면 빈 목록."""
    text = row.get(TECH_COLUMN) or ""
    return [name for name, rule in rules if rule.search(text)]
