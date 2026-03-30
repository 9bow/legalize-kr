# Scripts

법령 수집·변환·검증 파이프라인입니다.

## 사전 준비

```bash
pip install -r requirements.txt
```

환경 변수 `LAW_OC`에 [국가법령정보센터 OpenAPI](https://open.law.go.kr) 키를 설정합니다.

## 전체 import (최초 실행)

```bash
# 모든 법령
LAW_OC=your-law-openapi-key python import_laws.py

# 법률만
LAW_OC=your-law-openapi-key python import_laws.py --law-type 법률

# 대통령령만
LAW_OC=your-law-openapi-key python import_laws.py --law-type 대통령령

# 미리보기
LAW_OC=your-law-openapi-key python import_laws.py --limit 10 --dry-run
```

API 키 없이, 국가법령정보 사이트의 [법령목록지원](https://open.law.go.kr/LSO/lab/lawListSupport.do) 메뉴에서 CSV 파일을 내려받아 실행할 수도 있습니다:

```bash
python import_laws.py --csv /some/path/법령검색목록.csv
```

## 증분 업데이트 (일일 실행)

```bash
# 최근 7일 (기본값)
python update.py

# 최근 30일
python update.py --days 30
```

GitHub Actions에서 매일 13:00 KST에 자동 실행됩니다.

## 메타데이터 재생성

```bash
python generate_metadata.py
```

`kr/` 아래 모든 `.md` 파일을 스캔하여 `metadata.json`을 갱신합니다.

## 유효성 검증

```bash
python validate.py
```

검증 항목:
- YAML frontmatter 필수 필드
- `소관부처`가 YAML 리스트인지
- Unicode 가운뎃점 정규화 (U+00B7 → U+318D)
- `metadata.json`과 파일 시스템 일치

## 디렉토리 구조

```
kr/{법령명}/
  법률.md          # 국회에서 제정하는 법률
  시행령.md        # 법률의 시행령 (대통령령의 일종)
  시행규칙.md      # 법률의 시행규칙 (부령)
  대통령령.md      # 독립 대통령령 (규정, 직제 등 — 부모 법률 없음)
```

## 커밋 메시지 형식

각 법령 커밋은 law.go.kr 참조 URL과 메타데이터를 포함합니다:

```
법률: 민법 (일부개정)

법령 전문: https://www.law.go.kr/법령/민법
제개정문: https://www.law.go.kr/법령/제개정문/민법/(12345,20260317)
신구법비교: https://www.law.go.kr/법령/신구법비교/민법

공포일자: 2026-03-17 | 공포번호: 12345
소관부처: 법무부
법령분야: 민사
법령MST: 284415
```
