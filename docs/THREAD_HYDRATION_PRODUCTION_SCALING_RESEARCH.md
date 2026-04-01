작성일시: 2026-03-28 00:23 KST

# Thread Hydration Production Scaling Research

## 요약

현재 OrchAgent 프런트는 사용자가 이전 스레드를 클릭할 때 보통 두 개의 read endpoint를 호출한다.

- `/api/threads/{thread_id}`
- `/api/threads/{thread_id}/telemetry`

이 구조 자체는 비정상적이지 않다. 대화 본문과 오른쪽 보조 패널 데이터를 분리하는 패턴은 프로덕션에서도 충분히 성립한다. 다만 사용자 수, 스레드 수, 대화 길이, telemetry 계산량이 커지는 단계에서는 `매 클릭마다 2~3회 read`를 그대로 두기보다 `캐시`, `prefetch`, `precompute`, `conditional request`, `response shaping`으로 다듬는 것이 맞다.

핵심 결론은 다음과 같다.

- 현재 구조는 V1 기준으로 합리적이다.
- 대규모 단계에서는 “endpoint 개수”보다 “같은 데이터를 몇 번 다시 계산/다시 전송하느냐”가 더 중요하다.
- 가장 먼저 해야 할 최적화는 `thread detail + telemetry precompute`, `client cache`, `hover/click prefetch`, `ETag/304`다.
- `detail + telemetry`를 하나의 endpoint로 합칠지는 지연 비용과 계산 비용을 기준으로 결정해야 한다.
- 상용 대화형 서비스들도 고유 conversation URL을 가지며, 내부 구현은 공개되어 있지 않지만 제품 동작상 `on-demand hydration + route cache + partial reuse` 쪽일 가능성이 높다. 이 부분은 제품 동작 기반 추론이며, 공식 문서가 내부 fetch topology를 직접 공개한 것은 아니다.

## 현재 OrchAgent 구조 해석

현재 구조는 다음 장단점이 있다.

장점:

- 메시지 본문과 보조 패널 정보를 분리해 응답 스키마가 단순하다.
- telemetry가 무겁거나 생성 지연이 있어도 thread detail 본문 표시를 먼저 할 수 있다.
- suggested queries 재생성 같은 background 동작을 본문 hydrate와 분리할 수 있다.

단점:

- thread open 시 네트워크 round-trip이 2회 이상 발생한다.
- client cache가 없으면 같은 thread를 반복해서 열 때 read amplification이 생긴다.
- telemetry가 요청 시점 계산이면 DB/LLM/요약 로직이 클릭마다 반복될 수 있다.

즉, 지금 구조의 병목 가능성은 “2 endpoint라서”보다 “telemetry를 매번 다시 만들고 있는가”, “같은 thread를 다시 열 때 cache hit가 없는가”에 더 가깝다.

## 공개 문서 기준으로 볼 수 있는 상용 서비스 패턴

### 1. 고유 conversation URL

OpenAI는 shared links를 통해 ChatGPT conversation이 고유 URL을 가진다는 점을 공개하고 있다. 내부 hydration 구현은 공개하지 않지만, conversation URL이 존재한다는 사실 자체는 `route-driven conversation identity`를 전제로 한다.

시사점:

- conversation은 URL로 식별되고
- 내용을 여는 시점에 필요한 데이터를 불러오며
- 모든 스레드의 전체 본문을 초기 진입에서 한꺼번에 들고 있지는 않을 가능성이 높다

위 마지막 항목은 제품 동작 기반 추론이다.

### 2. App Router 계열의 일반적인 생산성 패턴

Next.js 문서는 App Router가 `Router Cache`, `prefetch`, `shared layout reuse`, `back/forward reuse`를 제공한다고 설명한다. 이건 대화형 제품에서 `/c/{threadId}` 같은 route를 열 때, 경로 전환을 빠르게 만들 수 있는 기본 메커니즘이다.

시사점:

- route를 source of truth로 두는 설계는 맞다
- navigation 성능은 네트워크 호출 수뿐 아니라 route cache와 prefetch에 크게 좌우된다
- “다음에 열 가능성이 높은 thread”에 대한 prefetch가 비용 대비 효율이 높다

### 3. Client query cache 관례

TanStack Query 문서는 기본적으로 query 데이터를 stale로 보지만, `staleTime`, `gcTime`, `prefetchQuery`로 refetch 빈도와 재사용 범위를 조절할 수 있다고 설명한다.

시사점:

- thread detail / telemetry는 query cache와 매우 잘 맞는 데이터다
- “한 번 열었던 thread를 곧바로 다시 열기”는 staleTime만 적절히 줘도 대부분 재요청을 줄일 수 있다
- hover prefetch나 router integration이 request waterfall을 줄이는 핵심이다

## 대규모 프로덕션 단계에서 권장되는 개선 축

## 1. On-click 계산을 없애고 turn-complete 시점에 telemetry를 저장

가장 먼저 검토해야 할 것은 `/telemetry`의 데이터가 요청 시점 계산인지, turn 완료 시점에 저장된 값인지다.

권장 방향:

- `reasoning_summary`
- `suggested_queries`

이 둘은 가능하면 turn 완료 시점에 precompute해서 저장한다.

이유:

- 클릭 read path에서 LLM 재호출을 막을 수 있다
- thread open latency의 분산이 줄어든다
- 클릭 수가 많아져도 read endpoint는 DB lookup 중심이 된다

## 2. detail/telemetry를 둘 다 유지하되, “항상 필요한 최소값”은 detail에 포함

