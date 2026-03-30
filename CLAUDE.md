# Legalize KR — Project Guidelines

## Repository

- **GitHub**: `9bow/legalize-kr` (private)
- **기본 브랜치**: `main`
- **도메인**: `legalize.kr`

## Directory Structure

```
kr/{법령명}/                # 법령 파일 (같은 법률 계열이 하나의 디렉토리)
  법률.md                  # 법률
  시행령.md                # 대통령령 (법률의 시행령)
  시행규칙.md              # 부령 (법률의 시행규칙)
  대통령령.md              # 독립 대통령령 (규정, 직제 등)
scripts/                   # 수집·변환·검증 파이프라인 (README.md 참조)
docs/                      # 웹사이트 (GitHub Pages, legalize.kr)
  llms.txt                 # LLM용 프로젝트 안내
.github/workflows/         # CI/CD
  import.yml               # 법령 import (매일 13:00 KST, workflow_dispatch)
  pages.yml                # GitHub Pages 배포
metadata.json              # 법령 인덱스 (import 후 자동 생성)
```

### 파일 이름 규칙

- `{법률명} 시행령` → `kr/{법률명}/시행령.md`
- `{법률명} 시행규칙` → `kr/{법률명}/시행규칙.md`
- 접미사 없는 법률 → `kr/{법률명}/법률.md`
- 독립 대통령령 → `kr/{대통령령명}/대통령령.md`

## Commit Convention

### 법령 커밋 (공포일자를 커밋 날짜로 사용)

```
법률: {법령명} ({제개정구분})

법령 전문: https://www.law.go.kr/법령/{법령명}
제개정문: https://www.law.go.kr/법령/제개정문/{법령명}/({공포번호},{공포일자})
신구법비교: https://www.law.go.kr/법령/신구법비교/{법령명}

공포일자: YYYY-MM-DD | 공포번호: NNNNN
소관부처: {부처명}
법령분야: {분야}
법령MST: {MST}
```

### 인프라 커밋 (일반 날짜)

```
feat|fix|chore|docs|ci: 설명
```

### 필터링

```bash
git log -- "kr/민법/"              # 민법 관련 법령 이력
git log --grep="^법률:"            # 법률 커밋만
git log --grep="^chore:"           # 인프라 커밋만
```

## API

- **데이터 출처**: [국가법령정보센터 OpenAPI](https://open.law.go.kr)
- **인증**: `LAW_OC` 환경변수 (GitHub Secrets: `LAW_OC`)
- **Rate limit**: 1 req/sec, exponential backoff

## Data Notes

- **Unicode 정규화**: 가운뎃점 (`·` U+00B7) → `ㆍ` U+318D로 통일
- **다부처 법령**: `소관부처` 필드는 항상 YAML 리스트 형식
- **Idempotency**: 커밋 메시지의 `법령MST:` + checkpoint.json으로 중복 방지

## Website (GitHub Pages)

- **소스**: `docs/` 폴더
- **배포**: `.github/workflows/pages.yml`
- **커스텀 도메인**: `legalize.kr` (`docs/CNAME`)
- **LLM 안내**: `docs/llms.txt`
