"""Derived configuration, CI and documentation tasks written in Korean."""
from fx import family

from ._derive import derive, take

KO = [
    ("devops-compose-stacks-02-version", "01-compose-version", "terse",
     "compose.yaml: compose가 `§0` 속성은 더 이상 쓰이지 않는다(obsolete)는 경고를 출력합니다. 고쳐 주세요 "
     "(설정이 검사받는 규칙은 `§1`에 정리돼 있습니다)."),
    ("devops-k8s-manifests-02-api-ing", "02-ingress-api-version", "ticket",
     "quill-render의 매니페스트(`§0`)에 문제가 있습니다:\n- Ingress가 이 클러스터(1.30)에서 더 이상 제공하지 않는 API 버전을 "
     "쓰고 있습니다\n\n고쳐 주세요. 설정이 검사받는 규칙은 `§1`에 정리돼 있습니다."),
    ("devops-dockerfile-hygiene-03-copy-order", "03-docker-layer-cache", "terse",
     "Dockerfile: docker build를 해도 의존성 레이어가 전혀 재사용되지 않습니다. 고쳐 주세요 "
     "(설정이 검사받는 규칙은 `§0`에 정리돼 있습니다). 애플리케이션, 시작 명령, 포트는 그대로 두세요."),
    ("devops-ci-workflow-02-cache-key", "04-ci-cache-key", "ticket",
     "lumen-api의 CI 워크플로(`§0`)에 문제가 있습니다:\n- `§1`의 캐시 히트가 낡은 결과를 가져옵니다: lock 파일이 바뀌어도 "
     "키가 변하지 않습니다\n\n고쳐 주세요. 워크플로가 충족해야 할 조건은 `§2`에 적혀 있으니, 모든 job과 그 안의 명령은 "
     "그대로 유지하세요."),
    ("docs-py-doctests-01-seedbank-3fn", "05-doctest-examples", "short",
     "문서화 작업입니다: `§1`의 모든 public 함수에 실행 가능한 `§0` 예제를 추가해 주세요(함수마다 2개 이상, 예외를 "
     "던지는 함수는 에러가 나는 예제도). doctest로 통과해야 합니다. docstring만 고치고 코드는 바꾸지 마세요."),
    ("docs-cli-help-02-seedctl-3rules", "06-cli-help", "ticket",
     "`§0`와 하위 명령의 도움말이 거의 비어 있습니다: 설명도 없고 인자 도움말도 없습니다. `§1`을 따라 `§2`에서 명령줄 "
     "전체를 문서화해 주세요. 동작(파싱과 출력)은 바뀌면 안 되고, 도움말은 파서를 순회하면서 검사합니다."),
    ("devops-systemd-units-backup-timer", "07-systemd-backup-timer", "formal",
     "`§0`와 `§1` 한 쌍을 작성해 주세요. 서비스는 원샷 작업(`§2`, 사용자 `§3`)이고 자체 `§4` 섹션은 없습니다. 타이머는 "
     "매일 02:30에 서비스를 실행하고, 그 시각에 머신이 꺼져 있었다면 켜진 뒤에 따라잡아 실행하며, 최대 15분(900초)의 "
     "무작위 지연을 더하고, timers target으로 enable 됩니다. 유닛 파일이 검사받는 항목은 `§5`에 정리돼 있습니다."),
    ("devops-nginx-routing-canary-map-routing", "08-nginx-canary", "detailed",
     "`§0`에는 업스트림 `§1`, `§2`가 이미 정의되어 있습니다. 요청 헤더와 쿠키(`§6`, `§7`)를 이용해 `§5`(포트 80)용 `§3` 블록과 "
     "`§4` 블록을 추가해 주세요.\n\n"
     "- 헤더 `§9`가 정확히 `§10`이거나 쿠키 `§11`가 정확히 `§12`이면(둘 중 하나만 맞아도 됩니다) 요청을 `§8`로 프록시하고, "
     "그 외의 요청은 모두 `§13`로 보냅니다. 경로는 그대로 전달합니다.\n"
     "- 단, 정적 자산은 예외입니다. `§14` 아래 경로는 카나리 상태와 상관없이 `§15`에서 서빙합니다(alias; `§16`는 `§17`입니다).\n"
     "- 경로가 정확히 `§18`일 때만: `§19`에 `§20` 또는 `§21`가 포함되어 있으면(대소문자 무시) `§22`로 302 리디렉션합니다. "
     "카나리 규칙은 이 리디렉션에는 적용되지 않습니다.\n"
     "- `§23`는 nginx가 직접 200과 본문 `§24`을 응답하며 프록시하지 않습니다."),
    ("devops-ssh-config-client-policy", "09-ssh-config-policy", "detailed",
     "엔지니어 한 명의 `§0` 전체를 작성해 주세요. 아래 조건이 모두 성립해야 합니다(검사기는 여러 호스트를 직접 resolve 해 봅니다).\n\n"
     "1. 모든 호스트의 기본값: `§1`, `§2`, 그리고 마지막으로 시도되는 키로 `§3`.\n"
     "2. `§4`: 사용자 `§5`, 포트 2222, 점프 호스트 없음, 키 `§6`가 가장 먼저.\n"
     "3. 그 밖의 모든 `§7` 호스트: `§8`를 거쳐 접속하고, 사용자는 `§9`, 키는 기본 키보다 앞에 `§10`; "
     "`§11`는 점프 호스트가 없고(`§12`) 사용자는 `§13`.\n"
     "4. 짧은 별칭: `§14`과 `§15`는 각각 `§16` / `§17`(`§18` 사용)이며, 가리키는 호스트의 설정을 모두 그대로 유지합니다"
     "(`§19` 블록으로 가능). `§20`는 `§21`에만 적용.\n"
     "5. `§22`: 사용자 `§23`, 키는 `§24` 하나만, `§25`.\n"
     "6. 원격 사용자가 `§26`일 때마다(`§27` 또는 `§28`), 어떤 호스트에서든: `§29`가 가장 먼저 시도되는 키이고 `§30`가 "
     "설정됩니다. 다른 설정은 영향을 받지 않습니다(키는 누적됩니다)."),
]


@family("i18n-ko-devops", category="i18n", lang="text", kind="fix", n=len(KO), mode="fixture",
        summary="derived: configuration, CI, nginx/ssh/systemd and documentation tasks written in Korean, d1-d5")
def ko_devops(rng, n):
    for src, slug, style, prompt in take(KO, n):
        yield derive(src, prompt, slug, "ko", style=style)