두 endpoint를 완전히 하나로 합칠지 여부는 케이스 바이 케이스다.

권장 기준:

- 오른쪽 패널이 항상 열려 있고 반드시 함께 보여야 한다면
  - `ThreadDetailWithTelemetry` 단일 응답이 더 실용적일 수 있다
- telemetry가 무겁거나, 패널이 접혀 있거나, 일부만 lazy-load 가능하다면
  - 분리 endpoint를 유지하는 편이 낫다

실용적인 절충안:

- `/api/threads/{thread_id}`
  - `thread`, `messages`
  - 가벼운 `reasoning_summary`
  - 가벼운 `suggested_queries_count` 또는 precomputed snippet
- `/api/threads/{thread_id}/telemetry`
  - 전체 reasoning summary
  - 전체 suggested queries
  - raw traces 또는 heavy debug payload

즉, “합치기 vs 분리” 이분법보다 “가벼운 값은 detail에 포함, 무거운 값은 telemetry에 유지”가 더 현실적이다.

## 3. Client cache 도입

현재 같은 thread를 여러 번 오갈 때마다 다시 요청한다면 대규모 단계에서 가장 아쉬운 지점이다.

우선순위가 높은 개선:

- thread detail cache
- telemetry cache
- `staleTime` 설정
- inactive query GC 정책
- focus refetch 억제

대화형 앱에서 적절한 기본값 예시는 다음 정도다.

- thread detail: `staleTime 30~120초`
- telemetry: `staleTime 30~120초`
- 새 message 전송, rename, pin, delete 시 명시적 invalidate

이렇게 하면 “사용자가 방금 열었던 스레드를 다시 누르는” 패턴에서 read traffic을 크게 줄일 수 있다.

## 4. Hover prefetch / viewport prefetch

대화 목록 UI는 다음 클릭 가능성이 높은 엔티티가 명확하다. 이런 경우 prefetch가 효과적이다.

좋은 후보:

- sidebar에서 hover된 thread
- pinned threads
- 최근 active threads 상위 N개

주의점:

- 무차별 prefetch는 오히려 비용을 늘린다
- hover intent 기반, 최근성 기반, viewport 상위 일부만 prefetch하는 편이 낫다

즉, “thread list 전체 prefetch”보다 “상위 few threads만 prefetch”가 맞다.

## 5. HTTP conditional request

MDN의 HTTP caching 가이드는 API endpoint에도 `ETag`, `Last-Modified`, `304 Not Modified` 패턴을 사용할 수 있다고 설명한다.

이건 thread detail/telemetry 같은 읽기 endpoint에 특히 잘 맞는다.

권장 방향:

- `ETag` 또는 `Last-Modified`
- `Cache-Control: private, no-cache`
- client가 `If-None-Match` 또는 `If-Modified-Since` 전송
- 변경 없으면 `304`

장점:

- payload transfer 감소
- 모바일/해외 네트워크에서 체감 개선
- CDN이 아니라도 브라우저/클라이언트 수준에서 효율이 좋아짐

## 6. Read path observability

대규모 단계에서는 반드시 아래 지표를 봐야 한다.

- thread detail p50/p95
- telemetry p50/p95
- combined open-thread latency
- cache hit ratio
- 304 ratio
- prefetch hit ratio
- invalid thread fallback rate
- user당 thread open read QPS

이게 없으면 “2 endpoint가 문제인지”, “telemetry 계산이 문제인지”, “같은 thread 재요청이 문제인지”를 구분하기 어렵다.

## 7. 실패 분리

대화 본문과 보조 패널은 실패 영향도를 다르게 가져가는 편이 좋다.

권장 정책:

- detail 실패
  - thread open 실패
  - `/` fallback 또는 명확한 error state
- telemetry 실패
  - 본문은 그대로 보여줌
  - 오른쪽 패널만 degraded state

즉, telemetry는 본문보다 낮은 우선순위로 다뤄야 한다.

## OrchAgent에 대한 실무 판단

현재 레포 기준으로는 아래 순서가 비용 대비 효과가 가장 높다.

1. telemetry precompute 저장
2. thread detail / telemetry client cache 도입
3. sidebar hover prefetch
4. ETag/304
5. 필요 시 detail + lightweight telemetry 결합

반대로 아래는 지금 바로 해도 효과가 애매할 수 있다.

- 무조건 detail/telemetry 단일 endpoint로 합치기
- thread list 모든 항목 prefetch
- raw trace까지 thread open 시 한 번에 모두 내려주기

## 추천 결론

- 현재 2-endpoint 구조는 유지 가능하다.
- 다만 프로덕션 단계에서는 `계산을 클릭 시점에서 turn 완료 시점으로 옮기고`, `cache/prefetch/conditional request`를 반드시 붙여야 한다.
- “2개를 1개로 합칠지”는 그 다음 문제다.

## 출처

- OpenAI Help: ChatGPT Shared Links FAQ  
  https://help.openai.com/en/articles/7925741-chatgpt-sharedlinks-faq
- Next.js Docs: Caching  
  https://nextjs.org/docs/app/deep-dive/caching
- Next.js Docs: Prefetching  
  https://nextjs.org/docs/app/guides/prefetching
- Next.js Docs: Linking and Navigating  
  https://nextjs.org/docs/app/getting-started/linking-and-navigating
- TanStack Query Docs: Important Defaults  
  https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults
- TanStack Query Docs: Prefetching & Router Integration  
  https://tanstack.com/query/latest/docs/framework/react/guides/prefetching
- MDN: HTTP Caching  
  https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching
