"""Exact generation inputs for audit; contains no API credentials."""
import hashlib
import json


def validate_generation_record(record):
    """Validate stored request bytes; no reconstruction or backfill of old drafts."""
    if not isinstance(record, dict):
        raise ValueError('Invalid generation record type')
    if record.get('schema_version') != 1 or record.get('prompt_version') not in ('selected-v1', 'legacy-v1'):
        raise ValueError('Unsupported AI generation record')
    for value, hash_key in (('instructions', 'instructions_sha256'), ('input_json', 'input_sha256')):
        text = record.get(value)
        if not isinstance(text, str) or not text or hashlib.sha256(text.encode('utf-8')).hexdigest() != record.get(hash_key):
            raise ValueError('Generation request fingerprint mismatch')
    if not isinstance(json.loads(record['input_json']), dict):
        raise ValueError('Invalid generation input')
    expected = SELECTED_INSTRUCTIONS if record['prompt_version'] == 'selected-v1' else LEGACY_INSTRUCTIONS
    if record['instructions'] != expected or record.get('max_output_tokens') != (950 if record['prompt_version'] == 'selected-v1' else 750) or record.get('store') is not False:
        raise ValueError('Generation method mismatch')

LEGACY_INSTRUCTIONS = '너는 K-POP 데이터 기사 작성 보조자다. 제공된 JSON 이외의 사실은 사용하지 않는다. 한국어로 제목 1줄 + 본문 2문단의 짧은 기사 초안을 작성한다(가능하면 450자 이내). 반드시 두 주차의 정확한 기간, Global 지역, Animal·SaWaDiKa의 플랫폼별 순위 변화 및 각 플랫폼 내부 소비량 증감률을 적는다. Spotify 주간 스트리밍과 YouTube 주간 곡 차트 조회수는 다른 지표라고 설명한다. Spotify 상위 200곡, YouTube 상위 100곡이라는 차트 범위 차이도 적는다. Spotify Charts와 YouTube Charts를 출처로 표시한다. Hootie Frutti는 검수 보류로 주요 분석에서 제외되었으니 언급하지 않는다. 확인되지 않은 원인, 사용자 수, 인용문, 팬덤 규모, 인기 배수, 글로벌 K-POP 전체의 일반화는 절대 작성하지 않는다. 새로운 수치를 계산하거나 창작하지 않는다. 출고 승인되었다고 표현하지 않는다.'

SELECTED_INSTRUCTIONS = '너는 데이터 저널리즘 기사의 초안을 작성하는 편집 보조자다. 제공된 JSON의 analysis_tracks에 있는 곡만 다룬다. 한국어 제목 한 줄과 본문 두세 문단을 작성한다. Global 범위, 두 주간 날짜, 각 곡의 두 플랫폼 순위 변화 및 플랫폼 내부 수치 변화율을 정확히 표기하라. Spotify는 주간 스트리밍, YouTube는 Weekly Top Songs 주간 조회수이며 동일 지표가 아니다. 차트의 상위 200곡/100곡 범위 차이를 밝혀라. 제공된 곡 외의 곡·인터뷰·원인·팬덤 규모·인구 추정·외부 통계를 만들어내지 마라. 인기도 배율이나 플랫폼 간 수치 차이 계산을 금한다. K-POP 전체 현상으로 일반화하지 않는다. 출처 Spotify Charts와 YouTube Charts를 적고, 검수 전 초안이며 최종 출고 미승인임을 끝에 적는다. 입력에 없는 숫자는 추가하지 마라.'

def generation_record(evidence, *, selected=True, ai_generated=True):
    """Record the same JSON serialization and instruction bytes sent to the model."""
    instructions = (SELECTED_INSTRUCTIONS if selected else LEGACY_INSTRUCTIONS) if ai_generated else None
    input_text = json.dumps(evidence, ensure_ascii=False)
    return {
        'schema_version': 1,
        'prompt_version': ('selected-v1' if selected else 'legacy-v1') if ai_generated else 'template-v1',
        'instructions': instructions,
        'instructions_sha256': hashlib.sha256(instructions.encode('utf-8')).hexdigest() if instructions else None,
        'input_json': input_text,
        'input_sha256': hashlib.sha256(input_text.encode('utf-8')).hexdigest(),
        'max_output_tokens': (950 if selected else 750) if ai_generated else None,
        'store': False if ai_generated else None,
    }
