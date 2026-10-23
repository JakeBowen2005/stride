from app.api.wellness import recovery_signals, training_status_label
from datetime import date

from app.services.wellness import fetch_range, flatten_summary, parse_day

SUMMARY = {"restingHeartRate": 41, "lastSevenDaysAvgRestingHeartRate": 43, "bodyBatteryMostRecentValue": 58,
           "bodyBatteryAtWakeTime": 95, "averageStressLevel": 20, "totalSteps": 11996, "dailyStepGoal": 19840}
SLEEP = {"dailySleepDTO": {"sleepTimeSeconds": 25980, "deepSleepSeconds": 5700, "remSleepSeconds": 5340,
                           "sleepScores": {"overall": {"value": 89, "qualifierKey": "GOOD"}}}}
HRV = {"hrvSummary": {"lastNightAvg": 103, "weeklyAvg": 97, "status": "BALANCED",
                      "baseline": {"balancedLow": 78, "balancedUpper": 115}}}
READINESS = [{"score": 70, "level": "MODERATE", "feedbackShort": "RECOVERY_IN_PROGRESS", "recoveryTime": 1385}]
STATUS = {"mostRecentTrainingStatus": {"latestTrainingStatusData": {"123": {
              "trainingStatusFeedbackPhrase": "PRODUCTIVE_3",
              "acuteTrainingLoadDTO": {"dailyTrainingLoadAcute": 585, "dailyTrainingLoadChronic": 466,
                                       "dailyAcuteChronicWorkloadRatio": 1.2}}}},
          "mostRecentVO2Max": {"generic": {"vo2MaxPreciseValue": 53.3}}}
PRED = {"time5K": 1280, "time10K": 2784, "timeHalfMarathon": 6387, "timeMarathon": 14310}


def test_parse_day_real_shapes():
    d = parse_day(SUMMARY, SLEEP, HRV, READINESS, STATUS, PRED)
    assert d["resting_hr"] == 41 and d["sleep_score"] == 89 and d["hrv_last_night"] == 103
    assert d["readiness_score"] == 70 and d["training_status"] == "PRODUCTIVE_3"
    assert d["acwr"] == 1.2 and d["vo2max"] == 53.3 and d["predicted_5k"] == 1280
    assert d["body_battery_wake"] == 95 and d["steps"] == 11996


def test_parse_day_tolerates_missing_endpoints():
    assert parse_day(None, None, None, None, None, None) == {}
    assert parse_day({"averageStressLevel": -1}, {}, {}, [], {}, None).get("stress_avg") is None


def test_recovery_signals():
    good = {"hrv_last_night": 103, "hrv_baseline_low": 78, "resting_hr": 41, "resting_hr_7d_avg": 43,
            "sleep_seconds": 26000, "readiness_score": 80}
    assert [s["level"] for s in recovery_signals(good)] == ["good"]
    tired = {"hrv_last_night": 60, "hrv_baseline_low": 78, "resting_hr": 50, "resting_hr_7d_avg": 43,
             "sleep_seconds": 5 * 3600, "acwr": 1.6}
    assert {s["metric"] for s in recovery_signals(tired)} == {"hrv", "resting_hr", "sleep", "acwr"}


def test_training_status_label():
    assert training_status_label("PRODUCTIVE_3") == "Productive"
    assert training_status_label(None) is None


V2 = {"calendarDate": "2026-10-21", "heartRate": {"restingValue": 42}, "stress": {"avgLevel": 32},
      "bodyBattery": {"minValue": 15, "maxValue": 80, "latestValue": 20},
      "movement": {"steps": {"goal": 19340, "value": 18251}}, "pulseOx": {"avgValue": 95},
      "respiration": {"avgValue": 13}}


class RangeClient:
    def daily_summaries(self, start, end):
        return [V2]

    def sleep_range(self, start, end):
        return [{"calendarDate": "2026-10-21", "sleepTimeSeconds": 25000, "deepSleepSeconds": 3600,
                 "sleepScores": {"overall": {"value": 71, "qualifierKey": "FAIR"}}}]

    def hrv_range(self, start, end):
        return [{"calendarDate": "2026-10-21", "lastNightAvg": 90, "weeklyAvg": 85, "status": "BALANCED",
                 "baseline": {"balancedLow": 75, "balancedUpper": 110}}]


def test_personal_api_range_payloads_map_to_wellness_fields():
    assert flatten_summary(V2)["restingHeartRate"] == 42
    day = fetch_range(RangeClient(), date(2026, 10, 21), date(2026, 10, 21))["2026-10-21"]
    assert day["resting_hr"] == 42 and day["stress_avg"] == 32 and day["steps"] == 18251
    assert day["sleep_score"] == 71 and day["sleep_seconds"] == 25000
    assert day["hrv_last_night"] == 90 and day["hrv_baseline_low"] == 75
    assert "readiness_score" not in day  # not exposed by the Personal API


def test_good_signal_without_garmin_readiness():
    signals = recovery_signals({"hrv_last_night": 90, "hrv_baseline_low": 75, "sleep_seconds": 7.5 * 3600})
    assert [s["level"] for s in signals] == ["good"]
