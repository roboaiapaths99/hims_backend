import pytest
from api.vitals import calculate_news_score

def test_news_score_calculation_normal():
    # Normal vitals: Systolic BP 120, pulse 75, temp 98.6, SpO2 98%
    score = calculate_news_score(bp_sys=120, pulse=75, temp_f=98.6, spo2=98)
    assert score == 0

def test_news_score_calculation_critical_low():
    # Critical low vitals: Systolic BP 80, pulse 35, temp 94.0, SpO2 88%
    score = calculate_news_score(bp_sys=80, pulse=35, temp_f=94.0, spo2=88)
    # Systolic BP <= 90 (+3)
    # Pulse <= 40 (+3)
    # SpO2 < 92 (+3)
    # Temp <= 95.0 (+3)
    # Total score should be 12
    assert score == 12

def test_news_score_calculation_moderate():
    # Moderate vitals: Systolic BP 98, pulse 115, temp 101.0, SpO2 93%
    score = calculate_news_score(bp_sys=98, pulse=115, temp_f=101.0, spo2=93)
    # Systolic BP 91-100 (+2)
    # Pulse 111-130 (+2)
    # SpO2 92-93 (+2)
    # Temp 100.5-102.2 (+2)
    # Total score should be 8
    assert score == 8
